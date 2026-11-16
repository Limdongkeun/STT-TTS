"""LFM3-Audio(llama.cpp) 받아쓰기·TTS 를 8002 에서 고르기(2026-11-16). 실제 llama-server 는 띄우지 않는다."""

import io
import json
import shutil
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engines import lfm3
from app.engines.lfm3 import Lfm3Error, Lfm3Runtime, Lfm3SttEngine, Lfm3TtsEngine
from app.main import create_app
from app.settings import (
    LFM3_MMPROJ_FILE, LFM3_MODEL_FILE, LFM3_SERVER_FILE, load_settings, stt_choices, tts_choices,
)
from tests.test_api import make_settings, make_wav

ffmpeg_required = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 필요")


def tts_wav(seconds: float = 0.5, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x01\x00" * int(seconds * rate))
    return buffer.getvalue()


class FakeHttp:
    def __init__(self, healthy=True, replies=None):
        self.healthy = healthy
        self.replies = replies or {}
        self.posts: list[tuple[str, dict]] = []

    def get_ok(self, url, timeout):
        return self.healthy

    def post_json(self, url, body, timeout):
        self.posts.append((url, body))
        reply = self.replies[url.rsplit(":", 1)[-1].split("/", 1)[-1]]
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_lfm3_dir(tmp_path: Path) -> Path:
    for name in (LFM3_SERVER_FILE, LFM3_MODEL_FILE, LFM3_MMPROJ_FILE):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


class FakeProcess:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code
        self.terminated = False

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def test_choices_only_when_lfm3_files_exist(tmp_path, monkeypatch):
    with_lfm3 = make_settings(lfm3_dir=str(tmp_path))
    assert tts_choices(with_lfm3) == ("prerecorded", "lfm3-tts-female", "lfm3-tts-male", "mock")
    assert stt_choices(with_lfm3) == ("mock", "lfm3-asr")
    assert stt_choices(make_settings()) == ("mock",)
    # load_settings: auto 는 파일이 다 있을 때만 켠다. off 면 끈다. LFM3 TTS 를 기본으로 하려면 파일이 있어야 한다.
    monkeypatch.setenv("LFM3_DIR", str(tmp_path))
    assert load_settings().lfm3_dir == ""
    make_lfm3_dir(tmp_path)
    assert load_settings().lfm3_dir == str(tmp_path)
    monkeypatch.setenv("LFM3", "off")
    assert load_settings().lfm3_dir == ""
    monkeypatch.setenv("TTS_ENGINE", "lfm3-tts-male")
    with pytest.raises(ValueError):
        load_settings()


def test_runtime_starts_llama_server_on_localhost_only(tmp_path):
    started = []
    runtime = Lfm3Runtime(
        make_lfm3_dir(tmp_path), 8091, http=FakeHttp(healthy=False),
        popen=lambda command, **kwargs: started.append(command) or FakeProcess(),
    )
    runtime.start()
    runtime.start()  # 두 번 불러도 하나만
    assert len(started) == 1
    command = started[0]
    assert command[0].endswith(LFM3_SERVER_FILE)
    assert command[command.index("--host") + 1] == "127.0.0.1" and command[command.index("--port") + 1] == "8091"


def test_runtime_reuses_running_server_and_reports_failures(tmp_path):
    started = []
    reuse = Lfm3Runtime(tmp_path, 8091, http=FakeHttp(healthy=True), popen=lambda c, **k: started.append(c))
    assert reuse.ensure_ready() == "http://127.0.0.1:8091" and started == []
    # 실행 파일이 없으면 띄우지 못한다
    with pytest.raises(Lfm3Error):
        Lfm3Runtime(tmp_path / "none", 8091, http=FakeHttp(healthy=False)).start()
    # 띄웠는데 바로 꺼지면 알린다
    died = Lfm3Runtime(
        make_lfm3_dir(tmp_path), 8091, http=FakeHttp(healthy=False),
        popen=lambda c, **k: FakeProcess(exit_code=1), sleep=lambda s: None,
    )
    with pytest.raises(Lfm3Error):
        died.ensure_ready()
    # 오래 준비되지 않으면 시간 초과
    ticks = iter(range(0, 1000, 10))
    slow = Lfm3Runtime(
        tmp_path, 8091, http=FakeHttp(healthy=False), popen=lambda c, **k: FakeProcess(),
        clock=lambda: next(ticks), sleep=lambda s: None,
    )
    with pytest.raises(Lfm3Error):
        slow.ensure_ready()


def test_stop_terminates_the_server_it_started(tmp_path):
    process = FakeProcess()
    runtime = Lfm3Runtime(make_lfm3_dir(tmp_path), 8091, http=FakeHttp(healthy=False), popen=lambda c, **k: process)
    runtime.start()
    runtime.stop()
    assert process.terminated


def test_stt_sends_audio_with_asr_prompt(tmp_path):
    reply = json.dumps({"choices": [{"message": {"content": " 가스비 얼마 내야 돼? "}}]}).encode()
    http = FakeHttp(replies={"v1/chat/completions": reply})
    engine = Lfm3SttEngine(Lfm3Runtime(tmp_path, 8091, http=http))
    wav = tmp_path / "in.wav"
    wav.write_bytes(make_wav())
    assert engine.transcribe(wav).text == "가스비 얼마 내야 돼?"
    body = http.posts[0][1]
    assert body["messages"][0] == {"role": "system", "content": "Perform ASR in Korean."}
    assert body["messages"][1]["content"][0]["type"] == "input_audio" and body["temperature"] == 0
    # 응답 모양이 다르면 Lfm3Error
    http.replies["v1/chat/completions"] = b'{"choices": []}'
    with pytest.raises(Lfm3Error):
        engine.transcribe(wav)


def test_tts_uses_korean_voice_and_fixed_seed(tmp_path):
    http = FakeHttp(replies={"tts": tts_wav()})
    engine = Lfm3TtsEngine(Lfm3Runtime(tmp_path, 8091, http=http), "lfm3-tts-male")
    result = engine.synthesize("가스비 사만 이천 원은 아직 안 냈어요.")
    assert result.sample_rate == 24000 and round(result.duration_sec, 1) == 0.5
    assert http.posts[0][1] == {"input": "가스비 사만 이천 원은 아직 안 냈어요.", "lang": "ko", "voice": "male", "seed": 7}
    assert engine.label == "LFM3-Audio-2B · 남자 목소리"
    http.replies["tts"] = b"not a wav"
    with pytest.raises(Lfm3Error):
        engine.synthesize("안녕")
    http.replies["tts"] = OSError("refused")
    with pytest.raises(Lfm3Error):
        engine.synthesize("안녕")


@pytest.fixture
def lfm3_app(tmp_path, monkeypatch):
    """LFM3 를 고를 수 있는 서버. llama-server 대신 가짜 응답을 쓴다."""
    http = FakeHttp(replies={
        "v1/chat/completions": json.dumps({"choices": [{"message": {"content": "장보기 목록 뭐 남았어?"}}]}).encode(),
        "tts": tts_wav(),
    })
    monkeypatch.setattr(lfm3, "_RUNTIMES", {(str(tmp_path), 8090): Lfm3Runtime(tmp_path, 8090, http=http)})
    settings = make_settings(lfm3_dir=str(tmp_path), answer_provider="family-demo", tts_engine="prerecorded")
    return TestClient(create_app(settings)), http


def test_health_lists_lfm3_stt_and_tts(lfm3_app):
    client, _ = lfm3_app
    body = client.get("/health").json()
    assert body["sttChoices"] == [
        {"engine": "mock", "label": "서버 mock STT"},
        {"engine": "lfm3-asr", "label": "LFM3-Audio-2B"},
    ]
    labels = {choice["engine"]: choice["label"] for choice in body["ttsChoices"]}
    assert labels["lfm3-tts-female"] == "LFM3-Audio-2B · 여자 목소리 · 입말"
    assert labels["lfm3-tts-male"] == "LFM3-Audio-2B · 남자 목소리 · 입말"


@ffmpeg_required
def test_stt_picks_engine_per_request(lfm3_app):
    client, http = lfm3_app
    chosen = client.post("/stt", files={"audio": ("v.wav", make_wav(), "audio/wav")}, data={"engine": "lfm3-asr"})
    assert chosen.status_code == 200
    assert (chosen.json()["engine"], chosen.json()["text"]) == ("lfm3-asr", "장보기 목록 뭐 남았어?")
    default = client.post("/stt", files={"audio": ("v.wav", make_wav(), "audio/wav")})
    assert default.json()["engine"] == "mock"
    unknown = client.post("/stt", files={"audio": ("v.wav", make_wav(), "audio/wav")}, data={"engine": "whisper"})
    assert unknown.status_code == 422
    http.replies["v1/chat/completions"] = OSError("refused")
    down = client.post("/stt", files={"audio": ("v.wav", make_wav(), "audio/wav")}, data={"engine": "lfm3-asr"})
    assert down.status_code == 503


def test_tts_and_ask_with_lfm3_voice(lfm3_app):
    client, http = lfm3_app
    # LFM3 도 입말 문장을 읽는다(그때그때 만드는 TTS)
    answer = client.post("/ask", json={"text": "가스비 얼마 내야 돼?", "ttsEngine": "lfm3-tts-female"}).json()
    assert "사만 이천" in answer["speechText"]
    spoken = client.post("/tts", json={"text": answer["speechText"], "engine": "lfm3-tts-female"})
    assert spoken.status_code == 200 and spoken.json()["engine"] == "lfm3-tts-female"
    assert http.posts[-1][1]["voice"] == "female"
    http.replies["tts"] = OSError("refused")
    assert client.post("/tts", json={"text": "안녕", "engine": "lfm3-tts-male"}).status_code == 503
