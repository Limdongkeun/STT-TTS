/** 화면 공통 값(2026-11-17, Expo 디자인 시스템 방식). 색·간격·모서리·글자 크기는 여기서만 정하고 화면은 가져다 쓴다.
 *  앱은 밝은 화면만 쓴다(app.json userInterfaceStyle: light). 색은 그동안 쓰던 값을 그대로 모았다. */

import type { TextStyle } from "react-native";

export const colors = {
  background: "#F7F8FA",
  surface: "#FFFFFF",
  separator: "#E1E4EA",
  border: "#CCD",
  label: "#111",
  secondaryLabel: "#555",
  tertiaryLabel: "#888",
  accent: "#1F4FD8",
  accentSoft: "#E6EDFB",
  conversation: "#1D7A46",
  conversationSoft: "#E3F4EA",
  danger: "#C0281A",
  dangerSoft: "#F9E3E1",
  recording: "#D83A1F",
  onTint: "#FFFFFF",
  dark: "#333",
} as const;

/** 4px 단위 간격 */
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;

export const radius = { sm: 8, md: 12, lg: 16, full: 999 } as const;

export const type = {
  title: { fontSize: 24, fontWeight: "700", color: colors.label },
  headline: { fontSize: 17, fontWeight: "700", color: colors.label },
  body: { fontSize: 16, fontWeight: "400", color: colors.label },
  subhead: { fontSize: 14, fontWeight: "400", color: colors.secondaryLabel },
  caption: { fontSize: 12, fontWeight: "400", color: colors.tertiaryLabel },
} as const satisfies Record<string, TextStyle>;
