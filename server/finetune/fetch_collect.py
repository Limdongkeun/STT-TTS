"""ProjectWatch 앱 '🎤 음성 모으기' 녹음 가져오기(2026-11-19, 와치 쪽 API).

    GET https://pw-api.uptive-korea.com/api/v1/stt-collect/export   헤더 X-Stt-Key
    200 zip(manifest.jsonl + audio/SPKxx/<clip_id>.wav) · 404 없음 · 401 키 틀림 · 503 서버에 키 없음

- 기본은 ?keep=1(서버에서 지우지 않음). 서버에서 지워지는 정식 받기는 --final 일 때만 한다.
  정식으로 받은 zip 은 다시 받을 수 없으니 지우지 않는다(.train/stt-ko/collect/, git 밖).
- 키는 환경변수 STT_COLLECT_KEY, 없으면 맥 키체인 'stt-collect-key'. 로그·파일에 남기지 않는다.
- 받은 zip 은 같은 이름 폴더에 풀고 manifest 를 검사한다(형식·길이·빠진 필드).

쓰기: cd server && .venv-asr/bin/python -m finetune.fetch_collect            (keep=1, 시험)
      cd server && .venv-asr/bin/python -m finetune.fetch_collect --final    (서버에서 지워짐)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import wave
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from finetune.build_dataset import OUT_DIR

API = "https://pw-api.uptive-korea.com/api/v1/stt-collect/export"
KEY_ENV = "STT_COLLECT_KEY"
KEYCHAIN_SERVICE = "stt-collect-key"
COLLECT_DIR = OUT_DIR.parent / "collect"
REQUIRED_FIELDS = ("clip_id", "audio", "item_id", "item_type", "transcript", "speaker_code")
ITEM_TYPES = ("read", "short", "situation")
MIN_SEC, MAX_SEC = 0.5, 20.0
TIMEOUT_SEC = 300


class CollectError(RuntimeError):
    pass


def read_key(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    try:
        result = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def download(target: Path, key: str, keep: bool, opener: Callable = urllib.request.urlopen) -> int | None:
    """zip 을 target 에 받는다. 받은 녹음 수(X-Clip-Count), 가져갈 녹음이 없으면 None."""
    url = API + ("?keep=1" if keep else "")
    request = urllib.request.Request(url, headers={"X-Stt-Key": key})
    part = target.with_suffix(".part")
    try:
        with opener(request, timeout=TIMEOUT_SEC) as response:  # noqa: S310 - 고정 주소
            count = int(response.headers.get("X-Clip-Count") or 0)
            with part.open("wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        if exc.code == 404:
            return None
        reason = {401: "키가 틀렸어요", 503: "서버에 키가 설정돼 있지 않아요"}.get(exc.code, "서버 오류")
        raise CollectError(f"내보내기 실패({exc.code}): {reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        part.unlink(missing_ok=True)
        raise CollectError(f"내보내기에 연결하지 못했어요: {exc}") from exc
    part.rename(target)
    return count


def safe_extract(zip_path: Path, dest: Path) -> None:
    """zip 을 풀되 dest 밖으로 나가는 경로는 막는다."""
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            path = (dest / member.filename).resolve()
            if root != path and root not in path.parents:
                raise CollectError(f"zip 안 경로가 이상해요: {member.filename}")
        archive.extractall(dest)


def load_manifest(folder: Path) -> list[dict]:
    lines = (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def check_rows(folder: Path, rows: list[dict]) -> list[str]:
    """문제 목록(빈 목록이면 모두 정상): 필드 빠짐, 종류, 소리 파일·형식·길이."""
    problems = []
    for row in rows:
        name = row.get("clip_id", "?")
        missing = [field for field in REQUIRED_FIELDS if not str(row.get(field, "")).strip()]
        if missing:
            problems.append(f"{name}: 빠진 칸 {missing}")
            continue
        if row["item_type"] not in ITEM_TYPES:
            problems.append(f"{name}: 모르는 종류 {row['item_type']}")
        audio = (folder / row["audio"]).resolve()
        if folder.resolve() not in audio.parents or not audio.is_file():
            problems.append(f"{name}: 소리 파일 없음 {row['audio']}")
            continue
        try:
            with wave.open(str(audio)) as reader:
                fmt = (reader.getframerate(), reader.getnchannels(), reader.getsampwidth())
                sec = reader.getnframes() / reader.getframerate()
        except (wave.Error, EOFError) as exc:
            problems.append(f"{name}: WAV 를 못 읽음({exc})")
            continue
        if fmt != (16000, 1, 2):
            problems.append(f"{name}: 형식 {fmt}(16000, 1, 2 아님)")
        if not MIN_SEC <= sec <= MAX_SEC:
            problems.append(f"{name}: 길이 {sec:.2f}초")
    return problems


def summarize(rows: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    by_speaker: dict[str, int] = {}
    for row in rows:
        by_type[row.get("item_type", "?")] = by_type.get(row.get("item_type", "?"), 0) + 1
        by_speaker[row.get("speaker_code", "?")] = by_speaker.get(row.get("speaker_code", "?"), 0) + 1
    total_ms = sum(int(row.get("duration_ms") or 0) for row in rows)
    return {"clips": len(rows), "minutes": round(total_ms / 60000, 2), "by_type": by_type, "by_speaker": by_speaker}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="와치 음성 모으기 녹음 가져오기")
    parser.add_argument("--final", action="store_true", help="정식으로 받기(서버에서 지워짐)")
    args = parser.parse_args(argv)
    key = read_key()
    if not key:
        print(f"키가 없어요({KEY_ENV} 또는 키체인 {KEYCHAIN_SERVICE}).")
        return 1
    COLLECT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = COLLECT_DIR / f"stt-collect-{stamp}-{'final' if args.final else 'keep'}.zip"
    try:
        count = download(zip_path, key, keep=not args.final)
    except CollectError as exc:
        print(exc)
        return 1
    if count is None:
        print("가져갈 녹음이 없어요(404).")
        return 0
    folder = zip_path.with_suffix("")
    safe_extract(zip_path, folder)
    rows = load_manifest(folder)
    problems = check_rows(folder, rows)
    print(json.dumps({"zip": str(zip_path), "header_count": count, **summarize(rows)}, ensure_ascii=False))
    for problem in problems:
        print("문제:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
