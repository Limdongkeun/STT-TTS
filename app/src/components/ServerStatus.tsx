/** 서버 상태 한 줄: 연결됨(초록)/확인 중/연결 안 됨(빨강). 누르면 다시 확인하고, 주소·오류 내용은 '자세히'로 접어 둔다. */

import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { describeServerInfo, type ServerInfo } from "../serverInfo";
import { colors, radius, spacing, type } from "../theme";

type Props = { info: ServerInfo; sttUrl?: string | null; ttsUrl?: string | null; onRefresh: () => void };

export function ServerStatus({ info, sttUrl, ttsUrl, onRefresh }: Props) {
  const [open, setOpen] = useState(false);
  const dot = info.kind === "ok" ? colors.conversation : info.kind === "error" ? colors.danger : colors.tertiaryLabel;
  const summary = info.kind === "error" ? "서버 연결 안 됨 · 눌러서 다시 확인" : describeServerInfo(info);
  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <Pressable
          testID="server-status"
          accessibilityRole="button"
          accessibilityHint="눌러서 서버 상태를 다시 확인"
          onPress={onRefresh}
          style={({ pressed }) => [styles.pill, info.kind === "error" && styles.pillError, pressed && styles.dim]}
        >
          <View style={[styles.dot, { backgroundColor: dot }]} />
          <Text style={[styles.pillText, info.kind === "error" && styles.errorText]} numberOfLines={1}>{summary} ↻</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={() => setOpen(!open)} hitSlop={8}>
          <Text style={type.caption}>{open ? "접기" : "자세히"}</Text>
        </Pressable>
      </View>
      {open ? (
        <View style={styles.details}>
          <Text style={type.caption}>STT 서버: {sttUrl ?? "설정 안 됨"}</Text>
          <Text style={type.caption}>답·TTS 서버: {ttsUrl ?? "설정 안 됨"}</Text>
          {info.kind === "error" ? <Text style={[type.caption, styles.errorText]}>{info.message}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  pill: {
    flexShrink: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.md - 4,
    borderRadius: radius.full,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.separator,
  },
  pillError: { backgroundColor: colors.dangerSoft, borderColor: colors.dangerSoft },
  dot: { width: 8, height: 8, borderRadius: 4 },
  pillText: { flexShrink: 1, fontSize: 13, fontWeight: "600", color: colors.secondaryLabel },
  errorText: { color: colors.danger },
  details: { paddingHorizontal: spacing.xs, gap: 2 },
  dim: { opacity: 0.6 },
});
