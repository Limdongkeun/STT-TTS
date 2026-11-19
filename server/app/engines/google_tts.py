"""Google Cloud Text-to-Speech(Chirp 3 HD 한국어) — 2026-11-18 사용자 결정: 8002 TTS 고르기에 붙인다(쓴 만큼 구글 결제).

키는 환경변수 GOOGLE_TTS_API_KEY, 없으면 맥 키체인 항목 'google-tts-api-key'(사용자가 준 TTS 전용 제한 키)에서만 읽는다.
키는 주소(?key=)가 아니라 X-Goog-Api-Key 머리글로 보내고, 로그·응답·파일에 남기지 않는다.
    POST https://texttospeech.googleapis.com/v1/text:synthesize
         {"input": {"text": ...}, "voice": {"languageCode": "ko-KR", "name": ...},
          "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000}}  → {"audioContent": base64 WAV}
목소리 이름은 2026-11-18 voices?languageCode=ko-KR 목록에서 확인했다(Chirp 3 HD 30개, 모두 24kHz).
"""

import base64
import binascii
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
from app.engines.elevenlabs import pcm_to_wav

API = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE_CODE = "ko-KR"
# 엔진 이름 → (구글 목소리 이름, 이름표)
VOICES = {
    "google-chirp3-hd-female": ("ko-KR-Chirp3-HD-Aoede", "Google Chirp 3 HD · Aoede(여자)"),
    "google-chirp3-hd-male": ("ko-KR-Chirp3-HD-Charon", "Google Chirp 3 HD · Charon(남자)"),
}
SAMPLE_RATE = 24000
KEY_ENV = "GOOGLE_TTS_API_KEY"
KEYCHAIN_SERVICE = "google-tts-api-key"
TIMEOUT_SEC = 30


class GoogleTtsError(RuntimeError):
    """구글 TTS 를 지금 못 쓴다(키 없음·결제 없음·권한·연결). 서버는 503 으로 돌려준다."""


def read_api_key(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    """환경변수 → 맥 키체인 순서. 없으면 빈 글."""
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    try:
        result = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _post(url: str, body: bytes, key: str) -> bytes:
    request = urllib.request.Request(url, data=body, headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:  # noqa: S310 - 고정 주소
        return response.read()


def wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int]:
    """구글 LINEAR16 응답(WAV 머리 포함) → (16비트 모노 PCM, 표본율)."""
    with wave.open(io.BytesIO(wav_bytes)) as reader:
        if reader.getsampwidth() != 2 or reader.getnchannels() != 1:
            raise GoogleTtsError("구글이 16비트 모노가 아닌 소리를 돌려줬어요.")
        return reader.readframes(reader.getnframes()), reader.getframerate()


class GoogleTtsEngine:
    def __init__(
        self,
        name: str,
        key_reader: Callable[[], str] = read_api_key,
        post: Callable[[str, bytes, str], bytes] = _post,
    ) -> None:
        if name not in VOICES:
            raise ValueError(f"모르는 구글 TTS 엔진: {name}")
        self.name = name
        self._voice, self.label = VOICES[name]
        self._key_reader = key_reader
        self._post = post
        self._key: str | None = None
        self._lock = threading.Lock()

    def _api_key(self) -> str:
        with self._lock:
            if self._key is None:
                self._key = self._key_reader()
        if not self._key:
            raise GoogleTtsError(f"구글 TTS 키가 없어요({KEY_ENV} 또는 키체인 {KEYCHAIN_SERVICE}).")
        return self._key

    def synthesize(self, text: str) -> TtsResult:
        body = json.dumps({
            "input": {"text": text},
            "voice": {"languageCode": LANGUAGE_CODE, "name": self._voice},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SAMPLE_RATE},
        }).encode("utf-8")
        try:
            raw = self._post(API, body, self._api_key())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise GoogleTtsError(f"구글 TTS 가 거절했어요({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GoogleTtsError(f"구글 TTS 에 연결하지 못했어요: {exc}") from exc
        try:
            audio = base64.b64decode(json.loads(raw)["audioContent"], validate=True)
            pcm, rate = wav_to_pcm(audio)
        except (ValueError, KeyError, TypeError, binascii.Error, wave.Error, EOFError) as exc:
            raise GoogleTtsError("구글 TTS 응답을 읽지 못했어요.") from exc
        pcm = pcm[: len(pcm) - len(pcm) % 2]
        if not pcm:
            raise GoogleTtsError("구글 TTS 가 빈 소리를 돌려줬어요.")
        return TtsResult(wav_bytes=pcm_to_wav(pcm, rate), sample_rate=rate, duration_sec=len(pcm) / 2 / rate)
