"""Qwen3-ASR 엔진 (qwen-asr 패키지, transformers 백엔드).

사용법은 qwen-asr 0.0.6 PyPI README 기준:
    Qwen3ASRModel.from_pretrained(model_id, dtype=..., device_map=...)
    model.transcribe(audio=<경로>, language=...)[0].text
모델은 처음 transcribe 를 부를 때 내려받고 불러온다.
"""

import logging
import threading
from pathlib import Path

from app.device import resolve_device, resolve_dtype
from app.engines.base import SttResult
from app.settings import Settings
from app.stt_hints import echoes_hint_context, hint_context, load_hint_words

logger = logging.getLogger(__name__)


class Qwen3AsrEngine:
    name = "qwen3-asr"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # 폰 STT 와 같은 힌트 낱말(공평 비교). STT_HINTS=off 면 넣지 않는다.
        words = load_hint_words() if settings.stt_hints == "on" else []
        self._words = words
        self.hint_count = len(words)
        self._context = hint_context(words)
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
        results = model.transcribe(audio=str(wav_path), context=self._context, language=self._settings.speech_language)
        first = results[0]
        text = first.text.strip()
        # 힌트 글을 따라 쓴 결과는 버린다 → 앱이 '인식된 말이 없어요. 다시 말해 주세요.'로 받는다(2026-11-12 D19).
        if echoes_hint_context(text, self._words):
            logger.warning("STT 결과가 힌트 글을 따라 써서 버림: %r", text[:60])
            text = ""
        return SttResult(text=text, language=getattr(first, "language", None))
