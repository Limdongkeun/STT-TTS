/** 서버 STT 용 녹음. 녹음 파일 주소(uri)를 돌려준다. */

import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";
import { useCallback, useState } from "react";

export function useServerRecorder() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [isRecording, setIsRecording] = useState(false);

  const start = useCallback(async () => {
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      throw new Error("마이크 권한이 없어요. 설정에서 켜 주세요.");
    }
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    setIsRecording(true);
  }, [recorder]);

  const stop = useCallback(async (): Promise<string> => {
    await recorder.stop();
    setIsRecording(false);
    // 녹음 모드를 끄지 않으면 iOS 에서 답 음성이 수화기 쪽으로 작게 나온다.
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    if (!recorder.uri) {
      throw new Error("녹음 파일을 찾지 못했어요.");
    }
    return recorder.uri;
  }, [recorder]);

  return { isRecording, start, stop };
}
