"""STT 학습 기록을 새 앱 어드민 형식(out/stt)으로 내보내기(2026-11-24). 실제 out 폴더는 건드리지 않는다."""

import json

import pytest

from finetune.export_admin import collect_summary, compare_eval, fetched_at, main, out_dir, run_record, write_collect, write_run
from finetune.verify_collect import VERIFY_FILE
from tests.test_fetch_collect import clip, make_folder


def pack(tmp_path, name="stt-collect-20261120-160855-keep"):
    clips = [
        {**clip("c1", "S100", "관리비 고지서 왔어"), "items_version": "2026-11-18"},
        {**clip("c2", "S101", "콩이 사료 거의 다 먹었어", speaker="SPK02"), "items_version": "2026-11-18", "duration_ms": 2000},
        {**clip("c3", "P048", "비서에게 물어보세요", day="2026-11-19", item_type="situation"), "items_version": "2026-11-18"},
        {**clip("c4", "S102", "우유 사 와"), "items_version": "2026-11-18"},
    ]
    folder = make_folder(tmp_path, clips)
    folder = folder.rename(tmp_path / name)
    results = [
        {"clip_id": "c2", "flagged": True, "reasons": ["정답과 다름", "앞 잘림 의심"]},
        {"clip_id": "c4", "flagged": True, "reasons": ["앞 잘림 의심"]},
        {"clip_id": "c1", "flagged": False, "reasons": []},
    ]
    (folder / VERIFY_FILE).write_text(json.dumps({"model": "/x/.models/qwen3_asr_1.7b_ko", "threshold": 0.15, "results": results}), encoding="utf-8")
    exclude = tmp_path / "ex.txt"
    exclude.write_text("P048 SPK01 2026-11-19  # 안내 문장\n", encoding="utf-8")
    return folder, exclude


def test_collect_summary_counts_without_transcripts(tmp_path):
    folder, exclude = pack(tmp_path)
    summary = collect_summary(folder, exclude)
    assert (summary["clips"], summary["train"], summary["excluded"], summary["trainSec"]) == (4, 1, 1, 1.0)
    assert summary["fetchedAt"] == "2026-11-20T16:08:55+09:00" and summary["mode"] == "keep"
    assert summary["itemsVersion"] == "2026-11-18" and summary["durationSec"] == 5.0
    assert summary["speakers"] == {"count": 2, "byCode": {"SPK01": 3, "SPK02": 1}}
    assert summary["byType"] == {"read": 3, "situation": 1}
    assert summary["verify"] == {"model": "qwen3_asr_1.7b_ko", "threshold": 0.15, "situationThreshold": 0.0, "minLeadMs": 40,
                                 "flagged": 2, "reasons": {"cer": 1, "leadCut": 2}}
    reasons = {c["clipId"]: (c["flagged"], c["reason"]) for c in summary["clipsList"]}
    assert reasons == {"c1": (False, None), "c2": (True, "정답과 다름, 앞 잘림 의심"), "c3": (False, "제외 목록"), "c4": (True, "앞 잘림 의심")}
    dumped = json.dumps(summary, ensure_ascii=False)
    assert "관리비" not in dumped and "transcript" not in dumped and "audio" not in dumped


def test_collect_summary_before_verify_and_odd_names(tmp_path):
    folder, exclude = pack(tmp_path, name="stt-collect-final")
    (folder / VERIFY_FILE).unlink()
    summary = collect_summary(folder, exclude)
    assert summary["verify"] is None and summary["mode"] == "final" and summary["fetchedAt"] is None
    assert summary["train"] == 3  # 검사 전이면 제외 목록만 뺀다
    assert fetched_at("stt-collect-2026xx20-160855-keep") is None


def write_eval(path, rows, cer):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": "m", "summary": {"count": len(rows), "cer": cer}, "rows": rows}, ensure_ascii=False), encoding="utf-8")


def row(case, text, cer, reference="ref", run="r1"):
    return {"case": case, "run": run, "reference": reference, "text": text, "cer": cer}


def test_compare_eval_counts_and_hides_family_names(tmp_path):
    base, final = tmp_path / "b.json", tmp_path / "f.json"
    write_eval(base, [row("D7", "사업비", 0.2), row("C2", "소윤이 보여", 0.3, "소윤이 뭐야"), row("D8", "팔만", 0.1), row("C1", "같음", 0.0)], 0.15)
    write_eval(final, [row("D7", "생활비", 0.0), row("C2", "소윤이 뭐야", 0.1, "소윤이 뭐야"), row("D8", "84000", 0.3), row("C1", "같음", 0.0)], 0.1)
    result = compare_eval(base, final)
    assert (result["better"], result["worse"], result["same"]) == (2, 1, 1)
    assert result["examples"] == [{"case": "D7", "before": "사업비", "after": "생활비"}, {"case": "D8", "before": "팔만", "after": "84000"}]


