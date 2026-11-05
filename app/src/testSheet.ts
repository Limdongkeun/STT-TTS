/** 앱 시험표 규칙 (순수 함수, 테스트 대상). 서버 /test-cases · /test-runs 와 같은 모양. */

export type Mark = "" | "o" | "x";

export type TestCase = {
  group: string;
  id: string;
  say: string;
  expect: string;
  dateDependent: boolean;
  chain: string;
};

export type SheetResult = {
  recognized: string;
  answer: string;
  key: Mark;
  screen: Mark;
  heard: Mark;
  note: string;
  /** 예전 저장본 호환용(지금은 쓰지 않음): '나' 역할 */
  speaker: "" | "wife" | "husband";
  /** 이 턴을 받아 적은 STT (예: "폰 기본 STT", "Qwen3-ASR-1.7B") */
  stt: string;
  updatedAt?: string;
};

export type SheetFilter = "all" | "todo" | "bad";

export const CHECKS = [
  ["key", "핵심 정보"],
  ["screen", "화면 답"],
  ["heard", "들린 답"],
] as const;

export type CheckKey = (typeof CHECKS)[number][0];

export const EMPTY_RESULT: SheetResult = {
  recognized: "",
  answer: "",
  key: "",
  screen: "",
  heard: "",
  note: "",
  speaker: "",
  stt: "",
};

const DEVICE_PATTERN = /^[a-z0-9][a-z0-9-]{0,39}$/;

/** 서버와 같은 기기 이름 규칙: 영문 소문자·숫자·- (40자까지) */
export function isValidDevice(device: string): boolean {
  return DEVICE_PATTERN.test(device);
}

/** 예: ("ios", "27.0.1") → "ios-27-0-1", ("android", 35) → "android-35". */
export function defaultDevice(os: string, version: string | number): string {
  const name = `${os}-${version}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
  return name || "device";
}

/** [저장하기]로 남긴 저장본 요약 (서버 /test-sheet/{기기}/attempts). */
export type Attempt = {
  savedAt: string;
  version: string;
  file: string;
  /** 이 저장본에 쓰인 STT 이름들(많이 쓰인 순서) */
  sttLabels: string[];
  tts: string;
  /** 비교한 저장본 파일(같은 STT 의 바로 앞 저장본). 없으면 "" */
  comparedWith: string;
  done: number;
  total: number;
  okMarks: number;
  badCases: string[];
  improved: string[];
  worsened: string[];
};

/** "11/5 13:40 · 9a49c4f · 끝낸 30/32 · × 3" */
export function describeAttempt(attempt: Attempt): string {
  const match = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(attempt.savedAt);
  const when = match ? `${Number(match[1])}/${Number(match[2])} ${match[3]}:${match[4]}` : attempt.savedAt;
  const stt = attempt.sttLabels.length ? attempt.sttLabels.join(" + ") : "STT 모름";
  return [`[${stt}]`, when, attempt.version || "버전 모름", `끝낸 ${attempt.done}/${attempt.total}`, `× ${attempt.badCases.length}`].join(" · ");
}

/** "×→○ D1 / ○→× D8" — 같은 STT 의 바로 앞 저장본과 비교. 비교할 게 없거나 변화가 없으면 그렇게 말한다. */
export function describeChanges(attempt: Attempt): string {
  if (!attempt.comparedWith) return "이 STT의 첫 저장본";
  const parts: string[] = [];
  if (attempt.improved.length) parts.push(`×→○ ${attempt.improved.join(", ")}`);
  if (attempt.worsened.length) parts.push(`○→× ${attempt.worsened.join(", ")}`);
  return parts.join(" / ") || "지난번과 같아요";
}

/** 시험표에 적힌 게 하나라도 있는지(저장할 거리가 있는지). */
export function hasRecords(results: Record<string, SheetResult>): boolean {
  return Object.values(results).some(
    (result) => result.recognized.trim() !== "" || result.key !== "" || result.screen !== "" || result.heard !== "",
  );
}

export function resultOf(results: Record<string, SheetResult>, caseId: string): SheetResult {
  return { ...EMPTY_RESULT, ...(results[caseId] ?? {}) };
}

/** 인식한 말이 있고 ○/× 세 개를 다 눌렀으면 끝난 문장. */
export function isDone(result: SheetResult): boolean {
  return result.recognized.trim() !== "" && CHECKS.every(([key]) => result[key] !== "");
}

export function hasBad(result: SheetResult): boolean {
  return CHECKS.some(([key]) => result[key] === "x");
}

export function isVisible(result: SheetResult, filter: SheetFilter): boolean {
  if (filter === "todo") return !isDone(result);
  if (filter === "bad") return hasBad(result);
  return true;
}

export function summarize(cases: TestCase[], results: Record<string, SheetResult>) {
  let done = 0;
  let bad = 0;
  for (const testCase of cases) {
    const result = resultOf(results, testCase.id);
    if (isDone(result)) done += 1;
    if (hasBad(result)) bad += 1;
  }
  return { done, bad, total: cases.length };
}

/** 날짜에 따라 바뀌지 않는 문장은 화면 답이 기대 답과 글자까지 같으면 ○ 를 미리 채운다. 아니면 비워 둔다. */
export function autoScreenMark(testCase: TestCase, answer: string): Mark {
  if (testCase.dateDependent) return "";
  return answer.trim() === testCase.expect.trim() ? "o" : "";
}

/** 말한 문장을 기록할 때의 결과. 사람이 이미 누른 화면 답(○/×)은 덮지 않는다. */
export function recordTurn(
  previous: SheetResult,
  testCase: TestCase,
  recognized: string,
  answer: string,
  stt: string,
): SheetResult {
  const auto = autoScreenMark(testCase, answer);
  return {
    ...previous,
    recognized,
    answer,
    stt,
    screen: auto === "o" ? "o" : previous.screen,
  };
}

export function nextCase(cases: TestCase[], currentId: string): TestCase | null {
  const index = cases.findIndex((testCase) => testCase.id === currentId);
  return index >= 0 && index + 1 < cases.length ? cases[index + 1] : null;
}
