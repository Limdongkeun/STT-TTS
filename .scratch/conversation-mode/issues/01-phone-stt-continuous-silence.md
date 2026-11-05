# 01 폰 STT: 연속 인식 + 쉬는 시간으로 끝내기

Status: ready-for-human
Blocked by: (없음)
Spec: `.scratch/conversation-mode/spec.md`

## 할 일

`app/src/usePhoneStt.ts`를 고친다.

1. 옵션에 쉬는 시간을 받는다. 예: `silenceMs: number`. 타이머가 바뀐 값을 바로 쓰도록 ref로 둔다.
2. `ExpoSpeechRecognitionModule.start({...})`에 `continuous: true`를 넣는다. 기존 `lang: "ko-KR"`, `interimResults`, `addsPunctuation`, `contextualStrings`는 그대로 둔다.
3. `createSilenceTimer`(`src/conversation.ts`)를 쓴다.
   - "start" 이벤트에서 `timer.start()`
   - "result" 이벤트마다 `appendResult`로 모으고 `timer.bump()`. `liveTranscript`는 `transcriptText(state)`로 보여 준다.
   - onTimeout이 오면 `ExpoSpeechRecognitionModule.stop()`
   - "end" 이벤트에서 `timer.cancel()`, 그다음 `onFinished(transcriptText(state))`
4. error 이벤트에서 `no-speech`는 빈 턴으로 다룬다(`onFinished("")`). 그 밖의 오류는 지금처럼 `onError`. 어느 경우든 타이머를 취소한다.
5. 경합 막기(작업판 점검 후보 3): 듣는 중임을 ref로 표시한다. 듣는 중이면 start를 무시하고, 안 듣는 중이면 stop을 무시한다. 한 세션에서 onFinished는 한 번만 부른다.
6. 언마운트할 때 타이머를 취소한다.

## 검증

- `cd app && npm test && npm run typecheck`
- 훅 자체는 유닛 테스트하기 어렵다. 판단 로직은 `conversation.ts`에 두고 테스트를 거기에 더한다.

## Comments

- 2026-11-04 15:01 KST · Codex · 연속 인식과 쉬는 시간 타이머를 연결했다. 권한 요청 및 네이티브 종료 중 중복 시작을 막고, 취소한 세션 결과를 무시한다. 앱 테스트 14개 및 타입 검사 통과. iPhone에서 0.8초/3초와 무음 종료를 확인할 차례다.
