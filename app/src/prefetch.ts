/** 대화 모드에서 말이 끝나기 전에 답과 첫 소리를 미리 만든다(2026-11-16 사용자: 실시간 대화는 정확도보다 속도).
 *  받아 적는 글이 PREFETCH_STABLE_MS 동안 안 바뀌면 그 글로 미리 만든다. 서버에는 미리보기(preview)로 물어서
 *  덜 끝난 말이 부탁·장보기 같은 기록을 바꾸지 않는다. 말이 끝났을 때 최종 글이 같으면 미리 만든 소리를 쓴다.
 *  107 GPU 를 같이 쓰므로 미리 만들기는 한 번에 하나만 한다(앞 것이 끝나면 그동안 바뀐 마지막 글로 다시). */

import type { TimerApi } from "./conversation";

// conversation.ts 의 isBargeIn 과 같은 비교 기준(띄어쓰기·문장부호·기호를 뺀 글). node 시험이 .ts 확장자 없는 가져오기를 못 해서 따로 둔다.
const compactText = (text: string) => text.replace(/[\s\p{P}\p{S}]/gu, "");
const DEFAULT_TIMERS: TimerApi = {
  set: (callback, ms) => setTimeout(callback, ms),
  clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** 받아 적는 글이 이만큼(ms) 안 바뀌면 미리 만든다. 말이 끝났다고 보는 쉬는 시간(0.8초~)보다 짧다. */
export const PREFETCH_STABLE_MS = 400;

/** 미리 만든 것: 읽기용 답 글, 그 첫 조각 글, 첫 조각 소리 주소. */
export type PrefetchResult = { speechText: string; firstPiece: string; audioUrl: string };

export type Prefetcher = {
  /** 듣는 중 받아 적은 글이 바뀌었다. */
  heard: (text: string) => void;
  /** 말이 끝났다: 최종 글과 같은 글로 미리 만든 것이 있으면 돌려준다(실패했으면 null 로 풀린다). 미리 만들기를 멈춘다. */
  take: (finalText: string) => Promise<PrefetchResult | null> | null;
  /** 새 턴·대화 끝: 미리 만든 것과 기다리는 글을 버린다. */
  reset: () => void;
};

type Entry = { compact: string; key: string; result: Promise<PrefetchResult | null> };

/** run: 그 글로 답·첫 소리를 만든다. getKey: 답이 달라질 수 있는 조건(앞 대화 상태·TTS). 바뀌면 미리 만든 것을 쓰지 않는다. */
export function createPrefetcher(
  run: (text: string) => Promise<PrefetchResult>,
  getKey: () => string,
  stableMs: number = PREFETCH_STABLE_MS,
  timers: TimerApi = DEFAULT_TIMERS,
): Prefetcher {
  let handle: unknown = null;
  let entry: Entry | null = null;
  let busy = false;
  let pending: string | null = null;

  const clearTimer = () => {
    if (handle !== null) {
      timers.clear(handle);
      handle = null;
    }
  };

  const launch = (text: string) => {
    const compact = compactText(text);
    const key = getKey();
    if (!compact || (entry && entry.compact === compact && entry.key === key)) return;
    if (busy) {
      pending = text;
      return;
    }
    busy = true;
    const result = run(text).catch(() => null);
    entry = { compact, key, result };
    void result.then(() => {
      busy = false;
      const next = pending;
      pending = null;
      if (next !== null) launch(next);
    });
  };

  return {
    heard: (text) => {
      clearTimer();
      handle = timers.set(() => {
        handle = null;
        launch(text);
      }, stableMs);
    },
    take: (finalText) => {
      clearTimer();
      pending = null;
      const found = entry;
      entry = null;
      if (!found || found.compact !== compactText(finalText) || found.key !== getKey()) return null;
      return found.result;
    },
    reset: () => {
      clearTimer();
      pending = null;
      entry = null;
    },
  };
}
