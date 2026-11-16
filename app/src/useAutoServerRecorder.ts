/** 서버 STT 대화용 녹음: 버튼 없이 말이 끝나면 저절로 멈춘다(소리 크기로 끝을 찾음, endpoint.ts).
 *  iOS 는 16kHz 한 채널 WAV 로 남겨 시험표에 소리를 붙일 수 있게 한다(서버는 WAV·CAF 만 받는다). */

import {
  AudioQuality,
  IOSOutputFormat,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  type RecordingOptions,
} from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";

import { DEFAULT_SILENCE_MS } from "./conversation";
import { createEndpointDetector, POLL_MS, type EndpointDetector } from "./endpoint";

const IOS_WAV: RecordingOptions = {
  ...RecordingPresets.HIGH_QUALITY,
  extension: ".wav",
  sampleRate: 16_000,
  numberOfChannels: 1,
  bitRate: 256_000,
  isMeteringEnabled: true,
  ios: {
    outputFormat: IOSOutputFormat.LINEARPCM,
    audioQuality: AudioQuality.MAX,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
};
// 안드로이드는 WAV 로 녹음할 수 없어 m4a 로 둔다(서버 STT 는 받지만 시험표에 소리는 붙지 않는다).
const RECORDING_OPTIONS: RecordingOptions = Platform.OS === "ios" ? IOS_WAV : { ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true };

export type AutoRecording = {
  uri: string;
  /** 마지막으로 말소리가 들린 시각(Date.now 기준). '말 끝→소리' 를 이때부터 잰다. */
  speechEndedAt: number;
  /** 시험표에 붙일 수 있는 WAV 인지 */
  isWav: boolean;
};

type Options = {
  silenceMs?: number;
  onFinished: (recording: AutoRecording) => void;
  /** 말이 시작되지 않고 끝났다(녹음은 버림). */
  onNoSpeech: () => void;
  onError: (message: string) => void;
};

type Session = { detector: EndpointDetector; startedAt: number; timer: ReturnType<typeof setInterval> | null; cancelled: boolean };

export function useAutoServerRecorder({ silenceMs = DEFAULT_SILENCE_MS, onFinished, onNoSpeech, onError }: Options) {
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  /** 마이크가 정말 녹음을 시작했는지(화면에 '말하세요'를 이때만 띄운다). */
  const [ready, setReady] = useState(false);
  const sessionRef = useRef<Session | null>(null);
  const silenceRef = useRef(silenceMs);
  silenceRef.current = silenceMs;
  const handlers = useRef({ onFinished, onNoSpeech, onError });
  handlers.current = { onFinished, onNoSpeech, onError };

  const finish = useCallback(async (session: Session, ended: boolean) => {
    if (session.timer !== null) clearInterval(session.timer);
    session.timer = null;
    if (sessionRef.current === session) sessionRef.current = null;
    setReady(false);
    try {
      await recorder.stop();
      // 녹음 모드를 끄지 않으면 iOS 에서 답 음성이 수화기 쪽으로 작게 나온다.
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    } catch (error) {
      if (!session.cancelled) handlers.current.onError(error instanceof Error ? error.message : String(error));
      return;
    }
    if (session.cancelled) return;
    const lastSpeech = session.detector.lastSpeechAtMs();
    if (!ended || lastSpeech === null || !recorder.uri) {
      handlers.current.onNoSpeech();
      return;
    }
    handlers.current.onFinished({
      uri: recorder.uri,
      speechEndedAt: session.startedAt + lastSpeech,
      isWav: recorder.uri.toLowerCase().endsWith(".wav"),
    });
  }, [recorder]);

  const start = useCallback(async (): Promise<boolean> => {
    if (sessionRef.current) return false;
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) throw new Error("마이크 권한이 없어요. 설정에서 켜 주세요.");
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    const session: Session = {
      detector: createEndpointDetector({ silenceMs: silenceRef.current }),
      startedAt: Date.now(),
      timer: null,
      cancelled: false,
    };
    sessionRef.current = session;
    session.timer = setInterval(() => {
      const status = recorder.getStatus();
      if (!status.isRecording) return;
      setReady(true);
      const decision = session.detector.push(Date.now() - session.startedAt, status.metering ?? Number.NEGATIVE_INFINITY);
      if (decision !== "listening") void finish(session, decision !== "noSpeech");
    }, POLL_MS);
    return true;
  }, [finish, recorder]);

  /** 대화를 끝낼 때: 녹음을 버리고 아무것도 부르지 않는다. */
  const cancel = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    session.cancelled = true;
    void finish(session, false);
  }, [finish]);

  useEffect(() => cancel, [cancel]);

  return { start, cancel, ready };
}
