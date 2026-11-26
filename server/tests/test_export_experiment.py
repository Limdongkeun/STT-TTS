"""바깥 자료 STT 실험 → 어드민 runs.jsonl(evals·data.sources) 내보내기(2026-11-26). 실제 out 폴더는 건드리지 않는다."""

import json
from pathlib import Path

import pytest

from finetune.evaluate import run, utterance_id
from finetune.export_admin import compare_eval, rows_by_id, utterance_keys
from finetune.export_experiment import experiment_record, main, run_times

SVC = "svc"


def swift(audio, text, case, run_id="R1"):
    return {"messages": [{"role": "user", "content": "<audio>"}, {"role": "assistant", "content": f"language Korean<asr_text>{text}"}],
            "audios": [audio], "meta": {"case": case, "run": run_id, "verified": False}}


def result_rows(lines, cers):
    return [{"case": l["meta"]["case"], "run": l["meta"]["run"], "verified": False,
             "reference": l["messages"][-1]["content"].split("<asr_text>")[1], "text": "x", "cer": c, "sec": 0.1}
            for l, c in zip(lines, cers)]


def write_jsonl(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines), encoding="utf-8")


def write_result(path, rows, cer):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": "m", "summary": {"count": len(rows), "cer": cer}, "rows": rows}, ensure_ascii=False), encoding="utf-8")


