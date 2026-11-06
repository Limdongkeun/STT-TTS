"""환경변수에서 서버 설정을 읽는다."""

import os
from dataclasses import dataclass

STT_ENGINES = ("mock", "qwen3-asr")
TTS_ENGINES = ("mock", "qwen3-tts", "prerecorded")
ANSWER_PROVIDERS = ("fixed", "family-demo")
DTYPES = ("bfloat16", "float16", "float32")
# fixed: 시험 시각(2026-11-05 15:00 KST)으로 답한다. 녹음·기대 답이 이 날짜 기준이라 날마다 결과가 같다.
DEMO_CLOCKS = ("fixed", "real")


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = os.environ.get(name, default).strip()
    if value not in allowed:
        raise ValueError(f"{name}={value!r} 는 지원하지 않습니다. 가능한 값: {', '.join(allowed)}")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name}={raw!r} 는 정수여야 합니다.") from exc
    if value <= 0:
        raise ValueError(f"{name} 는 0보다 커야 합니다.")
    return value


@dataclass(frozen=True)
class Settings:
    stt_engine: str
    tts_engine: str
    answer_provider: str
    asr_model_id: str
    tts_model_id: str
    tts_speaker: str
    speech_language: str
    model_device: str
    model_dtype: str
    max_upload_bytes: int
    # 시험표 결과 폴더. 비우면 <레포>/results/test-runs
    test_results_dir: str = ""
    # family-demo 답의 기준 시각: fixed(시험 시각 고정) 또는 real(실제 지금)
    demo_clock: str = "fixed"


def load_settings() -> Settings:
    return Settings(
        stt_engine=_choice("STT_ENGINE", "mock", STT_ENGINES),
        tts_engine=_choice("TTS_ENGINE", "prerecorded", TTS_ENGINES),
        # 기본은 가족 돌봄 시험 답. 인식과 답을 한 번에 확인한다. fixed 는 예전 고정 답(설정할 때만).
        answer_provider=_choice("ANSWER_PROVIDER", "family-demo", ANSWER_PROVIDERS),
        asr_model_id=os.environ.get("ASR_MODEL_ID", "Qwen/Qwen3-ASR-1.7B"),
        tts_model_id=os.environ.get("TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
        tts_speaker=os.environ.get("TTS_SPEAKER", "Sohee"),
        speech_language=os.environ.get("SPEECH_LANGUAGE", "Korean"),
        model_device=os.environ.get("MODEL_DEVICE", "auto"),
        model_dtype=_choice("MODEL_DTYPE", "bfloat16", DTYPES),
        max_upload_bytes=_positive_int("MAX_UPLOAD_MB", 20) * 1024 * 1024,
        test_results_dir=os.environ.get("TEST_RESULTS_DIR", "").strip(),
        demo_clock=_choice("DEMO_CLOCK", "fixed", DEMO_CLOCKS),
    )
