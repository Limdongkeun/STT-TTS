import logging
import unicodedata
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.family_demo import KST, FamilyDemoAnswerProvider, compact_question
from app.main import create_app
from app.stt_correction import correct_transcript, korean_number
from tests.test_api import make_settings

THIS_WEEK = "소윤이는 수요일에 학교 체험학습"
NEXT_WEEK_GUIDE = "이번 주 학교와 학원 일정만 준비돼 있어요"
BASE = "소윤이 이번 주 학교 학원 일정 뭐야"


def answer_text(question: str) -> str:
    return FamilyDemoAnswerProvider().answer(question)[0]


def test_compact_question_keeps_letters_and_digits_only():
    assert compact_question("소윤이 이번​주, 학교·학원?\t30분 전!") == "소윤이이번주학교학원30분전"
    assert compact_question(unicodedata.normalize("NFD", "소윤")) == "소윤"
    assert compact_question("   ") == ""


@pytest.mark.parametrize(
    "question",
    [
        BASE,
        BASE.replace(" ", "​"),  # 폭 없는 공백
        BASE.replace(" ", " "),  # 줄바꿈 없는 공백
        unicodedata.normalize("NFD", BASE),
        "소윤이 이번 주, 학교, 학원 일정 뭐야?",
        "소윤이 이번주 학교 학원 일정 뭐야",
        "소윤이 금주 학교 학원 일정 뭐야",
        "소윤이 이번 쭈 학교 학원 일정 뭐야",
        "소윤이 학원 언제 가?",
    ],
)
def test_soyun_this_week_variants(question):
    assert THIS_WEEK in answer_text(question)


@pytest.mark.parametrize(
    "question",
    ["소윤이 다음 주 학교 학원 일정 뭐야", "소윤이​다음​주​일정​뭐야?"],
)
def test_soyun_next_week_gets_scope_guide(question):
    assert NEXT_WEEK_GUIDE in answer_text(question)


def test_other_routes_survive_invisible_characters():
    assert "화요일에 가족 식사" in answer_text("다음​주​우리​집​일정​뭐야?")
    assert "11월 12일 목요일 오전 10시" in answer_text("아버지, 병원 예약 언제였지?")
    assert answer_text("애기​해열제​부르펜 계열 먹었는데 시간 체크해줘.") == "몇 시에 먹였나요?"


def test_unrelated_question_has_no_prepared_answer():
    assert answer_text("오늘 날씨 어때?") == "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."
    assert answer_text("소윤이 좋아하는 음식 뭐야") == "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."


def test_ask_logs_question_with_invisible_characters(caplog):
    client = TestClient(create_app(make_settings(answer_provider="family-demo")))
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post("/ask", json={"text": "소윤이​이번 주 일정"})
    assert response.status_code == 200
    assert THIS_WEEK in response.json()["answerText"]
    assert "ask question='소윤이\\u200b이번 주 일정'" in caplog.text


# ── STT 보정 (app/stt_correction.py) ─────────────────────────


NOW = datetime(2026, 11, 5, 10, 0, tzinfo=KST)  # 목요일


@pytest.mark.parametrize(
    ("compact", "expected"),
    [
        ("와이프한테부탁해줘", "아내한테부탁해줘"),
        ("신랑이금요일하원간다고해", "남편이금요일하원간다고해"),
        ("시어머님생신", "시어머니생신"),
        ("어머님생신선물", "시어머니생신선물"),
        ("장모님생신언제야", "친정엄마생신언제야"),
        ("재활용분리배출누구차례야", "재활용분리수거누구차례야"),
        ("가스요금얼마야", "가스비얼마야"),
        ("핸드폰요금언제나가", "통신비언제나가"),
        ("콩이예방주사언제맞아", "콩이백신언제맞아"),
        ("서윤이이번주일정", "소윤이이번주일정"),
        ("소연한테물어봐", "소윤한테물어봐"),
        ("애기브루펜계열먹였어", "애기부르펜계열먹였어"),
        ("마트에서팔만사천원썼어", "마트에서84000원썼어"),
        ("관리비이십삼만사천원", "관리비234000원"),
        ("만원썼어", "10000원썼어"),
        ("8만사천원썼어", "8만4000원썼어"),
        # 실기기 시험(2026-11-05 14:10)에서 폰 STT 가 틀리게 받아 적은 말
        ("수연이이번주학교일정뭐야", "소윤이이번주학교일정뭐야"),
        ("내일어린이집학원누가가", "내일어린이집하원누가가"),
        ("이번달에7년용돈보냈어", "이번달에친정용돈보냈어"),
        ("칠년용돈", "친정용돈"),
        ("공기심장사상충약언제먹어야돼", "콩이심장사상충약언제먹어야돼"),
    ],
)
def test_correct_transcript_fixes_known_variants(compact, expected):
    assert correct_transcript(compact) == expected


