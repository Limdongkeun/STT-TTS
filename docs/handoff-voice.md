# 가족비서 음성(STT·TTS) 작업 인수인계 — 2026-11-04

## 1. 목표
가족비서 앱에서 **내가 말하면 → 글로 바꾸고(STT) → 기존 LLM·DB에서 답을 찾고 → 음성으로 읽어 준다(TTS)**.
- 1차는 "듣고 → 찾고 → 읽어 주기"만 한다. 듣고 바로 말로 답하는 통합 음성 LLM은 지금 쓰지 않는다.
- 파인튜닝은 시작 조건이 아니다. 기본 한국어 목소리로 먼저 검증하고, 목소리나 발음이 부족할 때 검토한다. 한국어를 이미 잘하는 모델은 LoRA로 해도 품질이 거의 안 오른다는 연구가 있다(VoxCPM2 Khmer·Korean 논문, arXiv 2606.26618).
- 가족비서 1차 범위: 업체·기관에 거는 전화·예약·결제 대행은 뺀다. 가족에게 거는 자동 전화(예: 부모님 복약 확인)는 넣을 수 있다.

## 2. 결정된 구성
| 역할 | 1순위 | 2순위·비교 | 라이선스 |
|---|---|---|---|
| STT | **폰 기본 STT**(iOS·안드로이드 내장, `expo-speech-recognition`) | **Qwen3-ASR** 1.7B / 0.6B(서버) | Apache 2.0 |
| 답 찾기 | 기존 LLM·DB(아직 연결 전, 고정 답) | — | — |
| TTS | **Qwen3-TTS CustomVoice, 목소리 Sohee**(한국어 여성) 1.7B / 0.6B | Fun-CosyVoice3-0.5B-2512 | Apache 2.0 |
| 말 끝 감지(나중) | Silero VAD | — | MIT |

- **폰 기본 STT를 먼저 쓰는 이유:** 쉽고 무료다. 말하는 중에 글자가 바로 뜨고, 말이 끝나는 것도 알아서 감지한다.
  - 대신 품질을 우리가 고칠 수 없다.
  - 음성 데이터가 애플·구글로 간다.
  - 자동 전화에는 쓸 수 없다.
- **Qwen3-ASR을 함께 두는 이유:**
  - 부모님 자동 전화처럼 폰 기능을 쓸 수 없는 곳이 있다.
  - 인식 품질을 직접 고치고 싶을 때(파인튜닝, 가족 이름 교정) 필요하다.
- **Qwen3-TTS 모델 3종:** Base(목소리 복제), CustomVoice(정해진 목소리), VoiceDesign(목소리를 글로 설명).
  - 복제가 필요 없으므로 CustomVoice를 쓴다.
  - 모델 카드는 각 목소리를 그 목소리의 모국어로 쓰라고 권한다. 그래서 한국어는 Sohee다.
- 폰 기본 TTS는 기계 목소리라 쓰지 않는다.

## 3. 조사한 다른 후보 (참고)
> 공식 모델 카드로 다시 확인한 비교표는 [voice-models.md](voice-models.md)에 있다(2026-11-04). 바뀐 점: Supertonic 3과 Kokoro는 제외한다. CosyVoice3은 상업 이용 문구를 확인해야 한다. Qwen3-TTS 공개 패키지에는 스트리밍이 없다.

- **통합 음성 LLM(나중 검토)**
  - A.X K2 Raon-Speech 21B-A3B(크래프톤+SKT, 2026-07): 한국어 점수 0.72로 1위. 회사 자체 발표이고 라이선스는 확인 필요.
  - HyperCLOVA X SEED Omni 8B(네이버): 한국어에 강하다. 네이버와 경쟁하는 서비스면 별도 허가가 필요하다는 조항이 있다.
  - Qwen3-Omni 30B-A3B(Apache 2.0): 말 출력 10개 언어에 한국어가 들어 있고, Instruct만 말로 답한다.
- **TTS 기타**
  - Chatterbox Multilingual(MIT): 한국어를 지원하고, 만든 음성에 워터마크가 들어간다.
  - Supertonic 3(99M): 가중치가 OpenRAIL-M이다. 슈퍼톤이 2026-07 해산을 결의했다는 글이 미러 사이트에만 있고, 공식 확인은 못 했다.
  - Fish Audio S1-mini: 비상업용이라 제외했다.
  - Kokoro: 한국어 공식 지원이 불확실하다.
- **STT 기타**
  - Qwen3-ASR 한국어 파인튜닝판(TeamUNIVA): CER 6.86% → 5.37%. 만든 쪽이 잰 수치다.

