/** 서버 /health 응답을 화면 글로 바꾼다 (순수 함수, 테스트 대상). */

export type HealthResponse = {
  status: string;
  sttEngine: string;
  ttsEngine: string;
  answerProvider: string;
  /** 실제 모델을 쓸 때만 채워진다(예: "Qwen/Qwen3-ASR-1.7B"). 예전 서버에는 없다. */
  sttModel?: string;
  ttsModel?: string;
};

export const PHONE_STT_LABEL = "폰 기본 STT";

/** 시험표에 적을 STT 이름. 폰 기본 STT, 또는 서버 STT 의 모델 이름(조직 이름 뺌). */
export function sttLabelFor(mode: "phone" | "server", sttServerHealth: HealthResponse | null): string {
  if (mode === "phone") return PHONE_STT_LABEL;
  if (!sttServerHealth) return "서버 STT(모델 확인 안 됨)";
  if (sttServerHealth.sttEngine === "mock") return "서버 mock STT";
  const model = sttServerHealth.sttModel?.split("/").pop();
  return model || `서버 ${sttServerHealth.sttEngine}`;
}

const ANSWER_PROVIDER_LABELS: Record<string, string> = {
  "family-demo": "가족 돌봄 시험(family-demo)",
  fixed: "고정 답(fixed)",
};

export function isHealthResponse(body: unknown): body is HealthResponse {
  if (typeof body !== "object" || body === null) {
    return false;
  }
  const record = body as Record<string, unknown>;
  return ["status", "sttEngine", "ttsEngine", "answerProvider"].every((key) => typeof record[key] === "string");
}

export type ServerInfo = { kind: "checking" } | { kind: "ok"; health: HealthResponse } | { kind: "error"; message: string };

export function describeServerInfo(info: ServerInfo): string {
  if (info.kind === "checking") {
    return "서버 확인 중…";
  }
  if (info.kind === "error") {
    return `서버 연결 안 됨: ${info.message}`;
  }
  const { answerProvider, ttsEngine } = info.health;
  const answerLabel = ANSWER_PROVIDER_LABELS[answerProvider] ?? answerProvider;
  return `답: ${answerLabel} · TTS: ${ttsEngine}`;
}