def material(tmp_path):
    """방언처럼 (run, case)가 겹치는 평가 4줄(지역 0·1 두 개씩) + 학습 기록."""
    root = tmp_path / "material" / "m1"
    lines = [swift(f"/h/ev/{i}.wav", f"문장{i}", str(i // 2)) for i in range(4)]
    write_jsonl(root / "ev" / "eval.jsonl", lines)
    write_result(root / "res" / "cur.json", result_rows(lines, [0.2, 0.0, 0.5, None]), 0.2333)
    write_result(root / "res" / "new.json", result_rows(lines, [0.1, 0.0, 0.6, 0.4]), 0.275)
    write_jsonl(root / "train.jsonl", [swift(f"/h/tr/{i}.wav", "t", "0") for i in range(3)])
    run_dir = root / "run" / "v0-20261125-055828"
    (run_dir / "checkpoint-2").mkdir(parents=True)
    (run_dir / "checkpoint-2" / "trainer_state.json").write_text(json.dumps({"global_step": 2, "log_history": [{"loss": 1.0, "step": 1}]}), encoding="utf-8")
    final = {"global_step": 2, "memory": 5.949, "log_history": [{"loss": 1.23456, "step": 1}, {"loss": 0.5, "step": 2}, {"train_runtime": 257.595}]}
    (run_dir / "logging.jsonl").write_text(json.dumps({"loss": 1.0}) + "\n" + json.dumps(final) + "\n", encoding="utf-8")
    (run_dir / "args.json").write_text(json.dumps({"lora_rank": 16, "lora_alpha": 32, "learning_rate": 1e-4, "num_train_epochs": 1,
                                                    "per_device_train_batch_size": 1, "gradient_accumulation_steps": 8}), encoding="utf-8")
    return tmp_path / "material", lines


def spec(**over):
    base = {
        "id": "exp-1", "material": "m1", "run": "run/v0-20261125-055828", "checkpoint": "checkpoint-2", "trainList": "train.jsonl",
        "where": {"host": "vm", "zone": "z"}, "base": SVC, "output": "new", "deployed": None, "dataVersion": None, "notes": "n",
        "sources": [{"name": "aihub", "origin": "o", "location": "/h", "conversion": "c", "train": 2, "eval": 4, "speakerSplit": "s", "verified": 0},
                    {"name": "watch", "origin": "o", "location": "/h/tr", "conversion": "c", "train": 1, "eval": 0, "speakerSplit": "s", "verified": 0}],
        "evals": [{"id": "dialect", "label": "방언", "list": "ev/eval.jsonl", "groups": {"0": "강원", "1": "경상"},
                   "models": [{"name": SVC, "role": "service", "result": "res/cur.json"}, {"name": "new", "role": "new", "result": "res/new.json"}],
                   "compare": {"from": SVC, "to": "new"}, "notes": None}],
    }
    return {**base, **over}


def test_record_has_evals_groups_and_sources_without_text(tmp_path):
    root, _ = material(tmp_path)
    record = experiment_record(spec(), root)
    assert record["eval"] is None and record["data"]["train"] == 3 and record["data"]["sources"][0]["name"] == "aihub"
    assert (record["startedAt"], record["endedAt"]) == ("2026-11-25T14:58:28+09:00", "2026-11-25T15:02:46+09:00")
    assert record["config"]["steps"] == 2 and (record["durationSec"], record["peakMemGb"]) == (257.595, 5.95)
    assert record["loss"] == [{"step": 1, "loss": 1.2346}, {"step": 2, "loss": 0.5}]
    evaluation = record["evals"][0]
    assert (evaluation["count"], evaluation["verified"]) == (4, 0)
    assert evaluation["models"] == [{"name": SVC, "role": "service", "cer": 0.2333}, {"name": "new", "role": "new", "cer": 0.275}]
    assert evaluation["groups"] == [
        {"key": "0", "label": "강원", "count": 2, "cer": {SVC: 0.1, "new": 0.05}},
        {"key": "1", "label": "경상", "count": 2, "cer": {SVC: 0.5, "new": 0.5}},  # 받아 적지 못한 줄(None)은 평균에서 뺀다
    ]
    # (run, case)는 겹치지만 음성 이름으로 네 발화를 모두 센다. None → 0.4 는 나아짐
    assert evaluation["compare"] == {"from": SVC, "to": "new", "better": 2, "worse": 1, "same": 1}
    dumped = json.dumps(record, ensure_ascii=False)
    assert "문장" not in dumped and ".wav" not in dumped


def test_misaligned_or_missing_results_stop(tmp_path):
    root, lines = material(tmp_path)
    shuffled = result_rows(list(reversed(lines)), [0.1, 0.1, 0.1, 0.1])
    write_result(root / "m1" / "res" / "new.json", shuffled, 0.1)
    with pytest.raises(ValueError, match="순서"):
        experiment_record(spec(), root)
    write_result(root / "m1" / "res" / "new.json", result_rows(lines[:3], [0.1] * 3), 0.1)
    with pytest.raises(ValueError, match="수가 달라요"):
        experiment_record(spec(), root)


def test_bad_spec_stops(tmp_path):
    root, _ = material(tmp_path)
    with pytest.raises(ValueError, match="출처 train"):
        experiment_record(spec(sources=[]), root)
    evals = spec()["evals"]
    with pytest.raises(ValueError, match="묶음 이름표"):
        experiment_record(spec(evals=[{**evals[0], "groups": {"0": "강원"}}]), root)
    with pytest.raises(ValueError, match="역할"):
        experiment_record(spec(evals=[{**evals[0], "models": [{**evals[0]["models"][0], "role": "base"}]}]), root)


def test_rows_with_ids_are_matched_by_id_and_checked_for_gaps(tmp_path):
    root, lines = material(tmp_path)
    rows = result_rows(lines, [0.1] * 4)
    with_ids = [{**r, "id": utterance_id(l)} for r, l in zip(rows, lines)]
    write_result(root / "m1" / "res" / "new.json", list(reversed(with_ids)), 0.1)
    record = experiment_record(spec(evals=[{**spec()["evals"][0], "groups": None}]), root)
    assert record["evals"][0]["groups"] is None and record["evals"][0]["compare"] == {"from": SVC, "to": "new", "better": 3, "worse": 1, "same": 0}
    gap = [{**with_ids[0], "id": "other.wav"}] + with_ids[1:]
    write_result(root / "m1" / "res" / "new.json", gap, 0.1)
    with pytest.raises(ValueError, match="겹침·빠짐"):
        experiment_record(spec(), root)


def test_compare_is_null_when_ids_repeat(tmp_path):
    rows = [{"case": "0", "run": "R1", "reference": "a", "text": "a", "cer": 0.1}, {"case": "0", "run": "R1", "reference": "b", "text": "b", "cer": 0.2}]
    assert utterance_keys(rows) == ["R1/0", "R1/0"] and rows_by_id(rows) is None
    base, final = tmp_path / "b.json", tmp_path / "f.json"
    write_result(base, rows, 0.15)
    write_result(final, rows, 0.15)
    assert compare_eval(base, final) == {"better": None, "worse": None, "same": None, "examples": []}
    write_result(final, rows[:1], 0.1)
    base_one = tmp_path / "b1.json"
    write_result(base_one, [{**rows[0], "case": "1"}], 0.1)
    assert compare_eval(base_one, final)["better"] is None  # 두 쪽 발화가 다르면 세지 않는다


def test_evaluate_rows_carry_audio_name(tmp_path):
    lines = [swift("/h/a/0_000.wav", "가", "0"), {**swift("/h/a/0_001.wav", "나", "0"), "meta": {"case": "0", "id": "fixed"}}]
    path = tmp_path / "eval.jsonl"
    write_jsonl(path, lines)
    rows = run(lambda audio: "가", path)
    assert [r["id"] for r in rows] == ["0_000.wav", "fixed"]


def test_run_times_without_runtime_and_cli(tmp_path):
    assert run_times(Path("v0-20261125-052419"), None) == ("2026-11-25T14:24:19+09:00", None)
    root, _ = material(tmp_path)
    spec_path = tmp_path / "exp.json"
    spec_path.write_text(json.dumps(spec(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["--out", str(out), "--material", str(root), str(spec_path), str(spec_path)]) == 0
    lines = (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["id"] == "exp-1"  # 두 번 써도 한 줄


def test_shipped_specs_are_valid_json_with_known_roles():
    for path in sorted((Path(__file__).resolve().parents[1] / "finetune" / "experiments").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == path.stem and data["deployed"] is None
        for evaluation in data["evals"]:
            names = [m["name"] for m in evaluation["models"]]
            assert evaluation["compare"]["from"] in names and evaluation["compare"]["to"] in names
            assert all(m["role"] in ("service", "start", "new", "other") for m in evaluation["models"])
