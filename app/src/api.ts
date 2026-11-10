/** 시험 서버 호출. 서버 응답 키는 camelCase. */

import { isHealthResponse, type HealthResponse } from "./serverInfo";
import { DEFAULT_SPEAKER, type Speaker } from "./speaker";
import type { Attempt, SheetResult, TestCase } from "./testSheet";
import { readUploadResult } from "./uploadResult";
import { audioFileName, audioMimeType, joinUrl, normalizeBaseUrl } from "./url";

const REQUEST_TIMEOUT_MS = 120_000;
const HEALTH_TIMEOUT_MS = 5_000;

export const sttServerUrl = normalizeBaseUrl(process.env.EXPO_PUBLIC_STT_SERVER_URL);
export const ttsServerUrl = normalizeBaseUrl(process.env.EXPO_PUBLIC_TTS_SERVER_URL);

export type SttResponse = { text: string; language: string | null; engine: string; elapsedMs: number };
/** 서버가 들고 다니라고 준 대화 상태. last_topic: 바로 앞 턴에 답한 주제(예: "shopping"). */
export type AskContext = { awaiting_dose_time: boolean; dose_at?: string; last_topic?: string };
export type AskResponse = {
  answerText: string;
  speechText: string;
  provider: string;
  elapsedMs: number;
  context?: AskContext;
  /** family-demo 가 보정한 뒤의 글(띄어쓰기 없음). 시험표에 보정 전·후를 함께 남긴다 */
  correctedText?: string;
};
export type TtsResponse = {
  audioUrl: string;
  durationSec: number;
  sampleRate: number;
  engine: string;
  elapsedMs: number;
};

type ReactNativeFile = { uri: string; name: string; type: string };

/** 서버가 오류로 답했을 때. status 로 오류 종류를 가른다. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** 사전 녹음 TTS 에 이 답의 녹음이 없을 때(서버 /tts 404). 화면 답만 보여 주면 된다. */
export class NoRecordingError extends Error {}

function requireUrl(url: string | null, name: string): string {
  if (!url) {
    throw new Error(`${name} 주소가 없거나 잘못됐어요. app/.env 를 확인하세요.`);
  }
  return url;
}

async function request<T>(url: string, init: RequestInit, timeoutMs: number = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = typeof body === "object" && body !== null && "detail" in body ? String(body.detail) : "";
      throw new ApiError(`서버 오류 ${response.status} ${detail}`.trim(), response.status);
    }
    return body as T;
  } finally {
    clearTimeout(timer);
  }
}

/** 녹음 파일 하나를 multipart 필드 audio 로 올린다.
 * 전역 fetch(Expo)는 {uri,name,type} 파일을 못 보내서 XMLHttpRequest 를 쓴다(uploadResult.ts 참고). */
function uploadAudio<T>(url: string, method: "POST" | "PUT", recordingUri: string): Promise<T> {
  const name = audioFileName(recordingUri);
  const file: ReactNativeFile = { uri: recordingUri, name, type: audioMimeType(name) };
  const form = new FormData();
  // React Native 의 FormData 는 {uri,name,type} 객체를 파일로 보낸다.
  form.append("audio", file as unknown as Blob);
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.timeout = REQUEST_TIMEOUT_MS;
    xhr.onload = () => {
      const result = readUploadResult(xhr.status, xhr.responseText);
      if (result.ok) resolve(result.body as T);
      else reject(new ApiError(result.message, result.status));
    };
    // 연결 실패는 status 0 으로 읽는다(서버 꺼짐·주소 틀림 안내).
    xhr.onerror = () => {
      const result = readUploadResult(0, "");
      reject(new ApiError(result.ok ? "" : result.message, 0));
    };
    xhr.ontimeout = () => reject(new Error(`서버가 ${REQUEST_TIMEOUT_MS / 1000}초 안에 답하지 않았어요.`));
    xhr.send(form);
  });
}

/** 답·TTS 서버의 지금 모드(답 모드, 엔진)를 묻는다. */
export async function getHealth(target: "tts" | "stt" = "tts"): Promise<HealthResponse> {
  const baseUrl = target === "tts" ? requireUrl(ttsServerUrl, "TTS 서버") : requireUrl(sttServerUrl, "STT 서버");
  const body = await request<unknown>(joinUrl(baseUrl, "/health"), { method: "GET" }, HEALTH_TIMEOUT_MS);
  if (!isHealthResponse(body)) {
    throw new Error("서버 응답 모양이 달라요.");
  }
  return body;
}

