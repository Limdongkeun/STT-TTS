# STT-TTS 시험 프로젝트

가족비서 음성 기능 시험용. **앱에서 말하기 → STT → 기존 LLM·DB(지금은 고정 답) → TTS로 듣기**를 단계별로 시험한다.

```
STT-TTS/
├── server/     Python 3.12 + FastAPI (uv). STT·답 찾기·TTS 서버
├── app/        Expo(React Native, TypeScript) 시험 앱
├── docs/       단계별 시험 계획, 시험 문장
└── results/    시험 결과 기록 (음성·표)
```

- STT는 두 가지 중에서 고른다: **폰 기본 STT**(iOS·안드로이드 내장), **서버 Qwen3-ASR**.
- TTS: **Qwen3-TTS CustomVoice, 목소리 Sohee**.
- 모든 엔진에 **mock**(가짜)이 있다. 모델 없이도 흐름 전체를 시험할 수 있다.
- **모델은 아직 받지 않았다.** 실제 엔진을 처음 부를 때 Hugging Face에서 자동으로 받는다.

## 1. 서버

### 처음 한 번

```bash
cd server
uv sync          # 기본 패키지만 설치 (모델·torch 없음)
uv run pytest    # 테스트
```

### 실행 방법

서버는 같은 와이파이에 있는 폰에서 접속할 수 있도록 `--host 0.0.0.0`으로 띄운다. 시험용이므로 공용 와이파이에서는 띄우지 않는다.

| 상황 | 명령 (server 폴더에서) |
|---|---|
| ① 모델 없이 흐름만 (mock 전부, 포트 8002 하나) | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8002` |
| ② 실제 TTS (Qwen3-TTS Sohee) | `TTS_ENGINE=qwen3-tts uv run --extra tts uvicorn app.main:app --host 0.0.0.0 --port 8002` |
| ③ 실제 STT (Qwen3-ASR) | `STT_ENGINE=qwen3-asr uv run --extra asr uvicorn app.main:app --host 0.0.0.0 --port 8001` |

- 답 찾기는 기본으로 **가족 돌봄 시험 답(`family-demo`)** 이다. 따로 설정하지 않아도 `docs/test-plan.md`의 C1~C7 질문에 답한다. 예전 고정 답이 필요하면 앞에 `ANSWER_PROVIDER=fixed`를 붙인다. 지금 서버의 답 모드는 앱 맨 위 파란 글자(또는 `GET /health`)로 확인한다.
- **②③을 하나로 합칠 수 없다.** `qwen-asr`와 `qwen-tts`가 서로 다른 `transformers` 버전을 고정하기 때문이다. 그래서 STT 서버(8001)와 TTS 서버(8002)를 따로 띄운다. 코드는 같고 환경변수와 `--extra`만 다르다.
- `--extra asr`나 `--extra tts`로 처음 실행하면 torch 같은 큰 패키지를 설치한다. 첫 요청 때는 모델(1.7B 기준 약 3~4GB)을 받는다.
- 0.6B로 바꿀 때: `ASR_MODEL_ID=Qwen/Qwen3-ASR-0.6B`, `TTS_MODEL_ID=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- 그 밖의 설정은 `server/.env.example`에 있다. 장치(`MODEL_DEVICE=auto|mps|cpu|cuda:0`)와 자료형도 여기서 정한다.
- 맥에서는 `auto`가 `mps`(Apple GPU)를 고른다. 오류가 나면 `MODEL_DEVICE=cpu MODEL_DTYPE=float32`로 바꿔서 시험한다.

### API

| 주소 | 하는 일 |
|---|---|
| `GET /health` | 지금 쓰는 엔진 확인. 실제 모델이면 `sttModel`·`ttsModel`에 모델 이름 |
| `POST /stt` (multipart `audio`) | 음성 → 글 (ffmpeg로 16kHz 모노 변환 후 STT) |
| `POST /ask` `{ "text", "speaker"?, "context"? }` | 질문 → 답(화면용) + 읽기용 글. `speaker`는 `wife`(기본)/`husband`, `context`는 여러 턴 대화 상태 |
| `POST /demo/reset` | 부부 공유 업무 시험 기록을 처음 시험 데이터로 되돌림(family-demo 모드에서만) |
| `GET /test-cases` | 시험표 문장(C1~C7, D1~D25)과 기대 답 |
| `GET`·`PUT`·`DELETE /test-sheet/{기기}/draft[/{번호}]` | 작성 중인 시험표 읽기·한 문장 저장·비우기 |
| `POST`·`GET /test-sheet/{기기}/attempts` | 시험표를 저장본으로 남기기 / 저장본 목록(지난번과 비교 포함) |
| `POST /tts` `{ "text", "normalize"? }` | 글 → 음성. `audioUrl`을 돌려준다 |
| `GET /audio/{id}` | 만든 음성(wav) 받기 |

- 기존 LLM·DB 연결 자리는 `server/app/answers.py`에 있다. 아직 연결 전이라, 지금은 가족 돌봄 시험 답(`server/app/family_demo.py`)을 돌려준다.
- 읽기용 변환(시간·날짜·금액·전화번호·약어)은 `server/app/normalize.py`에 있다.

## 2. 앱

### 처음 한 번

```bash
cd app
cp .env.example .env     # 맥미니 IP로 고친다 (ipconfig getifaddr en0)
npm test                 # 주소 처리 유닛 테스트
npm run typecheck
```

### 실행 (개발 빌드)

**폰 기본 STT는 네이티브 모듈이어서 Expo Go에서는 동작하지 않는다.** 한 번 빌드해서 폰에 설치해야 한다. 그다음부터는 코드를 고치면 바로 반영된다.

```bash
npm run ios:device       # 아이폰을 케이블로 연결한 상태 (Xcode 서명 필요)
npm run android:device   # 안드로이드 폰 USB 디버깅 켠 상태
```

### 화면

- **STT 고르기**: 폰 기본 STT / 서버 Qwen3-ASR
- **🎤 말하기**: 누르면 듣기 시작, 다시 누르면 끝. 그 뒤 답을 찾고 읽어 주는 것까지 자동으로 진행된다.
- **글로 바로 묻기**: STT 없이 답 찾기와 TTS만 시험한다.
- 결과 칸에 인식한 말, 답(화면용), 답(읽기용), 단계별 걸린 시간이 표시되고, 다시 듣기를 할 수 있다.

## 3. 시험 순서

`docs/test-plan.md`를 본다. 시험 문장은 `docs/test-sentences.md`에 있다.

## 이번 주 임시 음성 (D1~D25)

서버 기본 TTS는 `prerecorded`다. `output/audio/d1-d25`의 지수 사전 음성을 답변과 일치할 때 재생한다. ElevenLabs API 호출이나 키가 필요하지 않다.

D1부터 순서대로 시험하면 녹음과 같은 답변을 받을 수 있다. 생성일(2026-11-05) 이후 날짜나 기록이 바뀌어 녹음과 달라지면 화면 답변과 “일치하는 사전 음성이 없습니다” 안내가 나온다. C1~C7과 녹음 밖 답변도 같은 안내가 나온다. 예전 삐 소리는 `TTS_ENGINE=mock`으로 선택한다.
