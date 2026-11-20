"""구글 STT(Chirp 3)용 로그인 — 2026-11-18 사용자 결정: 조직 정책으로 서비스 계정 JSON 키를 못 만들어서,
야구그림일기 때 만든 '설치형 로그인 앱(OAuth 클라이언트)'으로 사용자 본인이 한 번 로그인해 cloud-platform 권한을 받는다.

- 로그인 앱 파일: 환경변수 GOOGLE_STT_CLIENT_SECRET, 없으면 ~/.config/kbo-youtube/client_secret.json (읽기만 한다).
- 받은 새로 고침 토큰은 맥 키체인 'google-stt-refresh-token' 에만 둔다(레포·로그·응답에 남기지 않는다).
- 로그인 앱이 '테스트' 상태면 구글이 새로 고침 토큰을 7일 뒤 끊는다 → 다시 `login` 한다.
- 표준 라이브러리만 쓴다(127.0.0.1 임시 포트로 돌아오는 PKCE 로그인).

쓰기: cd server && .venv-asr/bin/python -m app.google_auth login   (맥 브라우저에 구글 로그인 창이 뜬다)
      cd server && .venv-asr/bin/python -m app.google_auth check   (토큰이 살아 있는지만 본다)
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_CLIENT_SECRET = Path.home() / ".config" / "kbo-youtube" / "client_secret.json"
KEYCHAIN_SERVICE = "google-stt-refresh-token"
REFRESH_ENV = "GOOGLE_STT_REFRESH_TOKEN"
KEYCHAIN_ACCOUNT = "stt-tts"
LOGIN_TIMEOUT_SEC = 300
# 만료 직전에 쓰다 끊기지 않게 이만큼 일찍 새로 받는다
REFRESH_MARGIN_SEC = 120


class GoogleAuthError(RuntimeError):
    """구글 로그인이 없거나 끊겼다. 서버는 503 으로 돌려주고 `python -m app.google_auth login` 을 안내한다."""


def client_info(path: Path | None = None) -> dict:
    """로그인 앱 파일 → {client_id, client_secret, project_id}. 설치형(installed)만 받는다."""
    path = path or Path(os.environ.get("GOOGLE_STT_CLIENT_SECRET", "").strip() or DEFAULT_CLIENT_SECRET)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))["installed"]
        return {"client_id": data["client_id"], "client_secret": data["client_secret"], "project_id": data["project_id"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GoogleAuthError(f"구글 로그인 앱 파일을 읽지 못했어요: {path}") from exc


def read_refresh_token(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    """환경변수 GOOGLE_STT_REFRESH_TOKEN → 맥 키체인 순서. 없으면 빈 글."""
    token = os.environ.get(REFRESH_ENV, "").strip()
    if token:
        return token
    try:
        result = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def save_refresh_token(
    token: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run, service: str = KEYCHAIN_SERVICE,
) -> None:
    result = run(["security", "add-generic-password", "-U", "-s", service, "-a", KEYCHAIN_ACCOUNT, "-w", token],
                 capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        raise GoogleAuthError("키체인에 구글 로그인을 저장하지 못했어요.")


def _post_form(url: str, fields: dict) -> dict:
    request = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - 구글 고정 주소
        return json.loads(response.read())


class TokenSource:
    """새로 고침 토큰 → 짧은 접근 토큰(약 1시간). 여러 요청이 같이 써도 되게 잠근다."""

    def __init__(
        self,
        client: Callable[[], dict] = client_info,
        refresh_reader: Callable[[], str] = read_refresh_token,
        post_form: Callable[[str, dict], dict] = _post_form,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client, self._refresh_reader, self._post_form, self._clock = client, refresh_reader, post_form, clock
        self._token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def project_id(self) -> str:
        return self._client()["project_id"]

    def access_token(self) -> str:
        with self._lock:
            if self._token and self._clock() < self._expires_at - REFRESH_MARGIN_SEC:
                return self._token
            refresh = self._refresh_reader()
            if not refresh:
                raise GoogleAuthError("구글 STT 로그인이 없어요. `python -m app.google_auth login` 을 해 주세요.")
            client = self._client()
            try:
                reply = self._post_form(TOKEN_URL, {
                    "client_id": client["client_id"], "client_secret": client["client_secret"],
                    "refresh_token": refresh, "grant_type": "refresh_token",
                })
            except urllib.error.HTTPError as exc:
                # invalid_grant: 7일이 지났거나 권한을 거둬들였다
                raise GoogleAuthError(f"구글 STT 로그인이 끊겼어요({exc.code}). 다시 로그인해 주세요.") from exc
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                raise GoogleAuthError(f"구글 로그인 서버에 연결하지 못했어요: {exc}") from exc
            token = str(reply.get("access_token", ""))
            if not token:
                raise GoogleAuthError("구글이 접근 토큰을 주지 않았어요.")
            self._token = token
            self._expires_at = self._clock() + float(reply.get("expires_in", 3600))
            return token


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def login(service: str = KEYCHAIN_SERVICE) -> None:
    """맥 브라우저로 구글 로그인 → 키체인(service)에 새로 고침 토큰 저장.
    2026-11-19: 다른 구글 계정(클라우드 GPU 확인용)은 다른 키체인 이름으로 받아 STT 로그인을 덮어쓰지 않는다."""
    client = client_info()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server 이름
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [""])[0] == state:
                result["code"] = query.get("code", [""])[0]
                result["error"] = query.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("구글 STT 로그인이 끝났어요. 이 창은 닫아도 돼요.".encode())

        def log_message(self, *args) -> None:  # 주소(코드 포함)를 화면에 찍지 않는다
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    subprocess.run(["open", url], check=False)
    print("맥 브라우저에 구글 로그인 창을 띄웠어요. 계정을 고르고 '허용'을 눌러 주세요.", flush=True)
    server.timeout = 1
    deadline = time.time() + LOGIN_TIMEOUT_SEC
    while "code" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if not result.get("code"):
        raise GoogleAuthError(f"로그인을 받지 못했어요({result.get('error') or '시간 초과'}).")
    reply = _post_form(TOKEN_URL, {
        "client_id": client["client_id"], "client_secret": client["client_secret"], "code": result["code"],
        "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect,
    })
    refresh = str(reply.get("refresh_token", ""))
    if not refresh:
        raise GoogleAuthError("구글이 새로 고침 토큰을 주지 않았어요.")
    if SCOPE not in str(reply.get("scope", "")):
        raise GoogleAuthError("클라우드 권한(cloud-platform)이 허락되지 않았어요.")
    save_refresh_token(refresh, service=service)
    print(f"로그인 저장 완료(키체인 {service}). 로그인 앱 프로젝트: {client['project_id']}", flush=True)


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    try:
        if command == "login":
            # login [키체인 이름] — 기본은 STT 로그인(google-stt-refresh-token)
            login(argv[1] if len(argv) > 1 else KEYCHAIN_SERVICE)
        elif command == "check":
            TokenSource().access_token()
            print("구글 STT 로그인 살아 있어요.")
        else:
            print("쓰기: python -m app.google_auth login|check")
            return 2
    except GoogleAuthError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
