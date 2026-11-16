// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createEndpointDetector,
  MAX_TURN_MS,
  MIN_SPEECH_DB,
  MIN_SPEECH_MS,
  NO_SPEECH_MS,
  POLL_MS,
  speechThresholdDb,
  type EndpointDecision,
} from "./endpoint.ts";

/** levels: 100ms 마다의 소리 크기. 끝난 때(ms)와 결과를 돌려준다. 끝나지 않으면 마지막 결과. */
function run(levels: number[], silenceMs = 1200): { atMs: number; decision: EndpointDecision; lastSpeechAtMs: number | null } {
  const detector = createEndpointDetector({ silenceMs });
  let decision: EndpointDecision = "listening";
  let atMs = 0;
  for (const [index, level] of levels.entries()) {
    atMs = index * POLL_MS;
    decision = detector.push(atMs, level);
    if (decision !== "listening") break;
  }
  return { atMs, decision, lastSpeechAtMs: detector.lastSpeechAtMs() };
}

const repeat = (level: number, count: number) => Array.from({ length: count }, () => level);

test("speechThresholdDb: 바닥 소음 + 여유, 너무 낮으면 하한", () => {
  assert.equal(speechThresholdDb(-40), -28);
  assert.equal(speechThresholdDb(-60), MIN_SPEECH_DB);
  assert.equal(speechThresholdDb(-160), MIN_SPEECH_DB);
});

test("말한 뒤 쉬는 시간만큼 조용하면 끝", () => {
  const result = run([...repeat(-55, 5), ...repeat(-25, 15), ...repeat(-55, 20)]);
  assert.equal(result.decision, "speechEnded");
  // 마지막 큰 소리 1900ms + 쉬는 시간 1200ms
  assert.equal(result.lastSpeechAtMs, 1900);
  assert.equal(result.atMs, 3100);
});

test("말 사이 짧은 쉼은 끝으로 보지 않는다", () => {
  const result = run([...repeat(-55, 3), ...repeat(-25, 10), ...repeat(-55, 8), ...repeat(-25, 10), ...repeat(-55, 15)]);
  assert.equal(result.decision, "speechEnded");
  assert.equal(result.lastSpeechAtMs, 3000);
});

test("짧게 튀는 소리는 말로 보지 않고, 말이 없으면 noSpeech", () => {
  const blip = Math.floor(MIN_SPEECH_MS / POLL_MS) - 1;
  const levels = [...repeat(-55, 5), ...repeat(-20, blip), ...repeat(-55, NO_SPEECH_MS / POLL_MS)];
  const result = run(levels);
  assert.equal(result.decision, "noSpeech");
  assert.equal(result.lastSpeechAtMs, null);
});

test("시끄러운 방은 바닥 소음에 맞춰 문턱을 올린다", () => {
  // 바닥 -35 → 문턱 -23. -30 소음은 말로 보지 않는다.
  const result = run([...repeat(-35, 10), ...repeat(-30, NO_SPEECH_MS / POLL_MS)]);
  assert.equal(result.decision, "noSpeech");
});

test("녹음 시작 직후 -160 은 바닥 소음으로 치지 않는다", () => {
  const result = run([-160, -160, ...repeat(-50, 3), ...repeat(-30, 10), ...repeat(-50, 15)]);
  assert.equal(result.decision, "speechEnded");
});

test("너무 길면 끊는다", () => {
  const result = run([...repeat(-55, 2), ...repeat(-25, MAX_TURN_MS / POLL_MS + 5)]);
  assert.equal(result.decision, "tooLong");
  assert.equal(result.atMs, MAX_TURN_MS);
});
