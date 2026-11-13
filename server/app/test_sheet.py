"""실기기 시험표: 시험 문장(C1~C7, D1~D25), 작성 중인 시험표, 저장본.

앱 맨 아래 시험표가 이 목록을 받아 보여 준다. 기기(예: ios-27-0-1)마다
- draft.json: 작성 중인 시험표. 누를 때마다 저장(앱을 새로고침해도 남음), 초기화하면 비움
- <저장 시각>.json · .md: [저장하기]로 남긴 저장본(그때 코드 버전·요약·결과)
- history.md: 저장본마다 한 줄. 개발하면서 결과가 어떻게 바뀌는지 본다
- draft-audio/, <저장 시각>-audio/: 폰 STT 가 들은 소리(WAV). 다음 주 서버 STT 에 같은 소리를 넣어 비교한다
가 results/test-runs/<기기>/ 에 남는다(results/ 는 git 에 올리지 않음).
기대 답은 docs/test-plan.md, .scratch/family-shared-tasks/spec.md 와 같다.
"""

import json
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from app.family_demo import compact_question
from pydantic.alias_generators import to_camel

KST = ZoneInfo("Asia/Seoul")
DEVICE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
LEGACY_RUN_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-(?P<device>[a-z0-9][a-z0-9-]{0,39})\.json$")
REPO_DIR = Path(__file__).resolve().parents[2]
MAX_ATTEMPTS_LISTED = 20
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "test-runs"

# 시험 환경: 조용함 · TV 소음 · 3m 거리 · 다른 사람 목소리
Condition = Literal["", "quiet", "tv", "far", "other_voice"]
CONDITION_LABELS = {"quiet": "조용함", "tv": "TV 소음", "far": "3m 거리", "other_voice": "다른 목소리", "": ""}
MAX_TIMING_MS = 600_000
MAX_SPOKEN_CHARS = 200
# 서버가 지어 주는 음성 파일 이름(예: D6_1762400000000.wav). 경로 문자는 들어갈 수 없다.
AUDIO_FILE_PATTERN = re.compile(r"^(?P<case>[A-Z][0-9]{1,2})_[0-9]{1,16}\.(?P<ext>wav|caf)$")
DRAFT_AUDIO_DIR = "draft-audio"

Mark = Literal["", "o", "x"]
# 들린 답에만 '-'(녹음 없음: 이 답의 소리가 없어 판단하지 않음)가 더 있다.
HeardMark = Literal["", "o", "x", "-"]


def _case(group: str, case_id: str, say: str, expect: str, *, date_dependent: bool = False, chain: str = "") -> dict:
    """시험 문장 하나. 누가 했는지는 문장 속 남편·아내로 알아듣는다(앱에서 '나'를 고르지 않음)."""
    return {
        "group": group,
        "id": case_id,
        "say": say,
        "expect": expect,
        "dateDependent": date_dependent,
        "chain": chain,
    }


