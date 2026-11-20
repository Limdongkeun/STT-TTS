"""구글 Speech-to-Text V2 Chirp 3(한국어) — 2026-11-18 사용자 결정: 8002 서버 STT 고르기에 붙인다(쓴 만큼 구글 결제).

1단계는 녹음이 끝난 뒤 한 번에 보내는 방식(Recognize, REST). 실시간(StreamingRecognize)은 gRPC 만 돼서 2단계로 미룬다.
로그인은 app.google_auth(사용자 본인 OAuth, 키체인 'google-stt-refresh-token'). 서비스 계정 키는 조직 정책으로 못 만든다.
chirp_3 는 us·eu 멀티 리전에만 있다(서울·도쿄 없음) → us-speech.googleapis.com, locations/us.
    POST https://us-speech.googleapis.com/v2/projects/{project}/locations/us/recognizers/_:recognize
         {"config": {"autoDecodingConfig": {}, "languageCodes": ["ko-KR"], "model": "chirp_3"}, "content": base64}
숫자는 구글이 '42,000원'처럼 아라비아 숫자로 적는다.
힌트: 2026-11-18 평가(76개 CER 0.153 → 0.132)를 보고 사용자 결정으로 서버도 기본으로 넣는다. 목록은 app/data/stt_hints.json
(폰 STT 와 같은 42개, config.adaptation 의 inlinePhraseSet, boost 없음, chirp_3 는 1,000개까지).
"""

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from app.engines.base import SttResult
from app.google_auth import GoogleAuthError, TokenSource

HINTS_PATH = Path(__file__).resolve().parents[1] / "data" / "stt_hints.json"

LOCATION = "us"
API = "https://us-speech.googleapis.com/v2/projects/{project}/locations/" + LOCATION + "/recognizers/_:recognize"
MODEL = "chirp_3"
LANGUAGE_CODE = "ko-KR"
LABEL = "Google Chirp 3 (us)"
HINT_LABEL = "Google Chirp 3 (us) · 힌트"
# 받아 적는 꼴 지시문(custom prompt, 구글 미리보기 기능). 2026-11-19 평가 76개: 힌트만 0.132 → 힌트+지시문 0.121.
# 반말 끝을 높임말로 바꾸는 버릇('차례야'→'차례예요')과 숫자 꼴('84,000원')을 고친다. 사용자 결정으로 서버 기본.
DEFAULT_PROMPT = (
    "Transcribe exactly what is said, word for word, in Korean. "
    "Keep every sentence ending exactly as spoken: never turn casual endings (반말) such as '뭐야', '냈어', '차례야', '언제야' "
    "into polite ones such as '뭐예요', '냈어요', '차례예요'. Do not add or drop words. "
    "Write money with Korean units like '8만 4천 원', times like '2시 30분', dates like '12월 3일', counts like '30분', '1시간'."
)
TIMEOUT_SEC = 60
# Recognize(한 번에 보내기)는 1분 안쪽 소리용. base64 로 늘어나도 요청 한도(10MB) 안에 들게 막는다.
MAX_AUDIO_BYTES = 7 * 1024 * 1024


class GoogleSttError(RuntimeError):
    """구글 STT 를 지금 못 쓴다(로그인 끊김·결제·권한·연결). 서버는 503 으로 돌려준다."""


def _post(url: str, body: bytes, headers: dict) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:  # noqa: S310 - 구글 고정 주소
        return response.read()


def load_hints(path: Path = HINTS_PATH) -> tuple[str, ...]:
    """서버 힌트 낱말(빈 줄·겹침 없이). 파일이 없거나 깨졌으면 오류(조용히 힌트 없이 돌지 않게)."""
    words = json.loads(path.read_text(encoding="utf-8"))["words"]
    cleaned = tuple(dict.fromkeys(str(word).strip() for word in words if str(word).strip()))
    if not cleaned:
        raise ValueError(f"힌트 낱말이 없어요: {path}")
    return cleaned


def transcript_of(reply: dict) -> str:
    """results 마다 첫 후보의 글을 이어 붙인다(긴 말은 조각으로 나뉘어 온다)."""
    parts = []
    for result in reply.get("results") or []:
        alternatives = result.get("alternatives") or []
        if alternatives:
            parts.append(str(alternatives[0].get("transcript", "")).strip())
    return " ".join(part for part in parts if part)


class GoogleSttEngine:
    def __init__(
        self,
        name: str,
        tokens: TokenSource | None = None,
        post: Callable[[str, bytes, dict], bytes] = _post,
        hints: tuple[str, ...] = (),
        boost: float | None = None,
        prompt: str = "",
    ) -> None:
        self.name = name
        self._hints = hints
        self._boost = boost
        # 받아 적는 꼴 지시문(chirp_3 custom prompt, 미리보기 기능). 위치는 config.features.customPromptConfig.customPrompt
        self._prompt = prompt
        self.label = (HINT_LABEL if hints else LABEL) + (" · 지시문" if prompt else "")
        self._tokens = tokens or TokenSource()
        self._post = post

    def _config(self) -> dict:
        config: dict = {"autoDecodingConfig": {}, "languageCodes": [LANGUAGE_CODE], "model": MODEL}
        if self._hints:
            phrases = [{"value": hint} if self._boost is None else {"value": hint, "boost": self._boost} for hint in self._hints]
            config["adaptation"] = {"phraseSets": [{"inlinePhraseSet": {"phrases": phrases}}]}
        if self._prompt:
            config["features"] = {"customPromptConfig": {"customPrompt": self._prompt}}
        return config

    def transcribe(self, wav_path: Path) -> SttResult:
        audio = Path(wav_path).read_bytes()
        if len(audio) > MAX_AUDIO_BYTES:
            raise GoogleSttError("구글 STT 에 한 번에 보내기엔 소리가 너무 길어요(1분 안쪽만).")
        body = json.dumps({"config": self._config(), "content": base64.b64encode(audio).decode()}).encode("utf-8")
        try:
            project = self._tokens.project_id()
            headers = {
                "Authorization": f"Bearer {self._tokens.access_token()}",
                # 사용자 로그인으로 부를 때 요금·한도를 매길 프로젝트
                "x-goog-user-project": project,
                "Content-Type": "application/json",
            }
            raw = self._post(API.format(project=project), body, headers)
        except GoogleAuthError as exc:
            raise GoogleSttError(str(exc)) from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise GoogleSttError(f"구글 STT 가 거절했어요({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GoogleSttError(f"구글 STT 에 연결하지 못했어요: {exc}") from exc
        try:
            reply = json.loads(raw)
        except ValueError as exc:
            raise GoogleSttError("구글 STT 응답을 읽지 못했어요.") from exc
        return SttResult(text=transcript_of(reply), language=LANGUAGE_CODE)
