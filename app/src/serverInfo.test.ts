// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { describeServerInfo, isHealthResponse, PHONE_STT_LABEL, sttLabelFor } from "./serverInfo.ts";

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
