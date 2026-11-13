/** 앱 맨 아래 '숫자 읽기 시험' 칸. 말하지 않고 [듣기]만 눌러 TTS 가 숫자를 제대로 읽는지 듣고 ○/× 를 남긴다.
 *  문장·읽기 글은 서버(/reading-samples)가 주고, 결과는 서버가 results/number-reading/ 에 파일로 남긴다. */

import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { getReadingSamples, saveReadingResults } from "./api";
import {
  canTestReading,
  countReadingMarks,
  MAX_READING_MEMO_CHARS,
  readingsFrom,
  setReadingMemo,
  toggleReadingMark,
  type ReadingHeard,
  type ReadingMarks,
  type ReadingSample,
} from "./numberReading";

type Props = {
  /** 결과 파일 폴더 이름(시험표와 같은 기기 이름). */
  device: string;
  ttsEngine: string | undefined;
  /** 결과 파일 머리에 적는 TTS 이름. */
  ttsLabel: string;
  /** 앱이 답을 듣거나 찾는 중이면 누르지 못하게 한다. */
  busy: boolean;
  /** App 이 지금 읽고 있는 조각 번호(onPlay 로 넘긴 목록 안의 번호). 읽는 게 없으면 null. */
  playingIndex: number | null;
  onPlay: (readings: string[]) => void;
  onStop: () => void;
};

