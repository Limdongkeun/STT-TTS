/** 대화 화면 가운데 얼굴의 움직임(2026-11-17 사용자 요청, expo/examples with-reanimated 방식).
 *  듣는 중: 천천히 숨 쉬듯 커졌다 작아짐 / 생각 중: 점 세 개가 차례로 깜빡임 / 말하는 중: 빠르게 살짝 출렁임 /
 *  쉬는 중: 흐려짐 / 준비 중: 멈춤. 폰의 '동작 줄이기'가 켜져 있으면 움직이지 않는다(상태는 글과 테두리 색으로 보인다).
 *  움직임은 UI 스레드에서 돈다(대화 로직이 바빠도 끊기지 않게). */

import { useEffect } from "react";
import { StyleSheet, Text, View } from "react-native";
import Animated, {
  cancelAnimation, Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withDelay, withRepeat, withSequence,
  withTiming, type SharedValue,
} from "react-native-reanimated";

import type { ConversationFace } from "./conversation";
import { colors } from "./theme";

type Props = { face: ConversationFace; emoji: string };

const BREATH_MS = 1400;
const TALK_MS = 180;
const DOT_MS = 400;

export function AnimatedFace({ face, emoji }: Props) {
  const reduceMotion = useReducedMotion();
  const scale = useSharedValue(1);
  const opacity = useSharedValue(1);
  const dots = [useSharedValue(0.3), useSharedValue(0.3), useSharedValue(0.3)];

  useEffect(() => {
    cancelAnimation(scale);
    dots.forEach((dot) => cancelAnimation(dot));
    opacity.value = withTiming(face === "paused" ? 0.45 : 1, { duration: 300 });
    if (reduceMotion) {
      scale.value = 1;
      return;
    }
    if (face === "listening") {
      scale.value = withRepeat(
        withSequence(
          withTiming(1.08, { duration: BREATH_MS, easing: Easing.inOut(Easing.sin) }),
          withTiming(1, { duration: BREATH_MS, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
      );
    } else if (face === "speaking") {
      scale.value = withRepeat(
        withSequence(withTiming(1.05, { duration: TALK_MS }), withTiming(0.98, { duration: TALK_MS })),
        -1,
        true,
      );
    } else {
      scale.value = withTiming(1, { duration: 200 });
    }
    if (face === "thinking") {
      dots.forEach((dot, index) => {
        dot.value = withDelay(
          index * (DOT_MS / 2),
          withRepeat(withSequence(withTiming(1, { duration: DOT_MS }), withTiming(0.3, { duration: DOT_MS })), -1),
        );
      });
    }
    // dots 는 그릴 때마다 새 배열이지만 안의 값은 같은 shared value 라 의존성에 넣지 않는다.
  }, [face, reduceMotion]);

  const faceStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }], opacity: opacity.value }));

  return (
    <View style={styles.wrap}>
      <Animated.View
        testID="conversation-face"
        style={[styles.faceCircle, face === "listening" && styles.faceListening, face === "speaking" && styles.faceSpeaking, faceStyle]}
      >
        <Text style={styles.face}>{emoji}</Text>
      </Animated.View>
      {face === "thinking" ? (
        <View style={styles.dots} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {dots.map((dot, index) => <Dot key={index} value={dot} />)}
        </View>
      ) : null}
    </View>
  );
}

function Dot({ value }: { value: SharedValue<number> }) {
  const style = useAnimatedStyle(() => ({ opacity: value.value }));
  return <Animated.View style={[styles.dot, style]} />;
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", gap: 6 },
  faceCircle: {
    width: 104, height: 104, borderRadius: 52, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surface, borderWidth: 3, borderColor: colors.separator,
  },
  faceListening: { borderColor: colors.conversation },
  faceSpeaking: { borderColor: colors.accent },
  face: { fontSize: 56 },
  dots: { flexDirection: "row", gap: 6, height: 10 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.secondaryLabel },
});
