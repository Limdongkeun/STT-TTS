"""말바꿈 기준선: 시험 문장을 다르게 말해도 같은 답이 나오는지 서버 규칙(family-demo)으로 잰다.

모델을 붙이기 전 규칙만의 이해율을 숫자로 남겨, 모델을 붙인 뒤 같은 문장으로 다시 재서 비교한다.
- 다르게 말한 문장: app/data/paraphrases.json (케이스 id → 문장 목록)
- 한 문장을 잴 때마다 새 기록으로 시작해 앞 케이스들의 원래 문장을 순서대로 말한 뒤 묻는다
  (실기기 시험 순서와 같게: D3 은 D2 에서 우유·기저귀를 넣은 뒤, C4 는 C3 다음).
- 원래 문장의 답과 글자·숫자가 같으면 알아들은 것으로 본다.

실행: cd server && uv run python -m app.paraphrase_baseline
결과: results/paraphrase-baseline/<날짜_시각>.md
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.family_demo import DEMO_NOW, KST, FamilyDemoAnswerProvider, FamilyDemoContext, compact_question
from app.test_sheet import REPO_DIR, TEST_CASES

PARAPHRASES_PATH = Path(__file__).resolve().parent / "data" / "paraphrases.json"
OUTPUT_DIR = REPO_DIR / "results" / "paraphrase-baseline"
# 서버(DEMO_CLOCK=fixed)와 같은 시험 시각으로 잰다.
FIXED_NOW = DEMO_NOW
MAX_SENTENCE_CHARS = 200
UNKNOWN_ANSWER = "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."


@dataclass(frozen=True)
class VariantResult:
    sentence: str
    answer: str
    passed: bool


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    say: str
    reference: str
    variants: list[VariantResult]

    @property
    def passed_count(self) -> int:
        return sum(variant.passed for variant in self.variants)


def load_paraphrases(path: Path = PARAPHRASES_PATH) -> dict[str, list[str]]:
    """파일을 읽고 형식을 확인한다. 밑줄로 시작하는 키(설명)는 건너뛴다."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("말바꿈 파일은 {케이스 id: [문장, ...]} 형태여야 해요.")
    known = {case["id"] for case in TEST_CASES}
    paraphrases: dict[str, list[str]] = {}
    for case_id, sentences in raw.items():
        if case_id.startswith("_"):
            continue
        if case_id not in known:
            raise ValueError(f"모르는 케이스 id: {case_id}")
        if not isinstance(sentences, list) or not sentences:
            raise ValueError(f"{case_id}: 문장 목록이 비어 있어요.")
        for sentence in sentences:
            if not isinstance(sentence, str) or not sentence.strip() or len(sentence) > MAX_SENTENCE_CHARS:
                raise ValueError(f"{case_id}: 빈 문장이거나 {MAX_SENTENCE_CHARS}자를 넘는 문장이 있어요.")
        paraphrases[case_id] = sentences
    return paraphrases


def answer_after_history(case_index: int, sentence: str, now: datetime = FIXED_NOW) -> str:
    """새 기록에서 앞 케이스들의 원래 문장을 차례로 말한 뒤 sentence 를 묻고 답을 돌려준다."""
    provider = FamilyDemoAnswerProvider()
    context: FamilyDemoContext | None = None
    for prior in TEST_CASES[:case_index]:
        _, context = provider.answer(prior["say"], context, now=now)
    answer, _ = provider.answer(sentence, context, now=now)
    return answer


def run_baseline(paraphrases: dict[str, list[str]], now: datetime = FIXED_NOW) -> list[CaseResult]:
    results: list[CaseResult] = []
    for index, case in enumerate(TEST_CASES):
        sentences = paraphrases.get(case["id"])
        if not sentences:
            continue
        reference = answer_after_history(index, case["say"], now)
        # 원래 문장도 못 알아들으면 비교할 답이 없으니 모두 실패로 본다.
        usable = reference != UNKNOWN_ANSWER
        variants = []
        for sentence in sentences:
            answer = answer_after_history(index, sentence, now)
            passed = usable and compact_question(answer) == compact_question(reference)
            variants.append(VariantResult(sentence, answer, passed))
        results.append(CaseResult(case["id"], case["say"], reference, variants))
    return results


def _percent(passed: int, total: int) -> str:
    return f"{round(passed * 100 / total)}%" if total else "-"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(results: list[CaseResult], created: datetime, now: datetime = FIXED_NOW) -> str:
    total = sum(len(result.variants) for result in results)
    passed = sum(result.passed_count for result in results)
    lines = [
        f"# 말바꿈 기준선 — {created:%Y-%m-%d %H:%M}",
        "",
        f"- 답: family-demo 규칙 (모델 없음), 기준 시각 {now:%Y-%m-%d %H:%M} KST",
        f"- **알아들음 {passed}/{total} ({_percent(passed, total)})** — 원래 문장과 같은 답이 나오면 알아들은 것",
        "",
        "| 케이스 | 알아들음 | 원래 문장 |",
        "|---|---|---|",
    ]
    for result in results:
        count = len(result.variants)
        lines.append(f"| {result.case_id} | {result.passed_count}/{count} | {_cell(result.say)} |")
    failures = [(result, variant) for result in results for variant in result.variants if not variant.passed]
    lines += ["", f"## 못 알아들은 문장 ({len(failures)}개)", ""]
    for result, variant in failures:
        lines.append(f"- **{result.case_id}** “{_cell(variant.sentence)}”")
        lines.append(f"  - 나온 답: {_cell(variant.answer)}")
        lines.append(f"  - 원래 답: {_cell(result.reference)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    results = run_baseline(load_paraphrases())
    created = datetime.now(KST)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{created:%Y-%m-%d_%H%M%S}.md"
    path.write_text(render_markdown(results, created), encoding="utf-8")
    total = sum(len(result.variants) for result in results)
    passed = sum(result.passed_count for result in results)
    print(f"알아들음 {passed}/{total} ({_percent(passed, total)}) → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
