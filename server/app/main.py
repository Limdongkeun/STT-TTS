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
from dataclasses import replace
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
from app.engines.qwen3_tts_107 import Tts107Error
from app.family_demo import DEMO_NOW, FamilyDemoAnswerProvider, FamilyDemoContext, compact_question
from app.normalize import normalize_for_speech
from app.settings import Settings, load_settings, tts_choices
from app.spoken_answers import SPOKEN_ENGINES, load_spoken_answers, spoken_for, to_spoken_style
from app.stt_correction import correct_transcript
from app.test_sheet import CASES_BY_ID, DEFAULT_RESULTS_DIR, TEST_CASES, SheetResult, SheetStore, is_valid_device, tts_label_for

# uvicorn 이 이미 출력하는 로거를 써서 서버 터미널에 바로 보이게 한다.
logger = logging.getLogger("uvicorn.error")
LOGGED_QUESTION_CHARS = 200

AUDIO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_STORED_AUDIO = 50
UPLOAD_CHUNK_BYTES = 1024 * 1024
# 시험표에 붙이는 폰 STT 소리: 16kHz 16비트 모노면 약 5분
MAX_SHEET_AUDIO_BYTES = 10 * 1024 * 1024


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
    # 앱이 고른 TTS 엔진(없으면 서버 기본). 사전 녹음일 때만 C4·C5 읽기용 글을 녹음에 맞춰 줄인다.
    tts_engine: str | None = Field(default=None, max_length=40)


class AskResponse(ApiModel):
    answer_text: str
    speech_text: str
    provider: str
    elapsed_ms: int
    context: FamilyDemoContext | None = None
    # family-demo 가 보정한 뒤의 글(띄어쓰기·문장부호 없음). 시험표에 보정 전·후를 함께 남긴다.
    corrected_text: str | None = None


