"""Qwen3-ASR 엔진 (qwen-asr 패키지, transformers 백엔드).

사용법은 qwen-asr 0.0.6 PyPI README 기준:
    Qwen3ASRModel.from_pretrained(model_id, dtype=..., device_map=...)
    model.transcribe(audio=<경로>, language=...)[0].text
모델은 처음 transcribe 를 부를 때 불러온다. 2026-11-17부터 한국어판(TeamUNIVA, settings.asr_ko_model_id)만 쓰고 힌트는 넣지 않는다
(원래 Qwen/Qwen3-ASR-1.7B 와 그 전용 힌트 42개는 사용자 결정으로 지움).

ASR_BACKEND=vllm(2026-11-20 사용자 결정, 클라우드 L4 전용): Qwen3ASRModel.LLM(...) 으로 vLLM 엔진을 쓴다.
같은 L4·같은 녹음 12개에서 받아 적기 0.63초 → 0.20초, 글자는 12개 모두 같았다. 맥에는 vLLM 이 없어 기본은 transformers.
GPU 메모리는 45%(L4 에서 약 11GB)만 잡아 같은 서버에서 학습할 자리를 남기고, 짧은 말만 받으니 길이 한도를 4096 으로 줄인다.
"""

import threading
from pathlib import Path

from app.device import resolve_device, resolve_dtype
from app.engines.base import SttResult
from app.settings import QWEN_KO_STT_ENGINE, Settings

VLLM_GPU_MEMORY_UTILIZATION = 0.45
VLLM_MAX_MODEL_LEN = 4096
# 버튼 방식 한 마디(1분 안쪽)는 글자 수십 개라 이 정도면 넉넉하다
VLLM_MAX_NEW_TOKENS = 256


class Qwen3AsrEngine:
    name = QWEN_KO_STT_ENGINE

    def __init__(self, settings: Settings, name: str = QWEN_KO_STT_ENGINE) -> None:
        self.name = name
        self._settings = settings
        self._model = None
        self._lock = threading.Lock()
        # 받아 적기는 한 번에 하나씩(2026-11-20: vLLM 동기 LLM 을 여러 요청 스레드가 함께 부르면 일부 요청이 끝없이 멈췄다.
        # 바깥 주소로 3개를 동시에 보내 2개가 30초 넘게 멈춤을 확인). 한 문장 0.2초라 줄 서도 짧다.
        self._run_lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from qwen_asr import Qwen3ASRModel
                except ImportError as exc:
                    raise RuntimeError("qwen-asr 가 없습니다. `uv run --extra asr ...` 로 실행하세요.") from exc
                if self._settings.asr_backend == "vllm":
                    self._model = Qwen3ASRModel.LLM(
                        model=self._settings.asr_ko_model_id,
                        gpu_memory_utilization=VLLM_GPU_MEMORY_UTILIZATION,
                        max_model_len=VLLM_MAX_MODEL_LEN,
                        max_new_tokens=VLLM_MAX_NEW_TOKENS,
                    )
                else:
                    self._model = Qwen3ASRModel.from_pretrained(
                        self._settings.asr_ko_model_id,
                        dtype=resolve_dtype(self._settings.model_dtype),
                        device_map=resolve_device(self._settings.model_device),
                    )
        return self._model

    def transcribe(self, wav_path: Path) -> SttResult:
        model = self._load()
        with self._run_lock:
            first = model.transcribe(audio=str(wav_path), language=self._settings.speech_language)[0]
        return SttResult(text=first.text.strip(), language=getattr(first, "language", None))
