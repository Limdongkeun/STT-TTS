/** 앱 맨 아래 시험표 화면. 문장 카드에서 "이 문장 시험"을 누르고 말하면 결과가 자동으로 적힌다.
 *  (파일 이름을 Panel 로 둔 까닭: testSheet.ts 와 대소문자만 다르면 macOS 에서 같은 파일로 잡힌다.) */

import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import {
  accuracyText,
  charErrorRate,
  CHECKS,
  conditionLabel,
  CONDITIONS,
  describeAttempt,
  describeChanges,
  hasBad,
  isDone,
  isVisible,
  resultOf,
  secondsText,
  summarize,
  type CheckKey,
  type Mark,
  type Attempt,
  type SheetFilter,
  type TestCase,
} from "./testSheet";
import type { TestSheetState } from "./useTestSheet";

const FILTERS: [SheetFilter, string][] = [
  ["all", "전체"],
  ["todo", "아직 안 한 것"],
  ["bad", "× 있는 것"],
];

type Props = {
  sheet: TestSheetState;
  /** idle: 누르면 듣기 시작 / listening: 시험 중인 카드만 눌러서 말하기 끝 / busy: 답 찾는 중 */
  stage: "idle" | "listening" | "busy";
  /** 듣는 중에 폰 STT 가 받아 적고 있는 글 */
  liveText: string;
  /** 지금 시험에 쓰는 STT 이름. 말로 한 턴마다 결과에 같이 적힌다. */
  sttLabel: string;
  /** 답·TTS 서버의 TTS 가 mock('삐' 소리)이면 '들린 답'은 판단할 수 없어 빼고 센다. */
  ttsIsMock: boolean;
  onChoose: (testCase: TestCase) => void;
  /** [저장하기]: 저장한 뒤 시험표와 서버 시험 데이터를 함께 비운다(App 이 맡음). */
  onSave: () => void;
};

