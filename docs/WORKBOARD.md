# 공유 작업판 (Claude · Codex)

Claude와 Codex가 이 파일 하나로 일을 이어받는다. 규칙은 `AGENTS.md`의 "공유 작업판" 절을 따른다.

- **시작 전**: 이 파일을 끝까지 읽는다. 특히 "진행 중"과 최근 "작업 기록"을 본다.
- **작업을 잡을 때**: "진행 중"에 `누가 · 무엇 · 시작 시각 · 건드리는 파일`을 적는다. 다른 쪽이 잡은 파일은 건드리지 않는다.
- **끝나면**: "진행 중"에서 그 줄을 지운다. "작업 기록" 맨 위에 한 줄을 더하고, 바뀐 상태가 있으면 다른 칸도 고친다.
- 시각은 KST, 날짜는 `YYYY-MM-DD`로 적는다. 비밀값(키·토큰·주소 비밀번호)은 적지 않는다.

## 지금 목표

iPhone 14 Pro에서 [폰 STT 대화 모드](../.scratch/conversation-mode/spec.md)를 확인한다. 이후 2단계에서 A1~A15를 기록한다.

## 진행 중

| 누가 | 무엇 | 시작 | 건드리는 파일 |
|---|---|---|---|
| (없음) | | | |

## 다음 할 일

- [ ] 가족 비서 시작 방식 검토 ([A안·B안 비교](../.scratch/family-onboarding/spec.md))
- [x] 대화 모드 이슈 01·02 구현 및 03 결과 기록
- [ ] 대화 모드 실기기 검증: 3턴 반복, 쉬는 시간 0.8초/3초, 무음 2턴, 듣기·재생 중 종료, 단발 및 서버 모드 확인

