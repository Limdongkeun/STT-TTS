"""실기기 시험표 (app/test_sheet.py, /test-cases, /test-sheet)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.family_demo import KST, FamilyDemoAnswerProvider
from app.main import create_app
from app.test_sheet import (
    TEST_CASES,
    SheetResult,
    SheetStore,
    case_state,
    is_valid_device,
    read_code_version,
    render_markdown,
    char_error_rate,
    stt_labels,
    summarize,
    tts_label_for,
)
from tests.test_api import make_settings

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=KST)  # 기대 답을 적은 날(목요일)
DEVICE = "ios-27-0-1"
LATER = datetime(2026, 11, 5, 14, 0, tzinfo=KST)


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(make_settings(answer_provider="family-demo", test_results_dir=str(tmp_path))))


def test_case_list_is_complete_and_unique():
    ids = [case["id"] for case in TEST_CASES]
    assert ids == [f"C{n}" for n in range(1, 8)] + [f"D{n}" for n in range(1, 26)] + ["E1", "E2"]
    assert all("who" not in case for case in TEST_CASES)  # '나' 역할 없음


def test_expected_answers_match_server_when_spoken_in_order():
    """시험표의 기대 답이 실제 서버 답과 같은지: 표 순서대로 말한다(2026-11-05 10:00 기준, 역할 없음)."""
    provider = FamilyDemoAnswerProvider()
    context = None
    for case in TEST_CASES:
        answer, context = provider.answer(case["say"], context, now=NOW)
        if case["id"] == "C4":
            assert answer.startswith("시험 기록에 11월 5일 오전 9시 30분에 먹인 걸로 기록했어요."), answer
        elif case["id"] == "C5":
            assert answer.startswith("시험 기록에 11월 5일 오전 9시에 먹인 걸로 수정했어요."), answer
        else:
            assert answer == case["expect"], f"{case['id']}: {answer}"


def done(mark: str = "o", **extra) -> dict:
    return {"recognized": "말한 글", "key": mark, "screen": "o", "heard": "o", **extra}


@pytest.mark.parametrize(
    ("device", "valid"),
    [
        (DEVICE, True),
        ("android-35", True),
        ("IOS", False),
        ("../ios", False),
        ("ios/../../x", False),
        ("", False),
        ("a" * 41, False),
    ],
)
def test_device_validation(device, valid):
    assert is_valid_device(device) is valid


def test_get_cases(client):
    body = client.get("/test-cases").json()
    assert len(body["cases"]) == 34
    assert body["cases"][13]["id"] == "D7"
    assert body["cases"][3]["dateDependent"] is True


def test_draft_save_read_and_clear(client, tmp_path):
    payload = {"recognized": "소윤이 이번 주 학교 | 학원 일정", "answer": "소윤이는 …", "screen": "o", "key": "x", "speaker": "wife"}
    saved = client.put(f"/test-sheet/{DEVICE}/draft/C2", json=payload)
    assert saved.status_code == 200
    assert saved.json()["updatedAt"]
    body = client.get(f"/test-sheet/{DEVICE}/draft").json()
    assert body["results"]["C2"]["recognized"] == payload["recognized"]
    assert (tmp_path / DEVICE / "draft.json").exists()

    assert client.delete(f"/test-sheet/{DEVICE}/draft").json() == {"status": "cleared"}
    assert client.get(f"/test-sheet/{DEVICE}/draft").json()["results"] == {}


def test_save_attempt_needs_something_recorded(client):
    response = client.post(f"/test-sheet/{DEVICE}/attempts")
    assert response.status_code == 400
    assert "저장할 시험 결과가 없어요" in response.json()["detail"]


def test_attempts_round_trip_and_compare(client, tmp_path):
    client.put(f"/test-sheet/{DEVICE}/draft/D1", json=done("x"))
    client.put(f"/test-sheet/{DEVICE}/draft/D2", json=done("o"))
    first = client.post(f"/test-sheet/{DEVICE}/attempts")
    assert first.status_code == 200
    assert first.json()["badCases"] == ["D1"]
    assert isinstance(first.json()["version"], str)

    client.delete(f"/test-sheet/{DEVICE}/draft")
    client.put(f"/test-sheet/{DEVICE}/draft/D1", json=done("o"))
    client.put(f"/test-sheet/{DEVICE}/draft/D2", json=done("x"))
    second = client.post(f"/test-sheet/{DEVICE}/attempts").json()
    assert second["improved"] == ["D1"]
    assert second["worsened"] == ["D2"]

    attempts = client.get(f"/test-sheet/{DEVICE}/attempts").json()["attempts"]
    assert [a["badCases"] for a in attempts] == [["D2"], ["D1"]]  # 최신이 먼저
    history = (tmp_path / DEVICE / "history.md").read_text(encoding="utf-8")
    assert history.count("\n| 20") == 2
    assert "×→○ D1 / ○→× D2" in history
    assert len(list((tmp_path / DEVICE).glob("*.md"))) == 3  # 저장본 2개 + history


def test_store_snapshot_contents_and_same_second(tmp_path):
    store = SheetStore(tmp_path, code_version=lambda: "abc1234 (수정 중)")
    store.save_draft_case(DEVICE, "C1", SheetResult(**done("o")))
    first = store.save_attempt(DEVICE, now=LATER)
    second = store.save_attempt(DEVICE, now=LATER)  # 같은 초에 두 번 → 파일 이름이 겹치지 않음
    assert first["file"] == "2026-11-05_140000.json"
    assert second["file"] == "2026-11-05_140000_02.json"
    assert [a["file"] for a in store.list_attempts(DEVICE)] == ["2026-11-05_140000_02.json", "2026-11-05_140000.json"]
    assert first["version"] == "abc1234 (수정 중)"
    assert (first["done"], first["total"], first["okMarks"]) == (1, 34, 3)
    markdown = (tmp_path / DEVICE / "2026-11-05_140000.md").read_text(encoding="utf-8")
    assert markdown.startswith("# 음성 시험 결과 — ios-27-0-1 · 2026-11-05 14:00 · STT STT 모름 · TTS 모름 · abc1234 (수정 중)")


def test_legacy_run_file_becomes_starting_draft(tmp_path):
    (tmp_path / "2026-11-04-ios-27-0-1.json").write_text('{"C1": {"recognized": "옛날"}}', encoding="utf-8")
    (tmp_path / "2026-11-05-ios-27-0-1.json").write_text('{"C1": {"recognized": "오늘"}}', encoding="utf-8")
    (tmp_path / "2026-11-05-android-35.json").write_text('{"C1": {"recognized": "다른 기기"}}', encoding="utf-8")
    store = SheetStore(tmp_path, code_version=lambda: "")
    assert store.load_draft(DEVICE)["C1"]["recognized"] == "오늘"
    store.clear_draft(DEVICE)
    assert store.load_draft(DEVICE) == {}  # 초기화하면 예전 기록을 다시 불러오지 않는다
    assert (tmp_path / "2026-11-05-ios-27-0-1.json").exists()  # 예전 파일은 지우지 않는다


@pytest.mark.parametrize(
    ("result", "state"),
    [(None, ""), ({}, ""), (done("o"), "good"), (done("x"), "bad"), ({"key": "x"}, "bad"), ({"recognized": "a", "key": "o"}, "")],
)
def test_case_state(result, state):
    assert case_state(result) == state


def test_summarize_without_previous_has_no_changes():
    summary = summarize({"D1": done("x")}, None)
    assert (summary["bad_cases"], summary["improved"], summary["worsened"]) == (["D1"], [], [])


def test_read_code_version_outside_git(tmp_path):
    assert read_code_version(tmp_path) == ""


@pytest.mark.parametrize(
    ("method", "path", "payload", "status"),
    [
        ("put", "/test-sheet/BAD/draft/C1", {}, 422),
        ("put", f"/test-sheet/{DEVICE}/draft/D99", {}, 404),
        ("put", f"/test-sheet/{DEVICE}/draft/C1", {"key": "y"}, 422),
        ("put", f"/test-sheet/{DEVICE}/draft/C1", {"recognized": "가" * 501}, 422),
        ("put", f"/test-sheet/{DEVICE}/draft/C1", {"speaker": "grandma"}, 422),
        ("get", "/test-sheet/IOS/draft", None, 422),
        ("delete", "/test-sheet/IOS/draft", None, 422),
        ("post", "/test-sheet/IOS/attempts", None, 422),
        ("get", "/test-sheet/IOS/attempts", None, 422),
    ],
)
def test_rejects_bad_input(client, method, path, payload, status):
    kwargs = {"json": payload} if payload is not None else {}
    assert getattr(client, method)(path, **kwargs).status_code == status


def test_markdown_lists_every_case_even_without_results():
    markdown = render_markdown(DEVICE, {})
    assert markdown.count("\n| C") == 7
    assert markdown.count("\n| D") == 25


def test_attempts_compare_only_with_same_stt(tmp_path):
    """폰 STT 저장본과 서버 모델 저장본은 서로 비교하지 않는다."""
    store = SheetStore(tmp_path, code_version=lambda: "v1")
    phone = {"stt": "폰 기본 STT"}
    model = {"stt": "Qwen3-ASR-1.7B"}

    store.save_draft_case(DEVICE, "D1", SheetResult(**done("x", **phone)))
    first_phone = store.save_attempt(DEVICE, now=LATER, tts_label="mock")
    assert (first_phone["sttLabels"], first_phone["tts"], first_phone["comparedWith"]) == (["폰 기본 STT"], "mock", "")

    store.clear_draft(DEVICE)
    store.save_draft_case(DEVICE, "D1", SheetResult(**done("o", **model)))
    first_model = store.save_attempt(DEVICE, now=LATER.replace(hour=15), tts_label="mock")
    assert first_model["comparedWith"] == ""  # 서버 모델의 첫 저장본: 폰 STT 저장본과 비교하지 않음
    assert first_model["improved"] == []

    store.clear_draft(DEVICE)
    store.save_draft_case(DEVICE, "D1", SheetResult(**done("o", **phone)))
    second_phone = store.save_attempt(DEVICE, now=LATER.replace(hour=16), tts_label="mock")
    assert second_phone["comparedWith"] == first_phone["file"]
    assert second_phone["improved"] == ["D1"]

    history = (tmp_path / DEVICE / "history.md").read_text(encoding="utf-8")
    # TTS 가 mock 이라 '들린 답'은 세지 않는다: ○ 는 핵심·화면 2개
    assert "| 2026-11-05 15:00 | Qwen3-ASR-1.7B | mock | v1 | - | 0% | - | 1/34 | 2 | - | 같은 STT 첫 저장본 |" in history
    assert "| 2026-11-05 16:00 | 폰 기본 STT | mock | v1 | - | 0% | - | 1/34 | 2 | - | ×→○ D1 |" in history


def test_stt_labels_and_tts_label():
    results = {"C1": {"stt": "폰 기본 STT"}, "C2": {"stt": "Qwen3-ASR-1.7B"}, "C3": {"stt": "폰 기본 STT"}, "C4": {}}
    assert stt_labels(results) == ["폰 기본 STT", "Qwen3-ASR-1.7B"]
    assert stt_labels({}) == []
    assert tts_label_for("mock", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice") == "mock"
    assert tts_label_for("qwen3-tts", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice") == "Qwen3-TTS-12Hz-0.6B-CustomVoice"


def test_api_attempt_records_server_tts(tmp_path):
    settings = make_settings(answer_provider="family-demo", test_results_dir=str(tmp_path))
    client = TestClient(create_app(settings))
    client.put(f"/test-sheet/{DEVICE}/draft/C1", json=done("o", stt="폰 기본 STT"))
    attempt = client.post(f"/test-sheet/{DEVICE}/attempts").json()
    assert (attempt["sttLabels"], attempt["tts"]) == (["폰 기본 STT"], "mock")
    assert client.put(f"/test-sheet/{DEVICE}/draft/C1", json={"stt": "가" * 121}).status_code == 422


# ── 인식 정확도(CER) · mock TTS 의 '들린 답' ─────────────────────


@pytest.mark.parametrize(
    ("reference", "hypothesis", "cer"),
    [
        ("소윤이 이번 주 학교 학원 일정 뭐야?", "소윤이 이번 주 학교 학원 일정 뭐야", 0.0),  # 띄어쓰기·문장부호 무시
        ("소윤이 이번 주 학교 학원 일정 뭐야?", "수연이 이번 주 학교 일정 뭐야?", 4 / 14),  # 14글자 중 바꿈 2 + 빠짐 2
        ("가스비 내가 냈어", "코스피 대가 됐어", 4 / 7),
        ("장보기 목록 뭐 남았어?", "", None),  # 인식한 말이 없으면 계산 안 함
        ("", "아무 말", None),
    ],
)
def test_char_error_rate(reference, hypothesis, cer):
    result = char_error_rate(reference, hypothesis)
    assert result == pytest.approx(cer) if cer is not None else result is None


def test_summary_average_cer_and_mock_tts_skips_heard():
    say_c1 = TEST_CASES[0]["say"]
    results = {
        "C1": {"recognized": say_c1, "key": "o", "screen": "o", "heard": ""},
        "C2": {"recognized": "수연이 이번 주 학교 일정 뭐야?", "key": "x", "screen": "x", "heard": ""},
    }
    with_heard = summarize(results, None, require_heard=True)
    without_heard = summarize(results, None, require_heard=False)
    assert with_heard["done"] == 0  # 들린 답이 비어 끝나지 않음
    assert without_heard["done"] == 2
    assert without_heard["cer"] == pytest.approx(round((0 + 4 / 14) / 2, 3))
    assert without_heard["cer_cases"] == 2
    assert summarize({}, None)["cer"] is None


def test_history_starts_new_table_when_columns_change(tmp_path):
    folder = tmp_path / DEVICE
    folder.mkdir()
    old = "# 시험 저장본 — ios-27-0-1\n\n| 저장 시각 | STT | TTS | 코드 버전 | 끝낸 문장 |\n|---|---|---|---|---|\n| 옛 줄 |\n"
    (folder / "history.md").write_text(old, encoding="utf-8")
    store = SheetStore(tmp_path, code_version=lambda: "v2")
    store.save_draft_case(DEVICE, "C1", SheetResult(recognized=TEST_CASES[0]["say"], key="o", screen="o"))
    store.save_attempt(DEVICE, now=LATER, tts_label="mock")
    history = (folder / "history.md").read_text(encoding="utf-8")
    assert history.startswith(old.rstrip("\n"))  # 예전 줄은 그대로
    assert "| 인식 정확도(평균) |" in history
    assert "| 2026-11-05 14:00 | STT 모름 | mock | v2 | - | 100% | - | 1/34 | 2 | - | 같은 STT 첫 저장본 |" in history
    markdown = (folder / "2026-11-05_140000.md").read_text(encoding="utf-8")
    assert "| C1 | 다음 주 우리 집 일정 뭐야? | 다음 주 우리 집 일정 뭐야? | 100% |" in markdown


def test_no_recording_heard_counts_as_done_and_shows_label():
    say_d1 = next(case["say"] for case in TEST_CASES if case["id"] == "D1")
    result = {"recognized": say_d1, "key": "o", "screen": "o", "heard": "-"}
    assert summarize({"D1": result}, None)["done"] == 1
    assert summarize({"D1": result}, None)["bad_cases"] == []
    assert "| 녹음 없음 |" in render_markdown("t", {"D1": result})
    assert SheetResult(heard="-").heard == "-"
    with pytest.raises(ValueError):
        SheetResult(key="-")


def _wav(seconds: float = 0.1) -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\0\0" * int(16000 * seconds))
    return buffer.getvalue()


def test_condition_and_timings_round_trip_and_summary(client, tmp_path):
    body = {"recognized": "장보기 목록 뭐 남았어", "key": "o", "screen": "o", "heard": "o",
            "condition": "tv", "askMs": 40, "ttsMs": 120, "replyMs": 1800}
    assert client.put(f"/test-sheet/{DEVICE}/draft/D1", json=body).status_code == 200
    client.put(f"/test-sheet/{DEVICE}/draft/D4", json={**body, "replyMs": 2200, "condition": "quiet"})
    saved = client.get(f"/test-sheet/{DEVICE}/draft").json()["results"]["D1"]
    assert (saved["condition"], saved["askMs"], saved["ttsMs"], saved["replyMs"]) == ("tv", 40, 120, 1800)
    attempt = client.post(f"/test-sheet/{DEVICE}/attempts").json()
    assert attempt["avgReplyMs"] == 2000
    assert attempt["conditions"] == ["tv", "quiet"]  # 시험 문장 순서(D1 → D4)로 처음 나온 순
    folder = tmp_path / DEVICE
    markdown = next(folder.glob("2*.md")).read_text(encoding="utf-8")
    assert "- 환경: TV 소음 + 조용함 · 말 끝→소리 평균 2.0초" in markdown
    assert "| TV 소음 | 1.8초 |" in markdown
    history = (folder / "history.md").read_text(encoding="utf-8")
    # D4 는 다른 문장을 적어 정확도가 낮다
    assert "| TV 소음 + 조용함 | 50% | 2.0초 |" in history


@pytest.mark.parametrize("patch", [
    {"condition": "kitchen"}, {"replyMs": -1}, {"askMs": 600_001}, {"audioFile": "../x.wav"}, {"audioFile": "D1_1.mp3"},
])
def test_rejects_bad_condition_timing_and_audio_name(client, patch):
    assert client.put(f"/test-sheet/{DEVICE}/draft/D1", json=patch).status_code == 422


def test_audio_upload_is_copied_into_attempt_and_cleared_with_draft(client, tmp_path):
    response = client.put(f"/test-sheet/{DEVICE}/draft/D1/audio", files={"audio": ("a.wav", _wav(), "audio/wav")})
    assert response.status_code == 200
    name = response.json()["audioFile"]
    assert name.startswith("D1_") and name.endswith(".wav")
    client.put(f"/test-sheet/{DEVICE}/draft/D1", json={"recognized": "장보기", "audioFile": name})
    # 시험표에 적히지 않은 파일(지난 턴 소리)은 저장본으로 옮기지 않는다
    stale = client.put(f"/test-sheet/{DEVICE}/draft/D4/audio", files={"audio": ("b.wav", _wav(), "audio/wav")})
    assert stale.status_code == 200
    attempt = client.post(f"/test-sheet/{DEVICE}/attempts").json()
    assert attempt["audioCount"] == 1
    stem = attempt["file"].removesuffix(".json")
    copied = tmp_path / DEVICE / f"{stem}-audio" / "D1.wav"
    assert copied.read_bytes() == _wav()
    assert not (tmp_path / DEVICE / f"{stem}-audio" / "D4.wav").exists()
    assert f"`{stem}-audio/`" in (tmp_path / DEVICE / f"{stem}.md").read_text(encoding="utf-8")
    client.delete(f"/test-sheet/{DEVICE}/draft")
    assert not (tmp_path / DEVICE / "draft-audio").exists()
    assert copied.exists()  # 저장본 소리는 남는다


def test_audio_upload_rejects_bad_input(client):
    url = f"/test-sheet/{DEVICE}/draft/D1/audio"
    assert client.put(url, files={"audio": ("a.mp3", b"ID3notwav", "audio/mpeg")}).status_code == 415
    assert client.put(url, files={"audio": ("a.wav", b"", "audio/wav")}).status_code == 400
    assert client.put(f"/test-sheet/{DEVICE}/draft/Z9/audio", files={"audio": ("a.wav", _wav(), "audio/wav")}).status_code == 404
    assert client.put(f"/test-sheet/BAD!/draft/D1/audio", files={"audio": ("a.wav", _wav(), "audio/wav")}).status_code == 422


def test_audio_upload_size_limit(client, monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "MAX_SHEET_AUDIO_BYTES", 1000)
    response = client.put(f"/test-sheet/{DEVICE}/draft/D1/audio", files={"audio": ("a.wav", _wav(1.0), "audio/wav")})
    assert response.status_code == 413


def test_spoken_sentence_is_the_reference_for_accuracy(client, tmp_path):
    # 대본과 다르게 말했으면 실제로 말한 문장과 비교한다(대본과 비교하면 STT가 맞게 적어도 깎인다).
    body = {"recognized": "장볼거리 뭐야", "spoken": "장볼거리 뭐야?", "key": "o", "screen": "o", "heard": "o"}
    assert client.put(f"/test-sheet/{DEVICE}/draft/D1", json=body).status_code == 200
    attempt = client.post(f"/test-sheet/{DEVICE}/attempts").json()
    assert attempt["avgCer"] == 0.0
    markdown = next((tmp_path / DEVICE).glob("2*.md")).read_text(encoding="utf-8")
    assert "- 바꿔 말한 문장 1개(✎): 인식 정확도는 실제로 말한 문장과 비교" in markdown
    assert "| D1 | ✎ 장볼거리 뭐야? | 장볼거리 뭐야 | 100% |" in markdown


def test_summary_counts_spoken_and_falls_back_to_script():
    results = {"D1": {"recognized": "장보기 목록 뭐 남았어", "spoken": "  "}}
    summary = summarize(results, None)
    assert summary["spoken_count"] == 0
    assert summary["cer"] == 0.0


def test_markdown_shows_corrected_text_only_when_it_differs():
    results = {
        "C2": {"recognized": "수연이 이번 주 학교 일정", "corrected": "소윤이이번주학교일정"},
        "D1": {"recognized": "장보기 목록 뭐 남았어", "corrected": "장보기목록뭐남았어"},
    }
    text = render_markdown("t", results)
    assert "수연이 이번 주 학교 일정 → 보정: 소윤이이번주학교일정" in text
    assert "장보기 목록 뭐 남았어 → 보정" not in text


@pytest.mark.parametrize("patch", [{"spoken": "가" * 201}, {"corrected": "가" * 501}])
def test_rejects_too_long_spoken_or_corrected(client, patch):
    assert client.put(f"/test-sheet/{DEVICE}/draft/D1", json=patch).status_code == 422


def test_attempt_tts_label_comes_from_turns(tmp_path):
    """앱에서 턴마다 고른 TTS 이름이 있으면 서버 기본 이름 대신 그걸 적는다."""
    store = SheetStore(tmp_path, code_version=lambda: "v1")
    store.save_draft_case(DEVICE, "D1", SheetResult(**done("o", stt="폰 기본 STT", tts="107 Qwen3-TTS · G 목소리")))
    store.save_draft_case(DEVICE, "D2", SheetResult(**done("o", stt="폰 기본 STT", tts="107 Qwen3-TTS · G 목소리")))
    attempt = store.save_attempt(DEVICE, now=LATER, tts_label="JISOO 사전 녹음 (C1~C7·D1~D25)")
    assert attempt["tts"] == "107 Qwen3-TTS · G 목소리"

    store.clear_draft(DEVICE)
    store.save_draft_case(DEVICE, "D1", SheetResult(**done("o", stt="폰 기본 STT")))
    assert store.save_attempt(DEVICE, now=LATER.replace(hour=16), tts_label="mock")["tts"] == "mock"