export function TestSheetPanel({ sheet, stage, liveText, sttLabel, ttsIsMock, onChoose, onSave }: Props) {
  const requireHeard = !ttsIsMock;
  const [filter, setFilter] = useState<SheetFilter>("all");
  const [deviceDraft, setDeviceDraft] = useState<string | null>(null);
  const [showAllAttempts, setShowAllAttempts] = useState(false);
  const { done, bad, total, avgCer } = summarize(sheet.cases, sheet.results, requireHeard);

  const toggle = (caseId: string, key: CheckKey, value: Mark) => {
    const current = resultOf(sheet.results, caseId)[key];
    sheet.update(caseId, { [key]: current === value ? "" : value });
  };

  const saveButton = (
    <Pressable
      accessibilityRole="button"
      disabled={!sheet.canSave || stage !== "idle"}
      onPress={onSave}
      style={[styles.saveButton, (!sheet.canSave || stage !== "idle") && styles.dim]}
    >
      <Text style={styles.saveText}>{sheet.saving ? "저장하는 중…" : "💾 저장하기 (저장하고 처음부터 다시)"}</Text>
    </Pressable>
  );

  let lastGroup = "";
  return (
    <View style={styles.sheet}>
      <Text style={styles.title}>시험표</Text>
      <Text style={styles.meta}>지금 STT: {sttLabel} (맨 위 STT 고르기로 바꿔요. 저장본은 같은 STT끼리 비교해요)</Text>
      <Text style={styles.meta}>시험 환경 (말한 턴마다 같이 적혀요)</Text>
      <View style={styles.row}>
        {CONDITIONS.map(([value, label]) => (
          <Pressable
            key={value}
            accessibilityRole="button"
            accessibilityState={{ selected: sheet.condition === value }}
            disabled={stage !== "idle"}
            onPress={() => sheet.setCondition(value)}
            style={[styles.smallButton, sheet.condition === value && styles.smallButtonActive]}
          >
            <Text style={[styles.smallText, sheet.condition === value && styles.smallTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable
        accessibilityRole="switch"
        accessibilityState={{ checked: sheet.saveAudio }}
        disabled={stage !== "idle"}
        onPress={() => sheet.setSaveAudio(!sheet.saveAudio)}
        style={[styles.smallButton, sheet.saveAudio && styles.smallButtonActive, styles.alignStart]}
      >
        <Text style={[styles.smallText, sheet.saveAudio && styles.smallTextActive]}>
          {sheet.saveAudio ? "🎙 들은 소리 저장 켜짐 (폰 STT, 다음 주 비교용)" : "🎙 들은 소리 저장 꺼짐"}
        </Text>
      </Pressable>
      <View style={styles.row}>
        {deviceDraft === null ? (
          <>
            <Text style={styles.meta}>기기 {sheet.device}</Text>
            <Pressable accessibilityRole="button" onPress={() => setDeviceDraft(sheet.device)} style={styles.smallButton}>
              <Text style={styles.smallText}>기기 이름 바꾸기</Text>
            </Pressable>
          </>
        ) : (
          <>
            <TextInput
              value={deviceDraft}
              onChangeText={setDeviceDraft}
              autoCapitalize="none"
              autoCorrect={false}
              style={[styles.input, styles.flex]}
              accessibilityLabel="기기 이름"
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                if (sheet.changeDevice(deviceDraft)) setDeviceDraft(null);
              }}
              style={styles.smallButton}
            >
              <Text style={styles.smallText}>적용</Text>
            </Pressable>
          </>
        )}
      </View>
      {saveButton}
      <AttemptList attempts={sheet.attempts} showAll={showAllAttempts} onToggle={() => setShowAllAttempts((value) => !value)} />
      <View style={styles.progress}>
        <View style={[styles.progressFill, { width: `${total ? Math.round((done / total) * 100) : 0}%` }]} />
      </View>
      <Text style={styles.meta}>
        끝낸 문장 {done}/{total} · × 있는 문장 {bad}
        {avgCer !== null ? ` · 평균 인식 정확도 ${accuracyText(avgCer)}` : ""}
        {ttsIsMock ? " · TTS가 mock이라 '들린 답'은 세지 않아요" : ""}
      </Text>
      <View style={styles.row}>
        {FILTERS.map(([value, label]) => (
          <Pressable
            key={value}
            accessibilityRole="button"
            accessibilityState={{ selected: filter === value }}
            onPress={() => setFilter(value)}
            style={[styles.smallButton, filter === value && styles.smallButtonActive]}
          >
            <Text style={[styles.smallText, filter === value && styles.smallTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      {sheet.status ? <Text style={[styles.status, isInfo(sheet.status) && styles.statusInfo]}>{sheet.status}</Text> : null}
      {sheet.status.startsWith("시험표를 불러오지") ? (
        <Pressable accessibilityRole="button" onPress={() => void sheet.reload()} style={styles.smallButton}>
          <Text style={styles.smallText}>다시 불러오기</Text>
        </Pressable>
      ) : null}

      {sheet.cases.map((testCase) => {
        const result = resultOf(sheet.results, testCase.id);
        if (!isVisible(result, filter, requireHeard)) return null;
        const cer = charErrorRate(testCase.say, result.recognized);
        const active = sheet.activeId === testCase.id;
        const listening = active && stage === "listening";
        const disabled = stage === "busy" || (stage === "listening" && !active);
        const header = testCase.group !== lastGroup ? <Text style={styles.group}>{testCase.group}</Text> : null;
        lastGroup = testCase.group;
        return (
          <View key={testCase.id} style={styles.cardWrap}>
            {header}
            <View
              style={[
                styles.card,
                isDone(result, requireHeard) && !hasBad(result, requireHeard) && styles.cardDone,
                hasBad(result, requireHeard) && styles.cardBad,
                active && styles.cardActive,
              ]}
            >
              <View style={styles.row}>
                <Text style={styles.caseId}>{testCase.id}</Text>
                {testCase.chain ? <Text style={styles.meta}>{testCase.chain}</Text> : null}
              </View>
              <Text style={styles.say}>“{testCase.say}”</Text>
              <Text style={styles.expect}>
                기대 답: {testCase.expect}
                {testCase.dateDependent ? " (날짜에 따라 달라요)" : ""}
              </Text>
              <Pressable
                accessibilityRole="button"
                disabled={disabled}
                onPress={() => onChoose(testCase)}
                style={[styles.chooseButton, listening && styles.chooseButtonActive, disabled && styles.dim]}
              >
                <Text style={[styles.chooseText, listening && styles.chooseTextActive]}>
                  {listening ? "■ 말하기 끝" : active && stage === "busy" ? "답 찾는 중…" : "🎤 이 문장 말하기"}
                </Text>
              </Pressable>
              {listening ? <Text style={styles.live}>{liveText || "듣는 중… 문장을 소리 내어 말하세요"}</Text> : null}

              <Text style={styles.label}>인식한 말</Text>
              <TextInput
                value={result.recognized}
                onChangeText={(value) => sheet.update(testCase.id, { recognized: value }, 600)}
                placeholder="말하면 자동으로 적혀요"
                style={styles.input}
                accessibilityLabel={`${testCase.id} 인식한 말`}
              />
              {cer !== null ? (
                <Text style={[styles.accuracy, cer > 0 && styles.answerDiff]}>
                  인식 정확도 {accuracyText(cer)} (말한 문장과 글자 비교, 띄어쓰기 빼고)
                </Text>
              ) : null}
              {result.answer ? (
                <Text style={[styles.answer, result.answer.trim() !== testCase.expect.trim() && styles.answerDiff]}>
                  화면 답: {result.answer}
                </Text>
              ) : null}
              {turnMeta(result.condition, result.replyMs, result.askMs, result.ttsMs)}

              <View style={styles.checks}>
                {CHECKS.map(([key, label]) => {
                  const mockSkipped = key === "heard" && !requireHeard;
                  const noRecording = key === "heard" && result.heard === "-";
                  const skipped = mockSkipped || noRecording;
                  return (
                  <View key={key} style={[styles.check, skipped && styles.dim]}>
                    <Text style={styles.label}>
                      {mockSkipped ? `${label} (mock 생략)` : noRecording ? `${label} (녹음 없음)` : label}
                    </Text>
                    <View style={styles.pair}>
                      {(["o", "x"] as const).map((value) => {
                        const on = result[key] === value;
                        return (
                          <Pressable
                            key={value}
                            accessibilityRole="button"
                            accessibilityState={{ selected: on, disabled: skipped }}
                            disabled={skipped}
                            accessibilityLabel={`${testCase.id} ${label} ${value === "o" ? "맞음" : "틀림"}`}
                            onPress={() => toggle(testCase.id, key, value)}
                            style={[styles.mark, on && (value === "o" ? styles.markOk : styles.markBad)]}
                          >
                            <Text style={[styles.markText, on && (value === "o" ? styles.markTextOk : styles.markTextBad)]}>
                              {value === "o" ? "○" : "×"}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
                  );
                })}
              </View>

              <Text style={styles.label}>메모 (틀린 낱말 → 보정 후보)</Text>
              <TextInput
                value={result.note}
                onChangeText={(value) => sheet.update(testCase.id, { note: value }, 600)}
                placeholder="예: 소윤 → 소연"
                style={styles.input}
                accessibilityLabel={`${testCase.id} 메모`}
              />
            </View>
          </View>
        );
      })}
      {saveButton}
    </View>
  );
}

const INFO_PREFIXES = ["저장했어요", "시험표를 비웠어요", "시험표를 불러오는 중"];
const isInfo = (status: string) => INFO_PREFIXES.some((prefix) => status.startsWith(prefix));
const ATTEMPTS_SHOWN = 3;

/** 지난 저장본: 최신이 먼저. 바로 앞 저장본과 비교해 나아진 문장(×→○)과 나빠진 문장(○→×)을 보여 준다. */
function AttemptList({ attempts, showAll, onToggle }: { attempts: Attempt[]; showAll: boolean; onToggle: () => void }) {
  if (!attempts.length) {
    return <Text style={styles.meta}>아직 저장본이 없어요. 다 시험한 뒤 [저장하기]를 누르면 여기에 쌓여요.</Text>;
  }
  const shown = showAll ? attempts : attempts.slice(0, ATTEMPTS_SHOWN);
  return (
    <View style={styles.attempts}>
      <Text style={styles.label}>지난 저장본 (최신이 위)</Text>
      {shown.map((attempt) => (
        <View key={attempt.file || attempt.savedAt} style={styles.attempt}>
          <Text style={styles.attemptMain}>{describeAttempt(attempt)}</Text>
          <Text style={[styles.meta, attempt.worsened.length > 0 && styles.worse]}>
            {describeChanges(attempt)}
            {attempt.badCases.length ? ` · × 있는 문장 ${attempt.badCases.join(", ")}` : ""}
          </Text>
        </View>
      ))}
      {attempts.length > ATTEMPTS_SHOWN ? (
        <Pressable accessibilityRole="button" onPress={onToggle} style={styles.smallButton}>
          <Text style={styles.smallText}>{showAll ? "접기" : `저장본 ${attempts.length}개 모두 보기`}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/** "TV 소음 · 말 끝→소리 1.8초 (답 0.1초 · TTS 0.2초)" — 적힌 게 없으면 아무것도 안 보인다. */
function turnMeta(condition: Parameters<typeof conditionLabel>[0], replyMs?: number | null, askMs?: number | null, ttsMs?: number | null) {
  const parts: string[] = [];
  if (condition) parts.push(conditionLabel(condition));
  if (replyMs != null) {
    const detail = [askMs != null ? `답 ${secondsText(askMs)}` : "", ttsMs != null ? `TTS ${secondsText(ttsMs)}` : ""].filter(Boolean);
    parts.push(`말 끝→소리 ${secondsText(replyMs)}${detail.length ? ` (${detail.join(" · ")})` : ""}`);
  }
  return parts.length ? <Text style={styles.meta}>{parts.join(" · ")}</Text> : null;
}

const styles = StyleSheet.create({
  sheet: { marginTop: 24, paddingTop: 16, borderTopWidth: 2, borderTopColor: "#111", gap: 10 },
  title: { fontSize: 20, fontWeight: "700", color: "#111" },
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 },
  flex: { flex: 1 },
  alignStart: { alignSelf: "flex-start" },
  meta: { fontSize: 12, color: "#666" },
  status: { fontSize: 13, color: "#C0281A" },
  statusInfo: { color: "#1D7A46" },
  saveButton: { paddingVertical: 12, borderRadius: 10, backgroundColor: "#1D7A46", alignItems: "center" },
  saveText: { fontSize: 15, fontWeight: "700", color: "#FFF" },
  attempts: { gap: 6, padding: 10, borderRadius: 10, backgroundColor: "#F0F2F5" },
  attempt: { gap: 2 },
  attemptMain: { fontSize: 14, fontWeight: "600", color: "#111" },
  worse: { color: "#B3261E" },
  progress: { height: 6, borderRadius: 3, backgroundColor: "#DDE1E6", overflow: "hidden" },
  progressFill: { height: 6, backgroundColor: "#1F4FD8" },
  smallButton: { paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: "#CCD" },
  smallButtonActive: { backgroundColor: "#E6EDFB", borderColor: "#1F4FD8" },
  smallText: { fontSize: 13, color: "#333" },
  smallTextActive: { color: "#1F4FD8", fontWeight: "700" },
  group: { marginTop: 8, fontSize: 15, fontWeight: "700", color: "#111" },
  cardWrap: { gap: 6 },
  card: { backgroundColor: "#FFF", borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: "#E1E4EA" },
  cardDone: { borderColor: "#1D7A46" },
  cardBad: { borderColor: "#B3261E" },
  cardActive: { borderColor: "#1F4FD8", borderWidth: 2 },
  caseId: { fontSize: 13, fontWeight: "700", color: "#333", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: "#F0F2F5" },
  say: { fontSize: 17, fontWeight: "700", color: "#111" },
  expect: { fontSize: 13, color: "#555" },
  chooseButton: { alignSelf: "flex-start", paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: "#1F4FD8" },
  chooseButtonActive: { backgroundColor: "#1F4FD8" },
  chooseText: { fontSize: 14, fontWeight: "700", color: "#1F4FD8" },
  chooseTextActive: { color: "#FFF" },
  dim: { opacity: 0.5 },
  live: { fontSize: 15, color: "#1F4FD8" },
  label: { fontSize: 12, color: "#777" },
  input: { borderWidth: 1, borderColor: "#CCD", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: "#FAFBFC", fontSize: 14 },
  answer: { fontSize: 13, color: "#1D7A46" },
  answerDiff: { color: "#B3261E" },
  accuracy: { fontSize: 13, color: "#1D7A46" },
  checks: { flexDirection: "row", gap: 8 },
  check: { flex: 1, gap: 4 },
  pair: { flexDirection: "row", gap: 4 },
  mark: { flex: 1, alignItems: "center", paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: "#CCD" },
  markOk: { backgroundColor: "#E1F2E7", borderColor: "#1D7A46" },
  markBad: { backgroundColor: "#F9E3E1", borderColor: "#B3261E" },
  markText: { fontSize: 16, fontWeight: "700", color: "#999" },
  markTextOk: { color: "#1D7A46" },
  markTextBad: { color: "#B3261E" },
});
