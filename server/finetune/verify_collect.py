"""와치 '음성 모으기' 녹음 검사(2026-11-19 사용자 결정): 맥 Qwen 한국어판으로 다시 받아 적어 정답(transcript)과 비교한다.

- 읽기 문장은 정답 칸에 문제 글이 미리 들어가고, 상황 문제는 폰 받아쓰기를 확인만 하고 올리는 일이 많다.
  그래서 잘못 읽었거나 폰이 잘못 들은 녹음이 정답과 어긋난 채 섞일 수 있다 → 크게 다른 녹음은 학습에서 뺀다.
- 숫자 꼴 차이('8만 4천 원' / '팔만 사천 원')로 잘못 걸리지 않게, 둘 다 normalize_for_speech(입말 한글)로 바꾼 뒤 CER 을 잰다.
- 결과는 그 폴더의 verify.json. build_dataset collect 가 flagged 인 녹음을 뺀다.
- 맥에서 모델을 올려 돌린다(사용자가 돌리라고 할 때만).

쓰기: cd server && .venv-asr/bin/python -m finetune.verify_collect <푼 폴더> [--threshold 0.15]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from app.normalize import normalize_for_speech
from app.test_sheet import char_error_rate

DEFAULT_MODEL = Path(__file__).resolve().parents[1] / ".models" / "qwen3_asr_1.7b_ko"
DEFAULT_THRESHOLD = 0.15
# 상황 문제는 폰 받아쓰기를 확인만 하고 올리는 일이 많아(11/19 6개 모두) 조금만 달라도 사람이 듣게 한다
SITUATION_THRESHOLD = 0.0
# 첫 소리가 녹음 시작과 거의 같이 나오면 앞이 잘렸을 수 있다(11/19: '나중에'→'중에', '이번 주 분리수거'→'주 분리수거')
MIN_LEAD_MS = 40
FRAME_MS = 20
VERIFY_FILE = "verify.json"


def lead_silence_ms(wav_path: Path) -> int | None:
    """첫 말소리(가장 큰 20ms 구간 세기의 10% 넘는 곳)까지의 길이(ms). 소리가 없으면 None."""
    import array
    import math
    import wave

    with wave.open(str(wav_path)) as reader:
        samples = array.array("h", reader.readframes(reader.getnframes()))
        frame = max(1, reader.getframerate() * FRAME_MS // 1000)
    levels = [math.sqrt(sum(x * x for x in samples[i:i + frame]) / frame) for i in range(0, len(samples) - frame + 1, frame)]
    if not levels or max(levels) == 0:
        return None
    floor = max(levels) * 0.1
    return next(i for i, level in enumerate(levels) if level > floor) * FRAME_MS


def spoken_cer(reference: str, hypothesis: str) -> float | None:
    """숫자를 입말로 맞춘 뒤의 글자 오류율. 받아 적은 글이 없으면 None."""
    return char_error_rate(normalize_for_speech(reference), normalize_for_speech(hypothesis))


def verify_rows(
    folder: Path, rows: list[dict], transcribe: Callable[[str], str],
    threshold: float = DEFAULT_THRESHOLD, situation_threshold: float = SITUATION_THRESHOLD,
) -> list[dict]:
    """녹음마다 {clip_id, item_id, …, mac_stt, cer, lead_ms, reasons, flagged}.
    걸리는 때: 받아 적지 못함 / 정답과 많이 다름(상황 문제는 조금이라도) / 앞이 잘렸을 수 있음."""
    results = []
    for row in rows:
        audio = (folder / row["audio"]).resolve()
        heard = transcribe(str(audio)).strip() if audio.is_file() else ""
        cer = spoken_cer(str(row.get("transcript", "")), heard)
        lead = lead_silence_ms(audio) if audio.is_file() else None
        limit = situation_threshold if row.get("item_type") == "situation" else threshold
        reasons = []
        if cer is None:
            reasons.append("받아 적지 못함")
        elif cer > limit:
            reasons.append("정답과 다름")
        if lead is not None and lead < MIN_LEAD_MS:
            reasons.append("앞 잘림 의심")
        results.append({
            "clip_id": row.get("clip_id"), "item_id": row.get("item_id"), "item_type": row.get("item_type"),
            "speaker_code": row.get("speaker_code"), "transcript_source": row.get("transcript_source"),
            "transcript": row.get("transcript"), "phone_stt_raw": row.get("phone_stt_raw"), "mac_stt": heard,
            "cer": None if cer is None else round(cer, 3), "lead_ms": lead,
            "reasons": reasons, "flagged": bool(reasons),
        })
    return results


def flagged_clip_ids(folder: Path) -> set[str]:
    """그 폴더의 verify.json 에서 걸린 녹음 id. 검사 전이면 빈 집합."""
    path = folder / VERIFY_FILE
    if not path.is_file():
        return set()
    return {str(r["clip_id"]) for r in json.loads(path.read_text(encoding="utf-8"))["results"] if r["flagged"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="음성 모으기 녹음을 맥 STT 로 검사")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    args = parser.parse_args(argv)
    from finetune.evaluate import qwen_transcriber
    from finetune.fetch_collect import load_manifest

    rows = load_manifest(args.folder)
    results = verify_rows(args.folder, rows, qwen_transcriber(args.model), args.threshold)
    (args.folder / VERIFY_FILE).write_text(
        json.dumps({"model": args.model, "threshold": args.threshold, "results": results}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    for r in results:
        mark = "⚠️" if r["flagged"] else "  "
        why = f" [{', '.join(r['reasons'])}]" if r["reasons"] else ""
        print(f"{mark} {r['speaker_code']} {r['item_id']} cer={r['cer']} 앞 {r['lead_ms']}ms{why} | 정답: {r['transcript']} | 맥: {r['mac_stt']}")
    print(f"검사 {len(results)}개, 걸림 {sum(r['flagged'] for r in results)}개 → {args.folder / VERIFY_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
