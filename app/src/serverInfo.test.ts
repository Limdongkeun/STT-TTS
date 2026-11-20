// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  activeTtsChoice, describeServerInfo, isHealthResponse, PHONE_STT_LABEL, sttButtonLabel, sttChoicesOf, sttLabelFor,
  ttsButtonLabel, ttsChoicesOf,
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
  assert.equal(
    sttLabelFor("server", { ...HEALTH, sttEngine: "qwen3-asr-ko", sttModel: "TeamUNIVA/qwen3_asr_1.7b_ko" }), "qwen3_asr_1.7b_ko",
  );
  assert.equal(sttLabelFor("server", { ...HEALTH, sttEngine: "qwen3-asr-ko", sttModel: "" }), "서버 qwen3-asr-ko");
});

test("ttsChoicesOf / activeTtsChoice: 고른 TTS 가 서버 목록에 있을 때만 쓴다", () => {
  const health = {
    status: "ok", sttEngine: "qwen3-asr-ko", ttsEngine: "prerecorded", answerProvider: "family-demo",
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
  assert.equal(ttsButtonLabel("qwen3-tts-107-h2"), "107 H2 목소리");
  assert.equal(ttsButtonLabel("새엔진"), "새엔진");
});

test("sttChoicesOf·sttLabelFor: 서버가 준 STT 고르기 목록(2026-11-16 LFM3)", () => {
  const health = {
    ...HEALTH, sttEngine: "qwen3-asr-ko",
    sttChoices: [
      { engine: "qwen3-asr-ko", label: "Qwen3-ASR-1.7B-ko (UNIVA)" },
      { engine: "lfm3-asr", label: "LFM3-Audio-2B" },
      { engine: 3, label: "모양이 틀림" },
    ],
  } as unknown as HealthResponse;
  assert.deepEqual(sttChoicesOf(health).map((choice) => choice.engine), ["qwen3-asr-ko", "lfm3-asr"]);
  assert.deepEqual(sttChoicesOf(HEALTH), []);
  assert.equal(sttLabelFor("server", health, "lfm3-asr"), "LFM3-Audio-2B");
  // 고르지 않았거나 목록에 없는 엔진이면 기본(첫째)
  assert.equal(sttLabelFor("server", health, null), "Qwen3-ASR-1.7B-ko (UNIVA)");
  assert.equal(sttLabelFor("server", health, "whisper"), "Qwen3-ASR-1.7B-ko (UNIVA)");
  assert.equal(sttLabelFor("phone", health, "lfm3-asr"), PHONE_STT_LABEL);
});

test("버튼 이름: LFM3 STT·TTS", () => {
  assert.equal(sttButtonLabel("lfm3-asr"), "서버 LFM3");
  assert.equal(sttButtonLabel("qwen3-asr-ko"), "서버 Qwen 한국어");
  assert.equal(sttButtonLabel("google-chirp3"), "Google Chirp 3");
  assert.equal(sttButtonLabel("qwen3-asr-ko-cloud"), "클라우드 Qwen 한국어");
  assert.equal(sttButtonLabel("whisper"), "서버 whisper");
  assert.equal(ttsButtonLabel("lfm3-tts-female"), "LFM3 여자");
  assert.equal(ttsButtonLabel("lfm3-tts-male"), "LFM3 남자");
  assert.equal(ttsButtonLabel("elevenlabs-v4-turbo-female"), "ElevenLabs 여자");
  assert.equal(ttsButtonLabel("elevenlabs-v4-turbo-male"), "ElevenLabs 남자");
  assert.equal(ttsButtonLabel("google-chirp3-hd-female"), "Google 여자");
  assert.equal(ttsButtonLabel("google-chirp3-hd-male"), "Google 남자");
  assert.equal(ttsButtonLabel("supertonic-male"), "Supertonic 남자");
});
