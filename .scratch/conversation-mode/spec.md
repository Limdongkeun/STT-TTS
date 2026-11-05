# 스펙: 폰 기본 STT 대화 모드 (자동 반복 + 쉬는 시간 설정)

- 작성: Claude, 2026-11-04 14:55 KST
- 맡을 쪽: **Codex** (사용자 요청: "직접 하지 말고 Codex에게 전달")
- 사용자 승인: 아래 계획에 사용자가 `계속`으로 동의함(2026-11-04 14:50). 구현만 Codex로 넘긴다.
- 작업 규칙: `AGENTS.md` → `docs/WORKBOARD.md`. 코딩 규칙은 Teddy Core Policy(`/Users/teddy/Desktop/UPTIVE/LLM-코딩/core_instructions.md` + `packs/`). 커밋은 사용자가 요청할 때만 한다.

## 배경

1단계(연결 확인)는 아이폰 14 Pro 실기기에서 통과했다(2026-11-04 14:24 스크린샷). 폰 기본 STT가 "가나다라마바사아자차카타파하"를 인식했고, 고정 답, 읽기용 변환, mock TTS까지 이어졌다(답 54ms · TTS 22ms · 합계 219ms).

지금 앱은 버튼 방식이다. 🎤를 누르면 듣고, 다시 누르거나 OS가 말 끝을 정하면 한 번 답하고 끝난다. 사용자는 대화처럼 계속 주고받기를 원한다.

## 목표

**폰 기본 STT 모드**에서 다음을 지원한다.
1. **대화 모드 켜기/끄기**: 켜면 "듣기 → 답 찾기 → 답 읽기 → 재생이 끝나면 다시 듣기"를 자동으로 반복한다. 처음 한 번만 누른다.
2. **쉬는 시간 설정**: 말이 끝났다고 볼 쉬는 시간을 화면에서 고른다. 후보는 0.8 / 1.2(기본) / 1.5 / 2 / 3초다. 부모님처럼 천천히 말하는 분은 길게 둔다.

대화 모드를 끄면 지금의 버튼 방식 그대로이되, 쉬는 시간 설정은 똑같이 적용한다.

## 범위 밖

- 서버 Qwen3-ASR 모드: 지금처럼 버튼 방식으로 둔다. 서버 VAD는 6단계다.
- 상시 듣기(화면 꺼짐·백그라운드), 호출어, 끼어들기(barge-in), 자동 전화
- 새 패키지 추가: 하지 않는다. 그래서 쉬는 시간 설정은 저장하지 않고, 앱을 다시 켜면 기본값으로 돌아간다.
- 네이티브 설정(`app.json`, 플러그인) 변경: 없다. JS만 바뀌므로 다시 빌드할 필요 없이 Metro 새로고침으로 반영된다.

## 확인한 API 사실 (설치된 패키지 타입·README 기준, SDK 58)

- `expo-speech-recognition` (`app/node_modules/expo-speech-recognition/build/ExpoSpeechRecognitionModule.types.d.ts`)
  - `continuous: false`일 때: iOS 17 이하는 3초 동안 말이 없으면 끝나고, **iOS 18 이상과 안드로이드는 `isFinal: true` 결과가 오면 끝난다.** 쉬는 시간을 우리가 정할 수 없다.
  - 그래서 **`continuous: true`로 듣고, 새 결과가 안 들어온 지 N ms가 지나면 앱이 `ExpoSpeechRecognitionModule.stop()`을 부른다.**
  - 안드로이드 연속 인식은 13 이상에서만 된다(README 표). 시험은 아이폰으로만 한다.
  - result 이벤트 모양: `{ isFinal: boolean; results: { transcript, ... }[] }`. iOS 중간 결과는 누적된 전체 글이고, 안드로이드 연속 모드는 확정 구간이 따로 온다고 가정했다. `appendResult`가 두 경우를 다 처리한다.
  - error 코드에 `"no-speech"`, `"aborted"`가 있다. `no-speech`는 오류가 아니라 **빈 턴**으로 다룬다.
  - `iosVoiceProcessingEnabled`(에코 제거)도 있다. 이번에는 쓰지 않는다. 끼어들기 작업 때 쓴다.
