"""가족 기록 주제별 시험 답 (규칙 기반). 스펙: .scratch/family-shared-tasks/spec.md

일정·병원 예약(C1·C2·C6·C7)과 부부가 같이 챙기는 일 10가지(D1~D25)를 다룬다.
기록은 서버 메모리에 두어 모든 폰이 같은 내용을 본다. 기록을 바꾸는 말은
"내가 …했어" 또는 "…했다고 체크해줘"처럼 말해야 한다(질문과 구분).
"""

import re
import threading
from datetime import date, datetime, timedelta

from app.family_records import (
    SPEAKER_LABELS,
    WEEKDAY_NAMES,
    FamilyRecords,
    FamilyRequest,
    copula,
    format_date,
    format_won,
    obj,
    other_speaker,
    parse_won,
    spaced_words,
    subject,
    topic,
)
from app.normalize import native_korean

DONE_MARKERS = ("내가", "했다고", "냈다고", "보냈다고", "먹였다고", "샀다고", "체크", "표시해")
CHANGE_MARKERS = ("바꿔", "가는걸로", "갈게", "간다고", "하는걸로")
SPEND_WORDS = ("썼어", "썼다", "결제했", "지출했")
BOUGHT_WORDS = ("샀어", "샀다", "샀고", "샀음")
RECIPIENTS = {"남편": "husband", "신랑": "husband", "아내": "wife", "와이프": "wife"}
# 받는 사람 없이 "약국 들러 달라고 부탁해 줘" → 배우자에게(폰 STT 가 "남편한테"를 빼먹은 실기기 사례)
REQUEST_WITHOUT_RECIPIENT = re.compile(r"^(.+?)\s*(?:해\s*)?(?:달라고|주라고|하라고)\s*부탁")
REQUEST_PATTERN = re.compile(
    r"(남편|신랑|아내|와이프|여보)\s*(?:한테|에게|께)\s+(.+?)\s*(?:해\s*)?(?:달라고|주라고|하라고)?\s*부탁"
)
ITEMS_AFTER_LIST = re.compile(r"(?:목록에|장보기에)\s+(.+?)\s*(?:좀\s+)?(?:넣어|추가|적어)")
# "장보기"라는 말 없이 장보기 목록을 묻는 말 (비교용 글 기준: 공백 없음)
SHOPPING_QUERY = re.compile(r"살거|살것|사야할거|사야할것|사야될거|사야돼|사야되|뭐사야|사올거")
# "장보기"라는 말 없이 넣어 달라고 해도 장보기로 보는 물건
GROCERY_WORDS = (
    "우유", "기저귀", "두부", "계란", "달걀", "휴지", "물티슈", "라면", "생수", "세제",
    "사과", "바나나", "빵", "쌀", "고기", "분유", "치약", "샴푸",
)
ADD_WORDS = ("넣어", "추가", "적어")
# 장보기가 아닌 다른 주제 말 (앞 턴이 장보기였어도 이 말이 있으면 장보기로 보지 않는다)
NOT_SHOPPING_WORDS = ("선물", "생신", "생일", "용돈", "생활비", "관리비", "가스비", "통신비", "부탁", "일정")
# 아이 준비물을 묻는 다른 말
SUPPLY_WORDS = ("준비물", "챙겨가", "챙겨갈", "챙길거", "가져가", "가져갈")
ITEM_SUFFIX = re.compile(r"(?:이랑|랑|하고|좀)$")
ITEM_STOPWORDS = {"좀", "목록", "목록에", "그리고", "장보기", "장보기에"}
EXPIRY_KEYS = {
    "자동차 보험": ("보험",),
    "자동차 정기검사": ("정기검사", "자동차검사", "차검사"),
    "남편 여권": ("여권",),
}
LIEUL_INDEX = 8


NAMED_SUBJECT = re.compile(r"(아내|남편)(?:가|이)")
PAST_DONE = re.compile(r"(?:샀|냈|했|보냈|먹였|챙겼)(?:어|어요|음|다|습니다)?$")
PERSON_KEYS = {"아내": "wife", "남편": "husband"}


