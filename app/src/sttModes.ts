export type SttMode = "phone" | "server";

export const STT_MODE_LABELS: Record<SttMode, string> = {
  phone: "폰 기본 STT",
  server: "서버 Qwen3-ASR",
};

/** 폰 기본 STT 에 넘길 자주 나오는 단어 (가족 호칭·이름). 인식을 돕는다. */
export const CONTEXTUAL_WORDS = ["외할머니", "할머니", "할아버지", "엄마", "아빠", "가족 일정", "학원", "병원"];