def make_run(tmp_path, collect_dir):
    run_dir = tmp_path / "runs" / "r1"
    (run_dir / "eval").mkdir(parents=True)
    write_eval(run_dir / "eval" / "base.json", [row("D7", "사업비", 0.2)], 0.1468)
    write_eval(run_dir / "eval" / "e1.json", [row("D7", "사업비", 0.2)], 0.1477)
    write_eval(run_dir / "eval" / "e2.json", [row("D7", "생활비", 0.0)], 0.1396)
    state = {"global_step": 14, "memory": 4.7109375, "log_history": [
        {"loss": 2.14119, "step": 1}, {"loss": 0.0995241, "step": 14}, {"train_runtime": 53.5882, "step": 14}]}
    (run_dir / "trainer_state.json").write_text(json.dumps(state), encoding="utf-8")
    args = {"lora_rank": 16, "lora_alpha": 32.0, "learning_rate": 0.0001, "num_train_epochs": 2.0,
            "per_device_train_batch_size": 1, "gradient_accumulation_steps": 8}
    (run_dir / "args.json").write_text(json.dumps(args), encoding="utf-8")
    meta = {"id": "r1", "startedAt": "2026-11-20T16:17:00+09:00", "endedAt": "2026-11-20T16:22:00+09:00",
            "where": {"host": "vm", "zone": "z"}, "base": "TeamUNIVA/qwen3_asr_1.7b_ko", "output": "ft",
            "dataVersions": ["stt-collect-20261120-160855-keep"], "trainerState": "trainer_state.json", "args": "args.json",
            "eval": {"set": "device-test-76", "base": "eval/base.json", "final": "checkpoint-14", "checkpoints": [
                {"name": "checkpoint-7", "epoch": 1, "file": "eval/e1.json"}, {"name": "checkpoint-14", "epoch": 2, "file": "eval/e2.json"}]},
            "deployed": {"at": "2026-11-20T16:25:00+09:00", "server": "vm", "model": "ft"}, "notes": "n"}
    (run_dir / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    return run_dir


def test_run_record_follows_the_agreed_shape(tmp_path):
    folder, exclude = pack(tmp_path)
    record = run_record(make_run(tmp_path, tmp_path), tmp_path, exclude)
    assert record["data"] == {"dataVersion": folder.name, "clips": 4, "flagged": 2, "excluded": 1, "train": 1, "trainSec": 1.0, "speakers": 2}
    assert record["config"] == {"rank": 16, "alpha": 32.0, "lr": 0.0001, "epochs": 2.0, "steps": 14, "batch": 1, "gradAccum": 8}
    assert (record["durationSec"], record["peakMemGb"]) == (53.5882, 4.71)
    assert record["loss"] == [{"step": 1, "loss": 2.1412}, {"step": 14, "loss": 0.0995}]
    assert record["eval"]["base"] == 0.1468
    assert record["eval"]["checkpoints"] == [{"name": "checkpoint-7", "epoch": 1, "cer": 0.1477}, {"name": "checkpoint-14", "epoch": 2, "cer": 0.1396}]
    assert (record["eval"]["better"], record["eval"]["worse"], record["eval"]["same"]) == (1, 0, 0)
    assert record["deployed"]["model"] == "ft" and record["where"] == {"host": "vm", "zone": "z"}


def test_run_record_reads_runtime_from_swift_logging(tmp_path):
    folder, exclude = pack(tmp_path)
    run_dir = make_run(tmp_path, tmp_path)
    (run_dir / "trainer_state.json").write_text(json.dumps({"global_step": 14, "log_history": [{"loss": 1.0, "step": 14}]}), encoding="utf-8")
    final = {"global_step": 14, "memory": 4.7109375, "log_history": [{"loss": 1.0, "step": 14}, {"train_runtime": 53.5882}]}
    (run_dir / "logging.jsonl").write_text(json.dumps({"loss": 1.0}) + "\n" + json.dumps(final) + "\n", encoding="utf-8")
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    (run_dir / "run.json").write_text(json.dumps({**meta, "logging": "logging.jsonl"}), encoding="utf-8")
    record = run_record(run_dir, tmp_path, exclude)
    assert (record["durationSec"], record["peakMemGb"]) == (53.5882, 4.71)


def test_write_run_replaces_same_id_and_keeps_order(tmp_path):
    out = tmp_path / "out"
    write_run({"id": "b", "startedAt": "2026-11-21"}, out)
    write_run({"id": "a", "startedAt": "2026-11-20", "v": 1}, out)
    write_run({"id": "a", "startedAt": "2026-11-20", "v": 2}, out)
    lines = [json.loads(l) for l in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["id"], r.get("v")) for r in lines] == [("a", 2), ("b", None)]
    path = write_collect({"name": "p"}, out)
    assert path == out / "data" / "p.json"


def test_out_dir_prefers_flag_then_env(tmp_path, monkeypatch):
    monkeypatch.delenv("STT_ADMIN_OUT", raising=False)
    assert out_dir().parts[-3:] == ("secretary-ai-test", "out", "stt")
    monkeypatch.setenv("STT_ADMIN_OUT", str(tmp_path / "env"))
    assert out_dir() == tmp_path / "env" and out_dir(tmp_path / "flag") == tmp_path / "flag"


def test_cli_writes_collect_and_run(tmp_path, monkeypatch):
    folder, exclude = pack(tmp_path)
    monkeypatch.setattr("finetune.export_admin.COLLECT_EXCLUDE_PATH", exclude)
    monkeypatch.setattr("finetune.export_admin.collect_summary", lambda f, e=exclude: collect_summary(f, e))
    monkeypatch.setattr("finetune.export_admin.COLLECT_DIR", tmp_path)
    monkeypatch.setattr("finetune.export_admin.RUNS_DIR", tmp_path / "runs")
    make_run(tmp_path, tmp_path)
    monkeypatch.setattr("finetune.export_admin.run_record", lambda d: run_record(d, tmp_path, exclude))
    out = tmp_path / "out"
    assert main(["--out", str(out), "all"]) == 0
    assert (out / "data" / f"{folder.name}.json").is_file()
    assert json.loads((out / "runs.jsonl").read_text(encoding="utf-8"))["id"] == "r1"
    with pytest.raises(SystemExit):
        main(["--out", str(out)])
