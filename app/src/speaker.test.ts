// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_SPEAKER, SPEAKER_LABELS, SPEAKERS } from "./speaker.ts";

test("speaker: 서버가 받는 값(wife/husband)과 화면 이름", () => {
  assert.deepEqual([...SPEAKERS], ["wife", "husband"]);
  assert.deepEqual(SPEAKERS.map((speaker) => SPEAKER_LABELS[speaker]), ["아내", "남편"]);
  assert.equal(DEFAULT_SPEAKER, "wife");
});
