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
# 상황만 보여 주고 자기 말로 말하게 하는 녹음 문제(2026-11-18). 정답은 녹음한 사람이 고친 글이다.
PROMPTS_PATH = Path(__file__).resolve().parent / "situation_prompts.txt"
# 와치 음성 모으기 녹음 중 학습에서 뺄 것(2026-11-19)
COLLECT_EXCLUDE_PATH = Path(__file__).resolve().parent / "collect_exclude.txt"
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


def load_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    """'상황 보고 자기 말로' 문제 → [{id(P001…, 파일 순서), category, prompt}]. 앱 녹음 화면이 id 로 녹음과 짝짓는다."""
    return [
        {"id": f"P{number:03d}", "category": category, "prompt": line}
        for number, (category, line) in enumerate(_raw_lines(path), start=1)
    ]


SHORT_CATEGORIES = ("짧은 말", "짧은 대답")


# 녹음 문제 목록 버전. 문장을 더하면 올린다(이미 받은 녹음은 그때 버전·id 로 남는다).
# 2026-11-20: '약한 낱말' S790~ 추가(사용자 결정). 기존 id 는 그대로.
ITEMS_VERSION = "2026-11-20"


def recording_items(sentences_path: Path = SENTENCES_PATH, prompts_path: Path = PROMPTS_PATH) -> list[dict]:
    """앱 '녹음 모으기'에 넘길 문제 목록(2026-11-18, ProjectWatch 앱 연결용).
    읽기 문장 id 는 S + train_sentences 순서(1부터, 녹음 파일 <번호>_<사람>.wav 의 번호와 같다), 상황 문제는 P + 순서."""
    items = []
    for number, (category, text) in enumerate(load_sentences(sentences_path), start=1):
        kind = "short" if category in SHORT_CATEGORIES else "read"
        items.append({"id": f"S{number:03d}", "type": kind, "category": category, "text": text})
    for prompt in load_prompts(prompts_path):
        items.append({"id": prompt["id"], "type": "situation", "category": prompt["category"], "prompt": prompt["prompt"]})
    return items


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


def load_collect_excludes(path: Path = COLLECT_EXCLUDE_PATH) -> set[tuple[str, str, str]]:
    """{(문제 id, 사람 코드, 날짜)}. '#' 뒤는 이유(무시)."""
    excludes = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].split()
        if not line:
            continue
        if len(line) != 3:
            raise ValueError(f"제외 줄 모양이 이상해요(문제 id, 사람, 날짜): {raw}")
        excludes.add((line[0], line[1], line[2]))
    return excludes


def collect_decisions(folders: list[Path], exclude_path: Path = COLLECT_EXCLUDE_PATH) -> list[tuple[dict, str, Path]]:
    """녹음마다 (manifest 줄, 뺀 이유 — 학습에 쓰면 빈 글, 소리 경로). build_collect 와 어드민 요약이 같은 판정을 쓴다.
    빼는 것: 제외 목록, 같은 녹음(clip_id) 두 번째, 정답이 시험표 문장과 거의 같은 것(평가가 부풀지 않게),
    맥 STT 검사(verify.json)에서 정답과 크게 달랐던 것."""
    from finetune.verify_collect import flagged_clip_ids

    excludes = load_collect_excludes(exclude_path)
    tests = [case["say"] for case in TEST_CASES]
    decisions, seen = [], set()
    for folder in folders:
        flagged = flagged_clip_ids(folder)
        for line in (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            clip = json.loads(line)
            clip_id = str(clip.get("clip_id", ""))
            day = str(clip.get("recorded_at", ""))[:10]
            text = str(clip.get("transcript", "")).strip()
            audio = (folder / str(clip.get("audio", ""))).resolve()
            reason = ""
            if clip_id in seen:
                reason = "같은 녹음"
            elif (clip.get("item_id"), clip.get("speaker_code"), day) in excludes:
                reason = "제외 목록"
            elif not text:
                reason = "정답 글 없음"
            elif clip_id in flagged:
                reason = "맥 STT 검사에서 걸림(verify.json)"
            elif folder.resolve() not in audio.parents or not audio.is_file():
                reason = "소리 파일 없음"
            elif hit := near_test_sentence(text, tests):
                reason = f"시험표와 비슷함({hit})"
            if not reason:
                seen.add(clip_id)
            decisions.append((clip, reason, audio))
    return decisions


def build_collect(folders: list[Path], out_dir: Path = OUT_DIR, exclude_path: Path = COLLECT_EXCLUDE_PATH) -> tuple[list[dict], list[str]]:
    """와치 음성 모으기 zip 을 푼 폴더들(manifest.jsonl) → 학습 줄. 정답은 manifest 의 transcript."""
    rows, skipped = [], []
    for clip, reason, audio in collect_decisions(folders, exclude_path):
        if reason:
            skipped.append(f"{clip.get('item_id')} {clip.get('speaker_code')} {str(clip.get('clip_id', ''))[:8]}: {reason}")
        else:
            rows.append(swift_row(str(audio), str(clip.get("transcript", "")).strip()))
    if rows:
        write_jsonl(out_dir / "train.jsonl", rows)
    return rows, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("eval", help="실기기 녹음으로 평가 세트 만들기")
    train = sub.add_parser("train", help="학습 문장 + 소리로 학습 세트 만들기")
    train.add_argument("--audio-dir", type=Path, required=True)
    sub.add_parser("check", help="학습 문장이 시험표와 겹치지 않는지만 확인")
    collect = sub.add_parser("collect", help="와치 음성 모으기 녹음(푼 폴더)으로 학습 세트 만들기")
    collect.add_argument("folders", type=Path, nargs="+")
    export = sub.add_parser("items", help="앱 녹음 모으기용 문제 목록 JSON 쓰기")
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "eval":
        rows = build_eval()
        verified = sum(r["verified"] for r in rows)
        print(f"평가 녹음 {len(rows)}개(사람 확인 {verified}개) → {OUT_DIR / 'eval.jsonl'}")
    elif args.command == "collect":
        rows, skipped = build_collect(args.folders)
        for line in skipped:
            print("뺌:", line)
        print(f"학습 줄 {len(rows)}개, 뺀 것 {len(skipped)}개" + (f" → {OUT_DIR / 'train.jsonl'}" if rows else ""))
    elif args.command == "items":
        items = recording_items()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"version": ITEMS_VERSION, "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        kinds = {kind: sum(item["type"] == kind for item in items) for kind in ("read", "short", "situation")}
        print(f"문제 {len(items)}개 {kinds} → {args.out}")
    elif args.command == "train":
        rows = build_train(args.audio_dir)
        print(f"학습 줄 {len(rows)}개 → {OUT_DIR / 'train.jsonl'}")
    else:
        sentences = load_sentences()
        tests = [case["say"] for case in TEST_CASES]
        near = [(t, hit) for _, t in sentences if (hit := near_test_sentence(t, tests))]
        for text, hit in near:
            print(f"겹침: {text} ≈ {hit}")
        print(f"학습 문장 {len(sentences)}개, 시험표와 겹침 {len(near)}개, 상황 문제 {len(load_prompts())}개")
        return 1 if near else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
