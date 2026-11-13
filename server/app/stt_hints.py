"""STT 힌트 낱말: 폰 기본 STT 와 서버 Qwen3-ASR 이 같은 목록을 쓴다(공평 비교, 2026-11-06).

- 목록: app/data/stt_hints.json (앱 app/src/sttModes.ts 의 CONTEXTUAL_WORDS 와 같아야 한다)
- Qwen3-ASR 에는 transcribe(context=...) 로 넣는다. 강제로 바꾸는 게 아니라 그 말 쪽으로 기울게 한다.
"""

import json
import re
from pathlib import Path

HINTS_PATH = Path(__file__).resolve().parent / "data" / "stt_hints.json"
MAX_HINTS = 100
MAX_HINT_CHARS = 20
HINT_PREFIX = "다음 낱말이 나올 수 있어요"
# 쉼표로 나눈 조각 가운데 힌트 낱말과 똑같은 것이 이만큼 이상이면 힌트 글을 따라 쓴 것으로 본다.
# 사람이 힌트 낱말 넷을 쉼표로 늘어놓아 말하는 일은 드물고, STT 가 그렇게 쉼표를 찍는 일은 더 드물다.
MIN_ECHOED_HINTS = 4


def load_hint_words(path: Path = HINTS_PATH) -> list[str]:
    """목록을 읽고 형식을 확인한다(빈 말·겹침·너무 긴 말·너무 많은 말은 ValueError)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    words = raw.get("words") if isinstance(raw, dict) else None
    if not isinstance(words, list) or not words:
        raise ValueError("힌트 파일은 {\"words\": [낱말, ...]} 형태여야 해요.")
    if len(words) > MAX_HINTS:
        raise ValueError(f"힌트는 {MAX_HINTS}개까지예요.")
    for word in words:
        if not isinstance(word, str) or not word.strip() or word != word.strip() or len(word) > MAX_HINT_CHARS:
            raise ValueError(f"잘못된 힌트 낱말: {word!r}")
    if len(set(words)) != len(words):
        raise ValueError("겹치는 힌트 낱말이 있어요.")
    return words


def hint_context(words: list[str]) -> str:
    """Qwen3-ASR context(시스템 글)로 넣을 문장."""
    return "다음 낱말이 나올 수 있어요: " + ", ".join(words) if words else ""


def echoes_hint_context(text: str, words: list[str]) -> bool:
    """STT 가 말 대신 힌트 글(context)을 따라 쓴 결과인지.

    2026-11-12 10:46 D19: Qwen3-ASR 이 '친정 용돈 아내가 보냈어' 대신 힌트 글 전체를 돌려줬다
    (소리가 거의 비었을 때로 짐작). 그 글 속 '남편한테·부탁' 때문에 엉뚱한 답이 나왔다.
    힌트를 넣지 않았으면(words 없음) 따라 쓸 글도 없으므로 늘 False.
    """
    if not words or not text:
        return False
    if re.sub(r"\s+", "", HINT_PREFIX) in re.sub(r"\s+", "", text):
        return True
    hint_set = set(words)
    pieces = (piece.strip(" .") for piece in re.split(r"[,，]", text))
    return sum(1 for piece in pieces if piece in hint_set) >= MIN_ECHOED_HINTS
