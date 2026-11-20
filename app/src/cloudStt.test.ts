import assert from "node:assert/strict";
import test from "node:test";

import { asCloudReply, CLOUD_STT_ENGINE, directCloudTarget } from "./cloudStt.ts";

const URL = "https://34-50-48-66.sslip.io/";

test("클라우드 Qwen 을 고르면 클라우드 /stt 로 바로, 열쇠와 서버 쪽 엔진 이름을 싣는다", () => {
  assert.deepEqual(directCloudTarget(CLOUD_STT_ENGINE, URL, " k1 "), {
    url: "https://34-50-48-66.sslip.io/stt",
    headers: { "X-Stt-Key": "k1" },
    fields: { engine: "qwen3-asr-ko" },
  });
});

test("다른 STT 이거나 주소·열쇠가 없으면 맥을 거친다(null)", () => {
  assert.equal(directCloudTarget("qwen3-asr-ko", URL, "k"), null);
  assert.equal(directCloudTarget(undefined, URL, "k"), null);
  assert.equal(directCloudTarget(CLOUD_STT_ENGINE, undefined, "k"), null);
  assert.equal(directCloudTarget(CLOUD_STT_ENGINE, URL, ""), null);
  assert.equal(directCloudTarget(CLOUD_STT_ENGINE, URL, undefined), null);
  assert.equal(directCloudTarget(CLOUD_STT_ENGINE, "not a url", "k"), null);
});

test("열쇠를 싣으므로 http 주소로는 보내지 않는다", () => {
  assert.equal(directCloudTarget(CLOUD_STT_ENGINE, "http://34.50.48.66", "k"), null);
});

test("받은 답의 엔진 이름은 앱에서 고른 클라우드 이름으로 되돌린다", () => {
  const reply = { text: "우유 사 와", language: "Korean", engine: "qwen3-asr-ko", elapsedMs: 290 };
  assert.deepEqual(asCloudReply(reply), { ...reply, engine: CLOUD_STT_ENGINE });
});