class TtsRequest(ApiModel):
    text: str = Field(min_length=1, max_length=1000)
    normalize: bool = False
    # 앱이 고른 TTS 엔진(없으면 서버 기본). /health 의 ttsChoices 안에서만 고를 수 있다.
    engine: str | None = Field(default=None, max_length=40)


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
    choices = tts_choices(settings)
    spoken_answers = load_spoken_answers() if settings.spoken_answers == "on" else {}

    def reads_spoken(engine_name: str) -> bool:
        """이 TTS 가 시험 답을 입말 문장으로 읽는지."""
        return bool(spoken_answers) and engine_name in SPOKEN_ENGINES
    # 앱이 요청마다 고르는 TTS. 기본 엔진 말고는 처음 고를 때 만든다(107 은 이때도 부르지 않는다).
    tts_engines = {settings.tts_engine: tts_engine}

    def pick_tts_engine(name: str | None):
        key = name or settings.tts_engine
        if key not in choices:
            raise HTTPException(status_code=422, detail=f"이 서버에서 고를 수 없는 TTS예요: {key[:40]}")
        if key not in tts_engines:
            tts_engines[key] = create_tts_engine(replace(settings, tts_engine=key))
        return tts_engines[key]

    def tts_record_label(name: str) -> str:
        """저장본·시험표에 적는 TTS 이름(예전 저장본과 같은 글). 입말로 읽으면 '· 입말'을 붙여 따로 비교한다."""
        label = getattr(pick_tts_engine(name), "label", name) if name == "qwen3-tts-107" else tts_label_for(
            name, settings.tts_model_id
        )
        return f"{label} · 입말" if reads_spoken(name) else label
    answer_provider = (
        FamilyDemoAnswerProvider() if settings.answer_provider == "family-demo" else create_answer_provider(settings)
    )
    work_dir = Path(tempfile.mkdtemp(prefix="stt-tts-"))
    sheet_store = SheetStore(Path(settings.test_results_dir) if settings.test_results_dir else DEFAULT_RESULTS_DIR)
    audio_store = AudioStore(work_dir)

    app = FastAPI(title="STT-TTS 시험 서버", version="0.1.0")

    def tts_model_label() -> str:
        """/health·저장본에 적는 TTS 이름. mock 은 빈 글."""
        if settings.tts_engine == "prerecorded":
            return VOICE_LABEL
        if settings.tts_engine == "qwen3-tts":
            return settings.tts_model_id
        return getattr(tts_engine, "label", "")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "sttEngine": stt_engine.name,
            "sttModel": settings.asr_model_id if settings.stt_engine == "qwen3-asr" else "",
            "ttsEngine": tts_engine.name,
            "ttsModel": tts_model_label(),
            "answerProvider": answer_provider.name,
            "demoClock": settings.demo_clock,
            # 서버 STT 에 넣는 힌트 낱말 수(0 = 힌트 없음). 폰 STT 는 늘 같은 목록을 쓴다.
            "sttHints": getattr(stt_engine, "hint_count", 0),
            # 앱 버튼으로 고를 수 있는 TTS(서버 하나로 합쳐 띄울 때). label 은 시험표에 적히는 이름.
            "ttsChoices": [{"engine": name, "label": tts_record_label(name)} for name in choices],
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
        corrected_text = None
        if isinstance(answer_provider, FamilyDemoAnswerProvider):
            corrected_text = correct_transcript(compact_question(text))
            demo_now = DEMO_NOW if settings.demo_clock == "fixed" else None
            answer_text, context = answer_provider.answer(text, request.context, speaker=request.speaker, now=demo_now)
        else:
            answer_text = answer_provider.answer(text)
        speech_text = answer_text
        chosen_tts = request.tts_engine or settings.tts_engine
        # 화면 답은 그대로, 소리만 입말로(그때그때 만드는 TTS 일 때만). 시험 답 목록에 없으면 규칙으로 다듬는다.
        if reads_spoken(chosen_tts):
            speech_text = spoken_for(answer_text, spoken_answers) or to_spoken_style(answer_text)
        if chosen_tts == "prerecorded" and context and context.dose_at and answer_text.startswith("시험 기록에 "):
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
            corrected_text=corrected_text,
        )

    @app.post("/tts", response_model=TtsResponse)
    def text_to_speech(request: TtsRequest) -> TtsResponse:
        started = time.perf_counter()
        text = normalize_for_speech(request.text) if request.normalize else request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="읽을 글이 없습니다.")
        try:
            engine = pick_tts_engine(request.engine)
            result = engine.synthesize(text)
        except RecordingUnavailableError as exc:
            # 404: 이 답의 녹음이 없다(앱은 오류 대신 화면 답만 보여 준다). 422 는 요청 모양 오류로 남겨 둔다.
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Tts107Error as exc:
            # 503: 107 TTS 를 지금 못 쓴다(회사 망 밖, 시험 페이지 꺼짐, 시간 초과). 앱은 이 안내를 보여 준다.
            logger.warning("tts107 failed: %s", exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        audio_id = audio_store.save(result.wav_bytes)
        return TtsResponse(
            audio_url=f"/audio/{audio_id}",
            duration_sec=round(result.duration_sec, 3),
            sample_rate=result.sample_rate,
            engine=engine.name,
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

    @app.put("/test-sheet/{device}/draft/{case_id}/audio")
    def save_draft_audio(device: str, case_id: str, audio: UploadFile = File(...)) -> dict[str, str]:
        """폰 STT 가 들은 소리(WAV)를 받아 둔다. 돌려준 파일 이름을 앱이 그 문장의 audioFile 에 적는다."""
        _check_device(device)
        if case_id not in CASES_BY_ID:
            raise HTTPException(status_code=404, detail="없는 시험 문장 번호예요.")
        data = _read_limited(audio, MAX_SHEET_AUDIO_BYTES)
        try:
            name = sheet_store.save_draft_audio(device, case_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        return {"audioFile": name}

    @app.delete("/test-sheet/{device}/draft")
    def clear_draft(device: str) -> dict[str, str]:
        _check_device(device)
        sheet_store.clear_draft(device)
        return {"status": "cleared"}

    @app.post("/test-sheet/{device}/attempts")
    def save_attempt(device: str) -> dict:
        _check_device(device)
        # 턴마다 앱이 적은 TTS 이름이 있으면 그걸 쓰고(시험표 안에서 TTS 를 바꿀 수 있다), 없으면 서버 기본.
        tts_label = tts_record_label(settings.tts_engine)
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
