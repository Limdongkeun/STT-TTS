import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.reading_samples import KST, ReadingResults, load_reading_samples, render_reading_results, save_reading_results
from tests.test_api import make_settings

NOW = datetime(2026, 11, 12, 10, 30, 5, tzinfo=KST)


def test_samples_load_with_readings():
    samples = load_reading_samples()
    assert len(samples) >= 20
    assert len({sample["id"] for sample in samples}) == len(samples)
    by_id = {sample["id"]: sample for sample in samples}
    assert by_id["N14"]["reading"] == "소윤이 체온은 삼십팔 점 오도예요."
    # 읽기 글에는 아라비아 숫자가 남지 않는다
    assert all(not any(char.isdigit() for char in sample["reading"]) for sample in samples)


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([{"id": "N1", "group": "날짜", "text": "1일"}, {"id": "N1", "group": "날짜", "text": "2일"}], "두 번"),
        ([{"id": "N1", "group": "날짜", "text": "  "}], "비었어요"),
    ],
)
def test_samples_reject_bad_file(tmp_path, items, message):
    path = tmp_path / "samples.json"
    path.write_text(json.dumps({"samples": items}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_reading_samples(path)


def test_render_counts_and_keeps_unheard_rows():
    samples = load_reading_samples()[:3]
    results = ReadingResults(tts="107 G", marks={"N1": {"heard": "○"}, "N2": {"heard": "×", "memo": "일 일로 읽음 | 끊김"}})
    text = render_reading_results(samples, results, "ios-27-0-1", NOW, "abc1234")
    assert text.startswith("# 숫자 읽기 시험 — ios-27-0-1 · 2026-11-12 10:30 · 107 G · abc1234")
    assert "○ 1 · × 1 · 안 들음 1 (모두 3)" in text
    assert "일 일로 읽음 \\| 끊김" in text  # 표가 깨지지 않게 | 를 막는다
    assert f"| {samples[2]['id']} |" in text  # 안 들은 줄도 남는다


def test_save_writes_file(tmp_path):
    samples = load_reading_samples()
    saved = save_reading_results(samples, ReadingResults(marks={"N1": {"heard": "○"}}), "ios-27-0-1", tmp_path, NOW)
    path = tmp_path / "ios-27-0-1" / "2026-11-12_103005.md"
    assert path.exists()
    assert saved["ok"] == 1 and saved["bad"] == 0


@pytest.mark.parametrize(
    ("marks", "message"),
    [({"N999": {"heard": "○"}}, "없는 문장"), ({}, "하나도")],
)
def test_save_rejects_unknown_or_empty(tmp_path, marks, message):
    with pytest.raises(ValueError, match=message):
        save_reading_results(load_reading_samples(), ReadingResults(marks=marks), "ios-27-0-1", tmp_path, NOW)


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(make_settings(test_results_dir=str(tmp_path))))


def test_api_lists_samples(client):
    samples = client.get("/reading-samples").json()["samples"]
    assert samples[0].keys() == {"id", "group", "text", "reading"}


def test_api_saves_results(client, tmp_path):
    response = client.post("/reading-results/ios-27-0-1", json={"tts": "107 G", "marks": {"N2": {"heard": "×", "memo": "일 일"}}})
    assert response.status_code == 200
    assert response.json()["bad"] == 1
    assert len(list((tmp_path / "number-reading" / "ios-27-0-1").glob("*.md"))) == 1


@pytest.mark.parametrize(
    ("device", "body", "status"),
    [
        ("../etc", {"marks": {"N1": {"heard": "○"}}}, 404),  # 경로로 못 나간다(라우트가 안 맞음)
        ("BAD NAME", {"marks": {"N1": {"heard": "○"}}}, 422),
        ("ios-27-0-1", {"marks": {"N1": {"heard": "?"}}}, 422),
        ("ios-27-0-1", {"marks": {"N999": {"heard": "○"}}}, 400),
        ("ios-27-0-1", {"marks": {}}, 400),
    ],
)
def test_api_rejects_bad_requests(client, device, body, status):
    assert client.post(f"/reading-results/{device}", json=body).status_code == status
