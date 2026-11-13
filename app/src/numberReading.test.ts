import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canTestReading,
  countReadingMarks,
  MAX_READING_MEMO_CHARS,
  readingsFrom,
  setReadingMemo,
  toggleReadingMark,
  type ReadingSample,
} from "./numberReading.ts";

const SAMPLES: ReadingSample[] = [
  { id: "N1", group: "날짜", text: "11월 20일", reading: "십일월 이십일" },
  { id: "N2", group: "날짜", text: "12월 1일", reading: "십이월 일일" },
  { id: "N3", group: "시각", text: "15:40", reading: "십오 시 사십 분" },
];

test("toggleReadingMark: 누르면 적고, 같은 걸 다시 누르면 지우고, 다른 걸 누르면 바꾼다", () => {
  let marks = toggleReadingMark({}, "N1", "○");
  assert.deepEqual(marks, { N1: { heard: "○" } });
  marks = toggleReadingMark(marks, "N1", "×");
  assert.deepEqual(marks, { N1: { heard: "×" } });
  marks = toggleReadingMark(marks, "N1", "×");
  assert.deepEqual(marks, {});
});

test("toggleReadingMark: 원래 객체는 바꾸지 않는다", () => {
  const before = { N1: { heard: "○" as const } };
  toggleReadingMark(before, "N2", "×");
  assert.deepEqual(before, { N1: { heard: "○" } });
});

test("countReadingMarks: ○·×·안 들음, 목록에 없는 번호는 세지 않는다", () => {
  assert.deepEqual(countReadingMarks(SAMPLES, { N1: { heard: "○" }, N3: { heard: "×" }, N9: { heard: "○" } }), {
    ok: 1, bad: 1, todo: 1, total: 3,
  });
  assert.deepEqual(countReadingMarks([], {}), { ok: 0, bad: 0, todo: 0, total: 0 });
});

test("canTestReading: 사전 녹음·엔진 모름은 안 된다", () => {
  assert.equal(canTestReading("qwen3-tts-107"), true);
  assert.equal(canTestReading("qwen3-tts-107-h2"), true);
  assert.equal(canTestReading("mock"), true);
  assert.equal(canTestReading("prerecorded"), false);
  assert.equal(canTestReading(undefined), false);
});

test("readingsFrom: 줄 하나 또는 그 줄부터 끝까지", () => {
  assert.deepEqual(readingsFrom(SAMPLES, 1, true), ["십이월 일일"]);
  assert.deepEqual(readingsFrom(SAMPLES, 0, false), ["십일월 이십일", "십이월 일일", "십오 시 사십 분"]);
  assert.deepEqual(readingsFrom(SAMPLES, 5, false), []);
});

test("setReadingMemo: × 줄에만 달고, 너무 길면 자른다. ○ 로 바꾸면 메모는 사라진다", () => {
  let marks = setReadingMemo({ N1: { heard: "○" } }, "N1", "메모");
  assert.deepEqual(marks, { N1: { heard: "○" } });
  assert.deepEqual(setReadingMemo({}, "N2", "메모"), {});
  marks = setReadingMemo({ N2: { heard: "×" } }, "N2", "가".repeat(MAX_READING_MEMO_CHARS + 10));
  assert.equal(marks.N2.memo?.length, MAX_READING_MEMO_CHARS);
  assert.deepEqual(toggleReadingMark(marks, "N2", "○"), { N2: { heard: "○" } });
});
