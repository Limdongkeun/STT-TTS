import io
import json
import urllib.error
import wave

import pytest
from fastapi.testclient import TestClient

from app.engines import create_tts_engine
from app.engines.qwen3_tts_107 import (
    VOICES_DIR,
    Qwen3Tts107Engine,
    Tts107Error,
    VoiceSample,
    load_voice,
    read_complete_event,
)
from app.main import create_app
from app.settings import load_settings
from tests.test_api import make_settings

BASE = "http://107.test:5110"
VOICE = VoiceSample(name="g", label="G 목소리", wav_bytes=b"RIFFvoice", ref_text="견본 문장이에요.", language="Korean")


def make_wav(seconds: float = 0.5, sample_rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buffer.getvalue()


class FakeHttp:
    """107 Gradio 대신 정해진 응답을 돌려주고, 받은 요청을 적어 둔다."""

    def __init__(self, lines=None, file_url=f"{BASE}/gradio_api/file=/tmp/out.wav", wav=None, fail=None):
        self.calls = []
        self.lines = lines
        self.file_url = file_url
        self.wav = make_wav() if wav is None else wav
        self.fail = fail

    def post_file(self, url, filename, data, timeout):
        self.calls.append(("upload", url, filename, data))
        if self.fail:
            raise self.fail
        return ["/tmp/gradio/g.wav"]

    def post_json(self, url, body, timeout):
        self.calls.append(("call", url, body))
        return {"event_id": "abc123"}

    def stream_lines(self, url, timeout):
        self.calls.append(("stream", url))
        complete = json.dumps([{"path": "/tmp/out.wav", "url": self.file_url}, "만드는 데 1초"])
        yield from self.lines or ["event: heartbeat", "data: null", "event: complete", f"data: {complete}"]

    def get_bytes(self, url, timeout):
        self.calls.append(("download", url))
        return self.wav


def make_engine(http, timeout_sec=90, clock=None):
    kwargs = {"clock": clock} if clock else {}
    return Qwen3Tts107Engine(BASE + "/", VOICE, timeout_sec, http=http, **kwargs)


def test_synthesize_uploads_voice_and_calls_clone_with_text():
    http = FakeHttp()
    result = make_engine(http).synthesize("가스비는 아내가 냈어요.")

    assert result.sample_rate == 24000
    assert result.duration_sec == pytest.approx(0.5)
    upload, call, stream, download = http.calls
    assert upload == ("upload", f"{BASE}/gradio_api/upload", "g.wav", b"RIFFvoice")
    assert call[1] == f"{BASE}/gradio_api/call/run_clone"
    assert call[2]["data"] == [
        {"path": "/tmp/gradio/g.wav", "meta": {"_type": "gradio.FileData"}},
        "견본 문장이에요.",
        False,
        "가스비는 아내가 냈어요.",
        "Korean",
    ]
    assert stream == ("stream", f"{BASE}/gradio_api/call/run_clone/abc123")
    assert download == ("download", f"{BASE}/gradio_api/file=/tmp/out.wav")


def test_label_names_voice():
    assert make_engine(FakeHttp()).label == "107 Qwen3-TTS · G 목소리"


def test_error_event_becomes_tts107_error():
    http = FakeHttp(lines=["event: error", 'data: "CUDA out of memory"'])
    with pytest.raises(Tts107Error, match="만들지 못했어요"):
        make_engine(http).synthesize("안녕")


def test_connection_failure_gives_network_hint():
    http = FakeHttp(fail=urllib.error.URLError("no route"))
    with pytest.raises(Tts107Error, match="회사 망"):
        make_engine(http).synthesize("안녕")


def test_timeout_while_waiting_for_result():
    ticks = iter([0.0, 5.0, 100.0, 200.0])
    http = FakeHttp(lines=["event: heartbeat", "data: null", "event: heartbeat", "data: null"])
    with pytest.raises(Tts107Error, match="제시간"):
        make_engine(http, timeout_sec=60, clock=lambda: next(ticks)).synthesize("안녕")


def test_result_url_must_point_to_107():
    http = FakeHttp(file_url="http://elsewhere.test/out.wav")
    with pytest.raises(Tts107Error, match="주소"):
        make_engine(http).synthesize("안녕")
    assert not any(call[0] == "download" for call in http.calls)


@pytest.mark.parametrize("wav", [b"not a wav", make_wav(seconds=0)])
def test_bad_audio_is_rejected(wav):
    with pytest.raises(Tts107Error):
        make_engine(FakeHttp(wav=wav)).synthesize("안녕")


def test_stream_that_ends_without_result():
    with pytest.raises(Tts107Error, match="끝까지"):
        read_complete_event(iter(["event: heartbeat", "data: null"]), deadline=10, clock=lambda: 0.0)


def test_bundled_voice_g_loads():
    voice = load_voice("g")
    assert voice.label == "G 목소리"
    assert voice.wav_bytes.startswith(b"RIFF")
    assert voice.ref_text.startswith("다음 주 가족 일정은")


@pytest.mark.parametrize("name", ["../g", "G", "", "a" * 33])
def test_voice_name_is_validated(name):
    with pytest.raises(ValueError):
        load_voice(name)


def test_voice_wav_must_stay_in_voices_dir(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"label": "x", "wavFile": "../escape.wav", "refText": "글"}))
    with pytest.raises(ValueError):
        load_voice("x", directory=tmp_path)


