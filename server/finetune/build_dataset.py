"""STT 추가 학습(TeamUNIVA Qwen3-ASR 한국어판 + ms-swift) 데이터 만들기. 2026-11-17 사용자: 학습 준비.

- eval  : 실기기 시험 녹음(results/test-runs/*/<run>-audio)을 평가 세트로 모은다. 같은 녹음(md5)은 한 번만.
          정답은 시험표 spoken 칸(사람이 적은 실제 말)이 있으면 그것, 없으면 대본(say) — 이때 verified=false.
          사람이 확인할 수 있게 eval_check.csv(대본·폰이 받아 적은 글·고칠 칸)도 쓴다.
- train : train_sentences.txt 문장과 그 소리(<audio-dir>/<번호>.wav, 녹음 또는 TTS)를 짝지어 학습 세트를 쓴다.
          시험표 문장과 너무 비슷한 문장은 막는다(평가가 부풀지 않게).

출력 줄 모양(ms-swift): {"messages": [{"role": "user", "content": "<audio>"},
                                      {"role": "assistant", "content": "language Korean<asr_text>…"}], "audios": [경로]}

쓰기: cd server && .venv-asr/bin/python -m finetune.build_dataset eval
      cd server && .venv-asr/bin/python -m finetune.build_dataset train --audio-dir <폴더>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from app.family_demo import compact_question
from app.test_sheet import TEST_CASES, _edit_distance, reference_text

SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SERVER_DIR.parent
SENTENCES_PATH = Path(__file__).resolve().parent / "train_sentences.txt"
RESULTS_DIR = REPO_DIR / "results" / "test-runs"
OUT_DIR = SERVER_DIR / ".train" / "stt-ko" / "data"
LANGUAGE = "Korean"
# 시험표 문장과 글자 차이가 이 비율보다 작으면 '거의 같은 문장'으로 본다
NEAR_DUPLICATE_RATIO = 0.35


def swift_row(audio_path: str, text: str, language: str = LANGUAGE) -> dict:
    """ms-swift qwen3_asr 학습 한 줄. 모델이 내는 글 모양(language X<asr_text>글) 그대로 정답을 쓴다."""
    clean = " ".join(text.split())
    if not clean:
        raise ValueError(f"정답 글이 비었어요: {audio_path}")
    return {
        "messages": [
            {"role": "user", "content": "<audio>"},
            {"role": "assistant", "content": f"language {language}<asr_text>{clean}"},
        ],
        "audios": [audio_path],
    }


def load_items(path: Path = SENTENCES_PATH) -> list[dict]:
    """'# 분류' 줄 아래 문장들 → [{category, text(정답·적는 글), speech(TTS 가 읽을 글)}].
    줄이 '적는 글 | 읽는 글'이면 읽는 글을 그대로, 아니면 normalize_for_speech(적는 글)로 읽는다."""
    from app.normalize import normalize_for_speech

    items = []
    for category, line in _raw_lines(path):
        text, _, spoken = (part.strip() for part in line.partition("|"))
        if not text:
            raise ValueError(f"빈 정답 글: {line}")
        items.append({"category": category, "text": text, "speech": spoken or normalize_for_speech(text)})
    return items


def load_sentences(path: Path = SENTENCES_PATH) -> list[tuple[str, str]]:
    """[(분류, 정답 글)]."""
    return [(item["category"], item["text"]) for item in load_items(path)]


def _raw_lines(path: Path) -> list[tuple[str, str]]:
    """'# 분류' 줄 아래 줄들 → [(분류, 줄)]. 첫 분류 전의 '#' 줄은 설명이라 건너뛴다."""
    category = ""
    sentences: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            name = line.lstrip("#").strip()
            # 분류 이름은 짧은 낱말(설명 줄은 길다)
            if name and len(name) <= 12:
                category = name
            continue
        if not category:
            raise ValueError(f"분류 없이 나온 문장: {line}")
        sentences.append((category, line))
    return sentences


def near_test_sentence(sentence: str, test_sentences: list[str], ratio: float = NEAR_DUPLICATE_RATIO) -> str | None:
    """시험표 문장과 거의 같으면 그 시험표 문장을, 아니면 None."""
    mine = compact_question(sentence)
    for test in test_sentences:
        other = compact_question(test)
        if not mine or not other:
            continue
        if mine in other or other in mine:
            # 아주 짧은 말('응')이 긴 문장 안에 들어가는 건 같은 문장이 아니다
            if min(len(mine), len(other)) >= 6:
                return test
            continue
        if _edit_distance(mine, other) / max(len(mine), len(other)) < ratio:
            return test
    return None


def file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def collect_eval_rows(results_dir: Path = RESULTS_DIR) -> list[dict]:
    """시험 저장본 중 소리가 있는 것 → 평가 줄 목록(같은 소리 파일은 처음 것만)."""
    cases = {case["id"]: case for case in TEST_CASES}
    seen: set[str] = set()
    rows: list[dict] = []
    for run_file in sorted(results_dir.glob("*/*.json")):
        run = json.loads(run_file.read_text(encoding="utf-8"))
        audio = run.get("audio") or {}
        results = run.get("results") or {}
        for case_id, relative in sorted(audio.items()):
            case = cases.get(case_id)
            wav = (run_file.parent / str(relative)).resolve()
            # 저장본이 가리키는 파일이 결과 폴더 밖이면 쓰지 않는다
            if case is None or not wav.is_file() or results_dir.resolve() not in wav.parents:
                continue
            digest = file_md5(wav)
            if digest in seen:
                continue
            seen.add(digest)
            result = results.get(case_id) or {}
            rows.append({
                "case": case_id,
                "run": run_file.stem,
                "audio": str(wav),
                "text": reference_text(case, result),
                "verified": bool(str(result.get("spoken", "")).strip()),
                "script": case["say"],
                "recognized": str(result.get("recognized", "")).strip(),
                "stt": str(result.get("stt", "")).strip(),
            })
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_eval(out_dir: Path = OUT_DIR, results_dir: Path = RESULTS_DIR) -> list[dict]:
    rows = collect_eval_rows(results_dir)
    write_jsonl(out_dir / "eval.jsonl", [{**swift_row(r["audio"], r["text"]), "meta": r} for r in rows])
    with (out_dir / "eval_check.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["run", "case", "audio", "script", "recognized", "stt", "actually_said(사람이 들어 보고 고칠 칸)"])
        for r in rows:
            writer.writerow([r["run"], r["case"], r["audio"], r["script"], r["recognized"], r["stt"], r["text"] if r["verified"] else ""])
    return rows


def build_train(audio_dir: Path, out_dir: Path = OUT_DIR, sentences_path: Path = SENTENCES_PATH) -> list[dict]:
    """<audio-dir>/<번호>.wav 또는 <번호>_<이름>.wav(번호는 train_sentences.txt 의 문장 순서, 1부터)를 정답과 짝짓는다."""
    sentences = load_sentences(sentences_path)
    tests = [case["say"] for case in TEST_CASES]
    near = [(text, hit) for _, text in sentences if (hit := near_test_sentence(text, tests))]
    if near:
        raise ValueError("시험표와 거의 같은 학습 문장: " + "; ".join(f"{a} ≈ {b}" for a, b in near))
    rows = []
    for wav in sorted(audio_dir.glob("*.wav")):
        number = wav.stem.split("_", 1)[0]
        if not number.isdigit() or not 1 <= int(number) <= len(sentences):
            continue
        rows.append(swift_row(str(wav.resolve()), sentences[int(number) - 1][1]))
    if not rows:
        raise ValueError(f"{audio_dir} 에 <번호>.wav 소리가 없어요")
    write_jsonl(out_dir / "train.jsonl", rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("eval", help="실기기 녹음으로 평가 세트 만들기")
    train = sub.add_parser("train", help="학습 문장 + 소리로 학습 세트 만들기")
    train.add_argument("--audio-dir", type=Path, required=True)
    sub.add_parser("check", help="학습 문장이 시험표와 겹치지 않는지만 확인")
    args = parser.parse_args(argv)
    if args.command == "eval":
        rows = build_eval()
        verified = sum(r["verified"] for r in rows)
        print(f"평가 녹음 {len(rows)}개(사람 확인 {verified}개) → {OUT_DIR / 'eval.jsonl'}")
    elif args.command == "train":
        rows = build_train(args.audio_dir)
        print(f"학습 줄 {len(rows)}개 → {OUT_DIR / 'train.jsonl'}")
    else:
        sentences = load_sentences()
        tests = [case["say"] for case in TEST_CASES]
        near = [(t, hit) for _, t in sentences if (hit := near_test_sentence(t, tests))]
        for text, hit in near:
            print(f"겹침: {text} ≈ {hit}")
        print(f"학습 문장 {len(sentences)}개, 시험표와 겹침 {len(near)}개")
        return 1 if near else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
