"""STT 힌트 낱말: 폰 기본 STT 와 서버 Qwen3-ASR 이 같은 목록을 쓴다(공평 비교, 2026-11-06).

- 목록: app/data/stt_hints.json (앱 app/src/sttModes.ts 의 CONTEXTUAL_WORDS 와 같아야 한다)
- Qwen3-ASR 에는 transcribe(context=...) 로 넣는다. 강제로 바꾸는 게 아니라 그 말 쪽으로 기울게 한다.
"""

import json
from pathlib import Path

HINTS_PATH = Path(__file__).resolve().parent / "data" / "stt_hints.json"
MAX_HINTS = 100
MAX_HINT_CHARS = 20


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