- `expo-audio`: `useAudioPlayerStatus(player)`가 `AudioStatus`를 돌려주고, 그 안에 `didJustFinish: boolean`이 있다(`app/node_modules/expo-audio/build/Audio.types.d.ts`). 재생이 끝난 순간을 여기서 잡는다.

## 이미 만들어 둔 것 (Claude, 테스트 통과)

`app/src/conversation.ts`와 `app/src/conversation.test.ts`가 있다. 아직 커밋 안 됐다. 순수 함수이고, 그대로 써도 되고 고쳐도 된다.

| 이름 | 하는 일 |
|---|---|
| `SILENCE_OPTIONS_MS`, `DEFAULT_SILENCE_MS`(1200), `NO_SPEECH_TIMEOUT_MS`(8000), `MAX_EMPTY_TURNS`(2) | 상수 |
| `decideNextTurn(enabled, emptyTurns, outcome)` | 한 턴이 끝난 뒤 다시 들을지 정한다. outcome은 `"answered"` / `"empty"` / `"error"` / `"stopped"` |
| `appendResult(state, transcript, isFinal)` / `transcriptText(state)` / `EMPTY_TRANSCRIPT` | 연속 인식 결과 모으기 |
| `createSilenceTimer(getSilenceMs, onTimeout, noSpeechMs?, timers?)` | `start()`는 8초 동안 말이 없는지 재고, `bump()`는 쉬는 시간을 처음부터 다시 잰다. `cancel()`. onTimeout은 한 번만 부른다. reason은 `"silence"` / `"noSpeech"` |
| `formatSilenceLabel(ms)` | `1200` → `"1.2초"` |

검증: `cd app && npm test` → 14개 통과(기존 4 + 새 10). 2026-11-04 14:51 Claude.

## 동작 규칙

- 듣기 시작 → `timer.start()`(8초 동안 말이 없으면 그 턴을 끝냄) → 결과가 올 때마다 `timer.bump()` → 쉬는 시간이 지나면 `stop()` → end 이벤트에서 모은 글로 턴을 끝낸다.
- 글이 있으면 `/ask` → `/tts` → 재생한다. 재생 전에 `setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true })`를 지금처럼 부른다.
- **답을 읽는 동안에는 마이크를 켜지 않는다.** 앱 목소리를 다시 듣지 않게 하려는 것이다.
- 대화 모드가 켜져 있으면 `didJustFinish`가 오는 순간 다시 듣는다.
- 멈추는 조건:
  - "대화 끝내기" 버튼: 언제든 누를 수 있다. 듣는 중이면 STT를 멈추고, 재생 중이면 player를 멈추고, idle로 돌아간다.
  - 오류(네트워크·서버·권한)
  - 빈 턴이 `MAX_EMPTY_TURNS`(2)번 연달아 나올 때. "말이 없어서 대화를 멈췄어요" 같은 안내를 띄운다.
- 시간 측정은 지금 규칙을 따른다. 폰 STT는 인식이 끝난 순간부터 잰다.

## 완료 기준

- [ ] 폰 기본 STT + 대화 모드 켬: 🎤 한 번 → 말하기 → 쉬는 시간 뒤에 자동으로 답과 '삐' → 다시 듣기, 최소 3번 반복
- [ ] 쉬는 시간 0.8초와 3초를 바꿔 가며 끝나는 시점이 달라지는 것을 확인
- [ ] 말 없이 두 턴(각 8초)이 지나면 대화가 멈추고 안내가 보임
- [ ] 대화 끝내기: 듣는 중과 재생 중 둘 다 바로 멈춤
- [ ] 대화 모드 끔: 지금 버튼 방식과 같게 동작(쉬는 시간 설정은 적용)
- [ ] 서버 Qwen3-ASR 모드: 동작이 바뀌지 않음
- [ ] `npm test`와 `npm run typecheck` 통과
- [ ] 실기기 확인은 사용자가 한다. 결과는 issue 파일 `## Comments`와 작업판에 적는다.

## 이슈

- `issues/01-phone-stt-continuous-silence.md`
- `issues/02-conversation-loop-ui.md`
- `issues/03-step1-results-record.md`
