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


# 2026-11-12: 실제 LLM·DB 답에 나올 꼴(소수·단위·약 개수·시각·날짜·범위) — 시험 답 밖의 빈틈
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("체온이 37.5도예요", "체온이 삼십칠 점 오도예요"),
        ("0.25", "영 점 이오"),
        ("2.5시간 걸려요", "이 점 오시간 걸려요"),
        ("해열제 5ml 먹였어요", "해열제 오 밀리리터 먹였어요"),
        ("200mg", "이백 밀리그램"),
        ("몸무게 12.3kg", "몸무게 십이 점 삼 킬로그램"),
        ("할인율 30%예요", "할인율 삼십 퍼센트예요"),
        ("25℃", "이십오 도"),
        ("25°C", "이십오 도"),
        ("2알 먹여요", "두 알 먹여요"),
        ("1포 먹여요", "한 포 먹여요"),
        ("3달 남았어요", "세 달 남았어요"),
        ("우유 2병", "우유 두 병"),
        ("1번째", "첫 번째"),
        ("11번째", "열한 번째"),
        ("1,200만 원이에요", "천이백만 원이에요"),
        ("14:30에 와요", "십사 시 삼십 분에 와요"),
        ("09:00", "아홉 시"),
        ("2026-11-12에 가요", "이천이십육년 십일월 십이일에 가요"),
        ("2026.11.12", "이천이십육년 십일월 십이일"),
        ("3~4시에 와요", "세 시에서 네 시에 와요"),
        ("2~3개 사요", "두 개에서 세 개 사요"),
        ("10~20만 원", "십만에서 이십만 원"),
    ],
)
def test_normalize_real_answer_shapes(text, expected):
    assert normalize_for_speech(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3개월", "삼개월"),  # '개월'은 한자어
        ("5달러", "오달러"),  # '달러'는 고유어 '달'이 아니다
        ("20대", "이십대"),  # 나이대는 한자어('대'는 고유어 단위에서 뺐다)
        ("1234개", "천이백삼십사개"),  # 네 자리 수 일부만 고유어로 읽지 않는다
        ("2026-13-40", "이천이십육-십삼-사십"),  # 없는 날짜는 날짜로 읽지 않는다
        ("버전 1.2.3", "버전 일.이.삼"),  # 점이 둘인 글은 소수가 아니다
        ("크기 3 MB", "크기 삼 MB"),  # 모르는 기호는 그대로
    ],
)
def test_normalize_leaves_ambiguous_shapes(text, expected):
    assert normalize_for_speech(text) == expected


# 2026-11-12 사용자 청취: '일일'을 붙여 읽으면 어색 → 숫자 읽기가 '일'로 끝나는 날은 띄어 쓴다
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12월 1일", "십이월 일 일"),
        ("매달 11일", "매달 십일 일"),
        ("21일까지", "이십일 일까지"),
        ("31일", "삼십일 일"),
        ("12월 2일", "십이월 이일"),  # '일'로 안 끝나면 그대로 붙인다
        ("10일", "십일"),
    ],
)
def test_day_ending_in_il_is_spaced(text, expected):
    assert normalize_for_speech(text) == expected
