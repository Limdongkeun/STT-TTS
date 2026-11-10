// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  activeTtsChoice, describeServerInfo, isHealthResponse, PHONE_STT_LABEL, sttLabelFor, ttsButtonLabel, ttsChoicesOf,
  type HealthResponse,
} from "./serverInfo.ts";

const HEALTH = { status: "ok", sttEngine: "mock", ttsEngine: "mock", answerProvider: "family-demo" };

test("describeServerInfo: 답 모드와 TTS 엔진을 보여 준다", () => {
  assert.equal(describeServerInfo({ kind: "ok", health: HEALTH }), "답: 가족 돌봄 시험(family-demo) · TTS: mock");
  assert.equal(
    describeServerInfo({ kind: "ok", health: { ...HEALTH, answerProvider: "fixed", ttsEngine: "qwen3-tts" } }),
    "답: 고정 답(fixed) · TTS: qwen3-tts",
  );
});

test("describeServerInfo: 모르는 답 모드는 이름 그대로", () => {
  assert.equal(describeServerInfo({ kind: "ok", health: { ...HEALTH, answerProvider: "llm" } }), "답: llm · TTS: mock");
});

test("describeServerInfo: 확인 중과 연결 실패", () => {
  assert.equal(describeServerInfo({ kind: "checking" }), "서버 확인 중…");
  assert.equal(describeServerInfo({ kind: "error", message: "서버 오류 500" }), "서버 연결 안 됨: 서버 오류 500");
});

test("isHealthResponse: 모양이 맞을 때만 true", () => {
  assert.equal(isHealthResponse(HEALTH), true);
  assert.equal(isHealthResponse(null), false);
  assert.equal(isHealthResponse("ok"), false);
  assert.equal(isHealthResponse({ ...HEALTH, answerProvider: 1 }), false);
  assert.equal(isHealthResponse({ status: "ok" }), false);
});

test("sttLabelFor: 폰 기본 STT / 서버 모델 이름 / 확인 안 됨", () => {
  assert.equal(sttLabelFor("phone", null), PHONE_STT_LABEL);
  assert.equal(sttLabelFor("server", null), "서버 STT(모델 확인 안 됨)");
  assert.equal(sttLabelFor("server", HEALTH), "서버 mock STT");
  assert.equal(sttLabelFor("server", { ...HEALTH, sttEngine: "qwen3-asr", sttModel: "Qwen/Qwen3-ASR-1.7B" }), "Qwen3-ASR-1.7B");
  assert.equal(sttLabelFor("server", { ...HEALTH, sttEngine: "qwen3-asr", sttModel: "" }), "서버 qwen3-asr");
  // 힌트를 쓰면 이름에 붙여 힌트 없는 저장본과 따로 비교한다.
  assert.equal(
    sttLabelFor("server", { ...HEALTH, sttEngine: "qwen3-asr", sttModel: "Qwen/Qwen3-ASR-1.7B", sttHints: 42 }),
    "Qwen3-ASR-1.7B · 힌트 42",
  );
  assert.equal(sttLabelFor("server", { ...HEALTH, sttEngine: "qwen3-asr", sttModel: "Qwen/Qwen3-ASR-1.7B", sttHints: 0 }), "Qwen3-ASR-1.7B");
});

test("ttsChoicesOf / activeTtsChoice: 고른 TTS 가 서버 목록에 있을 때만 쓴다", () => {
  const health = {
    status: "ok", sttEngine: "qwen3-asr", ttsEngine: "prerecorded", answerProvider: "family-demo",
    ttsChoices: [
      { engine: "prerecorded", label: "JISOO 사전 녹음 (C1~C7·D1~D25)" },
      { engine: "qwen3-tts-107", label: "107 Qwen3-TTS · G 목소리" },
      { engine: 3, label: "모양이 틀림" },
    ],
  } as unknown as HealthResponse;
  assert.deepEqual(ttsChoicesOf(health).map((choice) => choice.engine), ["prerecorded", "qwen3-tts-107"]);
  assert.deepEqual(activeTtsChoice(health, "qwen3-tts-107"), { engine: "qwen3-tts-107", label: "107 Qwen3-TTS · G 목소리" });
  assert.deepEqual(activeTtsChoice(health, "elevenlabs"), { engine: "prerecorded", label: "JISOO 사전 녹음 (C1~C7·D1~D25)" });
  assert.deepEqual(activeTtsChoice(health, null).engine, "prerecorded");
});

test("ttsChoicesOf: 예전 서버(목록 없음)·서버 모름은 빈 목록, 엔진은 서버 기본", () => {
  const old: HealthResponse = { status: "ok", sttEngine: "mock", ttsEngine: "mock", answerProvider: "fixed" };
  assert.deepEqual(ttsChoicesOf(old), []);
  assert.deepEqual(activeTtsChoice(old, "prerecorded"), { engine: "mock", label: "" });
  assert.deepEqual(activeTtsChoice(null, null), { engine: undefined, label: "" });
  assert.equal(ttsButtonLabel("qwen3-tts-107"), "107 G 목소리");
  assert.equal(ttsButtonLabel("새엔진"), "새엔진");
});
