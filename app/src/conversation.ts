/** 대화 모드 규칙 (순수 함수, 테스트 대상). */

/** 말이 끝났다고 보는 쉬는 시간 후보(ms). 화면에서 고른다. */
export const SILENCE_OPTIONS_MS = [800, 1200, 1500, 2000, 3000] as const;
export const DEFAULT_SILENCE_MS = 1200;
/** 대화 모드는 빨리 답하는 게 먼저라 쉬는 시간을 더 짧게 시작한다(2026-11-16 사용자: 실시간 대화는 속도, 버튼은 정확도). */
export const CONVERSATION_SILENCE_MS = 800;
/** 듣기 시작 후 이 시간 동안 아무 말도 없으면 그 턴을 끝낸다. */
export const NO_SPEECH_TIMEOUT_MS = 8000;
/** 대화 화면에서 오류가 연달아 이만큼 나면 잠깐 쉰다(얼굴을 누르면 다시 듣는다). */
export const MAX_CONVERSATION_ERRORS = 3;
/** 오류가 난 뒤 다시 듣기까지 기다리는 시간(ms). 오류 글을 읽을 틈을 준다. */
export const RETRY_DELAY_MS = 1500;

export type TurnOutcome = "answered" | "empty" | "error" | "stopped";

/** listen: 바로 다시 듣기 / retry: 잠깐 뒤 다시 듣기 / pause: 쉬기(눌러야 다시) / stop: 끝(사용자가 멈춤) */
export type ConversationStep = { action: "listen" | "retry" | "pause" | "stop"; errors: number };

/** 대화 화면에서 한 턴이 끝난 뒤 할 일(2026-11-13 사용자 요청: 끝내기를 누를 때까지 멈추지 않는다).
 *  답했거나 말이 없었으면 바로 다시 듣는다. 오류는 연달아 MAX_CONVERSATION_ERRORS 번째에 쉰다. */
export function nextConversationStep(errors: number, outcome: TurnOutcome): ConversationStep {
  if (outcome === "answered") return { action: "listen", errors: 0 };
  if (outcome === "empty") return { action: "listen", errors };
  if (outcome === "stopped") return { action: "stop", errors };
  const nextErrors = errors + 1;
  return { action: nextErrors < MAX_CONVERSATION_ERRORS ? "retry" : "pause", errors: nextErrors };
}

/** 대화 화면 가운데 얼굴. preparing: 마이크 준비 중(아직 말하지 말 것) / listening: 말하세요 /
 *  thinking: 받아 적기·답 찾기 / speaking: 답 읽기 / paused: 오류가 이어져 쉬는 중 */
export type ConversationFace = "preparing" | "listening" | "thinking" | "speaking" | "paused";

export function conversationFace(
  stage: "idle" | "listening" | "transcribing" | "asking" | "speaking", micReady: boolean, paused: boolean,
): ConversationFace {
  if (paused) return "paused";
  if (stage === "listening") return micReady ? "listening" : "preparing";
  if (stage === "transcribing" || stage === "asking") return "thinking";
  if (stage === "speaking") return "speaking";
  return "preparing";
}

/** 끼어들기로 보려면 받아 적은 글이 이만큼(글자, 띄어쓰기·문장부호·숫자 빼고) 있어야 한다.
 *  2글자로는 스피커 소리가 뭉개진 첫 글자만 보고 끼어들기로 봐서, 자기 답을 듣고 되풀이했다(2026-11-16 폰 시험). */
export const BARGE_IN_MIN_CHARS = 4;
/** 짧아도 바로 끊는 말. 지금 읽는 답에 같은 말이 있으면(자기 소리일 수 있어) 이 규칙은 쓰지 않는다. */
export const STOP_WORDS = ["잠깐", "그만", "멈춰"] as const;
/** 받아 적은 글의 두 글자 묶음 중 이 비율 이상이 지금 읽는 답에 있으면 답 소리가 새어 들어온 것으로 본다. */
export const ECHO_OVERLAP = 0.5;

const compactText = (text: string) => text.replace(/[\s\p{P}\p{S}]/gu, "");
/** 자기 소리 비교용 글: 숫자는 뺀다(답에 쓴 '4만 2천'과 소리를 받아 적은 '42,000'이 달라 다른 말로 보였다). */
const echoText = (text: string) => compactText(text).replace(/\p{N}/gu, "");

function bigrams(text: string): string[] {
  if (text.length < 2) return text ? [text] : [];
  return Array.from({ length: text.length - 1 }, (_, index) => text.slice(index, index + 2));
}

/** heard 의 두 글자 묶음 중 speaking 에도 있는 비율(0~1). heard 가 비면 0. */
function echoRatio(heard: string, speaking: string): number {
  const pairs = bigrams(echoText(heard));
  if (pairs.length === 0) return 0;
  const reference = new Set(bigrams(echoText(speaking)));
  return pairs.filter((pair) => reference.has(pair)).length / pairs.length;
}

/** 가족비서가 말하는 동안 들린 글이 사람이 끼어든 말인지(2026-11-13 사용자 요청).
 *  heard: 답을 읽는 동안 받아 적은 글, speaking: 지금 읽는 답(화면 답·소리 글).
 *  '잠깐·그만·멈춰'는 바로 끼어들기다. 그 밖에는 너무 짧거나, 대부분이 읽는 답과 같은 글(폰이 자기 소리를 들은 것)이면 아니다. */
export function isBargeIn(heard: string, speaking: string): boolean {
  const words = echoText(heard);
  const reading = echoText(speaking);
  if (STOP_WORDS.some((word) => words.includes(word) && !reading.includes(word))) return true;
  if (words.length < BARGE_IN_MIN_CHARS) return false;
  return echoRatio(heard, speaking) < ECHO_OVERLAP;
}

/** 끼어들기로 들은 말이 끝났을 때, 그 말이 대부분 방금 읽던 답이면(자기 소리) 답하지 않는다(2026-11-16 되풀이 막기). */
export function isSelfEcho(heard: string, speaking: string): boolean {
  return echoRatio(heard, speaking) >= ECHO_OVERLAP;
}

/** 대화 화면 말풍선. caseId: 시험표에 적은 칸(없으면 시험표에 없는 말). */
export type ChatItem = { id: number; who: "me" | "bot"; text: string; caseId?: string | null };
/** 말풍선은 최근 이만큼만 둔다. */
export const MAX_CHAT_ITEMS = 30;

export function addChat(items: ChatItem[], added: Omit<ChatItem, "id">[]): ChatItem[] {
  const lastId = items.length > 0 ? items[items.length - 1].id : 0;
  const next = [...items, ...added.map((item, index) => ({ ...item, id: lastId + index + 1 }))];
  return next.slice(-MAX_CHAT_ITEMS);
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