def _done_by(text: str, speaker: str, asking: bool) -> str | None:
    """기록을 바꾸는 말이면 한 사람, 아니면 None.

    문장 속 사람("아내가 냈어", "남편이 했다고 체크해줘")을 먼저 보고, 없으면 기본 사람(speaker)으로 본다.
    물음표로 끝나는 말("남편이 냈어?")은 묻는 말로 보고 기록하지 않는다.
    """
    if asking:
        return None
    named = NAMED_SUBJECT.search(text)
    actor = PERSON_KEYS[named.group(1)] if named else speaker
    if any(marker in text for marker in DONE_MARKERS):
        return actor
    if named and PAST_DONE.search(text):
        return actor
    return None


def _ro(word: str) -> str:
    """조사 (으)로: 받침이 있으면 '으로', 없거나 ㄹ 받침이면 '로'."""
    last = word[-1]
    code = ord(last) - 0xAC00
    if 0 <= code <= 0xD7A3 - 0xAC00 and code % 28 not in (0, LIEUL_INDEX):
        return word + "으로"
    return word + "로"


def _resolve_day(text: str, today: date) -> tuple[int, date | None] | None:
    """(요일 번호, 날짜) — '오늘/내일/모레'면 날짜까지, 'O요일'이면 요일만."""
    for offset, word in ((2, "모레"), (1, "내일"), (0, "오늘")):
        if word in text:
            day = today + timedelta(days=offset)
            return day.weekday(), day
    for index, name in enumerate(WEEKDAY_NAMES):
        if f"{name}요일" in text:
            return index, None
    return None


def _named_person(text: str, speaker: str) -> str | None:
    if "남편" in text or "신랑" in text:
        return "husband"
    if "아내" in text or "와이프" in text:
        return "wife"
    if "내가" in text or "나로" in text:
        return speaker
    return None


def _extract_items(words: str) -> list[str]:
    match = ITEMS_AFTER_LIST.search(words)
    segment = match.group(1) if match else re.split(r"장\s*보기|장\s*볼|\s(?:좀\s+)?(?:넣어|추가|적어)", words)[0]
    items: list[str] = []
    for token in segment.split():
        token = ITEM_SUFFIX.sub("", token)
        if token and token not in ITEM_STOPWORDS and token not in items:
            items.append(token)
    return items


