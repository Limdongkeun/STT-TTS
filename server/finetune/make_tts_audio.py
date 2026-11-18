"""STT 학습 소리 만들기: 맥 llama.cpp Qwen3-TTS 1.7B Base(Apache-2.0)로 train_sentences.txt 를 읽힌다(2026-11-17 사용자 결정).

- ElevenLabs 소리는 학습에 쓰지 않는다(ElevenLabs 금지 사용 정책 12항: Output 으로 AI 모델 학습 금지).
- 목소리: 서버 목소리 견본 g·h2·h2-d(app/data/voices, 107 이 설명으로 만든 목소리라 실제 사람 아님)를 문장마다 돌려 쓰고,
  seed 도 문장마다 바꿔 억양을 섞는다. 읽는 글은 load_items 의 speech(숫자는 입말로).
- 결과: <out>/<문장 번호>_<목소리>.wav (번호는 1부터, build_dataset train 이 이 이름으로 정답과 짝짓는다).
  이미 있는 파일은 건너뛴다(중간에 멈춰도 다시 돌리면 이어서 만든다).
- 사용자가 '시작해'라고 할 때만 돌린다(맥이 바빠진다). 문장당 약 6~7초.

쓰기: cd server && .venv-asr/bin/python -m finetune.make_tts_audio [--limit N]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from finetune.build_dataset import OUT_DIR, SERVER_DIR, load_items

TEACHER_DIR = SERVER_DIR / ".train" / "qwen-h2d" / "teacher"
LLAMA = SERVER_DIR / ".lfm3" / "llama" / "llama-server"
MODEL = TEACHER_DIR / "Qwen3-TTS-1.7B-Base-Q8_0.gguf"
MMPROJ = TEACHER_DIR / "mmproj-Qwen3-TTS-1.7B-Base-Q8_0.gguf"
VOICES_DIR = SERVER_DIR / "app" / "data" / "voices"
VOICES = ("g", "h2-d", "h2")
PORT = 8096
AUDIO_DIR = OUT_DIR.parent / "audio-qwen-tts"


def plan_jobs(count: int, voices: tuple[str, ...] = VOICES) -> list[tuple[int, str, int]]:
    """문장 번호(1부터)마다 (번호, 목소리, seed). 목소리는 차례로 돌리고 seed 는 번호로 바꾼다."""
    return [(number, voices[(number - 1) % len(voices)], 100 + number) for number in range(1, count + 1)]


def clip_path(out_dir: Path, number: int, voice: str) -> Path:
    return out_dir / f"{number:04d}_{voice}.wav"


def _post(body: dict, timeout: float = 180) -> bytes:
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/tts", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 127.0.0.1 고정
        return response.read()


def _healthy() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as response:  # noqa: S310
            return response.status == 200
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="STT 학습 소리 만들기(맥 Qwen3-TTS)")
    parser.add_argument("--limit", type=int, default=0, help="앞 N 문장만(시험용)")
    parser.add_argument("--out", type=Path, default=AUDIO_DIR)
    args = parser.parse_args(argv)
    for needed in (LLAMA, MODEL, MMPROJ, *(VOICES_DIR / f"{v}.wav" for v in VOICES)):
        if not needed.is_file():
            parser.error(f"없는 파일: {needed}")
    items = load_items()
    jobs = plan_jobs(len(items))[: args.limit or None]
    args.out.mkdir(parents=True, exist_ok=True)
    refs = {voice: base64.b64encode((VOICES_DIR / f"{voice}.wav").read_bytes()).decode() for voice in VOICES}
    log = open(OUT_DIR.parent / "logs" / "tts-server.log", "ab") if (OUT_DIR.parent / "logs").is_dir() else subprocess.DEVNULL
    server = subprocess.Popen(
        [str(LLAMA), "-m", str(MODEL), "-mm", str(MMPROJ), "--host", "127.0.0.1", "--port", str(PORT)],
        stdout=log, stderr=subprocess.STDOUT,
    )
    made = failed = 0
    started = time.time()
    try:
        for _ in range(240):
            if _healthy():
                break
            time.sleep(0.5)
        else:
            raise SystemExit("TTS 서버가 뜨지 않았어요")
        for number, voice, seed in jobs:
            path = clip_path(args.out, number, voice)
            if path.is_file() and path.stat().st_size > 1000:
                continue
            body = {"input": items[number - 1]["speech"], "lang": "ko", "speaker_ref_b64": refs[voice], "seed": seed}
            try:
                path.write_bytes(_post(body))
                made += 1
            except OSError as exc:
                failed += 1
                print(f"FAIL {path.name}: {exc}", flush=True)
                continue
            print(f"{number}/{len(items)} {path.name}", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    print(f"만듦 {made}, 실패 {failed}, {time.time() - started:.0f}초 → {args.out}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
