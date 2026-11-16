// 실행: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import type { TimerApi } from "./conversation.ts";
import { createPrefetcher, PREFETCH_STABLE_MS, type PrefetchResult } from "./prefetch.ts";

function createFakeTimers() {
  let now = 0;
  let nextId = 1;
  const pending = new Map<number, { at: number; callback: () => void }>();
  const timers: TimerApi = {
    set: (callback, ms) => {
      const id = nextId++;
      pending.set(id, { at: now + ms, callback });
      return id;
    },
    clear: (handle) => {
      pending.delete(handle as number);
    },
  };
  const advance = (ms: number) => {
    now += ms;
    for (const [id, item] of [...pending]) {
      if (item.at <= now) {
        pending.delete(id);
        item.callback();
      }
    }
  };
  return { timers, advance };
}

/** 부를 때마다 기록하고, 손으로 끝내는 가짜 run. */
function createRun() {
  const calls: { text: string; finish: (ok?: boolean) => void }[] = [];
  const run = (text: string) =>
    new Promise<PrefetchResult>((resolve, reject) => {
      calls.push({
        text,
        finish: (ok = true) => (ok ? resolve({ speechText: `답 ${text}`, firstPiece: `답 ${text}`, audioUrl: `url:${text}` }) : reject(new Error("x"))),
      });
    });
  return { run, calls };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test("prefetch: 글이 멈춘 뒤에만 미리 만들고, 같은 최종 글이면 그것을 준다", async () => {
  const fake = createFakeTimers();
  const { run, calls } = createRun();
  const prefetcher = createPrefetcher(run, () => "k", PREFETCH_STABLE_MS, fake.timers);
  prefetcher.heard("장보기");
  fake.advance(PREFETCH_STABLE_MS - 1);
  prefetcher.heard("장보기 뭐 남았어");
  fake.advance(PREFETCH_STABLE_MS - 1);
  assert.equal(calls.length, 0);
  fake.advance(1);
  assert.deepEqual(calls.map((call) => call.text), ["장보기 뭐 남았어"]);
  calls[0].finish();
  // 띄어쓰기·문장부호만 다르면 같은 말로 본다.
  const taken = prefetcher.take("장보기 뭐 남았어?");
  assert.ok(taken);
  assert.equal((await taken)?.audioUrl, "url:장보기 뭐 남았어");
});

test("prefetch: 최종 글이 다르거나 조건(key)이 바뀌면 쓰지 않는다", () => {
  const fake = createFakeTimers();
  const { run } = createRun();
  let key = "a";
  const prefetcher = createPrefetcher(run, () => key, PREFETCH_STABLE_MS, fake.timers);
  prefetcher.heard("콩이 밥 줬어");
  fake.advance(PREFETCH_STABLE_MS);
  assert.equal(prefetcher.take("콩이 밥 줬어 아니면 아직이야"), null);
  prefetcher.heard("가스비 냈어");
  fake.advance(PREFETCH_STABLE_MS);
  key = "b";
  assert.equal(prefetcher.take("가스비 냈어"), null);
});

test("prefetch: 한 번에 하나만 만들고, 끝나면 그사이 마지막 글로 다시 만든다", async () => {
  const fake = createFakeTimers();
  const { run, calls } = createRun();
  const prefetcher = createPrefetcher(run, () => "k", PREFETCH_STABLE_MS, fake.timers);
  prefetcher.heard("남편한테");
  fake.advance(PREFETCH_STABLE_MS);
  prefetcher.heard("남편한테 약국");
  fake.advance(PREFETCH_STABLE_MS);
  prefetcher.heard("남편한테 약국 들르라고 해");
  fake.advance(PREFETCH_STABLE_MS);
  assert.equal(calls.length, 1);
  calls[0].finish();
  await flush();
  assert.deepEqual(calls.map((call) => call.text), ["남편한테", "남편한테 약국 들르라고 해"]);
  // 같은 글이 또 멈춰도 다시 만들지 않는다.
  prefetcher.heard("남편한테 약국 들르라고 해");
  fake.advance(PREFETCH_STABLE_MS);
  assert.equal(calls.length, 2);
});

test("prefetch: 실패하면 null 로 풀리고, take·reset 뒤에는 새로 만들지 않는다", async () => {
  const fake = createFakeTimers();
  const { run, calls } = createRun();
  const prefetcher = createPrefetcher(run, () => "k", PREFETCH_STABLE_MS, fake.timers);
  prefetcher.heard("소윤이 일정");
  fake.advance(PREFETCH_STABLE_MS);
  calls[0].finish(false);
  assert.equal(await prefetcher.take("소윤이 일정"), null);
  prefetcher.heard("다음 주 일정");
  prefetcher.reset();
  fake.advance(PREFETCH_STABLE_MS * 2);
  assert.equal(calls.length, 1);
  // 빈 글·문장부호만 있는 글은 만들지 않는다.
  prefetcher.heard(" ?! ");
  fake.advance(PREFETCH_STABLE_MS);
  assert.equal(calls.length, 1);
});
