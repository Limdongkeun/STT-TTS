/** 폰 기본 STT (iOS SFSpeechRecognizer / 안드로이드 SpeechRecognizer). */

import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from "expo-speech-recognition";
import { useCallback, useRef, useState } from "react";

import { CONTEXTUAL_WORDS } from "./sttModes";

type Options = {
  onFinished: (transcript: string) => void;
  onError: (message: string) => void;
};

export function usePhoneStt({ onFinished, onError }: Options) {
  const [isListening, setIsListening] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const transcriptRef = useRef("");
  const failedRef = useRef(false);

  useSpeechRecognitionEvent("start", () => setIsListening(true));
  useSpeechRecognitionEvent("result", (event) => {
    const transcript = event.results[0]?.transcript ?? "";
    transcriptRef.current = transcript;
    setLiveTranscript(transcript);
  });
  useSpeechRecognitionEvent("error", (event) => {
    failedRef.current = true;
    onError(`폰 STT 오류 (${event.error}): ${event.message}`);
  });
  useSpeechRecognitionEvent("end", () => {
    setIsListening(false);
    if (!failedRef.current) {
      onFinished(transcriptRef.current.trim());
    }
  });

  const start = useCallback(async () => {
    const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
    if (!permission.granted) {
      onError("마이크·음성 인식 권한이 없어요. 설정에서 켜 주세요.");
      return;
    }
    transcriptRef.current = "";
    failedRef.current = false;
    setLiveTranscript("");
    ExpoSpeechRecognitionModule.start({
      lang: "ko-KR",
      interimResults: true,
      addsPunctuation: true,
      contextualStrings: CONTEXTUAL_WORDS,
    });
  }, [onError]);

  const stop = useCallback(() => {
    ExpoSpeechRecognitionModule.stop();
  }, []);

  return { isListening, liveTranscript, start, stop };
}
