"""Qwen3-ASR 한국어판(TeamUNIVA) 을 버튼 방식 STT 고르기에 더하기(2026-11-17). 모델은 올리지 않는다."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engines import create_stt_engine
from app.engines.base import SttResult
from app.engines.qwen3_asr import Qwen3AsrEngine
from app.main import create_app
from app.settings import load_settings, stt_choices
from tests.test_api import make_settings, make_wav

ffmpeg_required = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 필요")


def test_choice_added_next_to_mock_only_when_model_known():
    assert stt_choices(make_settings(stt_engine="mock", asr_ko_model_id="/m")) == ("mock", "qwen3-asr-ko")
    assert stt_choices(make_settings(stt_engine="mock")) == ("mock",)


def test_ko_is_the_only_qwen(monkeypatch):
    """2026-11-17 사용자: 한국어판이 메인, 원래 Qwen3-ASR(qwen3-asr)은 지움 — 둘째 선택지도, 설정 값도 없다."""
    settings = make_settings(stt_engine="qwen3-asr-ko", asr_ko_model_id="/models/ko")
    assert stt_choices(settings) == ("qwen3-asr-ko",)
    monkeypatch.setenv("STT_ENGINE", "qwen3-asr")
    with pytest.raises(ValueError):
        load_settings()
    monkeypatch.setenv("STT_ENGINE", "qwen3-asr-ko")
    monkeypatch.setenv("ASR_KO_MODEL_ID", "/models/ko")
    assert load_settings().asr_ko_model_id == "/models/ko"


def test_settings_find_model(monkeypatch, tmp_path):
    monkeypatch.setenv("ASR_KO_MODEL_ID", str(tmp_path))
    assert load_settings().asr_ko_model_id == str(tmp_path)
    monkeypatch.setenv("ASR_KO", "off")
    assert load_settings().asr_ko_model_id == ""


class _FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, **kwargs):
        self.calls.append(kwargs)
        return [SttResult(text=" 우유 사 와 ", language="Korean")]


def test_engine_uses_ko_model_without_hints(tmp_path):
    engine = create_stt_engine(make_settings(stt_engine="qwen3-asr-ko", asr_ko_model_id="/models/ko"))
    assert isinstance(engine, Qwen3AsrEngine)
    assert (engine.name, engine._settings.asr_ko_model_id, engine._model) == ("qwen3-asr-ko", "/models/ko", None)
    engine._model = fake = _FakeModel()  # 진짜 모델을 불러오지 않는다
    assert engine.transcribe(tmp_path / "x.wav").text == "우유 사 와"
    assert "context" not in fake.calls[0] and fake.calls[0]["language"] == "Korean"


@ffmpeg_required
def test_api_lists_and_uses_ko_engine(monkeypatch):
    monkeypatch.setattr(Qwen3AsrEngine, "transcribe", lambda self, path: SttResult(text=f"{self.name} 받아씀", language="Korean"))
    client = TestClient(create_app(make_settings(stt_engine="mock", asr_ko_model_id="/models/ko")))
    labels = {c["engine"]: c["label"] for c in client.get("/health").json()["sttChoices"]}
    assert labels["qwen3-asr-ko"] == "Qwen3-ASR-1.7B-ko (UNIVA)"
    res = client.post("/stt", files={"audio": ("v.wav", make_wav(), "audio/wav")}, data={"engine": "qwen3-asr-ko"}).json()
    assert (res["engine"], res["text"]) == ("qwen3-asr-ko", "qwen3-asr-ko 받아씀")
