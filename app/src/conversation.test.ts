// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addChat,
  appendResult,
  conversationFace,
  createSilenceTimer,
  EMPTY_TRANSCRIPT,
  formatSilenceLabel,
  isBargeIn,
  isSelfEcho,
  MAX_CHAT_ITEMS,
  MAX_CONVERSATION_ERRORS,
  nextConversationStep,
  type TimeoutReason,
  type TimerApi,
  transcriptText,
} from "./conversation.ts";

/** 손으로 시간을 넘기는 가짜 타이머. */
function createFakeTimers() {
  let now = 0;
  let nextId = 1;
  const pending = new Map<number, { at: number; callback: () => void }>();
  const timers: TimerApi = {
    set: (callback, ms) => {
      const id = nextId++;
      pending.set(id, { at: now + ms, callback });
      return id;
    },
    clear: (handle) => {
      pending.delete(handle as number);
    },
  };
  const advance = (ms: number) => {
    now += ms;
    for (const [id, item] of [...pending].sort((a, b) => a[1].at - b[1].at)) {
      if (item.at <= now && pending.has(id)) {
        pending.delete(id);
        item.callback();
      }
    }
  };
  return { timers, advance, pendingCount: () => pending.size };
}

test("nextConversationStep: 답했으면 다시 듣고 오류 수를 0으로", () => {
  assert.deepEqual(nextConversationStep(2, "answered"), { action: "listen", errors: 0 });
});

test("nextConversationStep: 말이 없으면 멈추지 않고 다시 듣는다(오류 수는 그대로)", () => {
  assert.deepEqual(nextConversationStep(0, "empty"), { action: "listen", errors: 0 });
  assert.deepEqual(nextConversationStep(1, "empty"), { action: "listen", errors: 1 });
});

test("nextConversationStep: 오류는 잠깐 뒤 다시, 연달아 한도에 닿으면 쉰다", () => {
  assert.deepEqual(nextConversationStep(0, "error"), { action: "retry", errors: 1 });
  assert.deepEqual(nextConversationStep(MAX_CONVERSATION_ERRORS - 2, "error").action, "retry");
  assert.deepEqual(nextConversationStep(MAX_CONVERSATION_ERRORS - 1, "error"), { action: "pause", errors: MAX_CONVERSATION_ERRORS });
});

test("nextConversationStep: 사용자가 멈췄으면 끝", () => {
  assert.deepEqual(nextConversationStep(1, "stopped"), { action: "stop", errors: 1 });
});

test("formatSilenceLabel", () => {
  assert.equal(formatSilenceLabel(1200), "1.2초");
  assert.equal(formatSilenceLabel(3000), "3초");
});

test("appendResult: iOS 처럼 누적 중간 결과는 마지막 것만, 확정되면 쌓는다", () => {
  let state = appendResult(EMPTY_TRANSCRIPT, "내일", false);
  state = appendResult(state, "내일 가족 일정", false);
  assert.equal(transcriptText(state), "내일 가족 일정");
  state = appendResult(state, "내일 가족 일정 알려줘", true);
  assert.equal(transcriptText(state), "내일 가족 일정 알려줘");
});

test("appendResult: 안드로이드처럼 확정 구간이 따로 오면 이어 붙인다", () => {
  let state = appendResult(EMPTY_TRANSCRIPT, "내일 가족 일정", true);
  state = appendResult(state, "알려", false);
  assert.equal(transcriptText(state), "내일 가족 일정 알려");
  state = appendResult(state, "알려줘", true);
  assert.equal(transcriptText(state), "내일 가족 일정 알려줘");
});

test("appendResult: 빈 결과와 공백은 무시한다", () => {
  let state = appendResult(EMPTY_TRANSCRIPT, "   ", true);
  state = appendResult(state, "", false);
  assert.equal(transcriptText(state), "");
  assert.deepEqual(state.finalParts, []);
});

test("createSilenceTimer: 말이 없으면 noSpeech 로 한 번 끝난다", () => {
  const fake = createFakeTimers();
  const reasons: TimeoutReason[] = [];
  const timer = createSilenceTimer(() => 1200, (reason) => reasons.push(reason), 8000, fake.timers);
  timer.start();
  fake.advance(7999);
  assert.deepEqual(reasons, []);
  fake.advance(1);
  assert.deepEqual(reasons, ["noSpeech"]);
  fake.advance(10000);
  assert.deepEqual(reasons, ["noSpeech"]);
});