const MARKS: ReadingHeard[] = ["○", "×"];

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function NumberReadingPanel({ device, ttsEngine, ttsLabel, busy, playingIndex, onPlay, onStop }: Props) {
  const [open, setOpen] = useState(false);
  const [samples, setSamples] = useState<ReadingSample[]>([]);
  const [marks, setMarks] = useState<ReadingMarks>({});
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  // 마지막으로 [듣기]/[전부 듣기]로 넘긴 줄 번호들. playingIndex 를 줄로 바꿀 때 쓴다.
  const [playedIds, setPlayedIds] = useState<string[]>([]);
  const playable = canTestReading(ttsEngine);
  const playingId = playingIndex === null ? null : (playedIds[playingIndex] ?? null);
  const { ok, bad, todo, total } = countReadingMarks(samples, marks);

  const load = useCallback(async () => {
    setStatus("문장을 불러오는 중…");
    try {
      setSamples(await getReadingSamples());
      setStatus("");
    } catch (error) {
      setStatus(`문장을 불러오지 못했어요: ${errorText(error)}`);
    }
  }, []);

  useEffect(() => {
    if (open && samples.length === 0) void load();
  }, [load, open, samples.length]);

  const play = (startIndex: number, onlyOne: boolean) => {
    const picked = onlyOne ? samples.slice(startIndex, startIndex + 1) : samples.slice(startIndex);
    setPlayedIds(picked.map((sample) => sample.id));
    onPlay(readingsFrom(samples, startIndex, onlyOne));
  };

  const save = async () => {
    setSaving(true);
    try {
      const saved = await saveReadingResults(device, ttsLabel, marks);
      setStatus(`저장했어요: ○ ${saved.ok} · × ${saved.bad} → ${saved.file}`);
      setMarks({});
    } catch (error) {
      setStatus(`저장하지 못했어요: ${errorText(error)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.panel}>
      <Pressable accessibilityRole="button" onPress={() => setOpen(!open)} style={styles.header}>
        <Text style={styles.title}>{open ? "▼" : "▶"} 숫자 읽기 시험</Text>
        <Text style={styles.meta}>말 없이 듣기만 · {ttsLabel || "TTS 모름"}</Text>
      </Pressable>
      {!open ? null : (
        <>
          {!playable ? (
            <Text style={styles.status}>지수 사전 녹음은 정해진 답 문장만 있어요. 위에서 107 같은 TTS 를 고르세요.</Text>
          ) : null}
          <Text style={styles.meta}>
            ○ {ok} · × {bad} · 안 들음 {todo} (모두 {total})
          </Text>
          <View style={styles.row}>
            {playingIndex === null ? (
              <Pressable
                accessibilityRole="button"
                disabled={!playable || busy || samples.length === 0}
                onPress={() => play(0, false)}
                style={[styles.button, (!playable || busy || samples.length === 0) && styles.dim]}
              >
                <Text style={styles.buttonText}>▶ 전부 듣기</Text>
              </Pressable>
            ) : (
              <Pressable accessibilityRole="button" onPress={onStop} style={styles.button}>
                <Text style={styles.buttonText}>■ 멈추기</Text>
              </Pressable>
            )}
            <Pressable
              accessibilityRole="button"
              disabled={saving || ok + bad === 0}
              onPress={() => void save()}
              style={[styles.saveButton, (saving || ok + bad === 0) && styles.dim]}
            >
              <Text style={styles.saveText}>{saving ? "저장 중…" : "결과 저장"}</Text>
            </Pressable>
          </View>
          {status ? <Text style={styles.status}>{status}</Text> : null}
          {samples.map((sample, index) => {
            const mark = marks[sample.id];
            const playing = playingId === sample.id;
            return (
              <View key={sample.id} style={[styles.card, playing && styles.cardPlaying, mark?.heard === "×" && styles.cardBad]}>
                <View style={styles.row}>
                  <Text style={styles.caseId}>{sample.id}</Text>
                  <Text style={styles.meta}>{sample.group}</Text>
                  {playing ? <Text style={styles.playing}>읽는 중</Text> : null}
                </View>
                <Text style={styles.text}>{sample.text}</Text>
                <Text style={styles.reading}>→ {sample.reading}</Text>
                <View style={styles.row}>
                  <Pressable
                    accessibilityRole="button"
                    disabled={!playable || busy || playingIndex !== null}
                    onPress={() => play(index, true)}
                    style={[styles.smallButton, (!playable || busy || playingIndex !== null) && styles.dim]}
                  >
                    <Text style={styles.smallText}>▶ 듣기</Text>
                  </Pressable>
                  {MARKS.map((heard) => (
                    <Pressable
                      key={heard}
                      accessibilityRole="button"
                      accessibilityState={{ selected: mark?.heard === heard }}
                      onPress={() => setMarks((current) => toggleReadingMark(current, sample.id, heard))}
                      style={[styles.smallButton, mark?.heard === heard && styles.smallButtonActive]}
                    >
                      <Text style={[styles.smallText, mark?.heard === heard && styles.smallTextActive]}>{heard}</Text>
                    </Pressable>
                  ))}
                </View>
                {mark?.heard === "×" ? (
                  <TextInput
                    value={mark.memo ?? ""}
                    onChangeText={(memo) => setMarks((current) => setReadingMemo(current, sample.id, memo))}
                    maxLength={MAX_READING_MEMO_CHARS}
                    placeholder="어떻게 읽었나요? (예: 일 일로 끊어 읽음)"
                    style={styles.input}
                  />
                ) : null}
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
  saveButton: { paddingVertical: 10, paddingHorizontal: 16, borderRadius: 10, backgroundColor: "#1D7A46" },
  saveText: { fontSize: 15, fontWeight: "700", color: "#FFF" },
  dim: { opacity: 0.5 },
  card: { backgroundColor: "#FFF", borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: "#E1E4EA" },
  cardPlaying: { borderColor: "#1F4FD8", borderWidth: 2 },
  cardBad: { borderColor: "#B3261E" },
  caseId: { fontSize: 13, fontWeight: "700", color: "#333", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: "#F0F2F5" },
  playing: { fontSize: 12, fontWeight: "700", color: "#1F4FD8" },
  text: { fontSize: 17, fontWeight: "700", color: "#111" },
  reading: { fontSize: 14, color: "#1D7A46" },
  smallButton: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: "#CCD" },
  smallButtonActive: { backgroundColor: "#E6EDFB", borderColor: "#1F4FD8" },
  smallText: { fontSize: 14, color: "#333" },
  smallTextActive: { color: "#1F4FD8", fontWeight: "700" },
  input: { borderWidth: 1, borderColor: "#CCD", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: "#FAFBFC", fontSize: 14 },
});
