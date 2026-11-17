/** 앱 틀(2026-11-17 Expo Router). 음성 상태(VoiceProvider)를 두 화면이 같이 쓴다.
 *  index: 메인 / conversation: 대화 모드(전체 화면, 쓸어서 닫지 않게 — '대화 끝내기'로만 닫는다). */

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { VoiceProvider } from "../voice/VoiceProvider";

export default function RootLayout() {
  return (
    <VoiceProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="conversation" options={{ presentation: "fullScreenModal", gestureEnabled: false }} />
      </Stack>
    </VoiceProvider>
  );
}
