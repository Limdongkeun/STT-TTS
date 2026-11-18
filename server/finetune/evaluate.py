"""STT 추가 학습 전후 비교: 평가 세트(eval.jsonl, 실기기 녹음)를 모델 하나로 받아 적고 CER·시간을 잰다.

- 서버와 같은 방식(Qwen3ASRModel, bf16, 기기 auto, 한국어, 힌트 없음)으로 불러온다.
- 학습한 LoRA 는 먼저 `swift export --adapters <체크포인트> --merge_lora true` 로 합친 폴더를 넘긴다.
- 정답이 사람 확인(verified)된 줄만 따로도 센다. 확인 안 된 줄은 대본 기준이라 입말 차이가 섞인다.

쓰기: cd server && .venv-asr/bin/python -m finetune.evaluate --model .models/qwen3_asr_1.7b_ko --name base
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from app.test_sheet import char_error_rate
from finetune.build_dataset import OUT_DIR

ASR_TEXT_TAG = "<asr_text>"


def answer_text(row: dict) -> str:
    """swift 줄의 정답 글(language X<asr_text> 뒤)."""
    content = row["messages"][-1]["content"]
    return content.split(ASR_TEXT_TAG, 1)[-1].strip()


def summarize(rows: list[dict]) -> dict:
    """줄마다 {cer, sec, verified} → 평균 CER(전체·확인된 것)·중앙 시간."""
    def mean_cer(items: list[dict]) -> float | None:
        values = [r["cer"] for r in items if r["cer"] is not None]
        return round(statistics.mean(values), 4) if values else None

    secs = [r["sec"] for r in rows]
    return {
        "count": len(rows),
        "cer": mean_cer(rows),
        "verified_count": sum(r["verified"] for r in rows),
        "verified_cer": mean_cer([r for r in rows if r["verified"]]),
        "empty": sum(r["cer"] is None for r in rows),
        "median_sec": round(statistics.median(secs), 3) if secs else None,
    }


def run(model_dir: str, eval_path: Path) -> list[dict]:
    from qwen_asr import Qwen3ASRModel

    from app.device import resolve_device, resolve_dtype

    model = Qwen3ASRModel.from_pretrained(model_dir, dtype=resolve_dtype("bfloat16"), device_map=resolve_device("auto"))
    lines = [json.loads(line) for line in eval_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # 첫 호출 예열(시간에서 뺀다)
    model.transcribe(audio=lines[0]["audios"][0], context="", language="Korean")
    rows = []
    for line in lines:
        start = time.perf_counter()
        text = model.transcribe(audio=line["audios"][0], context="", language="Korean")[0].text.strip()
        sec = time.perf_counter() - start
        reference = answer_text(line)
        meta = line.get("meta", {})
        rows.append({
            "case": meta.get("case", ""), "run": meta.get("run", ""), "verified": bool(meta.get("verified")),
            "reference": reference, "text": text, "cer": char_error_rate(reference, text), "sec": round(sec, 3),
        })
        print(rows[-1]["case"], rows[-1]["cer"], text, flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="평가 세트로 STT 모델 하나 재기")
    parser.add_argument("--model", required=True, help="모델 폴더(합친 LoRA 포함)")
    parser.add_argument("--name", required=True, help="결과 파일 이름(base, lora-e1 …)")
    parser.add_argument("--eval", type=Path, default=OUT_DIR / "eval.jsonl")
    args = parser.parse_args(argv)
    if not args.name.replace("-", "").replace("_", "").isalnum():
        parser.error("--name 은 글자·숫자·-·_ 만")
    rows = run(args.model, args.eval)
    result = {"model": args.model, "summary": summarize(rows), "rows": rows}
    out = OUT_DIR.parent / "eval" / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
