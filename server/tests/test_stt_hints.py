import json

import pytest

from app.engines.qwen3_asr import Qwen3AsrEngine
from app.stt_hints import echoes_hint_context, hint_context, load_hint_words
from tests.test_api import make_settings


def test_hint_file_loads_and_keeps_known_words():
    words = load_hint_words()
    assert {"소윤이", "부르펜", "어린이집 하원", "친정 용돈"} <= set(words)
    assert "학원" not in words  # 하원이 학원으로 끌려가지 않게


def test_hint_context_lists_words_and_is_empty_without_words():
    assert hint_context(["소윤이", "콩이"]) == "다음 낱말이 나올 수 있어요: 소윤이, 콩이"
    assert hint_context([]) == ""


@pytest.mark.parametrize(
    "words",
    [[], ["소윤이", "소윤이"], [" 콩이"], ["가" * 21], "소윤이"],
)
def test_load_rejects_bad_lists(tmp_path, words):
    path = tmp_path / "hints.json"
    path.write_text(json.dumps({"words": words}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_hint_words(path)


def test_qwen_engine_uses_hints_unless_turned_off():
    # 엔진을 만들기만 해서는 모델을 불러오지 않는다.
    on = Qwen3AsrEngine(make_settings(stt_engine="qwen3-asr"))
    off = Qwen3AsrEngine(make_settings(stt_engine="qwen3-asr", stt_hints="off"))
    assert on.hint_count == len(load_hint_words()) and on._context.startswith("다음 낱말")
    assert (off.hint_count, off._context) == (0, "")


D19_ECHO = (
    "다음 낱말이 나올 수 있어요: 소윤이, 소윤, 콩이, 남편, 아내, 남편한테, 아내한테, 시어머니, "
    "친정엄마, 외할머니, 할머니, 할아버지, 아버지, 엄마, 아빠, 가족 일정, 부탁"
)


@pytest.mark.parametrize(
    "text",
    [
        D19_ECHO,  # 11/12 10:46 D19 그대로
        "다음낱말이나올수있어요 소윤이",  # 띄어쓰기가 달라도
        "소윤이, 콩이, 남편, 아내, 부탁",  # 머리말 없이 힌트 낱말만 늘어놓음
    ],
)
def test_echo_detected(text):
    assert echoes_hint_context(text, load_hint_words())


@pytest.mark.parametrize(
    "text",
    [
        "친정 용돈 아내가 보냈어.",
        "남편한테 퇴근길에 약국 들러 달라고 부탁해 줘.",
        "장보기 목록에 우유, 기저귀 넣어 줘.",  # 쉼표가 있어도 힌트 낱말 셋 아래
        "소윤이, 콩이, 남편 다 데리고 가.",
        "",
    ],
)
def test_real_speech_is_kept(text):
    assert not echoes_hint_context(text, load_hint_words())


def test_no_hints_means_no_echo():
    assert not echoes_hint_context(D19_ECHO, [])


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.language = "Korean"


class _FakeModel:
    def __init__(self, text: str) -> None:
        self._text = text

    def transcribe(self, audio, context, language):
        return [_FakeResult(self._text)]


@pytest.mark.parametrize(("heard", "expected"), [(D19_ECHO, ""), (" 친정 용돈 아내가 보냈어. ", "친정 용돈 아내가 보냈어.")])
def test_engine_drops_echo_only(tmp_path, heard, expected):
    engine = Qwen3AsrEngine(make_settings(stt_engine="qwen3-asr"))
    engine._model = _FakeModel(heard)  # 진짜 모델을 불러오지 않는다
    assert engine.transcribe(tmp_path / "x.wav").text == expected