## 4. 시험 흐름
**1단계(지금): 버튼 방식**
1. 🎤 누르면 녹음 시작
2. 말하기
3. 다시 누르면 끝
4. 여기부터 자동: STT → `/ask`(답 + 읽기용 글) → `/tts` → 재생

**2단계(나중): 자동 방식**
- VAD로 말 끝을 자동 감지한다.
  - 조용한 시간 0.8~1.2초로 시작한다. 부모님처럼 천천히 말하는 분은 1.5초 이상으로 둔다.
  - 사용자별 설정값으로 만든다.
  - VAD는 말소리 구간만 찾을 뿐, 말이 끝났는지까지 이해하지는 못한다. 그래서 일정 시간 조용하면 끝내는 규칙이 필요하다.
- 답은 문장 단위로 읽는다. 첫 문장부터 바로 TTS에 넘긴다.
  - 기존 LLM이 스트리밍으로 답해야 효과가 있다.
  - 문장 단위로 끊어 읽는 것과 TTS 자체 스트리밍은 다르다.
  - Qwen3-TTS 모델 카드는 스트리밍을 지원하고 첫 소리까지 최소 97ms라고 한다. 실제 속도는 쓸 실행 방식에서 재야 한다.

## 5. 읽기용 글 변환 (텍스트 정규화)
화면용 답과 읽기용 답을 나눈다. 구현 파일은 `server/app/normalize.py`, 테스트는 `server/tests/test_normalize.py`.

| 화면 | 읽기 |
|---|---|
| 오후 3시 30분 | 오후 세 시 삼십 분 (시는 고유어, 분은 한자어) |
| 3개 / 4명 / 2시간 | 세 개 / 네 명 / 두 시간 |
| 11월 4일, 6월, 10월 | 십일월 사일, 유월, 시월 |
| 3.8억 원 / 12,000원 | 삼억 팔천만 원 / 만 이천원 |
| 02-123-4567 | 공이 일이삼 사오육칠 |
| AI, DB | 에이아이, 디비 |
| 4시~6시 | 네 시에서 여섯 시 |

- `11/4` 같은 빗금 날짜는 뜻이 갈려서 바꾸지 않는다. 답을 만들 때 DB 날짜로 "11월 4일"처럼 쓴다.
- '번'은 횟수(두 번)와 번호(3번 버스)가 갈려서 규칙에서 뺐다.

## 6. 프로젝트 현황
- 위치: `/Users/teddy/Desktop/UPTIVE/STT-TTS`
- GitHub: https://github.com/Limdongkeun/STT-TTS (main, 최근 커밋 a698cc8 "matt pocock setup")
- 폰 채팅방: STT-TTS 전용 채널이 연결돼 있다(herdr STT-TTS 창에서 `uclaude`).
- **작업 규칙:** 시작 전에 `AGENTS.md` → `docs/WORKBOARD.md`(Claude·Codex 공유 작업판)를 읽고, 잡은 일은 "진행 중"에 적는다. 파일 지도는 `docs/project-sync.md`, 이슈는 `.scratch/`(mattpocock-skills 설정). 코딩 규칙은 Teddy Core Policy. 커밋은 사용자가 요청할 때만 한다.
- **점검 후보(작업판에 있음)**
  1. TTS가 실패하면 "다시 듣기"가 이전 음성을 튼다 (`App.tsx` answerAndSpeak).
  2. ffmpeg 60초 TimeoutExpired를 잡지 않아 500으로 나간다 (`audio.py`).
  3. 폰 STT를 연속으로 탭하면 end 이벤트와 경합한다 (`App.tsx`, `usePhoneStt.ts`).
- **모델은 아직 받지 않았다.**

```
server/  Python 3.12(uv) + FastAPI
  app/main.py        GET /health, POST /stt(multipart audio → ffmpeg 16kHz 모노 → STT),
                     POST /ask {text} → {answerText, speechText}, POST /tts {text, normalize?} → {audioUrl…},
                     GET /audio/{id}
  app/engines/       mock / qwen3_asr.py / qwen3_tts.py (처음 호출할 때만 모델 로드)
  app/answers.py     기존 LLM·DB 연결 자리 (지금은 고정 답)
  app/normalize.py   읽기용 변환
  tests/             68개 통과
app/     Expo SDK 58 (TypeScript)
  App.tsx            STT 고르기(폰 기본 / 서버 Qwen3-ASR), 🎤 버튼, 글로 바로 묻기, 결과·걸린 시간, 다시 듣기
  src/usePhoneStt.ts expo-speech-recognition (ko-KR, interimResults, 가족 호칭을 contextualStrings로)
  src/useServerRecorder.ts  expo-audio 녹음(m4a)
  src/api.ts         서버 호출 / .env: EXPO_PUBLIC_STT_SERVER_URL, EXPO_PUBLIC_TTS_SERVER_URL
docs/    test-plan.md (단계 1~6), test-sentences.md (질문 15 + 답 15)
```

