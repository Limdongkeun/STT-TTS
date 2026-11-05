import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { postAsk, postStt, postTts, sttServerUrl, ttsServerUrl, type AskContext } from "./src/api";
import {
  decideNextTurn, DEFAULT_SILENCE_MS, formatSilenceLabel, SILENCE_OPTIONS_MS, type TurnOutcome,
} from "./src/conversation";
import { STT_MODE_LABELS, type SttMode } from "./src/sttModes";
import { usePhoneStt } from "./src/usePhoneStt";
import { useServerRecorder } from "./src/useServerRecorder";

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

  const answerAndSpeak = useCallback(
    async (text: string, startedAt: number, sttMs?: number): Promise<TurnOutcome> => {
      if (!text) return "empty";
      const conversation = conversationRef.current;
      const wasStopped = () => conversation !== null && conversationRef.current !== conversation;
      setCanReplay(false);
      setQuestion(text);
      try {
        setStage("asking");
        const askStarted = Date.now();
        const answer = await postAsk(text, askContext.current);
        if (wasStopped()) return "stopped";
        askContext.current = answer.context;
        const askMs = Date.now() - askStarted;
        setAnswerText(answer.answerText);
        setSpeechText(answer.speechText);

        setStage("speaking");
        const ttsStarted = Date.now();
        const speech = await postTts(answer.speechText);
        if (wasStopped()) return "stopped";
        const ttsMs = Date.now() - ttsStarted;
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
        if (wasStopped()) return "stopped";
        player.replace({ uri: speech.fullAudioUrl });
        if (conversation) {
          const next = decideNextTurn(true, conversation.emptyTurns, "answered");
          conversation.emptyTurns = next.emptyTurns;
          conversation.awaitingPlayback = next.continueListening;
        }
        player.play();
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
    [fail, player],
  );

  const resetResult = () => {
    setErrorMessage("");
    setQuestion("");
    setAnswerText("");
    setSpeechText("");
    setTimings({});
    setCanReplay(false);
  };

  const onPhoneFinished = async (transcript: string) => {
    const conversation = conversationRef.current;
    const outcome = await answerAndSpeak(transcript, Date.now());
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
    onFinished: (transcript) => void onPhoneFinished(transcript),
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
      if (await answerAndSpeak(recognized.text, stoppedAt, Date.now() - sttStarted) === "empty") {
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