@pytest.mark.parametrize(
    "compact",
    [
        "소연한날씨네",  # 이름 뒤에 조사가 없으면 이름으로 보지 않는다
        "공원가는길에약국들러",
        "구원받았어",  # 단위 없는 한글 숫자는 금액이 아니다
        "8만4천원썼어",  # 이미 숫자인 금액은 그대로
        "100만원썼어",
        "소윤이학원언제가",  # 어린이집이 없으면 학원은 학원
        "공기청정기켜줘",  # 반려견 말이 없으면 공기는 공기
        "7년동안모았어",  # 용돈 앞이 아니면 그대로
        "84000원",
        "",
    ],
)
def test_correct_transcript_leaves_other_text_alone(compact):
    assert correct_transcript(compact) == compact


@pytest.mark.parametrize(
    ("text", "value"),
    [("팔만사천", 84_000), ("이십삼만사천", 234_000), ("백오십만", 1_500_000), ("만", 10_000), ("삼천", 3_000), ("구", None)],
)
def test_korean_number(text, value):
    assert korean_number(text) == value


# ── STT 가 조금 다르게 적어도 알아듣는지 (주제별) ─────────────────


def fresh_answer(question: str, speaker: str = "wife") -> str:
    return FamilyDemoAnswerProvider().answer(question, speaker=speaker, now=NOW)[0]


