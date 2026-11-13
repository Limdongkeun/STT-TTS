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

/** 첫 조각이 이보다 글자가 많으면 쉼표에서 한 번 더 나눈다(2026-11-12, D21처럼 쉼표만 있는 긴 한 문장).
 *  2026-11-12 14:00 사용자 결정으로 splitSpeech 에서는 끔(통째가 더 자연스러움). 다시 켤 때를 위해 함수는 남긴다. */
export const LONG_FIRST_CHUNK_LETTERS = 25;
/** 쉼표에서 나눌 때 앞 조각이 이보다 짧으면 다음 쉼표까지 늘린다. */
export const MIN_COMMA_HEAD_LETTERS = 8;

/** 긴 첫 조각을 쉼표(뒤에 띄어쓰기)에서 앞·뒤 둘로 나눈다. 첫 소리만 당기면 되므로 한 번만 나눈다.
 *  뒤 조각까지 다 나누면 107 을 부를 때마다 드는 고정 시간만 늘어난다. 나눌 곳이 없으면 그대로. */
export function splitLongFirstChunk(chunk: string): string[] {
  if (letterCount(chunk) <= LONG_FIRST_CHUNK_LETTERS) return [chunk];
  for (let index = 0; index < chunk.length - 1; index += 1) {
    if (chunk[index] !== "," || !/\s/.test(chunk[index + 1])) continue;
    const head = chunk.slice(0, index + 1).trim();
    const tail = chunk.slice(index + 1).trim();
    if (letterCount(head) < MIN_COMMA_HEAD_LETTERS) continue;
    if (letterCount(tail) < MIN_CHUNK_LETTERS) break;
    return [head, tail];
  }
  return [chunk];
}

/** 문장 끝 부호 뒤에 띄어쓰기나 글 끝이 올 때만 자른다('1.5' 는 자르지 않는다). 부호는 앞 문장에 남긴다.
 *  한 문장은 쉼표가 있어도 통째로 읽는다. 2026-11-12 사용자 청취: C2를 쉼표에서 나눠 읽은 소리보다
 *  통째로 읽은 소리가 자연스러웠다(쉼표 앞뒤 억양이 이어짐). 그래서 splitLongFirstChunk 는 쓰지 않는다.
 *  대신 C2·D21처럼 쉼표만 있는 긴 한 문장은 첫 소리가 약 1초 늦다(11/12 10:46 시험 C2 2.4→3.4초). */
export function splitSpeech(text: string): string[] {
  return splitSentences(text);
}

function splitSentences(text: string): string[] {
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
  return ttsEngine === "qwen3-tts-107" || ttsEngine === "qwen3-tts-107-h2" || ttsEngine === "qwen3-tts";
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