**실행 (server 폴더)**
- 흐름만 시험(mock):
  `uv run uvicorn app.main:app --host 0.0.0.0 --port 8002`
- 실제 TTS:
  `TTS_ENGINE=qwen3-tts uv run --extra tts uvicorn app.main:app --host 0.0.0.0 --port 8002`
- 실제 STT:
  `STT_ENGINE=qwen3-asr uv run --extra asr uvicorn app.main:app --host 0.0.0.0 --port 8001`
- 0.6B로 바꿀 때:
  `ASR_MODEL_ID=Qwen/Qwen3-ASR-0.6B`, `TTS_MODEL_ID=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`

**앱**
- `.env`에 맥미니 IP를 넣는다(지금 `192.168.29.179`).
- 폰을 연결하고 `npm run ios:device` 또는 `npm run android:device`.
- 폰 기본 STT는 네이티브 모듈이라 Expo Go에서는 안 된다. 개발 빌드가 필요하다.

## 7. 꼭 알아야 할 함정
1. **qwen-asr와 qwen-tts는 한 환경에 설치할 수 없다.**
   - qwen-asr 0.0.6은 transformers 4.57.6을, qwen-tts 0.1.1은 4.57.3을 고정한다.
   - 그래서 STT 서버(8001, `--extra asr`)와 TTS 서버(8002, `--extra tts`)를 따로 띄운다.
   - `pyproject.toml`에 uv `conflicts`를 선언해 뒀다.
2. **처음 켤 때 오래 걸린다.** torch 같은 큰 패키지를 설치하고, 첫 요청 때 모델을 받는다(1.7B 약 3~4GB).
3. **맥미니(Apple 칩)는 느리다.** 맥에서는 `MODEL_DEVICE=auto`가 mps를 고르고, 안 되면 `cpu` + `float32`로 바꾼다.
   - CosyVoice3의 빠른 실행 방식(vLLM·TensorRT)은 NVIDIA GPU용이다.
   - 맥미니에서는 품질만 보고, 속도는 실제 서버에서 다시 잰다.
4. **API 사용법 확인 근거.** Qwen 패키지 사용법은 PyPI README를 따랐다.
   - `Qwen3ASRModel.from_pretrained(...).transcribe(audio=, language=)[0].text`
   - `Qwen3TTSModel.from_pretrained(...).generate_custom_voice(text=, language=, speaker=)` → `(wavs, sr)`
   - 실제 모델로는 아직 실행하지 않았다.
5. **STT는 고유명사를 자주 틀린다.** 가족 이름이나 학원 이름이 그렇다. 시험 문장에 넣었고, 틀리면 DB의 이름 목록으로 고치는 단계를 둔다.
6. **자동 전화로 가면 음질이 8kHz로 떨어진다.** 앱 녹음은 16kHz 이상이다. 전화 음질 샘플도 따로 시험한다.
7. **법·안전**
   - AI 기본법(2026-01-22 시행)에 따라 AI 음성 전화는 시작할 때 AI라고 알린다.
   - 자녀 목소리 복제는 하지 않는다. 보이스피싱으로 오해받을 수 있다.
   - 복약은 알림과 전달까지만 한다. 복용 지시나 증상 판단은 하지 않는다.

## 8. 다음 할 일
1. **1단계:** mock 서버를 띄우고 앱을 빌드한 뒤, '글로 바로 묻기'로 연결을 확인한다.
2. **2단계:** 폰 기본 STT로 질문 문장 A1~A15를 시험한다. 조용한 곳, 시끄러운 곳, 천천히 말하기를 각각 해 본다.
3. **3단계:** Qwen3-TTS Sohee로 답 문장 B1~B15를 듣는다. 1.7B와 0.6B를 비교한다.
   - 잴 것: `elapsedMs`, RTF(1보다 작아야 함), 틀린 발음 수, 자연스러움 1~5점
4. **4단계:** Qwen3-ASR(8001)로 같은 질문 문장을 시험한다. 폰 STT와 비교하고, 0.6B와 1.7B도 비교한다.
   - 잴 것: CER, 처리 시간, 8kHz 음질
5. **5단계:** `server/app/answers.py`에 기존 LLM·DB를 연결한다. 키와 주소는 환경변수로 넣는다.
6. **6단계:** VAD와 문장 단위 읽기를 붙인다.
- 결과는 `results/YYYY-MM-DD-단계N.md`에 남긴다. 양식은 `docs/test-plan.md`에 있다.
