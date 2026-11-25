"""STT 학습 기록·녹음 묶음 요약을 새 앱(secretary-ai-test) 어드민이 읽는 out/stt/ 로 내보낸다(2026-11-24).

약속한 형식(새 앱 세션과 정함):
- out/stt/runs.jsonl          학습 한 번에 한 줄(같은 id 는 바꿔 씀)
- out/stt/data/<묶음 이름>.json 와치 '음성 모으기' 묶음 하나에 파일 하나
소리·받아 적은 글(transcript)·사람 이름은 넣지 않는다. 시험표 예시에서 이름이 든 문장은 뺀다.

학습 한 번의 재료는 .train/stt-ko/runs/<id>/ 에 둔다:
  run.json(언제·어디서·무엇을 배포했나), trainer_state.json·args.json(ms-swift), eval/*.json(finetune.evaluate 결과).

쓰기: cd server && .venv/bin/python -m finetune.export_admin all            (묶음 전부 + 기록 전부)
      cd server && .venv/bin/python -m finetune.export_admin run <runs/id>   (학습 하나)
      출력 폴더는 --out, 없으면 환경변수 STT_ADMIN_OUT, 없으면 ../../secretary-ai-test/out/stt
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from finetune.build_dataset import COLLECT_EXCLUDE_PATH, OUT_DIR, collect_decisions
from finetune.verify_collect import DEFAULT_THRESHOLD, MIN_LEAD_MS, SITUATION_THRESHOLD, VERIFY_FILE

KST = timezone(timedelta(hours=9))
COLLECT_DIR = OUT_DIR.parent / "collect"
RUNS_DIR = OUT_DIR.parent / "runs"
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "secretary-ai-test" / "out" / "stt"
# 시험표 대본에 든 가족 이름(아이·반려동물). 이 낱말이 든 예시는 어드민에 내보내지 않는다.
HIDE_WORDS = ("소윤", "소연", "수윤", "콩이")
CER_REASONS = ("정답과 다름", "받아 적지 못함")
LEAD_REASON = "앞 잘림 의심"


def out_dir(explicit: Path | None = None) -> Path:
    return explicit or Path(os.environ.get("STT_ADMIN_OUT", "") or DEFAULT_OUT)


def fetched_at(name: str) -> str | None:
    """'stt-collect-20261120-160855-keep' → '2026-11-20T16:08:55+09:00'(받은 시각, 맥 시계 KST)."""
    parts = name.split("-")
    try:
        stamp = datetime.strptime(parts[2] + parts[3], "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except (IndexError, ValueError):
        return None
    return stamp.isoformat()


def collect_summary(folder: Path, exclude_path: Path = COLLECT_EXCLUDE_PATH) -> dict:
    """묶음 하나의 요약. 판정은 build_collect 와 같은 collect_decisions 를 쓴다."""
    verify_path = folder / VERIFY_FILE
    verify = json.loads(verify_path.read_text(encoding="utf-8")) if verify_path.is_file() else None
    reasons_by_clip = {r["clip_id"]: r.get("reasons", []) for r in (verify or {}).get("results", []) if r.get("flagged")}
    clips, train_ms, versions = [], 0, set()
    for clip, reason, _audio in collect_decisions([folder], exclude_path):
        if clip.get("items_version"):
            versions.add(str(clip["items_version"]))
        clip_id = str(clip.get("clip_id", ""))
        flagged = clip_id in reasons_by_clip
        if not reason:
            train_ms += int(clip.get("duration_ms") or 0)
        clips.append({
            "clipId": clip_id, "itemId": clip.get("item_id"), "itemType": clip.get("item_type"),
            "speakerCode": clip.get("speaker_code"), "durationMs": clip.get("duration_ms"),
            "flagged": flagged, "reason": ", ".join(reasons_by_clip[clip_id]) if flagged else (reason or None),
            "_used": not reason,
        })
    flagged_reasons = list(reasons_by_clip.values())
    versions = sorted(versions)
    speakers = Counter(c["speakerCode"] for c in clips)
    summary = {
        "name": folder.name,
        "fetchedAt": fetched_at(folder.name),
        "mode": "keep" if folder.name.endswith("-keep") else "final",
        "itemsVersion": versions[0] if len(versions) == 1 else (versions or None),
        "clips": len(clips),
        "durationSec": round(sum(int(c["durationMs"] or 0) for c in clips) / 1000, 1),
        "speakers": {"count": len(speakers), "byCode": dict(sorted(speakers.items()))},
        "byType": dict(Counter(c["itemType"] for c in clips)),
        "verify": None if verify is None else {
            "model": Path(str(verify.get("model", ""))).name or None,
            "threshold": verify.get("threshold", DEFAULT_THRESHOLD),
            "situationThreshold": SITUATION_THRESHOLD,
            "minLeadMs": MIN_LEAD_MS,
            "flagged": len(reasons_by_clip),
            "reasons": {
                "cer": sum(any(r in CER_REASONS for r in rs) for rs in flagged_reasons),
                "leadCut": sum(LEAD_REASON in rs for rs in flagged_reasons),
            },
        },
        "excluded": sum(1 for c in clips if not c["_used"] and not c["flagged"]),
        "train": sum(1 for c in clips if c["_used"]),
        "trainSec": round(train_ms / 1000, 1),
        "clipsList": [{k: v for k, v in c.items() if k != "_used"} for c in clips],
    }
    return summary


def _rows(path: Path) -> dict[tuple[str, str], dict]:
    return {(r.get("run", ""), r["case"]): r for r in json.loads(path.read_text(encoding="utf-8"))["rows"]}


def _cer(path: Path) -> float | None:
    return json.loads(path.read_text(encoding="utf-8"))["summary"].get("cer")


def compare_eval(base: Path, final: Path) -> dict:
    """같은 녹음(run, case)마다 CER 이 나아짐·나빠짐·같음. 예시는 이름이 없는 시험표 문장만."""
    before, after = _rows(base), _rows(final)
    counts, examples = Counter(), []
    for key in sorted(after.keys() & before.keys()):
        delta = after[key]["cer"] - before[key]["cer"]
        kind = "better" if delta < -1e-9 else "worse" if delta > 1e-9 else "same"
        counts[kind] += 1
        texts = (before[key]["text"], after[key]["text"], after[key].get("reference", ""))
        if kind != "same" and not any(word in text for word in HIDE_WORDS for text in texts):
            examples.append({"case": key[1], "before": texts[0], "after": texts[1]})
    return {"better": counts["better"], "worse": counts["worse"], "same": counts["same"], "examples": examples}


def run_record(run_dir: Path, collect_dir: Path = COLLECT_DIR, exclude_path: Path = COLLECT_EXCLUDE_PATH) -> dict:
    """runs/<id>/ 의 재료 → runs.jsonl 한 줄."""
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    state = json.loads((run_dir / meta["trainerState"]).read_text(encoding="utf-8"))
    if meta.get("logging"):
        # ms-swift logging.jsonl 의 마지막 요약 줄에는 체크포인트 상태에 없는 학습 시간·최대 메모리가 있다
        lines = [json.loads(l) for l in (run_dir / meta["logging"]).read_text(encoding="utf-8").splitlines() if l.strip()]
        state = next((l for l in reversed(lines) if "log_history" in l), state)
    args = json.loads((run_dir / meta["args"]).read_text(encoding="utf-8"))
    history = state.get("log_history", [])
    summary_row = next((h for h in history if "train_runtime" in h), {})
    data = [collect_summary(collect_dir / name, exclude_path) for name in meta.get("dataVersions", [])]
    evaluation = meta["eval"]
    checkpoints = [
        {"name": c["name"], "epoch": c.get("epoch"), "cer": _cer(run_dir / c["file"])} for c in evaluation["checkpoints"]
    ]
    final = next(c for c in evaluation["checkpoints"] if c["name"] == evaluation["final"])
    return {
        "id": meta["id"], "startedAt": meta.get("startedAt"), "endedAt": meta.get("endedAt"),
        "where": meta.get("where"), "base": meta.get("base"), "output": meta.get("output"),
        "data": {
            "dataVersion": ", ".join(d["name"] for d in data) or None,
            "clips": sum(d["clips"] for d in data),
            "flagged": sum((d["verify"] or {}).get("flagged", 0) for d in data),
            "excluded": sum(d["excluded"] for d in data),
            "train": sum(d["train"] for d in data),
            "trainSec": round(sum(d["trainSec"] for d in data), 1),
            "speakers": len({code for d in data for code in d["speakers"]["byCode"]}),
        },
        "config": {
            "rank": args.get("lora_rank"), "alpha": args.get("lora_alpha"), "lr": args.get("learning_rate"),
            "epochs": args.get("num_train_epochs"), "steps": state.get("global_step"),
            "batch": args.get("per_device_train_batch_size"), "gradAccum": args.get("gradient_accumulation_steps"),
        },
        "durationSec": summary_row.get("train_runtime"),
        "peakMemGb": round(state["memory"], 2) if state.get("memory") is not None else None,
        "loss": [{"step": h["step"], "loss": round(h["loss"], 4)} for h in history if "loss" in h],
        "eval": {
            "set": evaluation.get("set"), "base": _cer(run_dir / evaluation["base"]),
            "checkpoints": checkpoints,
            **compare_eval(run_dir / evaluation["base"], run_dir / final["file"]),
        },
        "deployed": meta.get("deployed"),
        "notes": meta.get("notes"),
    }


def write_collect(summary: dict, out: Path) -> Path:
    path = out / "data" / f"{summary['name']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_run(record: dict, out: Path) -> Path:
    """runs.jsonl 에 넣는다. 같은 id 가 있으면 그 줄을 바꾸고, 시작 시각 순으로 둔다."""
    path = out / "runs.jsonl"
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.is_file() else []
    rows = [r for r in rows if r.get("id") != record["id"]] + [record]
    rows.sort(key=lambda r: r.get("startedAt") or "")
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="STT 학습 기록을 새 앱 어드민(out/stt)으로 내보내기")
    parser.add_argument("--out", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("all", help="묶음 전부와 학습 기록 전부")
    collect = sub.add_parser("collect", help="와치 녹음 묶음(푼 폴더)")
    collect.add_argument("folders", type=Path, nargs="+")
    run = sub.add_parser("run", help="학습 한 번(runs/<id>, run.json 있는 폴더)")
    run.add_argument("dirs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    out = out_dir(args.out)
    if args.command == "all":
        folders = sorted(p for p in COLLECT_DIR.iterdir() if (p / "manifest.jsonl").is_file()) if COLLECT_DIR.is_dir() else []
        runs = sorted(p for p in RUNS_DIR.iterdir() if (p / "run.json").is_file()) if RUNS_DIR.is_dir() else []
    else:
        folders = args.folders if args.command == "collect" else []
        runs = args.dirs if args.command == "run" else []
    for folder in folders:
        print("묶음 →", write_collect(collect_summary(folder), out))
    for run_dir in runs:
        print("학습 →", write_run(run_record(run_dir), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
