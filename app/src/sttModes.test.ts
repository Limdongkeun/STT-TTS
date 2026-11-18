// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { CONTEXTUAL_WORDS } from "./sttModes.ts";

test("CONTEXTUAL_WORDS: 실기기 시험에서 잘못 적힌 말이 힌트에 들어 있다", () => {
  for (const word of ["소윤이", "어린이집 하원", "친정 용돈", "가스비", "콩이", "심장사상충"]) {
    assert.ok(CONTEXTUAL_WORDS.includes(word), word);
  }
});

test("CONTEXTUAL_WORDS: '학원'만 홀로 넣지 않는다(하원이 학원으로 끌려감)", () => {
  assert.equal(CONTEXTUAL_WORDS.includes("학원"), false);
});

test("CONTEXTUAL_WORDS: 겹치거나 빈 말이 없고 100개를 넘지 않는다", () => {
  assert.equal(new Set(CONTEXTUAL_WORDS).size, CONTEXTUAL_WORDS.length);
  assert.ok(CONTEXTUAL_WORDS.every((word) => word.trim() === word && word.length > 0));
  assert.ok(CONTEXTUAL_WORDS.length <= 100);
});
