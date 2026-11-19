"""와치 '음성 모으기' 녹음 가져오기와 학습 세트 만들기(2026-11-19). 실제 서버는 부르지 않는다."""

import io
import json
import subprocess
import urllib.error
import wave
import zipfile

import pytest

from finetune.build_dataset import build_collect, load_collect_excludes
from finetune.fetch_collect import CollectError, check_rows, download, read_key, safe_extract, summarize


def wav_bytes(seconds=1.0, rate=16000, channels=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x00" * int(seconds * rate) * channels)
    return buffer.getvalue()


def clip(clip_id, item_id, transcript, speaker="SPK01", day="2026-11-20", item_type="read"):
    return {"clip_id": clip_id, "audio": f"audio/{speaker}/{clip_id}.wav", "item_id": item_id, "item_type": item_type,
            "transcript": transcript, "speaker_code": speaker, "duration_ms": 1000, "recorded_at": f"{day}T10:00:00+09:00"}


def make_folder(tmp_path, clips, audio=None):
    folder = tmp_path / "pack"
    for row in clips:
        path = folder / row["audio"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((audio or {}).get(row["clip_id"], wav_bytes()))
    (folder / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in clips), encoding="utf-8")
    return folder


class FakeResponse:
    def __init__(self, body, headers):
        self._body, self.headers = io.BytesIO(body), headers

    def read(self, size=-1):
        return self._body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_keeps_by_default_and_sends_key_in_header(tmp_path):
    seen = []

    def opener(request, timeout):
        seen.append(request)
        return FakeResponse(b"zipbytes", {"X-Clip-Count": "3"})

    target = tmp_path / "a.zip"
    assert download(target, "k", keep=True, opener=opener) == 3
    assert seen[0].full_url.endswith("?keep=1") and seen[0].get_header("X-stt-key") == "k"
    assert target.read_bytes() == b"zipbytes" and not target.with_suffix(".part").exists()
    download(tmp_path / "b.zip", "k", keep=False, opener=opener)
    assert not seen[1].full_url.endswith("?keep=1")


def test_download_errors(tmp_path):
    def status(code):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, code, "x", {}, io.BytesIO(b""))
        return opener

    assert download(tmp_path / "a.zip", "k", True, opener=status(404)) is None
    for code, word in ((401, "키가 틀렸어요"), (503, "설정")):
        with pytest.raises(CollectError, match=word):
            download(tmp_path / "a.zip", "k", True, opener=status(code))
    assert not list(tmp_path.glob("*.part"))


def test_key_reader_prefers_env_then_keychain(monkeypatch):
    monkeypatch.setenv("STT_COLLECT_KEY", " envkey ")
    assert read_key(run=lambda *a, **k: pytest.fail("키체인을 보면 안 됨")) == "envkey"
    monkeypatch.delenv("STT_COLLECT_KEY")
    assert read_key(run=lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="ck\n", stderr="")) == "ck"
    assert read_key(run=lambda *a, **k: subprocess.CompletedProcess(a, 44, stdout="", stderr="")) == ""


def test_safe_extract_blocks_paths_outside(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../evil.txt", "x")
    with pytest.raises(CollectError):
        safe_extract(bad, tmp_path / "out")
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as archive:
        archive.writestr("manifest.jsonl", "")
    safe_extract(good, tmp_path / "ok")
    assert (tmp_path / "ok" / "manifest.jsonl").exists()


def test_check_rows_finds_format_length_and_missing(tmp_path):
    clips = [clip("c1", "S001", "응"), clip("c2", "S002", "아니"), clip("c3", "S003", "됐어"), clip("c4", "S004", "")]
    folder = make_folder(tmp_path, clips, audio={"c2": wav_bytes(rate=44100), "c3": wav_bytes(seconds=0.2)})
    problems = check_rows(folder, clips)
    assert not any(p.startswith("c1") for p in problems)
    assert any(p.startswith("c2") and "형식" in p for p in problems)
    assert any(p.startswith("c3") and "길이" in p for p in problems)
    assert any(p.startswith("c4") and "빠진 칸" in p for p in problems)
    assert summarize(clips)["by_speaker"] == {"SPK01": 4}


def test_build_collect_skips_excluded_duplicate_and_test_sheet(tmp_path):
    clips = [
        clip("c1", "S100", "관리비 고지서 왔어"),
        clip("c2", "P048", "비서에게 물어보세요", day="2026-11-19", item_type="situation"),  # 제외 목록
        clip("c3", "P010", "이번 달 관리비 냈어?", item_type="situation"),  # 시험표 D4 와 거의 같음
        clip("c1", "S100", "관리비 고지서 왔어"),  # 같은 녹음
    ]
    folder = make_folder(tmp_path, clips[:3])
    (folder / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in clips), encoding="utf-8")
    exclude = tmp_path / "ex.txt"
    exclude.write_text("# 이유\nP048 SPK01 2026-11-19  # 안내 문장 읽음\n", encoding="utf-8")
    rows, skipped = build_collect([folder], tmp_path / "out", exclude)
    assert len(rows) == 1 and rows[0]["messages"][1]["content"].endswith("관리비 고지서 왔어")
    assert any("제외 목록" in s for s in skipped) and any("시험표" in s for s in skipped) and any("같은 녹음" in s for s in skipped)
    assert (tmp_path / "out" / "train.jsonl").exists()


