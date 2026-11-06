/** 앱 시험표 규칙 (순수 함수, 테스트 대상). 서버 /test-cases · /test-runs 와 같은 모양. */

export type Mark = "" | "o" | "x";
/** 들린 답에만 "-"(녹음 없음: 이 답의 소리가 없어 판단하지 않음)가 더 있다. */
export type HeardMark = Mark | "-";

/** 시험 환경. 다음 주 서버 STT 와 같은 조건끼리 비교하려고 턴마다 적는다. */
export type Condition = "" | "quiet" | "tv" | "far" | "other_voice";

export const CONDITIONS = [
  ["quiet", "조용함"],
  ["tv", "TV 소음"],
  ["far", "3m 거리"],
  ["other_voice", "다른 목소리"],
] as const;

export const DEFAULT_CONDITION: Condition = "quiet";

export function conditionLabel(condition: Condition): string {
  return CONDITIONS.find(([key]) => key === condition)?.[1] ?? "";
}

/** 한 턴에 걸린 시간(ms). replyMs 는 말이 끝난 뒤 답 소리가 나기 시작할 때까지. */
export type TurnTimings = { askMs?: number; ttsMs?: number; replyMs?: number };

/** 서버와 같은 상한(10분). 넘거나 음수·NaN 이면 적지 않는다. */
export const MAX_TIMING_MS = 600_000;

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
  heard: HeardMark;
  note: string;
  /** 예전 저장본 호환용(지금은 쓰지 않음): '나' 역할 */
  speaker: "" | "wife" | "husband";
  /** 이 턴을 받아 적은 STT (예: "폰 기본 STT", "Qwen3-ASR-1.7B") */
  stt: string;
  condition: Condition;
  askMs?: number | null;
  ttsMs?: number | null;
  replyMs?: number | null;
  /** 이 턴에 폰 STT 가 들은 소리(서버가 지어 준 파일 이름). 다음 주 서버 STT 비교용 */
  audioFile?: string;
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
  condition: "",
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
  /** 평균 글자 오류율(CER). 인식한 말이 하나도 없으면 null */
  avgCer?: number | null;
  /** false 면 TTS 가 mock 이라 '들린 답'을 세지 않은 저장본 */
  heardChecked?: boolean;
  /** 말이 끝난 뒤 소리가 나기까지 평균(ms). 잰 턴이 없으면 null */
  avgReplyMs?: number | null;
  /** 저장본에 같이 남은 소리 파일 수 */
  audioCount?: number;
};

/** "11/5 13:40 · 9a49c4f · 끝낸 30/32 · × 3" */
export function describeAttempt(attempt: Attempt): string {
  const match = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(attempt.savedAt);
  const when = match ? `${Number(match[1])}/${Number(match[2])} ${match[3]}:${match[4]}` : attempt.savedAt;
  const stt = attempt.sttLabels.length ? attempt.sttLabels.join(" + ") : "STT 모름";
  const parts = [`[${stt}]`, when, attempt.version || "버전 모름"];
  if (attempt.avgCer !== undefined && attempt.avgCer !== null) parts.push(`인식 ${accuracyText(attempt.avgCer)}`);
  if (attempt.avgReplyMs !== undefined && attempt.avgReplyMs !== null) parts.push(`소리까지 ${secondsText(attempt.avgReplyMs)}`);
  parts.push(`끝낸 ${attempt.done}/${attempt.total}`, `× ${attempt.badCases.length}`);
  if (attempt.audioCount) parts.push(`소리 ${attempt.audioCount}개`);
  return parts.join(" · ");
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
/** TTS 가 mock('삐' 소리)이면 '들린 답'은 판단할 수 없어 세지 않는다. */
export function checkKeys(requireHeard: boolean): CheckKey[] {
  return CHECKS.map(([key]) => key).filter((key) => requireHeard || key !== "heard");
}

export function isDone(result: SheetResult, requireHeard = true): boolean {
  return result.recognized.trim() !== "" && checkKeys(requireHeard).every((key) => result[key] !== "");
}

export function hasBad(result: SheetResult, requireHeard = true): boolean {
  return checkKeys(requireHeard).some((key) => result[key] === "x");
}

export function isVisible(result: SheetResult, filter: SheetFilter, requireHeard = true): boolean {
  if (filter === "todo") return !isDone(result, requireHeard);
  if (filter === "bad") return hasBad(result, requireHeard);
  return true;
}

/** 비교용 글: 한글 표준형(NFC)으로 맞추고 글자·숫자만 남긴다(서버 compact_question 과 같은 규칙). */
function compact(text: string): string {
  return Array.from(text.normalize("NFC"))
    .filter((char) => /[\p{L}\p{N}]/u.test(char))
    .join("");
}

function editDistance(left: string[], right: string[]): number {
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let i = 1; i <= left.length; i += 1) {
    const current = [i];
    for (let j = 1; j <= right.length; j += 1) {
      current.push(Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left[i - 1] === right[j - 1] ? 0 : 1)));
    }
    previous = current;
  }
  return previous[right.length];
}

