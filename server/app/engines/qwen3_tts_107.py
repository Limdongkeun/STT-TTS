"""107 서버 Qwen3-TTS 시험 페이지(Gradio)를 불러 소리를 만드는 엔진.

107 에는 아무것도 저장하지 않는다. 고른 목소리 견본(app/data/voices/<이름>.wav)을 부를 때마다
Gradio 임시 올리기로 보내고, 복제 기능(run_clone)으로 그 목소리로 읽게 한다.

Gradio 6 호출 순서(2026-11-09 /gradio_api/info 로 확인):
    POST /gradio_api/upload                       견본 WAV → 107 임시 경로
    POST /gradio_api/call/run_clone {data: [...]} → {event_id}
    GET  /gradio_api/call/run_clone/{event_id}    이벤트 흐름, 'complete' 의 data[0] 이 결과 파일
    GET  <결과 파일 url>                           WAV
107 GPU 를 다른 기능과 같이 쓰므로 한 번에 한 문장씩만 부른다.
"""

import io
import json
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.engines.base import TtsResult

VOICES_DIR = Path(__file__).resolve().parents[1] / "data" / "voices"
VOICE_NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,32}$")
CLONE_API = "run_clone"
CONNECT_HINT = "회사 망에 있는지, 107 시험 페이지(:5110)가 켜져 있는지 확인하세요."


class Tts107Error(RuntimeError):
    """107 TTS 를 쓰지 못했다(연결·시간 초과·107 오류). 서버는 503 으로 돌려준다."""


@dataclass(frozen=True)
class VoiceSample:
    name: str
    label: str
    wav_bytes: bytes
    ref_text: str
    language: str


def load_voice(name: str, directory: Path = VOICES_DIR) -> VoiceSample:
    if not VOICE_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"목소리 이름 {name!r} 는 영문 소문자·숫자·- 만 쓸 수 있어요.")
    meta = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    wav_path = (directory / meta["wavFile"]).resolve()
    if wav_path.parent != directory.resolve():
        raise ValueError("목소리 견본 경로가 올바르지 않습니다.")
    ref_text = str(meta["refText"]).strip()
    if not ref_text:
        raise ValueError("목소리 견본의 refText 가 비었습니다.")
    return VoiceSample(
        name=name,
        label=str(meta["label"]),
        wav_bytes=wav_path.read_bytes(),
        ref_text=ref_text,
        language=str(meta.get("language", "Korean")),
    )


class Http(Protocol):
    def post_json(self, url: str, body: dict, timeout: float) -> object: ...
    def post_file(self, url: str, filename: str, data: bytes, timeout: float) -> object: ...
    def stream_lines(self, url: str, timeout: float) -> Iterator[str]: ...
    def get_bytes(self, url: str, timeout: float) -> bytes: ...


class UrllibHttp:
    """표준 라이브러리만 쓴다(의존성 추가 없음)."""

    def post_json(self, url: str, body: dict, timeout: float) -> object:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def post_file(self, url: str, filename: str, data: bytes, timeout: float) -> object:
        boundary = uuid.uuid4().hex
        head = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8")
        body = head + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def stream_lines(self, url: str, timeout: float) -> Iterator[str]:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            for raw in response:
                yield raw.decode("utf-8").rstrip("\r\n")

    def get_bytes(self, url: str, timeout: float) -> bytes:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()


def read_complete_event(lines: Iterator[str], deadline: float, clock: Callable[[], float]) -> list:
    """Gradio 이벤트 흐름에서 'complete' 의 data 를 꺼낸다. 'error' 나 시간 초과는 Tts107Error."""
    event = ""
    for line in lines:
        if clock() > deadline:
            raise Tts107Error("107 TTS 가 제시간에 소리를 만들지 못했어요.")
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:") and event in ("complete", "error"):
            payload = line[len("data:"):].strip()
            if event == "error":
                raise Tts107Error(f"107 TTS 가 소리를 만들지 못했어요: {payload[:120]}")
            data = json.loads(payload)
            if not isinstance(data, list) or not data:
                raise Tts107Error("107 TTS 응답 모양이 예상과 달라요.")
            return data
    raise Tts107Error("107 TTS 응답이 끝까지 오지 않았어요.")


def wav_result(data: bytes) -> TtsResult:
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            sample_rate = reader.getframerate()
            frames = reader.getnframes()
    except (wave.Error, EOFError) as exc:
        raise Tts107Error("107 TTS 가 WAV 가 아닌 파일을 돌려줬어요.") from exc
    if sample_rate <= 0 or frames <= 0:
        raise Tts107Error("107 TTS 가 빈 소리를 돌려줬어요.")
    return TtsResult(wav_bytes=data, sample_rate=sample_rate, duration_sec=frames / sample_rate)


class Qwen3Tts107Engine:
    name = "qwen3-tts-107"

    def __init__(
        self,
        base_url: str,
        voice: VoiceSample,
        timeout_sec: float,
        http: Http | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._voice = voice
        self._timeout_sec = timeout_sec
        self._http = http or UrllibHttp()
        self._clock = clock
        self._lock = threading.Lock()
        self.label = f"107 Qwen3-TTS · {voice.label}"

    def synthesize(self, text: str) -> TtsResult:
        with self._lock:
            try:
                return self._synthesize(text)
            except Tts107Error:
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise Tts107Error(f"107 TTS 에 연결하지 못했어요. {CONNECT_HINT}") from exc
            except (ValueError, KeyError, TypeError) as exc:
                raise Tts107Error("107 TTS 응답 모양이 예상과 달라요.") from exc

    def _synthesize(self, text: str) -> TtsResult:
        deadline = self._clock() + self._timeout_sec
        uploaded = self._http.post_file(
            f"{self._base_url}/gradio_api/upload", f"{self._voice.name}.wav", self._voice.wav_bytes, self._timeout_sec
        )
        if not isinstance(uploaded, list) or not uploaded or not isinstance(uploaded[0], str):
            raise Tts107Error("107 에 목소리 견본을 올리지 못했어요.")
        reference = {"path": uploaded[0], "meta": {"_type": "gradio.FileData"}}
        # run_clone 입력: 견본, 견본에서 말한 내용, '내용 없이 목소리만'(끔), 읽을 문장, 언어
        body = {"data": [reference, self._voice.ref_text, False, text, self._voice.language]}
        submitted = self._http.post_json(f"{self._base_url}/gradio_api/call/{CLONE_API}", body, self._timeout_sec)
        event_id = submitted["event_id"] if isinstance(submitted, dict) else None
        if not isinstance(event_id, str) or not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", event_id):
            raise Tts107Error("107 TTS 접수 번호를 받지 못했어요.")
        lines = self._http.stream_lines(f"{self._base_url}/gradio_api/call/{CLONE_API}/{event_id}", self._timeout_sec)
        data = read_complete_event(lines, deadline, self._clock)
        file_url = data[0].get("url") if isinstance(data[0], dict) else None
        # 결과 주소는 107 자신이어야 한다(다른 곳으로 요청이 새지 않게).
        if not isinstance(file_url, str) or not file_url.startswith(f"{self._base_url}/"):
            raise Tts107Error("107 TTS 결과 파일 주소가 예상과 달라요.")
        return wav_result(self._http.get_bytes(file_url, self._timeout_sec))
