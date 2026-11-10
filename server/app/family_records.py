"""가족 기록 시험 데이터와 도우미 (가상 가족, 2026년 11월 기준).

가족 기록 = 가족 공간에서 함께 보는 일정·병원 예약·장보기·부탁·당번 등 (GLOSSARY.md).
스펙: .scratch/family-shared-tasks/spec.md
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

SPEAKERS = ("wife", "husband")
SPEAKER_LABELS = {"wife": "아내", "husband": "남편"}
WEEKDAY_NAMES = ("월", "화", "수", "목", "금", "토", "일")

HANGUL_FIRST = 0xAC00
HANGUL_LAST = 0xD7A3
WON_PATTERN = re.compile(r"(?:(?P<man>\d+)만)?(?:(?P<cheon>\d+)천)?(?P<rest>\d+)?원")


def other_speaker(speaker: str) -> str:
    return "husband" if speaker == "wife" else "wife"


# ── 한국어 조사 ─────────────────────────────────────────────


def _has_final_consonant(word: str) -> bool:
    """마지막 한글 글자에 받침이 있는지. 따옴표·숫자 등은 건너뛴다."""
    for char in reversed(word):
        code = ord(char)
        if HANGUL_FIRST <= code <= HANGUL_LAST:
            return (code - HANGUL_FIRST) % 28 != 0
    return False


def subject(word: str) -> str:
    return word + ("이" if _has_final_consonant(word) else "가")


def topic(word: str) -> str:
    return word + ("은" if _has_final_consonant(word) else "는")


def obj(word: str) -> str:
    return word + ("을" if _has_final_consonant(word) else "를")


def copula(word: str) -> str:
    """문장을 끝맺는 '…이에요/예요.' (마침표 포함)."""
    return word + ("이에요." if _has_final_consonant(word) else "예요.")


# ── 금액 · 날짜 ─────────────────────────────────────────────


def format_won(amount: int) -> str:
    """84000 → '8만 4천 원'. 읽기 변환이 '팔만 사천 원'으로 읽는다."""
    man, rest = divmod(amount, 10000)
    parts = [f"{man}만"] if man else []
    if rest:
        parts.append(f"{rest // 1000}천" if rest % 1000 == 0 else f"{rest:,}")
    return " ".join(parts or ["0"]) + " 원"


def parse_won(compact: str) -> int | None:
    """비교용 글(공백·쉼표 없음)에서 첫 금액을 찾는다. '8만4천원', '84000원', '8만원'."""
    for match in WON_PATTERN.finditer(compact):
        if not any(match.group(name) for name in ("man", "cheon", "rest")):
            continue
        man = int(match["man"] or 0)
        cheon = int(match["cheon"] or 0)
        rest = int(match["rest"] or 0)
        return man * 10000 + cheon * 1000 + rest
    return None


def format_date(day: date, today: date, *, weekday: bool = False) -> str:
    text = f"{day.month}월 {day.day}일"
    if day.year != today.year:
        text = f"{day.year}년 {text}"
    if weekday:
        text += f" {WEEKDAY_NAMES[day.weekday()]}요일"
    return text


def spaced_words(question: str) -> str:
    """뽑아내기용 글: NFC 로 맞추고 글자·숫자가 아닌 문자(문장부호·특수 공백)는 공백으로."""
    normalized = unicodedata.normalize("NFC", question)
    cleaned = "".join(char if unicodedata.category(char)[0] in "LN" else " " for char in normalized)
    return " ".join(cleaned.split())


# ── 시험 데이터 ─────────────────────────────────────────────


@dataclass
class Bill:
    amount: int
    due: date | None = None
    auto_pay_day: int | None = None
    paid_by: str | None = None
    paid_on: date | None = None


@dataclass
class Chore:
    period: str  # "오늘" | "이번 주"
    assignee: str
    done_by: str | None = None


@dataclass
class FamilyRequest:
    sender: str
    recipient: str
    content: str
    done: bool = False


@dataclass
class Allowance:
    amount: int
    day_of_month: int
    sent_by: str | None = None


@dataclass
class Birthday:
    day: date
    gift: str | None
    gift_owner: str | None


@dataclass
class PetCare:
    medicine_day: int
    medicine_last_on: date
    medicine_last_by: str
    vaccine_on: date


@dataclass
class HospitalVisit:
    registered_on: date
    visit_on: date
    time_text: str


@dataclass
class FamilyRecords:
    shopping: list[str] = field(default_factory=lambda: ["두부", "계란"])
    bills: dict[str, Bill] = field(
        default_factory=lambda: {
            "관리비": Bill(234_000, paid_by="husband", paid_on=date(2026, 11, 3)),
            "가스비": Bill(42_000, due=date(2026, 11, 25)),
            "통신비": Bill(89_000, auto_pay_day=20),
            # E1(2026-11-09): 힌트 목록에 없는 영어 이름. STT 가 'Netflix'로 적어도 찾는다(_bills).
            "넷플릭스": Bill(17_000, auto_pay_day=22),
        }
    )
    budget: int = 1_500_000
    spent: int = 980_000
    expenses: list[tuple[str, str, int]] = field(default_factory=list)  # (누가, 어디서, 금액)
    pickup: dict[int, str] = field(
        default_factory=lambda: {0: "wife", 1: "husband", 2: "wife", 3: "husband", 4: "wife"}
    )
    dropoff: dict[int, str] = field(default_factory=lambda: {day: "husband" for day in range(5)})
    chores: dict[str, Chore] = field(
        default_factory=lambda: {
            "분리수거": Chore("이번 주", "husband"),
            "빨래": Chore("오늘", "wife"),
            "청소기": Chore("오늘", "husband"),
        }
    )
    requests: list[FamilyRequest] = field(
        default_factory=lambda: [FamilyRequest("husband", "wife", "소윤이 우산 챙기기")]
    )
    birthdays: dict[str, Birthday] = field(
        default_factory=lambda: {
            "시어머니": Birthday(date(2026, 11, 20), "안마기", "husband"),
            "친정엄마": Birthday(date(2027, 3, 8), None, None),
        }
    )
    allowances: dict[str, Allowance] = field(
        default_factory=lambda: {"친정": Allowance(300_000, 10), "시댁": Allowance(300_000, 10)}
    )
    expiries: dict[str, date] = field(
        default_factory=lambda: {
            "자동차 보험": date(2026, 12, 3),
            "자동차 정기검사": date(2027, 2, 14),
            "남편 여권": date(2027, 5, 30),
        }
    )
    supplies: dict[date, list[str]] = field(default_factory=lambda: {date(2026, 11, 6): ["색종이", "풀"]})
    consent_due: date = date(2026, 11, 7)
    consent_submitted_by: str | None = None
    pet: PetCare = field(
        default_factory=lambda: PetCare(1, date(2026, 11, 1), "husband", date(2027, 1, 15))
    )
    # C1·C2·C6 (가족 돌봄 대화 시험)
    next_week_family: list[tuple[str, str]] = field(default_factory=lambda: [("화", "가족 식사"), ("토", "장보기")])
    soyun_this_week: list[tuple[str, str]] = field(
        default_factory=lambda: [("수", "학교 체험학습"), ("금", "피아노 학원")]
    )
    father_hospital: HospitalVisit = field(
        default_factory=lambda: HospitalVisit(date(2026, 11, 2), date(2026, 11, 12), "오전 10시")
    )