export function postStt(recordingUri: string): Promise<SttResponse> {
  const baseUrl = requireUrl(sttServerUrl, "STT 서버");
  return uploadAudio<SttResponse>(joinUrl(baseUrl, "/stt"), "POST", recordingUri);
}

/** ttsEngine: 앱에서 고른 TTS(서버가 사전 녹음일 때만 읽기용 글을 녹음에 맞춘다). 없으면 서버 기본. */
export function postAsk(
  text: string, context?: AskContext, speaker: Speaker = DEFAULT_SPEAKER, ttsEngine?: string,
): Promise<AskResponse> {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  return request<AskResponse>(joinUrl(baseUrl, "/ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, context, speaker, ttsEngine }),
  });
}

/** 시험표 문장 목록 (C1~C7, D1~D25). */
export async function getTestCases(): Promise<TestCase[]> {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  const body = await request<{ cases: TestCase[] }>(joinUrl(baseUrl, "/test-cases"), { method: "GET" }, HEALTH_TIMEOUT_MS);
  return Array.isArray(body?.cases) ? body.cases : [];
}

function sheetUrl(device: string, path: string): string {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  return joinUrl(baseUrl, `/test-sheet/${encodeURIComponent(device)}${path}`);
}

/** 작성 중인 시험표 (문장 번호 → 결과). */
export async function getDraft(device: string): Promise<Record<string, SheetResult>> {
  const body = await request<{ results: Record<string, SheetResult> }>(sheetUrl(device, "/draft"), { method: "GET" }, HEALTH_TIMEOUT_MS);
  return body?.results ?? {};
}

/** 작성 중인 시험표에 한 문장의 결과를 통째로 저장한다. */
export function putDraftCase(device: string, caseId: string, result: SheetResult): Promise<SheetResult> {
  return request<SheetResult>(
    sheetUrl(device, `/draft/${encodeURIComponent(caseId)}`),
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(result) },
    HEALTH_TIMEOUT_MS,
  );
}

/** 폰 STT 가 들은 소리(WAV)를 그 문장 옆에 올린다. 서버가 지어 준 파일 이름을 돌려준다. */
export async function putDraftAudio(device: string, caseId: string, recordingUri: string): Promise<string> {
  const body = await uploadAudio<{ audioFile?: unknown } | null>(
    sheetUrl(device, `/draft/${encodeURIComponent(caseId)}/audio`), "PUT", recordingUri,
  );
  if (typeof body?.audioFile !== "string") throw new Error("서버 응답 모양이 달라요.");
  return body.audioFile;
}

/** 작성 중인 시험표를 비운다(저장본은 남는다). */
export async function clearDraft(device: string): Promise<void> {
  await request<unknown>(sheetUrl(device, "/draft"), { method: "DELETE" }, HEALTH_TIMEOUT_MS);
}

/** 작성 중인 시험표를 저장본으로 남긴다. */
export function saveAttempt(device: string): Promise<Attempt> {
  return request<Attempt>(sheetUrl(device, "/attempts"), { method: "POST" }, HEALTH_TIMEOUT_MS);
}

/** 저장본 목록(최신이 먼저). */
export async function getAttempts(device: string): Promise<Attempt[]> {
  const body = await request<{ attempts: Attempt[] }>(sheetUrl(device, "/attempts"), { method: "GET" }, HEALTH_TIMEOUT_MS);
  return Array.isArray(body?.attempts) ? body.attempts : [];
}

/** 서버의 부부 공유 업무 시험 기록(장보기·부탁·당번 등)을 처음 시험 데이터로 되돌린다. */
export async function resetDemo(): Promise<void> {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  await request<unknown>(joinUrl(baseUrl, "/demo/reset"), { method: "POST" }, HEALTH_TIMEOUT_MS);
}

/** engine: 앱에서 고른 TTS(/health ttsChoices 중 하나). 없으면 서버 기본. */
export async function postTts(text: string, engine?: string): Promise<TtsResponse & { fullAudioUrl: string }> {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  let result: TtsResponse;
  try {
    result = await request<TtsResponse>(joinUrl(baseUrl, "/tts"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, engine }),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) throw new NoRecordingError(error.message);
    throw error;
  }
  return { ...result, fullAudioUrl: joinUrl(baseUrl, result.audioUrl) };
}
