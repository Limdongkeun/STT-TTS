import assert from "node:assert/strict";
import { test } from "node:test";

import { readUploadResult } from "./uploadResult.ts";

test("readUploadResult: 2xx 는 JSON 본문을 돌려준다", () => {
  assert.deepEqual(readUploadResult(200, '{"text":"안녕","elapsedMs":12}'), { ok: true, body: { text: "안녕", elapsedMs: 12 } });
  assert.deepEqual(readUploadResult(201, "not json"), { ok: true, body: null });
});

test("readUploadResult: 오류는 상태와 서버 detail 을 담는다", () => {
  assert.deepEqual(readUploadResult(415, '{"detail":"WAV 가 아니에요."}'), {
    ok: false, status: 415, message: "서버 오류 415 WAV 가 아니에요.",
  });
  assert.deepEqual(readUploadResult(500, "<html>"), { ok: false, status: 500, message: "서버 오류 500" });
});

test("readUploadResult: 연결 실패(status 0)는 서버·주소 확인 안내", () => {
  const result = readUploadResult(0, "");
  assert.equal(result.ok, false);
  assert.match(result.ok ? "" : result.message, /연결하지 못했어요/);
});
