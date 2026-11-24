"""클라우드 L4 Qwen 한국어판(2026-11-20)과 vLLM 백엔드 설정. 진짜 클라우드·vLLM 은 부르지 않는다."""

import io
import json
import subprocess
import sys
import types
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.engines import create_stt_engine
from app.engines.base import SttResult
from app.engines.cloud_stt import CloudSttEngine, CloudSttError, multipart, read_key
from app.engines.qwen3_asr import Qwen3AsrEngine
from app.main import create_app
from app.settings import load_settings, stt_choices
from tests.test_api import make_settings

URL = "https://stt.example"


def wav(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"RIFFfake")
    return path


def test_sends_wav_with_key_and_ko_engine(tmp_path):
    calls = []

    def post(url, body, headers):
        calls.append((url, body, headers))
        return json.dumps({"text": " 가스비 언제까지야? ", "language": "Korean", "engine": "qwen3-asr-ko"}).encode()

    result = CloudSttEngine(URL + "/", key_reader=lambda: "k1", post=post).transcribe(wav(tmp_path))
    url, body, headers = calls[0]
    assert url == "https://stt.example/stt" and headers["X-Stt-Key"] == "k1"
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="engine"\r\n\r\nqwen3-asr-ko\r\n' in body and b"RIFFfake" in body
    assert (result.text, result.language) == ("가스비 언제까지야?", "Korean")


def test_multipart_has_closing_boundary():
    body, content_type = multipart({"a": "1"}, "audio", "x.wav", b"DATA")
    boundary = content_type.split("boundary=")[1]
    assert body.endswith(f"--{boundary}--\r\n".encode()) and body.count(boundary.encode()) == 3


@pytest.mark.parametrize("error, match", [
    (urllib.error.HTTPError(URL, 401, "no", {}, io.BytesIO(b"unauthorized")), "열쇠를 거절"),
    (urllib.error.HTTPError(URL, 500, "bad", {}, io.BytesIO(b"")), "500"),
    (urllib.error.URLError("refused"), "9~18시"),
    (TimeoutError(), "연결하지 못했어요"),
])
def test_failures_become_cloud_stt_error(tmp_path, error, match):
    def post(*args):
        raise error

    with pytest.raises(CloudSttError, match=match):
        CloudSttEngine(URL, key_reader=lambda: "k", post=post).transcribe(wav(tmp_path))


def test_missing_key_and_bad_reply(tmp_path):
    with pytest.raises(CloudSttError, match="열쇠가 없어요"):
        CloudSttEngine(URL, key_reader=lambda: "", post=lambda *a: pytest.fail("열쇠 없이 보내면 안 됨")).transcribe(wav(tmp_path))
    for raw in (b"not json", b"{}", b"[]"):
        with pytest.raises(CloudSttError, match="응답"):
            CloudSttEngine(URL, key_reader=lambda: "k", post=lambda *a, raw=raw: raw).transcribe(wav(tmp_path))


def test_key_reader_prefers_env_then_keychain(monkeypatch):
    monkeypatch.setenv("STT_CLOUD_KEY", " envkey ")
    assert read_key(run=lambda *a, **k: pytest.fail("키체인을 보면 안 됨")) == "envkey"
    monkeypatch.delenv("STT_CLOUD_KEY")
    assert read_key(run=lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="chain\n", stderr="")) == "chain"
    assert read_key(run=lambda *a, **k: subprocess.CompletedProcess(a, 44, stdout="", stderr="")) == ""


def test_choice_only_with_key_and_https(monkeypatch):
    assert stt_choices(make_settings(stt_cloud_url=URL))[-1] == "qwen3-asr-ko-cloud"
    assert "qwen3-asr-ko-cloud" not in stt_choices(make_settings())
    monkeypatch.setenv("STT_CLOUD_KEY", "k")
    assert load_settings().stt_cloud_url == "https://34-50-48-66.sslip.io"
    monkeypatch.setenv("STT_CLOUD_URL", "https://other.example/")
    assert load_settings().stt_cloud_url == "https://other.example"
    monkeypatch.setenv("STT_CLOUD_URL", "http://plain.example")
    with pytest.raises(ValueError, match="https"):
        load_settings()
    monkeypatch.delenv("STT_CLOUD_URL")
    monkeypatch.setenv("STT_CLOUD", "off")
    assert load_settings().stt_cloud_url == ""
    monkeypatch.setenv("STT_ENGINE", "qwen3-asr-ko-cloud")
    with pytest.raises(ValueError, match="열쇠"):
        load_settings()