/** 글자 오류율(CER) = 고쳐야 할 글자 수 ÷ 말한 문장 글자 수. 띄어쓰기·문장부호는 빼고 센다. 인식한 말이 없으면 null. */
export function charErrorRate(reference: string, hypothesis: string): number | null {
  const ref = Array.from(compact(reference));
  const hyp = Array.from(compact(hypothesis));
  if (!ref.length || !hyp.length) return null;
  return editDistance(ref, hyp) / ref.length;
}

/** CER 0.06 → "94%" (정확도 = 1 − CER, 0% 아래로는 안 내려감) */
export function accuracyText(cer: number): string {
  return `${Math.round(Math.max(0, 1 - cer) * 100)}%`;
}

export function summarize(cases: TestCase[], results: Record<string, SheetResult>, requireHeard = true) {
  let done = 0;
  let bad = 0;
  const cers: number[] = [];
  for (const testCase of cases) {
    const result = resultOf(results, testCase.id);
    if (isDone(result, requireHeard)) done += 1;
    if (hasBad(result, requireHeard)) bad += 1;
    const cer = charErrorRate(testCase.say, result.recognized);
    if (cer !== null) cers.push(cer);
  }
  const avgCer = cers.length ? cers.reduce((sum, value) => sum + value, 0) / cers.length : null;
  return { done, bad, total: cases.length, avgCer };
}

/** 날짜에 따라 바뀌지 않는 문장은 화면 답이 기대 답과 같으면 ○ 를 미리 채운다. 아니면 비워 둔다.
 * 띄어쓰기·문장부호 차이('퇴근 길에' / '퇴근길에')는 같은 답으로 본다. */
export function autoScreenMark(testCase: TestCase, answer: string): Mark {
  if (testCase.dateDependent) return "";
  const got = compact(answer);
  return got !== "" && got === compact(testCase.expect) ? "o" : "";
}

/** 말한 문장을 기록할 때의 결과. 사람이 이미 누른 화면 답(○/×)은 덮지 않는다.
 * 지난 턴의 '녹음 없음'과 걸린 시간은 이번 턴에 다시 정하므로 비운다. */
export function recordTurn(
  previous: SheetResult,
  testCase: TestCase,
  recognized: string,
  answer: string,
  stt: string,
  condition: Condition = "",
): SheetResult {
  const auto = autoScreenMark(testCase, answer);
  return {
    ...previous,
    recognized,
    answer,
    stt,
    condition,
    askMs: null,
    ttsMs: null,
    replyMs: null,
    audioFile: "",
    screen: auto === "o" ? "o" : previous.screen,
    heard: previous.heard === "-" ? "" : previous.heard,
  };
}

const validMs = (value: number | undefined): number | null =>
  value !== undefined && Number.isFinite(value) && value >= 0 && value <= MAX_TIMING_MS ? Math.round(value) : null;

/** 시험표에 적을 시간 칸. 잴 수 없었던 값(음수·너무 큼·없음)은 null 로 비운다. */
export function timingPatch(timings: TurnTimings): Pick<SheetResult, "askMs" | "ttsMs" | "replyMs"> {
  return { askMs: validMs(timings.askMs), ttsMs: validMs(timings.ttsMs), replyMs: validMs(timings.replyMs) };
}

/** 1830 → "1.8초" */
export function secondsText(ms: number): string {
  return `${(ms / 1000).toFixed(1)}초`;
}

export function nextCase(cases: TestCase[], currentId: string): TestCase | null {
  const index = cases.findIndex((testCase) => testCase.id === currentId);
  return index >= 0 && index + 1 < cases.length ? cases[index + 1] : null;
}
