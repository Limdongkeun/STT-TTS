// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  accuracyText,
  autoScreenMark,
  charErrorRate,
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

test("summarize: 끝낸 문장과 × 있는 문장 수, 평균 CER", () => {
  const results = { D1: done, D9: { ...EMPTY_RESULT, key: "x" as const } };
  const summary = summarize([CASE_A, CASE_B], results);
  assert.deepEqual({ ...summary, avgCer: null }, { done: 1, bad: 1, total: 2, avgCer: null });
  assert.equal(summary.avgCer, 0); // D1 만 인식한 말이 있고, 문장과 같음
  assert.equal(summarize([CASE_A], {}).avgCer, null);
  assert.deepEqual(resultOf({}, "D1"), EMPTY_RESULT);
});

test("autoScreenMark: 글자까지 같을 때만 ○, 날짜 따라 바뀌는 문장은 비워 둠", () => {
  assert.equal(autoScreenMark(CASE_A, " 장보기 목록은 두부, 계란 2가지예요. "), "o");
  assert.equal(autoScreenMark(CASE_A, "장보기 목록은 두부 2가지예요."), "");
  assert.equal(autoScreenMark(CASE_A, "장보기 목록은 두부,계란 2 가지예요"), "o"); // 띄어쓰기·문장부호만 다름
  assert.equal(autoScreenMark(CASE_A, "  "), "");
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

test("charErrorRate: 띄어쓰기·문장부호 무시, 바꿈·빠짐을 센다", () => {
  assert.equal(charErrorRate("소윤이 이번 주 학교 학원 일정 뭐야?", "소윤이 이번주 학교 학원 일정 뭐야"), 0);
  assert.equal(charErrorRate("소윤이 이번 주 학교 학원 일정 뭐야?", "수연이 이번 주 학교 일정 뭐야?"), 4 / 14);
  assert.equal(charErrorRate("가스비 내가 냈어", "코스피 대가 됐어"), 4 / 7);
  assert.equal(charErrorRate("장보기 목록 뭐 남았어?", ""), null);
  assert.equal(charErrorRate("", "아무 말"), null);
});

test("accuracyText: 정확도 %, 0% 아래로 안 내려감", () => {
  assert.equal(accuracyText(0), "100%");
  assert.equal(accuracyText(4 / 14), "71%");
  assert.equal(accuracyText(1.5), "0%");
});

test("mock TTS: 들린 답 없이도 끝난 문장, × 판단에서도 뺀다", () => {
  const noHeard: SheetResult = { ...done, heard: "" };
  assert.equal(isDone(noHeard), false);
  assert.equal(isDone(noHeard, false), true);
  assert.equal(hasBad({ ...done, heard: "x" }, false), false);
  assert.equal(isVisible(noHeard, "todo", false), false);
  assert.equal(summarize([CASE_A], { D1: noHeard }, false).done, 1);
});

test("describeAttempt: 평균 인식 정확도를 함께 보여 준다", () => {
  assert.equal(describeAttempt({ ...ATTEMPT, avgCer: 0.06 }), "[폰 기본 STT] · 11/5 13:40 · 9a49c4f (수정 중) · 인식 94% · 끝낸 30/32 · × 3");
});

test("녹음 없음('-'): 들린 답을 판단하지 않아도 끝난 문장, 다음 턴에는 비움", () => {
  const noRecording = { ...done, heard: "-" as const };
  assert.equal(isDone(noRecording), true);
  assert.equal(hasBad(noRecording), false);
  assert.equal(recordTurn(noRecording, CASE_A, "q", "답", "폰 기본 STT").heard, "");
  assert.equal(recordTurn({ ...done, heard: "x" }, CASE_A, "q", "답", "폰 기본 STT").heard, "x");
});
