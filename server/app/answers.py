"""질문 글 → 답 글. 기존 LLM·DB 연결 자리.

지금은 연결 정보가 없어서 고정 답만 돌려준다.
실제 LLM·DB 를 붙일 때는 AnswerProvider 를 구현한 클래스를 추가하고
create_answer_provider 에 분기를 넣는다. 키·주소는 환경변수로 받는다.
"""

from typing import Protocol

from app.settings import Settings

FIXED_ANSWER = (
    "내일 가족 일정은 두 개예요. "
    "오후 3시 30분에 외할머니 병원 예약이 있어요. "
    "저녁 7시에는 가족 식사가 있고, 4명이 와요."
)


class AnswerProvider(Protocol):
    name: str

    def answer(self, question: str) -> str: ...


class FixedAnswerProvider:
    name = "fixed"

    def answer(self, question: str) -> str:
        return FIXED_ANSWER


def create_answer_provider(settings: Settings) -> AnswerProvider:
    return FixedAnswerProvider()
