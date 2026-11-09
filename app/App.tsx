import { setAudioModeAsync, setIsAudioActiveAsync, useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, AppState, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import {
  getHealth,
  NoRecordingError,
  postAsk,
  postStt,
  postTts,
  resetDemo,
  sttServerUrl,
  ttsServerUrl,
  type AskContext,
} from "./src/api";
import { FIRST_START_TIMEOUT_MS, waitUntilLoaded, waitUntilStarted } from "./src/playback";
import { describeServerInfo, PHONE_STT_LABEL, sttLabelFor, type HealthResponse, type ServerInfo } from "./src/serverInfo";
import {
  decideNextTurn, DEFAULT_SILENCE_MS, formatSilenceLabel, SILENCE_OPTIONS_MS, type TurnOutcome,
} from "./src/conversation";
import { STT_MODE_LABELS, type SttMode } from "./src/sttModes";
import { usePhoneStt, type PhoneTurn } from "./src/usePhoneStt";
import { useServerRecorder } from "./src/useServerRecorder";
import { TestSheetPanel } from "./src/TestSheetPanel";
import { describeAttempt, type TestCase } from "./src/testSheet";
import { useTestSheet } from "./src/useTestSheet";

type Stage = "idle" | "listening" | "transcribing" | "asking" | "speaking";

type Conversation = { emptyTurns: number; awaitingPlayback: boolean };

type Timings = { sttMs?: number; askMs?: number; ttsMs?: number; totalMs?: number };

const STAGE_LABELS: Record<Stage, string> = {
  idle: "대기 중",
  listening: "듣는 중… 다 말하면 버튼을 다시 누르세요",
  transcribing: "글로 바꾸는 중",
  asking: "답 찾는 중",
  speaking: "답 읽는 중",
};

export default function App() {
  const [sttMode, setSttMode] = useState<SttMode>("phone");
  const [stage, setStage] = useState<Stage>("idle");
  const [question, setQuestion] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [speechText, setSpeechText] = useState("");
  const [typedQuestion, setTypedQuestion] = useState("");
  const [timings, setTimings] = useState<Timings>({});
  const [errorMessage, setErrorMessage] = useState("");
  const [conversationMode, setConversationMode] = useState(false);
  const [silenceMs, setSilenceMs] = useState(DEFAULT_SILENCE_MS);
  const [conversationActive, setConversationActive] = useState(false);
  const [canReplay, setCanReplay] = useState(false);
  const [serverInfo, setServerInfo] = useState<ServerInfo>({ kind: "checking" });
  const [notice, setNotice] = useState("");
  // 맨 아래 시험표: 시험 중인 문장이 있으면 이번 턴을 자동으로 적는다.
  const testSheet = useTestSheet();
  const recordTurnRef = useRef(testSheet.recordTurn);
  recordTurnRef.current = testSheet.recordTurn;
  const markNoRecordingRef = useRef(testSheet.markNoRecording);
  markNoRecordingRef.current = testSheet.markNoRecording;
  const markPlaybackFailedRef = useRef(testSheet.markPlaybackFailed);
  markPlaybackFailedRef.current = testSheet.markPlaybackFailed;
  const markPlaybackRetriedRef = useRef(testSheet.markPlaybackRetried);
  markPlaybackRetriedRef.current = testSheet.markPlaybackRetried;
  const recordTimingsRef = useRef(testSheet.recordTimings);
  recordTimingsRef.current = testSheet.recordTimings;
  /** 재생할 때마다 1씩 늘린다. 재생 확인 중에 새 답이 오면 지난 확인은 멈춘다. */
  const playIdRef = useRef(0);
  // 시험표에 적을 STT 이름(폰 기본 STT, 또는 서버 STT 모델 이름). 서버 STT 를 고르면 STT 서버에 모델을 묻는다.
  const [sttServerHealth, setSttServerHealth] = useState<HealthResponse | null>(null);
  const sttLabelRef = useRef(PHONE_STT_LABEL);
  const sttLabel = sttLabelFor(sttMode, sttServerHealth);
  sttLabelRef.current = sttLabel;
  useEffect(() => {
    if (sttMode !== "server") return;
    let cancelled = false;
    getHealth("stt").then(
      (health) => !cancelled && setSttServerHealth(health),
      () => !cancelled && setSttServerHealth(null),
    );
    return () => {
      cancelled = true;
    };
  }, [sttMode]);
  const askContext = useRef<AskContext | undefined>(undefined);
  const conversationRef = useRef<Conversation | null>(null);
  const player = useAudioPlayer();
  const playback = useAudioPlayerStatus(player);
  const serverRecorder = useServerRecorder();

  const finishConversation = useCallback(() => {
    conversationRef.current = null;
    setConversationActive(false);
    setStage("idle");
  }, []);

  const fail = useCallback((message: string) => {
    setErrorMessage(message);
    finishConversation();
  }, [finishConversation]);

  /** 재생이 2초 안에 시작하지 않으면 한 번 다시 튼다. 그래도 안 되면 알리고 시험표 메모에 적는다.
   *  소리가 나기 시작했으면 true (그 시각을 '말 끝→소리' 시간으로 쓴다). */
  const ensurePlaying = useCallback(
    async (playId: number, fromVoice: boolean): Promise<boolean> => {
      const probe = () => ({ playing: player.playing, currentTime: player.currentTime });
      if (await waitUntilStarted(probe, FIRST_START_TIMEOUT_MS)) return true;
      if (playIdRef.current !== playId) return false;
      await setIsAudioActiveAsync(true).catch(() => undefined);
      await player.seekTo(0);
      player.play();
      if (await waitUntilStarted(probe)) {
        // 다시 틀어서야 났다: 고쳐졌는지 시험표에서 셀 수 있게 남긴다.
        if (fromVoice && playIdRef.current === playId) markPlaybackRetriedRef.current();
        return true;
      }
      if (playIdRef.current !== playId) return false;
      if (fromVoice) markPlaybackFailedRef.current();
      setNotice("음성을 받았는데 폰에서 재생이 시작되지 않았어요. '다시 듣기'를 눌러 보세요.");
      // 대화 모드는 재생이 끝나야 다음 턴을 듣는데, 재생이 안 되면 거기서 멈춘다.
      if (conversationRef.current?.awaitingPlayback) finishConversation();
      return false;
    },
    [finishConversation, player],
  );

  const answerAndSpeak = useCallback(
    /** startedAt: 말이 끝난 시각. 이때부터 답 소리가 나기 시작할 때까지를 '말 끝→소리'로 잰다. */
    async (
      text: string, startedAt: number, sttMs?: number, fromVoice = false, phoneTurn: PhoneTurn | null = null,
    ): Promise<TurnOutcome> => {
      if (!text) return "empty";
      const conversation = conversationRef.current;
      const wasStopped = () => conversation !== null && conversationRef.current !== conversation;
      setCanReplay(false);
      setQuestion(text);
      try {
        setStage("asking");
        const askStarted = Date.now();
        // '나'(역할)는 보내지 않는다: 누가 했는지는 문장 속 남편·아내로 서버가 알아듣는다.
        const answer = await postAsk(text, askContext.current);
        if (wasStopped()) return "stopped";
        askContext.current = answer.context;
        const askMs = Date.now() - askStarted;
        setAnswerText(answer.answerText);
        setSpeechText(answer.speechText);
        // 시험표에는 말로 한 턴만 적는다(글로 묻기는 인식 시험이 아니다).
        if (fromVoice) recordTurnRef.current(text, answer.answerText, sttLabelRef.current, phoneTurn, answer.correctedText ?? "");

        setStage("speaking");
        const ttsStarted = Date.now();
        let speech;
        try {
          speech = await postTts(answer.speechText);
        } catch (error) {
          if (!(error instanceof NoRecordingError)) throw error;
          // 사전 녹음 TTS 에 이 답의 소리가 없다: 오류 대신 화면 답만 보여 주고 시험표에 '녹음 없음'을 적는다.
          if (wasStopped()) return "stopped";
          if (fromVoice) {
            markNoRecordingRef.current();
            recordTimingsRef.current({ askMs });
          }
          setNotice("이 답은 녹음이 없어 화면 답만 보여 줘요.");
          setTimings({ sttMs, askMs, totalMs: Date.now() - startedAt });
          finishConversation();
          return "answered";
        }
        if (wasStopped()) return "stopped";
        const ttsMs = Date.now() - ttsStarted;
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
        // 폰 음성인식이 막 끝나 오디오 세션이 녹음용으로 남아 있을 수 있어, 재생용으로 다시 켠다.
        await setIsAudioActiveAsync(true);
        if (wasStopped()) return "stopped";
        player.replace({ uri: speech.fullAudioUrl });
        // 다 읽히기 전에 play 를 부르면 무시될 수 있다(13:51 시험에서 20/23턴).
        await waitUntilLoaded(() => player.isLoaded);
        if (wasStopped()) return "stopped";
        if (conversation) {
          const next = decideNextTurn(true, conversation.emptyTurns, "answered");
          conversation.emptyTurns = next.emptyTurns;
          conversation.awaitingPlayback = next.continueListening;
        }
        player.play();
        void ensurePlaying(++playIdRef.current, fromVoice).then((started) => {
          if (started && fromVoice) recordTimingsRef.current({ askMs, ttsMs, replyMs: Date.now() - startedAt });
        });
        setTimings({ sttMs, askMs, ttsMs, totalMs: Date.now() - startedAt });
        setCanReplay(true);
        if (!conversation) setStage("idle");
        return "answered";
      } catch (error) {
        if (wasStopped()) return "stopped";
        fail(error instanceof Error ? error.message : String(error));
        return "error";
      }
    },
    [ensurePlaying, fail, finishConversation, player],
  );

  /** 시험표의 '이 문장 말하기': 그 문장의 '나'로 바꾸고 바로 듣기 시작한다. 듣는 중에 다시 누르면 말하기 끝. */
  const chooseTestCase = (testCase: TestCase) => {
    if (stage === "listening" && testSheet.activeId === testCase.id) {
      void onMicPress();
      return;
    }
    if (stage !== "idle" || conversationRef.current) return;
    testSheet.setActiveId(testCase.id);
    void onMicPress();
  };

  /** 서버 시험 데이터와 시험표(○/×·인식한 말)를 함께 처음으로 되돌린다. 저장본은 그대로 남는다. */
  const resetEverything = async (message = "시험 데이터와 시험표를 처음으로 되돌렸어요.") => {
    setNotice("");
    try {
      await resetDemo();
      await testSheet.clearSheet(message);
      askContext.current = undefined;
      resetResult();
      setNotice(message);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  /** [저장하기]: 저장본을 남긴 뒤 바로 전부 초기화한다. 저장이 실패하면 아무것도 지우지 않는다. */
  const saveAndReset = async () => {
    const attempt = await testSheet.save();
    if (!attempt) return;
    await resetEverything(`저장했어요: ${describeAttempt(attempt)} — 처음부터 다시 시험하면 돼요.`);
  };

  const onResetDemo = () => {
    if (!testSheet.dirty) {
      void resetEverything();
      return;
    }
    Alert.alert("저장하지 않은 시험표가 있어요", "지금 시험표를 저장본으로 남기지 않고 지울까요?", [
      { text: "취소", style: "cancel" },
      // 저장이 실패하면 지우지 않는다(시험표가 날아가지 않게).
      { text: "저장하고 초기화", onPress: () => void saveAndReset() },
      { text: "저장하지 않고 초기화", style: "destructive", onPress: () => void resetEverything() },
    ]);
  };

  const resetResult = () => {
    setNotice("");
    setErrorMessage("");
    setQuestion("");
    setAnswerText("");
    setSpeechText("");
    setTimings({});
    setCanReplay(false);
  };

  const onPhoneFinished = async (transcript: string, turn: PhoneTurn) => {
    const conversation = conversationRef.current;
    // 말이 끝난 때부터 잰다(쉬는 시간을 기다린 몫도 사람이 느끼는 시간이라 넣는다).
    const outcome = await answerAndSpeak(transcript, turn.speechEndedAt ?? Date.now(), undefined, true, turn);
    if (outcome !== "empty") return;
    if (!conversation) {
      fail("인식된 말이 없어요. 다시 말해 주세요.");
      return;
    }
    if (conversationRef.current !== conversation) return;
    const next = decideNextTurn(true, conversation.emptyTurns, outcome);
    conversation.emptyTurns = next.emptyTurns;
    if (next.continueListening) {
      await listenAgain(conversation);
    } else {
      fail("말이 없어서 대화를 멈췄어요.");
    }
  };

  const { liveTranscript, start: startPhone, stop: stopPhone, cancel: cancelPhone } = usePhoneStt({
    silenceMs,
    // 시험 중인 문장이 있을 때만 들은 소리를 남긴다('이 문장 말하기'는 문장을 고른 바로 뒤에 듣기 시작한다).
    persistAudio: () => testSheet.saveAudio && testSheet.getActiveId() !== null,
    onFinished: (transcript, turn) => void onPhoneFinished(transcript, turn),
    onError: fail,
  });

  const listenAgain = useCallback(async (conversation: Conversation) => {
    setStage("listening");
    if (!(await startPhone()) && conversationRef.current === conversation) {
      finishConversation();
    }
  }, [finishConversation, startPhone]);

  useEffect(() => {
    const conversation = conversationRef.current;
    if (!playback.didJustFinish || !conversation?.awaitingPlayback) return;
    conversation.awaitingPlayback = false;
    void listenAgain(conversation);
  }, [listenAgain, playback]);

  const stopConversation = useCallback(() => {
    askContext.current = undefined;
    finishConversation();
    cancelPhone();
    player.pause();
  }, [cancelPhone, finishConversation, player]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "background" && conversationRef.current) stopConversation();
    });
    return () => subscription.remove();
  }, [stopConversation]);

  // 서버가 어떤 답 모드로 떠 있는지 보여 준다. 앱을 열 때·앱으로 돌아올 때·글자를 누를 때 다시 묻는다.
  const refreshServerInfo = useCallback(async () => {
    setServerInfo({ kind: "checking" });
    try {
      setServerInfo({ kind: "ok", health: await getHealth() });
    } catch (error) {
      setServerInfo({ kind: "error", message: error instanceof Error ? error.message : String(error) });
    }
  }, []);

  useEffect(() => {
    void refreshServerInfo();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void refreshServerInfo();
    });
    return () => subscription.remove();
  }, [refreshServerInfo]);

  const onMicPress = async () => {
    try {
      if (stage === "idle" && !conversationRef.current) {
        resetResult();
        setStage("listening");
        if (sttMode === "phone") {
          player.pause();
          if (conversationMode) {
            const conversation: Conversation = { emptyTurns: 0, awaitingPlayback: false };
            conversationRef.current = conversation;
            setConversationActive(true);
            await listenAgain(conversation);
          } else if (!(await startPhone())) {
            setStage("idle");
          }
        } else {
          await serverRecorder.start();
        }
        return;
      }
      if (stage !== "listening") {
        return;
      }
      if (sttMode === "phone") {
        stopPhone();
        return;
      }
      const stoppedAt = Date.now();
      const uri = await serverRecorder.stop();
      setStage("transcribing");
      const sttStarted = Date.now();
      const recognized = await postStt(uri);
      if (await answerAndSpeak(recognized.text, stoppedAt, Date.now() - sttStarted, true) === "empty") {
        fail("인식된 말이 없어요. 다시 말해 주세요.");
      }
    } catch (error) {
      fail(error instanceof Error ? error.message : String(error));
    }
  };

  const onTypedAsk = () => {
    resetResult();
    void answerAndSpeak(typedQuestion.trim(), Date.now(), undefined);
  };

  const isBusy = stage !== "idle" && stage !== "listening";
  const liveText = sttMode === "phone" && stage === "listening" ? liveTranscript : "";

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>STT-TTS 시험</Text>
        <Text style={styles.meta}>STT 서버: {sttServerUrl ?? "설정 안 됨"}</Text>
        <Text style={styles.meta}>답·TTS 서버: {ttsServerUrl ?? "설정 안 됨"}</Text>
        <Pressable accessibilityRole="button" accessibilityHint="눌러서 서버 상태를 다시 확인" onPress={() => void refreshServerInfo()}>
          <Text style={[styles.serverInfo, serverInfo.kind === "error" && styles.error]}>
            {describeServerInfo(serverInfo)} ↻
          </Text>
        </Pressable>

        <View style={styles.modeRow}>
          <Pressable
            accessibilityRole="button"
            disabled={stage !== "idle"}
            onPress={onResetDemo}
            style={[styles.modeButton, stage !== "idle" && styles.disabled]}
          >
            <Text style={styles.modeText}>시험 데이터 초기화</Text>
          </Pressable>
        </View>
        {notice ? <Text style={styles.meta}>{notice}</Text> : null}

        <View style={styles.modeRow}>
          {(Object.keys(STT_MODE_LABELS) as SttMode[]).map((mode) => (
            <Pressable
              key={mode}
              disabled={stage !== "idle"}
              onPress={() => setSttMode(mode)}
              style={[styles.modeButton, sttMode === mode && styles.modeButtonActive]}
            >
              <Text style={[styles.modeText, sttMode === mode && styles.modeTextActive]}>{STT_MODE_LABELS[mode]}</Text>
            </Pressable>
          ))}
        </View>

        {sttMode === "phone" ? (
          <View>
            <Pressable
              accessibilityRole="switch"
              accessibilityState={{ checked: conversationMode, disabled: stage !== "idle" }}
              disabled={stage !== "idle"}
              onPress={() => setConversationMode((enabled) => !enabled)}
              style={[styles.modeButton, conversationMode && styles.modeButtonActive]}
            >
              <Text style={[styles.modeText, conversationMode && styles.modeTextActive]}>
                대화 모드 {conversationMode ? "켜짐" : "꺼짐"}
              </Text>
            </Pressable>
            <Text style={styles.meta}>말이 끝났다고 보는 쉬는 시간</Text>
            <View style={styles.modeRow}>
              {SILENCE_OPTIONS_MS.map((ms) => (
                <Pressable
                  key={ms}
                  accessibilityRole="button"
                  accessibilityState={{ selected: ms === silenceMs, disabled: stage !== "idle" }}
                  disabled={stage !== "idle"}
                  onPress={() => setSilenceMs(ms)}
                  style={[styles.modeButton, ms === silenceMs && styles.modeButtonActive]}
                >
                  <Text style={[styles.modeText, ms === silenceMs && styles.modeTextActive]}>
                    {formatSilenceLabel(ms)}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}

        {testSheet.activeCase ? (
          <View style={styles.testBanner}>
            <Text style={styles.testBannerText}>
              시험 중 {testSheet.activeCase.id} — “{testSheet.activeCase.say}”
            </Text>
            <Pressable accessibilityRole="button" onPress={() => testSheet.setActiveId(null)} style={styles.testBannerStop}>
              <Text style={styles.testBannerStopText}>그만</Text>
            </Pressable>
          </View>
        ) : null}

        <Pressable
          disabled={isBusy && !conversationActive}
          onPress={conversationActive ? stopConversation : onMicPress}
          style={[styles.micButton, (conversationActive || stage === "listening") && styles.micButtonActive, isBusy && !conversationActive && styles.disabled]}
        >
          <Text style={styles.micText}>{conversationActive ? "■ 대화 끝내기" : stage === "listening" ? "■ 말하기 끝" : "🎤 말하기"}</Text>
        </Pressable>
        <Text style={styles.stage}>
          {stage === "listening" && sttMode === "phone"
            ? "듣는 중… 말을 멈추면 자동으로 질문해요"
            : STAGE_LABELS[stage]}
        </Text>
        {liveText ? <Text style={styles.live}>{liveText}</Text> : null}

        <View style={styles.typedRow}>
          <TextInput
            value={typedQuestion}
            onChangeText={setTypedQuestion}
            placeholder="글로 바로 묻기 (STT 없이 시험)"
            style={styles.input}
          />
          <Pressable disabled={stage !== "idle" || !typedQuestion.trim()} onPress={onTypedAsk} style={styles.askButton}>
            <Text style={styles.askText}>묻기</Text>
          </Pressable>
        </View>

        {errorMessage ? <Text style={styles.error}>{errorMessage}</Text> : null}
        <ResultBlock label="인식한 말" value={question} />
        <ResultBlock label="답 (화면용)" value={answerText} />
        <ResultBlock label="답 (읽기용)" value={speechText} />
        <ResultBlock
          label="걸린 시간"
          value={
            timings.totalMs === undefined
              ? ""
              : [
                  timings.sttMs !== undefined ? `STT ${timings.sttMs}ms` : null,
                  `답 ${timings.askMs}ms`,
                  `TTS ${timings.ttsMs}ms`,
                  `합계 ${timings.totalMs}ms`,
                ]
                  .filter(Boolean)
                  .join(" · ")
          }
        />
        {canReplay && stage === "idle" ? (
          <Pressable
            onPress={() => {
              player.seekTo(0);
              player.play();
            }}
            style={styles.replayButton}
          >
            <Text style={styles.askText}>▶ 다시 듣기</Text>
          </Pressable>
        ) : null}

        <TestSheetPanel
          sheet={testSheet}
          stage={stage === "listening" ? "listening" : stage === "idle" && !conversationActive ? "idle" : "busy"}
          liveText={liveText}
          sttLabel={sttLabel}
          ttsIsMock={serverInfo.kind === "ok" && serverInfo.health.ttsEngine === "mock"}
          onChoose={chooseTestCase}
          onSave={() => void saveAndReset()}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function ResultBlock({ label, value }: { label: string; value: string }) {
  if (!value) {
    return null;
  }
  return (
    <View style={styles.block}>
      <Text style={styles.blockLabel}>{label}</Text>
      <Text style={styles.blockValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F7F8FA" },
  content: { padding: 20, gap: 12 },
  title: { fontSize: 24, fontWeight: "700", color: "#111" },
  meta: { fontSize: 12, color: "#666" },
  serverInfo: { fontSize: 13, fontWeight: "600", color: "#1F4FD8" },
  testBanner: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 10, backgroundColor: "#E6EDFB" },
  testBannerText: { flex: 1, fontSize: 14, color: "#1F4FD8", fontWeight: "600" },
  testBannerStop: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: "#1F4FD8" },
  testBannerStopText: { fontSize: 13, color: "#1F4FD8" },
  modeRow: { flexDirection: "row", gap: 8, marginTop: 8 },
  modeButton: { flex: 1, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: "#CCD", alignItems: "center" },
  modeButtonActive: { backgroundColor: "#1F4FD8", borderColor: "#1F4FD8" },
  modeText: { fontSize: 14, color: "#333" },
  modeTextActive: { color: "#FFF", fontWeight: "700" },
  micButton: { marginTop: 8, paddingVertical: 28, borderRadius: 16, backgroundColor: "#1F4FD8", alignItems: "center" },
  micButtonActive: { backgroundColor: "#D83A1F" },
  micText: { fontSize: 22, fontWeight: "700", color: "#FFF" },
  disabled: { opacity: 0.5 },
  stage: { textAlign: "center", color: "#444" },
  live: { textAlign: "center", fontSize: 18, color: "#111" },
  typedRow: { flexDirection: "row", gap: 8 },
  input: { flex: 1, borderWidth: 1, borderColor: "#CCD", borderRadius: 10, paddingHorizontal: 12, backgroundColor: "#FFF" },
  askButton: { paddingHorizontal: 16, justifyContent: "center", borderRadius: 10, backgroundColor: "#333" },
  askText: { color: "#FFF", fontWeight: "700" },
  error: { color: "#C0281A" },
  block: { backgroundColor: "#FFF", borderRadius: 10, padding: 12, gap: 4 },
  blockLabel: { fontSize: 12, color: "#777" },
  blockValue: { fontSize: 16, color: "#111" },
  replayButton: { alignSelf: "flex-start", paddingVertical: 10, paddingHorizontal: 16, borderRadius: 10, backgroundColor: "#333" },
});
