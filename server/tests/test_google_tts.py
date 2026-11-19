"""구글 Chirp 3 HD TTS(여자 Aoede·남자 Charon)를 8002 에서 고르기(2026-11-18 사용자 결정). 실제 구글은 부르지 않는다."""

import base64
import io
import json
import subprocess
import urllib.error
import wave

import pytest
from fastapi.testclient import TestClient

from app.engines.elevenlabs import pcm_to_wav
from app.engines.google_tts import API, GoogleTtsEngine, GoogleTtsError, read_api_key
from app.main import create_app
from app.settings import load_settings, tts_choices
from tests.test_api import make_settings


def google_reply(pcm: bytes, rate: int = 24000) -> bytes:
    return json.dumps({"audioContent": base64.b64encode(pcm_to_wav(pcm, rate)).decode()}).encode()


def test_engine_sends_voice_in_body_and_key_in_header_only():
    calls = []

    def post(url, body, key):
        calls.append((url, json.loads(body), key))
        return google_reply(b"\x01\x00" * 24000)  # 1초

    result = GoogleTtsEngine("google-chirp3-hd-female", key_reader=lambda: "k", post=post).synthesize("네, 적어 뒀어요.")
    url, body, key = calls[0]
    assert url == API and "key=" not in url and key == "k"
    assert body["input"] == {"text": "네, 적어 뒀어요."}
    assert body["voice"] == {"languageCode": "ko-KR", "name": "ko-KR-Chirp3-HD-Aoede"}
    assert body["audioConfig"] == {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000}
    with wave.open(io.BytesIO(result.wav_bytes)) as reader:
        assert (reader.getframerate(), reader.getnframes()) == (24000, 24000)
    assert result.duration_sec == 1.0


def test_engine_errors_become_google_error():
    with pytest.raises(GoogleTtsError, match="키가 없어요"):
        GoogleTtsEngine("google-chirp3-hd-male", key_reader=lambda: "", post=lambda *a: b"").synthesize("안녕")

    def refused(url, body, key):
        raise urllib.error.HTTPError(url, 403, "no", {}, io.BytesIO(b'{"error":"BILLING_DISABLED"}'))

    with pytest.raises(GoogleTtsError, match="403"):
        GoogleTtsEngine("google-chirp3-hd-male", key_reader=lambda: "k", post=refused).synthesize("안녕")
    for broken in (b"not json", b"{}", json.dumps({"audioContent": "!!"}).encode(), google_reply(b"")):
        with pytest.raises(GoogleTtsError):
            GoogleTtsEngine("google-chirp3-hd-male", key_reader=lambda: "k", post=lambda *a, r=broken: r).synthesize("안녕")
    with pytest.raises(ValueError):
        GoogleTtsEngine("google-chirp3-hd")


def test_key_reader_prefers_env_then_keychain(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", " envkey ")
    assert read_api_key(run=lambda *a, **k: pytest.fail("키체인을 보면 안 됨")) == "envkey"
    monkeypatch.delenv("GOOGLE_TTS_API_KEY")
    found = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="chainkey\n", stderr="")
    assert read_api_key(run=found) == "chainkey"
    missing = lambda *a, **k: subprocess.CompletedProcess(a, 44, stdout="", stderr="")
    assert read_api_key(run=missing) == ""


def test_choice_only_when_enabled(monkeypatch):
    on = tts_choices(make_settings(google_tts=True))
    assert "google-chirp3-hd-female" in on and "google-chirp3-hd-male" in on
    assert not any(name.startswith("google") for name in tts_choices(make_settings()))
    monkeypatch.setenv("GOOGLE_TTS", "off")
    assert load_settings().google_tts is False
    monkeypatch.setenv("TTS_ENGINE", "google-chirp3-hd-male")
    with pytest.raises(ValueError):
        load_settings()
    monkeypatch.setenv("GOOGLE_TTS", "auto")
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    assert load_settings().google_tts is True


def test_api_reads_spoken_and_reports_failures(monkeypatch):
    from app.engines import google_tts

    monkeypatch.setattr(google_tts.GoogleTtsEngine, "synthesize",
                        lambda self, text: google_tts.TtsResult(pcm_to_wav(b"\x01\x00" * 2400), 24000, 0.1))
    client = TestClient(create_app(make_settings(google_tts=True, answer_provider="family-demo", tts_engine="prerecorded")))
    labels = {c["engine"]: c["label"] for c in client.get("/health").json()["ttsChoices"]}
    assert labels["google-chirp3-hd-female"] == "Google Chirp 3 HD · Aoede(여자) · 입말"
    assert labels["google-chirp3-hd-male"] == "Google Chirp 3 HD · Charon(남자) · 입말"
    answer = client.post("/ask", json={"text": "가스비 얼마 내야 돼?", "ttsEngine": "google-chirp3-hd-male"}).json()
    assert "사만 이천" in answer["speechText"]
    assert client.post("/tts", json={"text": answer["speechText"], "engine": "google-chirp3-hd-male"}).status_code == 200

    def broken(self, text):
        raise google_tts.GoogleTtsError("결제 없음")

    monkeypatch.setattr(google_tts.GoogleTtsEngine, "synthesize", broken)
    assert client.post("/tts", json={"text": "안녕", "engine": "google-chirp3-hd-male"}).status_code == 503


def test_each_voice_uses_its_own_name():
    from app.engines import create_tts_engine

    names = []
    for engine_name in ("google-chirp3-hd-female", "google-chirp3-hd-male"):
        engine = create_tts_engine(make_settings(tts_engine=engine_name, google_tts=True))
        engine._key_reader = lambda: "k"
        engine._post = lambda url, body, key: names.append(json.loads(body)["voice"]["name"]) or google_reply(b"\x01\x00")
        engine.synthesize("안녕")
        assert engine.name == engine_name
    assert names == ["ko-KR-Chirp3-HD-Aoede", "ko-KR-Chirp3-HD-Charon"]
