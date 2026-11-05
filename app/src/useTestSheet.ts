/** 앱 맨 아래 시험표의 상태: 문장 목록, 기기, 작성 중인 시험표, 저장본, 지금 시험 중인 문장.
 *  작성 중인 시험표는 누를 때마다 서버에 임시 저장되고, [저장하기]를 누르면 저장본으로 남는다. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Platform } from "react-native";

import { clearDraft, getAttempts, getDraft, getTestCases, putDraftCase, saveAttempt } from "./api";
import {
  defaultDevice,
  describeAttempt,
  hasRecords,
  isValidDevice,
  nextCase,
  recordTurn as buildRecord,
  resultOf,
  type Attempt,
  type SheetResult,
  type TestCase,
} from "./testSheet";

const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

export function useTestSheet() {
  const [cases, setCases] = useState<TestCase[]>([]);
  const [device, setDevice] = useState(() => defaultDevice(Platform.OS, Platform.Version));
  const [results, setResults] = useState<Record<string, SheetResult>>({});
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [status, setStatus] = useState("시험표를 불러오는 중…");
  const [saving, setSaving] = useState(false);
  // 마지막 저장(또는 초기화) 뒤에 바뀐 게 있는지. 앱을 새로 열었을 때 남은 기록이 있으면 '있음'으로 본다.
  const [dirty, setDirty] = useState(false);

  // 콜백 안에서 늘 최신 값을 쓰려고 ref 로도 들고 있는다.
  const resultsRef = useRef(results);
  const casesRef = useRef(cases);
  const activeIdRef = useRef(activeId);
  const deviceRef = useRef(device);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const writes = useRef<Record<string, Promise<unknown>>>({});

  const replaceResults = (next: Record<string, SheetResult>) => {
    resultsRef.current = next;
    setResults(next);
  };

  const load = useCallback(async () => {
    setStatus("시험표를 불러오는 중…");
    try {
      const [list, draft, saved] = await Promise.all([getTestCases(), getDraft(device), getAttempts(device)]);
      casesRef.current = list;
      setCases(list);
      replaceResults(draft);
      setAttempts(saved);
      setDirty(hasRecords(draft));
      setStatus(list.length ? "" : "서버에 시험 문장이 없어요.");
    } catch (error) {
      setStatus(`시험표를 불러오지 못했어요: ${errorText(error)}`);
    }
  }, [device]);

  useEffect(() => {
    deviceRef.current = device;
    void load();
  }, [load, device]);

  useEffect(
    () => () => {
      for (const timer of Object.values(timers.current)) clearTimeout(timer);
    },
    [],
  );

  /** 문장마다 한 번에 하나씩 저장한다(앞 저장이 끝난 뒤 다음 저장). */
  const persist = useCallback((caseId: string, delay: number) => {
    clearTimeout(timers.current[caseId]);
    timers.current[caseId] = setTimeout(() => {
      delete timers.current[caseId];
      const target = deviceRef.current;
      const body = resultOf(resultsRef.current, caseId);
      const previous = writes.current[caseId] ?? Promise.resolve();
      writes.current[caseId] = previous
        .then(() => putDraftCase(target, caseId, body))
        .then(
          () => setStatus(""),
          (error) => setStatus(`${caseId} 저장하지 못했어요: ${errorText(error)}`),
        );
    }, delay);
  }, []);

  /** 아직 서버로 가지 않은 칸까지 모두 보낸 뒤에 끝난다. */
  const flushPending = useCallback(async () => {
    for (const [caseId, timer] of Object.entries(timers.current)) {
      clearTimeout(timer);
      delete timers.current[caseId];
      const target = deviceRef.current;
      const body = resultOf(resultsRef.current, caseId);
      const previous = writes.current[caseId] ?? Promise.resolve();
      writes.current[caseId] = previous.then(() => putDraftCase(target, caseId, body));
    }
    await Promise.all(Object.values(writes.current));
  }, []);

  const update = useCallback(
    (caseId: string, patch: Partial<SheetResult>, delay = 0) => {
      replaceResults({ ...resultsRef.current, [caseId]: { ...resultOf(resultsRef.current, caseId), ...patch } });
      setDirty(true);
      persist(caseId, delay);
    },
    [persist],
  );

  const setActiveId = useCallback((caseId: string | null) => {
    activeIdRef.current = caseId;
    setActiveIdState(caseId);
  }, []);

  /** 시험 중인 문장에 이번 턴(인식한 말·답)을 적고 다음 문장으로 넘어간다. 다음 문장을 돌려준다. */
  const recordTurn = useCallback(
    (recognized: string, answer: string, stt: string): TestCase | null => {
      const caseId = activeIdRef.current;
      const testCase = casesRef.current.find((item) => item.id === caseId);
      if (!caseId || !testCase) return null;
      update(caseId, buildRecord(resultOf(resultsRef.current, caseId), testCase, recognized, answer, stt));
      const following = nextCase(casesRef.current, caseId);
      setActiveId(following?.id ?? null);
      return following;
    },
    [setActiveId, update],
  );

  /** 지금 시험표를 저장본으로 남긴다. 남긴 저장본을 돌려주고, 실패하면 null. */
  const save = useCallback(async (): Promise<Attempt | null> => {
    setSaving(true);
    try {
      await flushPending();
      const attempt = await saveAttempt(deviceRef.current);
      setAttempts((current) => [attempt, ...current]);
      setDirty(false);
      setStatus(`저장했어요: ${describeAttempt(attempt)}`);
      return attempt;
    } catch (error) {
      setStatus(`저장본을 남기지 못했어요: ${errorText(error)}`);
      return null;
    } finally {
      setSaving(false);
    }
  }, [flushPending]);

  /** 시험표의 ○/×·인식한 말을 모두 비운다(저장본은 그대로). */
  const clearSheet = useCallback(async (message = "시험표를 비웠어요. 처음부터 다시 시험하면 돼요.") => {
    for (const timer of Object.values(timers.current)) clearTimeout(timer);
    timers.current = {};
    await Promise.allSettled(Object.values(writes.current));
    writes.current = {};
    await clearDraft(deviceRef.current);
    replaceResults({});
    setActiveId(null);
    setDirty(false);
    setStatus(message);
  }, [setActiveId]);

  const changeDevice = useCallback((value: string): boolean => {
    const trimmed = value.trim();
    if (!isValidDevice(trimmed)) {
      setStatus("기기 이름은 ios-27-0-1 처럼 영문 소문자·숫자·- 만 쓸 수 있어요.");
      return false;
    }
    setDevice(trimmed);
    return true;
  }, []);

  const activeCase = useMemo(() => cases.find((item) => item.id === activeId) ?? null, [cases, activeId]);
  const canSave = !saving && hasRecords(results);

  return {
    cases,
    device,
    results,
    attempts,
    activeId,
    activeCase,
    status,
    saving,
    dirty,
    canSave,
    setActiveId,
    update,
    recordTurn,
    save,
    clearSheet,
    changeDevice,
    reload: load,
  };
}

export type TestSheetState = ReturnType<typeof useTestSheet>;
