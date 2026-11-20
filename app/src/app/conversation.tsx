/** 대화 모드 화면(2026-11-17 Expo Router: 예전에는 메인 위에 Modal 로 띄웠다).
 *  메인에서 대화를 시작하면 이 화면으로 온다. 대화가 끝나면(끝내기·앱이 뒤로 감) 메인으로 돌아가고,
 *  다른 길로 이 화면을 벗어나도 대화를 끝낸다(듣기·소리가 화면 없이 남지 않게). */

import { router } from "expo-router";
import { useEffect, useRef } from "react";
import { StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ConversationScreen } from "../ConversationScreen";
import { colors } from "../theme";
import { useVoice } from "../voice/VoiceProvider";

export default function ConversationRoute() {
  const {
    conversationActive, stopConversation, resumeConversation, interruptByTap, face, liveText, chat, testSheet,
    activeTts, errorMessage, conversationSttLabel, conversationSttOptions, chooseConversationStt,
  } = useVoice();
  const stopRef = useRef(stopConversation);
  stopRef.current = stopConversation;
  const activeRef = useRef(conversationActive);
  activeRef.current = conversationActive;

  // 대화가 끝났으면 메인으로 돌아간다.
  useEffect(() => {
    if (!conversationActive && router.canGoBack()) router.back();
  }, [conversationActive]);

  // 이 화면이 닫히는데 대화가 남아 있으면 끝낸다.
  useEffect(() => () => {
    if (activeRef.current) stopRef.current();
  }, []);

  return (
    <SafeAreaView style={styles.screen}>
      <ConversationScreen
        face={face}
        liveText={liveText}
        chat={chat}
        cases={testSheet.cases}
        results={testSheet.results}
        sttLabel={conversationSttLabel}
        sttOptions={conversationSttOptions}
        onChooseStt={(mode) => void chooseConversationStt(mode)}
        ttsLabel={activeTts.label}
        errorMessage={errorMessage}
        onEnd={stopConversation}
        onResume={resumeConversation}
        onInterrupt={interruptByTap}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
});
