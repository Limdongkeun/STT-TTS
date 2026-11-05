/** 대화 모드 규칙 (순수 함수, 테스트 대상). */

/** 말이 끝났다고 보는 쉬는 시간 후보(ms). 화면에서 고른다. */
export const SILENCE_OPTIONS_MS = [800, 1200, 1500, 2000, 3000] as const;
export const DEFAULT_SILENCE_MS = 1200;
/** 듣기 시작 후 이 시간 동안 아무 말도 없으면 그 턴을 끝낸다. */
export const NO_SPEECH_TIMEOUT_MS = 8000;
/** 연달아 말이 없는 턴이 이만큼 쌓이면 대화 모드를 멈춘다. */
export const MAX_EMPTY_TURNS = 2;

export type TurnOutcome = "answered" | "empty" | "error" | "stopped";

export type ConversationDecision = { continueListening: boolean; emptyTurns: number };

/** 한 턴이 끝난 뒤 다시 들을지 정한다. */
export function decideNextTurn(enabled: boolean, emptyTurns: number, outcome: TurnOutcome): ConversationDecision {
  if (outcome === "answered") {
    return { continueListening: enabled, emptyTurns: 0 };
  }
  if (outcome === "empty") {
    const nextEmptyTurns = emptyTurns + 1;
    return { continueListening: enabled && nextEmptyTurns < MAX_EMPTY_TURNS, emptyTurns: nextEmptyTurns };
  }
  return { continueListening: false, emptyTurns: 0 };
}

export function formatSilenceLabel(silenceMs: number): string {
  return `${silenceMs / 1000}초`;
}

export type TranscriptState = { finalParts: string[]; interim: string };

export const EMPTY_TRANSCRIPT: TranscriptState = { finalParts: [], interim: "" };

/**
 * 연속 인식 결과를 모은다.
 * iOS 는 중간 결과가 누적된 전체 글이고, 안드로이드는 확정된 구간마다 따로 온다.
 * 확정 구간은 쌓고, 중간 결과는 마지막 것만 둔다.
 */
export function appendResult(state: TranscriptState, transcript: string, isFinal: boolean): TranscriptState {
  const text = transcript.trim();
  if (isFinal) {
    return { finalParts: text ? [...state.finalParts, text] : state.finalParts, interim: "" };
  }
  return { finalParts: state.finalParts, interim: text };
}

export function transcriptText(state: TranscriptState): string {
  return [...state.finalParts, state.interim].filter(Boolean).join(" ");
}

export type TimeoutReason = "silence" | "noSpeech";

export type TimerApi = {
  set: (callback: () => void, ms: number) => unknown;
  clear: (handle: unknown) => void;
};

const DEFAULT_TIMERS: TimerApi = {
  set: (callback, ms) => setTimeout(callback, ms),
  clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

export type SilenceTimer = {
  /** 듣기 시작: 말이 없는지 재기 시작. */
  start: () => void;
  /** 새 글자가 들어옴: 쉬는 시간을 처음부터 다시 잰다. */
  bump: () => void;
  cancel: () => void;
};

/** 말이 없거나 멈춘 시간을 재다가 한 번만 onTimeout 을 부른다. */
export function createSilenceTimer(
  getSilenceMs: () => number,
  onTimeout: (reason: TimeoutReason) => void,
  noSpeechMs: number = NO_SPEECH_TIMEOUT_MS,
  timers: TimerApi = DEFAULT_TIMERS,
): SilenceTimer {
  let handle: unknown = null;

  const cancel = () => {
    if (handle !== null) {
      timers.clear(handle);
      handle = null;
    }
  };

  const arm = (ms: number, reason: TimeoutReason) => {
    cancel();
    handle = timers.set(() => {
      handle = null;
      onTimeout(reason);
    }, ms);
  };

  return {
    start: () => arm(noSpeechMs, "noSpeech"),
    bump: () => arm(getSilenceMs(), "silence"),
    cancel,
  };
}
