/** 답 음성이 폰에서 실제로 재생되기 시작했는지 확인한다 (순수 함수, 테스트 대상).
 *
 * 2026-11-05 17:07 시험: 서버는 음성 26개를 다 보냈는데 몇 개는 폰에서 소리가 나지 않았다.
 * 폰 음성인식이 끝난 직후라 재생이 시작되지 않는 경우로 보고, 시작을 확인한 뒤 안 되면 다시 튼다.
 */

export type PlaybackState = { playing: boolean; currentTime: number };

export const PLAYBACK_START_TIMEOUT_MS = 2_000;
const POLL_INTERVAL_MS = 200;

const sleepFor = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 재생 중이거나, 이미 조금이라도 재생됐으면(짧은 음성은 확인 전에 끝날 수 있다) 시작한 것으로 본다. */
export function hasStarted(state: PlaybackState): boolean {
  return state.playing || state.currentTime > 0;
}

/** timeoutMs 안에 재생이 시작되면 true. */
export async function waitUntilStarted(
  probe: () => PlaybackState,
  timeoutMs: number = PLAYBACK_START_TIMEOUT_MS,
  sleep: (ms: number) => Promise<void> = sleepFor,
): Promise<boolean> {
  for (let waited = 0; waited <= timeoutMs; waited += POLL_INTERVAL_MS) {
    if (hasStarted(probe())) return true;
    await sleep(POLL_INTERVAL_MS);
  }
  return hasStarted(probe());
}
