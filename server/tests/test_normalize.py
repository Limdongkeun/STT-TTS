import pytest

from app.normalize import native_korean, normalize_for_speech, sino_korean


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "영"),
        (1, "일"),
        (10, "십"),
        (15, "십오"),
        (30, "삼십"),
        (110, "백십"),
        (1000, "천"),
        (2026, "이천이십육"),
        (10000, "만"),
        (15000, "만 오천"),
        (100000000, "일억"),
        (380000000, "삼억 팔천만"),
        (120005, "십이만 오"),
    ],
)
def test_sino_korean(number, expected):
    assert sino_korean(number) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "한"), (3, "세"), (4, "네"), (10, "열"), (11, "열한"), (20, "스무"), (21, "스물한"), (99, "아흔아홉")],
)
def test_native_korean(number, expected):
    assert native_korean(number) == expected


@pytest.mark.parametrize("number", [0, 100, -1])
def test_native_korean_out_of_range(number):
    with pytest.raises(ValueError):
        native_korean(number)


def test_sino_korean_rejects_negative():
    with pytest.raises(ValueError):
        sino_korean(-5)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("오후 3시 30분", "오후 세 시 삼십 분"),
        ("저녁 7시", "저녁 일곱 시"),
        ("12시 정각", "열두 시 정각"),
        ("15시", "십오 시"),
        ("2시간 걸려요", "두 시간 걸려요"),
        ("11월 4일", "십일월 사일"),
        ("6월 10일", "유월 십일"),
        ("10월", "시월"),
        ("4명이 와요", "네 명이 와요"),
        ("사과 3개", "사과 세 개"),
        ("3.8억 원", "삼억 팔천만 원"),
        ("5만원", "오만 원"),
        ("12,000원", "만 이천원"),
        ("010-1234-5678", "공일공 일이삼사 오육칠팔"),
        ("번호는 02-123-4567이에요", "번호는 공이 일이삼 사오육칠이에요"),
        ("AI 가족비서", "에이아이 가족비서"),
        ("3시~5시", "세 시에서 다섯 시"),
        ("숫자 없는 문장", "숫자 없는 문장"),
        ("부탁은 1건이에요", "부탁은 한 건이에요"),
        ("가스비 4만 2천 원", "가스비 사만 이천 원"),
        ("23만 4천 원은 남편이", "이십삼만 사천 원은 남편이"),
        ("2027년 1월 15일", "이천이십칠년 일월 십오일"),
    ],
)
def test_normalize_for_speech(text, expected):
    assert normalize_for_speech(text) == expected


def test_slash_date_is_left_as_is():
    # 빗금 날짜는 뜻이 갈려서 바꾸지 않는다(문서 참고). 숫자만 한자어로 읽힌다.
    assert "/" in normalize_for_speech("11/4")


def test_counter_above_native_range_uses_sino():
    assert normalize_for_speech("120명") == "백이십 명"
