/** 화면의 한 구역: 제목(+짧은 설명) 아래에 내용을 묶는다. 구역끼리는 배경과 테두리로 나뉜다. */

import type { ReactNode } from "react";
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";

import { colors, radius, spacing, type } from "../theme";

type Props = { title?: string; caption?: string; children: ReactNode; style?: StyleProp<ViewStyle> };

export function Section({ title, caption, children, style }: Props) {
  return (
    <View style={[styles.section, style]}>
      {title ? <Text accessibilityRole="header" style={type.headline}>{title}</Text> : null}
      {caption ? <Text style={type.subhead}>{caption}</Text> : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderCurve: "continuous",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.separator,
    padding: spacing.md,
    gap: spacing.sm,
  },
});
