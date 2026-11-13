"""화면 답을 소리로 읽을 때 쓰는 입말 문장 (app/data/spoken_answers.json).

2026-11-09 청취 비교: 같은 G 목소리라도 글말("시험 기록에 … 기록했어요")보다 입말("네, 두 시 반으로 적어 뒀어요")이
더 사람 같았다(D7·D11·D24). 화면 답은 그대로 두고 소리만 바꾼다. 규칙은 docs/speech-style-guide.md.
지금은 시험 답 34개만 있다. 실제 서비스에서는 답을 만드는 쪽(LLM)이 이 규칙으로 소리용 문장을 따로 만든다.
"""

import json
import re
from pathlib import Path

from app.engines.prerecorded import canonical_text

SPOKEN_PATH = Path(__file__).resolve().parent / "data" / "spoken_answers.json"
MAX_SPOKEN_CHARS = 200
# 그때그때 소리를 만드는 TTS. 앞뒤 조용한 부분을 자른다.
SPOKEN_ENGINES = ("qwen3-tts-107", "qwen3-tts-107-h2", "qwen3-tts")
# 입말 문장을 읽는 TTS. 지수 녹음도 2026-11-12부터 입말 문장으로 녹음했다(소리 끝 자르기는 SPOKEN_ENGINES 만).
SPOKEN_READERS = (*SPOKEN_ENGINES, "prerecorded")


def load_spoken_answers(path: Path = SPOKEN_PATH) -> dict[str, str]:
    """{화면 답(글자·숫자만): 입말 문장}. 비었거나 같은 답이 두 번 있거나 너무 길면 ValueError."""
    items = json.loads(path.read_text(encoding="utf-8"))["answers"]
    spoken: dict[str, str] = {}
    for item in items:
        key = canonical_text(str(item["answer"]))
        text = str(item["spoken"]).strip()
        if not key or not text:
            raise ValueError(f"{item.get('id')}: 화면 답과 입말 문장이 모두 있어야 해요.")
        if len(text) > MAX_SPOKEN_CHARS:
            raise ValueError(f"{item.get('id')}: 입말 문장은 {MAX_SPOKEN_CHARS}자 이하로 써 주세요.")
        if key in spoken:
            raise ValueError(f"{item.get('id')}: 같은 화면 답이 두 번 있어요.")
        spoken[key] = text
    return spoken


def load_answer_samples(path: Path = SPOKEN_PATH) -> list[dict[str, str]]:
    """'답 듣기' 칸용 시험 답 목록 [{id, answer, spoken}] (파일 순서). 질문 없이 답 소리만 들어 볼 때 쓴다.
    load_spoken_answers 와 같은 검사를 거친다(잘못된 파일이면 ValueError)."""
    load_spoken_answers(path)
    items = json.loads(path.read_text(encoding="utf-8"))["answers"]
    return [
        {"id": str(item["id"]), "answer": str(item["answer"]).strip(), "spoken": str(item["spoken"]).strip()}
        for item in items
    ]


def spoken_for(answer_text: str, spoken: dict[str, str]) -> str | None:
    """이 화면 답의 입말 문장. 없으면 None(원래 문장을 읽는다)."""
    return spoken.get(canonical_text(answer_text))


# ── 목록에 없는 답(실제 LLM·DB 답 포함)을 위한 안전망: 자주 나오는 글말만 입말로 바꾼다 ──
# 숫자·이름·금액·날짜는 건드리지 않는다(테스트로 확인). 순서를 바꾸거나 줄이는 일은 하지 않는다.
# 정말 자연스러운 입말은 답을 만드는 쪽이 소리용 문장을 같이 주는 것이다(docs/speech-style-guide.md).
UNKNOWN_SPOKEN = "음, 그건 아직 잘 모르겠어요. 한 번만 다시 말해 줄래요?"
WHOLE_ANSWER_RULES: dict[str, str] = {
    canonical_text("이 질문에 맞는 시험 답변이 준비돼 있지 않아요."): UNKNOWN_SPOKEN,
}
SPOKEN_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        (r"시험 기록에\s*", ""),
        (r"가상 일정에 등록된 다음 복용 예정 시각은", "다음 약은"),
        (r"걸로 기록했어요", "걸로 적어 뒀어요"),
        (r"을 기록했어요", "을 적어 뒀어요"),
        (r"걸로 수정했어요", "걸로 고쳐 뒀어요"),
        (r"걸로 표시했어요", "걸로 해 뒀어요"),
        (r"걸로 체크했어요", "걸로 체크해 뒀어요"),
        (r"(?<![0-9])1건이에요", "하나예요"),
        (r"두 건이에요", "두 개예요"),
        (r"(?<=[가-힣])에게(?=[ 온보])", "한테"),
        (r"[\'\"‘’“”]", ""),
    )
)


def to_spoken_style(text: str) -> str:
    """어떤 답이든 TTS 로 보내기 전에 자주 나오는 글말을 입말로 바꾼다(안전망)."""
    whole = WHOLE_ANSWER_RULES.get(canonical_text(text))
    if whole:
        return whole
    for pattern, replacement in SPOKEN_RULES:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s{2,}", " ", text).strip()
