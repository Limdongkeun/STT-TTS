// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { hasStarted, waitUntilLoaded, waitUntilStarted, type PlaybackState } from "./playback.ts";

const noSleep = async () => {};

test("hasStarted: 재생 중이거나 조금이라도 재생됐으면 시작", () => {
  assert.equal(hasStarted({ playing: true, currentTime: 0 }), true);
  assert.equal(hasStarted({ playing: false, currentTime: 3.6 }), true); // 확인 전에 끝난 짧은 음성
  assert.equal(hasStarted({ playing: false, currentTime: 0 }), false);
});

test("waitUntilStarted: 몇 번 확인한 뒤 시작하면 true", async () => {
  const states: PlaybackState[] = [
    { playing: false, currentTime: 0 },
    { playing: false, currentTime: 0 },
    { playing: true, currentTime: 0.1 },
  ];
  let calls = 0;
  const probe = () => states[Math.min(calls++, states.length - 1)];
  assert.equal(await waitUntilStarted(probe, 2_000, noSleep), true);
  assert.equal(calls, 3);
});

test("waitUntilStarted: 끝까지 시작하지 않으면 false (정해진 횟수만 확인)", async () => {
  let calls = 0;
  const probe = () => {
    calls += 1;
    return { playing: false, currentTime: 0 };
  };
  assert.equal(await waitUntilStarted(probe, 1_000, noSleep), false);
  assert.equal(calls, 7); // 0·200·…·1000ms 6번 + 마지막 1번
});

test("waitUntilLoaded: 다 읽히면 바로 true, 끝까지 안 읽히면 false", async () => {
  let calls = 0;
  assert.equal(await waitUntilLoaded(() => ++calls >= 3, 1_000, noSleep), true);
  assert.equal(calls, 3);
  calls = 0;
  assert.equal(await waitUntilLoaded(() => { calls += 1; return false; }, 100, noSleep), false);
  assert.equal(calls, 4); // 0·50·100ms 3번 + 마지막 1번
});
