"""STT 추가 학습 데이터 만들기(finetune/build_dataset.py). 모델은 올리지 않는다."""

import json

import pytest

from app.test_sheet import TEST_CASES
from finetune.build_dataset import (
    build_eval, build_train, collect_eval_rows, load_items, load_sentences, near_test_sentence, swift_row,
)


def test_swift_row_uses_model_output_shape():
    row = swift_row("/a/1.wav", "  우유  사 와 ")
    assert row["audios"] == ["/a/1.wav"]
    assert row["messages"][0] == {"role": "user", "content": "<audio>"}
    assert row["messages"][1]["content"] == "language Korean<asr_text>우유 사 와"


def test_swift_row_rejects_empty_text():
    with pytest.raises(ValueError):
        swift_row("/a/1.wav", "   ")


def test_shipped_sentences_avoid_test_sheet_and_read_in_hangul():
    """2026-11-17: 가족 비서 200개 + 일상 말 → 약 700문장·1만 자(사용자 요청). 읽는 글엔 숫자·영문이 남지 않는다."""
    import re

    items = load_items()
    sentences = [(item["category"], item["text"]) for item in items]
    assert len(sentences) >= 650 and sum(len(text) for _, text in sentences) >= 9000
    assert len({text for _, text in sentences}) == len(sentences)
    assert [item["speech"] for item in items if re.search(r"[0-9A-Za-z+]", item["speech"])] == []
    tests = [case["say"] for case in TEST_CASES]
    assert [text for _, text in sentences if near_test_sentence(text, tests)] == []


@pytest.mark.parametrize(
    ("sentence", "hit"),
    [("이번 달 관리비 냈어?", True), ("이번달 관리비 냈어", True), ("친정 용돈 아직 안 보냈어", True),
     ("콩이 사료 다 떨어져 가", False), ("응", False)],
)
def test_near_test_sentence(sentence, hit):
    tests = [case["say"] for case in TEST_CASES]
    assert (near_test_sentence(sentence, tests) is not None) is hit


