"""숫자 읽기 시험: 말하지 않고 TTS 가 숫자·날짜·단위를 제대로 읽는지만 듣는다 (2026-11-12 사용자 요청).

문장은 app/data/reading_samples.json. 읽기 글은 답을 읽을 때와 같은 normalize_for_speech 로 만든다.
앱에서 줄마다 ○/× 를 누르고 저장하면 results/number-reading/<기기>/<날짜_시각>.md 로 남긴다.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.normalize import normalize_for_speech
from app.test_sheet import KST, REPO_DIR, read_code_version

SAMPLES_PATH = Path(__file__).resolve().parent / "data" / "reading_samples.json"
DEFAULT_READING_DIR = REPO_DIR / "results" / "number-reading"
MAX_MEMO_CHARS = 200


def load_reading_samples(path: Path = SAMPLES_PATH) -> list[dict[str, str]]:
    """[{id, group, text, reading}]. 번호가 겹치거나 글이 비면 ValueError."""
    samples: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in json.loads(path.read_text(encoding="utf-8"))["samples"]:
        sample_id, group, text = str(item["id"]), str(item["group"]), str(item["text"]).strip()
        if not text:
            raise ValueError(f"{sample_id}: 글이 비었어요.")
        if sample_id in seen:
            raise ValueError(f"{sample_id}: 같은 번호가 두 번 있어요.")
        seen.add(sample_id)
        samples.append({"id": sample_id, "group": group, "text": text, "reading": normalize_for_speech(text)})
    return samples


class ReadingMark(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    heard: Literal["○", "×"]
    memo: str = Field(default="", max_length=MAX_MEMO_CHARS)


class ReadingResults(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    # 시험에 쓴 TTS 이름(/health ttsChoices 의 label). 결과 파일 머리에 적는다.
    tts: str = Field(default="", max_length=80)
    marks: dict[str, ReadingMark] = Field(default_factory=dict, max_length=200)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_reading_results(
    samples: list[dict[str, str]], results: ReadingResults, device: str, moment: datetime, code_version: str
) -> str:
    """결과 마크다운. 안 들은 줄도 표에 남겨 무엇을 빼먹었는지 보이게 한다."""
    ok = sum(1 for mark in results.marks.values() if mark.heard == "○")
    bad = sum(1 for mark in results.marks.values() if mark.heard == "×")
    title = " · ".join(
        part for part in (device, moment.strftime("%Y-%m-%d %H:%M"), results.tts, code_version) if part
    )
    lines = [
        f"# 숫자 읽기 시험 — {title}",
        "",
        f"- 결과: ○ {ok} · × {bad} · 안 들음 {len(samples) - ok - bad} (모두 {len(samples)})",
        "",
        "| # | 갈래 | 글 | 읽기 글 | 들림 | 메모 |",
        "|---|---|---|---|---|---|",
    ]
    for sample in samples:
        mark = results.marks.get(sample["id"])
        lines.append(
            "| " + " | ".join(_cell(value) for value in (
                sample["id"], sample["group"], sample["text"], sample["reading"],
                mark.heard if mark else "", mark.memo if mark else "",
            )) + " |"
        )
    return "\n".join(lines) + "\n"


def save_reading_results(
    samples: list[dict[str, str]],
    results: ReadingResults,
    device: str,
    directory: Path = DEFAULT_READING_DIR,
    now: datetime | None = None,
) -> dict[str, object]:
    """결과 파일을 쓰고 {file, ok, bad} 를 돌려준다. 모르는 번호나 아무것도 안 누른 결과는 ValueError.
    device 는 부르는 쪽이 DEVICE_PATTERN 으로 검사한 값만 넣는다(경로 밖으로 못 나감)."""
    known = {sample["id"] for sample in samples}
    unknown = sorted(set(results.marks) - known)
    if unknown:
        raise ValueError(f"없는 문장 번호예요: {', '.join(unknown[:5])}")
    if not results.marks:
        raise ValueError("○/× 를 하나도 누르지 않았어요.")
    moment = (now or datetime.now(KST)).astimezone(KST)
    path = directory / device / f"{moment.strftime('%Y-%m-%d_%H%M%S')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_reading_results(samples, results, device, moment, read_code_version()), encoding="utf-8")
    shown = path.relative_to(REPO_DIR) if path.is_relative_to(REPO_DIR) else path
    return {
        "file": str(shown),
        "ok": sum(1 for mark in results.marks.values() if mark.heard == "○"),
        "bad": sum(1 for mark in results.marks.values() if mark.heard == "×"),
    }
