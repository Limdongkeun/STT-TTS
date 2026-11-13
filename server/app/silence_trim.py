"""TTS 소리 앞뒤의 조용한 부분을 줄인다 (2026-11-12 사용자 결정).

107 Qwen3-TTS 가 만든 소리는 끝에 약 0.9초씩 조용한 부분이 붙어 있었다(10개 모두 0.88~1.00초).
답을 문장·쉼표에서 나눠 틀면 조각마다 이 0.9초에 다음 조각으로 넘어가는 시간까지 더해져 1초 넘게 비었다.
같은 문장을 통째로 읽을 때 쉼표 쉼은 0.4초였다. 그래서 끝은 쉼표 조각 0.15초, 문장 끝 0.3초만 남긴다.

16비트 PCM WAV 만 다룬다. 다른 형식이거나 소리가 아예 없으면 그대로 돌려준다(소리를 망가뜨리지 않게).
"""

import io
import math
import wave
from array import array

WINDOW_SEC = 0.02
# 가장 큰 창의 이 비율보다 작으면 조용한 창으로 본다(107 소리에서 숨소리·잔향을 말로 치지 않는 값).
RELATIVE_THRESHOLD = 0.05
KEEP_HEAD_SEC = 0.05
KEEP_TAIL_SENTENCE_SEC = 0.3
KEEP_TAIL_COMMA_SEC = 0.15
COMMA_ENDINGS = (",", "，", "、")


def tail_for(text: str) -> float:
    """조각 글이 쉼표로 끝나면 짧게(바로 이어 말하듯), 아니면 문장 끝만큼 남긴다."""
    return KEEP_TAIL_COMMA_SEC if text.rstrip().endswith(COMMA_ENDINGS) else KEEP_TAIL_SENTENCE_SEC


def trim_silence(
    wav_bytes: bytes, keep_tail_sec: float = KEEP_TAIL_SENTENCE_SEC, keep_head_sec: float = KEEP_HEAD_SEC
) -> tuple[bytes, float]:
    """(새 WAV, 새 길이 초). 줄일 게 없거나 다룰 수 없는 형식이면 원래 WAV 와 원래 길이."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as reader:
            params = reader.getparams()
            frames = reader.readframes(params.nframes)
    except (wave.Error, EOFError):
        return wav_bytes, 0.0
    rate, channels = params.framerate, params.nchannels
    original_sec = params.nframes / rate if rate else 0.0
    if params.sampwidth != 2 or rate <= 0 or params.nframes == 0:
        return wav_bytes, original_sec

    samples = array("h")
    samples.frombytes(frames[: len(frames) - len(frames) % (2 * channels)])
    frame_count = len(samples) // channels
    window = max(1, int(rate * WINDOW_SEC))
    levels = []
    for start in range(0, frame_count, window):
        chunk = samples[start * channels : min(frame_count, start + window) * channels]
        levels.append(math.sqrt(sum(value * value for value in chunk) / len(chunk)))
    loudest = max(levels)
    if loudest == 0:
        return wav_bytes, original_sec
    voiced = [index for index, level in enumerate(levels) if level > loudest * RELATIVE_THRESHOLD]
    first = max(0, voiced[0] * window - int(rate * keep_head_sec))
    last = min(frame_count, (voiced[-1] + 1) * window + int(rate * keep_tail_sec))
    if first == 0 and last == frame_count:
        return wav_bytes, original_sec

    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(samples[first * channels : last * channels].tobytes())
    return output.getvalue(), (last - first) / rate
