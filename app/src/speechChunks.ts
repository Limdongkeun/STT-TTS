/** 답 소리를 문장으로 나눠 첫 문장부터 트는 데 쓰는 순수 함수들 (테스트 대상).
 *
 * 2026-11-09 시험: 107 TTS 는 답 전체를 다 만든 뒤에야 소리를 줘서 TTS 기다림이 평균 3.7초였다
 * (66~70자 답은 6초 넘게). 첫 문장만 먼저 만들어 틀고, 그동안 다음 문장을 만든다.
 * 사전 녹음(prerecorded)은 답 전체가 녹음 하나라 나누지 않는다.
 */

/** 이보다 글자(한글·영문·숫자)가 적은 조각은 옆 문장에 붙인다("네." 하나만 따로 읽지 않게). */
export const MIN_CHUNK_LETTERS = 5;

const SENTENCE_END = new Set([".", "?", "!", "。", "…"]);
const LETTER = /[0-9A-Za-z가-힣]/g;

function letterCount(text: string): number {
  return text.match(LETTER)?.length ?? 0;
}

/** 문장 끝 부호 뒤에 띄어쓰기나 글 끝이 올 때만 자른다('1.5' 는 자르지 않는다). 부호는 앞 문장에 남긴다. */
export function splitSpeech(text: string): string[] {
  const pieces: string[] = [];
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    const next = text[index + 1];
    if (SENTENCE_END.has(text[index]) && (next === undefined || /\s/.test(next))) {
      pieces.push(text.slice(start, index + 1));
      start = index + 1;
    }
  }
  pieces.push(text.slice(start));
  const trimmed = pieces.map((piece) => piece.trim()).filter((piece) => piece.length > 0);

  const chunks: string[] = [];
  let carry = "";
  for (const piece of trimmed) {
    const joined = carry ? `${carry} ${piece}` : piece;
    if (letterCount(joined) < MIN_CHUNK_LETTERS) {
      carry = joined;
      continue;
    }
    chunks.push(joined);
    carry = "";
  }
  if (carry) {
    if (chunks.length > 0) chunks[chunks.length - 1] = `${chunks[chunks.length - 1]} ${carry}`;
    else chunks.push(carry);
  }
  return chunks;
}

/** 소리를 그때그때 만드는 TTS 만 나눈다. 엔진을 모르면(서버 상태 확인 실패) 나누지 않는다. */
export function shouldSplitSpeech(ttsEngine: string | undefined): boolean {
  return ttsEngine === "qwen3-tts-107" || ttsEngine === "qwen3-tts";
}

export class SpeechCancelledError extends Error {
  constructor() {
    super("답 읽기를 멈췄어요.");
    this.name = "SpeechCancelledError";
  }
}

/** 한 번에 하나씩 차례로 만든다(107 GPU 를 같이 쓰므로 동시에 부르지 않는다).
 *  앞 것이 끝나야 다음을 부르고, 앞 것이 실패하거나 shouldContinue 가 false 면 뒤는 부르지 않는다. */
export function fetchSequentially<T>(
  items: string[],
  fetchOne: (item: string) => Promise<T>,
  shouldContinue: () => boolean = () => true,
): Promise<T>[] {
  const results: Promise<T>[] = [];
  let previous: Promise<unknown> = Promise.resolve();
  for (const item of items) {
    const current = previous.then(() => {
      if (!shouldContinue()) throw new SpeechCancelledError();
      return fetchOne(item);
    });
    // 아무도 기다리지 않는 뒤 조각의 실패가 '처리 안 된 거부' 경고로 뜨지 않게 한다(기다리는 쪽은 그대로 받는다).
    current.catch(() => undefined);
    results.push(current);
    previous = current;
  }
  return results;
}
