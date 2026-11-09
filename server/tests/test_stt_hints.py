import json

import pytest

from app.engines.qwen3_asr import Qwen3AsrEngine
from app.stt_hints import hint_context, load_hint_words
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
