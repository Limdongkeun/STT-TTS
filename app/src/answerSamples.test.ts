import assert from "node:assert/strict";
import { test } from "node:test";

import { answerReadingsFrom, answerTextFor, canListenAnswers, type AnswerSample } from "./answerSamples.ts";

const SAMPLES: AnswerSample[] = [
  { id: "C1", answer: "다음 주 가족 일정은 두 건이에요.", spoken: "다음 주엔 가족 일정이 두 개 있어요." },
  { id: "C2", answer: "소윤이는 수요일에 학교 체험학습이 있어요.", spoken: "소윤이는 수요일에 체험학습 가요." },
  { id: "D5", answer: "가스비 4만 2천 원은 아직 안 냈어요.", spoken: "가스비 사만 이천 원은 아직 안 냈어요." },
];

test("answerTextFor: 소리용 입말을 읽는다", () => {
  assert.equal(answerTextFor(SAMPLES[2]), "가스비 사만 이천 원은 아직 안 냈어요.");
});

test("answerReadingsFrom: 전부 듣기는 그 줄부터 끝까지, 줄 듣기는 그 줄 하나", () => {
  assert.deepEqual(answerReadingsFrom(SAMPLES, 0, false), SAMPLES.map((sample) => sample.spoken));
  assert.deepEqual(answerReadingsFrom(SAMPLES, 1, true), ["소윤이는 수요일에 체험학습 가요."]);
  assert.deepEqual(answerReadingsFrom(SAMPLES, 2, false), ["가스비 사만 이천 원은 아직 안 냈어요."]);
  assert.deepEqual(answerReadingsFrom(SAMPLES, 5, true), []);
});

test("canListenAnswers: 엔진을 모르면 못 듣고, 지수 녹음(입말 녹음)·107 은 들을 수 있다", () => {
  assert.equal(canListenAnswers(undefined), false);
  assert.equal(canListenAnswers("prerecorded"), true);
  assert.equal(canListenAnswers("qwen3-tts-107-h2"), true);
  assert.equal(canListenAnswers("mock"), true);
});