test("createSilenceTimer: 글자가 들어올 때마다 쉬는 시간을 다시 잰다", () => {
  const fake = createFakeTimers();
  const reasons: TimeoutReason[] = [];
  let silenceMs = 1200;
  const timer = createSilenceTimer(() => silenceMs, (reason) => reasons.push(reason), 8000, fake.timers);
  timer.start();
  fake.advance(500);
  timer.bump();
  fake.advance(1000);
  timer.bump();
  fake.advance(1199);
  assert.deepEqual(reasons, []);
  fake.advance(1);
  assert.deepEqual(reasons, ["silence"]);
  // 설정을 바꾸면 다음 bump 부터 새 값이 쓰인다
  silenceMs = 3000;
  timer.bump();
  fake.advance(2999);
  assert.deepEqual(reasons, ["silence"]);
  fake.advance(1);
  assert.deepEqual(reasons, ["silence", "silence"]);
});

test("createSilenceTimer: cancel 하면 부르지 않고 타이머도 남기지 않는다", () => {
  const fake = createFakeTimers();
  const reasons: TimeoutReason[] = [];
  const timer = createSilenceTimer(() => 800, (reason) => reasons.push(reason), 8000, fake.timers);
  timer.start();
  timer.bump();
  timer.cancel();
  timer.cancel();
  fake.advance(20000);
  assert.deepEqual(reasons, []);
  assert.equal(fake.pendingCount(), 0);
});

test("conversationFace: 마이크가 준비된 뒤에만 '말하세요'", () => {
  assert.equal(conversationFace("listening", false, false), "preparing");
  assert.equal(conversationFace("listening", true, false), "listening");
  assert.equal(conversationFace("transcribing", false, false), "thinking");
  assert.equal(conversationFace("asking", true, false), "thinking");
  assert.equal(conversationFace("speaking", false, false), "speaking");
  assert.equal(conversationFace("idle", false, false), "preparing");
  assert.equal(conversationFace("listening", true, true), "paused");
});

test("addChat: 번호를 이어 붙이고 최근 것만 남긴다", () => {
  const two = addChat([], [{ who: "me", text: "장보기 뭐 남았어", caseId: "D1" }, { who: "bot", text: "두부, 계란" }]);
  assert.deepEqual(two.map((item) => item.id), [1, 2]);
  let many = two;
  for (let index = 0; index < MAX_CHAT_ITEMS; index += 1) many = addChat(many, [{ who: "me", text: `${index}` }]);
  assert.equal(many.length, MAX_CHAT_ITEMS);
  assert.equal(many[many.length - 1].id, MAX_CHAT_ITEMS + 2);
});

test("isBargeIn: 읽는 답과 다른 말은 끼어들기", () => {
  const speaking = "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요.";
  assert.equal(isBargeIn("잠깐", speaking), true);
  assert.equal(isBargeIn("장보기 목록 뭐 남았어?", speaking), true);
  // 같은 낱말이 조금 겹쳐도 새 말이면 끼어들기
  assert.equal(isBargeIn("가스비 아내가 냈어", speaking), true);
});

test("isBargeIn: 폰이 자기 답 소리를 받아 적은 것은 끼어들기가 아니다", () => {
  const speaking = "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요.";
  assert.equal(isBargeIn("가스비 4만 2천 원은", speaking), false);
  assert.equal(isBargeIn("아직 안 냈어요 11월", speaking), false);
});

test("isBargeIn: 너무 짧거나 빈 글은 넘긴다", () => {
  assert.equal(isBargeIn("", "답"), false);
  assert.equal(isBargeIn("음.", "답"), false);
  assert.equal(isBargeIn("  ", "답"), false);
  // 스피커 소리가 뭉개진 2~3글자는 아직 판단하지 않는다(11/16 자기 답을 듣고 되풀이)
  assert.equal(isBargeIn("이지", "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."), false);
  assert.equal(isBargeIn("시점 답", "이 질문에 맞는 시험 답변이 준비돼 있지 않아요."), false);
});

test("isBargeIn: 숫자를 다르게 받아 적어도 자기 소리로 본다", () => {
  const speaking = "가스비 4만 2천 원은 아직 안 냈어요. 11월 25일까지 내야 해요.";
  assert.equal(isBargeIn("가스비 42,000원은 아직", speaking), false);
});

test("isBargeIn: '잠깐·그만·멈춰'는 짧아도 끼어들기, 읽는 답에 있는 말이면 아니다", () => {
  const speaking = "장보기 목록은 두부, 계란 2가지예요.";
  assert.equal(isBargeIn("잠깐", speaking), true);
  assert.equal(isBargeIn("그만.", speaking), true);
  assert.equal(isBargeIn("멈춰 봐", speaking), true);
  assert.equal(isBargeIn("그만", "그만 둘까요?"), false);
});

test("isSelfEcho: 끼어든 말이 대부분 읽던 답이면 자기 소리", () => {
  const speaking = "이 질문에 맞는 시험 답변이 준비돼 있지 않아요.";
  assert.equal(isSelfEcho("질문에 맞는 시험 답변이", speaking), true);
  assert.equal(isSelfEcho("장보기 목록 뭐 남았어?", speaking), false);
  assert.equal(isSelfEcho("", speaking), false);
});
