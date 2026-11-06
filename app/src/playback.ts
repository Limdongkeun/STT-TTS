/** 답 음성이 폰에서 실제로 재생되기 시작했는지 확인한다 (순수 함수, 테스트 대상).
 *
 * 2026-11-05 17:07 시험: 서버는 음성 26개를 다 보냈는데 몇 개는 폰에서 소리가 나지 않았다.
 * 폰 음성인식이 끝난 직후라 재생이 시작되지 않는 경우로 보고, 시작을 확인한 뒤 안 되면 다시 튼다.
 *
 * 2026-11-06 13:51 시험: 23턴 중 20턴이 첫 재생에서 2초 안에 시작하지 않고 다시 틀어서야 났다(말 끝→소리 4.6초).
 * 소리를 바꿔 끼운 직후(아직 읽는 중) play 를 불러 무시된 것으로 보고, 다 읽힌 뒤 틀고 첫 확인은 짧게 한다.
 */

export type PlaybackState = { playing: boolean; currentTime: number };

export const PLAYBACK_START_TIMEOUT_MS = 2_000;
/** 처음 틀고 이만큼 안에 시작하지 않으면 바로 다시 튼다. */
export const FIRST_START_TIMEOUT_MS = 600;
/** 소리를 바꿔 끼운 뒤 다 읽힐 때까지 기다리는 최대 시간. 넘으면 그냥 튼다. */
export const LOAD_TIMEOUT_MS = 1_500;
const POLL_INTERVAL_MS = 200;
const LOAD_POLL_INTERVAL_MS = 50;

const sleepFor = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 재생 중이거나, 이미 조금이라도 재생됐으면(짧은 음성은 확인 전에 끝날 수 있다) 시작한 것으로 본다. */
export function hasStarted(state: PlaybackState): boolean {
  return state.playing || state.currentTime > 0;
}

/** timeoutMs 안에 condition 이 참이 되면 true. intervalMs 마다 확인한다. */
export async function waitFor(
  condition: () => boolean,
  timeoutMs: number,
  intervalMs: number,
  sleep: (ms: number) => Promise<void> = sleepFor,
): Promise<boolean> {
  for (let waited = 0; waited <= timeoutMs; waited += intervalMs) {
    if (condition()) return true;
    await sleep(intervalMs);
  }
  return condition();
}

/** timeoutMs 안에 재생이 시작되면 true. */
export function waitUntilStarted(
  probe: () => PlaybackState,
  timeoutMs: number = PLAYBACK_START_TIMEOUT_MS,
  sleep: (ms: number) => Promise<void> = sleepFor,
): Promise<boolean> {
  return waitFor(() => hasStarted(probe()), timeoutMs, POLL_INTERVAL_MS, sleep);
}

/** 바꿔 끼운 소리가 다 읽히면 true (timeoutMs 를 넘으면 false). */
export function waitUntilLoaded(
  isLoaded: () => boolean,
  timeoutMs: number = LOAD_TIMEOUT_MS,
  sleep: (ms: number) => Promise<void> = sleepFor,
): Promise<boolean> {
  return waitFor(isLoaded, timeoutMs, LOAD_POLL_INTERVAL_MS, sleep);
}
