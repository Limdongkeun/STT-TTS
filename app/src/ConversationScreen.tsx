/** 대화 화면(2026-11-13 사용자 요청): '대화 모드'를 누르면 이 화면으로 바뀌고 버튼 없이 계속 대화한다.
 *  가족비서가 말하는 중에 말하거나 얼굴을 누르면 답을 멈추고 듣는다(끼어들기, 2026-11-13 사용자 요청).
 *  가운데 얼굴이 지금 상태(준비 중·말하세요·생각 중·말하는 중·쉬는 중)를 보여 주고, 그 아래 작은 시험표 창에서
 *  말할 문장을 보며(다 외울 수 없어서, 사용자 요청), 맨 아래에 말풍선이 쌓인다.
 *  위쪽 STT 고르기로 폰 기본 STT 와 클라우드 Qwen(차례 방식, 2026-11-20)을 바꾼다.
 *  듣기·답·소리는 VoiceProvider 가 맡고, 이 파일은 보여 주기만 한다. 얼굴 움직임은 AnimatedFace(Reanimated). */

import { memo, useRef, useState, type ComponentRef } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { AnimatedFace } from "./AnimatedFace";
import { colors } from "./theme";
import type { ChatItem, ConversationFace, ConversationStt } from "./conversation";
import { sheetPreviewRows, type SheetResult, type TestCase } from "./testSheet";

type Props = {
  face: ConversationFace;
  /** 폰 STT 가 듣는 중에 받아 적고 있는 글 */
  liveText: string;
  chat: ChatItem[];
  /** 작은 시험표 창에 보일 시험 문장과 지금까지 적힌 결과 */
  cases: TestCase[];
  results: Record<string, SheetResult>;
  sttLabel: string;
  /** 대화 STT 고르기(폰 기본 / 클라우드 Qwen, 2026-11-20). 클라우드가 서버 목록에 없으면 폰 하나만 온다. */
  sttOptions: { mode: ConversationStt; label: string; active: boolean }[];
  onChooseStt: (mode: ConversationStt) => void;
  ttsLabel: string;
  errorMessage: string;
  onEnd: () => void;
  /** 쉬는 중일 때 얼굴을 누르면 다시 듣는다. */
  onResume: () => void;
  /** 말하는 중일 때 얼굴을 누르면 답을 멈추고 듣는다(끼어들기). */
  onInterrupt: () => void;
};

const FACES: Record<ConversationFace, { emoji: string; label: string }> = {
  preparing: { emoji: "🙂", label: "준비 중… 잠깐만요" },
  listening: { emoji: "👂", label: "말하세요" },
  thinking: { emoji: "🤔", label: "생각 중" },
  speaking: { emoji: "🗣️", label: "말하는 중 — 말하거나 얼굴을 누르면 멈춰요" },
  paused: { emoji: "😴", label: "잠깐 쉬는 중 — 얼굴을 누르면 다시 들어요" },
};

