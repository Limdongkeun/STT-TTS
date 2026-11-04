# 공유 작업판 (Claude · Codex)

Claude와 Codex가 이 파일 하나로 일을 이어받는다. 규칙은 `AGENTS.md`의 "공유 작업판" 절을 따른다.

- **시작 전**: 이 파일을 끝까지 읽는다. 특히 "진행 중"과 최근 "작업 기록"을 본다.
- **작업을 잡을 때**: "진행 중"에 `누가 · 무엇 · 시작 시각 · 건드리는 파일`을 적는다. 다른 쪽이 잡은 파일은 건드리지 않는다.
- **끝나면**: "진행 중"에서 그 줄을 지운다. "작업 기록" 맨 위에 한 줄을 더하고, 바뀐 상태가 있으면 다른 칸도 고친다.
- 시각은 KST, 날짜는 `YYYY-MM-DD`로 적는다. 비밀값(키·토큰·주소 비밀번호)은 적지 않는다.

## 지금 목표

`docs/test-plan.md` 1단계(연결 확인, 모델 없음)를 실제 폰에서 통과시킨다.

## 진행 중

| 누가 | 무엇 | 시작 | 건드리는 파일 |
|---|---|---|---|
| (없음) | | | |

## 다음 할 일

- [ ] 1단계: 서버 mock(8002) + 앱 개발 빌드 → "글로 바로 묻기"로 고정 답과 '삐' 소리 확인
- [ ] 2단계: 폰 기본 STT로 `docs/test-sentences.md`의 A 문장 기록
- [ ] 3단계: Qwen3-TTS Sohee (1.7B / 0.6B 비교)
- [ ] 4단계: Qwen3-ASR (8001) — 폰 STT와 CER·속도 비교
- [ ] 5단계: `server/app/answers.py`에 기존 LLM·DB 연결
- [ ] 점검 후보 1: TTS가 실패하면 "다시 듣기"가 이전 답 음성을 튼다 (`app/App.tsx` answerAndSpeak — TTS 전에 setSpeechText를 한다)
- [ ] 점검 후보 2: ffmpeg 60초 TimeoutExpired를 잡지 않아서 500으로 나간다 (`server/app/audio.py` to_wav16k)
- [ ] 점검 후보 3: 폰 STT를 연속으로 탭하면 end 이벤트와 경합할 수 있다 (`app/App.tsx` onMicPress, `app/src/usePhoneStt.ts`)
- [ ] 정리: 커밋 안 된 `AGENTS.md`, `CLAUDE.md`, `docs/project-sync.md`, `docs/shared-instructions-snapshot.md`, `docs/WORKBOARD.md`, `docs/agents/*`를 커밋할지 사용자에게 확인

## 정한 것

- 실제 STT 서버는 8001(`--extra asr`), 답+TTS 서버는 8002(`--extra tts`)로 나눈다. qwen-asr와 qwen-tts가 서로 다른 transformers 버전을 쓰기 때문이다. mock만 쓸 때는 8002 하나로 된다.
- 코딩 규칙은 Teddy Core Policy(`/Users/teddy/Desktop/UPTIVE/LLM-코딩/core_instructions.md` + `packs/`)를 따른다.
- 커밋은 사용자가 요청할 때만 한다.
- 이슈·스펙은 `.scratch/<기능>/`에 마크다운으로 둔다(GitHub Issues는 안 씀). 상태 라벨은 기본 5개를 쓴다. 이 작업판은 "누가 무엇을 하는지", `.scratch`는 "이슈 내용"을 맡는다. 자세한 건 `docs/agents/`에 있다.

## 검증 기준선

| 항목 | 결과 | 확인 |
|---|---|---|
| server `uv run pytest` | 68개 통과 | 2026-11-04 Claude |
| app `npm test` / `npm run typecheck` | 4개 통과 / 통과 | 2026-11-04 Claude |
| app 린트 | ESLint 설정 없음, 못 돌림 | 2026-11-04 Claude |

## 작업 기록 (최신이 위)

| 날짜 시각 | 누가 | 한 일 | 검증 |
|---|---|---|---|
| 2026-11-04 10:32 | Claude | setup-matt-pocock-skills 적용: 이슈는 로컬 마크다운(`.scratch/`), 라벨은 기본값, 도메인 문서는 단일 구성. `docs/agents/` 3개 파일 생성, `AGENTS.md`에 `## Agent skills` 블록 추가 | 문서만 바꿈 |
| 2026-11-04 10:24 | Claude | 공유 작업판을 만들고, 루트 `CLAUDE.md`(@AGENTS.md)를 추가하고, `AGENTS.md`에 작업판 규칙을 더함 | 문서만 바꿈 |
| 2026-11-04 10:15 | Claude | 프로젝트 전체 분석, Core Policy를 메모리에 저장, 사본이 원본과 같은지 확인 | pytest 68 · npm test 4 · tsc 통과 |
| 2026-11-04 (이전) | 다른 세션(Codex로 추정) | `AGENTS.md`, `docs/project-sync.md`, `docs/shared-instructions-snapshot.md` 작성 | 문서에 pytest 68 · node 4 · tsc 통과로 적혀 있음 |
