"""Qwen3-TTS CustomVoice 엔진 (qwen-tts 패키지).

사용법은 qwen-tts 0.1.1 PyPI README 기준:
    Qwen3TTSModel.from_pretrained(model_id, device_map=..., dtype=...)
    wavs, sr = model.generate_custom_voice(text=..., language=..., speaker=...)
모델은 처음 synthesize 를 부를 때 내려받고 불러온다.
"""

import io
import threading

from app.device import resolve_device, resolve_dtype
from app.engines.base import TtsResult
from app.settings import Settings


class Qwen3TtsEngine:
    name = "qwen3-tts"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from qwen_tts import Qwen3TTSModel
                except ImportError as exc:
                    raise RuntimeError("qwen-tts 가 없습니다. `uv run --extra tts ...` 로 실행하세요.") from exc
                self._model = Qwen3TTSModel.from_pretrained(
                    self._settings.tts_model_id,
                    device_map=resolve_device(self._settings.model_device),
                    dtype=resolve_dtype(self._settings.model_dtype),
                )
        return self._model

    def synthesize(self, text: str) -> TtsResult:
        import soundfile as sf

        model = self._load()
        wavs, sample_rate = model.generate_custom_voice(
            text=text,
            language=self._settings.speech_language,
            speaker=self._settings.tts_speaker,
        )
        waveform = wavs[0]
        buffer = io.BytesIO()
        sf.write(buffer, waveform, sample_rate, format="WAV")
        return TtsResult(
            wav_bytes=buffer.getvalue(),
            sample_rate=sample_rate,
            duration_sec=len(waveform) / sample_rate,
        )