export function ConversationScreen({
  face, liveText, chat, cases, results, sttLabel, sttOptions, onChooseStt, ttsLabel, errorMessage, onEnd, onResume, onInterrupt,
}: Props) {
  const { emoji, label } = FACES[face];
  // 방금 시험표에 적힌 문장(마지막 내 말풍선의 칸)을 초록색으로 보여 준다.
  const lastCaseId = [...chat].reverse().find((item) => item.who === "me")?.caseId ?? null;

  return (
    <View style={styles.screen}>
      <Text style={styles.meta}>대화 모드 · STT {sttLabel} · TTS {ttsLabel || "모름"}</Text>
      {sttOptions.length > 1 ? (
        <View style={styles.sttRow}>
          {sttOptions.map((option) => (
            <Pressable
              key={option.mode}
              testID={`conversation-stt-${option.mode}`}
              accessibilityRole="button"
              accessibilityState={{ selected: option.active }}
              onPress={() => onChooseStt(option.mode)}
              style={[styles.sttButton, option.active && styles.sttButtonActive]}
            >
              <Text style={[styles.sttText, option.active && styles.sttTextActive]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        disabled={face !== "paused" && face !== "speaking"}
        onPress={face === "paused" ? onResume : onInterrupt}
        style={styles.faceArea}
      >
        <AnimatedFace face={face} emoji={emoji} />
        <Text testID="conversation-face-label" style={[styles.faceLabel, face === "listening" && styles.faceLabelListening]}>{label}</Text>
        {face === "listening" && liveText ? <Text style={styles.live}>{liveText}</Text> : null}
      </Pressable>
      {errorMessage ? <Text style={styles.error}>{errorMessage}</Text> : null}

      <SheetPreview cases={cases} results={results} lastCaseId={lastCaseId} />

      <ChatList chat={chat} />

      <Pressable testID="conversation-end" accessibilityRole="button" onPress={onEnd} style={styles.endButton}>
        <Text style={styles.endText}>■ 대화 끝내기</Text>
      </Pressable>
    </View>
  );
}

/** 작은 시험표 창. 받아 적는 글이 바뀔 때마다 다시 그리지 않게 따로 둔다(2026-11-17 발열). */
const SheetPreview = memo(function SheetPreview({
  cases, results, lastCaseId,
}: { cases: TestCase[]; results: Record<string, SheetResult>; lastCaseId: string | null }) {
  const [sheetOpen, setSheetOpen] = useState(true);
  const [onlyTodo, setOnlyTodo] = useState(false);
  const rows = sheetPreviewRows(cases, results, onlyTodo);
  const saidCount = sheetPreviewRows(cases, results, false).filter((row) => row.said).length;
  return (
    <View style={styles.sheet}>
      <View style={styles.sheetHeader}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: sheetOpen }}
          onPress={() => setSheetOpen(!sheetOpen)}
          style={styles.flex}
        >
          <Text style={styles.sheetTitle}>
            {sheetOpen ? "▼" : "▶"} 📋 시험표 · 말한 문장 {saidCount}/{cases.length}
          </Text>
        </Pressable>
        {sheetOpen ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: onlyTodo }}
            onPress={() => setOnlyTodo(!onlyTodo)}
            style={[styles.todoButton, onlyTodo && styles.todoButtonActive]}
          >
            <Text style={[styles.todoText, onlyTodo && styles.todoTextActive]}>안 한 것만</Text>
          </Pressable>
        ) : null}
      </View>
      {sheetOpen ? (
        <ScrollView style={styles.sheetList} nestedScrollEnabled>
          {rows.length === 0 ? (
            <Text style={styles.meta}>{cases.length === 0 ? "시험표를 불러오지 못했어요." : "모든 문장을 말했어요."}</Text>
          ) : null}
          {rows.map((row) => (
            <View key={row.id} style={[styles.sheetRow, row.id === lastCaseId && styles.sheetRowLast]}>
              <Text style={[styles.sheetId, row.said && styles.said]}>{row.said ? "✓" : " "} {row.id}</Text>
              <Text style={[styles.sheetSay, row.said && styles.said]}>{row.say}</Text>
            </View>
          ))}
        </ScrollView>
      ) : null}
    </View>
  );
});

/** 말풍선 목록. 새 말풍선이 생길 때만 다시 그린다. */
const ChatList = memo(function ChatList({ chat }: { chat: ChatItem[] }) {
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);
  return (
    <ScrollView
      ref={scrollRef}
      style={styles.chat}
      contentContainerStyle={styles.chatContent}
      onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
    >
      {chat.length === 0 ? (
        <Text style={styles.meta}>시험표 문장을 아무 순서로 말해 보세요. 맞는 칸에 적혀요.</Text>
      ) : null}
      {chat.map((item) => (
        <View key={item.id} style={[styles.bubble, item.who === "me" ? styles.mine : styles.theirs]}>
          <Text style={[styles.bubbleText, item.who === "me" && styles.mineText]}>{item.text}</Text>
          {item.who === "me" ? (
            <Text style={styles.caseTag}>{item.caseId ? `시험표 ${item.caseId}` : "시험표에 없는 말"}</Text>
          ) : null}
        </View>
      ))}
    </ScrollView>
  );
});

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 16, gap: 12, backgroundColor: colors.background },
  meta: { fontSize: 12, color: colors.secondaryLabel, textAlign: "center" },
  sttRow: { flexDirection: "row", justifyContent: "center", gap: 8 },
  sttButton: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: colors.border },
  sttButtonActive: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  sttText: { fontSize: 13, color: colors.dark },
  sttTextActive: { color: colors.accent, fontWeight: "700" },
  faceArea: { alignItems: "center", gap: 6 },
  faceLabel: { fontSize: 20, fontWeight: "700", color: colors.dark },
  faceLabelListening: { color: colors.conversation },
  live: { fontSize: 16, color: colors.accent, textAlign: "center" },
  error: { fontSize: 13, color: colors.danger, textAlign: "center" },
  flex: { flex: 1 },
  sheet: { backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.separator, padding: 10, gap: 6 },
  sheetHeader: { flexDirection: "row", alignItems: "center", gap: 8 },
  sheetTitle: { fontSize: 15, fontWeight: "700", color: colors.label },
  todoButton: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: colors.border },
  todoButtonActive: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  todoText: { fontSize: 13, color: colors.dark },
  todoTextActive: { color: colors.accent, fontWeight: "700" },
  sheetList: { maxHeight: 190 },
  sheetRow: { flexDirection: "row", gap: 8, paddingVertical: 4, paddingHorizontal: 4, borderRadius: 6 },
  sheetRowLast: { backgroundColor: colors.conversationSoft },
  sheetId: { width: 44, fontSize: 14, fontWeight: "700", color: colors.dark },
  sheetSay: { flex: 1, fontSize: 15, color: colors.label },
  said: { color: "#9AA0A6" },
  chat: { flex: 1 },
  chatContent: { gap: 8, paddingVertical: 4 },
  bubble: { maxWidth: "85%", borderRadius: 14, paddingVertical: 8, paddingHorizontal: 12, gap: 2 },
  mine: { alignSelf: "flex-end", backgroundColor: colors.accent },
  theirs: { alignSelf: "flex-start", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.separator },
  bubbleText: { fontSize: 16, color: colors.label },
  mineText: { color: colors.surface },
  caseTag: { fontSize: 11, color: "#DCE6FF", textAlign: "right" },
  endButton: { paddingVertical: 16, borderRadius: 12, backgroundColor: colors.danger, alignItems: "center" },
  endText: { fontSize: 18, fontWeight: "700", color: colors.surface },
});
