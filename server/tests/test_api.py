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
    assert body == {
        "status": "ok",
        "sttEngine": "mock",
        "sttModel": "",
        "ttsEngine": "mock",
        "ttsModel": "",
        "answerProvider": "fixed",
    }


def test_health_names_real_models_without_loading_them():
    settings = make_settings(stt_engine="qwen3-asr", tts_engine="qwen3-tts", asr_model_id="Qwen/Qwen3-ASR-0.6B")
    body = TestClient(create_app(settings)).get("/health").json()
    assert (body["sttModel"], body["ttsModel"]) == ("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")


def test_health_shows_family_demo_provider():
    body = TestClient(create_app(make_settings(answer_provider="family-demo"))).get("/health").json()
    assert body["answerProvider"] == "family-demo"


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


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("다음주 우리집 일정 뭐야?", "화요일에 가족 식사"),
        ("소윤이 이번주 학교 학원 일정 뭐야", "수요일에 학교 체험학습"),
        ("아버지 병원 예약 언제였지", "11월 12일 목요일 오전 10시"),
        ("소윤이 다음 주 학교 학원 일정 뭐야", "이번 주 학교와 학원 일정만"),
    ],
)
def test_family_demo_routes_questions(question, expected):
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))
    answer = client.post("/ask", json={"text": question}).json()
    assert answer["provider"] == "family-demo"
    assert expected in answer["answerText"]
    assert answer["speechText"]


def test_family_demo_carries_dose_across_turns_and_corrects_it(monkeypatch):
    from datetime import datetime

    from app import family_demo

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 4, 16, 0, tzinfo=tz)

    monkeypatch.setattr(family_demo, "datetime", FixedClock)
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))

    def ask(text, context=None):
        response = client.post("/ask", json={"text": text, "context": context})
        assert response.status_code == 200
        return response.json()

    first = ask("애기 해열제 부르펜 계열 먹었는데 시간 체크해줘")
    assert first["answerText"] == "몇 시에 먹였나요?"
    assert "dose_at" not in first["context"]
    assert "context" not in ask("30분 전에 먹였어")
    second = ask("30분전에 먹였어", first["context"])
    assert "오후 3시 30분" in second["answerText"]
    assert "가상 일정에 등록된 다음 복용 예정 시각은 오후 9시" in second["answerText"]
    corrected = ask("아니, 30분 전이 아니라 한 시간 전이야", second["context"])
    assert "오후 3시" in corrected["answerText"]
    assert "수정했어요" in corrected["answerText"]
    assert corrected["context"]["dose_at"] == "2026-11-04T15:00:00+09:00"
    assert "context" not in ask("아버지 병원 예약 언제였지", corrected["context"])
