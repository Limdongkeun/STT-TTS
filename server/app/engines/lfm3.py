"""LFM3-Audio-2B 받아쓰기·TTS (llama.cpp 서버를 8002 안에서 띄워 부른다, 2026-11-16 사용자 요청).

맥에만 둔 실행 파일·모델(server/.lfm3/, git 밖)로 llama-server 를 127.0.0.1 에만 띄운다(바깥 접속 없음).
    받아쓰기: POST /v1/chat/completions  system "Perform ASR in Korean." + input_audio(wav base64)
    TTS:      POST /tts {input, lang: ko, voice: female|male, seed}  → wav
API 모양은 llama.cpp tools/server/README.md·docs/multimodal/tts.md(LFM3-Audio) 기준.
목소리는 여자·남자 둘뿐이다(목소리 복제 없음). seed 를 고정해 같은 글은 같은 말투로 읽는다.
"""

import atexit
import base64
import json
import logging
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Protocol

from app.engines.base import SttResult, TtsResult
from app.engines.qwen3_tts_107 import Tts107Error, wav_result
from app.settings import LFM3_MMPROJ_FILE as MMPROJ_FILE
from app.settings import LFM3_MODEL_FILE as MODEL_FILE
from app.settings import LFM3_SERVER_FILE as SERVER_FILE
from app.settings import LFM3_STT_ENGINE, LFM3_TTS_ENGINES, lfm3_files_ready as files_ready

logger = logging.getLogger("uvicorn.error")

MODEL_LABEL = "LFM3-Audio-2B"
VOICE_LABELS = {"female": "여자 목소리", "male": "남자 목소리"}
TTS_SEED = 7
START_TIMEOUT_SEC = 90
REQUEST_TIMEOUT_SEC = 60


class Lfm3Error(RuntimeError):
    """LFM3 를 지금 못 쓴다(실행 파일 없음·띄우기 실패·시간 초과). 서버는 503 으로 돌려준다."""


class Http(Protocol):
    def post_json(self, url: str, body: dict, timeout: float) -> bytes: ...

    def get_ok(self, url: str, timeout: float) -> bool: ...


class UrllibHttp:
    def post_json(self, url: str, body: dict, timeout: float) -> bytes:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 127.0.0.1 고정
            return response.read()

    def get_ok(self, url: str, timeout: float) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - 127.0.0.1 고정
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False


class Lfm3Runtime:
    """llama-server 하나를 띄우고(처음 부를 때 준비될 때까지 기다린다) 8002 가 끝날 때 함께 끈다."""

    def __init__(
        self,
        directory: Path,
        port: int,
        http: Http | None = None,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._directory = directory
        self.base_url = f"http://127.0.0.1:{port}"
        self._port = port
        self._http = http or UrllibHttp()
        self._popen = popen
        self._clock = clock
        self._sleep = sleep
        self._process: subprocess.Popen | None = None
        self._ready = False
        self._lock = threading.Lock()
        # 같은 모델을 동시에 두 번 부르지 않는다(받아쓰기·TTS·미리 만들기가 겹쳐도 차례로).
        self.call_lock = threading.Lock()

    def start(self) -> None:
        """llama-server 를 띄운다(기다리지 않는다). 이미 그 자리에 떠 있으면 그것을 쓴다."""
        with self._lock:
            if self._process is not None or self._http.get_ok(f"{self.base_url}/health", 1):
                return
            if not files_ready(self._directory):
                raise Lfm3Error(f"LFM3 실행 파일·모델이 없어요: {self._directory}")
            command = [
                str(self._directory / SERVER_FILE),
                "-m", str(self._directory / MODEL_FILE),
                "-mm", str(self._directory / MMPROJ_FILE),
                "--host", "127.0.0.1",
                "--port", str(self._port),
            ]
            log = (self._directory / "llama-server.log").open("ab")
            self._process = self._popen(command, stdout=log, stderr=subprocess.STDOUT)
            atexit.register(self.stop)
            logger.info("LFM3 llama-server 띄움 (127.0.0.1:%d)", self._port)

    def ensure_ready(self) -> str:
        """준비될 때까지 기다리고 주소를 돌려준다. 꺼졌거나 오래 걸리면 Lfm3Error."""
        if self._ready:
            return self.base_url
        self.start()
        deadline = self._clock() + START_TIMEOUT_SEC
        while self._clock() < deadline:
            if self._process is not None and self._process.poll() is not None:
                self._process = None
                raise Lfm3Error("LFM3 서버가 꺼졌어요. server/.lfm3/llama-server.log 를 확인하세요.")
            if self._http.get_ok(f"{self.base_url}/health", 2):
                self._ready = True
                return self.base_url
            self._sleep(0.5)
        raise Lfm3Error(f"LFM3 서버가 {START_TIMEOUT_SEC}초 안에 준비되지 않았어요.")

    def post(self, path: str, body: dict) -> bytes:
        url = self.ensure_ready()
        with self.call_lock:
            try:
                return self._http.post_json(f"{url}{path}", body, REQUEST_TIMEOUT_SEC)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._ready = False
                raise Lfm3Error(f"LFM3 서버를 부르지 못했어요: {exc}") from exc

    def stop(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            self._ready = False
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


_RUNTIMES: dict[tuple[str, int], Lfm3Runtime] = {}


def get_runtime(directory: str, port: int) -> Lfm3Runtime:
    """같은 폴더·포트는 llama-server 하나를 같이 쓴다(STT·TTS 여자·남자)."""
    key = (directory, port)
    if key not in _RUNTIMES:
        _RUNTIMES[key] = Lfm3Runtime(Path(directory), port)
    return _RUNTIMES[key]


class Lfm3SttEngine:
    name = LFM3_STT_ENGINE
    label = MODEL_LABEL

    def __init__(self, runtime: Lfm3Runtime, language: str = "Korean") -> None:
        self._runtime = runtime
        self._language = language

    def transcribe(self, wav_path: Path) -> SttResult:
        audio = base64.b64encode(wav_path.read_bytes()).decode("ascii")
        body = {
            "messages": [
                {"role": "system", "content": f"Perform ASR in {self._language}."},
                {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": audio, "format": "wav"}}]},
            ],
            "temperature": 0,
        }
        try:
            reply = json.loads(self._runtime.post("/v1/chat/completions", body))
            text = reply["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise Lfm3Error("LFM3 받아쓰기 응답 모양이 예상과 달라요.") from exc
        return SttResult(text=str(text or "").strip(), language=self._language)


class Lfm3TtsEngine:
    def __init__(self, runtime: Lfm3Runtime, engine_name: str) -> None:
        self.name = engine_name
        self._voice = LFM3_TTS_ENGINES[engine_name]
        self._runtime = runtime
        self.label = f"{MODEL_LABEL} · {VOICE_LABELS[self._voice]}"

    def synthesize(self, text: str) -> TtsResult:
        data = self._runtime.post("/tts", {"input": text, "lang": "ko", "voice": self._voice, "seed": TTS_SEED})
        try:
            return wav_result(data)
        except Tts107Error as exc:  # 소리 파일 읽기 도우미를 107 엔진과 같이 쓴다
            raise Lfm3Error("LFM3 TTS 가 소리 파일을 돌려주지 않았어요.") from exc
