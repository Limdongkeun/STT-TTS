"""화면용 글 → 읽기용 글 (한국어 텍스트 정규화).

TTS 가 자주 틀리는 숫자·시간·날짜·금액·전화번호·영어 약어를 한글 읽기로 바꾼다.
처음 버전은 자주 나오는 경우만 다룬다. 어색한 사례가 나오면 규칙을 더한다.
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
# '번'은 '두 번(횟수)'과 '3번 버스(번호)'가 갈려서 넣지 않았다.
NATIVE_COUNTERS = ("시간", "개", "명", "살", "마리", "잔", "권", "곳", "가지")

ABBREVIATIONS = {
    "AI": "에이아이",
    "DB": "디비",
    "TTS": "티티에스",
    "STT": "에스티티",
    "SMS": "에스엠에스",
    "OK": "오케이",
}

MONTH_READINGS = {6: "유월", 10: "시월"}


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


def _read_counter(match: re.Match[str]) -> str:
    number = int(match.group(1))
    counter = match.group(2)
    if 1 <= number <= NATIVE_MAX:
        return f"{native_korean(number)} {counter}"
    return f"{sino_korean(number)} {counter}"


def _read_plain_number(match: re.Match[str]) -> str:
    return sino_korean(int(match.group(0).replace(",", "")))


def normalize_for_speech(text: str) -> str:
    """화면용 글을 TTS 가 읽기 좋은 글로 바꾼다."""
    result = text
    # \b 는 한글을 글자로 보아 "4567이에요" 에서 끊지 못하므로 숫자 경계로 판단한다.
    result = re.sub(r"(?<!\d)0\d{1,2}-\d{3,4}-\d{4}(?!\d)", _read_phone, result)
    result = re.sub(r"(\d+(?:\.\d+)?)\s*(억|만)\s*(원)?", _read_money, result)
    result = re.sub(r"(\d{1,2})\s*시(?!간)(?:\s*(\d{1,2})\s*분)?", _read_time, result)
    result = re.sub(r"(\d{1,2})\s*월", _read_month, result)
    result = re.sub(r"(\d{1,2})\s*일", lambda m: sino_korean(int(m.group(1))) + "일", result)
    counters = "|".join(NATIVE_COUNTERS)
    result = re.sub(rf"(\d{{1,3}})\s*({counters})", _read_counter, result)
    result = re.sub(r"\d{1,3}(?:,\d{3})+|\d+", _read_plain_number, result)
    for abbreviation, reading in ABBREVIATIONS.items():
        result = re.sub(rf"(?<![A-Za-z]){abbreviation}(?![A-Za-z])", reading, result)
    result = result.replace("~", "에서 ")
    return re.sub(r"[ \t]{2,}", " ", result).strip()
