"""가족 돌봄 대화 시험 답(family-demo)의 입구.

주제별 가족 기록 답은 family_topics.py, 시험 데이터는 family_records.py 에 있다.
여기서는 질문 정리와, 앱이 상태(context)를 들고 다니는 해열제 복용 시각 대화(C3~C5)를 맡는다.
"""

import logging
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.family_topics import FamilyTopics
from app.stt_correction import correct_transcript

KST = ZoneInfo("Asia/Seoul")
# uvicorn 이 이미 출력하는 로거: 보정 전후를 서버 터미널에서 바로 본다.
logger = logging.getLogger("uvicorn.error")
RELATIVE_TIME = re.compile(r"(?<![0-9])(?:(?P<hours>[0-9]{1,2})시간|(?P<minutes>[0-9]{1,3})분)전")
KOREAN_NUMBERS = {"한시간": "1시간", "두시간": "2시간", "삼십분": "30분"}


def compact_question(question: str) -> str:
    """비교용 글: 한글 표준형(NFC)으로 맞추고 글자·숫자만 남긴다.

    폰 STT 글에는 일반 공백 대신 폭 없는 공백 같은 보이지 않는 문자나 문장부호가 섞일 수 있다.
    """
    normalized = unicodedata.normalize("NFC", question)
    return "".join(char for char in normalized if unicodedata.category(char)[0] in "LN")


class FamilyDemoContext(BaseModel):
    awaiting_dose_time: bool = False
    dose_at: datetime | None = None
    # 바로 앞 턴에 답한 주제(예: "shopping"). "우유랑 기저귀 추가해줘"처럼 주제 말이 빠진 다음 말을 푼다.
    last_topic: str = Field(default="", max_length=40, pattern=r"^[a-z_]*$")


class FamilyDemoAnswerProvider:
    name = "family-demo"

    def __init__(self) -> None:
        # 가족 기록(일정·장보기·부탁·당번 등). 서버가 떠 있는 동안 모든 폰이 같이 본다.
        self._topics = FamilyTopics()

    def reset(self) -> None:
        self._topics.reset()

    def answer(
        self,
        question: str,
        context: FamilyDemoContext | None = None,
        *,
        speaker: str = "wife",
        now: datetime | None = None,
    ) -> tuple[str, FamilyDemoContext | None]:
        compact = compact_question(question)
        text = correct_transcript(compact)
        if text != compact:
            logger.info("ask corrected %r -> %r", compact, text)
        current = (now if now is not None else datetime.now(KST)).astimezone(KST)
        last_topic = context.last_topic if context else ""
        topic_reply, topic_name = self._topics.answer(question, text, speaker, current, last_topic=last_topic)
        if topic_reply:
            return topic_reply, FamilyDemoContext(last_topic=topic_name)

        if "해열제" in text and ("부르펜" in text or "브루펜" in text) and any(
            word in text for word in ("애기", "아기", "아이")
        ):
            context = FamilyDemoContext(awaiting_dose_time=True)
        if context and (context.awaiting_dose_time or context.dose_at):
            return self._answer_dose(text, context, current)
        return "이 질문에 맞는 시험 답변이 준비돼 있지 않아요.", None

    def _answer_dose(
        self, text: str, context: FamilyDemoContext, now: datetime
    ) -> tuple[str, FamilyDemoContext]:
        for spoken, digits in KOREAN_NUMBERS.items():
            text = text.replace(spoken, digits)
        times = list(RELATIVE_TIME.finditer(text))
        correction = "아니" in text or "정정" in text
        if len(times) > 1 and "아니라" in text:
            times = list(RELATIVE_TIME.finditer(text.rsplit("아니라", 1)[1]))
        if len(times) != 1 or not (context.awaiting_dose_time or (context.dose_at and correction)):
            question = "몇 시에 먹였나요?" if context.awaiting_dose_time else "복용 시각을 정정하려면 다시 말씀해 주세요."
            return question, context

        match = times[0]
        hours = int(match["hours"] or 0)
        minutes = int(match["minutes"] or 0)
        dose_at = now.astimezone(KST) - timedelta(hours=hours, minutes=minutes)
        period = "오전" if dose_at.hour < 12 else "오후"
        time_text = f"{period} {dose_at.hour % 12 or 12}시"
        if dose_at.minute:
            time_text += f" {dose_at.minute}분"
        action = "수정했어요" if context.dose_at else "기록했어요"
        return (
            f"시험 기록에 {dose_at.month}월 {dose_at.day}일 {time_text}에 먹인 걸로 {action}. "
            "가상 일정에 등록된 다음 복용 예정 시각은 오후 9시예요.",
            FamilyDemoContext(dose_at=dose_at),
        )