def test_load_sentences_needs_category(tmp_path):
    path = tmp_path / "s.txt"
    path.write_text("# 이것은 아주 긴 설명 줄이라 분류가 아니다\n우유 사 와\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_sentences(path)
    path.write_text("# 장보기\n우유 2개 사 와\nTV 꺼줘 | 티비 꺼줘\n\n# 짧은 말\n응\n", encoding="utf-8")
    assert load_sentences(path) == [("장보기", "우유 2개 사 와"), ("장보기", "TV 꺼줘"), ("짧은 말", "응")]
    assert [item["speech"] for item in load_items(path)] == ["우유 두 개 사 와", "티비 꺼줘", "응"]


def _run(results, name, audio, cases):
    run_dir = results / "ios"
    (run_dir / f"{name}-audio").mkdir(parents=True)
    for case_id, data in audio.items():
        (run_dir / f"{name}-audio" / f"{case_id}.wav").write_bytes(data)
    body = {"audio": {c: f"{name}-audio/{c}.wav" for c in audio}, "results": cases}
    (run_dir / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def test_eval_rows_dedupe_and_prefer_spoken(tmp_path):
    results = tmp_path / "test-runs"
    _run(results, "a", {"C1": b"one", "D4": b"two"}, {"C1": {"spoken": "다음 주 일정 뭐야", "recognized": "다음 주 일정 뭐야"}})
    _run(results, "b", {"C1": b"one", "X9": b"three"}, {})  # 같은 소리·모르는 칸은 건너뛴다
    rows = collect_eval_rows(results)
    assert [(r["case"], r["verified"]) for r in rows] == [("C1", True), ("D4", False)]
    assert rows[0]["text"] == "다음 주 일정 뭐야"
    assert rows[1]["text"] == next(c["say"] for c in TEST_CASES if c["id"] == "D4")


def test_eval_skips_audio_outside_results(tmp_path):
    results = tmp_path / "test-runs"
    (results / "ios").mkdir(parents=True)
    (tmp_path / "secret.wav").write_bytes(b"x")
    body = {"audio": {"C1": "../../secret.wav"}, "results": {}}
    (results / "ios" / "r.json").write_text(json.dumps(body), encoding="utf-8")
    assert collect_eval_rows(results) == []


def test_build_eval_and_train_write_files(tmp_path):
    results = tmp_path / "test-runs"
    _run(results, "a", {"C1": b"one"}, {})
    out = tmp_path / "out"
    build_eval(out, results)
    line = json.loads((out / "eval.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["meta"]["case"] == "C1" and line["meta"]["verified"] is False
    assert (out / "eval_check.csv").read_text(encoding="utf-8-sig").startswith("run,case,audio")

    sentences = tmp_path / "s.txt"
    sentences.write_text("# 장보기\n우유 사 와\n두부 사 와\n", encoding="utf-8")
    audio = tmp_path / "wav"
    audio.mkdir()
    for name in ("1_f.wav", "2.wav", "3.wav", "x.wav"):
        (audio / name).write_bytes(b"x")
    rows = build_train(audio, out, sentences)
    assert [r["messages"][1]["content"] for r in rows] == ["language Korean<asr_text>우유 사 와", "language Korean<asr_text>두부 사 와"]
    with pytest.raises(ValueError):
        build_train(tmp_path / "out", out, sentences)


def test_evaluate_summary_and_answer_text():
    from finetune.evaluate import answer_text, summarize

    assert answer_text(swift_row("/a.wav", "우유 사 와")) == "우유 사 와"
    rows = [
        {"cer": 0.1, "sec": 0.5, "verified": True},
        {"cer": 0.3, "sec": 0.9, "verified": False},
        {"cer": None, "sec": 0.7, "verified": False},
    ]
    assert summarize(rows) == {
        "count": 3, "cer": 0.2, "verified_count": 1, "verified_cer": 0.1, "empty": 1, "median_sec": 0.7,
    }
    assert summarize([])["median_sec"] is None


def test_train_pairs_numbered_clip_with_sentence(tmp_path):
    # <번호>_<이름>.wav(녹음한 사람 이름 등)를 그 번호 문장과 짝짓는다
    path = tmp_path / "0012_g.wav"
    sentences = tmp_path / "s.txt"
    sentences.write_text("# 장보기\n" + "".join(f"문장 {i}\n" for i in range(1, 13)), encoding="utf-8")
    path.write_bytes(b"x")
    rows = build_train(tmp_path, tmp_path / "out", sentences)
    assert rows[0]["messages"][1]["content"].endswith("문장 12")


def test_situation_prompts_are_unique_and_do_not_quote_the_test_sheet():
    from app.family_demo import compact_question
    from app.test_sheet import TEST_CASES
    from finetune.build_dataset import load_prompts

    prompts = load_prompts()
    assert len(prompts) >= 90
    assert [p["id"] for p in prompts[:2]] == ["P001", "P002"]
    assert len({p["prompt"] for p in prompts}) == len(prompts)
    tests = [compact_question(case["say"]) for case in TEST_CASES]
    # 상황만 주고 시험표 문장을 그대로 읽게 하지 않는다
    assert not [p["prompt"] for p in prompts if any(t and t in compact_question(p["prompt"]) for t in tests)]
    assert {"짧은 대답", "고쳐 말하기", "숫자 말하기"} <= {p["category"] for p in prompts}


def test_recording_items_number_sentences_like_audio_files(tmp_path):
    from finetune.build_dataset import load_sentences, recording_items

    items = recording_items()
    reads = [item for item in items if item["type"] in ("read", "short")]
    sentences = load_sentences()
    assert len(reads) == len(sentences)
    # S 번호 = 학습 문장 순서 = 녹음 파일 <번호>_<사람>.wav 의 번호
    assert reads[11]["id"] == "S012" and reads[11]["text"] == sentences[11][1]
    assert {item["type"] for item in items} == {"read", "short", "situation"}
    assert len({item["id"] for item in items}) == len(items)
    assert all(item.get("text") or item.get("prompt") for item in items)