def test_shipped_exclude_list_has_the_three_first_day_clips():
    assert {("P048", "SPK01", "2026-11-19"), ("P049", "SPK01", "2026-11-19"), ("P099", "SPK01", "2026-11-19")} <= load_collect_excludes()


def test_verify_flags_big_differences_and_ignores_number_style(tmp_path):
    from finetune.verify_collect import VERIFY_FILE, flagged_clip_ids, spoken_cer, verify_rows

    assert spoken_cer("오늘 마트에서 8만 4천 원 썼어", "오늘 마트에서 팔만 사천 원 썼어") == 0.0
    clips = [clip("c1", "S001", "콩이 산책 했어?"), clip("c2", "S002", "기저귀 2팩 주문해줘"), clip("c3", "S003", "됐어")]
    folder = make_folder(tmp_path, clips)
    heard = {"c1": "공이 산책 했어?", "c2": "기저귀 이팩 주문해 줘", "c3": ""}
    results = verify_rows(folder, clips, lambda path: heard[path.rsplit("/", 1)[-1][:-4]], threshold=0.15)
    flags = {r["clip_id"]: r["flagged"] for r in results}
    # c1: 짧은 문장의 이름 한 글자(콩이→공이, 1/6)도 걸린다 — 잘못 읽었을 수 있어 사람이 본다
    # c2: 숫자 꼴·띄어쓰기 차이는 안 걸린다 / c3: 받아 적지 못하면 걸린다(무음 녹음이라 앞 잘림은 판단 안 함)
    assert flags == {"c1": True, "c2": False, "c3": True}
    assert results[2]["reasons"] == ["받아 적지 못함"]
    (folder / VERIFY_FILE).write_text(json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8")
    assert flagged_clip_ids(folder) == {"c1", "c3"}


def test_build_collect_drops_clips_flagged_by_verify(tmp_path):
    from finetune.verify_collect import VERIFY_FILE

    clips = [clip("c1", "S100", "관리비 고지서 왔어"), clip("c2", "S101", "콩이 사료 거의 다 먹었어")]
    folder = make_folder(tmp_path, clips)
    (folder / VERIFY_FILE).write_text(json.dumps({"results": [{"clip_id": "c2", "flagged": True}, {"clip_id": "c1", "flagged": False}]}), encoding="utf-8")
    exclude = tmp_path / "ex.txt"
    exclude.write_text("", encoding="utf-8")
    rows, skipped = build_collect([folder], tmp_path / "out", exclude)
    assert len(rows) == 1 and any("맥 STT" in s for s in skipped)


def test_verify_marks_situation_differences_and_clipped_starts(tmp_path):
    import array

    from finetune.verify_collect import lead_silence_ms, verify_rows

    def tone(lead_sec, rate=16000):
        quiet = [0] * int(lead_sec * rate)
        loud = [8000 if i % 2 else -8000 for i in range(rate)]
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(array.array("h", quiet + loud).tobytes())
        return buffer.getvalue()

    clips = [clip("s1", "P001", "빨래 배우자가 있다고 체크해줘", item_type="situation"), clip("r1", "S001", "나중에")]
    folder = make_folder(tmp_path, clips, audio={"s1": tone(0.3), "r1": tone(0.0)})
    assert lead_silence_ms(folder / clips[0]["audio"]) == 300 and lead_silence_ms(folder / clips[1]["audio"]) == 0
    heard = {"s1": "빨래 배우자가 했다고 체크해 줘", "r1": "나중에"}
    results = {r["clip_id"]: r for r in verify_rows(folder, clips, lambda p: heard[p.rsplit("/", 1)[-1][:-4]])}
    assert results["s1"]["reasons"] == ["정답과 다름"]  # 상황 문제는 한 글자만 달라도 사람이 듣는다
    assert results["r1"]["reasons"] == ["앞 잘림 의심"]

