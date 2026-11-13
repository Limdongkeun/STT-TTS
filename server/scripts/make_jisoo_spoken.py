"""시험 답의 소리용 입말 문장을 일레븐랩스 지수 목소리로 녹음해 사전 녹음 폴더를 만든다.

2026-11-12 사용자 결정: 사용자 본인 일레븐랩스 키로, 지수 목소리로 입말 문장(app/data/spoken_answers.json 34개와
모르는 질문 답 1개)을 녹음하고 예전 녹음(11/05 원래 답 글)을 바꾼다. 이번 녹음만 허락받았다 — 다시 돌리기 전에 사용자에게 묻는다.

키: 환경변수 ELEVENLABS_API_KEY, 없으면 ~/.elevenlabs_key 파일(레포 밖). 키는 화면·파일·기록에 남기지 않는다.
실행(서버 폴더에서):  .venv-asr/bin/python scripts/make_jisoo_spoken.py [--dry-run]
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from app.normalize import normalize_for_speech  # noqa: E402
from app.spoken_answers import UNKNOWN_SPOKEN, load_answer_samples  # noqa: E402

OUT_DIR = SERVER_DIR.parent / "output" / "audio" / "jisoo-spoken"
VOICE_ID = "iWLjl1zCuqXRkW6494ve"  # 지수 (11/05 녹음과 같은 목소리)
MODEL_ID = "eleven_v4"  # 11/05 녹음과 같은 모델
SAMPLE_RATE = 24000
API = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format=pcm_{SAMPLE_RATE}"
KEY_FILE = Path.home() / ".elevenlabs_key"
UNKNOWN_ANSWER = "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."


def read_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit("일레븐랩스 키가 없어요: ELEVENLABS_API_KEY 또는 ~/.elevenlabs_key")
    return key


def items() -> list[dict[str, str]]:
    rows = [
        {"id": sample["id"], "answerText": sample["answer"], "speechText": normalize_for_speech(sample["spoken"])}
        for sample in load_answer_samples()
    ]
    rows.append({"id": "UNKNOWN", "answerText": UNKNOWN_ANSWER, "speechText": normalize_for_speech(UNKNOWN_SPOKEN)})
    return rows


def synthesize(key: str, text: str) -> bytes:
    body = json.dumps({"text": text, "model_id": MODEL_ID}).encode("utf-8")
    request = urllib.request.Request(API, body, {"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"일레븐랩스 오류 {error.code}: {detail}") from None


def pcm_to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(pcm)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="부르지 않고 읽을 글과 글자 수만 본다")
    args = parser.parse_args()
    rows = items()
    print(f"{len(rows)}개 · {sum(len(row['speechText']) for row in rows)}자")
    if args.dry_run:
        for row in rows:
            print(row["id"], row["speechText"])
        return
    key = read_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    recordings = []
    for row in rows:  # 한 번에 하나씩
        started = time.time()
        pcm = synthesize(key, row["speechText"])
        if len(pcm) < SAMPLE_RATE:  # 0.5초 미만이면 이상한 소리
            raise SystemExit(f"{row['id']}: 소리가 너무 짧아요({len(pcm)} bytes)")
        wav = pcm_to_wav(pcm)
        wav_name, mp3_name = f"{row['id']}.wav", f"{row['id']}.mp3"
        (OUT_DIR / wav_name).write_bytes(wav)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT_DIR / wav_name), "-b:a", "128k", str(OUT_DIR / mp3_name)],
            check=True,
        )
        duration = len(pcm) / 2 / SAMPLE_RATE
        recordings.append({
            **row, "wavFile": wav_name, "mp3File": mp3_name,
            "durationSec": round(duration, 2), "sha256": hashlib.sha256(wav).hexdigest(),
        })
        print(f"{row['id']} {duration:.2f}초 ({time.time() - started:.1f}초 걸림)", flush=True)
    manifest = {
        "generatedOn": time.strftime("%Y-%m-%d"), "voiceName": "지수", "voiceId": VOICE_ID, "model": MODEL_ID,
        "source": "ElevenLabs API", "text": "app/data/spoken_answers.json 입말 문장 + 모르는 질문 답",
        "totalDurationSec": round(sum(item["durationSec"] for item in recordings), 2), "recordings": recordings,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"끝: {OUT_DIR} · 모두 {manifest['totalDurationSec']}초")


if __name__ == "__main__":
    main()
