"""모델 없이 흐름만 시험하는 가짜 엔진."""

import io
import math
import struct
import wave
from pathlib import Path

from app.engines.base import SttResult, TtsResult

MOCK_TRANSCRIPT = "내일 가족 일정 알려줘"
MOCK_SAMPLE_RATE = 16000


class MockSttEngine:
    name = "mock"

    def transcribe(self, wav_path: Path) -> SttResult:
        return SttResult(text=MOCK_TRANSCRIPT, language="Korean")


class MockTtsEngine:
    """글자 수에 비례한 길이의 짧은 '삐' 소리를 만든다."""

    name = "mock"

    def synthesize(self, text: str) -> TtsResult:
        duration_sec = min(0.3 + 0.05 * len(text), 5.0)
        frame_count = int(MOCK_SAMPLE_RATE * duration_sec)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(MOCK_SAMPLE_RATE)
            frames = bytearray()
            for index in range(frame_count):
                sample = int(8000 * math.sin(2 * math.pi * 440 * index / MOCK_SAMPLE_RATE))
                frames += struct.pack("<h", sample)
            writer.writeframes(bytes(frames))
        return TtsResult(wav_bytes=buffer.getvalue(), sample_rate=MOCK_SAMPLE_RATE, duration_sec=duration_sec)
