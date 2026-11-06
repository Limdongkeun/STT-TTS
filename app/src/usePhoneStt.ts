/** 폰 기본 STT (iOS SFSpeechRecognizer / 안드로이드 SpeechRecognizer). */

import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from "expo-speech-recognition";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  appendResult, createSilenceTimer, DEFAULT_SILENCE_MS, EMPTY_TRANSCRIPT, transcriptText,
  type TranscriptState,
} from "./conversation";
import { CONTEXTUAL_WORDS } from "./sttModes";

/** 한 턴을 마칠 때 같이 넘기는 것. */
export type PhoneTurn = {
  /** 말하는 중 마지막으로 글자가 들어온 시각(Date.now 기준). 말이 끝난 때로 본다. 없으면 null */
  speechEndedAt: number | null;
  /** persistAudio 일 때 폰 STT 가 들은 소리 파일(16kHz WAV). 없으면 null */
  audioUri: string | null;
  /** 이 턴에 소리 파일을 달라고 했는지. 달라고 했는데 audioUri 가 없으면 폰이 파일을 안 준 것이다. */
  audioRequested: boolean;
};

type Options = {
  silenceMs?: number;
  /** 듣기를 시작할 때 물어본다: 들은 소리를 파일로 남길지(다음 주 서버 STT 와 같은 소리로 비교). */
  persistAudio?: () => boolean;
  onFinished: (transcript: string, turn: PhoneTurn) => void;
  onError: (message: string) => void;
};

type Session = {
  phase: "permission" | "starting" | "listening" | "stopping" | "ending" | "cancelled";
  transcript: TranscriptState;
  error?: string;
  lastSpeechAt: number | null;
  audioUri: string | null;
  audioRequested: boolean;
};

// 서버 STT 모델(Qwen3-ASR)이 받는 모양과 같게: 16kHz 16비트
const RECORDING_OPTIONS = { persist: true, outputSampleRate: 16_000, outputEncoding: "pcmFormatInt16" } as const;

export function usePhoneStt({ silenceMs = DEFAULT_SILENCE_MS, persistAudio, onFinished, onError }: Options) {
  const [liveTranscript, setLiveTranscript] = useState("");
  const sessionRef = useRef<Session | null>(null);
  const silenceRef = useRef(silenceMs);
  const persistRef = useRef(persistAudio);
  persistRef.current = persistAudio;

  useEffect(() => {
    silenceRef.current = silenceMs;
  }, [silenceMs]);


  const [timer] = useState(() => createSilenceTimer(
    () => silenceRef.current,
    () => stop(),
  ));

  function stop() {
    const session = sessionRef.current;
    if (session?.phase !== "listening") return;
    session.phase = "stopping";
    timer.cancel();
    ExpoSpeechRecognitionModule.stop();
  }

  const cancel = useCallback(() => {
    const session = sessionRef.current;
    if (!session || session.phase === "cancelled") return;
    timer.cancel();
    if (session.phase === "permission") {
      sessionRef.current = null;
      return;
    }
    const alreadyEnding = session.phase === "ending";
    session.phase = "cancelled";
    // Wait for the native end event before accepting another start.
    if (!alreadyEnding) ExpoSpeechRecognitionModule.abort();
  }, [timer]);

  useEffect(() => cancel, [cancel]);

  useSpeechRecognitionEvent("start", () => {
    const session = sessionRef.current;
    if (session?.phase !== "starting") return;
    session.phase = "listening";
    timer.start();
  });

  useSpeechRecognitionEvent("result", (event) => {
    const session = sessionRef.current;
    if (session?.phase !== "listening" && session?.phase !== "stopping") return;
    const text = event.results[0]?.transcript;
    if (!text?.trim()) return;
    session.transcript = appendResult(session.transcript, text, event.isFinal);
    setLiveTranscript(transcriptText(session.transcript));
    if (session.phase === "listening") {
      session.lastSpeechAt = Date.now();
      timer.bump();
    }
  });

  // 소리 파일은 audioend 뒤에 다 써진다(end 보다 먼저 온다).
  useSpeechRecognitionEvent("audioend", (event) => {
    const session = sessionRef.current;
    if (session && session.phase !== "cancelled") session.audioUri = event.uri ?? null;
  });

  useSpeechRecognitionEvent("error", (event) => {
    const session = sessionRef.current;
    if (!session || session.phase === "cancelled" || session.phase === "ending") return;
    timer.cancel();
    session.phase = "ending";
    if (event.error === "no-speech" || event.error === "speech-timeout") {
      session.transcript = EMPTY_TRANSCRIPT;
    } else {
      session.error = `폰 STT 오류 (${event.error}): ${event.message}`;
    }
  });

  useSpeechRecognitionEvent("end", () => {
    const session = sessionRef.current;
    if (!session || session.phase === "permission") return;
    timer.cancel();
    sessionRef.current = null;
    if (session.phase === "cancelled") return;
    if (session.error) onError(session.error);
    else onFinished(transcriptText(session.transcript), {
      speechEndedAt: session.lastSpeechAt, audioUri: session.audioUri, audioRequested: session.audioRequested,
    });
  });

  const start = useCallback(async (): Promise<boolean> => {
    if (sessionRef.current) return false;
    const session: Session = { phase: "permission", transcript: EMPTY_TRANSCRIPT, lastSpeechAt: null, audioUri: null, audioRequested: false };
    sessionRef.current = session;
    setLiveTranscript("");
    try {
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (sessionRef.current !== session) return false;
      if (!permission.granted) {
        throw new Error("마이크·음성 인식 권한이 없어요. 설정에서 켜 주세요.");
      }
      session.phase = "starting";
      session.audioRequested = persistRef.current?.() ?? false;
      ExpoSpeechRecognitionModule.start({
        lang: "ko-KR",
        continuous: true,
        interimResults: true,
        addsPunctuation: true,
        contextualStrings: CONTEXTUAL_WORDS,
        ...(session.audioRequested ? { recordingOptions: RECORDING_OPTIONS } : {}),
      });
      return true;
    } catch (error) {
      if (sessionRef.current === session) {
        sessionRef.current = null;
        timer.cancel();
        onError(error instanceof Error ? error.message : String(error));
      }
      return false;
    }
  }, [onError, timer]);

  return { liveTranscript, start, stop, cancel };
}
