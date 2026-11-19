"""구글 Chirp 3 STT(2026-11-18 사용자 결정)와 그 로그인(사용자 OAuth). 실제 구글은 부르지 않는다."""

import io
import json
import subprocess
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.engines.google_stt import API, GoogleSttEngine, GoogleSttError, transcript_of
from app.google_auth import GoogleAuthError, TokenSource, client_info, read_refresh_token
from app.main import create_app
from app.settings import load_settings, stt_choices
from tests.test_api import make_settings

CLIENT = {"client_id": "cid", "client_secret": "csecret", "project_id": "proj-1"}


def tokens(post_form=None, refresh="r1", clock=lambda: 1000.0):
    return TokenSource(client=lambda: CLIENT, refresh_reader=lambda: refresh,
                       post_form=post_form or (lambda url, fields: {"access_token": "at", "expires_in": 3600}), clock=clock)


def test_engine_sends_chirp3_korean_with_bearer_and_quota_project(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    calls = []

    def post(url, body, headers):
        calls.append((url, json.loads(body), headers))
        return json.dumps({"results": [{"alternatives": [{"transcript": "가스비 42,000원"}]},
                                       {"alternatives": [{"transcript": " 언제까지야?"}]}]}).encode()

    result = GoogleSttEngine("google-chirp3", tokens=tokens(), post=post).transcribe(wav)
    url, body, headers = calls[0]
    assert url == API.format(project="proj-1") and url.startswith("https://us-speech.googleapis.com/v2/")
    assert body["config"] == {"autoDecodingConfig": {}, "languageCodes": ["ko-KR"], "model": "chirp_3"}
    assert headers["Authorization"] == "Bearer at" and headers["x-goog-user-project"] == "proj-1"
    assert result.text == "가스비 42,000원 언제까지야?" and result.language == "ko-KR"


def test_transcript_of_handles_empty_and_missing():
    assert transcript_of({}) == ""
    assert transcript_of({"results": [{"alternatives": []}, {}]}) == ""


def test_engine_errors_become_google_stt_error(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")

    def refused(url, body, headers):
        raise urllib.error.HTTPError(url, 403, "no", {}, io.BytesIO(b'{"error":"SERVICE_DISABLED"}'))

    with pytest.raises(GoogleSttError, match="403"):
        GoogleSttEngine("google-chirp3", tokens=tokens(), post=refused).transcribe(wav)
    with pytest.raises(GoogleSttError, match="로그인"):
        GoogleSttEngine("google-chirp3", tokens=tokens(refresh=""), post=lambda *a: b"{}").transcribe(wav)
    with pytest.raises(GoogleSttError):
        GoogleSttEngine("google-chirp3", tokens=tokens(), post=lambda *a: b"not json").transcribe(wav)
    big = tmp_path / "big.wav"
    big.write_bytes(b"\0" * (8 * 1024 * 1024))
    with pytest.raises(GoogleSttError, match="너무 길어요"):
        GoogleSttEngine("google-chirp3", tokens=tokens(), post=lambda *a: b"{}").transcribe(big)


def test_token_is_reused_until_near_expiry_then_refreshed():
    now = [1000.0]
    calls = []

    def post_form(url, fields):
        calls.append(fields)
        return {"access_token": f"at{len(calls)}", "expires_in": 3600}

    source = tokens(post_form=post_form, clock=lambda: now[0])
    assert source.access_token() == "at1"
    assert source.access_token() == "at1" and len(calls) == 1
    assert calls[0]["grant_type"] == "refresh_token" and calls[0]["refresh_token"] == "r1"
    now[0] += 3600 - 60  # 만료 1분 전 → 새로 받는다
    assert source.access_token() == "at2"


def test_expired_login_becomes_auth_error():
    def invalid_grant(url, fields):
        raise urllib.error.HTTPError(url, 400, "bad", {}, io.BytesIO(b'{"error":"invalid_grant"}'))

    with pytest.raises(GoogleAuthError, match="끊겼어요"):
        tokens(post_form=invalid_grant).access_token()
    with pytest.raises(GoogleAuthError):
        tokens(post_form=lambda url, fields: {}).access_token()


def test_client_info_reads_installed_app_only(tmp_path):
    good = tmp_path / "c.json"
    good.write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b", "project_id": "p"}}))
    assert client_info(good) == {"client_id": "a", "client_secret": "b", "project_id": "p"}
    web = tmp_path / "w.json"
    web.write_text(json.dumps({"web": {"client_id": "a"}}))
    for path in (web, tmp_path / "none.json"):
        with pytest.raises(GoogleAuthError):
            client_info(path)


def test_refresh_token_reader_prefers_env_then_keychain(monkeypatch):
    monkeypatch.setenv("GOOGLE_STT_REFRESH_TOKEN", " envtok ")
    assert read_refresh_token(run=lambda *a, **k: pytest.fail("키체인을 보면 안 됨")) == "envtok"
    monkeypatch.delenv("GOOGLE_STT_REFRESH_TOKEN")
    found = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="chaintok\n", stderr="")
    assert read_refresh_token(run=found) == "chaintok"
    assert read_refresh_token(run=lambda *a, **k: subprocess.CompletedProcess(a, 44, stdout="", stderr="")) == ""


def test_choice_only_when_logged_in(monkeypatch):
    assert "google-chirp3" in stt_choices(make_settings(google_stt=True))
    assert "google-chirp3" not in stt_choices(make_settings())
    # 기본 STT 가 구글이면 두 번 넣지 않는다
    assert stt_choices(make_settings(stt_engine="google-chirp3", google_stt=True)).count("google-chirp3") == 1
    monkeypatch.setenv("GOOGLE_STT", "off")
    assert load_settings().google_stt is False
    monkeypatch.setenv("STT_ENGINE", "google-chirp3")
    with pytest.raises(ValueError):
        load_settings()
    monkeypatch.setenv("GOOGLE_STT", "auto")
    monkeypatch.setenv("GOOGLE_STT_REFRESH_TOKEN", "t")
    assert load_settings().google_stt is True


def test_api_lists_google_and_reports_failures(monkeypatch):
    from app.engines import google_stt

    monkeypatch.setattr(google_stt.GoogleSttEngine, "transcribe",
                        lambda self, path: google_stt.SttResult(text="가스비 얼마야?", language="ko-KR"))
    monkeypatch.setattr("app.main.to_wav16k", lambda source, target: source)
    client = TestClient(create_app(make_settings(google_stt=True)))
    labels = {c["engine"]: c["label"] for c in client.get("/health").json()["sttChoices"]}
    assert labels["google-chirp3"] == "Google Chirp 3 (us) · 힌트"
    files = {"audio": ("a.wav", b"RIFFfake", "audio/wav")}
    reply = client.post("/stt", files=files, data={"engine": "google-chirp3"})
    assert reply.status_code == 200 and reply.json()["text"] == "가스비 얼마야?" and reply.json()["engine"] == "google-chirp3"

    def broken(self, path):
        raise google_stt.GoogleSttError("로그인이 끊겼어요")

    monkeypatch.setattr(google_stt.GoogleSttEngine, "transcribe", broken)
    assert client.post("/stt", files=files, data={"engine": "google-chirp3"}).status_code == 503


def test_hints_go_into_inline_phrase_set(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    bodies = []

    def post(url, body, headers):
        bodies.append(json.loads(body))
        return b"{}"

    GoogleSttEngine("google-chirp3", tokens=tokens(), post=post, hints=("아내", "가스비")).transcribe(wav)
    GoogleSttEngine("google-chirp3", tokens=tokens(), post=post, hints=("아내",), boost=10.0).transcribe(wav)
    GoogleSttEngine("google-chirp3", tokens=tokens(), post=post).transcribe(wav)
    assert bodies[0]["config"]["adaptation"] == {"phraseSets": [{"inlinePhraseSet": {"phrases": [{"value": "아내"}, {"value": "가스비"}]}}]}
    assert bodies[1]["config"]["adaptation"]["phraseSets"][0]["inlinePhraseSet"]["phrases"] == [{"value": "아내", "boost": 10.0}]
    assert "adaptation" not in bodies[2]["config"]


def test_eval_reads_the_same_hint_list_as_phone_stt(tmp_path):
    from finetune.evaluate import phone_hint_words

    words = phone_hint_words()
    assert "아내" in words and "가스비" in words and len(words) == len(set(words))
    broken = tmp_path / "x.ts"
    broken.write_text("export const CONTEXTUAL_WORDS = [\n];\n")
    with pytest.raises(ValueError):
        phone_hint_words(broken)


def test_server_engine_uses_the_shared_hint_file(tmp_path):
    from app.engines import create_stt_engine
    from app.engines.google_stt import load_hints

    engine = create_stt_engine(make_settings(stt_engine="google-chirp3", google_stt=True))
    assert engine._hints == load_hints() and "아내" in engine._hints and engine.label.endswith("· 힌트")
    messy = tmp_path / "h.json"
    messy.write_text(json.dumps({"words": [" 아내 ", "", "아내", "가스비"]}))
    assert load_hints(messy) == ("아내", "가스비")
    empty = tmp_path / "e.json"
    empty.write_text(json.dumps({"words": []}))
    with pytest.raises(ValueError):
        load_hints(empty)
