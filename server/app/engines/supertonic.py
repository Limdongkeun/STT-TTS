"""Supertonic 3(Supertone, 약 99M, ONNX) 맥 로컬 TTS — 2026-11-18 사용자 결정: 견본을 만들고 8002 TTS 고르기에 붙인다.

- 모델: server/.models/supertonic-3(Hugging Face Supertone/supertonic-3, 패키지 supertonic 1.3.1 이 고정한 커밋, 385MB).
  가중치 라이선스는 BigScience OpenRAIL-M(상업 배포는 되지만 사용 제한이 따라붙음 — 의료 조언 금지, 기계 소리임을 숨기지 않기 등).
  GitHub 는 2026-09-09 부터 보관(지원 끝).
- 목소리는 기본 목소리 10개(F1~F5, M1~M5)뿐이고 복제는 안 된다. 2026-11-18 사용자가 견본 10개를 듣고 여자 F1·남자 M2 로 골랐다.
- 읽는 글은 서버가 이미 입말·숫자를 한글로 바꾼 글(lang="ko").
- 모델은 처음 부를 때 한 번 읽고(두 목소리가 같이 쓴다), 한 번에 하나만 만든다.
"""

import threading
from array import array
from pathlib import Path
from typing import Any

from app.engines.base import TtsResult
from app.engines.elevenlabs import pcm_to_wav

MODEL_NAME = "supertonic-3"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / ".models" / "supertonic-3"
# 엔진 이름 → (기본 목소리, 이름표)
VOICES = {
    "supertonic-female": ("F1", "Supertonic 3 · F1(여자)"),
    "supertonic-male": ("M2", "Supertonic 3 · M2(남자)"),
}
LANG = "ko"

_runtime_lock = threading.Lock()
_runtimes: dict[str, Any] = {}


class SupertonicError(RuntimeError):
    """Supertonic 을 지금 못 쓴다(패키지·모델 없음, 만들기 실패). 서버는 503 으로 돌려준다."""


def model_ready(model_dir: Path = DEFAULT_MODEL_DIR) -> bool:
    """모델 파일(onnx 폴더·목소리)이 있는지. 없으면 고르기 목록에 나오지 않는다."""
    return (model_dir / "onnx").is_dir() and (model_dir / "voice_styles").is_dir()


def _load_runtime(model_dir: Path):
    key = str(model_dir)
    with _runtime_lock:
        if key not in _runtimes:
            try:
                from supertonic import TTS
            except ImportError as exc:
                raise SupertonicError("supertonic 패키지가 없어요(uv pip install --python .venv-asr/bin/python supertonic==1.3.1).") from exc
            try:
                _runtimes[key] = TTS(model=MODEL_NAME, model_dir=model_dir, auto_download=False)
            except Exception as exc:  # noqa: BLE001 - 바깥 라이브러리 오류를 503 으로 바꾼다
                raise SupertonicError(f"Supertonic 모델을 읽지 못했어요: {exc}") from exc
        return _runtimes[key]


def float_to_pcm16(samples) -> bytes:
    """-1~1 소리(float, numpy 배열 또는 [[...]] 목록) → 16비트 PCM. 넘치는 값은 자른다.
    서버(.venv-asr)에는 numpy 가 있고, 시험 환경(.venv)에는 없어서 둘 다 받는다."""
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        flat = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
        return (flat * 32767.0).astype("<i2").tobytes()
    values = list(_flatten(samples))
    return array("h", (int(max(-1.0, min(1.0, float(v))) * 32767.0) for v in values)).tobytes()


def _flatten(samples):
    for item in samples:
        if isinstance(item, (list, tuple)):
            yield from _flatten(item)
        else:
            yield item


class SupertonicTtsEngine:
    def __init__(self, name: str, model_dir: Path = DEFAULT_MODEL_DIR, loader=_load_runtime) -> None:
        if name not in VOICES:
            raise ValueError(f"모르는 Supertonic 엔진: {name}")
        self.name = name
        self._voice, self.label = VOICES[name]
        self._model_dir = model_dir
        self._loader = loader
        self._lock = threading.Lock()

    def synthesize(self, text: str) -> TtsResult:
        runtime = self._loader(self._model_dir)
        with self._lock:
            try:
                style = runtime.get_voice_style(voice_name=self._voice)
                wav, _ = runtime.synthesize(text, voice_style=style, lang=LANG)
            except Exception as exc:  # noqa: BLE001
                raise SupertonicError(f"Supertonic 이 소리를 만들지 못했어요: {exc}") from exc
        pcm = float_to_pcm16(wav)
        if not pcm:
            raise SupertonicError("Supertonic 이 빈 소리를 돌려줬어요.")
        rate = int(runtime.sample_rate)
        return TtsResult(wav_bytes=pcm_to_wav(pcm, rate), sample_rate=rate, duration_sec=len(pcm) / 2 / rate)
