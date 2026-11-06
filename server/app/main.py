"""가족비서 음성 시험 서버.

흐름: (앱) 녹음 → POST /stt → 글
              글 → POST /ask → 답 글 + 읽기용 글
         읽기용 글 → POST /tts → 음성 주소 → GET /audio/{id}
STT 서버와 TTS 서버를 따로 띄울 수 있다(같은 코드, 다른 환경변수·extra).
"""

import logging
import re
import tempfile
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.answers import create_answer_provider
from app.audio import AudioConversionError, normalize_suffix, to_wav16k
from app.engines.prerecorded import RecordingUnavailableError, VOICE_LABEL
from app.engines import create_stt_engine, create_tts_engine
from app.family_demo import FamilyDemoAnswerProvider, FamilyDemoContext
from app.normalize import normalize_for_speech
from app.settings import Settings, load_settings
from app.test_sheet import CASES_BY_ID, DEFAULT_RESULTS_DIR, TEST_CASES, SheetResult, SheetStore, is_valid_device, tts_label_for

# uvicorn 이 이미 출력하는 로거를 써서 서버 터미널에 바로 보이게 한다.
logger = logging.getLogger("uvicorn.error")
LOGGED_QUESTION_CHARS = 200

AUDIO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_STORED_AUDIO = 50
UPLOAD_CHUNK_BYTES = 1024 * 1024


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SttResponse(ApiModel):
    text: str
    language: str | None
    engine: str
    elapsed_ms: int


class AskRequest(ApiModel):
    text: str = Field(min_length=1, max_length=500)
    context: FamilyDemoContext | None = None
    # 말하는 사람(부부 공유 업무 시험). "내가", "나한테", "여보"를 이 사람 기준으로 푼다.
    speaker: Literal["wife", "husband"] = "wife"


class AskResponse(ApiModel):
    answer_text: str
    speech_text: str
    provider: str
    elapsed_ms: int
    context: FamilyDemoContext | None = None


class TtsRequest(ApiModel):
    text: str = Field(min_length=1, max_length=1000)
    normalize: bool = False


class TtsResponse(ApiModel):
    audio_url: str
    duration_sec: float
    sample_rate: int
    engine: str
    elapsed_ms: int


