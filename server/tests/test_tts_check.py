"""TTS 점검(2026-11-19): 점검 문장 목록과 한 문장 검사. 실제 ElevenLabs·구글은 부르지 않는다."""

import io
import re
import wave
from types import SimpleNamespace

from tts_check.run import check_one, load_sentences


def wav_bytes(seconds=1.0, rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


def test_check_sentences_cover_many_kinds_and_read_digits_as_words():
    items = load_sentences()
    assert len(items) >= 250 and len({i["text"] for i in items}) == len(items)
    assert {"돈", "날짜", "영어·약어", "기호·행사", "물음", "긴 답", "영어 섞인 말"} <= {i["category"] for i in items}
    # 숫자·대문자 약어·기호는 모두 읽기 글로 바뀐다(영어 낱말 섞인 말만 일부러 남긴다)
    leftovers = [i for i in items if i["category"] != "영어 섞인 말" and re.search(r"[0-9A-Z$%&+]", i["speech"])]
    assert not leftovers, leftovers[:3]


def test_check_one_flags_misread(tmp_path, monkeypatch):
    monkeypatch.setattr("app.audio.to_wav16k", lambda source, target: source)
    (tmp_path / "audio").mkdir()
    tts = SimpleNamespace(synthesize=lambda text: SimpleNamespace(wav_bytes=wav_bytes()))
    item = {"no": 1, "category": "돈", "text": "관리비는 23만 4천 원이에요.", "speech": "관리비는 이십삼만 사천 원이에요."}
    good = check_one(item, tmp_path, tts, SimpleNamespace(transcribe=lambda p: SimpleNamespace(text="관리비는 23만 4천 원이에요.")))
    assert good["flagged"] is False and good["cer"] == 0.0 and good["audio_sec"] == 1.0
    (tmp_path / "audio" / "001.wav").unlink()
    bad = check_one(item, tmp_path, tts, SimpleNamespace(transcribe=lambda p: SimpleNamespace(text="관리비는 이십삼만 원이에요.")))
    assert bad["flagged"] is True
