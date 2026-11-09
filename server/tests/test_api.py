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
        "demoClock": "fixed",
        "sttHints": 0,
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
    # 시계를 직접 바꿔 시험하므로 실제 시각 모드로 띄운다.
    client = TestClient(create_app(make_settings(answer_provider="family-demo", demo_clock="real")))

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
    # 다른 주제로 넘어가면 복용 시각 대화는 끝나고, 답한 주제만 남는다.
    after = ask("아버지 병원 예약 언제였지", corrected["context"])["context"]
    assert after.get("dose_at") is None and after["last_topic"] == "father_hospital"


def test_prerecorded_answer_is_downloadable_and_labeled():
    from app.family_demo import FamilyDemoAnswerProvider
    from app.normalize import normalize_for_speech

    client = TestClient(create_app(make_settings(tts_engine="prerecorded")))
    text, _ = FamilyDemoAnswerProvider().answer("장보기 목록 뭐 남았어?")
    response = client.post("/tts", json={"text": normalize_for_speech(text)})
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "prerecorded"
    assert body["durationSec"] > 1
    assert client.get(body["audioUrl"]).content[:4] == b"RIFF"
    assert "JISOO" in client.get("/health").json()["ttsModel"]


def test_prerecorded_rejects_a_different_answer():
    client = TestClient(create_app(make_settings(tts_engine="prerecorded")))
    response = client.post("/tts", json={"text": "장보기 목록은 사과예요."})
    assert response.status_code == 404
    assert "일치하는 사전 음성" in response.json()["detail"]


def test_all_25_recordings_match_their_manifest():
    import json

    from app.engines.prerecorded import DEFAULT_RECORDINGS_DIR, PrerecordedTtsEngine

    manifest = json.loads((DEFAULT_RECORDINGS_DIR / "manifest.json").read_text())
    engine = PrerecordedTtsEngine()
    assert len(manifest["recordings"]) == 25
    for item in manifest["recordings"]:
        result = engine.synthesize(item["speechText"])
        assert result.sample_rate == 24000
        assert abs(result.duration_sec - item["durationSec"]) < 0.01


def test_prerecorded_c1_to_c7_including_dynamic_dose_times():
    from app.test_sheet import TEST_CASES

    client = TestClient(create_app(make_settings(tts_engine="prerecorded", answer_provider="family-demo")))
    context = None
    for case in TEST_CASES:
        if not case["id"].startswith("C"):
            continue
        response = client.post("/ask", json={"text": case["say"], "context": context})
        assert response.status_code == 200
        answer = response.json()
        context = answer.get("context")
        if case["id"] in ("C4", "C5"):
            assert "시험 기록에 " in answer["answerText"]
            assert "말씀하신 시각으로" in answer["speechText"]
        audio = client.post("/tts", json={"text": answer["speechText"]})
        assert audio.status_code == 200, (case["id"], audio.text)
        assert client.get(audio.json()["audioUrl"]).content[:4] == b"RIFF"


def test_prerecorded_ignores_spacing_and_punctuation():
    """폰 STT 가 띄어 쓴 말('퇴근 길에')이 답에 들어가도 녹음('퇴근길에')을 찾는다."""
    from app.engines.prerecorded import PrerecordedTtsEngine, canonical_text

    engine = PrerecordedTtsEngine()
    spaced = "남편에게 '퇴근 길에 약국 들러' 부탁을 보냈어요"
    assert engine.synthesize(spaced).sample_rate == 24000
    assert canonical_text(" 두부, 계란 ") == "두부계란"


def test_prerecorded_keys_are_unique_after_compacting():
    import json

    from app.engines.prerecorded import DEFAULT_RECORDINGS_DIR, canonical_text

    texts = []
    for folder in (DEFAULT_RECORDINGS_DIR, DEFAULT_RECORDINGS_DIR.parent / "c1-c7"):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        texts += [canonical_text(item["speechText"]) for item in manifest["recordings"]]
    assert len(texts) == 32 and len(set(texts)) == 32


def test_family_demo_answers_at_fixed_test_time_by_default():
    # 녹음은 11월 5일 기준('28일 남았어요'). 시험하는 날이 달라도 같은 답이 나와야 녹음과 맞는다.
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))
    assert "28일 남았어요" in client.post("/ask", json={"text": "자동차 보험 언제 끝나?"}).json()["answerText"]


def test_family_demo_real_clock_uses_now(monkeypatch):
    from datetime import datetime

    from app import family_demo

    seen = []
    original = family_demo.FamilyDemoAnswerProvider.answer

    def spy(self, question, context=None, *, speaker="wife", now=None):
        seen.append(now)
        return original(self, question, context, speaker=speaker, now=now)

    monkeypatch.setattr(family_demo.FamilyDemoAnswerProvider, "answer", spy)
    for clock, expected in (("fixed", family_demo.DEMO_NOW), ("real", None)):
        client = TestClient(create_app(make_settings(answer_provider="family-demo", demo_clock=clock)))
        assert client.post("/ask", json={"text": "자동차 보험 언제 끝나?"}).status_code == 200
        assert seen[-1] == expected
    assert isinstance(family_demo.DEMO_NOW, datetime)


def test_ask_returns_corrected_text_for_family_demo():
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))
    body = client.post("/ask", json={"text": "수연이 이번 주 학교 일정 뭐야?"}).json()
    assert body["correctedText"].startswith("소윤이")
    fixed = TestClient(create_app(make_settings(answer_provider="fixed"))).post("/ask", json={"text": "안녕"}).json()
    assert "correctedText" not in fixed
