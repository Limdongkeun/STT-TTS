// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  appendResult,
  createSilenceTimer,
  decideNextTurn,
  EMPTY_TRANSCRIPT,
  formatSilenceLabel,
  MAX_EMPTY_TURNS,
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

test("decideNextTurn: 답했으면 대화 모드일 때만 다시 듣고, 빈 턴 수는 0으로", () => {
  assert.deepEqual(decideNextTurn(true, 1, "answered"), { continueListening: true, emptyTurns: 0 });
  assert.deepEqual(decideNextTurn(false, 1, "answered"), { continueListening: false, emptyTurns: 0 });
});

test("decideNextTurn: 빈 턴이 한도에 닿으면 멈춘다", () => {
  assert.deepEqual(decideNextTurn(true, 0, "empty"), { continueListening: true, emptyTurns: 1 });
  assert.deepEqual(decideNextTurn(true, MAX_EMPTY_TURNS - 1, "empty"), {
    continueListening: false,
    emptyTurns: MAX_EMPTY_TURNS,
  });
  assert.equal(decideNextTurn(false, 0, "empty").continueListening, false);
});

test("decideNextTurn: 오류나 직접 멈춤이면 항상 멈춘다", () => {
  assert.deepEqual(decideNextTurn(true, 1, "error"), { continueListening: false, emptyTurns: 0 });
  assert.deepEqual(decideNextTurn(true, 0, "stopped"), { continueListening: false, emptyTurns: 0 });
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
