"""환경변수에서 서버 설정을 읽는다."""

import os
from dataclasses import dataclass

STT_ENGINES = ("mock", "qwen3-asr")
TTS_ENGINES = ("mock", "qwen3-tts", "prerecorded", "qwen3-tts-107")
ANSWER_PROVIDERS = ("fixed", "family-demo")
DTYPES = ("bfloat16", "float16", "float32")
# fixed: 시험 시각(2026-11-05 15:00 KST)으로 답한다. 녹음·기대 답이 이 날짜 기준이라 날마다 결과가 같다.
DEMO_CLOCKS = ("fixed", "real")
# on: 서버 STT 에도 폰 STT 와 같은 힌트 낱말(app/data/stt_hints.json)을 넣는다. off 는 힌트 없이 비교할 때.
STT_HINTS = ("on", "off")
# on: 그때그때 만드는 TTS(107·맥 Qwen)는 시험 답을 입말 문장(app/data/spoken_answers.json)으로 읽는다. off 는 원래 문장.
SPOKEN_ANSWERS = ("on", "off")


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
    stt_hints: str = "on"
    # qwen3-tts-107: 107 시험 페이지 주소(예: http://<107 주소>:5110), 목소리 견본 이름, 한 문장 제한 시간(초)
    tts107_url: str = ""
    tts107_voice: str = "g"
    tts107_timeout_sec: int = 90
    spoken_answers: str = "on"


# 서버 하나로 여러 TTS 를 고를 때 보여 주는 순서. 맥에서 모델을 돌리는 qwen3-tts 는 기본 엔진일 때만 고를 수 있다
# (qwen-tts 는 qwen-asr 와 한 환경에 못 들어가서, 합친 서버(.venv-asr)에서는 쓰지 않는다).
TTS_CHOICE_ORDER = ("prerecorded", "qwen3-tts-107", "qwen3-tts", "mock")


def tts_choices(settings: "Settings") -> tuple[str, ...]:
    """이 서버에서 앱이 요청마다 고를 수 있는 TTS 엔진들."""
    available = {settings.tts_engine, "prerecorded", "mock"}
    if settings.tts107_url:
        available.add("qwen3-tts-107")
    return tuple(name for name in TTS_CHOICE_ORDER if name in available)


def _tts107_url(tts_engine: str) -> str:
    url = os.environ.get("TTS_107_URL", "").strip().rstrip("/")
    if tts_engine == "qwen3-tts-107" and not url:
        raise ValueError("TTS_ENGINE=qwen3-tts-107 이면 TTS_107_URL(107 시험 페이지 주소)이 필요합니다.")
    if url and not url.startswith(("http://", "https://")):
        raise ValueError(f"TTS_107_URL={url!r} 는 http:// 또는 https:// 로 시작해야 합니다.")
    return url


def load_settings() -> Settings:
    tts_engine = _choice("TTS_ENGINE", "prerecorded", TTS_ENGINES)
    return Settings(
        stt_engine=_choice("STT_ENGINE", "mock", STT_ENGINES),
        tts_engine=tts_engine,
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
        stt_hints=_choice("STT_HINTS", "on", STT_HINTS),
        tts107_url=_tts107_url(tts_engine),
        tts107_voice=os.environ.get("TTS_107_VOICE", "g").strip(),
        tts107_timeout_sec=_positive_int("TTS_107_TIMEOUT_SEC", 90),
        spoken_answers=_choice("SPOKEN_ANSWERS", "on", SPOKEN_ANSWERS),
    )
