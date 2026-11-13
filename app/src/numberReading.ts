/** 숫자 읽기 시험의 순수 함수들 (테스트 대상).
 *  2026-11-12 사용자 요청: 말하지 않고, TTS 가 날짜·시각·금액·약 용량 같은 숫자를 제대로 읽는지만 듣고 ○/× 를 남긴다. */

export type ReadingSample = { id: string; group: string; text: string; reading: string };
export type ReadingHeard = "○" | "×";
/** memo: × 일 때 어떻게 잘못 읽었는지(예: '일 일'로 끊어 읽음). 서버에서 200자까지 받는다. */
export type ReadingMarks = Record<string, { heard: ReadingHeard; memo?: string }>;
export const MAX_READING_MEMO_CHARS = 200;

/** 같은 표시를 다시 누르면 지운다(잘못 누른 것을 되돌리게). */
export function toggleReadingMark(marks: ReadingMarks, id: string, heard: ReadingHeard): ReadingMarks {
  const next = { ...marks };
  if (next[id]?.heard === heard) delete next[id];
  else next[id] = { heard };
  return next;
}

/** × 줄에만 메모를 단다. 표시가 없거나 ○ 인 줄은 그대로 둔다. */
export function setReadingMemo(marks: ReadingMarks, id: string, memo: string): ReadingMarks {
  if (marks[id]?.heard !== "×") return marks;
  return { ...marks, [id]: { heard: "×", memo: memo.slice(0, MAX_READING_MEMO_CHARS) } };
}

export function countReadingMarks(samples: ReadingSample[], marks: ReadingMarks) {
  let ok = 0;
  let bad = 0;
  for (const sample of samples) {
    const heard = marks[sample.id]?.heard;
    if (heard === "○") ok += 1;
    else if (heard === "×") bad += 1;
  }
  return { ok, bad, todo: samples.length - ok - bad, total: samples.length };
}

/** 그때그때 소리를 만드는 TTS 만 이 시험을 할 수 있다. 사전 녹음은 정해진 답 문장만 있다. */
export function canTestReading(ttsEngine: string | undefined): boolean {
  return ttsEngine !== undefined && ttsEngine !== "prerecorded";
}

/** startIndex 부터 끝까지 읽기 글. [전부 듣기]는 0, 줄의 [듣기]는 그 줄 하나만. */
export function readingsFrom(samples: ReadingSample[], startIndex: number, onlyOne: boolean): string[] {
  const picked = onlyOne ? samples.slice(startIndex, startIndex + 1) : samples.slice(startIndex);
  return picked.map((sample) => sample.reading);
}
