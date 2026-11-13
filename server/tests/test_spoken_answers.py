import json

import pytest
from fastapi.testclient import TestClient

from app.family_demo import DEMO_NOW, FamilyDemoAnswerProvider
from app.main import create_app
from app.spoken_answers import load_spoken_answers, spoken_for
from app.test_sheet import TEST_CASES
from tests.test_api import make_settings

BASE = "http://107.test:5110"


def test_every_test_answer_has_spoken_version_in_order():
    """시험표 순서대로 물으면 나오는 화면 답 34개 모두 입말 문장이 있다(답이 바뀌면 이 테스트가 알려 준다)."""
    spoken = load_spoken_answers()
    provider = FamilyDemoAnswerProvider()
    context = None
    for case in TEST_CASES:
        answer, context = provider.answer(case["say"], context, now=DEMO_NOW)
        assert spoken_for(answer, spoken), (case["id"], answer)
    assert len(spoken) == len(TEST_CASES)


def test_spoken_lookup_ignores_spacing_and_unknown_answer_is_none():
    spoken = load_spoken_answers()
    assert spoken_for("이번 주 분리수거는 남편 차례예요.아직 안 했어요", spoken) == "이번 주 분리수거는 남편 차례인데요, 아직 안 했어요."
    assert spoken_for("처음 보는 답이에요.", spoken) is None


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([{"id": "X", "answer": "답", "spoken": ""}], "모두"),
        ([{"id": "X", "answer": "답", "spoken": "가" * 201}], "200자"),
        ([{"id": "X", "answer": "답.", "spoken": "가"}, {"id": "Y", "answer": "답", "spoken": "나"}], "두 번"),
    ],
)
def test_bad_spoken_file_is_rejected(tmp_path, items, message):
    path = tmp_path / "spoken.json"
    path.write_text(json.dumps({"answers": items}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_spoken_answers(path)


def _ask(client, tts_engine):
    body = {"text": "이번 주 분리수거 누구 차례야?"}
    if tts_engine:
        body["ttsEngine"] = tts_engine
    return client.post("/ask", json=body).json()


def test_ask_reads_spoken_for_generated_tts_and_jisoo_recordings():
    """2026-11-12부터 지수 녹음도 입말로 녹음했다. mock 은 원래 문장."""
    client = TestClient(create_app(make_settings(tts_engine="prerecorded", answer_provider="family-demo", tts107_url=BASE)))
    generated = _ask(client, "qwen3-tts-107")
    recorded = _ask(client, None)
    beep = _ask(client, "mock")
    assert generated["answerText"] == recorded["answerText"] == "이번 주 분리수거는 남편 차례예요. 아직 안 했어요."
    assert generated["speechText"] == recorded["speechText"] == "이번 주 분리수거는 남편 차례인데요, 아직 안 했어요."
    assert beep["speechText"] == "이번 주 분리수거는 남편 차례예요. 아직 안 했어요."


def test_spoken_answers_off_keeps_original_and_label():
    settings = make_settings(tts_engine="prerecorded", answer_provider="family-demo", tts107_url=BASE, spoken_answers="off")
    client = TestClient(create_app(settings))
    assert _ask(client, "qwen3-tts-107")["speechText"] == "이번 주 분리수거는 남편 차례예요. 아직 안 했어요."
    labels = {choice["engine"]: choice["label"] for choice in client.get("/health").json()["ttsChoices"]}
    assert labels["qwen3-tts-107"] == "107 Qwen3-TTS · G 목소리"


from app.spoken_answers import UNKNOWN_SPOKEN, to_spoken_style  # noqa: E402

# 11/05~11/09 저장본에 실제로 나왔는데 시험 답 목록(34개)에는 없는 답들
REAL_UNMATCHED = [
    "시험 기록에 11월 5일 오후 1시 33분에 먹인 걸로 기록했어요. 가상 일정에 등록된 다음 복용 예정 시각은 오후 9시예요.",
    "남편에게 온 부탁이 없어요.",
    "남편이 보낸 부탁 중 남은 건 1건이에요. 아내에게 보낸 '소윤이 우산 챙기기'예요.",
    "'소윤이 우산 챙기기' 부탁을 끝낸 걸로 표시했어요.",
    "가스비 4만 2천 원은 아내가 11월 6일에 낸 걸로 기록했어요.",
    "마트 8만 2천 원을 기록했어요. 이번 달 생활비는 43만 8천 원 남았어요.",
    "이번 달 친정 용돈 30만 원은 아내가 보냈어요. 이번 달 시댁 용돈 30만 원은 아직 안 보냈어요. 매달 10일에 보내기로 했어요.",
    "11월 7일 토요일 준비물은 시험 데이터에 없어요. 준비된 날은 11월 6일 금요일이에요.",
    "누가 하원할지 같이 말해 주세요.",
]


def test_rules_turn_written_style_into_spoken():
    assert to_spoken_style(REAL_UNMATCHED[0]) == "11월 5일 오후 1시 33분에 먹인 걸로 적어 뒀어요. 다음 약은 오후 9시예요."
    assert to_spoken_style(REAL_UNMATCHED[1]) == "남편한테 온 부탁이 없어요."
    assert to_spoken_style(REAL_UNMATCHED[2]) == "남편이 보낸 부탁 중 남은 건 하나예요. 아내한테 보낸 소윤이 우산 챙기기예요."
    assert to_spoken_style(REAL_UNMATCHED[3]) == "소윤이 우산 챙기기 부탁을 끝낸 걸로 해 뒀어요."
    assert to_spoken_style("이 질문에 맞는 시험 답변이 준비돼 있지 않아요.") == UNKNOWN_SPOKEN


def test_rules_never_change_numbers_or_names():
    """규칙은 표현만 바꾼다: 숫자와 사람·물건 이름은 그대로 남아야 한다."""
    import re as _re

    for answer in REAL_UNMATCHED + [case["expect"] for case in TEST_CASES]:
        spoken = to_spoken_style(answer)
        # '1건이에요' → '하나예요'만은 숫자를 말로 바꾼 것이라 되돌려 비교한다
        assert _re.findall(r"\d+", spoken.replace("하나예요", "1건이에요")) == _re.findall(r"\d+", answer), answer
        for name in ("남편", "아내", "소윤", "콩이", "친정", "시댁", "가스비", "관리비", "넷플릭스"):
            assert (name in spoken) == (name in answer), (name, answer)


def test_rules_leave_plain_spoken_text_alone():
    for text in ("이번 주 분리수거는 남편 차례인데요, 아직 안 했어요.", "11건이에요.", "누가 하원할지 같이 말해 주세요."):
        assert to_spoken_style(text) == text


def test_ask_uses_rules_for_answers_outside_the_list():
    client = TestClient(create_app(make_settings(tts_engine="prerecorded", answer_provider="family-demo", tts107_url=BASE)))
    unknown = client.post("/ask", json={"text": "오늘 날씨 어때?", "ttsEngine": "qwen3-tts-107"}).json()
    assert unknown["answerText"] == "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."
    assert unknown["speechText"] == UNKNOWN_SPOKEN
    recorded = client.post("/ask", json={"text": "오늘 날씨 어때?"}).json()
    assert recorded["speechText"] == UNKNOWN_SPOKEN  # 지수 녹음도 이 문장으로 녹음했다
    beep = client.post("/ask", json={"text": "오늘 날씨 어때?", "ttsEngine": "mock"}).json()
    assert beep["speechText"] == "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."


# ── 답 듣기 칸 (/answer-samples, 2026-11-12) ──
from app.spoken_answers import load_answer_samples  # noqa: E402


def test_answer_samples_keep_file_order_and_fields():
    samples = load_answer_samples()
    assert len(samples) == 34
    assert [sample["id"] for sample in samples[:2]] == ["C1", "C2"] and samples[-1]["id"] == "E2"
    assert all(sample.keys() == {"id", "answer", "spoken"} for sample in samples)
    # 입말 문장에는 아라비아 숫자가 없다(그대로 읽혀도 숫자를 틀리지 않게)
    assert not any(char.isdigit() for sample in samples for char in sample["spoken"])


def test_answer_samples_reject_bad_file(tmp_path):
    path = tmp_path / "spoken.json"
    path.write_text(json.dumps({"answers": [{"id": "C1", "answer": "답", "spoken": " "}]}, ensure_ascii=False))
    with pytest.raises(ValueError):
        load_answer_samples(path)


def test_api_lists_answer_samples():
    client = TestClient(create_app(make_settings(tts_engine="mock")))
    samples = client.get("/answer-samples").json()["samples"]
    assert samples[0]["id"] == "C1" and samples[0]["spoken"].startswith("다음 주")
