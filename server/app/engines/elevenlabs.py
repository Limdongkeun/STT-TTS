"""ElevenLabs TTS(v4 Turbo) — 2026-11-17 사용자 허락: 107 이 자꾸 멈춰서 8002 TTS 고르기에 붙인다(쓴 만큼 계정 크레딧 차감).

키는 환경변수 ELEVENLABS_API_KEY, 없으면 맥 키체인 항목 'elevenlabs-api-key'(사용자가 이름을 알려 줌)에서만 읽는다.
키는 로그·응답·파일에 남기지 않는다. 목소리는 2026-11-17 16:10 사용자 결정으로 여자 Anna Kim·남자 Chris(둘 다 계정 내 목소리,
한국어 서울; Chris 는 계정에 'KKC HQ' 이름). 지수 Turbo 는 뺐다(지수 녹음 재생 엔진 prerecorded 는 그대로).
    POST https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=pcm_24000
         {"text": ..., "model_id": "eleven_v4_turbo"}  → 24kHz 16비트 PCM
"""

import io
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
import wave
from typing import Callable

from app.engines.base import TtsResult

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=pcm_{rate}"
MODEL_ID = "eleven_v4_turbo"
# 엔진 이름 → (목소리 id, 이름표)
VOICES = {
    "elevenlabs-v4-turbo-female": ("uyVNoMrnUku1dZyVEXwD", "ElevenLabs v4 Turbo · Anna Kim(여자)"),  # Anna Kim - Tender, Calm and Clear
    "elevenlabs-v4-turbo-male": ("PDoCXqBQFGsvfO0hNkEs", "ElevenLabs v4 Turbo · Chris(남자)"),  # Chris - Warm and Clear
}
SAMPLE_RATE = 24000
KEYCHAIN_SERVICE = "elevenlabs-api-key"
TIMEOUT_SEC = 30


class ElevenLabsError(RuntimeError):
    """ElevenLabs 를 지금 못 쓴다(키 없음·크레딧 부족·권한·연결). 서버는 503 으로 돌려준다."""


def read_api_key(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    """환경변수 → 맥 키체인 순서. 없으면 빈 글(그러면 고르기 목록에 나오지 않는다)."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    try:
        result = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm)
    return buffer.getvalue()


def _post(url: str, body: bytes, key: str) -> bytes:
    request = urllib.request.Request(url, data=body, headers={"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:  # noqa: S310 - 고정 주소
        return response.read()


class ElevenLabsTtsEngine:
    def __init__(
        self,
        name: str,
        key_reader: Callable[[], str] = read_api_key,
        post: Callable[[str, bytes, str], bytes] = _post,
        voice_id: str | None = None,
    ) -> None:
        self._key_reader = key_reader
        self._post = post
        if name not in VOICES:
            raise ValueError(f"모르는 ElevenLabs 엔진: {name}")
        self.name = name
        default_voice, self.label = VOICES[name]
        self._voice_id = voice_id or default_voice
        self._key: str | None = None
        self._lock = threading.Lock()

    def _api_key(self) -> str:
        with self._lock:
            if self._key is None:
                self._key = self._key_reader()
        if not self._key:
            raise ElevenLabsError("ElevenLabs 키가 없어요(ELEVENLABS_API_KEY 또는 키체인 elevenlabs-api-key).")
        return self._key

    def synthesize(self, text: str) -> TtsResult:
        url = API.format(voice=self._voice_id, rate=SAMPLE_RATE)
        body = json.dumps({"text": text, "model_id": MODEL_ID}).encode("utf-8")
        try:
            pcm = self._post(url, body, self._api_key())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise ElevenLabsError(f"ElevenLabs 가 거절했어요({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ElevenLabsError(f"ElevenLabs 에 연결하지 못했어요: {exc}") from exc
        if len(pcm) < 2:
            raise ElevenLabsError("ElevenLabs 가 빈 소리를 돌려줬어요.")
        pcm = pcm[: len(pcm) - len(pcm) % 2]
        return TtsResult(wav_bytes=pcm_to_wav(pcm), sample_rate=SAMPLE_RATE, duration_sec=len(pcm) / 2 / SAMPLE_RATE)
