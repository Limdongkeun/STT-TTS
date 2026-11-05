"""가족 돌봄 대화 시험용 가상 일정과 복용 기록."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

KST = ZoneInfo("Asia/Seoul")
RELATIVE_TIME = re.compile(r"(?<![0-9])(?:(?P<hours>[0-9]{1,2})시간|(?P<minutes>[0-9]{1,3})분)전")
KOREAN_NUMBERS = {"한시간": "1시간", "두시간": "2시간", "삼십분": "30분"}


class FamilyDemoContext(BaseModel):
    awaiting_dose_time: bool = False
    dose_at: datetime | None = None


class FamilyDemoAnswerProvider:
    name = "family-demo"

    def answer(
        self, question: str, context: FamilyDemoContext | None = None, *, now: datetime | None = None
    ) -> tuple[str, FamilyDemoContext | None]:
        text = re.sub(r"\s+", "", question)
        if ("아버지" in text or "아빠" in text) and "병원" in text and "예약" in text:
            return "11월 2일에 등록한 아버지 병원 예약은 11월 12일 목요일 오전 10시로 확인돼요.", None
        if "소윤" in text and "일정" in text:
            if "이번주" in text and "학교" in text and "학원" in text:
                return "소윤이는 수요일에 학교 체험학습, 금요일에 피아노 학원이 있어요.", None
            return "시험 일정은 소윤이의 이번 주 학교와 학원 일정만 준비돼 있어요.", None
        if "다음주" in text and ("우리집" in text or "가족" in text) and "일정" in text:
            return "다음 주 가족 일정은 두 건이에요. 화요일에 가족 식사, 토요일에 장보기가 있어요.", None

        if "해열제" in text and ("부르펜" in text or "브루펜" in text) and any(
            word in text for word in ("애기", "아기", "아이")
        ):
            context = FamilyDemoContext(awaiting_dose_time=True)
        if context:
            return self._answer_dose(text, context, now if now is not None else datetime.now(KST))
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
