import io
import math
import wave

import pytest

from app.silence_trim import KEEP_TAIL_COMMA_SEC, KEEP_TAIL_SENTENCE_SEC, tail_for, trim_silence

RATE = 24000


def make_wav(parts: list[tuple[float, int]], sampwidth: int = 2, channels: int = 1) -> bytes:
    """parts: (초, 세기) 목록. 세기 0 은 조용함, 그 밖은 440Hz 소리."""
    frames = bytearray()
    for seconds, amplitude in parts:
        for index in range(int(seconds * RATE)):
            value = int(amplitude * math.sin(2 * math.pi * 440 * index / RATE))
            frames += value.to_bytes(sampwidth, "little", signed=True) * channels
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sampwidth)
        writer.setframerate(RATE)
        writer.writeframes(bytes(frames))
    return buffer.getvalue()


def seconds_of(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as reader:
        return reader.getnframes() / reader.getframerate()


@pytest.mark.parametrize("tail", [KEEP_TAIL_SENTENCE_SEC, KEEP_TAIL_COMMA_SEC])
def test_trims_head_and_tail_keeps_speech(tail):
    # 107 처럼 앞 0.3초·끝 0.9초가 조용한 소리
    original = make_wav([(0.3, 0), (1.0, 8000), (0.9, 0)])
    trimmed, seconds = trim_silence(original, keep_tail_sec=tail)
    assert seconds == pytest.approx(0.05 + 1.0 + tail, abs=0.03)
    assert seconds_of(trimmed) == pytest.approx(seconds, abs=0.001)


def test_quiet_part_in_the_middle_stays():
    # 쉼표 쉼(0.4초)처럼 가운데 조용한 곳은 건드리지 않는다
    _, seconds = trim_silence(make_wav([(1.0, 8000), (0.4, 0), (1.0, 8000), (0.9, 0)]))
    assert seconds == pytest.approx(2.4 + KEEP_TAIL_SENTENCE_SEC, abs=0.03)


def test_stereo_is_trimmed_too():
    _, seconds = trim_silence(make_wav([(1.0, 8000), (0.9, 0)], channels=2))
    assert seconds == pytest.approx(1.0 + KEEP_TAIL_SENTENCE_SEC, abs=0.03)


@pytest.mark.parametrize(
    "wav_bytes",
    [
        make_wav([(1.0, 0)]),  # 아예 조용함
        make_wav([(1.0, 8000)]),  # 줄일 게 없음
        make_wav([(1.0, 80), (0.9, 0)], sampwidth=1),  # 8비트는 다루지 않음
    ],
)
def test_returns_original_when_nothing_to_do(wav_bytes):
    trimmed, _ = trim_silence(wav_bytes)
    assert trimmed == wav_bytes


def test_not_a_wav_is_returned_as_is():
    assert trim_silence(b"not a wav") == (b"not a wav", 0.0)


@pytest.mark.parametrize(
    ("text", "tail"),
    [("소윤이는 수요일에 체험학습 가고요,", KEEP_TAIL_COMMA_SEC), ("금요일엔 피아노 학원 가요.", KEEP_TAIL_SENTENCE_SEC),
     ("가고요， ", KEEP_TAIL_COMMA_SEC), ("부호 없는 글", KEEP_TAIL_SENTENCE_SEC)],
)
def test_tail_for(text, tail):
    assert tail_for(text) == tail
