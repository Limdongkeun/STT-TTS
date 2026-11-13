"""검증된 답변과 일치하는 로컬 WAV를 재생한다."""

import hashlib
import io
import json
import unicodedata
import wave
from pathlib import Path

from app.engines.base import TtsResult

# 2026-11-12 사용자 결정: 일레븐랩스 지수로 입말 문장(spoken_answers.json 34개 + 모르는 질문 답)을 다시 녹음했다
# (server/scripts/make_jisoo_spoken.py). 11/05 원래 답 글 녹음(c1-c7·d1-d25)은 지웠다.
DEFAULT_RECORDINGS_DIR = Path(__file__).resolve().parents[3] / "output/audio/jisoo-spoken"
VOICE_LABEL = "JISOO 녹음 (C1~E2)"


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
        self._recordings = {}
        manifest = json.loads((self._directory / "manifest.json").read_text(encoding="utf-8"))
        for item in manifest["recordings"]:
            self._recordings[canonical_text(item["speechText"])] = (self._directory, item)

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
