/** 말하는 사람 (부부 공유 업무 시험). 서버 /ask 의 speaker 값과 같다. */

export const SPEAKERS = ["wife", "husband"] as const;

export type Speaker = (typeof SPEAKERS)[number];

export const SPEAKER_LABELS: Record<Speaker, string> = {
  wife: "아내",
  husband: "남편",
};

export const DEFAULT_SPEAKER: Speaker = "wife";
