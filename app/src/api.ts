/** 시험 서버 호출. 서버 응답 키는 camelCase. */

import { audioFileName, audioMimeType, joinUrl, normalizeBaseUrl } from "./url";

const REQUEST_TIMEOUT_MS = 120_000;

export const sttServerUrl = normalizeBaseUrl(process.env.EXPO_PUBLIC_STT_SERVER_URL);
export const ttsServerUrl = normalizeBaseUrl(process.env.EXPO_PUBLIC_TTS_SERVER_URL);

export type SttResponse = { text: string; language: string | null; engine: string; elapsedMs: number };
export type AskResponse = { answerText: string; speechText: string; provider: string; elapsedMs: number };
export type TtsResponse = {
  audioUrl: string;
  durationSec: number;
  sampleRate: number;
  engine: string;
  elapsedMs: number;
};

type ReactNativeFile = { uri: string; name: string; type: string };

function requireUrl(url: string | null, name: string): string {
  if (!url) {
    throw new Error(`${name} 주소가 없거나 잘못됐어요. app/.env 를 확인하세요.`);
  }
  return url;
}

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = typeof body === "object" && body !== null && "detail" in body ? String(body.detail) : "";
      throw new Error(`서버 오류 ${response.status} ${detail}`.trim());
    }
    return body as T;
  } finally {
    clearTimeout(timer);
  }
}

export function postStt(recordingUri: string): Promise<SttResponse> {
  const baseUrl = requireUrl(sttServerUrl, "STT 서버");
  const name = audioFileName(recordingUri);
  const file: ReactNativeFile = { uri: recordingUri, name, type: audioMimeType(name) };
  const form = new FormData();
  // React Native 의 FormData 는 {uri,name,type} 객체를 파일로 보낸다.
  form.append("audio", file as unknown as Blob);
  return request<SttResponse>(joinUrl(baseUrl, "/stt"), { method: "POST", body: form });
}

export function postAsk(text: string): Promise<AskResponse> {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  return request<AskResponse>(joinUrl(baseUrl, "/ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function postTts(text: string): Promise<TtsResponse & { fullAudioUrl: string }> {
  const baseUrl = requireUrl(ttsServerUrl, "TTS 서버");
  const result = await request<TtsResponse>(joinUrl(baseUrl, "/tts"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return { ...result, fullAudioUrl: joinUrl(baseUrl, result.audioUrl) };
}
