"""ElevenLabs v4 Turbo TTS(여자 Anna Kim·남자 Chris)를 8002 에서 고르기(2026-11-17 사용자 허락). 실제 ElevenLabs 는 부르지 않는다."""

import io
import json
import subprocess
import urllib.error
import wave

import pytest
from fastapi.testclient import TestClient

from app.engines.elevenlabs import ElevenLabsError, ElevenLabsTtsEngine, read_api_key
from app.main import create_app
from app.settings import load_settings, tts_choices
from tests.test_api import make_settings


def test_engine_sends_turbo_model_and_wraps_pcm_as_wav():
    calls = []

    def post(url, body, key):
        calls.append((url, json.loads(body), key))
        return b"\x01\x00" * 24000  # 1초

    engine = ElevenLabsTtsEngine("elevenlabs-v4-turbo-female", key_reader=lambda: "k", post=post, voice_id="voice1")
    result = engine.synthesize("네, 적어 뒀어요.")
    url, body, key = calls[0]
    assert "/v1/text-to-speech/voice1/stream?output_format=pcm_24000" in url
    assert body == {"text": "네, 적어 뒀어요.", "model_id": "eleven_v4_turbo"} and key == "k"
    with wave.open(io.BytesIO(result.wav_bytes)) as reader:
        assert (reader.getframerate(), reader.getnframes()) == (24000, 24000)
    assert result.duration_sec == 1.0


def test_engine_errors_become_elevenlabs_error():
    with pytest.raises(ElevenLabsError):
        ElevenLabsTtsEngine("elevenlabs-v4-turbo-female", key_reader=lambda: "", post=lambda *a: b"").synthesize("안녕")

    def refused(url, body, key):
        raise urllib.error.HTTPError(url, 401, "no", {}, io.BytesIO(b'{"detail":"quota_exceeded"}'))

    with pytest.raises(ElevenLabsError, match="401"):
        ElevenLabsTtsEngine("elevenlabs-v4-turbo-female", key_reader=lambda: "k", post=refused).synthesize("안녕")
    with pytest.raises(ElevenLabsError):
        ElevenLabsTtsEngine("elevenlabs-v4-turbo-female", key_reader=lambda: "k", post=lambda *a: b"").synthesize("안녕")


def test_key_reader_prefers_env_then_keychain(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", " envkey ")
    assert read_api_key(run=lambda *a, **k: pytest.fail("키체인을 보면 안 됨")) == "envkey"
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    found = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="chainkey\n", stderr="")
    assert read_api_key(run=found) == "chainkey"
    missing = lambda *a, **k: subprocess.CompletedProcess(a, 44, stdout="", stderr="")
    assert read_api_key(run=missing) == ""


def test_choice_only_when_enabled(monkeypatch):
    on = tts_choices(make_settings(elevenlabs=True))
    assert "elevenlabs-v4-turbo-female" in on and "elevenlabs-v4-turbo-male" in on and "elevenlabs-v4-turbo" not in on
    assert not any(name.startswith("elevenlabs") for name in tts_choices(make_settings()))
    monkeypatch.setenv("ELEVENLABS", "off")
    assert load_settings().elevenlabs is False
    monkeypatch.setenv("ELEVENLABS", "auto")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    assert load_settings().elevenlabs is True


def test_api_reads_spoken_and_reports_failures(monkeypatch):
    from app.engines import elevenlabs

    monkeypatch.setattr(elevenlabs.ElevenLabsTtsEngine, "synthesize",
                        lambda self, text: elevenlabs.TtsResult(elevenlabs.pcm_to_wav(b"\x01\x00" * 2400), 24000, 0.1))
    client = TestClient(create_app(make_settings(elevenlabs=True, answer_provider="family-demo", tts_engine="prerecorded")))
    labels = {c["engine"]: c["label"] for c in client.get("/health").json()["ttsChoices"]}
    assert labels["elevenlabs-v4-turbo-female"] == "ElevenLabs v4 Turbo · Anna Kim(여자) · 입말"
    assert labels["elevenlabs-v4-turbo-male"] == "ElevenLabs v4 Turbo · Chris(남자) · 입말"
    answer = client.post("/ask", json={"text": "가스비 얼마 내야 돼?", "ttsEngine": "elevenlabs-v4-turbo-male"}).json()
    assert "사만 이천" in answer["speechText"]
    assert client.post("/tts", json={"text": answer["speechText"], "engine": "elevenlabs-v4-turbo-male"}).status_code == 200

    def broken(self, text):
        raise elevenlabs.ElevenLabsError("크레딧 부족")

    monkeypatch.setattr(elevenlabs.ElevenLabsTtsEngine, "synthesize", broken)
    assert client.post("/tts", json={"text": "안녕", "engine": "elevenlabs-v4-turbo-male"}).status_code == 503


def test_each_voice_uses_its_own_voice_id():
    from app.engines import create_tts_engine

    urls = []
    for name in ("elevenlabs-v4-turbo-female", "elevenlabs-v4-turbo-male"):
        engine = create_tts_engine(make_settings(tts_engine=name, elevenlabs=True))
        engine._key_reader, engine._post = (lambda: "k"), (lambda url, body, key: urls.append(url) or b"\x01\x00" * 10)
        engine.synthesize("안녕")
        assert engine.name == name
    assert "uyVNoMrnUku1dZyVEXwD" in urls[0] and "PDoCXqBQFGsvfO0hNkEs" in urls[1]
    with pytest.raises(ValueError):
        ElevenLabsTtsEngine("elevenlabs-v4-turbo")
