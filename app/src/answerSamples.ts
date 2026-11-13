/** '답 듣기' 칸의 순수 함수들 (테스트 대상).
 *  2026-11-12 사용자 요청: 질문을 말하지 않고도, 고른 목소리로 시험 답 34개를 바로 들어 본다. */

export type AnswerSample = { id: string; answer: string; spoken: string };

/** 이 칸에서 읽는 글은 소리용 입말(spoken). 화면에는 원래 답(answer)도 같이 보인다. */
export function answerTextFor(sample: AnswerSample): string {
  return sample.spoken;
}

/** startIndex 부터 끝까지(또는 그 줄 하나) 읽을 글. [전부 듣기]는 0, 줄의 [듣기]는 그 줄 하나만. */
export function answerReadingsFrom(
  samples: AnswerSample[], startIndex: number, onlyOne: boolean,
): string[] {
  const picked = onlyOne ? samples.slice(startIndex, startIndex + 1) : samples.slice(startIndex);
  return picked.map(answerTextFor);
}

/** 서버를 모르면(엔진 없음) 못 듣는다. 지수 녹음도 2026-11-12부터 입말 34개를 모두 녹음해서 들을 수 있다. */
export function canListenAnswers(ttsEngine: string | undefined): boolean {
  return ttsEngine !== undefined;
}
