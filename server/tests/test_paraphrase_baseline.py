import json
from datetime import datetime

import pytest

from app.paraphrase_baseline import (
    CaseResult, VariantResult, answer_after_history, load_paraphrases, render_markdown, run_baseline,
)
from app.test_sheet import TEST_CASES


def test_paraphrase_file_covers_every_case_with_new_sentences():
    paraphrases = load_paraphrases()
    # 말바꿈 기준선은 2026-11-06의 C·D 32문장으로 고정했다(E 문장은 11/09 추가, 기준선에 넣지 않음).
    baseline_cases = [case for case in TEST_CASES if case["id"][0] in "CD"]
    assert set(paraphrases) == {case["id"] for case in baseline_cases}
    for case in baseline_cases:
        sentences = paraphrases[case["id"]]
        assert len(sentences) >= 4
        assert case["say"] not in sentences  # 원래 문장 그대로는 말바꿈이 아니다
        assert len(set(sentences)) == len(sentences)


def test_original_sentence_always_matches_itself():
    # 같은 문장을 다시 물으면 같은 답이어야 한다: 매번 새 기록에서 앞 케이스를 다시 말하므로 결과가 흔들리지 않는다.
    paraphrases = {case["id"]: [case["say"]] for case in TEST_CASES}
    results = run_baseline(paraphrases)
    assert [result.case_id for result in results] == [case["id"] for case in TEST_CASES]
    assert all(result.passed_count == 1 for result in results)


def test_history_is_replayed_before_the_question():
    # D3 은 D2 에서 우유·기저귀를 넣은 뒤라야 '남은 건 두부, 계란, 우유'가 된다.
    index = next(i for i, case in enumerate(TEST_CASES) if case["id"] == "D3")
    assert "두부, 계란, 우유" in answer_after_history(index, "기저귀는 아내가 샀어")
    # C4 는 C3 의 '몇 시에 먹였나요?' 다음이라야 복용 시각으로 받는다.
    c4 = next(i for i, case in enumerate(TEST_CASES) if case["id"] == "C4")
    assert "오후 2시 30분" in answer_after_history(c4, "30분 전에 먹였어")


def test_unrelated_sentence_is_not_understood():
    results = run_baseline({"D1": ["오늘 날씨 어때?"]})
    assert results[0].passed_count == 0


def test_load_rejects_unknown_case_and_empty_sentence(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"Z9": ["뭐야"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="모르는 케이스"):
        load_paraphrases(path)
    path.write_text(json.dumps({"D1": ["  "]}), encoding="utf-8")
    with pytest.raises(ValueError, match="빈 문장"):
        load_paraphrases(path)
    path.write_text(json.dumps({"_설명": "건너뜀", "D1": ["장볼거리 뭐야?"]}), encoding="utf-8")
    assert load_paraphrases(path) == {"D1": ["장볼거리 뭐야?"]}


def test_markdown_shows_total_and_failures():
    results = [
        CaseResult("D1", "장보기 목록 뭐 남았어?", "목록 답", [
            VariantResult("장볼거리 뭐야?", "목록 답", True),
            VariantResult("마트 | 뭐 사?", "모름", False),
        ]),
    ]
    text = render_markdown(results, datetime(2026, 11, 6, 11, 30))
    assert "알아들음 1/2 (50%)" in text
    assert "| D1 | 1/2 |" in text
    assert "마트 \\| 뭐 사?" in text  # 표가 깨지지 않게
    assert "못 알아들은 문장 (1개)" in text
