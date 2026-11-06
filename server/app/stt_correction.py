"""폰 STT 글 보정 (family-demo 시험용).

비교용 글(compact_question 결과: 공백·문장부호 없음)에 차례로 적용한다.
1. 동의어 → 표준 말 (와이프 → 아내)
2. 가족 이름·어려운 낱말을 잘못 받아 적은 것 → 이름 목록 (서윤 → 소윤)
   실제 서비스에서는 DB 의 가족 이름 목록으로 고친다(docs/handoff-voice.md 7-5).
3. 앞뒤 말을 보고 고치기 (어린이집 + 학원 → 하원)
4. 한글로 적힌 금액 → 숫자 (팔만사천원 → 84000원)

정해진 목록만 바꾼다(비슷한 글자 추측 없음). 실제로 틀린 사례가 나오면 목록에 더한다.
"""

import re

# 1. 동의어 → 표준 말. (패턴, 바꿀 말) — 위에서부터 차례로.
SYNONYMS: tuple[tuple[str, str], ...] = (
    (r"와이프", "아내"),
    (r"신랑", "남편"),
    (r"시어머님", "시어머니"),
    (r"(?<!시)어머님", "시어머니"),
    (r"장모님|장모|친정어머니", "친정엄마"),
    (r"분리배출", "분리수거"),
    (r"가스요금", "가스비"),
    (r"(?:핸드폰|휴대폰|통신)요금", "통신비"),
    (r"예방주사|예방접종", "백신"),
)

# 2. 이름 목록: 표준 이름 → 잘못 받아 적기 쉬운 꼴. 뒤에 조사가 오거나 글이 끝날 때만 고친다.
NAME_VARIANTS: dict[str, tuple[str, ...]] = {
    "소윤": ("소연", "서윤", "수연"),
    "부르펜": ("브루펜", "부루펜", "부르팬", "브루팬"),
}
NAME_FOLLOWERS = r"(?=이|가|는|은|의|한테|에게|도|랑|계열|결|해열제|$)"

# 3. 앞뒤 말을 보고 고치기(그 말이 함께 있을 때만). 실기기 시험(2026-11-05 14:10)에서 나온 사례.
CONTEXT_FIXES: tuple[tuple[str, str], ...] = (
    (r"(어린이집.*?)학원", r"\1하원"),  # "내일 어린이집 학원 누가 가?" → 하원
    (r"(?:7년|칠년)(?=용돈)", "친정"),  # "이번 달에 7년 용돈 보냈어" → 친정
    (r"공기(?=.*(?:심장사상충|백신|약))", "콩이"),  # "공기 심장사상충 약" → 콩이(반려견 말이 함께 있을 때만)
    # 실기기 시험(2026-11-05 17:07)에서 나온 사례
    (r"(?:충전정|충정)(?=용돈)", "친정"),  # "이번 달 충전정 용돈 보냈어"
    (r"(부르펜)결(?=먹)", r"\1계열"),  # "부루펜 결 먹였는데" (이름 보정 뒤)
    (r"헤어제(?=.*(?:부르펜|먹))", "해열제"),  # "애기 헤어제 부루펜 …"
    (r"(현장학습)(?:통해서|동이서|동의소)", r"\1동의서"),  # "현장학습 통해서 냈어"
    (r"아니(?=한테|에게)", "아내"),  # "아니한테 온 부탁 뭐 있어?"
)

# 4. 한글 금액
SINO_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
SMALL_UNITS = {"십": 10, "백": 100, "천": 1000}
LARGE_UNITS = {"만": 10_000, "억": 100_000_000}
# 숫자 바로 뒤('8만4천원'의 '천원', '100만원'의 '만원')는 이미 숫자 금액의 일부라 건드리지 않는다.
KOREAN_AMOUNT = re.compile(r"(?<![0-9])([일이삼사오육칠팔구십백천만억]+)원")


def korean_number(text: str) -> int | None:
    """'팔만사천' → 84000. 단위(십·백·천·만·억)가 하나도 없으면 None(예: '구' 는 금액으로 보지 않음)."""
    if not any(char in SMALL_UNITS or char in LARGE_UNITS for char in text):
        return None
    total = section = digit = 0
    for char in text:
        if char in SINO_DIGITS:
            digit = SINO_DIGITS[char]
        elif char in SMALL_UNITS:
            section += (digit or 1) * SMALL_UNITS[char]
            digit = 0
        else:
            total += ((section + digit) or 1) * LARGE_UNITS[char]
            section = digit = 0
    return total + section + digit


def _korean_amount_to_digits(match: re.Match[str]) -> str:
    value = korean_number(match.group(1))
    return f"{value}원" if value is not None else match.group(0)


def correct_transcript(compact: str) -> str:
    """비교용 글을 보정한다. 바뀐 게 없으면 그대로 돌려준다."""
    text = compact
    for pattern, replacement in SYNONYMS:
        text = re.sub(pattern, replacement, text)
    for name, variants in NAME_VARIANTS.items():
        text = re.sub(rf"(?:{'|'.join(variants)}){NAME_FOLLOWERS}", name, text)
    for pattern, replacement in CONTEXT_FIXES:
        text = re.sub(pattern, replacement, text)
    return KOREAN_AMOUNT.sub(_korean_amount_to_digits, text)
