// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  autoScreenMark,
  defaultDevice,
  describeAttempt,
  describeChanges,
  EMPTY_RESULT,
  hasBad,
  hasRecords,
  isDone,
  isValidDevice,
  isVisible,
  nextCase,
  recordTurn,
  resultOf,
  summarize,
  type Attempt,
  type SheetResult,
  type TestCase,
} from "./testSheet.ts";

const CASE_A: TestCase = { group: "장보기", id: "D1", say: "장보기 목록 뭐 남았어?", expect: "장보기 목록은 두부, 계란 2가지예요.", dateDependent: false, chain: "" };
const CASE_B: TestCase = { group: "등·하원", id: "D9", say: "내일 하원 누가 가?", expect: "11월 6일 금요일 하원은 아내가 가요.", dateDependent: true, chain: "" };
const done: SheetResult = { ...EMPTY_RESULT, recognized: "장보기 목록 뭐 남았어", key: "o", screen: "o", heard: "o" };

test("defaultDevice: OS + 버전, 서버 규칙에 맞는 모양", () => {
  assert.equal(defaultDevice("ios", "27.0.1"), "ios-27-0-1");
  assert.equal(defaultDevice("android", 35), "android-35");
  assert.equal(defaultDevice("", ""), "device");
  assert.ok(isValidDevice(defaultDevice("iOS ", "17.5 (beta)")));
  assert.ok(isValidDevice(defaultDevice("ios", "1".repeat(60))));
});

test("isValidDevice: 경계와 실패", () => {
  assert.equal(isValidDevice("ios-27-0-1"), true);
  assert.equal(isValidDevice("IOS"), false);
  assert.equal(isValidDevice("../ios"), false);
  assert.equal(isValidDevice(""), false);
  assert.equal(isValidDevice("a".repeat(41)), false);
});

const ATTEMPT: Attempt = {
  savedAt: "2026-11-05T13:40:12+09:00",
  version: "9a49c4f (수정 중)",
  file: "2026-11-05_134012.json",
  sttLabels: ["폰 기본 STT"],
  tts: "mock",
  comparedWith: "2026-11-05_120000.json",
  done: 30,
  total: 32,
  okMarks: 85,
  badCases: ["D8", "D13", "C2"],
  improved: ["D1"],
  worsened: ["D8"],
};

test("describeAttempt / describeChanges", () => {
  assert.equal(describeAttempt(ATTEMPT), "[폰 기본 STT] · 11/5 13:40 · 9a49c4f (수정 중) · 끝낸 30/32 · × 3");
  assert.equal(
    describeAttempt({ ...ATTEMPT, version: "", savedAt: "이상한 값", sttLabels: [] }),
    "[STT 모름] · 이상한 값 · 버전 모름 · 끝낸 30/32 · × 3",
  );
  assert.equal(describeAttempt({ ...ATTEMPT, sttLabels: ["폰 기본 STT", "Qwen3-ASR-1.7B"] }).startsWith("[폰 기본 STT + Qwen3-ASR-1.7B]"), true);
  assert.equal(describeChanges(ATTEMPT), "×→○ D1 / ○→× D8");
  assert.equal(describeChanges({ ...ATTEMPT, improved: [], worsened: [] }), "지난번과 같아요");
  assert.equal(describeChanges({ ...ATTEMPT, comparedWith: "" }), "이 STT의 첫 저장본");
});

test("hasRecords: 적힌 게 있어야 저장할 거리", () => {
  assert.equal(hasRecords({}), false);
  assert.equal(hasRecords({ D1: { ...EMPTY_RESULT, note: "메모만" } }), false);
  assert.equal(hasRecords({ D1: { ...EMPTY_RESULT, heard: "x" } }), true);
  assert.equal(hasRecords({ D1: { ...EMPTY_RESULT, recognized: "말" } }), true);
});

test("isDone / hasBad / isVisible", () => {
  assert.equal(isDone(done), true);
  assert.equal(isDone({ ...done, recognized: "  " }), false);
  assert.equal(isDone({ ...done, heard: "" }), false);
  assert.equal(hasBad({ ...done, key: "x" }), true);
  assert.equal(isVisible(done, "todo"), false);
  assert.equal(isVisible({ ...done, screen: "x" }, "bad"), true);
  assert.equal(isVisible(EMPTY_RESULT, "all"), true);
});

test("summarize: 끝낸 문장과 × 있는 문장 수", () => {
  const results = { D1: done, D9: { ...EMPTY_RESULT, key: "x" as const } };
  assert.deepEqual(summarize([CASE_A, CASE_B], results), { done: 1, bad: 1, total: 2 });
  assert.deepEqual(resultOf({}, "D1"), EMPTY_RESULT);
});

test("autoScreenMark: 글자까지 같을 때만 ○, 날짜 따라 바뀌는 문장은 비워 둠", () => {
  assert.equal(autoScreenMark(CASE_A, " 장보기 목록은 두부, 계란 2가지예요. "), "o");
  assert.equal(autoScreenMark(CASE_A, "장보기 목록은 두부 2가지예요."), "");
  assert.equal(autoScreenMark(CASE_B, CASE_B.expect), "");
});

test("recordTurn: 인식한 말·답·STT 를 넣고, 사람이 누른 화면 답은 지키기", () => {
  const recorded = recordTurn({ ...EMPTY_RESULT, screen: "x", note: "메모" }, CASE_A, "장보기 목록 뭐 남았어", "다른 답", "폰 기본 STT");
  assert.deepEqual(recorded, {
    ...EMPTY_RESULT,
    recognized: "장보기 목록 뭐 남았어",
    answer: "다른 답",
    stt: "폰 기본 STT",
    screen: "x",
    note: "메모",
  });
  assert.equal(recordTurn(EMPTY_RESULT, CASE_A, "q", CASE_A.expect, "폰 기본 STT").screen, "o");
});

test("nextCase: 다음 문장, 마지막이거나 없으면 null", () => {
  assert.equal(nextCase([CASE_A, CASE_B], "D1")?.id, "D9");
  assert.equal(nextCase([CASE_A, CASE_B], "D9"), null);
  assert.equal(nextCase([CASE_A, CASE_B], "C1"), null);
});
