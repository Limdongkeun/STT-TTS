/** 폰 기본 STT (iOS SFSpeechRecognizer / 안드로이드 SpeechRecognizer). */

import {
  ExpoSpeechRecognitionModule, useSpeechRecognitionEvent, type ExpoSpeechRecognitionOptions,
} from "expo-speech-recognition";
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
  /** 끼어들기 대기 중(가족비서가 말하는 동안)에 받아 적은 글이 바뀔 때마다. 끼어든 말이면 confirmBargeIn 을 부른다. */
  onHeard?: (transcript: string) => void;
  /** 보통 듣기(끼어들기 대기가 아님) 중에 받아 적은 글이 바뀔 때마다. 대화 모드가 답을 미리 만드는 데 쓴다. */
  onTranscript?: (transcript: string) => void;
};

/** start 옵션. bargeIn: 가족비서가 말하는 동안 듣는다(자기 소리 빼기를 켜고, 끼어들기 전에는 턴을 끝내지 않는다). */
export type PhoneStartOptions = { bargeIn?: boolean };

type Session = {
  phase: "permission" | "starting" | "listening" | "stopping" | "ending" | "cancelled";
  transcript: TranscriptState;
  error?: string;
  lastSpeechAt: number | null;
  audioUri: string | null;
  audioRequested: boolean;
  /** 끼어들기 대기 중: 받아 적은 글을 onHeard 로만 넘기고, 쉬는 시간을 재지 않고, 끝나도 아무것도 부르지 않는다. */
  armed: boolean;
  /** cancel 을 기다리는 쪽(end 이벤트가 오면 부른다). */
  endWaiters: (() => void)[];
};

/** cancel 뒤 end 이벤트를 이만큼(ms)만 기다린다(오지 않아도 대화가 멈추지 않게). */
const CANCEL_WAIT_MS = 1500;

// 끼어들기: 답 소리를 스피커로 내면서 듣고, iOS 의 자기 소리 빼기(통화와 같은 방식)를 켠다.
const BARGE_IN_OPTIONS: Pick<ExpoSpeechRecognitionOptions, "iosVoiceProcessingEnabled" | "iosCategory"> = {
  iosVoiceProcessingEnabled: true,
  iosCategory: { category: "playAndRecord", categoryOptions: ["defaultToSpeaker", "allowBluetooth"], mode: "voiceChat" },
};

// 서버 STT 모델(Qwen3-ASR)이 받는 모양과 같게: 16kHz 16비트
const RECORDING_OPTIONS = { persist: true, outputSampleRate: 16_000, outputEncoding: "pcmFormatInt16" } as const;

export function usePhoneStt({
  silenceMs = DEFAULT_SILENCE_MS, persistAudio, onFinished, onError, onHeard, onTranscript,
}: Options) {
  const [liveTranscript, setLiveTranscript] = useState("");
  /** 폰이 정말 듣기 시작했는지(start 이벤트). 대화 화면은 이때만 '말하세요'를 띄운다 — 앞이 잘리지 않게(11/13 C6·D5). */
  const [ready, setReady] = useState(false);
  const sessionRef = useRef<Session | null>(null);
  const silenceRef = useRef(silenceMs);
  const persistRef = useRef(persistAudio);
  persistRef.current = persistAudio;
  const onHeardRef = useRef(onHeard);
  onHeardRef.current = onHeard;
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

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

  /** 듣기를 버린다. 돌려주는 약속은 폰이 정말 끝낸 뒤(end 이벤트) 풀린다 — 그 뒤에야 새로 start 할 수 있다. */
  const cancel = useCallback((): Promise<void> => {
    const session = sessionRef.current;
    if (!session) return Promise.resolve();
    timer.cancel();
    if (session.phase === "permission") {
      sessionRef.current = null;
      return Promise.resolve();
    }
    const ended = new Promise<void>((resolve) => {
      session.endWaiters.push(resolve);
      setTimeout(resolve, CANCEL_WAIT_MS);
    });
    if (session.phase === "cancelled") return ended;
    const alreadyEnding = session.phase === "ending";
    session.phase = "cancelled";
    // Wait for the native end event before accepting another start.
    if (!alreadyEnding) ExpoSpeechRecognitionModule.abort();
    return ended;
  }, [timer]);

  /** 끼어든 말이다: 대기를 풀고 보통 턴처럼 말이 멈출 때까지 듣는다(받아 적은 글은 그대로 이어진다). */
  const confirmBargeIn = useCallback((): boolean => {
    const session = sessionRef.current;
    if (!session?.armed || (session.phase !== "starting" && session.phase !== "listening")) return false;
    session.armed = false;
    if (session.phase === "listening") {
      session.lastSpeechAt = Date.now();
      timer.bump();
    }
    return true;
  }, [timer]);

  useEffect(() => () => void cancel(), [cancel]);

  useSpeechRecognitionEvent("start", () => {
    const session = sessionRef.current;
    if (session?.phase !== "starting") return;
    session.phase = "listening";
    setReady(true);
    // 끼어들기 대기 중에는 '말이 없음'을 재지 않는다(답이 길 수 있다). 시작 전에 끼어들기로 바뀌었으면 바로 잰다.
    if (!session.armed) {
      if (session.lastSpeechAt === null) timer.start();
      else timer.bump();
    }
  });

  useSpeechRecognitionEvent("result", (event) => {
    const session = sessionRef.current;
    if (session?.phase !== "listening" && session?.phase !== "stopping") return;
    const text = event.results[0]?.transcript;
    if (!text?.trim()) return;
    session.transcript = appendResult(session.transcript, text, event.isFinal);
    setLiveTranscript(transcriptText(session.transcript));
    if (session.armed) {
      onHeardRef.current?.(transcriptText(session.transcript));
      return;
    }
    if (session.phase === "listening") {
      session.lastSpeechAt = Date.now();
      timer.bump();
      onTranscriptRef.current?.(transcriptText(session.transcript));
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
    setReady(false);
    session.endWaiters.forEach((resolve) => resolve());
    // 끼어들지 않은 채 끝난 대기는 조용히 버린다(답을 다 읽으면 App 이 새로 듣는다).
    if (session.phase === "cancelled" || session.armed) return;
    if (session.error) onError(session.error);
    else onFinished(transcriptText(session.transcript), {
      speechEndedAt: session.lastSpeechAt, audioUri: session.audioUri, audioRequested: session.audioRequested,
    });
  });

  const start = useCallback(async ({ bargeIn = false }: PhoneStartOptions = {}): Promise<boolean> => {
    if (sessionRef.current) return false;
    const session: Session = {
      phase: "permission", transcript: EMPTY_TRANSCRIPT, lastSpeechAt: null, audioUri: null, audioRequested: false,
      armed: bargeIn, endWaiters: [],
    };
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
        ...(bargeIn ? BARGE_IN_OPTIONS : {}),
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

  return { liveTranscript, ready, start, stop, cancel, confirmBargeIn };
}
