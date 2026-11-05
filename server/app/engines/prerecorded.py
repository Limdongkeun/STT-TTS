"""검증된 답변과 일치하는 로컬 WAV를 재생한다."""

import hashlib
import io
import json
import unicodedata
import wave
from pathlib import Path

from app.engines.base import TtsResult

DEFAULT_RECORDINGS_DIR = Path(__file__).resolve().parents[3] / "output/audio/d1-d25"
VOICE_LABEL = "JISOO 사전 녹음 (D1~D25)"


class RecordingUnavailableError(RuntimeError):
    pass


def canonical_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


class PrerecordedTtsEngine:
    name = "prerecorded"

    def __init__(self, directory: Path = DEFAULT_RECORDINGS_DIR) -> None:
        self._directory = directory.resolve()
        manifest = json.loads((self._directory / "manifest.json").read_text(encoding="utf-8"))
        self._recordings = {canonical_text(item["speechText"]): item for item in manifest["recordings"]}

    def synthesize(self, text: str) -> TtsResult:
        item = self._recordings.get(canonical_text(text))
        if item is None:
            raise RecordingUnavailableError("이 답변과 일치하는 사전 음성이 없습니다. 화면 답변을 확인해 주세요.")
        path = (self._directory / item["wavFile"]).resolve()
        if path.parent != self._directory:
            raise ValueError("사전 음성 파일 경로가 올바르지 않습니다.")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("사전 음성 파일 검증에 실패했습니다.")
        with wave.open(io.BytesIO(data), "rb") as reader:
            sample_rate = reader.getframerate()
            duration = reader.getnframes() / sample_rate
        return TtsResult(wav_bytes=data, sample_rate=sample_rate, duration_sec=duration)