@pytest.mark.parametrize(
    ("speaker", "question", "expected"),
    [
        # C1·C2·C6·C7 일정·병원
        ("wife", "다음주 우리집 일정은?", "화요일에 가족 식사, 토요일에 장보기가 있어요."),
        ("wife", "다음 주에 가족 일정 알려줘", "다음 주 가족 일정은 두 건이에요."),
        ("wife", "서윤이 이번 주 학교랑 학원 일정 알려줘", THIS_WEEK),
        ("wife", "소연이 다음주 학원 일정은?", NEXT_WEEK_GUIDE),
        ("wife", "아빠 병원 예약 언제지?", "11월 12일 목요일 오전 10시로 확인돼요."),
        ("wife", "아기 브루펜 해열제 먹였는데 시간 체크해 줘.", "몇 시에 먹였나요?"),
        # 1 장보기
        ("wife", "장 보기 목록에 뭐 있어?", "장보기 목록은 두부, 계란 2가지예요."),
        ("wife", "우유하고 휴지 장보기에 추가해 줘", "장보기 목록에 우유, 휴지를 넣었어요."),
        ("wife", "두부는 내가 샀다", "두부는 장보기 목록에서 뺐어요."),
        # 2 고정 지출
        ("wife", "가스 요금 얼마야?", "가스비 4만 2천 원은 아직 안 냈어요."),
        ("wife", "관리비 납부했어?", "관리비 23만 4천 원은 남편이 11월 3일에 냈어요."),
        ("wife", "핸드폰 요금 언제 나가?", "통신비 8만 9천 원은 매달 20일 자동이체예요."),
        # 3 지출 기록 (금액 표기 여러 가지)
        ("wife", "마트에서 84,000원 썼어", "마트 8만 4천 원을 기록했어요."),
        ("wife", "마트에서 8만4천원 썼어", "마트 8만 4천 원을 기록했어요."),
        ("wife", "마트에서 팔만 사천 원 썼어", "마트 8만 4천 원을 기록했어요."),
        ("wife", "마트에서 8만 사천 원 결제했어", "마트 8만 4천 원을 기록했어요."),
        ("wife", "생활비 얼마나 남았어요?", "52만 원 남았어요."),
        # 4 육아 분담
        ("wife", "내일 하원은 누가 해?", "11월 6일 금요일 하원은 아내가 가요."),
        ("husband", "목요일 하원 와이프가 가는 걸로 바꿔 줘", "목요일 하원은 아내가 가는 걸로 바꿨어요."),
        ("wife", "신랑이 금요일 하원 간다고 해", "금요일 하원은 남편이 가는 걸로 바꿨어요."),
        # 5 집안일
        ("wife", "재활용 분리배출 누구 차례야?", "이번 주 분리수거는 남편 차례예요."),
        ("wife", "빨래 했다고 체크해 줘.", "오늘 빨래는 아내가 한 걸로 체크했어요."),
        ("wife", "오늘 집안일 당번 누구야?", "이번 주 분리수거는 남편, 오늘 빨래는 아내, 오늘 청소기는 남편 차례예요."),
        # 6 부탁
        ("husband", "와이프한테 우유 사 달라고 부탁해줘", "아내에게 '우유 사' 부탁을 보냈어요."),
        ("wife", "신랑한테 쓰레기 버려 달라고 부탁해 줘", "남편에게 '쓰레기 버려' 부탁을 보냈어요."),
        ("wife", "나한테 온 부탁 있어?", "남편이 부탁한 '소윤이 우산 챙기기'예요."),
        # 7 양가
        ("wife", "어머님 생신 선물 뭐로 했지?", "시어머니 생신은 11월 20일이에요."),
        ("wife", "장모님 생신 언제야?", "친정엄마 생신은 2027년 3월 8일이에요."),
        ("husband", "처가 용돈 보냈어?", "이번 달 친정 용돈 30만 원은 아직 안 보냈어요."),
        # 8 만기
        ("wife", "차 보험 만기 언제야?", "자동차 보험은 12월 3일에 끝나요. 28일 남았어요."),
        ("wife", "여권 만료일 알려줘", "남편 여권은 2027년 5월 30일에 끝나요."),
        # 9 준비물·서류
        ("wife", "소윤이 내일 준비물 있어?", "소윤이 준비물은 색종이, 풀이에요."),
        ("wife", "체험학습 동의서 제출했어?", "현장학습 동의서는 아직 안 냈어요."),
        # 10 반려동물
        ("wife", "콩이 심장 사상충 약 언제 먹여?", "다음은 12월 1일이에요."),
        ("wife", "콩이 예방 주사 언제 맞아?", "콩이 종합백신은 2027년 1월 15일 예정이에요."),
        # 실기기 시험(2026-11-05 14:10)에서 폰 STT 가 실제로 받아 적은 그대로
        ("wife", "수연이 이번 주 학교 일정 뭐야?", THIS_WEEK),
        ("wife", "내일 어린이집 학원 누가 가?", "11월 6일 금요일 하원은 아내가 가요."),
        ("wife", "이번 달에 7년 용돈 보냈어", "이번 달 친정 용돈 30만 원은 아직 안 보냈어요."),
        ("wife", "공기 심장사상충 약 언제 먹어야 돼?", "다음은 12월 1일이에요."),
        ("wife", "퇴근할 때 약국 들려 달라고 부탁 해 줘", "남편에게 '퇴근할 때 약국 들려' 부탁을 보냈어요."),
        ("husband", "퇴근길에 우유 사 달라고 부탁해줘", "아내에게 '퇴근길에 우유 사' 부탁을 보냈어요."),
        ("husband", "나한테 부탁이 뭐야?", "남편에게 온 부탁이 없어요."),
        ("wife", "이번 달 관리비 됐어", "관리비 23만 4천 원은 남편이 11월 3일에 냈어요."),
    ],
)
def test_topic_variants(speaker, question, expected):
    assert expected in fresh_answer(question, speaker)


def test_ask_logs_correction(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        FamilyDemoAnswerProvider().answer("서윤이 이번 주 일정", now=NOW)
    assert "ask corrected '서윤이이번주일정' -> '소윤이이번주일정'" in caplog.text
