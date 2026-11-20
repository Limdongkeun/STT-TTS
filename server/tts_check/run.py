"""TTS 점검(2026-11-19 사용자 결정): 점검 문장을 서버처럼 읽기용 글로 바꿔 ElevenLabs 로 읽히고,
그 소리를 다시 받아 적어(Google Chirp 3, 힌트 없음) 원래 글과 비교한다. 많이 다른 문장 = TTS 가 틀리게 읽었을 수 있는 문장.

- ElevenLabs 크레딧을 쓴다(문장 274개 ≈ 9천 자). 만든 소리는 점검에만 쓰고 다른 모델 학습에 쓰지 않는다(ElevenLabs 정책).
- 받아 적기는 '채점하는 귀'일 뿐이라 STT 가 틀린 것도 섞인다 → 걸린 문장은 사람이 듣고 판단한다.
- 결과: server/.train/tts-check/<시각>/ (report.json, listen.csv, 걸린 문장·무작위 문장 묶음 m4a). 이미 만든 소리는 건너뛴다.

쓰기: cd server && .venv-asr/bin/python -m tts_check.run [--engine elevenlabs-v4-turbo-female] [--limit N] [--out 폴더]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import tempfile
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from app.normalize import normalize_for_speech
from finetune.build_dataset import _raw_lines
from finetune.verify_collect import spoken_cer

SENTENCES_PATH = Path(__file__).resolve().parent / "check_sentences.txt"
OUT_ROOT = Path(__file__).resolve().parents[1] / ".train" / "tts-check"
FLAG_CER = 0.10
WORKERS = 3
RANDOM_SAMPLE = 30


def load_sentences(path: Path = SENTENCES_PATH) -> list[dict]:
    return [
        {"no": number, "category": category, "text": text, "speech": normalize_for_speech(text)}
        for number, (category, text) in enumerate(_raw_lines(path), start=1)
    ]


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as reader:
        return reader.getnframes() / reader.getframerate()


def check_one(item: dict, out_dir: Path, tts, stt) -> dict:
    from app.audio import to_wav16k

    wav = out_dir / "audio" / f"{item['no']:03d}.wav"
    tts_sec = None
    if not wav.is_file():
        started = time.perf_counter()
        wav.write_bytes(tts.synthesize(item["speech"]).wav_bytes)
        tts_sec = round(time.perf_counter() - started, 2)
    with tempfile.TemporaryDirectory() as job:
        heard = stt.transcribe(to_wav16k(wav, Path(job) / "a.wav")).text.strip()
    cer = spoken_cer(item["text"], heard)
    seconds = wav_seconds(wav)
    return {
        **item, "heard": heard, "cer": None if cer is None else round(cer, 3), "tts_sec": tts_sec,
        "audio_sec": round(seconds, 2), "chars_per_sec": round(len(item["speech"].replace(" ", "")) / seconds, 1) if seconds else None,
        "flagged": cer is None or cer > FLAG_CER,
    }


def bundle(paths: list[Path], target: Path) -> None:
    """여러 wav 를 0.8초 쉼을 두고 이어 m4a 한 파일로(폰에서 듣기용)."""
    if not paths:
        return
    with tempfile.TemporaryDirectory() as job:
        gap = Path(job) / "gap.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.8", str(gap)], check=True)
        listing = Path(job) / "list.txt"
        listing.write_text("".join(f"file '{p}'\nfile '{gap}'\n" for p in paths), encoding="utf-8")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-ar", "24000", "-ac", "1", "-c:a", "aac", "-b:a", "96k", str(target)], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TTS 점검(ElevenLabs → Chirp 3 받아 적기)")
    parser.add_argument("--engine", default="elevenlabs-v4-turbo-female")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    from app.engines.elevenlabs import ElevenLabsTtsEngine
    from app.engines.google_stt import GoogleSttEngine

    items = load_sentences()[: args.limit or None]
    out_dir = args.out or OUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M")
    (out_dir / "audio").mkdir(parents=True, exist_ok=True)
    tts, stt = ElevenLabsTtsEngine(args.engine), GoogleSttEngine("google-chirp3")
    with ThreadPoolExecutor(WORKERS) as pool:
        rows = list(pool.map(lambda item: check_one(item, out_dir, tts, stt), items))
    flagged = [r for r in rows if r["flagged"]]
    rest = [r for r in rows if not r["flagged"]]
    sample = sorted(random.Random(19).sample(rest, min(RANDOM_SAMPLE, len(rest))), key=lambda r: r["no"])
    summary = {
        "engine": args.engine, "sentences": len(rows), "flagged": len(flagged),
        "chars": sum(len(r["speech"]) for r in rows),
        "by_category": {c: sum(1 for r in flagged if r["category"] == c) for c in dict.fromkeys(r["category"] for r in rows)},
    }
    (out_dir / "report.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out_dir / "listen.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["no", "category", "text", "speech", "heard", "cer", "flagged", "자연스러움(1~5)", "메모"])
        for r in rows:
            writer.writerow([r["no"], r["category"], r["text"], r["speech"], r["heard"], r["cer"], r["flagged"], "", ""])
    bundle([out_dir / "audio" / f"{r['no']:03d}.wav" for r in flagged], out_dir / "flagged.m4a")
    bundle([out_dir / "audio" / f"{r['no']:03d}.wav" for r in sample], out_dir / "random30.m4a")
    (out_dir / "bundles.txt").write_text(
        "flagged.m4a 순서:\n" + "".join(f"{r['no']} {r['text']}\n" for r in flagged)
        + "\nrandom30.m4a 순서:\n" + "".join(f"{r['no']} {r['text']}\n" for r in sample), encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    for r in flagged:
        print(f"⚠️ {r['no']} [{r['category']}] cer={r['cer']} | {r['text']} | 읽기: {r['speech']} | 들림: {r['heard']}")
    print(f"→ {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
