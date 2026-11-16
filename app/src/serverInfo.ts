/** 서버 /health 응답을 화면 글로 바꾼다 (순수 함수, 테스트 대상). */

export type HealthResponse = {
  status: string;
  sttEngine: string;
  ttsEngine: string;
  answerProvider: string;
  /** 실제 모델을 쓸 때만 채워진다(예: "Qwen/Qwen3-ASR-1.7B"). 예전 서버에는 없다. */
  sttModel?: string;
  ttsModel?: string;
  /** 서버 STT 에 넣는 힌트 낱말 수(0 = 없음). 폰 STT 는 늘 같은 목록을 쓴다. 예전 서버에는 없다. */
  sttHints?: number;
  /** 서버 하나로 합쳐 띄웠을 때 앱 버튼으로 고를 수 있는 TTS. label 은 시험표에 적는 이름. 예전 서버에는 없다. */
  ttsChoices?: TtsChoice[];
  /** 버튼 방식에서 고를 수 있는 서버 STT(첫째가 기본, 2026-11-16 LFM3 추가~). label 은 시험표에 적는 이름. 예전 서버에는 없다. */
  sttChoices?: SttChoice[];
  /** /ask 미리보기(기록을 바꾸지 않는 답)를 아는 서버(2026-11-16~). 예전 서버에는 없다 — 그때는 미리 묻지 않는다. */
  askPreview?: boolean;
};

export type TtsChoice = { engine: string; label: string };
export type SttChoice = TtsChoice;

const TTS_BUTTON_LABELS: Record<string, string> = {
  prerecorded: "지수 녹음",
  "qwen3-tts-107": "107 G 목소리",
  "qwen3-tts-107-h2": "107 H2 목소리",
  "lfm3-tts-female": "LFM3 여자",
  "lfm3-tts-male": "LFM3 남자",
  "qwen3-tts": "맥 Qwen TTS",
  mock: "삐 (mock)",
};

/** 버튼에 쓰는 짧은 이름. 모르는 엔진은 이름 그대로. */
export function ttsButtonLabel(engine: string): string {
  return TTS_BUTTON_LABELS[engine] ?? engine;
}

function validChoices(choices: unknown): TtsChoice[] {
  if (!Array.isArray(choices)) return [];
  return choices.filter(
    (choice): choice is TtsChoice =>
      typeof choice === "object" && choice !== null && typeof choice.engine === "string" && typeof choice.label === "string",
  );
}

/** /health 의 ttsChoices 중 모양이 맞는 것만. 없거나 이상하면 빈 목록(예전 서버: 고르기 버튼 없음). */
export function ttsChoicesOf(health: HealthResponse | null): TtsChoice[] {
  return validChoices(health?.ttsChoices);
}

/** /health 의 sttChoices 중 모양이 맞는 것만. 없으면 빈 목록(예전 서버: 서버 STT 버튼 하나). */
export function sttChoicesOf(health: HealthResponse | null): SttChoice[] {
  return validChoices(health?.sttChoices);
}

const STT_BUTTON_LABELS: Record<string, string> = {
  "qwen3-asr": "서버 Qwen3-ASR",
  "lfm3-asr": "서버 LFM3",
  mock: "서버 mock",
};

/** 서버 STT 버튼 이름. 모르는 엔진은 '서버 <이름>'. */
export function sttButtonLabel(engine: string): string {
  return STT_BUTTON_LABELS[engine] ?? `서버 ${engine}`;
}

/** 지금 쓸 TTS: 고른 것이 서버 목록에 있으면 그것, 아니면 서버 기본. 서버를 모르면 undefined. */
export function activeTtsChoice(
  health: HealthResponse | null, chosen: string | null,
): { engine: string | undefined; label: string } {
  const choices = ttsChoicesOf(health);
  const engine = chosen && choices.some((choice) => choice.engine === chosen) ? chosen : health?.ttsEngine;
  return { engine, label: choices.find((choice) => choice.engine === engine)?.label ?? "" };
}

export const PHONE_STT_LABEL = "폰 기본 STT";

/** 시험표에 적을 STT 이름. 폰 기본 STT, 또는 서버 STT 의 모델 이름(조직 이름 뺌).
 * 서버 STT 가 힌트를 쓰면 '· 힌트 42'를 붙인다: 힌트 있고 없음은 다른 조건이라 저장본 비교도 따로 한다. */
export function sttLabelFor(
  mode: "phone" | "server", sttServerHealth: HealthResponse | null, serverEngine: string | null = null,
): string {
  if (mode === "phone") return PHONE_STT_LABEL;
  if (!sttServerHealth) return "서버 STT(모델 확인 안 됨)";
  // 서버가 고르기 목록을 주면 고른 STT 의 이름(목록에 없으면 기본=첫째)을 그대로 쓴다.
  const choices = sttChoicesOf(sttServerHealth);
  if (choices.length > 0) return (choices.find((choice) => choice.engine === serverEngine) ?? choices[0]).label;
  if (sttServerHealth.sttEngine === "mock") return "서버 mock STT";
  const model = sttServerHealth.sttModel?.split("/").pop() || `서버 ${sttServerHealth.sttEngine}`;
  const hints = sttServerHealth.sttHints ?? 0;
  return hints > 0 ? `${model} · 힌트 ${hints}` : model;
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
