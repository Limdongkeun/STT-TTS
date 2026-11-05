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

- [ ] **이번 주(~11/7)**: 폰 기본 STT로 C1~C7·D1~D25 시험 → 저장본 쌓으며 서버 답·보정 개선
- [ ] 폰 기본 STT 한계로 보이는 사례(14:10 시험) — 다음 주 서버 STT와 비교: D6 "가스비 내가 냈어"→"코스피 대가 됐어", D10 "아내가 가는"→"안에만 하는", D15 "부탁 다 했어"→"나한테 부탁이 뭐야?", D22 "소윤이"→"토요일"
- [ ] **다음 주(11/9~)**: 서버 STT 모델(Qwen3-ASR, 필요하면 TeamUNIVA 한국어판) 연결 → 같은 시험표로 시험·저장 → 폰 기본 STT 저장본과 비교
- [ ] 부부 공유 업무 D1~D25 실기기 시험 (아내·남편 전환, 가능하면 폰 두 대로 공유 확인) — [스펙](../.scratch/family-shared-tasks/spec.md), [순서](test-plan.md#2단계-추가-시험--부부-공유-업무-d1d25)
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
- 서버 기본 답 모드는 `family-demo`(가족 돌봄 시험 답)다. 고정 답은 `ANSWER_PROVIDER=fixed`일 때만 쓴다. 앱 맨 위 파란 글자에 서버의 답 모드가 보인다(2026-11-05).
- 부부 공유 업무 기록은 서버 메모리에 두고 모든 폰이 같이 본다(재시작·`POST /demo/reset`으로 초기화). 앱에서 '나'(역할)는 고르지 않는다: 누가 했는지는 문장 속 남편·아내로 알아듣고, 사람이 없는 "내가"는 아내로 본다(2026-11-05 14:20 사용자 결정).
- 이슈·스펙은 `.scratch/<기능>/`에 마크다운으로 둔다(GitHub Issues는 안 씀). 상태 라벨은 기본 5개를 쓴다. 이 작업판은 "누가 무엇을 하는지", `.scratch`는 "이슈 내용"을 맡는다. 자세한 건 `docs/agents/`에 있다.

## 검증 기준선

| 항목 | 결과 | 확인 |
|---|---|---|
| server pytest | 248개 통과 | 2026-11-05 Claude |
| app `npm test` / `npm run typecheck` | 29개 통과 / 통과 | 2026-11-05 Claude |
| app 린트 | ESLint 설정 없음, 못 돌림 | 2026-11-04 Claude |

## 작업 기록 (최신이 위)

| 날짜 시각 | 누가 | 한 일 | 검증 |
|---|---|---|---|
| 2026-11-05 14:35 | Claude | '나' 역할 없앰: 앱의 나: 아내/남편 버튼·카드 표시 삭제, `/ask`에 speaker 안 보냄. 서버는 문장 속 남편·아내로 누가 했는지 판단("가스비 아내가 냈어", "남편한테 온 부탁", "남편이 약국 부탁 다 했어"), 물음표로 끝나면 묻는 말. 시험 문장 D3·D6·D12·D14~D16·D19를 사람 이름 문장으로 바꿈 | server 248개 · app 29개 · tsc 통과 |
| 2026-11-05 14:25 | Claude | 14:10 실기기 시험 반영: [저장하기] = 저장 후 시험표·서버 시험 데이터 전부 초기화(실패하면 안 지움). 보정 추가(수연→소윤, 어린이집+학원→하원, 7년·칠년+용돈→친정, 공기+심장사상충·약·백신→콩이), 받는 사람 없는 '…해 달라고 부탁해 줘'는 배우자에게 | server 240개 · app 29개 · tsc 통과 |
| 2026-11-05 14:05 | Claude | 저장본에 STT·TTS 기록: 말로 한 턴마다 STT 이름(폰 기본 STT / 서버 모델 이름) 저장, `/health`에 sttModel·ttsModel, 저장본 비교는 같은 STT의 바로 앞 저장본과만, history.md에 STT·TTS 칸. 시험표 위에 '지금 STT' 표시 | server 224개 · app 29개 · tsc 통과 |
| 2026-11-05 13:55 | Claude | 시험표 저장본: 기기별 draft(자동 임시 저장) → [💾 저장하기]로 저장본(코드 버전·요약) + history.md 한 줄, '시험 데이터 초기화'가 시험표도 비움(저장 안 했으면 묻기), 시험표 위쪽 '지난 저장본'에서 ×→○/○→× 비교. `/test-runs` → `/test-sheet/{기기}/draft·attempts`. 예전 `2026-11-05-ios-27-0-1.json`은 같은 기기의 첫 draft로 불러옴(파일은 그대로) | server 220개 · app 28개 · tsc 통과 |
| 2026-11-05 13:30 | Claude | 웹 시험표(claude.ai 페이지) 삭제 — 앱 맨 아래 시험표로 대체 | 링크 삭제 확인 |
| 2026-11-05 13:25 | Claude | 사용자 실기기 피드백 반영: 시험표 카드의 '🎤 이 문장 말하기'가 바로 듣기를 시작(다시 누르면 끝, 카드 안에 받아 적는 글 표시). 시험표에는 말로 한 턴만 기록, 글로 묻기 미리 채우기 제거 | app 26개 · tsc 통과 |
| 2026-11-05 11:50 | Claude | 앱 맨 아래 시험표: 서버 `test_sheet.py`(문장 목록·회차별 결과 저장 → `results/test-runs/<회차>.json·.md`), `GET /test-cases`·`GET/PUT /test-runs/{회차}/results`. 앱 `testSheet.ts`·`useTestSheet.ts`·`TestSheetPanel.tsx`: '이 문장 시험' → 말하면 인식한 말·화면 답 자동 기록, 나 자동 전환, 다음 문장으로. 기대 답이 실제 서버 답과 같은지 테스트로 묶음 | server 207개 · app 26개 · tsc 통과, 실기기 확인 대기 |
| 2026-11-05 11:35 | Claude | 실기기 시험표(폰 웹 페이지) 게시: https://claude.ai/artifact/87CJwffjUDuWYwDMv5KNeX — C1~C7·D1~D25, 회차별로 인식한 말·○/×·메모 저장, 마크다운 표로 복사 | 저장소 연결 확인(회차 0개) |
| 2026-11-05 11:25 | Claude | ① couple_* → `family_records.py`(가족 기록 데이터)·`family_topics.py`(주제별 답, C1·C2·C6·C7 포함)로 통일, `family_demo.py`는 입구와 해열제 대화만. 스펙 폴더 `.scratch/family-shared-tasks/`로 이름 바꿈 ② STT 보정 `stt_correction.py`(동의어·이름 목록·한글 금액) + `test_family_demo.py`에 주제별 STT 변형 35개·보정 유닛·과보정 방지 테스트 | server 187개 통과(동작 변화 없음 확인 후 보정 추가) |
| 2026-11-05 11:12 | Claude | 부부 공유 업무 시험 10가지(장보기·고정 지출·생활비·등하원·집안일·부탁·양가·만기·준비물·반려동물) 추가. A 스펙 `.scratch/couple-shared-tasks/`, B 서버 `couple_state.py`·`couple_demo.py`·`/ask` speaker·`POST /demo/reset`·읽기 변환(건, 만 단위 띄어 읽기), C 앱 나: 아내/남편·초기화 버튼, D test-sentences·test-plan·GLOSSARY·README | server 122개 · app 19개 · tsc 통과, 실기기 시험 대기 |
| 2026-11-05 10:45 | Claude | 폰에서 C2가 '이번 주만 준비' 안내로 빠지던 문제: family-demo 비교 글을 NFC + 글자·숫자만 남기게 바꿈(폭 없는 공백·문장부호 대응). 소윤이 일정은 '다음 주'일 때만 범위 안내. `/ask` 받은 질문을 uvicorn 로그에 repr로 남김. 폰이 실제로 보낸 글자는 아직 미확인 → 서버 로그로 확인 예정 | server 91개 통과 |
| 2026-11-05 10:35 | Claude | 서버 기본 답 모드를 family-demo로 바꿈(fixed는 설정할 때만). 앱 상단에 /health 기반 서버 모드 표시(`app/src/serverInfo.ts`, 눌러서 다시 확인). README·test-plan·.env.example 갱신. 떠 있는 서버는 사용자가 다시 켜야 반영됨 | server 76개 · app 18개 · tsc 통과 |
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
