import { setAudioModeAsync, setIsAudioActiveAsync, useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, AppState, Modal, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import {
  getHealth,
  NoRecordingError,
  postAsk,
  postStt,
  postTts,
  resetDemo,
  sttServerUrl,
  ttsServerUrl,
  type AskContext,
} from "./src/api";
import { FIRST_START_TIMEOUT_MS, waitUntilLoaded, waitUntilStarted } from "./src/playback";
import {
  activeTtsChoice, describeServerInfo, PHONE_STT_LABEL, sttButtonLabel, sttChoicesOf, sttLabelFor, ttsButtonLabel,
  ttsChoicesOf,
  type HealthResponse, type ServerInfo,
} from "./src/serverInfo";
import { fetchSequentially, shouldSplitSpeech, SpeechCancelledError, speechPieces } from "./src/speechChunks";
import { createPrefetcher } from "./src/prefetch";
import {
  addChat, CONVERSATION_SILENCE_MS, conversationFace, formatSilenceLabel, isBargeIn, isSelfEcho, nextConversationStep,
  RETRY_DELAY_MS, SILENCE_OPTIONS_MS, type ChatItem, type TurnOutcome,
} from "./src/conversation";
import { ConversationScreen } from "./src/ConversationScreen";
import { STT_MODE_LABELS, type SttMode } from "./src/sttModes";
import { usePhoneStt, type PhoneTurn } from "./src/usePhoneStt";
import { useServerRecorder } from "./src/useServerRecorder";
import { AnswerListenPanel } from "./src/AnswerListenPanel";
import { NumberReadingPanel } from "./src/NumberReadingPanel";
import { TestSheetPanel } from "./src/TestSheetPanel";
import { describeAttempt, type TestCase } from "./src/testSheet";
import { useTestSheet } from "./src/useTestSheet";

type Stage = "idle" | "listening" | "transcribing" | "asking" | "speaking";

/** 대화 화면이 열려 있는 동안의 대화. errors: 연달아 난 오류 수(쉬기 판단). awaitingPlayback: 답을 다 읽으면 다시 듣기.
 *  끼어들기(2026-11-13 사용자 요청): 답을 읽는 동안 폰 STT 로 듣는다. bargeIn — off: 안 들음 / armed: 끼어들기를 기다림 /
 *  taken: 끼어들어서 그 말을 듣는 중. speakingText: 지금 읽는 답(화면 답·소리 글, 폰이 자기 소리를 받아 적은 것을 가려낸다).
 *  speakingAnswer: 지금 읽는 화면 답(끼어든 말의 답이 이것과 같으면 되풀이라 읽지 않는다). */
type BargeIn = "off" | "armed" | "taken";
type Conversation = {
  errors: number; awaitingPlayback: boolean; bargeIn: BargeIn; speakingText: string; speakingAnswer: string;
};
/** 끼어든 말이 자기 답 소리였을 때 보여 주는 글(2026-11-16: 자기 답을 듣고 같은 답을 되풀이했다). */
const SELF_ECHO_NOTICE = "제 목소리를 들은 것 같아 넘겼어요. 말하세요.";
/** 말로 끼어들기는 iOS 만(자기 소리 빼기). 안드로이드는 얼굴을 눌러 끊는다. */
const VOICE_BARGE_IN = Platform.OS === "ios";

type Timings = { sttMs?: number; askMs?: number; ttsMs?: number; totalMs?: number };

/** 한 답의 소리 조각들(문장 단위). audios[i] 는 i번째 조각의 음성 주소, next 는 다음에 틀 조각.
 *  onChunk: 숫자 읽기 시험처럼 몇 번째 조각을 트는지 화면에 보여야 할 때. 있으면 끝나도 대화 모드로 넘어가지 않는다. */
type SpeechQueue = { audios: Promise<string>[]; next: number; urls: string[]; onChunk?: (index: number) => void };

/** 뒤 조각을 아무도 기다리지 않을 때 '처리 안 된 거부' 경고가 뜨지 않게 한다. */
function quiet<T>(promise: Promise<T>): Promise<T> {
  promise.catch(() => undefined);
  return promise;
}

const STAGE_LABELS: Record<Stage, string> = {
  idle: "대기 중",
  listening: "듣는 중… 다 말하면 버튼을 다시 누르세요",
  transcribing: "글로 바꾸는 중",
  asking: "답 찾는 중",
  speaking: "답 읽는 중",
};

export default function App() {
  // 버튼 말하기는 정확도가 먼저라 서버 Qwen 으로 시작한다. 대화 모드는 늘 폰 STT(2026-11-16 사용자).
  const [sttMode, setSttMode] = useState<SttMode>("server");
  // 서버 STT 중 고른 것(Qwen·LFM3, 2026-11-16 사용자: 기존 것과 조합해 시험). null 이면 서버 기본.
  const [serverStt, setServerStt] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [question, setQuestion] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [speechText, setSpeechText] = useState("");
  const [typedQuestion, setTypedQuestion] = useState("");
  const [timings, setTimings] = useState<Timings>({});
  const [errorMessage, setErrorMessage] = useState("");
  const [silenceMs, setSilenceMs] = useState(CONVERSATION_SILENCE_MS);
  // 대화 화면이 열려 있는지. 열려 있는 동안은 '대화 끝내기'를 누를 때까지 듣기·답하기를 이어 간다(2026-11-13).
  const [conversationActive, setConversationActive] = useState(false);
  // 오류가 연달아 나서 쉬는 중(얼굴을 누르면 다시 듣는다).
  const [conversationPaused, setConversationPaused] = useState(false);
  const [chat, setChat] = useState<ChatItem[]>([]);
  const [canReplay, setCanReplay] = useState(false);
  const [serverInfo, setServerInfo] = useState<ServerInfo>({ kind: "checking" });
  // 앱에서 고른 TTS(null = 서버 기본). 서버 하나로 합쳐 띄웠을 때 /health 의 ttsChoices 중에서 고른다.
  const [ttsChoice, setTtsChoice] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  // 숫자 읽기 시험에서 지금 읽는 조각 번호(없으면 null).
  const [readingIndex, setReadingIndex] = useState<number | null>(null);
  // readingIndex 가 어느 칸(답 듣기 / 숫자 읽기 시험)에서 넘긴 목록의 번호인지. 그 칸만 '읽는 중'을 보인다.
  const [readingOwner, setReadingOwner] = useState<"answers" | "numbers">("numbers");
  // 맨 아래 시험표: 시험 중인 문장이 있으면 이번 턴을 자동으로 적는다.
  const testSheet = useTestSheet();
  const recordTurnRef = useRef(testSheet.recordTurn);
  recordTurnRef.current = testSheet.recordTurn;
  const recordMatchedTurnRef = useRef(testSheet.recordMatchedTurn);
  recordMatchedTurnRef.current = testSheet.recordMatchedTurn;
  const markNoRecordingRef = useRef(testSheet.markNoRecording);
  markNoRecordingRef.current = testSheet.markNoRecording;
  const markPlaybackFailedRef = useRef(testSheet.markPlaybackFailed);
  markPlaybackFailedRef.current = testSheet.markPlaybackFailed;
  const markPlaybackRetriedRef = useRef(testSheet.markPlaybackRetried);
  markPlaybackRetriedRef.current = testSheet.markPlaybackRetried;
  const recordTimingsRef = useRef(testSheet.recordTimings);
  recordTimingsRef.current = testSheet.recordTimings;
  const markInterruptedRef = useRef(testSheet.markInterrupted);
  markInterruptedRef.current = testSheet.markInterrupted;
  const markPrefetchedRef = useRef(testSheet.markPrefetched);
  markPrefetchedRef.current = testSheet.markPrefetched;
  /** 재생할 때마다 1씩 늘린다. 재생 확인 중에 새 답이 오면 지난 확인은 멈춘다. */
  const playIdRef = useRef(0);
  // 시험표에 적을 STT 이름(폰 기본 STT, 또는 서버 STT 모델 이름)과 서버 STT 고르기 목록. STT 서버에 묻는다
  // (STT 를 바꾸거나 서버 정보를 다시 읽을 때).
  const [sttServerHealth, setSttServerHealth] = useState<HealthResponse | null>(null);
  const sttLabelRef = useRef(PHONE_STT_LABEL);
  const sttLabel = sttLabelFor(sttMode, sttServerHealth, serverStt);
  sttLabelRef.current = sttLabel;
  const sttChoices = sttChoicesOf(sttServerHealth);
  // 서버에 보낼 STT: 고른 것이 목록에 있을 때만(예전 서버·목록에 없으면 서버 기본)
  const serverSttEngine = serverStt && sttChoices.some((choice) => choice.engine === serverStt) ? serverStt : undefined;
  useEffect(() => {
    let cancelled = false;
    getHealth("stt").then(
      (health) => !cancelled && setSttServerHealth(health),
      () => !cancelled && setSttServerHealth(null),
    );
    return () => {
      cancelled = true;
    };
  }, [sttMode, serverInfo]);
  const askContext = useRef<AskContext | undefined>(undefined);
  const conversationRef = useRef<Conversation | null>(null);
  // 다시 듣기는 아래에서 만든다(폰 STT·서버 녹음 훅 뒤). 그 앞의 콜백들은 이 ref 로 부른다.
  const listenAgainRef = useRef<(conversation: Conversation) => Promise<void>>(async () => undefined);
  // 답을 읽기 직전에 끼어들기 듣기를 켠다(폰 STT 훅 뒤에서 만든다).
  const startBargeInRef = useRef<(conversation: Conversation) => Promise<void>>(async () => undefined);
  const player = useAudioPlayer();
  const playback = useAudioPlayerStatus(player);
  const serverRecorder = useServerRecorder();
  // 지금 읽는 답의 소리 조각들. 새 답·마이크·대화 멈춤 때 null 로 바꾸면 남은 조각은 만들지도 틀지도 않는다.
  const speechQueueRef = useRef<SpeechQueue | null>(null);
  const handledFinishRef = useRef<unknown>(null);
  // '다시 듣기'용: 마지막 답의 조각 주소들(조각을 받을 때마다 늘어난다).
  const lastSpeechUrlsRef = useRef<string[]>([]);
  const serverHealth = serverInfo.kind === "ok" ? serverInfo.health : null;
  const ttsChoices = ttsChoicesOf(serverHealth);
  const activeTts = activeTtsChoice(serverHealth, ttsChoice);
  const ttsEngineRef = useRef<string | undefined>(undefined);
  ttsEngineRef.current = activeTts.engine;
  // 고르기 버튼이 있는 서버에만 엔진을 보낸다(예전 서버는 늘 서버 기본).
  const ttsRequestEngineRef = useRef<string | undefined>(undefined);
  ttsRequestEngineRef.current = ttsChoices.length > 0 ? activeTts.engine : undefined;
  const ttsLabelRef = useRef("");
  ttsLabelRef.current = activeTts.label;
  // 미리보기(기록을 바꾸지 않는 답)를 아는 서버에만 말하는 중에 미리 묻는다. 모르는 서버에 미리 물으면 덜 끝난 말이 기록된다.
  const askPreviewRef = useRef(false);
  askPreviewRef.current = serverHealth?.askPreview === true;
  // 대화 모드: 말이 끝나기 전에 답과 첫 소리를 미리 만든다(2026-11-16 사용자: 실시간 대화는 속도가 먼저).
  const [prefetcher] = useState(() => createPrefetcher(
    async (text) => {
      const engine = ttsRequestEngineRef.current;
      const answer = await postAsk(text, askContext.current, undefined, engine, true);
      const firstPiece = speechPieces(answer.speechText, shouldSplitSpeech(ttsEngineRef.current))[0];
      const speech = await postTts(firstPiece, engine);
      return { speechText: answer.speechText, firstPiece, audioUrl: speech.fullAudioUrl };
    },
    // 앞 대화 상태나 TTS 가 바뀌면 같은 말이라도 답·소리가 다를 수 있다.
    () => JSON.stringify([askContext.current ?? null, ttsRequestEngineRef.current ?? null, ttsEngineRef.current ?? null]),
  ));

  /** 답 소리를 멈춘다(남은 조각 포함). 말하기를 시작할 때 부른다 — 앞 답 소리가 녹음에 섞이지 않게. */
  const stopSpeech = useCallback(() => {
    speechQueueRef.current = null;
    setReadingIndex(null);
    player.pause();
  }, [player]);

  const finishConversation = useCallback(() => {
    conversationRef.current = null;
    setConversationActive(false);
    setConversationPaused(false);
    setStage("idle");
  }, []);

  /** 대화 화면에서 한 턴이 끝났다: 규칙(nextConversationStep)대로 다시 듣거나, 잠깐 뒤 다시 듣거나, 쉰다. */
  const continueConversation = useCallback((conversation: Conversation, outcome: TurnOutcome) => {
    if (conversationRef.current !== conversation) return;
    const step = nextConversationStep(conversation.errors, outcome);
    conversation.errors = step.errors;
    if (step.action === "listen") {
      void listenAgainRef.current(conversation);
    } else if (step.action === "retry") {
      setStage("idle");
      setTimeout(() => {
        if (conversationRef.current === conversation) void listenAgainRef.current(conversation);
      }, RETRY_DELAY_MS);
    } else if (step.action === "pause") {
      setStage("idle");
      setConversationPaused(true);
    }
  }, []);

  /** 오류를 보여 준다. 대화 화면이면 닫지 않고 잠깐 뒤 다시 듣는다(연달아 나면 쉰다). */
  const fail = useCallback((message: string) => {
    setErrorMessage(message);
    const conversation = conversationRef.current;
    if (conversation) {
      conversation.awaitingPlayback = false;
      continueConversation(conversation, "error");
      return;
    }
    setStage("idle");
  }, [continueConversation]);

  /** 재생이 2초 안에 시작하지 않으면 한 번 다시 튼다. 그래도 안 되면 알리고 시험표 메모에 적는다.
   *  소리가 나기 시작했으면 true (그 시각을 '말 끝→소리' 시간으로 쓴다). */
  const ensurePlaying = useCallback(
    async (playId: number, fromVoice: boolean): Promise<boolean> => {
      const probe = () => ({ playing: player.playing, currentTime: player.currentTime });
      if (await waitUntilStarted(probe, FIRST_START_TIMEOUT_MS)) return true;
      if (playIdRef.current !== playId) return false;
      await setIsAudioActiveAsync(true).catch(() => undefined);
      await player.seekTo(0);
      player.play();
      if (await waitUntilStarted(probe)) {
        // 다시 틀어서야 났다: 고쳐졌는지 시험표에서 셀 수 있게 남긴다.
        if (fromVoice && playIdRef.current === playId) markPlaybackRetriedRef.current();
        return true;
      }
      if (playIdRef.current !== playId) return false;
      if (fromVoice) markPlaybackFailedRef.current();
      setNotice("음성을 받았는데 폰에서 재생이 시작되지 않았어요. '다시 듣기'를 눌러 보세요.");
      // 대화는 재생이 끝나야 다음 턴을 듣는데, 재생이 안 되면 끝남 신호가 오지 않으므로 여기서 다시 듣는다.
      const conversation = conversationRef.current;
      if (conversation?.awaitingPlayback) {
        conversation.awaitingPlayback = false;
        setErrorMessage("답 소리가 나지 않았어요. 다시 들을게요.");
        continueConversation(conversation, "error");
      }
      return false;
    },
    [continueConversation, player],
  );

  const answerAndSpeak = useCallback(
    /** startedAt: 말이 끝난 시각. 이때부터 답 소리가 나기 시작할 때까지를 '말 끝→소리'로 잰다. */
    async (
      text: string, startedAt: number, sttMs?: number, fromVoice = false, phoneTurn: PhoneTurn | null = null,
      interruptedAnswer: string | null = null,
    ): Promise<TurnOutcome> => {
      if (!text) return "empty";
      const conversation = conversationRef.current;
      const wasStopped = () => conversation !== null && conversationRef.current !== conversation;
      setCanReplay(false);
      setQuestion(text);
      // 말하는 중에 같은 글로 미리 만든 답·소리(대화 모드). 진짜 답은 아래에서 다시 물어 기록한다.
      const prefetched = conversation && fromVoice ? prefetcher.take(text) : null;
      try {
        setStage("asking");
        const askStarted = Date.now();
        // '나'(역할)는 보내지 않는다: 누가 했는지는 문장 속 남편·아내로 서버가 알아듣는다.
        // 이 턴 동안 쓸 TTS 를 먼저 정해 둔다(턴 중간에 버튼을 바꿔도 한 답은 한 목소리로).
        const turnTtsEngine = ttsRequestEngineRef.current;
        const turnTtsLabel = ttsLabelRef.current;
        const splitTurn = shouldSplitSpeech(ttsEngineRef.current);
        const answer = await postAsk(text, askContext.current, undefined, turnTtsEngine);
        if (wasStopped()) return "stopped";
        askContext.current = answer.context;
        // 끼어든 말의 답이 끊긴 답과 같으면 자기 답 소리를 다시 물은 것이다: 읽지도 적지도 않고 다시 듣는다.
        if (conversation && interruptedAnswer !== null && answer.answerText === interruptedAnswer) {
          setNotice(SELF_ECHO_NOTICE);
          return "empty";
        }
        const askMs = Date.now() - askStarted;
        setAnswerText(answer.answerText);
        setSpeechText(answer.speechText);
        // 시험표에는 말로 한 턴만 적는다(글로 묻기는 인식 시험이 아니다).
        // 대화 모드는 순서 없이 말하므로 한 말에 맞는 문장 칸을 찾아 적는다(2026-11-13 사용자 요청).
        let recorded = false;
        if (fromVoice && conversation) {
          const matched = recordMatchedTurnRef.current(
            text, answer.answerText, PHONE_STT_LABEL, phoneTurn, answer.correctedText ?? "", turnTtsLabel,
          );
          recorded = matched !== null;
          setNotice(matched ? `시험표 ${matched.id} 칸에 적었어요.` : "시험표에 없는 말이라 시험표에는 적지 않았어요.");
          setErrorMessage("");
          setChat((items) => addChat(items, [
            { who: "me", text, caseId: matched?.id ?? null },
            { who: "bot", text: answer.answerText },
          ]));
        } else if (fromVoice) {
          recordTurnRef.current(
            text, answer.answerText, sttLabelRef.current, phoneTurn, answer.correctedText ?? "", turnTtsLabel,
          );
          recorded = true;
        }

        setStage("speaking");
        const ttsStarted = Date.now();
        // 그때그때 만드는 TTS(107 등)는 문장으로 나눠 첫 문장부터 튼다. ttsMs 는 첫 조각까지 기다린 시간이다.
        const pieces = speechPieces(answer.speechText, splitTurn);
        // 미리 만든 답이 진짜 답과 같으면 그 첫 소리를 쓴다(아직 만드는 중이면 기다린다 — 새로 부르는 것보다 빠르다).
        const ready = prefetched ? await prefetched : null;
        if (wasStopped()) return "stopped";
        let reusedUrl = ready && ready.speechText === answer.speechText && ready.firstPiece === pieces[0] ? ready.audioUrl : null;
        if (reusedUrl && recorded) markPrefetchedRef.current();
        const queue: SpeechQueue = { audios: [], next: 1, urls: [] };
        speechQueueRef.current = queue;
        setReadingIndex(null);
        lastSpeechUrlsRef.current = queue.urls;
        queue.audios = fetchSequentially(
          pieces,
          (piece) => {
            if (reusedUrl === null) return postTts(piece, turnTtsEngine).then((speech) => speech.fullAudioUrl);
            const url = reusedUrl;
            reusedUrl = null;
            return Promise.resolve(url);
          },
          () => speechQueueRef.current === queue,
        ).map(quiet);
        let firstUrl: string;
        try {
          firstUrl = await queue.audios[0];
        } catch (error) {
          if (speechQueueRef.current === queue) speechQueueRef.current = null;
          if (error instanceof SpeechCancelledError) return "stopped";
          if (!(error instanceof NoRecordingError)) throw error;
          // 사전 녹음 TTS 에 이 답의 소리가 없다: 오류 대신 화면 답만 보여 주고 시험표에 '녹음 없음'을 적는다.
          if (wasStopped()) return "stopped";
          if (fromVoice) {
            markNoRecordingRef.current();
            recordTimingsRef.current({ askMs });
          }
          setNotice("이 답은 녹음이 없어 화면 답만 보여 줘요.");
          setTimings({ sttMs, askMs, totalMs: Date.now() - startedAt });
          // 대화 화면은 멈추지 않는다: 답은 말풍선으로만 보여 주고 바로 다시 듣는다(11/13 D13에서 대화가 끝났음).
          if (conversation) continueConversation(conversation, "answered");
          else setStage("idle");
          return "answered";
        }
        if (wasStopped()) return "stopped";
        const ttsMs = Date.now() - ttsStarted;
        // 대화 화면(iOS)은 답을 읽는 동안에도 듣는다(끼어들기): 녹음을 켠 채 스피커로 낸다.
        const bargeIn = conversation !== null && VOICE_BARGE_IN;
        await setAudioModeAsync({ allowsRecording: bargeIn, playsInSilentMode: true });
        // 폰 음성인식이 막 끝나 오디오 세션이 녹음용으로 남아 있을 수 있어, 재생용으로 다시 켠다.
        await setIsAudioActiveAsync(true);
        if (wasStopped() || speechQueueRef.current !== queue) return "stopped";
        if (conversation && bargeIn) {
          conversation.speakingText = `${answer.answerText} ${answer.speechText}`;
          conversation.speakingAnswer = answer.answerText;
          await startBargeInRef.current(conversation);
          if (wasStopped() || speechQueueRef.current !== queue) return "stopped";
        }
        queue.urls.push(firstUrl);
        player.replace({ uri: firstUrl });
        // 다 읽히기 전에 play 를 부르면 무시될 수 있다(13:51 시험에서 20/23턴).
        await waitUntilLoaded(() => player.isLoaded);
        if (wasStopped()) return "stopped";
        if (conversation) {
          conversation.errors = 0;
          conversation.awaitingPlayback = true;
        }
        player.play();
        void ensurePlaying(++playIdRef.current, fromVoice).then((started) => {
          if (started && fromVoice) recordTimingsRef.current({ askMs, ttsMs, replyMs: Date.now() - startedAt });
        });
        setTimings({ sttMs, askMs, ttsMs, totalMs: Date.now() - startedAt });
        setCanReplay(true);
        if (!conversation) setStage("idle");
        return "answered";
      } catch (error) {
        if (wasStopped()) return "stopped";
        fail(error instanceof Error ? error.message : String(error));
        return "error";
      }
    },
    [continueConversation, ensurePlaying, fail, player, prefetcher],
  );

  /** '대화 모드': 대화 화면을 열고 버튼 없이 바로 듣기 시작한다(2026-11-13 사용자 요청).
   *  시험표 순서는 따르지 않고 한 말에 맞는 칸에 적는다. 늘 폰 STT 로 듣는다(빠르게, 2026-11-16). */
  const startConversation = () => {
    if (stage !== "idle" || conversationRef.current) return;
    resetResult();
    stopSpeech();
    testSheet.setActiveId(null);
    setChat([]);
    setConversationPaused(false);
    const conversation: Conversation = { errors: 0, awaitingPlayback: false, bargeIn: "off", speakingText: "", speakingAnswer: "" };
    conversationRef.current = conversation;
    setConversationActive(true);
    void listenAgainRef.current(conversation);
  };

  /** 쉬는 중에 얼굴을 누르면 다시 듣는다. */
  const resumeConversation = () => {
    const conversation = conversationRef.current;
    if (!conversation) return;
    conversation.errors = 0;
    setConversationPaused(false);
    setErrorMessage("");
    void listenAgainRef.current(conversation);
  };

  /** 시험표의 '이 문장 말하기': 그 문장의 '나'로 바꾸고 바로 듣기 시작한다. 듣는 중에 다시 누르면 말하기 끝. */
  const chooseTestCase = (testCase: TestCase) => {
    if (stage === "listening" && testSheet.activeId === testCase.id) {
      void onMicPress();
      return;
    }
    if (stage !== "idle" || conversationRef.current) return;
    testSheet.setActiveId(testCase.id);
    void onMicPress();
  };

  /** 서버 시험 데이터와 시험표(○/×·인식한 말)를 함께 처음으로 되돌린다. 저장본은 그대로 남는다. */
  const resetEverything = async (message = "시험 데이터와 시험표를 처음으로 되돌렸어요.") => {
    setNotice("");
    try {
      await resetDemo();
      await testSheet.clearSheet(message);
      askContext.current = undefined;
      resetResult();
      setNotice(message);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  /** [저장하기]: 저장본을 남긴 뒤 바로 전부 초기화한다. 저장이 실패하면 아무것도 지우지 않는다. */
  const saveAndReset = async () => {
    const attempt = await testSheet.save();
    if (!attempt) return;
    await resetEverything(`저장했어요: ${describeAttempt(attempt)} — 처음부터 다시 시험하면 돼요.`);
  };

  const onResetDemo = () => {
    if (!testSheet.dirty) {
      void resetEverything();
      return;
    }
    Alert.alert("저장하지 않은 시험표가 있어요", "지금 시험표를 저장본으로 남기지 않고 지울까요?", [
      { text: "취소", style: "cancel" },
      // 저장이 실패하면 지우지 않는다(시험표가 날아가지 않게).
      { text: "저장하고 초기화", onPress: () => void saveAndReset() },
      { text: "저장하지 않고 초기화", style: "destructive", onPress: () => void resetEverything() },
    ]);
  };

  const resetResult = () => {
    setNotice("");
    setErrorMessage("");
    setQuestion("");
    setAnswerText("");
    setSpeechText("");
    setTimings({});
    setCanReplay(false);
  };

  const onPhoneFinished = async (transcript: string, turn: PhoneTurn) => {
    const conversation = conversationRef.current;
    const interrupted = conversation?.bargeIn === "taken" ? conversation : null;
    if (conversation) conversation.bargeIn = "off";
    // 끼어든 말이 대부분 읽던 답이면 폰이 자기 소리를 들은 것이다: 묻지 않고 다시 듣는다(2026-11-16 되풀이 막기).
    if (interrupted && isSelfEcho(transcript, interrupted.speakingText)) {
      setNotice(SELF_ECHO_NOTICE);
      continueConversation(interrupted, "empty");
      return;
    }
    // 말이 끝난 때부터 잰다(쉬는 시간을 기다린 몫도 사람이 느끼는 시간이라 넣는다).
    const outcome = await answerAndSpeak(
      transcript, turn.speechEndedAt ?? Date.now(), undefined, true, turn, interrupted?.speakingAnswer ?? null,
    );
    if (outcome !== "empty") return;
    if (!conversation) {
      fail("인식된 말이 없어요. 다시 말해 주세요.");
      return;
    }
    continueConversation(conversation, "empty");
  };

  const {
    liveTranscript, ready: phoneReady, start: startPhone, stop: stopPhone, cancel: cancelPhone, confirmBargeIn,
  } = usePhoneStt({
    silenceMs,
    // 시험표에 적힐 수 있는 턴만 들은 소리를 남긴다: 시험 중인 문장이 있거나('이 문장 말하기'는 문장을 고른 바로 뒤에
    // 듣기 시작한다), 대화 모드(한 말에 맞는 칸을 찾아 적는다. 맞는 칸이 없으면 소리도 붙지 않는다).
    persistAudio: () => testSheet.saveAudio && (testSheet.getActiveId() !== null || conversationRef.current !== null),
    onFinished: (transcript, turn) => void onPhoneFinished(transcript, turn),
    onError: fail,
    // 대화 모드에서 받아 적는 글: 멈추면 그 글로 답·소리를 미리 만든다.
    onTranscript: (text) => {
      if (conversationRef.current && askPreviewRef.current) prefetcher.heard(text);
    },
    // 답을 읽는 동안 들린 글: 읽는 답과 다른 말이면 끼어든 것이다.
    onHeard: (heard) => {
      const conversation = conversationRef.current;
      if (conversation?.bargeIn !== "armed" || !isBargeIn(heard, conversation.speakingText)) return;
      interruptRef.current(conversation, "voice");
    },
  });

  /** 대화에서 다음 말을 듣는다. 대화는 빠르게 답하려고 늘 폰 STT 로 듣는다(글자가 멈추면 턴이 끝난다, 2026-11-16). */
  const listenAgain = useCallback(async (conversation: Conversation) => {
    if (conversationRef.current !== conversation) return;
    prefetcher.reset();
    try {
      // 답을 읽는 동안 켜 둔 끼어들기 듣기가 남아 있으면 먼저 끝낸다(폰이 끝내야 새로 들을 수 있다).
      // 그동안 '말하세요'가 뜨지 않게 듣기 단계는 그 뒤에 바꾼다.
      if (conversation.bargeIn !== "off") {
        conversation.bargeIn = "off";
        await cancelPhone();
        if (conversationRef.current !== conversation) return;
      }
      setStage("listening");
      const started = await startPhone();
      if (!started && conversationRef.current === conversation) fail("듣기를 시작하지 못했어요.");
    } catch (error) {
      if (conversationRef.current === conversation) fail(error instanceof Error ? error.message : String(error));
    }
  }, [cancelPhone, fail, prefetcher, startPhone]);
  listenAgainRef.current = listenAgain;

  /** 답을 읽기 직전: 폰 STT 를 끼어들기 대기로 켠다. */
  const startBargeIn = useCallback(async (conversation: Conversation) => {
    try {
      const started = await startPhone({ bargeIn: true });
      conversation.bargeIn = started ? "armed" : "off";
    } catch {
      // 끼어들기를 못 켜도 답은 읽는다(얼굴을 눌러 끊을 수는 있다).
      conversation.bargeIn = "off";
    }
  }, [startPhone]);
  startBargeInRef.current = startBargeIn;

  /** 답을 읽는 중에 끊는다. voice: 말로 끼어듦(그 말을 이어 듣는다) / tap: 얼굴을 누름(새로 듣는다). */
  const interruptSpeech = useCallback((conversation: Conversation, how: "voice" | "tap") => {
    if (conversationRef.current !== conversation || !conversation.awaitingPlayback) return;
    conversation.awaitingPlayback = false;
    // 재생 확인(ensurePlaying)이 멈춘 답을 다시 틀지 않게 한다.
    playIdRef.current += 1;
    stopSpeech();
    markInterruptedRef.current(how);
    setNotice(how === "voice" ? "끼어든 말을 듣고 답을 멈췄어요." : "답을 멈췄어요. 말하세요.");
    if (how === "voice" && conversation.bargeIn === "armed" && confirmBargeIn()) {
      conversation.bargeIn = "taken";
      setStage("listening");
      return;
    }
    void listenAgain(conversation);
  }, [confirmBargeIn, listenAgain, stopSpeech]);
  const interruptRef = useRef(interruptSpeech);
  interruptRef.current = interruptSpeech;

  /** 답 소리를 끝까지 다 읽었다: 대화 모드면 다음 말을 듣는다. */
  const onSpeechFinished = useCallback(() => {
    const conversation = conversationRef.current;
    if (!conversation?.awaitingPlayback) return;
    conversation.awaitingPlayback = false;
    void listenAgain(conversation);
  }, [listenAgain]);

  /** 다음 조각을 기다렸다가 튼다. 그사이 멈췄으면(speechQueueRef 가 바뀜) 아무것도 하지 않는다. */
  const playNextChunk = useCallback(async (queue: SpeechQueue) => {
    const index = queue.next;
    queue.next += 1;
    let url: string;
    try {
      url = await queue.audios[index];
    } catch (error) {
      if (speechQueueRef.current !== queue) return;
      speechQueueRef.current = null;
      if (!(error instanceof SpeechCancelledError)) {
        setNotice(`답 뒷부분 소리를 만들지 못했어요: ${error instanceof Error ? error.message : String(error)}`);
      }
      if (queue.onChunk) {
        setReadingIndex(null);
        return;
      }
      onSpeechFinished();
      return;
    }
    if (speechQueueRef.current !== queue) return;
    queue.onChunk?.(index);
    queue.urls.push(url);
    player.replace({ uri: url });
    await waitUntilLoaded(() => player.isLoaded);
    if (speechQueueRef.current !== queue) return;
    player.play();
  }, [onSpeechFinished, player]);

  useEffect(() => {
    // 같은 '끝남' 상태로 이 효과가 다시 돌면 조각을 하나 건너뛰게 되므로 한 번만 처리한다.
    if (!playback.didJustFinish || handledFinishRef.current === playback) return;
    handledFinishRef.current = playback;
    const queue = speechQueueRef.current;
    if (queue && queue.next < queue.audios.length) {
      void playNextChunk(queue);
      return;
    }
    if (queue?.onChunk) {
      speechQueueRef.current = null;
      setReadingIndex(null);
      return;
    }
    onSpeechFinished();
  }, [onSpeechFinished, playNextChunk, playback]);

  /** 숫자 읽기 시험: 읽기 글들을 차례로 만들어 튼다(답 소리와 같은 길: 하나씩 만들고, 앞 것을 트는 동안 다음 것을 만든다). */
  const playReadings = useCallback(async (readings: string[], owner: "answers" | "numbers") => {
    if (readings.length === 0) return;
    stopSpeech();
    setReadingOwner(owner);
    setNotice("");
    const engine = ttsRequestEngineRef.current;
    const queue: SpeechQueue = { audios: [], next: 1, urls: [], onChunk: setReadingIndex };
    speechQueueRef.current = queue;
    queue.audios = fetchSequentially(
      readings,
      (reading) => postTts(reading, engine),
      () => speechQueueRef.current === queue,
    ).map((audio) => quiet(audio.then((speech) => speech.fullAudioUrl)));
    setReadingIndex(0);
    let firstUrl: string;
    try {
      firstUrl = await queue.audios[0];
    } catch (error) {
      if (speechQueueRef.current !== queue) return;
      speechQueueRef.current = null;
      setReadingIndex(null);
      if (!(error instanceof SpeechCancelledError)) {
        setNotice(`숫자 읽기 소리를 만들지 못했어요: ${error instanceof Error ? error.message : String(error)}`);
      }
      return;
    }
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    await setIsAudioActiveAsync(true);
    if (speechQueueRef.current !== queue) return;
    queue.urls.push(firstUrl);
    player.replace({ uri: firstUrl });
    await waitUntilLoaded(() => player.isLoaded);
    if (speechQueueRef.current === queue) player.play();
  }, [player, stopSpeech]);

  /** '다시 듣기': 조각이 여럿이면 처음 조각부터 차례로 다시 튼다. */
  const replaySpeech = useCallback(async () => {
    const urls = [...lastSpeechUrlsRef.current];
    if (urls.length <= 1) {
      player.seekTo(0);
      player.play();
      return;
    }
    const queue: SpeechQueue = { audios: urls.map((url) => Promise.resolve(url)), next: 1, urls: [] };
    speechQueueRef.current = queue;
    player.replace({ uri: urls[0] });
    await waitUntilLoaded(() => player.isLoaded);
    if (speechQueueRef.current === queue) player.play();
  }, [player]);

  const stopConversation = useCallback(() => {
    askContext.current = undefined;
    finishConversation();
    cancelPhone();
    prefetcher.reset();
    stopSpeech();
  }, [cancelPhone, finishConversation, prefetcher, stopSpeech]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "background" && conversationRef.current) stopConversation();
    });
    return () => subscription.remove();
  }, [stopConversation]);

  // 서버가 어떤 답 모드로 떠 있는지 보여 준다. 앱을 열 때·앱으로 돌아올 때·글자를 누를 때 다시 묻는다.
  const refreshServerInfo = useCallback(async () => {
    setServerInfo({ kind: "checking" });
    try {
      setServerInfo({ kind: "ok", health: await getHealth() });
    } catch (error) {
      setServerInfo({ kind: "error", message: error instanceof Error ? error.message : String(error) });
    }
  }, []);

  useEffect(() => {
    void refreshServerInfo();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void refreshServerInfo();
    });
    return () => subscription.remove();
  }, [refreshServerInfo]);

  /** 🎤 한 번 말하기(버튼 방식). 대화는 '대화 모드' 화면에서 한다. */
  const onMicPress = async () => {
    try {
      if (stage === "idle" && !conversationRef.current) {
        resetResult();
        setStage("listening");
        // 앞 답 소리를 먼저 멈춘다. 서버 STT 모드에서 멈추지 않아 앞 답이 녹음에 섞였다(11/09 D18·D21).
        stopSpeech();
        if (sttMode === "phone") {
          if (!(await startPhone())) setStage("idle");
        } else {
          await serverRecorder.start();
        }
        return;
      }
      if (stage !== "listening") {
        return;
      }
      if (sttMode === "phone") {
        stopPhone();
        return;
      }
      const stoppedAt = Date.now();
      const uri = await serverRecorder.stop();
      setStage("transcribing");
      const sttStarted = Date.now();
      const recognized = await postStt(uri, serverSttEngine);
      if (await answerAndSpeak(recognized.text, stoppedAt, Date.now() - sttStarted, true) === "empty") {
        fail("인식된 말이 없어요. 다시 말해 주세요.");
      }
    } catch (error) {
      fail(error instanceof Error ? error.message : String(error));
    }
  };

  const onTypedAsk = () => {
    resetResult();
    void answerAndSpeak(typedQuestion.trim(), Date.now(), undefined);
  };

  const isBusy = stage !== "idle" && stage !== "listening";
  const liveText = (sttMode === "phone" || conversationActive) && stage === "listening" ? liveTranscript : "";
  // STT 버튼: 폰 기본 STT + 서버 STT 고르기 목록(예전 서버는 '서버 Qwen3-ASR' 하나).
  const activeServerStt = serverSttEngine ?? sttChoices[0]?.engine;
  const sttButtons: { key: string; mode: SttMode; engine?: string; label: string; active: boolean }[] = [
    { key: "phone", mode: "phone", label: STT_MODE_LABELS.phone, active: sttMode === "phone" },
    ...(sttChoices.length > 0
      ? sttChoices.map((choice) => ({
        key: `server-${choice.engine}`, mode: "server" as const, engine: choice.engine,
        label: sttButtonLabel(choice.engine), active: sttMode === "server" && activeServerStt === choice.engine,
      }))
      : [{ key: "server", mode: "server" as const, label: STT_MODE_LABELS.server, active: sttMode === "server" }]),
  ];

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />
      {/* 시험표(1번째 자식)가 보이는 동안은 그 위치를 지킨다: '이 문장 말하기'를 누르면 위쪽 칸(시험 중 띠·듣는 중·
          인식한 말·답·걸린 시간)이 커졌다 작아졌다 해서 보던 카드가 밀렸다(2026-11-12 사용자 제보).
          그래서 위쪽은 View 하나(0번째)로 묶어 자식 번호가 바뀌지 않게 한다. 맨 위를 볼 때는 평소처럼 움직인다. */}
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        maintainVisibleContentPosition={{ minIndexForVisible: 1 }}
      >
        <View style={styles.top}>
          <Text style={styles.title}>STT-TTS 시험</Text>
          <Text style={styles.meta}>STT 서버: {sttServerUrl ?? "설정 안 됨"}</Text>
          <Text style={styles.meta}>답·TTS 서버: {ttsServerUrl ?? "설정 안 됨"}</Text>
          <Pressable accessibilityRole="button" accessibilityHint="눌러서 서버 상태를 다시 확인" onPress={() => void refreshServerInfo()}>
            <Text style={[styles.serverInfo, serverInfo.kind === "error" && styles.error]}>
              {describeServerInfo(serverInfo)} ↻
            </Text>
          </Pressable>

          <View style={styles.modeRow}>
            <Pressable
              accessibilityRole="button"
              disabled={stage !== "idle"}
              onPress={onResetDemo}
              style={[styles.modeButton, stage !== "idle" && styles.disabled]}
            >
              <Text style={styles.modeText}>시험 데이터 초기화</Text>
            </Pressable>
          </View>
          {notice ? <Text style={styles.meta}>{notice}</Text> : null}

          <View style={styles.modeRow}>
            {sttButtons.map((button) => (
              <Pressable
                key={button.key}
                accessibilityRole="button"
                accessibilityState={{ selected: button.active, disabled: stage !== "idle" }}
                disabled={stage !== "idle"}
                onPress={() => {
                  setSttMode(button.mode);
                  if (button.engine) setServerStt(button.engine);
                }}
                style={[styles.modeButton, button.active && styles.modeButtonActive]}
              >
                <Text style={[styles.modeText, button.active && styles.modeTextActive]}>{button.label}</Text>
              </Pressable>
            ))}
          </View>

          {ttsChoices.length > 1 ? (
            <View style={styles.modeRow}>
              {ttsChoices.map((choice) => (
                <Pressable
                  key={choice.engine}
                  accessibilityRole="button"
                  accessibilityState={{ selected: activeTts.engine === choice.engine, disabled: stage !== "idle" }}
                  disabled={stage !== "idle"}
                  onPress={() => setTtsChoice(choice.engine)}
                  style={[styles.modeButton, activeTts.engine === choice.engine && styles.modeButtonActive]}
                >
                  <Text style={[styles.modeText, activeTts.engine === choice.engine && styles.modeTextActive]}>
                    TTS {ttsButtonLabel(choice.engine)}
                  </Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          <View>
            <Pressable
              accessibilityRole="button"
              disabled={stage !== "idle"}
              onPress={startConversation}
              style={[styles.conversationButton, stage !== "idle" && styles.disabled]}
            >
              <Text style={styles.conversationButtonText}>💬 대화 모드</Text>
            </Pressable>
            <Text style={styles.meta}>
              누르면 대화 화면으로 바뀌고 바로 들어요. 빠르게 답하려고 위 STT 고르기와 상관없이 폰 기본 STT로 들어요. 시험표 문장을 순서 없이 말하면 맞는 칸에 적혀요.
            </Text>
            <Text style={styles.meta}>말이 끝났다고 보는 쉬는 시간</Text>
            <View style={styles.modeRow}>
              {SILENCE_OPTIONS_MS.map((ms) => (
                <Pressable
                  key={ms}
                  accessibilityRole="button"
                  accessibilityState={{ selected: ms === silenceMs, disabled: stage !== "idle" }}
                  disabled={stage !== "idle"}
                  onPress={() => setSilenceMs(ms)}
                  style={[styles.modeButton, ms === silenceMs && styles.modeButtonActive]}
                >
                  <Text style={[styles.modeText, ms === silenceMs && styles.modeTextActive]}>
                    {formatSilenceLabel(ms)}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>

          {testSheet.activeCase ? (
            <View style={styles.testBanner}>
              <Text style={styles.testBannerText}>
                시험 중 {testSheet.activeCase.id} — “{testSheet.activeCase.say}”
              </Text>
              <Pressable accessibilityRole="button" onPress={() => testSheet.setActiveId(null)} style={styles.testBannerStop}>
                <Text style={styles.testBannerStopText}>그만</Text>
              </Pressable>
            </View>
          ) : null}

          <Pressable
            disabled={isBusy && !conversationActive}
            onPress={conversationActive ? stopConversation : () => void onMicPress()}
            style={[styles.micButton, (conversationActive || stage === "listening") && styles.micButtonActive, isBusy && !conversationActive && styles.disabled]}
          >
            <Text style={styles.micText}>{conversationActive ? "■ 대화 끝내기" : stage === "listening" ? "■ 말하기 끝" : "🎤 말하기"}</Text>
          </Pressable>
          <Text style={styles.stage}>
            {stage === "listening" && sttMode === "phone"
              ? "듣는 중… 말을 멈추면 자동으로 질문해요"
              : STAGE_LABELS[stage]}
          </Text>
          {liveText ? <Text style={styles.live}>{liveText}</Text> : null}

          <View style={styles.typedRow}>
            <TextInput
              value={typedQuestion}
              onChangeText={setTypedQuestion}
              placeholder="글로 바로 묻기 (STT 없이 시험)"
              style={styles.input}
            />
            <Pressable disabled={stage !== "idle" || !typedQuestion.trim()} onPress={onTypedAsk} style={styles.askButton}>
              <Text style={styles.askText}>묻기</Text>
            </Pressable>
          </View>

          {errorMessage ? <Text style={styles.error}>{errorMessage}</Text> : null}
          <ResultBlock label="인식한 말" value={question} />
          <ResultBlock label="답 (화면용)" value={answerText} />
          <ResultBlock label="답 (읽기용)" value={speechText} />
          <ResultBlock
            label="걸린 시간"
            value={
              timings.totalMs === undefined
                ? ""
                : [
                    timings.sttMs !== undefined ? `STT ${timings.sttMs}ms` : null,
                    `답 ${timings.askMs}ms`,
                    `TTS ${timings.ttsMs}ms`,
                    `합계 ${timings.totalMs}ms`,
                  ]
                    .filter(Boolean)
                    .join(" · ")
            }
          />
          {canReplay && stage === "idle" ? (
            <Pressable
              onPress={() => void replaySpeech()}
              style={styles.replayButton}
            >
              <Text style={styles.askText}>▶ 다시 듣기</Text>
            </Pressable>
          ) : null}
        </View>

        <TestSheetPanel
          sheet={testSheet}
          stage={stage === "listening" ? "listening" : stage === "idle" && !conversationActive ? "idle" : "busy"}
          liveText={liveText}
          sttLabel={sttLabel}
          ttsIsMock={activeTts.engine === "mock"}
          onChoose={chooseTestCase}
          onSave={() => void saveAndReset()}
        />
        <AnswerListenPanel
          ttsEngine={activeTts.engine}
          ttsLabel={activeTts.label}
          busy={stage !== "idle" || conversationActive}
          playingIndex={readingOwner === "answers" ? readingIndex : null}
          onPlay={(readings) => void playReadings(readings, "answers")}
          onStop={stopSpeech}
        />
        <NumberReadingPanel
          device={testSheet.device}
          ttsEngine={activeTts.engine}
          ttsLabel={activeTts.label}
          busy={stage !== "idle" || conversationActive}
          playingIndex={readingOwner === "numbers" ? readingIndex : null}
          onPlay={(readings) => void playReadings(readings, "numbers")}
          onStop={stopSpeech}
        />
      </ScrollView>
      {/* 대화 화면: 아래 화면(시험표 접힘 등)은 그대로 둔 채 위에 띄운다. */}
      <Modal visible={conversationActive} animationType="slide" onRequestClose={stopConversation}>
        <SafeAreaView style={styles.screen}>
          <ConversationScreen
            face={conversationFace(stage, phoneReady, conversationPaused)}
            liveText={liveText}
            chat={chat}
            cases={testSheet.cases}
            results={testSheet.results}
            sttLabel={PHONE_STT_LABEL}
            ttsLabel={activeTts.label}
            errorMessage={errorMessage}
            onEnd={stopConversation}
            onResume={resumeConversation}
            onInterrupt={() => {
              const conversation = conversationRef.current;
              if (conversation) interruptSpeech(conversation, "tap");
            }}
          />
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

function ResultBlock({ label, value }: { label: string; value: string }) {
  if (!value) {
    return null;
  }
  return (
    <View style={styles.block}>
      <Text style={styles.blockLabel}>{label}</Text>
      <Text style={styles.blockValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F7F8FA" },
  content: { padding: 20, gap: 12 },
  top: { gap: 12 },
  title: { fontSize: 24, fontWeight: "700", color: "#111" },
  meta: { fontSize: 12, color: "#666" },
  serverInfo: { fontSize: 13, fontWeight: "600", color: "#1F4FD8" },
  testBanner: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 10, backgroundColor: "#E6EDFB" },
  testBannerText: { flex: 1, fontSize: 14, color: "#1F4FD8", fontWeight: "600" },
  testBannerStop: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: "#1F4FD8" },
  testBannerStopText: { fontSize: 13, color: "#1F4FD8" },
  modeRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
  modeButton: { flex: 1, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: "#CCD", alignItems: "center" },
  modeButtonActive: { backgroundColor: "#1F4FD8", borderColor: "#1F4FD8" },
  modeText: { fontSize: 14, color: "#333" },
  modeTextActive: { color: "#FFF", fontWeight: "700" },
  micButton: { marginTop: 8, paddingVertical: 28, borderRadius: 16, backgroundColor: "#1F4FD8", alignItems: "center" },
  micButtonActive: { backgroundColor: "#D83A1F" },
  micText: { fontSize: 22, fontWeight: "700", color: "#FFF" },
  disabled: { opacity: 0.5 },
  conversationButton: { paddingVertical: 16, borderRadius: 12, backgroundColor: "#1D7A46", alignItems: "center" },
  conversationButtonText: { fontSize: 18, fontWeight: "700", color: "#FFF" },
  stage: { textAlign: "center", color: "#444" },
  live: { textAlign: "center", fontSize: 18, color: "#111" },
  typedRow: { flexDirection: "row", gap: 8 },
  input: { flex: 1, borderWidth: 1, borderColor: "#CCD", borderRadius: 10, paddingHorizontal: 12, backgroundColor: "#FFF" },
  askButton: { paddingHorizontal: 16, justifyContent: "center", borderRadius: 10, backgroundColor: "#333" },
  askText: { color: "#FFF", fontWeight: "700" },
  error: { color: "#C0281A" },
  block: { backgroundColor: "#FFF", borderRadius: 10, padding: 12, gap: 4 },
  blockLabel: { fontSize: 12, color: "#777" },
  blockValue: { fontSize: 16, color: "#111" },
  replayButton: { alignSelf: "flex-start", paddingVertical: 10, paddingHorizontal: 16, borderRadius: 10, backgroundColor: "#333" },
});