TEST_CASES: list[dict] = [
    _case("가족 돌봄 대화", "C1", "다음 주 우리 집 일정 뭐야?", "다음 주 가족 일정은 두 건이에요. 화요일에 가족 식사, 토요일에 장보기가 있어요."),
    _case("가족 돌봄 대화", "C2", "소윤이 이번 주 학교 학원 일정 뭐야?", "소윤이는 수요일에 학교 체험학습, 금요일에 피아노 학원이 있어요."),
    _case("가족 돌봄 대화", "C3", "애기 해열제 부르펜 계열 먹었는데 시간 체크해줘", "몇 시에 먹였나요?", chain="C4로 이어서"),
    _case(
        "가족 돌봄 대화", "C4", "30분 전에 먹였어",
        "지금보다 30분 전 시각으로 기록했어요. 다음 복용 예정 시각은 오후 9시예요.", date_dependent=True, chain="C3에서 이어서",
    ),
    _case("가족 돌봄 대화", "C5", "아니, 30분 전이 아니라 한 시간 전이야", "한 시간 전 시각으로 수정했어요.", date_dependent=True, chain="C4에서 이어서"),
    _case("가족 돌봄 대화", "C6", "아버지 병원 예약 언제였지?", "11월 2일에 등록한 아버지 병원 예약은 11월 12일 목요일 오전 10시로 확인돼요."),
    _case("가족 돌봄 대화", "C7", "소윤이 다음 주 학교 학원 일정 뭐야?", "시험 일정은 소윤이의 이번 주 학교와 학원 일정만 준비돼 있어요."),
    _case("장보기", "D1", "장보기 목록 뭐 남았어?", "장보기 목록은 두부, 계란 2가지예요."),
    _case("장보기", "D2", "우유랑 기저귀 장보기 목록에 넣어줘", "장보기 목록에 우유, 기저귀를 넣었어요. 지금 목록은 두부, 계란, 우유, 기저귀예요."),
    _case("장보기", "D3", "기저귀는 아내가 샀어", "기저귀는 장보기 목록에서 뺐어요. 남은 건 두부, 계란, 우유예요."),
    _case("고정 지출", "D4", "이번 달 관리비 냈어?", "관리비 23만 4천 원은 남편이 11월 3일에 냈어요."),
    _case("고정 지출", "D5", "가스비 얼마 내야 돼?", "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요."),
    _case("고정 지출", "D6", "가스비 아내가 냈어", "가스비 4만 2천 원은 아내가 11월 5일에 낸 걸로 기록했어요.", date_dependent=True),
    _case("생활비", "D7", "이번 달 생활비 얼마 남았어?", "이번 달 생활비 150만 원 중 98만 원을 써서 52만 원 남았어요."),
    _case("생활비", "D8", "오늘 마트에서 8만 4천 원 썼어", "마트 8만 4천 원을 기록했어요. 이번 달 생활비는 43만 6천 원 남았어요."),
    _case("어린이집 등·하원", "D9", "내일 어린이집 하원 누가 가?", "11월 6일 금요일 하원은 아내가 가요.", date_dependent=True),
    _case("어린이집 등·하원", "D10", "목요일 하원은 아내가 가는 걸로 바꿔줘", "목요일 하원은 아내가 가는 걸로 바꿨어요."),
    _case("집안일 당번", "D11", "이번 주 분리수거 누구 차례야?", "이번 주 분리수거는 남편 차례예요. 아직 안 했어요."),
    _case("집안일 당번", "D12", "빨래 아내가 했다고 체크해줘", "오늘 빨래는 아내가 한 걸로 체크했어요."),
    _case("부탁", "D13", "남편한테 퇴근길에 약국 들러 달라고 부탁해줘", "남편에게 '퇴근길에 약국 들러' 부탁을 보냈어요."),
    _case("부탁", "D14", "남편한테 온 부탁 뭐 있어?", "남편에게 온 부탁은 1건이에요. 아내가 부탁한 '퇴근길에 약국 들러'예요."),
    _case("부탁", "D15", "남편이 약국 부탁 다 했어", "'퇴근길에 약국 들러' 부탁을 끝낸 걸로 표시했어요."),
    _case("부탁", "D16", "아내한테 온 부탁 뭐 있어?", "아내에게 온 부탁은 1건이에요. 남편이 부탁한 '소윤이 우산 챙기기'예요."),
    _case("양가 챙기기", "D17", "시어머니 생신 선물 뭐 하기로 했지?", "시어머니 생신은 11월 20일이에요. 선물은 안마기로 정했고, 남편이 주문하기로 했어요."),
    _case("양가 챙기기", "D18", "이번 달 친정 용돈 보냈어?", "이번 달 친정 용돈 30만 원은 아직 안 보냈어요. 매달 10일에 보내기로 했어요."),
    _case("양가 챙기기", "D19", "친정 용돈 아내가 보냈어", "이번 달 친정 용돈 30만 원은 아내가 보낸 걸로 기록했어요."),
    _case("만기·갱신", "D20", "자동차 보험 언제 끝나?", "자동차 보험은 12월 3일에 끝나요. 28일 남았어요.", date_dependent=True),
    _case(
        "만기·갱신", "D21", "만기 다가오는 거 뭐 있어?",
        "곧 끝나는 건 자동차 보험 12월 3일, 자동차 정기검사 2027년 2월 14일, 남편 여권 2027년 5월 30일이에요.",
    ),
    _case("준비물·서류", "D22", "소윤이 내일 준비물 뭐야?", "11월 6일 금요일 소윤이 준비물은 색종이, 풀이에요.", date_dependent=True),
    _case("준비물·서류", "D23", "현장학습 동의서 냈어?", "현장학습 동의서는 아직 안 냈어요. 11월 7일까지 내야 해요."),
    _case(
        "반려동물", "D24", "콩이 심장사상충 약 언제 먹여야 돼?",
        "콩이 심장사상충 약은 매달 1일에 먹여요. 이번 달은 11월 1일에 남편이 먹였고, 다음은 12월 1일이에요.",
    ),
    _case("반려동물", "D25", "콩이 예방접종 언제야?", "콩이 종합백신은 2027년 1월 15일 예정이에요."),
    # 2026-11-09 추가: 힌트 목록에 없는 낱말(넷플릭스·혈압약)과 새 읽기(영어 이름, 날짜·요일·시각 + 두 문장)
    _case("새 문장 (힌트 없음)", "E1", "넷플릭스 구독료 언제 빠져나가?", "넷플릭스 1만 7천 원은 매달 22일 자동이체예요."),
    _case(
        "새 문장 (힌트 없음)", "E2", "아버지 혈압약 다 떨어졌는데 다음 병원 언제야?",
        "아버지 다음 진료는 11월 12일 목요일 오전 10시예요. 혈압약 처방은 그때 받으면 돼요.",
    ),
]
CASES_BY_ID = {case["id"]: case for case in TEST_CASES}
MARK_LABELS = {"o": "○", "x": "×", "-": "녹음 없음", "": ""}


