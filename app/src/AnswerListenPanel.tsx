/** '답 듣기' 칸. 질문을 말하지 않고, 위에서 고른 목소리로 시험 답 34개를 바로 들어 본다(2026-11-12 사용자 요청).
 *  답 목록은 서버(/answer-samples)가 주고, 소리는 숫자 읽기 시험과 같은 길(App 의 onPlay → /tts 하나씩)로 만든다. */

import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { answerReadingsFrom, answerTextFor, canListenAnswers, type AnswerSample } from "./answerSamples";
import { getAnswerSamples } from "./api";

type Props = {
  ttsEngine: string | undefined;
  ttsLabel: string;
  /** 앱이 답을 듣거나 찾는 중이면 누르지 못하게 한다. */
  busy: boolean;
  /** App 이 이 칸에서 넘긴 목록 중 지금 읽는 번호. 이 칸이 읽는 게 아니면 null. */
  playingIndex: number | null;
  onPlay: (readings: string[]) => void;
  onStop: () => void;
};

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function AnswerListenPanel({ ttsEngine, ttsLabel, busy, playingIndex, onPlay, onStop }: Props) {
  const [open, setOpen] = useState(false);
  const [samples, setSamples] = useState<AnswerSample[]>([]);
  const [status, setStatus] = useState("");
  // 마지막으로 [듣기]/[전부 듣기]로 넘긴 줄 번호들. playingIndex 를 줄로 바꿀 때 쓴다.
  const [playedIds, setPlayedIds] = useState<string[]>([]);
  const playable = canListenAnswers(ttsEngine);
  const playingId = playingIndex === null ? null : (playedIds[playingIndex] ?? null);

  const load = useCallback(async () => {
    setStatus("답을 불러오는 중…");
    try {
      setSamples(await getAnswerSamples());
      setStatus("");
    } catch (error) {
      setStatus(`답을 불러오지 못했어요: ${errorText(error)}`);
    }
  }, []);

  useEffect(() => {
    if (open && samples.length === 0) void load();
  }, [load, open, samples.length]);

  const play = (startIndex: number, onlyOne: boolean) => {
    const picked = onlyOne ? samples.slice(startIndex, startIndex + 1) : samples.slice(startIndex);
    setPlayedIds(picked.map((sample) => sample.id));
    onPlay(answerReadingsFrom(samples, startIndex, onlyOne));
  };

  const disabled = !playable || busy || samples.length === 0;

  return (
    <View style={styles.panel}>
      <Pressable accessibilityRole="button" onPress={() => setOpen(!open)} style={styles.header}>
        <Text style={styles.title}>{open ? "▼" : "▶"} 답 듣기</Text>
        <Text style={styles.meta}>질문 없이 시험 답만 듣기 · {ttsLabel || "TTS 모름"}</Text>
      </Pressable>
      {!open ? null : (
        <>
          {!playable ? (
            <Text style={styles.status}>서버 TTS 를 모르겠어요. 위에서 서버 상태를 다시 확인하세요.</Text>
          ) : null}
          <View style={styles.row}>
            {playingIndex === null ? (
              <Pressable
                accessibilityRole="button"
                disabled={disabled}
                onPress={() => play(0, false)}
                style={[styles.button, disabled && styles.dim]}
              >
                <Text style={styles.buttonText}>▶ 전부 듣기</Text>
              </Pressable>
            ) : (
              <Pressable accessibilityRole="button" onPress={onStop} style={styles.button}>
                <Text style={styles.buttonText}>■ 멈추기</Text>
              </Pressable>
            )}
          </View>
          {status ? <Text style={styles.status}>{status}</Text> : null}
          {samples.map((sample, index) => {
            const playing = playingId === sample.id;
            return (
              <View key={sample.id} style={[styles.card, playing && styles.cardPlaying]}>
                <View style={styles.row}>
                  <Text style={styles.caseId}>{sample.id}</Text>
                  {playing ? <Text style={styles.playing}>읽는 중</Text> : null}
                  <Pressable
                    accessibilityRole="button"
                    disabled={disabled || playingIndex !== null}
                    onPress={() => play(index, true)}
                    style={[styles.smallButton, (disabled || playingIndex !== null) && styles.dim]}
                  >
                    <Text style={styles.smallText}>▶ 듣기</Text>
                  </Pressable>
                </View>
                <Text style={styles.text}>{answerTextFor(sample)}</Text>
                {sample.answer !== sample.spoken ? <Text style={styles.meta}>화면 답: {sample.answer}</Text> : null}
              </View>
            );
          })}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { marginTop: 24, paddingTop: 16, borderTopWidth: 2, borderTopColor: "#111", gap: 10 },
  header: { gap: 2 },
  title: { fontSize: 20, fontWeight: "700", color: "#111" },
  meta: { fontSize: 12, color: "#666" },
  status: { fontSize: 13, color: "#C0281A" },
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 },
  button: { paddingVertical: 10, paddingHorizontal: 16, borderRadius: 10, backgroundColor: "#1F4FD8" },
  buttonText: { fontSize: 15, fontWeight: "700", color: "#FFF" },
  dim: { opacity: 0.5 },
  card: { backgroundColor: "#FFF", borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: "#E1E4EA" },
  cardPlaying: { borderColor: "#1F4FD8", borderWidth: 2 },
  caseId: { fontSize: 13, fontWeight: "700", color: "#333", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: "#F0F2F5" },
  playing: { fontSize: 12, fontWeight: "700", color: "#1F4FD8" },
  text: { fontSize: 16, color: "#111" },
  smallButton: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: "#CCD" },
  smallText: { fontSize: 14, color: "#333" },
});
