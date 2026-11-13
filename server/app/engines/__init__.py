"""STT·TTS 엔진. 설정값으로 골라 쓴다."""

from app.engines.base import SttEngine, SttResult, TtsEngine, TtsResult
from app.settings import TTS_107_ENGINES, Settings


def create_stt_engine(settings: Settings) -> SttEngine:
    if settings.stt_engine == "qwen3-asr":
        from app.engines.qwen3_asr import Qwen3AsrEngine

        return Qwen3AsrEngine(settings)
    from app.engines.mock import MockSttEngine

    return MockSttEngine()


def create_tts_engine(settings: Settings) -> TtsEngine:
    if settings.tts_engine == "prerecorded":
        from app.engines.prerecorded import PrerecordedTtsEngine

        return PrerecordedTtsEngine()
    if settings.tts_engine == "qwen3-tts":
        from app.engines.qwen3_tts import Qwen3TtsEngine

        return Qwen3TtsEngine(settings)
    if settings.tts_engine in TTS_107_ENGINES:
        from app.engines.qwen3_tts_107 import Qwen3Tts107Engine, load_voice

        voice = load_voice(TTS_107_ENGINES[settings.tts_engine] or settings.tts107_voice)
        return Qwen3Tts107Engine(
            settings.tts107_url, voice, settings.tts107_timeout_sec, engine_name=settings.tts_engine
        )
    from app.engines.mock import MockTtsEngine

    return MockTtsEngine()


__all__ = ["SttEngine", "SttResult", "TtsEngine", "TtsResult", "create_stt_engine", "create_tts_engine"]