def test_api_lists_cloud_and_reports_outage(monkeypatch):
    from app.engines import cloud_stt

    monkeypatch.setattr(cloud_stt.CloudSttEngine, "transcribe", lambda self, path: SttResult(text="우유 사 와", language="Korean"))
    monkeypatch.setattr("app.main.to_wav16k", lambda source, target: source)
    client = TestClient(create_app(make_settings(stt_cloud_url=URL)))
    labels = {c["engine"]: c["label"] for c in client.get("/health").json()["sttChoices"]}
    assert labels["qwen3-asr-ko-cloud"] == "Qwen3-ASR-1.7B-ko (클라우드 L4)"
    files = {"audio": ("a.wav", b"RIFFfake", "audio/wav")}
    reply = client.post("/stt", files=files, data={"engine": "qwen3-asr-ko-cloud"})
    assert reply.status_code == 200 and reply.json()["engine"] == "qwen3-asr-ko-cloud"

    def down(self, path):
        raise cloud_stt.CloudSttError("클라우드 STT 서버에 연결하지 못했어요.")

    monkeypatch.setattr(cloud_stt.CloudSttEngine, "transcribe", down)
    assert client.post("/stt", files=files, data={"engine": "qwen3-asr-ko-cloud"}).status_code == 503


class _FakeQwen:
    calls = []

    @classmethod
    def LLM(cls, **kwargs):
        cls.calls.append(("vllm", kwargs))
        return "vllm-model"

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        cls.calls.append(("transformers", model_id))
        return "tf-model"


def test_backend_picks_vllm_or_transformers(monkeypatch):
    monkeypatch.setitem(sys.modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=_FakeQwen))
    monkeypatch.setattr("app.engines.qwen3_asr.resolve_device", lambda value: "cpu")
    monkeypatch.setattr("app.engines.qwen3_asr.resolve_dtype", lambda value: "float32")
    _FakeQwen.calls.clear()
    vllm = create_stt_engine(make_settings(stt_engine="qwen3-asr-ko", asr_ko_model_id="/m", asr_backend="vllm"))
    assert vllm._load() == "vllm-model"
    kind, kwargs = _FakeQwen.calls[0]
    assert kind == "vllm" and kwargs["model"] == "/m" and kwargs["gpu_memory_utilization"] < 0.5
    assert kwargs["max_model_len"] == 4096
    assert isinstance(vllm, Qwen3AsrEngine)
    plain = create_stt_engine(make_settings(stt_engine="qwen3-asr-ko", asr_ko_model_id="/m"))
    assert plain._load() == "tf-model" and _FakeQwen.calls[1] == ("transformers", "/m")


def test_backend_setting(monkeypatch):
    assert load_settings().asr_backend == "transformers"
    monkeypatch.setenv("ASR_BACKEND", "vllm")
    assert load_settings().asr_backend == "vllm"
    monkeypatch.setenv("ASR_BACKEND", "tensorrt")
    with pytest.raises(ValueError):
        load_settings()


def test_transcribe_runs_one_at_a_time(tmp_path):
    """vLLM 은 여러 스레드가 함께 부르면 멈춘다 → 받아 적기는 한 번에 하나씩(2026-11-20)."""
    import threading
    import time as _time

    state = {"now": 0, "max": 0}
    guard = threading.Lock()

    class SlowModel:
        def transcribe(self, **kwargs):
            with guard:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            _time.sleep(0.02)
            with guard:
                state["now"] -= 1
            return [SttResult(text="응", language="Korean")]

    engine = create_stt_engine(make_settings(stt_engine="qwen3-asr-ko", asr_ko_model_id="/m", asr_backend="vllm"))
    engine._model = SlowModel()
    threads = [threading.Thread(target=engine.transcribe, args=(tmp_path / "a.wav",)) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert state["max"] == 1
