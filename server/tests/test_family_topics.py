"""가족 기록 주제별 답 (.scratch/family-shared-tasks/spec.md 의 D1~D25 와 경계·실패)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.family_records import format_won, parse_won
from app.family_demo import KST, FamilyDemoAnswerProvider
from app.main import create_app
from app.normalize import normalize_for_speech
from tests.test_api import make_settings

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=KST)  # 목요일

SCENARIO = [
    ("wife", "장보기 목록 뭐 남았어?", "장보기 목록은 두부, 계란 2가지예요."),
    ("wife", "우유랑 기저귀 장보기 목록에 넣어줘", "장보기 목록에 우유, 기저귀를 넣었어요. 지금 목록은 두부, 계란, 우유, 기저귀예요."),
    ("wife", "기저귀는 아내가 샀어", "기저귀는 장보기 목록에서 뺐어요. 남은 건 두부, 계란, 우유예요."),
    ("wife", "이번 달 관리비 냈어?", "관리비 23만 4천 원은 남편이 11월 3일에 냈어요."),
    ("wife", "가스비 얼마 내야 돼?", "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요."),
    ("wife", "가스비 아내가 냈어", "가스비 4만 2천 원은 아내가 11월 5일에 낸 걸로 기록했어요."),
    ("wife", "이번 달 생활비 얼마 남았어?", "이번 달 생활비 150만 원 중 98만 원을 써서 52만 원 남았어요."),
    ("wife", "오늘 마트에서 8만 4천 원 썼어", "마트 8만 4천 원을 기록했어요. 이번 달 생활비는 43만 6천 원 남았어요."),
    ("wife", "내일 어린이집 하원 누가 가?", "11월 6일 금요일 하원은 아내가 가요."),
    ("wife", "목요일 하원은 아내가 가는 걸로 바꿔줘", "목요일 하원은 아내가 가는 걸로 바꿨어요."),
    ("wife", "이번 주 분리수거 누구 차례야?", "이번 주 분리수거는 남편 차례예요. 아직 안 했어요."),
    ("wife", "빨래 아내가 했다고 체크해줘", "오늘 빨래는 아내가 한 걸로 체크했어요."),
    ("wife", "남편한테 퇴근길에 약국 들러 달라고 부탁해줘", "남편에게 '퇴근길에 약국 들러' 부탁을 보냈어요."),
    ("wife", "남편한테 온 부탁 뭐 있어?", "남편에게 온 부탁은 1건이에요. 아내가 부탁한 '퇴근길에 약국 들러'예요."),
    ("wife", "남편이 약국 부탁 다 했어", "'퇴근길에 약국 들러' 부탁을 끝낸 걸로 표시했어요."),
    ("wife", "아내한테 온 부탁 뭐 있어?", "아내에게 온 부탁은 1건이에요. 남편이 부탁한 '소윤이 우산 챙기기'예요."),
    ("wife", "시어머니 생신 선물 뭐 하기로 했지?", "시어머니 생신은 11월 20일이에요. 선물은 안마기로 정했고, 남편이 주문하기로 했어요."),
    ("wife", "이번 달 친정 용돈 보냈어?", "이번 달 친정 용돈 30만 원은 아직 안 보냈어요. 매달 10일에 보내기로 했어요."),
    ("wife", "친정 용돈 아내가 보냈어", "이번 달 친정 용돈 30만 원은 아내가 보낸 걸로 기록했어요."),
    ("wife", "자동차 보험 언제 끝나?", "자동차 보험은 12월 3일에 끝나요. 28일 남았어요."),
    (
        "wife",
        "만기 다가오는 거 뭐 있어?",
        "곧 끝나는 건 자동차 보험 12월 3일, 자동차 정기검사 2027년 2월 14일, 남편 여권 2027년 5월 30일이에요.",
    ),
    ("wife", "소윤이 내일 준비물 뭐야?", "11월 6일 금요일 소윤이 준비물은 색종이, 풀이에요."),
    ("wife", "현장학습 동의서 냈어?", "현장학습 동의서는 아직 안 냈어요. 11월 7일까지 내야 해요."),
    (
        "wife",
        "콩이 심장사상충 약 언제 먹여야 돼?",
        "콩이 심장사상충 약은 매달 1일에 먹여요. 이번 달은 11월 1일에 남편이 먹였고, 다음은 12월 1일이에요.",
    ),
    ("wife", "콩이 예방접종 언제야?", "콩이 종합백신은 2027년 1월 15일 예정이에요."),
]


@pytest.fixture
def provider() -> FamilyDemoAnswerProvider:
    return FamilyDemoAnswerProvider()


def ask(provider: FamilyDemoAnswerProvider, question: str, speaker: str = "wife") -> str:
    return provider.answer(question, speaker=speaker, now=NOW)[0]


def test_spec_scenario_d1_to_d25_in_order(provider):
    for index, (speaker, question, expected) in enumerate(SCENARIO, start=1):
        assert ask(provider, question, speaker) == expected, f"D{index}: {question}"


def test_scenario_answers_read_naturally():
    assert normalize_for_speech(SCENARIO[4][2]) == "가스비 사만 이천 원은 아직 안 냈어요. 십일월 이십오일까지 내야 해요."
    assert normalize_for_speech(SCENARIO[0][2]) == "장보기 목록은 두부, 계란 두 가지예요."


# ── 경계·실패 ─────────────────────────────────────────────


def test_unknown_item_does_not_change_list(provider):
    assert ask(provider, "장보기 목록에서 바나나 샀어") == "장보기 목록에서 그 물건을 못 찾았어요."
    assert ask(provider, "장보기 목록 뭐 남았어") == "장보기 목록은 두부, 계란 2가지예요."


def test_add_items_after_list_word_and_empty_list(provider):
    assert ask(provider, "장보기 목록에 휴지 넣어줘").startswith("장보기 목록에 휴지를 넣었어요.")
    assert ask(provider, "두부랑 계란, 휴지 내가 샀어") == "두부, 계란, 휴지는 장보기 목록에서 뺐어요. 이제 목록이 비었어요."
    assert ask(provider, "장보기 뭐 남았어?") == "장보기 목록이 비어 있어요."
    assert ask(provider, "장보기 목록에 넣어줘") == "장보기 목록에 넣을 물건을 같이 말해 주세요."


def test_spending_needs_amount_and_comma_amount_works(provider):
    assert ask(provider, "마트에서 썼어") == "얼마를 썼는지 금액을 같이 말해 주세요."
    assert ask(provider, "약국에서 84,000원 썼어") == "약국 8만 4천 원을 기록했어요. 이번 달 생활비는 43만 6천 원 남았어요."
    assert ask(provider, "이번 달 얼마 썼어?") == "이번 달 생활비 150만 원 중 106만 4천 원을 써서 43만 6천 원 남았어요."


def test_overspending_is_reported(provider):
    assert ask(provider, "가구점에서 100만 원 썼어") == "가구점 100만 원을 기록했어요. 예산을 48만 원 넘었어요."


def test_childcare_needs_day_and_weekend_is_closed(provider):
    assert ask(provider, "하원 남편이 가는 걸로 바꿔줘") == "어느 요일 하원인지 같이 말해 주세요."
    assert ask(provider, "토요일 하원 누가 가?") == "토요일은 어린이집이 쉬어요."
    assert ask(provider, "월요일 하원은 내가 갈게", speaker="husband") == "월요일 하원은 남편이 가는 걸로 바꿨어요."
    assert ask(provider, "월요일 하원 누가 가?") == "월요일 하원은 남편이 가요."
    assert ask(provider, "오늘 등원 누가 했어?") == "11월 5일 목요일 등원은 남편이 가요."


def test_requests_edge_cases(provider):
    # 역할 없이: "아내한테" 부탁하면 보낸 사람은 남편
    assert ask(provider, "아내한테 빨래 개 달라고 부탁해줘") == "아내에게 '빨래 개' 부탁을 보냈어요."
    assert ask(provider, "남편이 부탁한 거 뭐 있어").startswith("남편이 보낸 부탁 중 남은 건 2건이에요.")
    assert ask(provider, "아내가 부탁 다 했어") == "'빨래 개' 부탁을 끝낸 걸로 표시했어요."
    assert ask(provider, "나한테 온 부탁 뭐 있어", speaker="husband") == "남편에게 온 부탁이 없어요."
    assert ask(provider, "여보한테 우유 사 오라고 부탁해줘", speaker="husband") == "아내에게 '우유 사 오라고' 부탁을 보냈어요."
    assert ask(provider, "내가 부탁한 거 뭐 있어", speaker="husband").startswith("남편이 보낸 부탁 중 남은 건 2건이에요.")
    assert ask(provider, "부탁 다 했어") == "'우유 사 오라고' 부탁을 끝낸 걸로 표시했어요."


def test_supplies_on_unprepared_day(provider):
    assert ask(provider, "소윤이 오늘 준비물 뭐야") == (
        "11월 5일 목요일 준비물은 시험 데이터에 없어요. 준비된 날은 11월 6일 금요일이에요."
    )


def test_done_markers_update_records(provider):
    assert ask(provider, "현장학습 동의서 내가 냈어") == "현장학습 동의서는 아내가 낸 걸로 표시했어요."
    assert ask(provider, "현장학습 동의서 냈어?", speaker="husband") == "현장학습 동의서는 아내가 냈어요."
    assert ask(provider, "분리수거 내가 했어", speaker="husband") == "이번 주 분리수거는 남편이 한 걸로 체크했어요."
    assert ask(provider, "분리수거 누구 차례야") == "이번 주 분리수거는 남편 차례예요. 남편이 했어요."
    assert ask(provider, "콩이 약 내가 먹였어") == "이번 달 콩이 심장사상충 약은 아내가 먹인 걸로 기록했어요."


def test_bill_due_date_update_and_summary(provider):
    assert ask(provider, "가스비 28일까지 내야 돼") == "가스비 납부 기한을 11월 28일로 적었어요."
    assert ask(provider, "통신비 언제 나가?") == "통신비 8만 9천 원은 매달 20일 자동이체예요."
    assert ask(provider, "공과금 안 낸 거 있어?") == "아직 안 낸 공과금은 가스비 4만 2천 원이에요."


def test_birthday_and_allowance_without_side(provider):
    assert ask(provider, "친정엄마 생신 선물 정했어?") == "친정엄마 생신은 2027년 3월 8일이에요. 선물은 아직 안 정했어요."
    assert ask(provider, "이번 달 용돈 보냈어?") == (
        "이번 달 친정 용돈 30만 원은 아직 안 보냈어요. 매달 10일에 보내기로 했어요. "
        "이번 달 시댁 용돈 30만 원은 아직 안 보냈어요. 매달 10일에 보내기로 했어요."
    )


def test_existing_c_questions_still_work(provider):
    assert "화요일에 가족 식사" in ask(provider, "다음 주 우리 집 일정 뭐야?")
    assert "수요일에 학교 체험학습" in ask(provider, "소윤이 이번 주 학교 학원 일정 뭐야?")
    assert "11월 12일 목요일 오전 10시" in ask(provider, "아버지 병원 예약 언제였지?")
    assert ask(provider, "애기 해열제 부르펜 계열 먹었는데 시간 체크해줘") == "몇 시에 먹였나요?"


@pytest.mark.parametrize(
    ("amount", "text"),
    [(84_000, "8만 4천 원"), (1_500_000, "150만 원"), (300_000, "30만 원"), (4_500, "4,500 원"), (12_345, "1만 2,345 원")],
)
def test_format_won(amount, text):
    assert format_won(amount) == text


@pytest.mark.parametrize(
    ("compact", "amount"),
    [("8만4천원썼어", 84_000), ("84000원", 84_000), ("8만원", 80_000), ("3천원", 3_000), ("원래", None), ("돈썼어", None)],
)
def test_parse_won(compact, amount):
    assert parse_won(compact) == amount


# ── API ─────────────────────────────────────────────


def test_api_shares_records_between_speakers_and_resets():
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))

    def post(text: str, speaker: str) -> str:
        response = client.post("/ask", json={"text": text, "speaker": speaker})
        assert response.status_code == 200
        return response.json()["answerText"]

    assert post("남편한테 우유 사 달라고 부탁해줘", "wife") == "남편에게 '우유 사' 부탁을 보냈어요."
    assert "아내가 부탁한 '우유 사'" in post("나한테 온 부탁 뭐 있어", "husband")
    assert client.post("/demo/reset").json() == {"status": "reset"}
    assert post("나한테 온 부탁 뭐 있어", "husband") == "남편에게 온 부탁이 없어요."


def test_api_rejects_unknown_speaker():
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))
    assert client.post("/ask", json={"text": "장보기 뭐 남았어", "speaker": "grandma"}).status_code == 422


def test_reset_is_not_found_for_fixed_answers():
    client = TestClient(create_app(make_settings(answer_provider="fixed")))
    assert client.post("/demo/reset").status_code == 404


# ── 역할 없이 문장 속 남편·아내로 누가 했는지 ─────────────────────


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("가스비 남편이 냈어", "가스비 4만 2천 원은 남편이 11월 5일에 낸 걸로 기록했어요."),
        ("분리수거 남편이 했다고 체크해줘", "이번 주 분리수거는 남편이 한 걸로 체크했어요."),
        ("시댁 용돈 남편이 보냈어", "이번 달 시댁 용돈 30만 원은 남편이 보낸 걸로 기록했어요."),
        ("현장학습 동의서 남편이 냈어", "현장학습 동의서는 남편이 낸 걸로 표시했어요."),
        ("콩이 약 남편이 먹였어", "이번 달 콩이 심장사상충 약은 남편이 먹인 걸로 기록했어요."),
        ("가스비 내가 냈어", "가스비 4만 2천 원은 아내가 11월 5일에 낸 걸로 기록했어요."),  # '내가'는 기본 사람(아내)
    ],
)
def test_named_person_records(provider, question, expected):
    assert ask(provider, question) == expected


def test_question_mark_with_person_is_a_question_not_a_record(provider):
    assert ask(provider, "가스비 남편이 냈어?") == "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요."
    assert ask(provider, "가스비 얼마야") == "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요."


def test_request_query_by_name_does_not_create_request(provider):
    assert ask(provider, "남편한테 온 부탁 뭐 있어?") == "남편에게 온 부탁이 없어요."
    assert ask(provider, "남편에게 부탁 온 거 있어") == "남편에게 온 부탁이 없어요."
    assert ask(provider, "아내가 부탁한 거 뭐 있어") == "아내가 보낸 부탁 중 남은 게 없어요."


def test_e1_netflix_found_even_when_stt_writes_english():
    from app.family_demo import DEMO_NOW, FamilyDemoAnswerProvider

    provider = FamilyDemoAnswerProvider()
    for question in ("넷플릭스 구독료 언제 빠져나가?", "Netflix 구독료 언제 빠져나가?"):
        assert provider.answer(question, None, now=DEMO_NOW)[0] == "넷플릭스 1만 7천 원은 매달 22일 자동이체예요."
    # 자동이체라 '아직 안 낸 공과금'에는 들어가지 않는다
    assert "넷플릭스" not in provider.answer("아직 안 낸 공과금 뭐 있어?", None, now=DEMO_NOW)[0]


def test_e2_blood_pressure_medicine_points_to_next_visit_and_c6_unchanged():
    from app.family_demo import DEMO_NOW, FamilyDemoAnswerProvider

    provider = FamilyDemoAnswerProvider()
    e2 = provider.answer("아버지 혈압약 다 떨어졌는데 다음 병원 언제야?", None, now=DEMO_NOW)[0]
    assert e2 == "아버지 다음 진료는 11월 12일 목요일 오전 10시예요. 혈압약 처방은 그때 받으면 돼요."
    c6 = provider.answer("아버지 병원 예약 언제였지?", None, now=DEMO_NOW)[0]
    assert c6.startswith("11월 2일에 등록한 아버지 병원 예약은")
    # 예약도 혈압약도 아닌 병원 말은 이 주제가 아니다
    assert provider.answer("아버지 병원 가는 길 알려줘", None, now=DEMO_NOW)[0] == "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."

