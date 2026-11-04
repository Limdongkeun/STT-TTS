import pytest

from app.settings import load_settings


def test_defaults(monkeypatch):
    for name in ("STT_ENGINE", "TTS_ENGINE", "MAX_UPLOAD_MB", "MODEL_DTYPE"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()
    assert settings.stt_engine == "mock"
    assert settings.tts_engine == "mock"
    assert settings.tts_speaker == "Sohee"
    assert settings.max_upload_bytes == 20 * 1024 * 1024


def test_real_engines_selectable(monkeypatch):
    monkeypatch.setenv("STT_ENGINE", "qwen3-asr")
    monkeypatch.setenv("TTS_ENGINE", "qwen3-tts")
    settings = load_settings()
    assert (settings.stt_engine, settings.tts_engine) == ("qwen3-asr", "qwen3-tts")


@pytest.mark.parametrize(
    ("name", "value"),
    [("STT_ENGINE", "whisper"), ("TTS_ENGINE", "unknown"), ("MAX_UPLOAD_MB", "abc"), ("MAX_UPLOAD_MB", "0"), ("MODEL_DTYPE", "int4")],
)
def test_invalid_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        load_settings()


def test_real_engine_object_does_not_load_model(monkeypatch):
    """엔진을 만들기만 해서는 모델을 내려받지 않는다(처음 호출할 때 불러옴)."""
    from app.engines import create_stt_engine, create_tts_engine

    monkeypatch.setenv("STT_ENGINE", "qwen3-asr")
    monkeypatch.setenv("TTS_ENGINE", "qwen3-tts")
    settings = load_settings()
    assert create_stt_engine(settings)._model is None
    assert create_tts_engine(settings)._model is None
