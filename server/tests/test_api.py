import io
import shutil
import wave

import pytest
from fastapi.testclient import TestClient

from app.engines.mock import MOCK_TRANSCRIPT
from app.main import AudioStore, create_app
from app.settings import Settings

ffmpeg_required = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 필요")


def make_settings(**overrides) -> Settings:
    values = dict(
        stt_engine="mock",
        tts_engine="mock",
        answer_provider="fixed",
        asr_model_id="Qwen/Qwen3-ASR-1.7B",
        tts_model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        tts_speaker="Sohee",
        speech_language="Korean",
        model_device="cpu",
        model_dtype="float32",
        max_upload_bytes=1024 * 1024,
    )
    values.update(overrides)
    return Settings(**values)


def make_wav(seconds: float = 0.2, sample_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buffer.getvalue()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(make_settings()))


def test_health(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "sttEngine": "mock", "ttsEngine": "mock", "answerProvider": "fixed"}


@ffmpeg_required
def test_stt_with_wav(client):
    response = client.post("/stt", files={"audio": ("voice.wav", make_wav(), "audio/wav")})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == MOCK_TRANSCRIPT
    assert body["engine"] == "mock"
    assert body["elapsedMs"] >= 0


def test_stt_rejects_unknown_format(client):
    response = client.post("/stt", files={"audio": ("voice.exe", b"abc", "application/octet-stream")})
    assert response.status_code == 415


def test_stt_rejects_empty_file(client):
    response = client.post("/stt", files={"audio": ("voice.wav", b"", "audio/wav")})
    assert response.status_code == 400


def test_stt_rejects_too_large_file():
    small_client = TestClient(create_app(make_settings(max_upload_bytes=100)))
    response = small_client.post("/stt", files={"audio": ("voice.wav", make_wav(1.0), "audio/wav")})
    assert response.status_code == 413


@ffmpeg_required
def test_stt_rejects_broken_audio(client):
    response = client.post("/stt", files={"audio": ("voice.m4a", b"not audio at all", "audio/mp4")})
    assert response.status_code == 422


def test_ask_returns_answer_and_speech_text(client):
    body = client.post("/ask", json={"text": "내일 가족 일정 알려줘"}).json()
    assert "3시 30분" in body["answerText"]
    assert "세 시 삼십 분" in body["speechText"]
    assert body["provider"] == "fixed"


@pytest.mark.parametrize("text", ["", "가" * 501])
def test_ask_validates_length(client, text):
    assert client.post("/ask", json={"text": text}).status_code == 422


def test_tts_then_download_audio(client):
    body = client.post("/tts", json={"text": "안녕하세요"}).json()
    assert body["engine"] == "mock"
    assert body["audioUrl"].startswith("/audio/")
    audio = client.get(body["audioUrl"])
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content[:4] == b"RIFF"


def test_tts_rejects_blank_text(client):
    assert client.post("/tts", json={"text": "   "}).status_code == 400


@pytest.mark.parametrize("audio_id", ["../etc/passwd", "zz", "0" * 32])
def test_audio_unknown_or_invalid_id(client, audio_id):
    assert client.get(f"/audio/{audio_id}").status_code == 404


def test_audio_store_drops_oldest(tmp_path):
    store = AudioStore(tmp_path, limit=2)
    first = store.save(b"1")
    store.save(b"2")
    store.save(b"3")
    assert store.get(first) is None
    assert len(list(tmp_path.iterdir())) == 2
