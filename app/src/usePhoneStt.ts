/** 폰 기본 STT (iOS SFSpeechRecognizer / 안드로이드 SpeechRecognizer). */

import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from "expo-speech-recognition";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  appendResult, createSilenceTimer, DEFAULT_SILENCE_MS, EMPTY_TRANSCRIPT, transcriptText,
  type TranscriptState,
} from "./conversation";
import { CONTEXTUAL_WORDS } from "./sttModes";

type Options = {
  silenceMs?: number;
  onFinished: (transcript: string) => void;
  onError: (message: string) => void;
};

type Session = {
  phase: "permission" | "starting" | "listening" | "stopping" | "ending" | "cancelled";
  transcript: TranscriptState;
  error?: string;
};

export function usePhoneStt({ silenceMs = DEFAULT_SILENCE_MS, onFinished, onError }: Options) {
  const [liveTranscript, setLiveTranscript] = useState("");
  const sessionRef = useRef<Session | null>(null);
  const silenceRef = useRef(silenceMs);

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
    if (session.phase === "listening") timer.bump();
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
    else onFinished(transcriptText(session.transcript));
  });

  const start = useCallback(async (): Promise<boolean> => {
    if (sessionRef.current) return false;
    const session: Session = { phase: "permission", transcript: EMPTY_TRANSCRIPT };
    sessionRef.current = session;
    setLiveTranscript("");
    try {
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (sessionRef.current !== session) return false;
      if (!permission.granted) {
        throw new Error("마이크·음성 인식 권한이 없어요. 설정에서 켜 주세요.");
      }
      session.phase = "starting";
      ExpoSpeechRecognitionModule.start({
        lang: "ko-KR",
        continuous: true,
        interimResults: true,
        addsPunctuation: true,
        contextualStrings: CONTEXTUAL_WORDS,
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
