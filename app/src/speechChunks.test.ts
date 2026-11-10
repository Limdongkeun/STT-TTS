import assert from "node:assert/strict";
import { test } from "node:test";

import { fetchSequentially, shouldSplitSpeech, SpeechCancelledError, splitSpeech } from "./speechChunks.ts";

test("splitSpeech: 문장 끝 부호에서 나누고 부호는 앞 문장에 남긴다", () => {
  assert.deepEqual(splitSpeech("다음 주 가족 일정은 두 건이에요. 화요일에 가족 식사, 토요일에 장보기가 있어요."), [
    "다음 주 가족 일정은 두 건이에요.",
    "화요일에 가족 식사, 토요일에 장보기가 있어요.",
  ]);
  assert.deepEqual(splitSpeech("몇 시에 먹였나요? 알려 주세요!"), ["몇 시에 먹였나요?", "알려 주세요!"]);
});

test("splitSpeech: 한 문장·부호 없는 글·빈 글", () => {
  assert.deepEqual(splitSpeech("오늘 빨래는 아내가 한 걸로 체크했어요."), ["오늘 빨래는 아내가 한 걸로 체크했어요."]);
  assert.deepEqual(splitSpeech("부호 없는 글"), ["부호 없는 글"]);
  assert.deepEqual(splitSpeech("   "), []);
});

test("splitSpeech: 부호 뒤에 띄어쓰기가 없으면 자르지 않는다", () => {
  assert.deepEqual(splitSpeech("1.5배 빨라요. 좋아요 정말로."), ["1.5배 빨라요.", "좋아요 정말로."]);
});

test("splitSpeech: 아주 짧은 조각은 옆 문장에 붙인다", () => {
  assert.deepEqual(splitSpeech("네. 장보기 목록에 우유를 넣었어요."), ["네. 장보기 목록에 우유를 넣었어요."]);
  assert.deepEqual(splitSpeech("가스비는 아내가 냈어요. 끝."), ["가스비는 아내가 냈어요. 끝."]);
  assert.deepEqual(splitSpeech("네."), ["네."]);
});

test("shouldSplitSpeech: 그때그때 만드는 TTS 만", () => {
  assert.equal(shouldSplitSpeech("qwen3-tts-107"), true);
  assert.equal(shouldSplitSpeech("qwen3-tts"), true);
  assert.equal(shouldSplitSpeech("prerecorded"), false);
  assert.equal(shouldSplitSpeech("mock"), false);
  assert.equal(shouldSplitSpeech(undefined), false);
});

test("fetchSequentially: 앞 것이 끝난 뒤에 다음을 부른다", async () => {
  const log: string[] = [];
  const resolvers: Array<() => void> = [];
  const fetchOne = (item: string) => {
    log.push(`start ${item}`);
    return new Promise<string>((resolve) => resolvers.push(() => resolve(item)));
  };
  const results = fetchSequentially(["a", "b"], fetchOne);
  await Promise.resolve();
  assert.deepEqual(log, ["start a"]);
  resolvers[0]();
  assert.equal(await results[0], "a");
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(log, ["start a", "start b"]);
  resolvers[1]();
  assert.equal(await results[1], "b");
});

test("fetchSequentially: 앞 것이 실패하면 뒤는 부르지 않고 같이 실패한다", async () => {
  const called: string[] = [];
  const results = fetchSequentially(["a", "b"], async (item) => {
    called.push(item);
    throw new Error(`fail ${item}`);
  });
  await assert.rejects(results[0], /fail a/);
  await assert.rejects(results[1], /fail a/);
  assert.deepEqual(called, ["a"]);
});

test("fetchSequentially: 멈추면 남은 조각을 부르지 않는다", async () => {
  let keepGoing = true;
  const called: string[] = [];
  const results = fetchSequentially(["a", "b"], async (item) => {
    called.push(item);
    keepGoing = false;
    return item;
  }, () => keepGoing);
  assert.equal(await results[0], "a");
  await assert.rejects(results[1], SpeechCancelledError);
  assert.deepEqual(called, ["a"]);
});