- [x] 1단계: iPhone 14 Pro에서 mock 서버 연결, 고정 답과 ‘삐’ 소리 확인 ([결과](../results/2026-11-04-단계1.md))
- [ ] 2단계: 폰 기본 STT로 `docs/test-sentences.md`의 A 문장 기록
- [ ] iOS·Android에서 가족 돌봄 대화 C1~C7을 말하고 받아쓰기와 응답을 따로 기록 ([시험 계획](test-plan.md#2단계-추가-시험--가족-돌봄-대화))
- [ ] 3단계: Qwen3-TTS Sohee (1.7B / 0.6B 비교)
- [ ] 4단계: Qwen3-ASR (8001) — 폰 STT와 CER·속도 비교
- [ ] 5단계: `server/app/answers.py`에 기존 LLM·DB 연결
- [ ] 점검 후보 1: TTS가 실패하면 "다시 듣기"가 이전 답 음성을 튼다 (`app/App.tsx` answerAndSpeak — TTS 전에 setSpeechText를 한다)
- [ ] 점검 후보 2: ffmpeg 60초 TimeoutExpired를 잡지 않아서 500으로 나간다 (`server/app/audio.py` to_wav16k)
- [ ] 점검 후보 3: 폰 STT를 연속으로 탭하면 end 이벤트와 경합할 수 있다 (`app/App.tsx` onMicPress, `app/src/usePhoneStt.ts`)

## 정한 것

- 실제 STT 서버는 8001(`--extra asr`), 답+TTS 서버는 8002(`--extra tts`)로 나눈다. qwen-asr와 qwen-tts가 서로 다른 transformers 버전을 쓰기 때문이다. mock만 쓸 때는 8002 하나로 된다.
- 코딩 규칙은 Teddy Core Policy(`/Users/teddy/Desktop/UPTIVE/LLM-코딩/core_instructions.md` + `packs/`)를 따른다.
- 커밋은 사용자가 요청할 때만 한다.
- 이슈·스펙은 `.scratch/<기능>/`에 마크다운으로 둔다(GitHub Issues는 안 씀). 상태 라벨은 기본 5개를 쓴다. 이 작업판은 "누가 무엇을 하는지", `.scratch`는 "이슈 내용"을 맡는다. 자세한 건 `docs/agents/`에 있다.

## 검증 기준선

| 항목 | 결과 | 확인 |
|---|---|---|
| server pytest | 73개 통과 | 2026-11-04 Codex |
| app `npm test` / `npm run typecheck` | 14개 통과 / 통과 | 2026-11-04 Codex |
| app 린트 | ESLint 설정 없음, 못 돌림 | 2026-11-04 Claude |

## 작업 기록 (최신이 위)

| 날짜 시각 | 누가 | 한 일 | 검증 |
|---|---|---|---|
| 2026-11-05 10:14 | Claude | ba2e256에서 빠진 앱 변경(대화 모드, `/ask` context 주고받기, package.json 스크립트)을 커밋함 | server 73개 · app 14개 · tsc 통과 |
| 2026-11-04 17:55 | Codex | ProjectWatch 제공 원문과 공개 자료를 대조해 가족 AI 사업성·전략·시장 동향 정리 | PPTX 2종·DOCX 1종 렌더링 확인 |
| 2026-11-04 17:43 | Codex | Q4 확정 반영 및 가족 비서 시작 흐름 PDF 제작 | PDF 2쪽 한글·표 렌더링 확인 |
| 2026-11-04 17:40 | Codex | B안에 제한된 일반 질문과 첫 일정에서 초대로 이어지는 흐름 추가 | 검토 초안 |
| 2026-11-04 17:35 | Codex | 가족 합류 후 시작과 첫 기록 체험 후 합류 흐름을 정리하고 가족 공간·개인 대화 용어 정의 | 검토 초안 |
| 2026-11-04 16:00 | Claude | 음성 모델 정리 `docs/voice-models.md` 작성(STT 표·TTS 비교표·음성 LLM, 공식 모델 카드 기준). handoff에 링크 추가. 바뀐 점: Supertonic 3·Kokoro 제외, CosyVoice3 "academic purposes only" 문구 확인 필요, Qwen3-TTS 공개 패키지 스트리밍 없음, TeamUNIVA 후속판 CER 4.83% | 문서만 바꿈 |
| 2026-11-04 16:55 | Codex | 가족 돌봄 시험 답변과 복용 시각 후속 대화·정정 구현 | 서버 73개·앱 14개·타입 검사 통과, 실기기 시험 대기 |
| 2026-11-04 15:01 | Codex | 대화 모드 01·02 구현, 03 결과 기록 및 1단계 통과 반영 | npm test 14개·타입 검사 통과, 새 대화 모드 실기기 검증 대기 |
| 2026-11-04 14:56 | Claude | 1단계가 실기기에서 통과한 것을 확인(스크린샷: 폰 STT 인식, 고정 답, 합계 219ms). 대화 모드 순수 로직 `app/src/conversation.ts` + 테스트를 만듦. 사용자 요청으로 구현은 Codex에게 넘기고 스펙과 이슈 3개를 `.scratch/conversation-mode/`에 작성 | npm test 14개 통과 |
| 2026-11-04 13:35 | Claude(UPTIVE 세션) | 음성 작업 전체 인수인계 문서 `docs/handoff-voice.md` 작성(목표·결정·후보 조사·함정·다음 할 일) | 문서만 바꿈 |
| 2026-11-04 10:32 | Claude | setup-matt-pocock-skills 적용: 이슈는 로컬 마크다운(`.scratch/`), 라벨은 기본값, 도메인 문서는 단일 구성. `docs/agents/` 3개 파일 생성, `AGENTS.md`에 `## Agent skills` 블록 추가 | 문서만 바꿈 |
| 2026-11-04 10:24 | Claude | 공유 작업판을 만들고, 루트 `CLAUDE.md`(@AGENTS.md)를 추가하고, `AGENTS.md`에 작업판 규칙을 더함 | 문서만 바꿈 |
| 2026-11-04 10:15 | Claude | 프로젝트 전체 분석, Core Policy를 메모리에 저장, 사본이 원본과 같은지 확인 | pytest 68 · npm test 4 · tsc 통과 |
| 2026-11-04 (이전) | 다른 세션(Codex로 추정) | `AGENTS.md`, `docs/project-sync.md`, `docs/shared-instructions-snapshot.md` 작성 | 문서에 pytest 68 · node 4 · tsc 통과로 적혀 있음 |
