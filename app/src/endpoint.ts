/** 서버 STT(Qwen3-ASR) 대화에서 말이 끝난 때를 소리 크기로 찾는다 (순수 함수, 테스트 대상).
 *
 * 폰 STT 는 받아 적은 글자가 멈추면 말이 끝난 것으로 보지만, 서버 STT 는 녹음을 다 보낸 뒤에야 글자가 나온다.
 * 그래서 녹음하는 동안 폰 마이크의 소리 크기(dBFS, 0 이 가장 큼)를 보고 끝을 정한다(2026-11-13 사용자 요청).
 */

/** 소리 크기를 읽는 간격(ms). */
export const POLL_MS = 100;
/** 바닥 소음보다 이만큼(dB) 크면 말소리로 본다. */
export const SPEECH_MARGIN_DB = 12;
/** 아주 조용한 방에서도 이보다 작으면 말소리로 보지 않는다. */
export const MIN_SPEECH_DB = -45;
/** 바닥 소음은 이보다 낮게 잡지 않는다(녹음 시작 직후 -160 같은 값이 온다). */
export const FLOOR_LIMIT_DB = -70;
/** 이 시간(ms) 이상 이어서 커야 말이 시작된 것으로 본다(문 닫는 소리 같은 짧은 소리는 넘긴다). */
export const MIN_SPEECH_MS = 200;
/** 말이 시작되지 않고 이 시간(ms)이 지나면 빈 턴으로 끝낸다(대화는 바로 다시 듣는다). */
export const NO_SPEECH_MS = 8000;
/** 한 턴이 이보다 길면 거기서 끊어 보낸다. */
export const MAX_TURN_MS = 20000;

/** listening: 계속 듣기 / speechEnded: 말이 끝남 / tooLong: 너무 길어 끊음 / noSpeech: 말이 없음 */
export type EndpointDecision = "listening" | "speechEnded" | "tooLong" | "noSpeech";

export type EndpointOptions = { silenceMs: number; noSpeechMs?: number; maxTurnMs?: number };

export type EndpointDetector = {
  /** atMs: 녹음 시작부터 지난 시간, levelDb: 그때 소리 크기. 끝났으면 listening 이 아닌 값을 돌려준다. */
  push: (atMs: number, levelDb: number) => EndpointDecision;
  /** 마지막으로 말소리가 들린 때(녹음 시작부터 ms). 말이 없었으면 null. '말 끝→소리' 시간을 잴 때 쓴다. */
  lastSpeechAtMs: () => number | null;
};

export function speechThresholdDb(floorDb: number): number {
  return Math.max(MIN_SPEECH_DB, Math.max(floorDb, FLOOR_LIMIT_DB) + SPEECH_MARGIN_DB);
}

export function createEndpointDetector({
  silenceMs, noSpeechMs = NO_SPEECH_MS, maxTurnMs = MAX_TURN_MS,
}: EndpointOptions): EndpointDetector {
  let floorDb = Number.POSITIVE_INFINITY;
  let loudSince: number | null = null;
  let lastLoudAt: number | null = null;
  let heardSpeech = false;

  const push = (atMs: number, levelDb: number): EndpointDecision => {
    const usable = Number.isFinite(levelDb) && levelDb > -120;
    // 말이 시작되기 전의 가장 작은 소리를 바닥 소음으로 본다.
    if (usable && !heardSpeech) floorDb = Math.min(floorDb, levelDb);
    const loud = usable && Number.isFinite(floorDb) && levelDb >= speechThresholdDb(floorDb);
    if (loud) {
      loudSince ??= atMs;
      lastLoudAt = atMs;
      if (!heardSpeech && atMs - loudSince >= MIN_SPEECH_MS) heardSpeech = true;
    } else if (!heardSpeech) {
      loudSince = null;
    }
    if (atMs >= maxTurnMs) return heardSpeech ? "tooLong" : "noSpeech";
    if (heardSpeech && lastLoudAt !== null && atMs - lastLoudAt >= silenceMs) return "speechEnded";
    if (!heardSpeech && atMs >= noSpeechMs) return "noSpeech";
    return "listening";
  };

  return { push, lastSpeechAtMs: () => (heardSpeech ? lastLoudAt : null) };
}
