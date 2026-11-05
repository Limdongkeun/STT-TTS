# 02 대화 모드 반복 + 화면

Status: ready-for-human
Blocked by: (없음 — 01 구현 완료, 실기기 검증 함께 진행)
Spec: `.scratch/conversation-mode/spec.md`

## 할 일

`app/App.tsx`를 고친다. 커지면 훅으로 빼도 된다(예: `src/useConversation.ts`).

1. 상태를 더한다. `conversationMode`(기본 false), `silenceMs`(기본 `DEFAULT_SILENCE_MS`), 빈 턴 수, 대화 진행 중 표시(ref).
2. 화면
   - "대화 모드" 켜기/끄기. 폰 기본 STT일 때만 켤 수 있다.
   - 쉬는 시간 버튼: `SILENCE_OPTIONS_MS`, 라벨은 `formatSilenceLabel`
   - 대화가 진행 중이면 "■ 대화 끝내기" 버튼. 어느 단계(asking·speaking 포함)에서든 누를 수 있다.
3. 턴 흐름
   - `answerAndSpeak`는 결과(`TurnOutcome`)를 알 수 있게 한다.
   - 빈 글이면 `"empty"`, 성공해서 재생을 시작하면 `"answered"`, 예외가 나면 `"error"`
   - `decideNextTurn`으로 다음을 정한다. 빈 턴으로 멈추면 안내 문구를 띄운다.
4. 재생 끝 감지
   - `useAudioPlayerStatus(player)`의 `didJustFinish`가 오고, "다시 들을 예정" 표시가 켜져 있으면 듣기를 다시 시작한다(`phoneStt.start()`, stage `"listening"`).
   - 대화 중에는 재생이 끝날 때까지 stage를 `"speaking"`으로 둔다. 대화 모드가 꺼져 있으면 지금처럼 재생을 시작하고 바로 idle로 둔다.
5. 대화 끝내기: 진행 중 표시와 다시 들을 예정 표시를 끈다. 듣는 중이면 `phoneStt.stop()`, 재생 중이면 `player.pause()`. stage는 `"idle"`
6. 서버 Qwen3-ASR 모드의 흐름은 건드리지 않는다.

## 검증

- `cd app && npm test && npm run typecheck`
- 실기기 시험은 사용자에게 부탁한다. 순서는 spec의 "완료 기준". 앱은 Metro 새로고침만 하면 된다(다시 빌드할 필요 없음).

## Comments

- 2026-11-04 15:01 KST · Codex · 폰 STT 대화 모드, 쉬는 시간 선택, 재생 완료 후 다음 턴, 빈 턴 2회 및 수동 종료를 구현했다. 앱 테스트 14개 및 타입 검사 통과. iPhone 실기기 검증은 스펙 완료 기준에 따라 진행한다.
