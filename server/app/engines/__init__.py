"""STT·TTS 엔진. 설정값으로 골라 쓴다."""

from app.engines.base import SttEngine, SttResult, TtsEngine, TtsResult
from app.settings import Settings


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
    if settings.tts_engine == "qwen3-tts-107":
        from app.engines.qwen3_tts_107 import Qwen3Tts107Engine, load_voice

        return Qwen3Tts107Engine(settings.tts107_url, load_voice(settings.tts107_voice), settings.tts107_timeout_sec)
    from app.engines.mock import MockTtsEngine

    return MockTtsEngine()


__all__ = ["SttEngine", "SttResult", "TtsEngine", "TtsResult", "create_stt_engine", "create_tts_engine"]
