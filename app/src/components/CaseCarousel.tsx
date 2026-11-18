/** 시험표 카드를 옆으로 넘겨 보는 줄(2026-11-17 사용자: 밑으로 계속 늘어나서 불편).
 *  한 번에 카드 하나, 옆으로 쓸거나 ◀ ▶ 로 넘기고, 위의 번호 줄(C1·D2…)을 눌러 바로 간다.
 *  번호 색: 끝냄(초록)·× 있음(빨강)·시험 중(파랑 테두리).
 *  저절로 넘어가지 않는다(2026-11-17 사용자: 자꾸 옆으로 넘어가서 불편) — 넘기는 건 사용자만 한다. */

import { useEffect, useRef, useState, type ComponentRef, type ReactElement } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, View, type LayoutChangeEvent } from "react-native";

import { colors, radius, spacing, type } from "../theme";

export type CaseTone = "todo" | "done" | "bad";

type Props<T extends { id: string }> = {
  items: T[];
  activeId: string | null;
  toneOf: (item: T) => CaseTone;
  renderCard: (item: T) => ReactElement;
};

const GAP = spacing.sm;

export function CaseCarousel<T extends { id: string }>({ items, activeId, toneOf, renderCard }: Props<T>) {
  const listRef = useRef<FlatList<T>>(null);
  const stripRef = useRef<ComponentRef<typeof ScrollView>>(null);
  const [width, setWidth] = useState(0);
  const [index, setIndex] = useState(0);
  const current = Math.min(index, Math.max(items.length - 1, 0));
  const page = width + GAP;

  const goTo = (next: number, animated = true) => {
    if (items.length === 0) return;
    const target = Math.max(0, Math.min(items.length - 1, next));
    setIndex(target);
    listRef.current?.scrollToOffset({ offset: target * page, animated });
  };

  // 번호 줄도 지금 카드가 보이게 따라간다(번호 칸 하나 약 56px).
  useEffect(() => {
    stripRef.current?.scrollTo({ x: Math.max(0, current * 56 - 112), animated: true });
  }, [current]);

  const onLayout = (event: LayoutChangeEvent) => setWidth(Math.round(event.nativeEvent.layout.width));

  if (items.length === 0) {
    return <Text style={type.subhead}>보일 문장이 없어요.</Text>;
  }
  return (
    <View style={styles.wrap} onLayout={onLayout}>
      <ScrollView ref={stripRef} horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
        {items.map((item, i) => {
          const tone = toneOf(item);
          const selected = i === current;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="button"
              accessibilityLabel={`${item.id} 카드로 가기`}
              accessibilityState={{ selected }}
              onPress={() => goTo(i)}
              style={[
                styles.idChip,
                tone === "done" && styles.idDone,
                tone === "bad" && styles.idBad,
                item.id === activeId && styles.idActive,
                selected && styles.idSelected,
              ]}
            >
              <Text style={[styles.idText, selected && styles.idTextSelected]}>{item.id}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={styles.nav}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="이전 문장"
          disabled={current === 0}
          onPress={() => goTo(current - 1)}
          hitSlop={8}
          style={({ pressed }) => [styles.navButton, (current === 0 || pressed) && styles.dim]}
        >
          <Text style={styles.navText}>◀</Text>
        </Pressable>
        <Text style={type.subhead}>
          {items[current]?.id} · {current + 1}/{items.length}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="다음 문장"
          disabled={current >= items.length - 1}
          onPress={() => goTo(current + 1)}
          hitSlop={8}
          style={({ pressed }) => [styles.navButton, (current >= items.length - 1 || pressed) && styles.dim]}
        >
          <Text style={styles.navText}>▶</Text>
        </Pressable>
      </View>

      {width > 0 ? (
        <FlatList
          ref={listRef}
          data={items}
          keyExtractor={(item) => item.id}
          horizontal
          showsHorizontalScrollIndicator={false}
          snapToInterval={page}
          snapToAlignment="start"
          decelerationRate="fast"
          disableIntervalMomentum
          ItemSeparatorComponent={() => <View style={{ width: GAP }} />}
          getItemLayout={(_, i) => ({ length: page, offset: page * i, index: i })}
          initialScrollIndex={current}
          // 보이는 카드와 양옆만 그린다(카드마다 입력칸이 많아 한꺼번에 그리면 무겁다, 2026-11-17 발열)
          initialNumToRender={2}
          maxToRenderPerBatch={2}
          windowSize={3}
          onMomentumScrollEnd={(event) => setIndex(Math.round(event.nativeEvent.contentOffset.x / page))}
          renderItem={({ item }) => <View style={{ width }}>{renderCard(item)}</View>}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  strip: { gap: spacing.xs + 2, paddingVertical: 2 },
  idChip: {
    minWidth: 50, paddingVertical: spacing.xs + 2, paddingHorizontal: spacing.sm, borderRadius: radius.full,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center",
  },
  idDone: { backgroundColor: colors.conversationSoft, borderColor: colors.conversationSoft },
  idBad: { backgroundColor: colors.dangerSoft, borderColor: colors.dangerSoft },
  idActive: { borderColor: colors.accent, borderWidth: 2 },
  idSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  idText: { fontSize: 13, fontWeight: "600", color: colors.dark },
  idTextSelected: { color: colors.onTint },
  nav: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  navButton: {
    width: 44, height: 36, borderRadius: radius.md, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  navText: { fontSize: 16, color: colors.dark },
  dim: { opacity: 0.4 },
});
