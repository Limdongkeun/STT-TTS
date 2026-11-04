import { setAudioModeAsync, useAudioPlayer } from "expo-audio";
import { StatusBar } from "expo-status-bar";
import { useCallback, useState } from "react";
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { postAsk, postStt, postTts, sttServerUrl, ttsServerUrl } from "./src/api";
import { STT_MODE_LABELS, type SttMode } from "./src/sttModes";
import { usePhoneStt } from "./src/usePhoneStt";
import { useServerRecorder } from "./src/useServerRecorder";

type Stage = "idle" | "listening" | "transcribing" | "asking" | "speaking";

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
  const player = useAudioPlayer();
  const serverRecorder = useServerRecorder();

  const fail = useCallback((message: string) => {
    setErrorMessage(message);
    setStage("idle");
  }, []);

  const answerAndSpeak = useCallback(
    async (text: string, startedAt: number, sttMs?: number) => {
      if (!text) {
        fail("인식된 말이 없어요. 다시 말해 주세요.");
        return;
      }
      setQuestion(text);
      try {
        setStage("asking");
        const askStarted = Date.now();
        const answer = await postAsk(text);
        const askMs = Date.now() - askStarted;
        setAnswerText(answer.answerText);
        setSpeechText(answer.speechText);

        setStage("speaking");
        const ttsStarted = Date.now();
        const speech = await postTts(answer.speechText);
        const ttsMs = Date.now() - ttsStarted;
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
        player.replace({ uri: speech.fullAudioUrl });
        player.play();
        setTimings({ sttMs, askMs, ttsMs, totalMs: Date.now() - startedAt });
        setStage("idle");
      } catch (error) {
        fail(error instanceof Error ? error.message : String(error));
      }
    },
    [fail, player],
  );

  const phoneStt = usePhoneStt({
    // 폰 STT 는 말하는 중에 바로 글자가 나오므로, 합계 시간은 인식이 끝난 순간부터 잰다.
    onFinished: (transcript) => void answerAndSpeak(transcript, Date.now(), undefined),
    onError: fail,
  });

  const resetResult = () => {
    setErrorMessage("");
    setQuestion("");
    setAnswerText("");
    setSpeechText("");
    setTimings({});
  };

  const onMicPress = async () => {
    try {
      if (stage === "idle") {
        resetResult();
        setStage("listening");
        if (sttMode === "phone") {
          await phoneStt.start();
        } else {
          await serverRecorder.start();
        }
        return;
      }
      if (stage !== "listening") {
        return;
      }
      if (sttMode === "phone") {
        phoneStt.stop();
        return;
      }
      const stoppedAt = Date.now();
      const uri = await serverRecorder.stop();
      setStage("transcribing");
      const sttStarted = Date.now();
      const recognized = await postStt(uri);
      await answerAndSpeak(recognized.text, stoppedAt, Date.now() - sttStarted);
    } catch (error) {
      fail(error instanceof Error ? error.message : String(error));
    }
  };

  const onTypedAsk = () => {
    resetResult();
    void answerAndSpeak(typedQuestion.trim(), Date.now(), undefined);
  };

  const isBusy = stage !== "idle" && stage !== "listening";
  const liveText = sttMode === "phone" && stage === "listening" ? phoneStt.liveTranscript : "";

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

        <Pressable
          disabled={isBusy}
          onPress={onMicPress}
          style={[styles.micButton, stage === "listening" && styles.micButtonActive, isBusy && styles.disabled]}
        >
          <Text style={styles.micText}>{stage === "listening" ? "■ 말하기 끝" : "🎤 말하기"}</Text>
        </Pressable>
        <Text style={styles.stage}>{STAGE_LABELS[stage]}</Text>
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
        {speechText && stage === "idle" ? (
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
