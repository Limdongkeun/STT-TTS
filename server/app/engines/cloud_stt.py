"""클라우드 L4 의 Qwen 한국어판 STT 를 부른다(2026-11-20 사용자 결정: 앱에서 맥 Qwen 과 나란히 비교).

클라우드 서버도 이 레포의 server/app 그대로이고, 바깥에는 Caddy 가 HTTPS 로 /stt·/health 만 연다.
    POST {url}/stt   머리 X-Stt-Key: <열쇠>   multipart: audio=<16k wav>, engine=qwen3-asr-ko
열쇠는 환경변수 STT_CLOUD_KEY → 맥 키체인 'familybot-stt-api-key' 순서로 읽고, 로그·응답에 남기지 않는다.
서버는 평일 9~18시에만 켜져 있다(그 밖엔 연결 실패 → 503 으로 알린다).
"""

import json
import os
import secrets
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from app.engines.base import SttResult
from app.settings import QWEN_KO_CLOUD_STT_ENGINE, QWEN_KO_STT_ENGINE

KEY_ENV = "STT_CLOUD_KEY"
KEYCHAIN_SERVICE = "familybot-stt-api-key"
LABEL = "Qwen3-ASR-1.7B-ko (클라우드 L4)"
# 받아 적기는 1초 안쪽이지만, 서버가 막 켜져 모델을 읽는 중이면 더 걸린다
TIMEOUT_SEC = 30


class CloudSttError(RuntimeError):
    """클라우드 STT 를 지금 못 쓴다(꺼짐·열쇠·연결). 서버는 503 으로 돌려준다."""


def read_key(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    try:
        result = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _post(url: str, body: bytes, headers: dict) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:  # noqa: S310 - 설정의 https 주소만
        return response.read()


def multipart(fields: dict[str, str], file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    """표준 라이브러리로 multipart/form-data 를 만든다 → (본문, Content-Type)."""
    boundary = "----stt" + secrets.token_hex(12)
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode() + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class CloudSttEngine:
    label = LABEL

    def __init__(
        self,
        url: str,
        name: str = QWEN_KO_CLOUD_STT_ENGINE,
        key_reader: Callable[[], str] = read_key,
        post: Callable[[str, bytes, dict], bytes] = _post,
    ) -> None:
        self.name = name
        self._url = url.rstrip("/") + "/stt"
        self._key_reader = key_reader
        self._post = post

    def transcribe(self, wav_path: Path) -> SttResult:
        key = self._key_reader()
        if not key:
            raise CloudSttError("클라우드 STT 열쇠가 없어요(맥 키체인 familybot-stt-api-key).")
        body, content_type = multipart({"engine": QWEN_KO_STT_ENGINE}, "audio", "input16k.wav", Path(wav_path).read_bytes())
        try:
            raw = self._post(self._url, body, {"X-Stt-Key": key, "Content-Type": content_type})
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise CloudSttError("클라우드 STT 가 열쇠를 거절했어요(401).") from exc
            raise CloudSttError(f"클라우드 STT 가 거절했어요({exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudSttError("클라우드 STT 서버에 연결하지 못했어요. 평일 9~18시에만 켜져 있어요.") from exc
        try:
            reply = json.loads(raw)
            return SttResult(text=str(reply["text"]).strip(), language=reply.get("language"))
        except (ValueError, KeyError, TypeError) as exc:
            raise CloudSttError("클라우드 STT 응답을 읽지 못했어요.") from exc
