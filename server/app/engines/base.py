"""엔진이 지켜야 할 모양."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SttResult:
    text: str
    language: str | None = None


@dataclass(frozen=True)
class TtsResult:
    wav_bytes: bytes
    sample_rate: int
    duration_sec: float


class SttEngine(Protocol):
    name: str

    def transcribe(self, wav_path: Path) -> SttResult: ...


class TtsEngine(Protocol):
    name: str

    def synthesize(self, text: str) -> TtsResult: ...
