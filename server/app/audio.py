"""업로드된 음성을 STT 가 읽기 쉬운 16kHz 모노 WAV 로 바꾼다."""

import shutil
import subprocess
from pathlib import Path

TARGET_SAMPLE_RATE = 16000
ALLOWED_SUFFIXES = (".wav", ".m4a", ".mp4", ".aac", ".mp3", ".webm", ".ogg", ".3gp", ".caf")


class AudioConversionError(RuntimeError):
    pass


def normalize_suffix(filename: str | None) -> str:
    """파일 이름의 확장자를 검사한다. 허용 목록에 없으면 오류."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise AudioConversionError(f"지원하지 않는 음성 형식입니다: {suffix or '(확장자 없음)'}")
    return suffix


def to_wav16k(source: Path, target: Path) -> Path:
    """ffmpeg 로 16kHz 모노 WAV 변환. 셸을 거치지 않고 인자 목록으로 실행한다."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioConversionError("ffmpeg 가 설치되어 있지 않습니다. `brew install ffmpeg`")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-ac", "1", "-ar", str(TARGET_SAMPLE_RATE),
        str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise AudioConversionError(f"음성 변환 실패: {result.stderr.strip()[:300]}")
    return target