class AudioStore:
    """만든 음성을 임시 폴더에 두고, 오래된 것부터 지운다."""

    def __init__(self, directory: Path, limit: int = MAX_STORED_AUDIO) -> None:
        self._directory = directory
        self._limit = limit
        self._items: OrderedDict[str, Path] = OrderedDict()

    def save(self, wav_bytes: bytes) -> str:
        audio_id = uuid.uuid4().hex
        path = self._directory / f"{audio_id}.wav"
        path.write_bytes(wav_bytes)
        self._items[audio_id] = path
        while len(self._items) > self._limit:
            _, old_path = self._items.popitem(last=False)
            old_path.unlink(missing_ok=True)
        return audio_id

    def get(self, audio_id: str) -> Path | None:
        if not AUDIO_ID_PATTERN.fullmatch(audio_id):
            return None
        return self._items.get(audio_id)


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = bytearray()
    while chunk := upload.file.read(UPLOAD_CHUNK_BYTES):
        data += chunk
        if len(data) > limit:
            raise HTTPException(status_code=413, detail="음성 파일이 너무 큽니다.")
    if not data:
        raise HTTPException(status_code=400, detail="빈 음성 파일입니다.")
    return bytes(data)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    stt_engine = create_stt_engine(settings)
    tts_engine = create_tts_engine(settings)
    answer_provider = (
        FamilyDemoAnswerProvider() if settings.answer_provider == "family-demo" else create_answer_provider(settings)
    )
    work_dir = Path(tempfile.mkdtemp(prefix="stt-tts-"))
    sheet_store = SheetStore(Path(settings.test_results_dir) if settings.test_results_dir else DEFAULT_RESULTS_DIR)
    audio_store = AudioStore(work_dir)

    app = FastAPI(title="STT-TTS 시험 서버", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "sttEngine": stt_engine.name,
            "sttModel": settings.asr_model_id if settings.stt_engine == "qwen3-asr" else "",
            "ttsEngine": tts_engine.name,
            "ttsModel": VOICE_LABEL if settings.tts_engine == "prerecorded" else (
                settings.tts_model_id if settings.tts_engine == "qwen3-tts" else ""
            ),
            "answerProvider": answer_provider.name,
        }

    @app.post("/stt", response_model=SttResponse)
    def speech_to_text(audio: UploadFile = File(...)) -> SttResponse:
        started = time.perf_counter()
        try:
            suffix = normalize_suffix(audio.filename)
        except AudioConversionError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        data = _read_limited(audio, settings.max_upload_bytes)
        with tempfile.TemporaryDirectory(dir=work_dir) as job_dir:
            source = Path(job_dir) / f"input{suffix}"
            source.write_bytes(data)
            try:
                wav_path = to_wav16k(source, Path(job_dir) / "input16k.wav")
            except AudioConversionError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            result = stt_engine.transcribe(wav_path)
        return SttResponse(
            text=result.text,
            language=result.language,
            engine=stt_engine.name,
            elapsed_ms=_elapsed_ms(started),
        )

    @app.post("/ask", response_model=AskResponse, response_model_exclude_none=True)
    def ask(request: AskRequest) -> AskResponse:
        started = time.perf_counter()
        text = request.text.strip()
        # 시험용: 폰 STT 가 보낸 글을 repr 로 남겨 보이지 않는 문자(예: ​)도 확인한다.
        logger.info("ask question=%r", text[:LOGGED_QUESTION_CHARS])
        context = None
        if isinstance(answer_provider, FamilyDemoAnswerProvider):
            answer_text, context = answer_provider.answer(text, request.context, speaker=request.speaker)
        else:
            answer_text = answer_provider.answer(text)
        speech_text = answer_text
        if settings.tts_engine == "prerecorded" and context and context.dose_at and answer_text.startswith("시험 기록에 "):
            action = "수정했어요" if "수정했어요." in answer_text else "기록했어요"
            speech_text = (
                f"말씀하신 시각으로 복용 시간을 {action}. "
                "가상 일정에 등록된 다음 복용 예정 시각은 오후 9시예요."
            )
        return AskResponse(
            answer_text=answer_text,
            speech_text=normalize_for_speech(speech_text),
            provider=answer_provider.name,
            context=context,
            elapsed_ms=_elapsed_ms(started),
        )

    @app.post("/tts", response_model=TtsResponse)
    def text_to_speech(request: TtsRequest) -> TtsResponse:
        started = time.perf_counter()
        text = normalize_for_speech(request.text) if request.normalize else request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="읽을 글이 없습니다.")
        try:
            result = tts_engine.synthesize(text)
        except RecordingUnavailableError as exc:
            # 404: 이 답의 녹음이 없다(앱은 오류 대신 화면 답만 보여 준다). 422 는 요청 모양 오류로 남겨 둔다.
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audio_id = audio_store.save(result.wav_bytes)
        return TtsResponse(
            audio_url=f"/audio/{audio_id}",
            duration_sec=round(result.duration_sec, 3),
            sample_rate=result.sample_rate,
            engine=tts_engine.name,
            elapsed_ms=_elapsed_ms(started),
        )

    # ── 실기기 시험표 (앱 맨 아래) ─────────────────────────
    def _check_device(device: str) -> None:
        if not is_valid_device(device):
            raise HTTPException(status_code=422, detail="기기 이름은 영문 소문자·숫자·- 만 쓸 수 있어요(예: ios-27-0-1).")

    @app.get("/test-cases")
    def test_cases() -> dict[str, list[dict]]:
        return {"cases": TEST_CASES}

    @app.get("/test-sheet/{device}/draft")
    def get_draft(device: str) -> dict:
        _check_device(device)
        results = {
            case_id: SheetResult.model_validate(body).model_dump(by_alias=True)
            for case_id, body in sheet_store.load_draft(device).items()
            if case_id in CASES_BY_ID
        }
        return {"device": device, "results": results}

    @app.put("/test-sheet/{device}/draft/{case_id}")
    def save_draft_case(device: str, case_id: str, result: SheetResult) -> dict:
        _check_device(device)
        if case_id not in CASES_BY_ID:
            raise HTTPException(status_code=404, detail="없는 시험 문장 번호예요.")
        saved = sheet_store.save_draft_case(device, case_id, result)
        return SheetResult.model_validate(saved).model_dump(by_alias=True)

    @app.delete("/test-sheet/{device}/draft")
    def clear_draft(device: str) -> dict[str, str]:
        _check_device(device)
        sheet_store.clear_draft(device)
        return {"status": "cleared"}

    @app.post("/test-sheet/{device}/attempts")
    def save_attempt(device: str) -> dict:
        _check_device(device)
        tts_label = tts_label_for(settings.tts_engine, settings.tts_model_id)
        try:
            return sheet_store.save_attempt(device, tts_label=tts_label)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/test-sheet/{device}/attempts")
    def list_attempts(device: str) -> dict[str, list[dict]]:
        _check_device(device)
        return {"attempts": sheet_store.list_attempts(device)}

    @app.post("/demo/reset")
    def reset_demo() -> dict[str, str]:
        """시험 기록(장보기·부탁·당번 등)을 처음 시험 데이터로 되돌린다."""
        if not isinstance(answer_provider, FamilyDemoAnswerProvider):
            raise HTTPException(status_code=404, detail="지금 답 모드에는 시험 기록이 없어요.")
        answer_provider.reset()
        return {"status": "reset"}

    @app.get("/audio/{audio_id}")
    def get_audio(audio_id: str) -> FileResponse:
        path = audio_store.get(audio_id)
        if path is None or not path.exists():
            raise HTTPException(status_code=404, detail="음성을 찾을 수 없습니다.")
        return FileResponse(path, media_type="audio/wav")

    return app


app = create_app()
