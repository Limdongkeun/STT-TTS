"""검증된 답변과 일치하는 로컬 WAV를 재생한다."""

import hashlib
import io
import json
import unicodedata
import wave
from pathlib import Path

from app.engines.base import TtsResult

DEFAULT_RECORDINGS_DIR = Path(__file__).resolve().parents[3] / "output/audio/d1-d25"
VOICE_LABEL = "JISOO 사전 녹음 (C1~C7·D1~D25)"


class RecordingUnavailableError(RuntimeError):
    pass


def canonical_text(text: str) -> str:
    """녹음 찾기용 글: 한글 표준형(NFC)에서 글자·숫자만 남긴다.

    폰 STT 가 띄어 쓴 말이 답에 그대로 들어가도('퇴근 길에' / '퇴근길에') 같은 녹음을 찾는다.
    """
    return "".join(char for char in unicodedata.normalize("NFC", text) if unicodedata.category(char)[0] in "LN")


class PrerecordedTtsEngine:
    name = "prerecorded"

    def __init__(self, directory: Path = DEFAULT_RECORDINGS_DIR) -> None:
        self._directory = directory.resolve()
        directories = [self._directory]
        if self._directory == DEFAULT_RECORDINGS_DIR.resolve():
            directories.append(self._directory.parent / "c1-c7")
        self._recordings = {}
        for folder in directories:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            for item in manifest["recordings"]:
                self._recordings[canonical_text(item["speechText"])] = (folder, item)

    def synthesize(self, text: str) -> TtsResult:
        recording = self._recordings.get(canonical_text(text))
        if recording is None:
            raise RecordingUnavailableError("이 답변과 일치하는 사전 음성이 없습니다. 화면 답변을 확인해 주세요.")
        directory, item = recording
        path = (directory / item["wavFile"]).resolve()
        if path.parent != directory:
            raise ValueError("사전 음성 파일 경로가 올바르지 않습니다.")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("사전 음성 파일 검증에 실패했습니다.")
        with wave.open(io.BytesIO(data), "rb") as reader:
            sample_rate = reader.getframerate()
            duration = reader.getnframes() / sample_rate
        return TtsResult(wav_bytes=data, sample_rate=sample_rate, duration_sec=duration)
