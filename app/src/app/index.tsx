/** 메인 화면: 서버 상태, 받아쓰기(STT)·목소리(TTS) 고르기, 버튼 말하기·글로 묻기, 결과, 대화 모드, 시험표, 답 듣기·숫자 읽기 시험.
 *  상태와 동작은 VoiceProvider(useVoice). 대화 모드는 /conversation 화면으로 연다(2026-11-17 Expo Router).
 *  2026-11-17 보기 편하게: 구역마다 제목, 가장 많이 쓰는 '말하기'를 가운데, 지우는 '시험 데이터 초기화'는 맨 아래 '관리'로. */

import { router, useIsFocused } from "expo-router";
import { memo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { sttServerUrl, ttsServerUrl } from "../api";
import { AnswerListenPanel } from "../AnswerListenPanel";
import { ChoiceRow } from "../components/ChoiceRow";
import { Section } from "../components/Section";
import { ServerStatus } from "../components/ServerStatus";
import { formatSilenceLabel, SILENCE_OPTIONS_MS } from "../conversation";
import { NumberReadingPanel } from "../NumberReadingPanel";
import { ttsButtonLabel } from "../serverInfo";
import { TestSheetPanel } from "../TestSheetPanel";
import { colors, radius, spacing, type } from "../theme";
import { STAGE_LABELS, useVoice } from "../voice/VoiceProvider";

export default function MainScreen() {
  const voice = useVoice();
  const focused = useIsFocused();
  return <MainContent voice={voice} focused={focused} />;
}

/** 대화 화면이 위에 떠 있는 동안(이 화면 포커스 없음)은 다시 그리지 않는다. 받아 적는 글이 바뀔 때마다
 *  가려진 메인 화면(시험표 카드 등)까지 다시 그려 폰이 뜨거웠다(2026-11-17). 돌아오면 그때 한 번 그린다. */
const MainContent = memo(MainView, (prev, next) => !prev.focused && !next.focused);

function MainView({ voice }: { voice: ReturnType<typeof useVoice>; focused: boolean }) {
  const {
    serverInfo, refreshServerInfo, notice, onResetDemo, saveAndReset,
    sttMode, setSttMode, setServerStt, sttButtons, sttLabel,
    ttsChoices, activeTts, setTtsChoice, silenceMs, setSilenceMs,
    stage, isBusy, liveText, onMicPress, typedQuestion, setTypedQuestion, onTypedAsk,
    errorMessage, question, answerText, speechText, timings, canReplay, replaySpeech,
    testSheet, chooseTestCase, readingOwner, readingIndex, playReadings, stopSpeech,
    conversationActive, startConversation, stopConversation,
  } = voice;
  const idle = stage === "idle";
  const listening = stage === "listening";
  const timingText = timings.totalMs === undefined
    ? ""
    : [
        timings.sttMs !== undefined ? `STT ${timings.sttMs}ms` : null,
        `답 ${timings.askMs}ms`,
        `TTS ${timings.ttsMs}ms`,
        `합계 ${timings.totalMs}ms`,
      ].filter(Boolean).join(" · ");
  const hasResult = Boolean(question || answerText || speechText || timingText);

  return (
    <SafeAreaView style={styles.screen} edges={["top", "left", "right"]}>
      {/* 시험표(1번째 자식)가 보이는 동안은 그 위치를 지킨다: '이 문장 말하기'를 누르면 위쪽 칸이 커졌다 작아졌다 해서
          보던 카드가 밀렸다(2026-11-12 사용자 제보). 그래서 위쪽은 View 하나(0번째)로 묶어 자식 번호가 바뀌지 않게 한다. */}
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        // 시험 중일 때만 시험표 위치를 지킨다. 늘 켜 두면 앱을 열 때 위쪽(서버 상태를 받아 TTS 칸이 생김)이 커지면서
        // 화면이 시험표 쪽으로 내려가 있었다(2026-11-17 시뮬레이터).
        maintainVisibleContentPosition={testSheet.activeCase ? { minIndexForVisible: 1 } : undefined}
      >
        <View style={styles.top}>
          <View style={styles.header}>
            <Text testID="main-title" accessibilityRole="header" style={type.title}>STT-TTS 시험</Text>
            <ServerStatus info={serverInfo} sttUrl={sttServerUrl} ttsUrl={ttsServerUrl} onRefresh={() => void refreshServerInfo()} />
            {notice ? <Text style={type.subhead}>{notice}</Text> : null}
          </View>

          <Section title="받아쓰기 (STT)">
            <ChoiceRow
              disabled={!idle}
              choices={sttButtons.map((button) => ({
                key: button.key,
                label: button.label,
                selected: button.active,
                onPress: () => {
                  setSttMode(button.mode);
                  if (button.engine) setServerStt(button.engine);
                },
              }))}
            />
          </Section>

          {ttsChoices.length > 1 ? (
            <Section title="목소리 (TTS)">
              <ChoiceRow
                disabled={!idle}
                choices={ttsChoices.map((choice) => ({
                  key: choice.engine,
                  label: ttsButtonLabel(choice.engine),
                  selected: activeTts.engine === choice.engine,
                  onPress: () => setTtsChoice(choice.engine),
                }))}
              />
            </Section>
          ) : null}

          {testSheet.activeCase ? (
            <View style={styles.testBanner}>
              <Text style={styles.testBannerText}>시험 중 {testSheet.activeCase.id} — “{testSheet.activeCase.say}”</Text>
              <Pressable accessibilityRole="button" onPress={() => testSheet.setActiveId(null)} style={styles.testBannerStop}>
                <Text style={styles.testBannerStopText}>그만</Text>
              </Pressable>
            </View>
          ) : null}

          <View style={styles.speak}>
            <Pressable
              testID="mic-button"
              accessibilityRole="button"
              disabled={isBusy && !conversationActive}
              onPress={conversationActive ? stopConversation : () => void onMicPress()}
              style={({ pressed }) => [
                styles.micButton,
                (conversationActive || listening) && styles.micButtonActive,
                ((isBusy && !conversationActive) || pressed) && styles.dim,
              ]}
            >
              <Text style={styles.micText}>{conversationActive ? "■ 대화 끝내기" : listening ? "■ 말하기 끝" : "🎤 말하기"}</Text>
            </Pressable>
            <Text style={styles.stage}>
              {listening && sttMode === "phone" ? "듣는 중… 말을 멈추면 자동으로 질문해요" : STAGE_LABELS[stage]}
            </Text>
            {liveText ? <Text style={styles.live}>{liveText}</Text> : null}
            <View style={styles.typedRow}>
              <TextInput
                testID="typed-question"
                value={typedQuestion}
                onChangeText={setTypedQuestion}
                placeholder="글로 바로 묻기 (STT 없이 시험)"
                placeholderTextColor={colors.tertiaryLabel}
                returnKeyType="send"
                onSubmitEditing={() => idle && typedQuestion.trim() && onTypedAsk()}
                style={styles.input}
              />
              <Pressable
                testID="typed-ask"
                accessibilityRole="button"
                disabled={!idle || !typedQuestion.trim()}
                onPress={onTypedAsk}
                style={({ pressed }) => [styles.askButton, (!idle || !typedQuestion.trim() || pressed) && styles.dim]}
              >
                <Text style={styles.askText}>묻기</Text>
              </Pressable>
            </View>
            {errorMessage ? <Text style={styles.error}>{errorMessage}</Text> : null}
          </View>

          {hasResult ? (
            <Section title="결과">
              <ResultLine label="인식한 말" value={question} />
              <ResultLine label="답 (화면용)" value={answerText} />
              <ResultLine label="답 (읽기용)" value={speechText} />
              <ResultLine label="걸린 시간" value={timingText} small />
              {canReplay && idle ? (
                <Pressable accessibilityRole="button" onPress={() => void replaySpeech()} style={({ pressed }) => [styles.replayButton, pressed && styles.dim]}>
                  <Text style={styles.askText}>▶ 다시 듣기</Text>
                </Pressable>
              ) : null}
            </Section>
          ) : null}

          <Section title="대화 모드" caption="버튼 없이 계속 대화해요. 늘 폰 STT로 빠르게 듣고, 시험표 문장을 순서 없이 말하면 맞는 칸에 적혀요.">
            <Pressable
              testID="start-conversation"
              accessibilityRole="button"
              disabled={!idle}
              onPress={() => {
                if (startConversation()) router.push("/conversation");
              }}
              style={({ pressed }) => [styles.conversationButton, (!idle || pressed) && styles.dim]}
            >
              <Text style={styles.conversationButtonText}>💬 대화 모드</Text>
            </Pressable>
            <Text style={type.subhead}>말이 끝났다고 보는 쉬는 시간</Text>
            <ChoiceRow
              disabled={!idle}
              choices={SILENCE_OPTIONS_MS.map((ms) => ({
                key: String(ms),
                label: formatSilenceLabel(ms),
                selected: ms === silenceMs,
                onPress: () => setSilenceMs(ms),
              }))}
            />
          </Section>
        </View>

        <TestSheetPanel
          sheet={testSheet}
          stage={listening ? "listening" : idle && !conversationActive ? "idle" : "busy"}
          liveText={liveText}
          sttLabel={sttLabel}
          ttsIsMock={activeTts.engine === "mock"}
          onChoose={chooseTestCase}
          onSave={() => void saveAndReset()}
        />
        <AnswerListenPanel
          ttsEngine={activeTts.engine}
          ttsLabel={activeTts.label}
          busy={!idle || conversationActive}
          playingIndex={readingOwner === "answers" ? readingIndex : null}
          onPlay={(readings) => void playReadings(readings, "answers")}
          onStop={stopSpeech}
        />
        <NumberReadingPanel
          device={testSheet.device}
          ttsEngine={activeTts.engine}
          ttsLabel={activeTts.label}
          busy={!idle || conversationActive}
          playingIndex={readingOwner === "numbers" ? readingIndex : null}
          onPlay={(readings) => void playReadings(readings, "numbers")}
          onStop={stopSpeech}
        />

        <Section title="관리" caption="서버의 시험 데이터(부탁·장보기 등)와 시험표를 처음으로 되돌려요.">
          <Pressable
            accessibilityRole="button"
            disabled={!idle}
            onPress={onResetDemo}
            style={({ pressed }) => [styles.resetButton, (!idle || pressed) && styles.dim]}
          >
            <Text style={styles.resetText}>시험 데이터 초기화</Text>
          </Pressable>
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

function ResultLine({ label, value, small = false }: { label: string; value: string; small?: boolean }) {
  if (!value) return null;
  return (
    <View style={styles.resultLine}>
      <Text style={type.caption}>{label}</Text>
      <Text style={small ? type.subhead : type.body}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xl },
  top: { gap: spacing.md },
  header: { gap: spacing.sm },
  testBanner: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md - 4,
    borderRadius: radius.md, backgroundColor: colors.accentSoft,
  },
  testBannerText: { flex: 1, fontSize: 14, color: colors.accent, fontWeight: "600" },
  testBannerStop: {
    paddingVertical: spacing.xs, paddingHorizontal: spacing.md - 4, borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.accent,
  },
  testBannerStopText: { fontSize: 13, color: colors.accent },
  speak: { gap: spacing.sm },
  micButton: {
    paddingVertical: spacing.lg + 4, borderRadius: radius.lg, borderCurve: "continuous",
    backgroundColor: colors.accent, alignItems: "center",
  },
  micButtonActive: { backgroundColor: colors.recording },
  micText: { fontSize: 22, fontWeight: "700", color: colors.onTint },
  dim: { opacity: 0.55 },
  stage: { textAlign: "center", fontSize: 14, color: colors.secondaryLabel },
  live: { textAlign: "center", fontSize: 18, color: colors.label },
  typedRow: { flexDirection: "row", gap: spacing.sm },
  input: {
    flex: 1, minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md - 4, backgroundColor: colors.surface, fontSize: 16, color: colors.label,
  },
  askButton: { paddingHorizontal: spacing.md, justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.dark },
  askText: { color: colors.onTint, fontWeight: "700" },
  error: { color: colors.danger, fontSize: 14 },
  resultLine: { gap: 2 },
  replayButton: {
    alignSelf: "flex-start", paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.md,
    borderRadius: radius.md, backgroundColor: colors.dark,
  },
  conversationButton: {
    paddingVertical: spacing.md, borderRadius: radius.md, borderCurve: "continuous",
    backgroundColor: colors.conversation, alignItems: "center",
  },
  conversationButtonText: { fontSize: 18, fontWeight: "700", color: colors.onTint },
  resetButton: {
    alignSelf: "flex-start", paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.md,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.danger,
  },
  resetText: { color: colors.danger, fontWeight: "600" },
});
