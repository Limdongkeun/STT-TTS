"""바깥 자료(AI-Hub 샘플 등)로 한 STT 실험을 새 앱 어드민(out/stt/runs.jsonl)에 한 줄로 내보낸다(2026-11-26).

export_admin 의 학습 기록(runs/<id>/run.json)과 달리, 실험은 클라우드 폴더 구조를 그대로 받아 와서 쓴다.
무엇을 어디서 읽을지는 실험 설명 파일(finetune/experiments/<id>.json)에 적는다:
  material   받아 온 자료 폴더 이름(.train/stt-ko/experiments/<material>/, 클라우드 홈 아래 경로 그대로)
  run        ms-swift 출력 폴더(v0-YYYYMMDD-HHMMSS, 클라우드 시계 UTC), checkpoint 는 그 안의 마지막 체크포인트
  trainList  학습 목록(줄 수가 출처 train 합과 같아야 한다)
  evals[]    평가셋마다 목록(eval.jsonl)과 모델별 결과(finetune.evaluate JSON), 지역 같은 묶음 이름표, 비교할 두 모델
  sources[]  데이터 출처(어드민 data.sources 그대로)
결과 줄은 평가 목록과 순서·정답 글이 같아야 한다(어긋나면 멈춘다). 발화는 음성 파일 이름으로 맞춘다.
소리·받아 적은 글·정답 글은 내보내지 않는다.

쓰기: cd server && .venv/bin/python -m finetune.export_experiment finetune/experiments/2026-11-25-dialect.json [...]
      출력 폴더는 --out, 없으면 환경변수 STT_ADMIN_OUT, 없으면 ../../secretary-ai-test/out/stt
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from finetune.build_dataset import OUT_DIR
from finetune.evaluate import utterance_id
from finetune.export_admin import KST, compare_rows, load_rows, out_dir, rows_by_id, train_fields, trainer_state, utterance_keys, write_run

MATERIAL_DIR = OUT_DIR.parent / "experiments"
ROLES = ("service", "start", "new", "other")


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def mean_cer(rows: list[dict]) -> float | None:
    """finetune.evaluate.summarize 와 같은 평균(받아 적지 못한 줄은 뺀다)."""
    values = [r["cer"] for r in rows if r["cer"] is not None]
    return round(statistics.mean(values), 4) if values else None


def run_times(run_dir: Path, duration_sec: float | None) -> tuple[str, str | None]:
    """ms-swift 폴더 이름(v0-20261125-055828, 클라우드 UTC) → 시작·끝(시작 + 학습 시간) KST."""
    stamp = "-".join(run_dir.name.split("-")[1:3])
    started = datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).astimezone(KST)
    ended = started + timedelta(seconds=round(duration_sec)) if duration_sec is not None else None
    return started.isoformat(), ended.isoformat() if ended else None


def eval_set(spec: dict, material: Path) -> dict:
    """평가셋 하나 → 어드민 evals[] 한 칸."""
    lines = read_lines(material / spec["list"])
    names = [m["name"] for m in spec["models"]]
    if len(set(names)) != len(names) or any(m["role"] not in ROLES for m in spec["models"]):
        raise ValueError(f"{spec['id']}: 모델 이름이 겹치거나 역할이 {ROLES} 밖이에요")
    rows = {m["name"]: load_rows(material / m["result"]) for m in spec["models"]}
    case_by_id = {utterance_id(line): str((line.get("meta") or {}).get("case", "")) for line in lines}
    if len(case_by_id) != len(lines):
        raise ValueError(f"{spec['id']}: 평가 목록에 같은 음성 이름이 있어요")
    keys = {}
    for name, model_rows in rows.items():
        keys[name] = utterance_keys(model_rows, lines)  # id 가 없으면 줄 수·순서·정답 글이 목록과 같아야 한다
        if sorted(keys[name]) != sorted(case_by_id):
            raise ValueError(f"{spec['id']}: {name} 결과의 발화가 평가 목록과 달라요(겹침·빠짐)")
    cers = {m["name"]: json.loads((material / m["result"]).read_text(encoding="utf-8"))["summary"].get("cer") for m in spec["models"]}
    groups = None
    if spec.get("groups"):
        cases = list(case_by_id.values())
        groups = [{
            "key": key, "label": label, "count": cases.count(key),
            "cer": {name: mean_cer([r for r, i in zip(model_rows, keys[name]) if case_by_id[i] == key]) for name, model_rows in rows.items()},
        } for key, label in spec["groups"].items()]
        if sum(g["count"] for g in groups) != len(lines):
            raise ValueError(f"{spec['id']}: 묶음 이름표에 없는 묶음이 있어요")
    compare = None
    if spec.get("compare"):
        start, new = spec["compare"]["from"], spec["compare"]["to"]
        counts = compare_rows(rows_by_id(rows[start], lines), rows_by_id(rows[new], lines))
        if counts is not None:
            compare = {"from": start, "to": new, "better": counts["better"], "worse": counts["worse"], "same": counts["same"]}
    return {
        "id": spec["id"], "label": spec.get("label"), "count": len(lines),
        "verified": sum(bool((line.get("meta") or {}).get("verified")) for line in lines),
        "models": [{"name": m["name"], "role": m["role"], "cer": cers[m["name"]]} for m in spec["models"]],
        "groups": groups, "compare": compare, "notes": spec.get("notes"),
    }


def experiment_record(spec: dict, material_root: Path = MATERIAL_DIR) -> dict:
    """실험 설명 → runs.jsonl 한 줄(옛 eval 은 null, 평가는 evals)."""
    material = material_root / spec["material"]
    run_dir = material / spec["run"]
    state = trainer_state(run_dir / spec["checkpoint"] / "trainer_state.json", run_dir / "logging.jsonl")
    fields = train_fields(state, json.loads((run_dir / "args.json").read_text(encoding="utf-8")))
    started, ended = run_times(run_dir, fields["durationSec"])
    train = len(read_lines(material / spec["trainList"]))
    sources = spec["sources"]
    if sum(s.get("train") or 0 for s in sources) != train:
        raise ValueError(f"{spec['id']}: 출처 train 합이 학습 목록 {train}줄과 달라요")
    return {
        "id": spec["id"], "startedAt": started, "endedAt": ended, "where": spec.get("where"),
        "base": spec.get("base"), "output": spec.get("output"),
        "data": {
            "dataVersion": spec.get("dataVersion"), "clips": None, "flagged": None, "excluded": None,
            "train": train, "trainSec": None, "speakers": None, "sources": sources,
        },
        **fields,
        "eval": None,
        "evals": [eval_set(e, material) for e in spec["evals"]],
        "deployed": spec.get("deployed"),
        "notes": spec.get("notes"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="바깥 자료 STT 실험을 새 앱 어드민(out/stt/runs.jsonl)으로 내보내기")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--material", type=Path, default=MATERIAL_DIR, help="받아 온 실험 자료 폴더들의 위치")
    parser.add_argument("specs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    out = out_dir(args.out)
    for spec_path in args.specs:
        record = experiment_record(json.loads(spec_path.read_text(encoding="utf-8")), args.material)
        print("실험 →", write_run(record, out), record["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
