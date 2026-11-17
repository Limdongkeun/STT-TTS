/** 여럿 중 하나를 고르는 버튼 줄(STT·TTS·쉬는 시간). 고른 것은 채운 색, 누르는 동안은 흐리게, 넘치면 다음 줄로. */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "../theme";

export type Choice = { key: string; label: string; selected: boolean; onPress: () => void; testID?: string };

export function ChoiceRow({ choices, disabled = false }: { choices: Choice[]; disabled?: boolean }) {
  return (
    <View style={styles.row}>
      {choices.map((choice) => (
        <Pressable
          key={choice.key}
          testID={choice.testID}
          accessibilityRole="button"
          accessibilityState={{ selected: choice.selected, disabled }}
          disabled={disabled}
          onPress={choice.onPress}
          style={({ pressed }) => [
            styles.chip,
            choice.selected && styles.chipSelected,
            (pressed || disabled) && styles.dim,
          ]}
        >
          <Text style={[styles.text, choice.selected && styles.textSelected]}>{choice.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    minHeight: 40,
    paddingHorizontal: spacing.md,
    justifyContent: "center",
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  dim: { opacity: 0.55 },
  text: { fontSize: 14, color: colors.dark },
  textSelected: { color: colors.onTint, fontWeight: "700" },
});