def test_settings_require_url_for_107(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "qwen3-tts-107")
    monkeypatch.delenv("TTS_107_URL", raising=False)
    with pytest.raises(ValueError, match="TTS_107_URL"):
        load_settings()


@pytest.mark.parametrize("url", ["ftp://107:5110", "192.168.0.1:5110"])
def test_settings_reject_non_http_url(monkeypatch, url):
    monkeypatch.setenv("TTS_ENGINE", "qwen3-tts-107")
    monkeypatch.setenv("TTS_107_URL", url)
    with pytest.raises(ValueError):
        load_settings()


def test_settings_read_107_values(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "qwen3-tts-107")
    monkeypatch.setenv("TTS_107_URL", "http://107.test:5110/")
    monkeypatch.setenv("TTS_107_TIMEOUT_SEC", "30")
    settings = load_settings()
    assert (settings.tts107_url, settings.tts107_voice, settings.tts107_timeout_sec) == ("http://107.test:5110", "g", 30)


def test_factory_builds_107_engine_without_calling_107():
    engine = create_tts_engine(make_settings(tts_engine="qwen3-tts-107", tts107_url=BASE))
    assert engine.name == "qwen3-tts-107"
    assert VOICES_DIR.joinpath("g.wav").exists()


def test_factory_builds_h2_engine_with_its_own_voice():
    """2026-11-12: H2 목소리를 따로 고를 수 있다. TTS_107_VOICE 를 바꿔도 H2 엔진은 h2 견본을 쓴다."""
    engine = create_tts_engine(make_settings(tts_engine="qwen3-tts-107-h2", tts107_url=BASE, tts107_voice="g"))
    assert (engine.name, engine.label) == ("qwen3-tts-107-h2", "107 Qwen3-TTS · H2 목소리")
    voice = load_voice("h2")
    assert voice.ref_text.startswith("안녕하세요!") and voice.wav_bytes[:4] == b"RIFF"


def test_h2_engine_sends_h2_sample_and_shares_one_lock():
    from app.engines import qwen3_tts_107

    http = FakeHttp()
    engine = Qwen3Tts107Engine(BASE, load_voice("h2"), 30, http=http, engine_name="qwen3-tts-107-h2")
    engine.synthesize("소윤이는 수요일에 체험학습 가고요.")
    upload = next(call for call in http.calls if call[0] == "upload")
    clone = next(call for call in http.calls if call[0] == "call")
    assert upload[2] == "h2.wav"
    assert clone[2]["data"][1] == load_voice("h2").ref_text
    # G·H2 엔진이 따로 있어도 107 은 한 번에 하나씩(잠금 하나를 같이 쓴다)
    assert not hasattr(engine, "_lock") and hasattr(qwen3_tts_107.CALL_LOCK, "acquire")


class FailingEngine:
    name = "qwen3-tts-107"
    label = "107 Qwen3-TTS · G 목소리"

    def synthesize(self, text):
        raise Tts107Error("107 TTS 에 연결하지 못했어요. 회사 망에 있는지 확인하세요.")


def test_api_returns_503_and_health_label(monkeypatch):
    monkeypatch.setattr("app.main.create_tts_engine", lambda settings: FailingEngine())
    client = TestClient(create_app(make_settings(tts_engine="qwen3-tts-107", tts107_url=BASE)))

    response = client.post("/tts", json={"text": "안녕하세요"})
    assert response.status_code == 503
    assert "107 TTS" in response.json()["detail"]
    assert client.get("/health").json()["ttsModel"] == "107 Qwen3-TTS · G 목소리"
