"""화면용 글 → 읽기용 글 (한국어 텍스트 정규화).

TTS 가 자주 틀리는 숫자·시간·날짜·금액·전화번호·영어 약어를 한글 읽기로 바꾼다.
처음 버전은 자주 나오는 경우만 다룬다. 어색한 사례가 나오면 규칙을 더한다.
2026-11-12: 실제 LLM·DB 답에 나올 꼴을 더했다 — 소수(37.5도), 단위 기호(ml·mg·kg·%·℃),
약·물건 개수(알·포·병·달 …), 14:30, 2026-11-12, 범위(2~3개), 쉼표 있는 큰 금액(1,200만 원).
'11/4' 같은 빗금 날짜는 뜻이 갈리므로 바꾸지 않는다 → 답을 만들 때 DB 날짜로 "11월 4일"처럼 쓴다.
"""

import re

SINO_DIGITS = ("", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
SINO_SMALL_UNITS = ("", "십", "백", "천")
SINO_LARGE_UNITS = ("", "만", "억", "조")
PHONE_DIGITS = ("공", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")

NATIVE_ONES = ("", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉")
NATIVE_TENS = ("", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔")
NATIVE_MAX = 99

# 고유어 수로 읽는 단위 (한 개, 두 명, 세 살 …)
# '번'은 '두 번(횟수)'과 '3번 버스(번호)'가 갈려서 넣지 않았다. '대'는 '두 대(차)'와 '20대(나이)'가 갈려서 뺐다.
# '개월'은 한자어(삼 개월)라 '개' 뒤에 '월'이 오면 고유어로 읽지 않는다.
NATIVE_COUNTERS = (
    "시간", "개", "명", "살", "마리", "잔", "권", "곳", "가지", "건",
    "알", "포", "달", "병", "판", "통", "장", "봉지", "그릇", "벌", "켤레", "송이", "바퀴", "군데", "캔",
    # 2026-11-19 TTS 점검에서 더함: 4자리 → 네 자리, 2팩 → 두 팩, 1컵 → 한 컵
    "자리", "팩", "컵", "묶음", "단", "쪽", "줄",
)
# 범위(2~3개, 3~4시)에서 앞 숫자에도 단위를 붙여 '두 개에서 세 개'로 읽는다. 긴 단위부터 맞춘다.
RANGE_UNITS = tuple(sorted(set(NATIVE_COUNTERS) | {"개월", "시", "분", "초", "일", "월", "년", "주", "만", "천", "원", "도"},
                           key=len, reverse=True))

# 숫자 바로 뒤에 붙은 단위 기호 → 한글. 긴 기호부터 맞춘다('mg'가 'm'보다 먼저).
UNIT_READINGS = (
    ("km/h", "킬로미터"), ("kcal", "킬로칼로리"),
    ("°C", "도"), ("℃", "도"), ("°", "도"), ("%", "퍼센트"),
    ("GB", "기가바이트"), ("MB", "메가바이트"), ("TB", "테라바이트"), ("cc", "씨씨"),
    ("mg", "밀리그램"), ("kg", "킬로그램"), ("ml", "밀리리터"), ("mL", "밀리리터"),
    ("km", "킬로미터"), ("cm", "센티미터"), ("mm", "밀리미터"),
    ("g", "그램"), ("m", "미터"), ("L", "리터"),
)
DECIMAL_DIGITS = ("영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")

ABBREVIATIONS = {
    "AI": "에이아이",
    "DB": "디비",
    "TTS": "티티에스",
    "STT": "에스티티",
    "SMS": "에스엠에스",
    "OK": "오케이",
}

MONTH_READINGS = {6: "유월", 10: "시월"}

# 2026-11-19 TTS 점검: 처음 보는 영어 약어도 글자로 읽게 한다(KTX → 케이티엑스). 위 ABBREVIATIONS 에 없는 대문자 2~5자.
LETTER_READINGS = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지", "H": "에이치", "I": "아이",
    "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔", "O": "오", "P": "피", "Q": "큐", "R": "알",
    "S": "에스", "T": "티", "U": "유", "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}
# 글자로 읽지 않고 낱말로 읽는 대문자 말(필요할 때 더한다)
WORD_ACRONYMS = {"TV": "티비", "CCTV": "씨씨티비", "NASA": "나사", "KAIST": "카이스트", "UNESCO": "유네스코"}


def _spell_acronym(match: re.Match[str]) -> str:
    word = match.group(0)
    return WORD_ACRONYMS.get(word) or "".join(LETTER_READINGS[char] for char in word)


def _read_fraction(match: re.Match[str]) -> str:
    """3분의 1 → '삼분의 일'. 뒤의 '만'(…만 먹었어)을 금액으로 읽지 않게 먼저 바꾼다."""
    return f"{sino_korean(int(match.group(1)))}분의 {sino_korean(int(match.group(2)))}"


def _read_zero_led(match: re.Match[str]) -> str:
    """0으로 시작하는 번호(우편번호 04001, 코드 0123)는 한 자씩: '공사공공일'."""
    return "".join(PHONE_DIGITS[int(char)] for char in match.group(0))


def _read_times(match: re.Match[str]) -> str:
    """횟수 '번'은 고유어: 하루 3번 → '하루 세 번', 2번씩 → '두 번씩'. '3번 출구'(번호)는 한자어로 남긴다."""
    number = int(match.group(2))
    reading = native_korean(number) if 1 <= number <= NATIVE_MAX else sino_korean(number)
    return f"{match.group(1)}{reading} 번{match.group(3)}"


def _read_thousands(match: re.Match[str]) -> str:
    """천·백 단위가 붙은 수: 1천 → '천'(일천 아님), 7천 → '칠천', 5백 → '오백'. 2026-11-19 사용자 청취: '일천 원'이 어색."""
    value = int(match.group(1)) * (1000 if match.group(2) == "천" else 100)
    return sino_korean(value)


def _read_dollars(match: re.Match[str]) -> str:
    return f"{match.group(1)} 달러"


def sino_korean(number: int) -> str:
    """한자어 수: 380000000 → '삼억 팔천만'."""
    if number < 0:
        raise ValueError("음수는 지원하지 않습니다.")
    if number == 0:
        return "영"
    if number >= 10 ** 16:
        raise ValueError("너무 큰 수입니다.")
    groups: list[str] = []
    large_index = 0
    while number > 0:
        group_value = number % 10000
        number //= 10000
        if group_value:
            unit = SINO_LARGE_UNITS[large_index]
            words = _sino_group(group_value)
            if unit == "만" and group_value == 1:
                words = ""
            groups.append(words + unit)
        large_index += 1
    return " ".join(reversed(groups))


def _sino_group(value: int) -> str:
    words = []
    for position in range(3, -1, -1):
        digit = (value // 10 ** position) % 10
        if digit == 0:
            continue
        digit_word = "" if (digit == 1 and position > 0) else SINO_DIGITS[digit]
        words.append(digit_word + SINO_SMALL_UNITS[position])
    return "".join(words)


def native_korean(number: int) -> str:
    """고유어 수(단위 앞 꼴): 3 → '세', 20 → '스무', 21 → '스물한'. 1~99 만."""
    if not 1 <= number <= NATIVE_MAX:
        raise ValueError("고유어 수는 1~99 만 지원합니다.")
    tens, ones = divmod(number, 10)
    if tens == 2 and ones == 0:
        return "스무"
    return NATIVE_TENS[tens] + NATIVE_ONES[ones]


def _read_phone(match: re.Match[str]) -> str:
    parts = match.group(0).split("-")
    return " ".join("".join(PHONE_DIGITS[int(char)] for char in part) for part in parts)


def _read_money(match: re.Match[str]) -> str:
    amount = float(match.group(1).replace(",", ""))
    unit = 10 ** 8 if match.group(2) == "억" else 10 ** 4
    won = match.group(3) or ""
    return sino_korean(round(amount * unit)) + (" 원" if won else "")


def _read_time(match: re.Match[str]) -> str:
    hour = int(match.group(1))
    hour_word = native_korean(hour) if 1 <= hour <= 12 else sino_korean(hour)
    text = f"{hour_word} 시"
    if match.group(2):
        minute = int(match.group(2))
        if minute:
            text += f" {sino_korean(minute)} 분"
    return text


def _read_month(match: re.Match[str]) -> str:
    month = int(match.group(1))
    if not 1 <= month <= 12:
        return match.group(0)
    return MONTH_READINGS.get(month, sino_korean(month) + "월")


def _read_day(match: re.Match[str]) -> str:
    """11월 4일 → '사일'. 숫자 읽기가 '일'로 끝나면(1·11·21·31일) 띄어 쓴다: '일 일', '이십일 일'.
    2026-11-12 사용자 청취: 107 이 '십이월 일일'을 붙여 읽으면 어색했고, '일 일'(띄어 씀)이 가장 자연스러웠다
    ('이릴'·'초하루'·'일일'과 비교)."""
    reading = sino_korean(int(match.group(1)))
    return f"{reading} 일" if reading.endswith("일") else f"{reading}일"


def _read_counter(match: re.Match[str]) -> str:
    number = int(match.group(1))
    counter = match.group(2)
    if 1 <= number <= NATIVE_MAX:
        return f"{native_korean(number)} {counter}"
    return f"{sino_korean(number)} {counter}"


def _read_plain_number(match: re.Match[str]) -> str:
    return sino_korean(int(match.group(0).replace(",", "")))


def _read_iso_date(match: re.Match[str]) -> str:
    """2026-11-12, 2026.11.12 → '2026년 11월 12일' (뒤에서 다시 한글로 읽는다). 없는 달·날이면 그대로."""
    year, month, day = (int(part) for part in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return match.group(0)
    return f"{year}년 {month}월 {day}일"


def _read_clock(match: re.Match[str]) -> str:
    """14:30 → '14시 30분', 09:00 → '9시'."""
    hour, minute = int(match.group(1)), int(match.group(2))
    return f"{hour}시 {minute}분" if minute else f"{hour}시"


def _read_decimal(match: re.Match[str]) -> str:
    """37.5 → '삼십칠 점 오', 0.25 → '영 점 이오'(소수 자리는 한 자씩)."""
    whole = sino_korean(int(match.group(1)))
    return f"{whole} 점 " + "".join(DECIMAL_DIGITS[int(char)] for char in match.group(2))


def _read_ordinal(match: re.Match[str]) -> str:
    number = int(match.group(1))
    if number == 1:
        return "첫 번째"
    return f"{native_korean(number) if number <= NATIVE_MAX else sino_korean(number)} 번째"


def _counter_pattern() -> str:
    """긴 단위부터. '개월'(삼 개월)·'달러'(오 달러)는 한자어로 읽으므로 고유어 단위로 보지 않는다."""
    blocked_after = {"개": "월", "달": "러"}
    parts = []
    for counter in sorted(NATIVE_COUNTERS, key=len, reverse=True):
        after = blocked_after.get(counter)
        parts.append(f"{counter}(?!{after})" if after else counter)
    return "|".join(parts)


COUNTER_PATTERN = _counter_pattern()
UNIT_PATTERN = "|".join(re.escape(symbol) for symbol, _ in UNIT_READINGS)
UNIT_LOOKUP = dict(UNIT_READINGS)
RANGE_PATTERN = "|".join(f"{unit}(?!월)" if unit == "개" else unit for unit in RANGE_UNITS)
NUMBER = r"\d{1,3}(?:,\d{3})+|\d+"


def normalize_for_speech(text: str) -> str:
    """화면용 글을 TTS 가 읽기 좋은 글로 바꾼다."""
    result = text
    # \b 는 한글을 글자로 보아 "4567이에요" 에서 끊지 못하므로 숫자 경계로 판단한다.
    result = re.sub(r"(?<!\d)0\d{1,2}-\d{3,4}-\d{4}(?!\d)", _read_phone, result)
    # 행사·기호 꼴: 1+1 → 원 플러스 원, Q&A → 큐앤에이, $5 → 5 달러(뒤에서 숫자를 읽는다)
    result = re.sub(r"(?<![\d+])1\s*\+\s*1(?![\d+])", "원 플러스 원", result)
    result = re.sub(r"(?<![\d+])2\s*\+\s*1(?![\d+])", "투 플러스 원", result)
    result = result.replace("Q&A", "큐앤에이")
    result = re.sub(r"\$\s?(\d+(?:\.\d+)?)", _read_dollars, result)
    result = re.sub(r"(?<![\d.])(\d{1,3})\s*분의\s*(\d{1,3})(?![\d.])", _read_fraction, result)
    result = re.sub(r"(?<![\d.,-])0\d{2,}(?![\d.,-])", _read_zero_led, result)
    # 횟수: '하루·일주일에·한 달에·매일·매주' 뒤나 '번씩' 꼴의 번은 고유어
    result = re.sub(
        r"((?:하루에?|일주일에|1주일에|주에|한 달에|달에|매일|매주|매달)\s*)(\d{1,2})\s*번(?!째)(\S*)", _read_times, result
    )
    result = re.sub(r"()(?<![\d.])(\d{1,2})\s*번(씩)", _read_times, result)
    # 날짜·시각 꼴을 먼저 '년·월·일·시·분' 글로 바꿔 두면 아래 규칙이 그대로 읽는다.
    result = re.sub(r"(?<![\d.-])(\d{4})[-.](\d{1,2})[-.](\d{1,2})(?![\d.-])", _read_iso_date, result)
    result = re.sub(r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])", _read_clock, result)
    # 단위 기호: 5ml → 5 밀리리터, 30% → 30 퍼센트 (숫자 바로 뒤에 있을 때만)
    result = re.sub(
        rf"(?<=\d)\s*({UNIT_PATTERN})(?![A-Za-z])", lambda m: " " + UNIT_LOOKUP[m.group(1)], result
    )
    # 범위: 2~3개 → 2개~3개 (앞 숫자도 단위와 같이 읽게)
    result = re.sub(
        rf"(?<![\d.])(\d+(?:\.\d+)?)\s*~\s*(?=(\d+(?:\.\d+)?)\s*({RANGE_PATTERN}))",
        lambda m: f"{m.group(1)}{m.group(3)}~",
        result,
    )
    # '원'이 없으면 뒤 공백을 남긴다: "4만 2천 원" → "사만 이천 원"
    result = re.sub(rf"(?<![\d.,])((?:{NUMBER})(?:\.\d+)?)\s*(억|만)(?:\s*(원))?", _read_money, result)
    result = re.sub(r"(?<![\d.,])(\d{1,2})\s*(천|백)", _read_thousands, result)
    result = re.sub(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])", _read_decimal, result)
    result = re.sub(r"(\d{1,2})\s*시(?!간)(?:\s*(\d{1,2})\s*분)?", _read_time, result)
    result = re.sub(r"(\d{1,2})\s*월", _read_month, result)
    result = re.sub(r"(\d{1,2})\s*일", _read_day, result)
    result = re.sub(r"(?<![\d.])(\d{1,3})\s*번째", _read_ordinal, result)
    result = re.sub(rf"(?<![\d.,])(\d{{1,3}})\s*({COUNTER_PATTERN})", _read_counter, result)
    result = re.sub(NUMBER, _read_plain_number, result)
    for abbreviation, reading in ABBREVIATIONS.items():
        result = re.sub(rf"(?<![A-Za-z]){abbreviation}(?![A-Za-z])", reading, result)
    # 나머지 대문자 약어(2~5자)는 글자로 읽는다: KTX → 케이티엑스, SNS → 에스엔에스
    result = re.sub(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])", _spell_acronym, result)
    # 기호: '&'는 '앤', '→'는 '에서', 'x2' 같은 곱하기는 그대로 둔다
    result = re.sub(r"(?<=\S)\s*&\s*(?=\S)", " 앤 ", result)
    result = result.replace("→", " 에서 ").replace("·", ", ")
    result = result.replace("~", "에서 ")
    return re.sub(r"[ \t]{2,}", " ", result).strip()