class SheetResult(BaseModel):
    """한 문장의 시험 결과. 앱이 통째로 보낸다(덮어쓰기)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    recognized: str = Field(default="", max_length=500)
    answer: str = Field(default="", max_length=1000)
    key: Mark = ""
    screen: Mark = ""
    heard: HeardMark = ""
    note: str = Field(default="", max_length=500)
    speaker: Literal["", "wife", "husband"] = ""
    # 이 턴을 받아 적은 STT (예: "폰 기본 STT", "Qwen3-ASR-1.7B"). 앱이 적는다.
    stt: str = Field(default="", max_length=120)
    # 이 턴의 답을 읽은 TTS (예: "JISOO 사전 녹음 (C1~C7·D1~D25)", "107 Qwen3-TTS · G 목소리"). 앱이 적는다.
    tts: str = Field(default="", max_length=120)
    condition: Condition = ""
    # 걸린 시간(ms): 답 만들기 · TTS · 말이 끝난 뒤 답 소리가 나기 시작할 때까지
    ask_ms: int | None = Field(default=None, ge=0, le=MAX_TIMING_MS)
    tts_ms: int | None = Field(default=None, ge=0, le=MAX_TIMING_MS)
    reply_ms: int | None = Field(default=None, ge=0, le=MAX_TIMING_MS)
    # 이 턴에 폰 STT 가 들은 소리(draft-audio/ 안 파일 이름). 서버가 지어 준 이름만 받는다.
    audio_file: str = Field(default="", max_length=40, pattern=AUDIO_FILE_PATTERN.pattern + "|^$")
    # 대본과 다르게 말했을 때 실제로 말한 문장(사람이 적는다). 있으면 인식 정확도를 이 문장과 비교한다.
    spoken: str = Field(default="", max_length=MAX_SPOKEN_CHARS)
    # 서버가 보정한 뒤의 글(/ask 의 correctedText). 보정 전 글은 recognized.
    corrected: str = Field(default="", max_length=500)
    updated_at: str = Field(default="", max_length=40)


def tts_label_for(engine: str, model_id: str) -> str:
    """'mock' 또는 'Qwen3-TTS-12Hz-1.7B-CustomVoice' (조직 이름은 뺀다)."""
    if engine == "prerecorded":
        # 2026-11-12부터 입말 녹음(C1~E2). 예전 저장본의 'JISOO 사전 녹음 (C1~C7·D1~D25)'은 원래 답 글 녹음이다.
        return "JISOO 녹음 (C1~E2)"
    return model_id.rsplit("/", 1)[-1] if engine != "mock" and model_id else engine


def labels_of(results: dict[str, dict], field: str) -> list[str]:
    """저장본 턴들에 적힌 이름(stt·tts)들, 많이 쓰인 순서. 적힌 게 없으면 빈 목록."""
    counts: dict[str, int] = {}
    for result in results.values():
        label = str(result.get(field, "")).strip()
        if label:
            counts[label] = counts.get(label, 0) + 1
    return sorted(counts, key=lambda label: -counts[label])


def stt_labels(results: dict[str, dict]) -> list[str]:
    """저장본에 쓰인 STT 이름들, 많이 쓰인 순서. 적힌 게 없으면 빈 목록."""
    return labels_of(results, "stt")


def is_valid_device(device: str) -> bool:
    return bool(DEVICE_PATTERN.fullmatch(device))


def read_code_version(repo: Path = REPO_DIR) -> str:
    """'9a49c4f' 또는 '9a49c4f (수정 중)'. git 이 없으면 빈 글. 셸 없이 정해진 명령만 실행한다."""
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        head = subprocess.run([git, "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
        status = subprocess.run([git, "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    commit = head.stdout.strip() if head.returncode == 0 else ""
    if commit and status.returncode == 0 and status.stdout.strip():
        return f"{commit} (수정 중)"
    return commit


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _check_keys(require_heard: bool) -> tuple[str, ...]:
    """TTS 가 mock('삐' 소리)이면 '들린 답'은 판단할 수 없어 뺀다."""
    return ("key", "screen", "heard") if require_heard else ("key", "screen")


def _has_bad(result: dict, require_heard: bool = True) -> bool:
    return any(result.get(key) == "x" for key in _check_keys(require_heard))


def _is_done(result: dict, require_heard: bool = True) -> bool:
    recognized = bool(str(result.get("recognized", "")).strip())
    return recognized and all(result.get(key) in ("o", "x", "-") for key in _check_keys(require_heard))


def case_state(result: dict | None, require_heard: bool = True) -> str:
    """'bad'(× 하나라도) · 'good'(다 끝났고 × 없음) · ''(아직)."""
    if not result:
        return ""
    if _has_bad(result, require_heard):
        return "bad"
    return "good" if _is_done(result, require_heard) else ""


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def char_error_rate(reference: str, hypothesis: str) -> float | None:
    """글자 오류율(CER) = 고쳐야 할 글자 수 ÷ 말한 문장 글자 수. 띄어쓰기·문장부호는 빼고 센다.
    인식한 말이 없으면 None. 숫자와 한글 수('1시간' vs '한 시간')는 다른 글자로 센다."""
    ref = compact_question(reference)
    hyp = compact_question(hypothesis)
    if not ref or not hyp:
        return None
    return _edit_distance(ref, hyp) / len(ref)


def reference_text(case: dict, result: dict | None) -> str:
    """인식 정확도를 잴 기준 문장: 실제로 말한 문장이 적혀 있으면 그것, 아니면 대본."""
    spoken = str((result or {}).get("spoken", "")).strip()
    return spoken or case["say"]


def summarize(results: dict[str, dict], previous: dict[str, dict] | None, require_heard: bool = True) -> dict:
    ordered = [case["id"] for case in TEST_CASES]
    keys = _check_keys(require_heard)
    states = {case_id: case_state(results.get(case_id), require_heard) for case_id in ordered}
    cers = [
        cer
        for case in TEST_CASES
        if (cer := char_error_rate(
            reference_text(case, results.get(case["id"])), str(results.get(case["id"], {}).get("recognized", "")),
        )) is not None
    ]
    summary = {
        "done": sum(1 for case_id in ordered if _is_done(results.get(case_id, {}), require_heard)),
        "total": len(ordered),
        "ok_marks": sum(1 for case_id in ordered for key in keys if results.get(case_id, {}).get(key) == "o"),
        "bad_cases": [case_id for case_id in ordered if states[case_id] == "bad"],
        "improved": [],
        "worsened": [],
        "cer": round(sum(cers) / len(cers), 3) if cers else None,
        "cer_cases": len(cers),
        "heard_checked": require_heard,
        "reply_ms": average_reply_ms(results),
        "conditions": conditions_used(results),
        "spoken_count": sum(1 for case in TEST_CASES if str(results.get(case["id"], {}).get("spoken", "")).strip()),
    }
    if previous is not None:
        before = {case_id: case_state(previous.get(case_id), require_heard) for case_id in ordered}
        summary["improved"] = [c for c in ordered if before[c] == "bad" and states[c] == "good"]
        summary["worsened"] = [c for c in ordered if before[c] == "good" and states[c] == "bad"]
    return summary


def average_reply_ms(results: dict[str, dict]) -> int | None:
    """말이 끝난 뒤 소리가 나기까지 평균(ms). 잰 턴이 없으면 None."""
    values = [value for result in results.values() if isinstance(value := result.get("reply_ms"), int)]
    return round(sum(values) / len(values)) if values else None


def conditions_used(results: dict[str, dict]) -> list[str]:
    """시험표에 적힌 환경(시험 문장 순서로 처음 나온 순)."""
    found: list[str] = []
    for case in TEST_CASES:
        condition = results.get(case["id"], {}).get("condition", "")
        if condition and condition not in found:
            found.append(condition)
    return found


def _seconds(ms: int | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f}초"


def _percent(cer: float | None) -> str:
    """CER 0.06 → '인식 94%' (정확도 = 1 − CER, 0 아래는 0)."""
    return "-" if cer is None else f"{round(max(0.0, 1 - cer) * 100)}%"


def render_markdown(title: str, results: dict[str, dict]) -> str:
    lines = [
        f"# 음성 시험 결과 — {title}",
        "",
        "| # | 말한 문장 | 인식한 말 | 인식 정확도 | 화면 답 | 핵심 | 화면 | 들림 | 환경 | 말 끝→소리 | 메모 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case in TEST_CASES:
        result = results.get(case["id"], {})
        spoken = str(result.get("spoken", "")).strip()
        cells = [
            case["id"],
            _cell(f"✎ {spoken}" if spoken else case["say"]),
            _cell(_recognized_text(result)),
            _percent(char_error_rate(reference_text(case, result), str(result.get("recognized", "")))),
            _cell(result.get("answer", "")),
            MARK_LABELS.get(result.get("key", ""), ""),
            MARK_LABELS.get(result.get("screen", ""), ""),
            MARK_LABELS.get(result.get("heard", ""), ""),
            CONDITION_LABELS.get(result.get("condition", ""), ""),
            _seconds(result.get("reply_ms")) if isinstance(result.get("reply_ms"), int) else "",
            _cell(result.get("note", "")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _recognized_text(result: dict) -> str:
    """인식한 말. 서버 보정으로 글자가 달라졌으면 보정 뒤 글을 같이 보인다."""
    recognized = str(result.get("recognized", ""))
    corrected = str(result.get("corrected", ""))
    if corrected and compact_question(corrected) != compact_question(recognized):
        return f"{recognized} → 보정: {corrected}"
    return recognized


def _changes_text(summary: dict) -> str:
    parts = []
    if summary["improved"]:
        parts.append(f"×→○ {', '.join(summary['improved'])}")
    if summary["worsened"]:
        parts.append(f"○→× {', '.join(summary['worsened'])}")
    return " / ".join(parts) or "변화 없음"


HISTORY_HEADER = (
    "| 저장 시각 | STT | TTS | 코드 버전 | 환경 | 인식 정확도(평균) | 말 끝→소리(평균) | 끝낸 문장 | ○ | × 있는 문장 | 같은 STT 지난번보다 |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)


class SheetStore:
    """기기마다 작성 중인 시험표(draft)와 저장본(attempt)을 파일에 둔다."""

    def __init__(self, directory: Path, code_version: Callable[[], str] = read_code_version) -> None:
        self._directory = directory
        self._code_version = code_version
        self._lock = threading.Lock()

    def _device_dir(self, device: str) -> Path:
        # device 는 DEVICE_PATTERN 으로 검사된 값만 들어온다(경로 밖으로 못 나감).
        return self._directory / device

    @staticmethod
    def _read(path: Path) -> dict:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _legacy_draft(self, device: str) -> dict[str, dict]:
        """예전 방식(results/test-runs/<날짜>-<기기>.json) 기록이 있으면 가장 최근 것을 시작점으로 쓴다."""
        if not self._directory.exists():
            return {}
        legacy = sorted(
            path for path in self._directory.glob("*.json")
            if (match := LEGACY_RUN_PATTERN.fullmatch(path.name)) and match["device"] == device
        )
        return self._read(legacy[-1]) if legacy else {}

    def load_draft(self, device: str) -> dict[str, dict]:
        path = self._device_dir(device) / "draft.json"
        if path.exists():
            return self._read(path)
        return self._legacy_draft(device)

    def save_draft_case(self, device: str, case_id: str, result: SheetResult) -> dict:
        body = result.model_dump()
        body["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
        with self._lock:
            draft = self.load_draft(device)
            draft[case_id] = body
            self._write(self._device_dir(device) / "draft.json", json.dumps(draft, ensure_ascii=False, indent=2))
        return body

    def clear_draft(self, device: str) -> None:
        with self._lock:
            self._write(self._device_dir(device) / "draft.json", "{}")
            shutil.rmtree(self._device_dir(device) / DRAFT_AUDIO_DIR, ignore_errors=True)

    def save_draft_audio(self, device: str, case_id: str, data: bytes, now: datetime | None = None) -> str:
        """폰 STT 가 들은 소리를 작성 중인 시험표 옆에 둔다. 지어 준 파일 이름을 돌려준다(앱이 시험표에 적음).
        WAV(RIFF/WAVE)·CAF 만 받는다. 아니면 ValueError."""
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            ext = "wav"
        elif data[:4] == b"caff":
            ext = "caf"
        else:
            raise ValueError("WAV 또는 CAF 음성 파일만 받아요.")
        stamp = round((now or datetime.now(KST)).timestamp() * 1000)
        name = f"{case_id}_{stamp}.{ext}"
        if not AUDIO_FILE_PATTERN.fullmatch(name):
            raise ValueError("음성 파일 이름을 만들 수 없어요.")
        folder = self._device_dir(device) / DRAFT_AUDIO_DIR
        with self._lock:
            folder.mkdir(parents=True, exist_ok=True)
            temp = folder / f"{name}.tmp"
            temp.write_bytes(data)
            temp.replace(folder / name)
        return name

    def _copy_audio(self, device: str, draft: dict[str, dict], target: Path) -> dict[str, str]:
        """시험표에 적힌 음성 파일만 저장본 폴더로 복사한다. 케이스 id → 저장본 기준 경로."""
        source = self._device_dir(device) / DRAFT_AUDIO_DIR
        copied: dict[str, str] = {}
        for case_id, result in draft.items():
            name = str(result.get("audio_file", ""))
            match = AUDIO_FILE_PATTERN.fullmatch(name)
            if not match or match["case"] != case_id or not (source / name).is_file():
                continue
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target / f"{case_id}.{match['ext']}")
            copied[case_id] = f"{target.name}/{case_id}.{match['ext']}"
        return copied

    def _attempt_paths(self, device: str) -> list[Path]:
        folder = self._device_dir(device)
        if not folder.exists():
            return []
        return sorted(path for path in folder.glob("*.json") if path.name != "draft.json")

    def save_attempt(self, device: str, now: datetime | None = None, tts_label: str = "") -> dict:
        """작성 중인 시험표를 저장본으로 남긴다. 비어 있으면 ValueError.
        비교 대상은 바로 앞 저장본이 아니라, STT 가 같은 가장 최근 저장본이다(폰 STT ↔ 서버 모델 섞임 방지)."""
        moment = (now or datetime.now(KST)).astimezone(KST)
        with self._lock:
            draft = self.load_draft(device)
            if not any(case_state(result) or str(result.get("recognized", "")).strip() for result in draft.values()):
                raise ValueError("저장할 시험 결과가 없어요.")
            labels = stt_labels(draft)
            # 턴마다 적힌 TTS 가 있으면 그걸로(앱에서 TTS 를 골라 바꿀 수 있다). 없으면 서버가 준 이름.
            tts_label = " + ".join(labels_of(draft, "tts")) or tts_label
            same_stt = [
                record for record in (self._read(path) for path in reversed(self._attempt_paths(device)))
                if record.get("stt_labels", []) == labels
            ]
            previous_record = same_stt[0] if same_stt else None
            previous = previous_record.get("results") if previous_record else None
            folder = self._device_dir(device)
            folder.mkdir(parents=True, exist_ok=True)
            stem = moment.strftime("%Y-%m-%d_%H%M%S")
            suffix = 1
            while (folder / f"{stem}.json").exists():
                suffix += 1
                # '_02' 는 이름순 정렬에서 원래 이름 뒤에 온다('-' 는 '.' 보다 앞이라 안 됨)
                stem = f"{moment.strftime('%Y-%m-%d_%H%M%S')}_{suffix:02d}"
            version = self._code_version()
            audio = self._copy_audio(device, draft, folder / f"{stem}-audio")
            # TTS 가 mock 이면 '들린 답'은 판단할 수 없으니 끝낸 문장·비교에서 뺀다.
            summary = summarize(draft, previous, require_heard=tts_label != "mock")
            record = {
                "device": device,
                "saved_at": moment.isoformat(timespec="seconds"),
                "version": version,
                "file": f"{stem}.json",
                "stt_labels": labels,
                "tts": tts_label,
                "compared_with": previous_record.get("file", "") if previous_record else "",
                "summary": summary,
                "audio": audio,
                "results": draft,
            }
            self._write(folder / f"{stem}.json", json.dumps(record, ensure_ascii=False, indent=2))
            stt_text = " + ".join(labels) or "STT 모름"
            conditions = " + ".join(CONDITION_LABELS[c] for c in summary["conditions"]) or "-"
            title = f"{device} · {moment.strftime('%Y-%m-%d %H:%M')} · STT {stt_text} · TTS {tts_label or '모름'} · {version or '버전 모름'}"
            markdown = render_markdown(title, draft)
            extra = [f"- 환경: {conditions} · 말 끝→소리 평균 {_seconds(summary['reply_ms'])}"]
            if summary.get("spoken_count"):
                extra.append(f"- 바꿔 말한 문장 {summary['spoken_count']}개(✎): 인식 정확도는 실제로 말한 문장과 비교")
            if audio:
                extra.append(f"- 들은 소리 {len(audio)}개: `{stem}-audio/` (다음 주 서버 STT 비교용)")
            heading, _, table = markdown.partition("\n\n")
            self._write(folder / f"{stem}.md", heading + "\n\n" + "\n".join(extra) + "\n\n" + table)
            history = folder / "history.md"
            row = (
                f"| {moment.strftime('%Y-%m-%d %H:%M')} | {stt_text} | {tts_label or '-'} | {version or '-'} | {conditions} | "
                f"{_percent(summary['cer'])} | {_seconds(summary['reply_ms'])} | {summary['done']}/{summary['total']} | {summary['ok_marks']} | {', '.join(summary['bad_cases']) or '-'} | "
                f"{_changes_text(summary) if previous_record else '같은 STT 첫 저장본'} |\n"
            )
            if history.exists():
                existing = history.read_text(encoding="utf-8")
                if HISTORY_HEADER.splitlines()[0] not in existing:
                    # 칸이 바뀐 예전 표 아래에 새 표를 시작한다(예전 줄은 그대로 둔다).
                    existing = existing.rstrip("\n") + "\n\n" + HISTORY_HEADER
            else:
                existing = f"# 시험 저장본 — {device}\n\n{HISTORY_HEADER}"
            self._write(history, existing + row)
        return self._attempt_view(record)

    def list_attempts(self, device: str) -> list[dict]:
        records = [self._read(path) for path in reversed(self._attempt_paths(device))]
        return [self._attempt_view(record) for record in records[:MAX_ATTEMPTS_LISTED] if record]

    @staticmethod
    def _attempt_view(record: dict) -> dict:
        summary = record.get("summary", {})
        return {
            "savedAt": record.get("saved_at", ""),
            "version": record.get("version", ""),
            "file": record.get("file", ""),
            "sttLabels": record.get("stt_labels", []),
            "tts": record.get("tts", ""),
            "comparedWith": record.get("compared_with", ""),
            "done": summary.get("done", 0),
            "total": summary.get("total", 0),
            "okMarks": summary.get("ok_marks", 0),
            "avgCer": summary.get("cer"),
            "cerCases": summary.get("cer_cases", 0),
            "heardChecked": summary.get("heard_checked", True),
            "avgReplyMs": summary.get("reply_ms"),
            "conditions": summary.get("conditions", []),
            "audioCount": len(record.get("audio", {})),
            "badCases": summary.get("bad_cases", []),
            "improved": summary.get("improved", []),
            "worsened": summary.get("worsened", []),
        }

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
