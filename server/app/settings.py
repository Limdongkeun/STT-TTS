"""환경변수에서 서버 설정을 읽는다."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# LFM3-Audio-2B(llama.cpp, 맥에만 둔 server/.lfm3/): 8002 가 함께 띄워 받아쓰기·TTS 를 고를 수 있게 한다(2026-11-16 사용자 요청).
LFM3_STT_ENGINE = "lfm3-asr"
# 엔진 이름 → llama.cpp 목소리(여자·남자 둘뿐, 복제 없음)
LFM3_TTS_ENGINES = {"lfm3-tts-female": "female", "lfm3-tts-male": "male"}
LFM3_DEFAULT_DIR = Path(__file__).resolve().parents[1] / ".lfm3"
LFM3_SERVER_FILE = "llama/llama-server"
LFM3_MODEL_FILE = "models/LFM3-Audio-2B-Q4_K_M.gguf"
LFM3_MMPROJ_FILE = "models/mmproj-LFM3-Audio-2B-Q8_0.gguf"
# off(기본): 끈다 / auto: server/.lfm3 에 실행 파일·모델이 있으면 켠다.
# 2026-11-17 폰 시험에서 한국어 받아쓰기 오류율 25%·목소리 억양이 어색해 기본으로 끈다(사용자 결정, 코드·모델은 남김).
LFM3_MODES = ("off", "auto")

# Qwen3-ASR 한국어 학습판(TeamUNIVA/qwen3_asr_1.7b_ko, Apache-2.0). 2026-11-17 사용자: 버튼 방식 STT 에 더해 비교.
# 11/13 녹음 33개로 힌트 없이 CER 0.098(지금 Qwen 힌트 42 는 0.103), 한 문장 0.71초. 힌트를 넣어도 나아지지 않아 힌트 없이 쓴다.
QWEN_KO_STT_ENGINE = "qwen3-asr-ko"
QWEN_KO_DEFAULT_PATH = Path(__file__).resolve().parents[1] / ".models" / "qwen3_asr_1.7b_ko"
QWEN_KO_HF_ID = "TeamUNIVA/qwen3_asr_1.7b_ko"
# 2026-11-17 사용자: 원래 Qwen3-ASR-1.7B(qwen3-asr)는 한국어판이 메인이 되어 필요 없다고 지움(선택지·모델 파일). 엔진 코드는 한국어판이 쓰고, 원래 모델 전용 힌트 42개(STT_HINTS)·ASR_MODEL_ID 도 지움.
STT_ENGINES = ("mock", QWEN_KO_STT_ENGINE)
# ElevenLabs v4 Turbo(2026-11-17 사용자 허락: 107 이 자꾸 멈춰 8002 에 붙임, 쓴 만큼 크레딧 차감).
# 2026-11-17 16:10 사용자: Turbo 목소리를 여자 Anna Kim·남자 Chris 둘로(지수 Turbo 는 뺌, 지수 녹음 재생은 그대로).
ELEVENLABS_TTS_ENGINES = ("elevenlabs-v4-turbo-female", "elevenlabs-v4-turbo-male")
# auto(기본): 키(ELEVENLABS_API_KEY 또는 맥 키체인 'elevenlabs-api-key')가 있으면 고르기 목록에 넣는다 / off: 뺀다
ELEVENLABS_MODES = ("auto", "off")
TTS_ENGINES = ("mock", "qwen3-tts", "prerecorded", "qwen3-tts-107", "qwen3-tts-107-h2", *ELEVENLABS_TTS_ENGINES, *LFM3_TTS_ENGINES)
# 107 복제(run_clone) 엔진 → 목소리 견본 이름(app/data/voices/<이름>.json). 빈 글이면 TTS_107_VOICE(기본 g).
# 2026-11-12 사용자 결정: 밝은 H2 목소리를 더하고 G 는 그대로 둔다(앱에서 고른다).
# 2026-11-16 사용자 결정: H2 엔진의 견본을 답하는 말투(h2-d)로 바꾼다(h2 견본은 답마다 말투가 출렁였다). h2 는 남긴다.
TTS_107_ENGINES = {"qwen3-tts-107": "", "qwen3-tts-107-h2": "h2-d"}
ANSWER_PROVIDERS = ("fixed", "family-demo")
DTYPES = ("bfloat16", "float16", "float32")
# fixed: 시험 시각(2026-11-05 15:00 KST)으로 답한다. 녹음·기대 답이 이 날짜 기준이라 날마다 결과가 같다.
DEMO_CLOCKS = ("fixed", "real")
# on: 그때그때 만드는 TTS(107·맥 Qwen)와 지수 녹음은 시험 답을 입말 문장(app/data/spoken_answers.json)으로 읽는다.
# off 는 원래 문장(지수 녹음은 입말로만 녹음해서 off 면 녹음이 없다).
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
    # qwen3-tts-107: 107 시험 페이지 주소(예: http://<107 주소>:5110), 목소리 견본 이름, 한 문장 제한 시간(초)
    tts107_url: str = ""
    tts107_voice: str = "g"
    tts107_timeout_sec: int = 90
    spoken_answers: str = "on"
    # LFM3 실행 파일·모델 폴더(비우면 LFM3 를 고를 수 없다)와 8002 가 띄우는 llama-server 포트(127.0.0.1 에만)
    lfm3_dir: str = ""
    lfm3_port: int = 8090
    # ElevenLabs TTS 를 고를 수 있는지(키가 있을 때만)
    elevenlabs: bool = False
    # Qwen3-ASR 한국어판 모델(맥 폴더 또는 Hugging Face 이름). 비우면 고르기 목록에 없다.
    asr_ko_model_id: str = ""


def lfm3_files_ready(directory: Path) -> bool:
    """LFM3 실행 파일과 모델이 다 있는지. 없으면 LFM3 는 고르기 목록에 나오지 않는다."""
    return all((directory / name).is_file() for name in (LFM3_SERVER_FILE, LFM3_MODEL_FILE, LFM3_MMPROJ_FILE))


# 서버 하나로 여러 TTS 를 고를 때 보여 주는 순서. 맥에서 모델을 돌리는 qwen3-tts 는 기본 엔진일 때만 고를 수 있다
# (qwen-tts 는 qwen-asr 와 한 환경에 못 들어가서, 합친 서버(.venv-asr)에서는 쓰지 않는다).
TTS_CHOICE_ORDER = ("prerecorded", "qwen3-tts-107", "qwen3-tts-107-h2", *ELEVENLABS_TTS_ENGINES, *LFM3_TTS_ENGINES, "qwen3-tts", "mock")


def tts_choices(settings: "Settings") -> tuple[str, ...]:
    """이 서버에서 앱이 요청마다 고를 수 있는 TTS 엔진들.
    삐(mock)는 서버 기본으로 띄웠을 때만 고를 수 있다(2026-11-16 사용자: 삐 버튼은 뺀다)."""
    available = {settings.tts_engine, "prerecorded"}
    if settings.tts107_url:
        available.update(TTS_107_ENGINES)
    if settings.lfm3_dir:
        available.update(LFM3_TTS_ENGINES)
    if settings.elevenlabs:
        available.update(ELEVENLABS_TTS_ENGINES)
    return tuple(name for name in TTS_CHOICE_ORDER if name in available)


def stt_choices(settings: "Settings") -> tuple[str, ...]:
    """앱이 요청마다 고를 수 있는 서버 STT. 첫째가 기본(STT_ENGINE)."""
    names = [settings.stt_engine]
    if settings.stt_engine != QWEN_KO_STT_ENGINE and settings.asr_ko_model_id:
        names.append(QWEN_KO_STT_ENGINE)
    if settings.lfm3_dir:
        names.append(LFM3_STT_ENGINE)
    return tuple(names)


def _asr_ko_model_id(stt_engine: str) -> str:
    """ASR_KO=auto(기본): 맥 폴더(server/.models/qwen3_asr_1.7b_ko)가 있으면 그것을 쓴다. 다른 곳은 ASR_KO_MODEL_ID 로."""
    if _choice("ASR_KO", "auto", ("auto", "off")) == "off":
        return ""
    explicit = os.environ.get("ASR_KO_MODEL_ID", "").strip()
    if explicit:
        return explicit
    if QWEN_KO_DEFAULT_PATH.is_dir():
        return str(QWEN_KO_DEFAULT_PATH)
    return QWEN_KO_HF_ID if stt_engine == QWEN_KO_STT_ENGINE else ""


def elevenlabs_key_available() -> bool:
    """키가 있는지만 본다(키 글은 돌려주지 않는다). 환경변수 → 맥 키체인 'elevenlabs-api-key'."""
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        return True
    try:
        result = subprocess.run(["security", "find-generic-password", "-s", "elevenlabs-api-key"],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _elevenlabs(tts_engine: str) -> bool:
    on = _choice("ELEVENLABS", "auto", ELEVENLABS_MODES) == "auto" and elevenlabs_key_available()
    if tts_engine in ELEVENLABS_TTS_ENGINES and not on:
        raise ValueError(f"TTS_ENGINE={tts_engine} 이면 ElevenLabs 키가 있어야 합니다.")
    return on


def _lfm3_dir(tts_engine: str) -> str:
    mode = _choice("LFM3", "off", LFM3_MODES)
    directory = Path(os.environ.get("LFM3_DIR", "").strip() or LFM3_DEFAULT_DIR)
    ready = mode == "auto" and lfm3_files_ready(directory)
    if tts_engine in LFM3_TTS_ENGINES and not ready:
        raise ValueError(f"TTS_ENGINE={tts_engine} 이면 LFM3 실행 파일·모델이 {directory} 에 있어야 합니다.")
    return str(directory) if ready else ""


def _tts107_url(tts_engine: str) -> str:
    url = os.environ.get("TTS_107_URL", "").strip().rstrip("/")
    if tts_engine in TTS_107_ENGINES and not url:
        raise ValueError("TTS_ENGINE=qwen3-tts-107 이면 TTS_107_URL(107 시험 페이지 주소)이 필요합니다.")
    if url and not url.startswith(("http://", "https://")):
        raise ValueError(f"TTS_107_URL={url!r} 는 http:// 또는 https:// 로 시작해야 합니다.")
    return url


def load_settings() -> Settings:
    tts_engine = _choice("TTS_ENGINE", "prerecorded", TTS_ENGINES)
    stt_engine = _choice("STT_ENGINE", "mock", STT_ENGINES)
    return Settings(
        stt_engine=stt_engine,
        tts_engine=tts_engine,
        # 기본은 가족 돌봄 시험 답. 인식과 답을 한 번에 확인한다. fixed 는 예전 고정 답(설정할 때만).
        answer_provider=_choice("ANSWER_PROVIDER", "family-demo", ANSWER_PROVIDERS),
        tts_model_id=os.environ.get("TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
        tts_speaker=os.environ.get("TTS_SPEAKER", "Sohee"),
        speech_language=os.environ.get("SPEECH_LANGUAGE", "Korean"),
        model_device=os.environ.get("MODEL_DEVICE", "auto"),
        model_dtype=_choice("MODEL_DTYPE", "bfloat16", DTYPES),
        max_upload_bytes=_positive_int("MAX_UPLOAD_MB", 20) * 1024 * 1024,
        test_results_dir=os.environ.get("TEST_RESULTS_DIR", "").strip(),
        demo_clock=_choice("DEMO_CLOCK", "fixed", DEMO_CLOCKS),
        tts107_url=_tts107_url(tts_engine),
        tts107_voice=os.environ.get("TTS_107_VOICE", "g").strip(),
        tts107_timeout_sec=_positive_int("TTS_107_TIMEOUT_SEC", 90),
        spoken_answers=_choice("SPOKEN_ANSWERS", "on", SPOKEN_ANSWERS),
        lfm3_dir=_lfm3_dir(tts_engine),
        lfm3_port=_positive_int("LFM3_PORT", 8090),
        elevenlabs=_elevenlabs(tts_engine),
        asr_ko_model_id=_asr_ko_model_id(stt_engine),
    )
