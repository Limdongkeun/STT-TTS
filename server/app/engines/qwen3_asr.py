"""Qwen3-ASR 엔진 (qwen-asr 패키지, transformers 백엔드).

사용법은 qwen-asr 0.0.6 PyPI README 기준:
    Qwen3ASRModel.from_pretrained(model_id, dtype=..., device_map=...)
    model.transcribe(audio=<경로>, language=...)[0].text
모델은 처음 transcribe 를 부를 때 내려받고 불러온다.
"""

import threading
from pathlib import Path

from app.device import resolve_device, resolve_dtype
from app.engines.base import SttResult
from app.settings import Settings


class Qwen3AsrEngine:
    name = "qwen3-asr"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from qwen_asr import Qwen3ASRModel
                except ImportError as exc:
                    raise RuntimeError("qwen-asr 가 없습니다. `uv run --extra asr ...` 로 실행하세요.") from exc
                self._model = Qwen3ASRModel.from_pretrained(
                    self._settings.asr_model_id,
                    dtype=resolve_dtype(self._settings.model_dtype),
                    device_map=resolve_device(self._settings.model_device),
                )
        return self._model

    def transcribe(self, wav_path: Path) -> SttResult:
        model = self._load()
        results = model.transcribe(audio=str(wav_path), language=self._settings.speech_language)
        first = results[0]
        return SttResult(text=first.text.strip(), language=getattr(first, "language", None))
