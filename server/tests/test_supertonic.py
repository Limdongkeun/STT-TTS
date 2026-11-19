"""Supertonic 3(맥 로컬 TTS)를 8002 에서 고르기(2026-11-18 사용자 결정). 실제 모델은 읽지 않는다."""

import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.engines.supertonic import SupertonicError, SupertonicTtsEngine, float_to_pcm16, model_ready
from app.main import create_app
from app.settings import load_settings, tts_choices
from tests.test_api import make_settings


class FakeRuntime:
    sample_rate = 44100

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def get_voice_style(self, voice_name):
        return f"style-{voice_name}"

    def synthesize(self, text, voice_style, lang):
        if self.fail:
            raise RuntimeError("onnx 터짐")
        self.calls.append((text, voice_style, lang))
        return [[0.5] * 44100], [1.0]


def test_engine_reads_korean_with_its_voice_and_wraps_wav():
    runtime = FakeRuntime()
    for name, voice in (("supertonic-female", "F1"), ("supertonic-male", "M2")):
        result = SupertonicTtsEngine(name, loader=lambda d: runtime).synthesize("두 시로 고쳐 뒀어요.")
        assert runtime.calls[-1] == ("두 시로 고쳐 뒀어요.", f"style-{voice}", "ko")
        with wave.open(io.BytesIO(result.wav_bytes)) as reader:
            assert (reader.getframerate(), reader.getnframes()) == (44100, 44100)
        assert result.duration_sec == 1.0


def test_pcm_conversion_clips_and_flattens():
    pcm = float_to_pcm16([[2.0, -2.0, 0.0]])
    assert len(pcm) == 6
    assert int.from_bytes(pcm[0:2], "little", signed=True) == 32767
    assert int.from_bytes(pcm[2:4], "little", signed=True) == -32767


def test_errors_become_supertonic_error():
    with pytest.raises(SupertonicError):
        SupertonicTtsEngine("supertonic-female", loader=lambda d: FakeRuntime(fail=True)).synthesize("안녕")

    class Empty(FakeRuntime):
        def synthesize(self, text, voice_style, lang):
            return [[]], [0.0]

    with pytest.raises(SupertonicError, match="빈 소리"):
        SupertonicTtsEngine("supertonic-female", loader=lambda d: Empty()).synthesize("안녕")
    with pytest.raises(ValueError):
        SupertonicTtsEngine("supertonic-F3")


def test_model_ready_needs_onnx_and_voices(tmp_path):
    assert model_ready(tmp_path) is False
    (tmp_path / "onnx").mkdir()
    (tmp_path / "voice_styles").mkdir()
    assert model_ready(tmp_path) is True


def test_choice_only_when_ready(monkeypatch):
    on = tts_choices(make_settings(supertonic=True))
    assert "supertonic-female" in on and "supertonic-male" in on
    assert not any(name.startswith("supertonic") for name in tts_choices(make_settings()))
    monkeypatch.setenv("SUPERTONIC", "off")
    assert load_settings().supertonic is False
    monkeypatch.setenv("TTS_ENGINE", "supertonic-male")
    with pytest.raises(ValueError):
        load_settings()
    monkeypatch.setenv("SUPERTONIC", "auto")
    monkeypatch.setattr("app.settings.supertonic_ready", lambda: True)
    assert load_settings().supertonic is True


def test_api_reads_spoken_and_reports_failures(monkeypatch):
    from app.engines import supertonic

    monkeypatch.setattr(supertonic.SupertonicTtsEngine, "synthesize",
                        lambda self, text: supertonic.TtsResult(supertonic.pcm_to_wav(b"\x01\x00" * 4410, 44100), 44100, 0.1))
    client = TestClient(create_app(make_settings(supertonic=True, answer_provider="family-demo", tts_engine="prerecorded")))
    labels = {c["engine"]: c["label"] for c in client.get("/health").json()["ttsChoices"]}
    assert labels["supertonic-female"] == "Supertonic 3 · F1(여자) · 입말"
    assert labels["supertonic-male"] == "Supertonic 3 · M2(남자) · 입말"
    answer = client.post("/ask", json={"text": "가스비 얼마 내야 돼?", "ttsEngine": "supertonic-female"}).json()
    assert "사만 이천" in answer["speechText"]
    assert client.post("/tts", json={"text": answer["speechText"], "engine": "supertonic-female"}).status_code == 200

    def broken(self, text):
        raise supertonic.SupertonicError("모델 없음")

    monkeypatch.setattr(supertonic.SupertonicTtsEngine, "synthesize", broken)
    assert client.post("/tts", json={"text": "안녕", "engine": "supertonic-female"}).status_code == 503