class FamilyTopics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = FamilyRecords()
        self._asking = False
        self._last_topic = ""

    def reset(self) -> None:
        with self._lock:
            self._state = FamilyRecords()

    def answer(
        self, question: str, text: str, speaker: str, now: datetime, *, last_topic: str = ""
    ) -> tuple[str | None, str]:
        """(답, 답한 주제 이름). 맞는 주제가 없으면 (None, ""). text 는 compact_question 결과.

        last_topic 은 바로 앞 턴에 답한 주제(예: "shopping"): 주제 말이 빠진 말을 푸는 데 쓴다.
        """
        words = spaced_words(question)
        today = now.date()
        # 물음표로 끝나면 묻는 말: "남편이 냈어?" 는 기록하지 않는다.
        asking = question.strip().endswith("?")
        handlers = (
            self._requests,
            self._shopping,
            self._bills,
            self._expenses,
            self._childcare,
            self._chores,
            self._family_events,
            self._expiries,
            self._school,
            self._pet,
            self._father_hospital,
            self._soyun_schedule,
            self._family_schedule,
        )
        with self._lock:
            self._asking = asking
            self._last_topic = last_topic
            for handler in handlers:
                reply = handler(text, words, speaker, today)
                if reply:
                    return reply, handler.__name__.lstrip("_")
        return None, ""

    # 6. 부탁 주고받기
    def _requests(self, text: str, words: str, speaker: str, today: date) -> str | None:
        """부탁 보내기·묻기·끝내기. 누구에게/누가는 문장 속 남편·아내로 알아듣는다.

        - 보내기: "남편한테 ~ 달라고 부탁해줘" → 아내가 남편에게(보낸 사람은 받는 사람의 배우자)
        - 묻기: "남편한테 온 부탁 뭐 있어?", "나한테 온 부탁"(기본 사람)
        - 끝내기: "남편이 (약국) 부탁 다 했어"
        """
        if "부탁" not in text:
            return None
        state = self._state
        asking_me = any(word in text for word in ("나한테", "내게", "나에게"))
        sending = "부탁해" in text or "달라고" in text
        match = REQUEST_PATTERN.search(words)
        if sending and match and not asking_me:
            name, content = match.groups()
            recipient = other_speaker(speaker) if name == "여보" else RECIPIENTS[name]
            sender = speaker if name == "여보" else other_speaker(recipient)
            return self._send_request(sender, recipient, content)
        loose = REQUEST_WITHOUT_RECIPIENT.search(words)
        if sending and loose and not asking_me and "부탁한" not in text:
            return self._send_request(speaker, other_speaker(speaker), loose.group(1))

        sent_by = re.search(r"(아내|남편)(?:가|이)부탁한|(내)가부탁한", text)
        if sent_by:
            sender = PERSON_KEYS[sent_by.group(1)] if sent_by.group(1) else speaker
            label = SPEAKER_LABELS[sender]
            sent = [item for item in state.requests if item.sender == sender and not item.done]
            if not sent:
                return f"{subject(label)} 보낸 부탁 중 남은 게 없어요."
            listed = ", ".join(f"{SPEAKER_LABELS[item.recipient]}에게 보낸 '{item.content}'" for item in sent)
            return f"{subject(label)} 보낸 부탁 중 남은 건 {len(sent)}건이에요. {copula(listed)}"

        to_named = re.search(r"(아내|남편)(?:한테|에게)", text)
        finisher = NAMED_SUBJECT.search(text)
        if any(word in text for word in ("다했", "완료", "끝냈", "했다고")):
            owner = PERSON_KEYS[finisher.group(1)] if finisher else speaker
            pending = [item for item in state.requests if item.recipient == owner and not item.done]
            if not pending:
                return f"{SPEAKER_LABELS[owner]}에게 남은 부탁이 없어요."
            finished = pending[-1]
            finished.done = True
            return f"'{finished.content}' 부탁을 끝낸 걸로 표시했어요."

        owner = PERSON_KEYS[to_named.group(1)] if to_named and not asking_me else speaker
        label = SPEAKER_LABELS[owner]
        received = [item for item in state.requests if item.recipient == owner and not item.done]
        if not received:
            return f"{label}에게 온 부탁이 없어요."
        listed = ", ".join(f"{subject(SPEAKER_LABELS[item.sender])} 부탁한 '{item.content}'" for item in received)
        return f"{label}에게 온 부탁은 {len(received)}건이에요. {copula(listed)}"

    def _send_request(self, speaker: str, recipient: str, content: str) -> str:
        content = content.removesuffix(" 좀").strip()
        self._state.requests.append(FamilyRequest(speaker, recipient, content))
        return f"{SPEAKER_LABELS[recipient]}에게 '{content}' 부탁을 보냈어요."

    # 1. 장보기 목록
    def _shopping(self, text: str, words: str, speaker: str, today: date) -> str | None:
        state = self._state
        has_list = any(word in text for word in ("장보기", "장볼", "장봐"))
        removing = any(word in text for word in BOUGHT_WORDS) or (
            has_list and any(word in text for word in ("지워", "빼줘", "삭제"))
        )
        if removing:
            found = [item for item in state.shopping if item in text]
            if not found:
                return "장보기 목록에서 그 물건을 못 찾았어요." if has_list else None
            for item in found:
                state.shopping.remove(item)
            tail = f" 남은 건 {copula(', '.join(state.shopping))}" if state.shopping else " 이제 목록이 비었어요."
            return f"{topic(', '.join(found))} 장보기 목록에서 뺐어요.{tail}"
        adding = any(word in text for word in ADD_WORDS)
        other_topic = any(word in text for word in NOT_SHOPPING_WORDS)
        if not has_list and not other_topic:
            # "살 거 뭐 있어?" / "우유랑 기저귀 추가해줘"(앞 턴이 장보기였거나 장보기 물건이 있을 때)
            has_list = bool(SHOPPING_QUERY.search(text)) or (
                adding and (self._last_topic == "shopping" or any(word in text for word in GROCERY_WORDS))
            )
        if not has_list:
            return None
        if adding:
            items = _extract_items(words)
            if not items:
                return "장보기 목록에 넣을 물건을 같이 말해 주세요."
            state.shopping.extend(item for item in items if item not in state.shopping)
            return f"장보기 목록에 {obj(', '.join(items))} 넣었어요. 지금 목록은 {copula(', '.join(state.shopping))}"
        if not state.shopping:
            return "장보기 목록이 비어 있어요."
        return f"장보기 목록은 {', '.join(state.shopping)} {copula(f'{len(state.shopping)}가지')}"

    # 2. 공과금·고정 지출
    def _bills(self, text: str, words: str, speaker: str, today: date) -> str | None:
        state = self._state
        # 영어로 받아 적은 이름도 같은 고지서로 본다(E1: STT 가 'Netflix'로 적을 수 있다).
        text = re.sub("netflix", "넷플릭스", text, flags=re.IGNORECASE)
        name = next((bill_name for bill_name in state.bills if bill_name in text), None)
        if name is None:
            if "공과금" not in text and "고정지출" not in text:
                return None
            unpaid = [(n, bill) for n, bill in state.bills.items() if not bill.paid_by and not bill.auto_pay_day]
            if not unpaid:
                return "이번 달 공과금은 다 냈어요."
            listed = ", ".join(f"{n} {format_won(bill.amount)}" for n, bill in unpaid)
            return f"아직 안 낸 공과금은 {copula(listed)}"
        bill = state.bills[name]
        label = f"{name} {format_won(bill.amount)}"
        actor = _done_by(text, speaker, self._asking)
        if actor:
            bill.paid_by, bill.paid_on = actor, today
            return f"{topic(label)} {subject(SPEAKER_LABELS[actor])} {format_date(today, today)}에 낸 걸로 기록했어요."
        due = re.search(r"(\d{1,2})일까지", text)
        if due:
            try:
                bill.due = date(today.year, today.month, int(due.group(1)))
            except ValueError:
                return "납부 날짜를 다시 말해 주세요."
            return f"{name} 납부 기한을 {_ro(format_date(bill.due, today))} 적었어요."
        if bill.auto_pay_day:
            return f"{topic(label)} 매달 {bill.auto_pay_day}일 자동이체예요."
        if bill.paid_by and bill.paid_on:
            return f"{topic(label)} {subject(SPEAKER_LABELS[bill.paid_by])} {format_date(bill.paid_on, today)}에 냈어요."
        due_text = f" {format_date(bill.due, today)}까지 내야 해요." if bill.due else ""
        return f"{topic(label)} 아직 안 냈어요.{due_text}"

    # 3. 지출 기록(생활비)
    def _expenses(self, text: str, words: str, speaker: str, today: date) -> str | None:
        spending = any(word in text for word in SPEND_WORDS)
        if not spending and "생활비" not in text and "가계부" not in text:
            return None
        state = self._state
        amount = parse_won(text)
        if spending and not ("얼마" in text and amount is None):
            if amount is None:
                return "얼마를 썼는지 금액을 같이 말해 주세요."
            place_match = re.search(r"(\S+?)에서", words)
            place = place_match.group(1) if place_match else "지출"
            state.spent += amount
            state.expenses.append((speaker, place, amount))
            return f"{place} {obj(format_won(amount))} 기록했어요. {self._budget_left()}"
        return (
            f"이번 달 생활비 {format_won(state.budget)} 중 {obj(format_won(state.spent))} 써서 "
            f"{self._budget_left(short=True)}"
        )

    def _budget_left(self, *, short: bool = False) -> str:
        left = self._state.budget - self._state.spent
        if left < 0:
            return f"예산을 {format_won(-left)} 넘었어요."
        return f"{format_won(left)} 남았어요." if short else f"이번 달 생활비는 {format_won(left)} 남았어요."

    # 4. 육아 분담 (어린이집 등원·하원)
    def _childcare(self, text: str, words: str, speaker: str, today: date) -> str | None:
        kind = "하원" if "하원" in text else "등원" if "등원" in text else None
        if kind is None:
            return None
        table = self._state.pickup if kind == "하원" else self._state.dropoff
        resolved = _resolve_day(text, today)
        if any(word in text for word in CHANGE_MARKERS):
            if resolved is None:
                return f"어느 요일 {kind}인지 같이 말해 주세요."
            if resolved[0] >= 5:
                return "주말에는 어린이집이 쉬어요."
            person = _named_person(text, speaker)
            if person is None:
                return f"누가 {kind}할지 같이 말해 주세요."
            table[resolved[0]] = person
            return f"{WEEKDAY_NAMES[resolved[0]]}요일 {topic(kind)} {subject(SPEAKER_LABELS[person])} 가는 걸로 바꿨어요."
        weekday, day = resolved if resolved else (today.weekday(), today)
        when = format_date(day, today, weekday=True) if day else f"{WEEKDAY_NAMES[weekday]}요일"
        if weekday >= 5:
            return f"{topic(when)} 어린이집이 쉬어요."
        return f"{when} {topic(kind)} {subject(SPEAKER_LABELS[table[weekday]])} 가요."

    # 5. 집안일 당번
    def _chores(self, text: str, words: str, speaker: str, today: date) -> str | None:
        chores = self._state.chores
        name = next((chore_name for chore_name in chores if chore_name in text), None)
        if name is None:
            if not any(word in text for word in ("당번", "집안일", "차례")):
                return None
            listed = ", ".join(
                f"{chore.period} {topic(n)} {SPEAKER_LABELS[chore.assignee]}" for n, chore in chores.items()
            )
            return f"{listed} 차례예요."
        chore = chores[name]
        head = f"{chore.period} {topic(name)}"
        actor = _done_by(text, speaker, self._asking)
        if actor:
            chore.done_by = actor
            return f"{head} {subject(SPEAKER_LABELS[actor])} 한 걸로 체크했어요."
        status = f" {subject(SPEAKER_LABELS[chore.done_by])} 했어요." if chore.done_by else " 아직 안 했어요."
        return f"{head} {SPEAKER_LABELS[chore.assignee]} 차례예요.{status}"

    # 7. 양가 챙기기 (용돈·생신)
    def _family_events(self, text: str, words: str, speaker: str, today: date) -> str | None:
        state = self._state
        if "용돈" in text:
            if any(word in text for word in ("친정", "처가")):
                sides = ["친정"]
            elif any(word in text for word in ("시댁", "본가", "시가")):
                sides = ["시댁"]
            else:
                sides = list(state.allowances)
            replies = []
            for side in sides:
                allowance = state.allowances[side]
                label = f"이번 달 {side} 용돈 {format_won(allowance.amount)}"
                actor = _done_by(text, speaker, self._asking)
                if actor and len(sides) == 1:
                    allowance.sent_by = actor
                    return f"{topic(label)} {subject(SPEAKER_LABELS[actor])} 보낸 걸로 기록했어요."
                if allowance.sent_by:
                    replies.append(f"{topic(label)} {subject(SPEAKER_LABELS[allowance.sent_by])} 보냈어요.")
                else:
                    replies.append(
                        f"{topic(label)} 아직 안 보냈어요. 매달 {allowance.day_of_month}일에 보내기로 했어요."
                    )
            return " ".join(replies)
        if not any(word in text for word in ("생신", "생일", "선물")):
            return None
        if any(word in text for word in ("시어머니", "어머님", "시댁")):
            who = "시어머니"
        elif any(word in text for word in ("친정엄마", "친정어머니", "장모", "친정")):
            who = "친정엄마"
        else:
            return None
        birthday = state.birthdays[who]
        if birthday.gift and birthday.gift_owner:
            gift = f" 선물은 {_ro(birthday.gift)} 정했고, {subject(SPEAKER_LABELS[birthday.gift_owner])} 주문하기로 했어요."
        else:
            gift = " 선물은 아직 안 정했어요."
        return f"{who} 생신은 {copula(format_date(birthday.day, today))}{gift}"

    # 8. 만기·갱신
    def _expiries(self, text: str, words: str, speaker: str, today: date) -> str | None:
        expiries = self._state.expiries
        name = next((n for n, keys in EXPIRY_KEYS.items() if any(key in text for key in keys)), None)
        if name:
            day = expiries[name]
            left = (day - today).days
            if left < 0:
                return f"{topic(name)} {format_date(day, today)}에 이미 끝났어요."
            return f"{topic(name)} {format_date(day, today)}에 끝나요. {left}일 남았어요."
        if not any(word in text for word in ("만기", "만료", "갱신")):
            return None
        upcoming = sorted((day, n) for n, day in expiries.items() if day >= today)
        if not upcoming:
            return "곧 끝나는 건 없어요."
        listed = ", ".join(f"{n} {format_date(day, today)}" for day, n in upcoming)
        return f"곧 끝나는 건 {copula(listed)}"

    # 9. 아이 준비물·서류
    def _school(self, text: str, words: str, speaker: str, today: date) -> str | None:
        state = self._state
        if "동의서" in text:
            actor = _done_by(text, speaker, self._asking)
            if actor:
                state.consent_submitted_by = actor
                return f"현장학습 동의서는 {subject(SPEAKER_LABELS[actor])} 낸 걸로 표시했어요."
            if state.consent_submitted_by:
                return f"현장학습 동의서는 {subject(SPEAKER_LABELS[state.consent_submitted_by])} 냈어요."
            return f"현장학습 동의서는 아직 안 냈어요. {format_date(state.consent_due, today)}까지 내야 해요."
        if not any(word in text for word in SUPPLY_WORDS):
            return None
        resolved = _resolve_day(text, today)
        if resolved and resolved[1]:
            day = resolved[1]
        elif resolved:
            day = today + timedelta(days=(resolved[0] - today.weekday()) % 7)
        else:
            day = today + timedelta(days=1)
        items = state.supplies.get(day)
        if not items:
            prepared = ", ".join(format_date(d, today, weekday=True) for d in sorted(state.supplies))
            return f"{format_date(day, today, weekday=True)} 준비물은 시험 데이터에 없어요. 준비된 날은 {copula(prepared)}"
        return f"{format_date(day, today, weekday=True)} 소윤이 준비물은 {copula(', '.join(items))}"

    # 10. 반려동물
    def _pet(self, text: str, words: str, speaker: str, today: date) -> str | None:
        if not any(word in text for word in ("콩이", "강아지", "심장사상충")):
            return None
        pet = self._state.pet
        if any(word in text for word in ("백신", "접종", "예방주사")):
            return f"콩이 종합백신은 {format_date(pet.vaccine_on, today)} 예정이에요."
        actor = _done_by(text, speaker, self._asking)
        if actor:
            pet.medicine_last_on, pet.medicine_last_by = today, actor
            return f"이번 달 콩이 심장사상충 약은 {subject(SPEAKER_LABELS[actor])} 먹인 걸로 기록했어요."
        base = f"콩이 심장사상충 약은 매달 {pet.medicine_day}일에 먹여요."
        given = (pet.medicine_last_on.year, pet.medicine_last_on.month) == (today.year, today.month)
        if not given:
            return f"{base} 이번 달은 아직 안 먹였어요."
        next_month = date(today.year + today.month // 12, today.month % 12 + 1, pet.medicine_day)
        return (
            f"{base} 이번 달은 {format_date(pet.medicine_last_on, today)}에 "
            f"{subject(SPEAKER_LABELS[pet.medicine_last_by])} 먹였고, 다음은 {copula(format_date(next_month, today))}"
        )

    # C6. 아버지 병원 예약 (등록일과 예약일을 구분) · E2. 혈압약이 떨어졌을 때 다음 진료
    def _father_hospital(self, text: str, words: str, speaker: str, today: date) -> str | None:
        if not (("아버지" in text or "아빠" in text) and "병원" in text):
            return None
        visit = self._state.father_hospital
        if "혈압약" in text or "처방" in text:
            return (
                f"아버지 다음 진료는 {format_date(visit.visit_on, today, weekday=True)} {copula(visit.time_text)} "
                "혈압약 처방은 그때 받으면 돼요."
            )
        if "예약" not in text:
            return None
        return (
            f"{format_date(visit.registered_on, today)}에 등록한 아버지 병원 예약은 "
            f"{format_date(visit.visit_on, today, weekday=True)} {_ro(visit.time_text)} 확인돼요."
        )

    # C2·C7. 소윤이 이번 주 학교·학원 (시험 데이터는 이번 주뿐)
    def _soyun_schedule(self, text: str, words: str, speaker: str, today: date) -> str | None:
        if "소윤" not in text or not any(word in text for word in ("일정", "학교", "학원")):
            return None
        if "다음주" in text:
            return "시험 일정은 소윤이의 이번 주 학교와 학원 일정만 준비돼 있어요."
        return f"소윤이는 {_weekday_list(self._state.soyun_this_week)} 있어요."

    # C1. 다음 주 가족 일정
    def _family_schedule(self, text: str, words: str, speaker: str, today: date) -> str | None:
        if not ("다음주" in text and ("우리집" in text or "가족" in text) and "일정" in text):
            return None
        events = self._state.next_week_family
        return (
            f"다음 주 가족 일정은 {native_korean(len(events))} 건이에요. "
            f"{_weekday_list(events)} 있어요."
        )


def _weekday_list(events: list[tuple[str, str]]) -> str:
    """[("수", "학교 체험학습"), ("금", "피아노 학원")] → '수요일에 학교 체험학습, 금요일에 피아노 학원이'."""
    listed = ", ".join(f"{weekday}요일에 {name}" for weekday, name in events)
    return subject(listed)
