// 실행: npm test  (Node 의 TypeScript 지원으로 별도 의존성 없이 돈다)
import assert from "node:assert/strict";
import { test } from "node:test";

import { audioFileName, audioMimeType, joinUrl, normalizeBaseUrl } from "./url.ts";

test("normalizeBaseUrl: 정상 주소와 끝 빗금 정리", () => {
  assert.equal(normalizeBaseUrl("http://192.168.0.10:8002/"), "http://192.168.0.10:8002");
  assert.equal(normalizeBaseUrl("  https://example.com  "), "https://example.com");
});

test("normalizeBaseUrl: 비었거나 잘못된 주소는 null", () => {
  assert.equal(normalizeBaseUrl(undefined), null);
  assert.equal(normalizeBaseUrl(""), null);
  assert.equal(normalizeBaseUrl("192.168.0.10:8002"), null);
  assert.equal(normalizeBaseUrl("ftp://host"), null);
  assert.equal(normalizeBaseUrl("http://bad host"), null);
});

test("joinUrl: 상대 경로를 붙이고 절대 주소는 그대로", () => {
  assert.equal(joinUrl("http://a:1", "/audio/x"), "http://a:1/audio/x");
  assert.equal(joinUrl("http://a:1", "audio/x"), "http://a:1/audio/x");
  assert.equal(joinUrl("http://a:1", "http://b:2/y"), "http://b:2/y");
});

test("audioFileName / audioMimeType", () => {
  assert.equal(audioFileName("file:///tmp/rec-1.m4a"), "voice.m4a");
  assert.equal(audioFileName("file:///tmp/rec.WAV"), "voice.wav");
  assert.equal(audioFileName("file:///tmp/rec"), "voice.m4a");
  assert.equal(audioMimeType("voice.m4a"), "audio/mp4");
  assert.equal(audioMimeType("voice.xyz"), "application/octet-stream");
});
