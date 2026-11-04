# STT-TTS 프로젝트 동기화 — 2026-11-04

가족비서의 한국어 음성 왕복을 평가하는 프로토타입이다. 일정이나 가족 데이터는 연동되지 않았고 질문 종류에 관계없이 고정 답을 반환한다. 앱은 Expo SDK 58/RN 0.88/TypeScript 단일 화면이며 서버는 Python 3.12/FastAPI/uv다.

## 실행 흐름

1. **폰 STT**: 마이크·음성 인식 권한 → OS 인식기(ko-KR, 중간 결과, 가족 단어 힌트) → end 이벤트에서 마지막 결과 사용. 서버 STT 호출은 없다. OS 인식기를 쓴다는 사실만으로 오프라인 처리를 보장하지 않는다.
2. **서버 STT**: Expo Audio로 녹음 → multipart `audio`로 STT 서버의 POST /stt → 확장자 및 크기 검사 → 임시 폴더 → ffmpeg 16 kHz mono WAV → mock 또는 Qwen3-ASR → 인식 텍스트. ffmpeg 변환은 mock STT에도 필요하다.
3. **텍스트 입력**: STT를 생략한다. 이후 세 경로 모두 답·TTS 서버의 POST /ask → 고정 화면용 답 및 한국어 발음 변환을 거친 speechText → POST /tts → WAV 생성 → GET /audio/{id} 재생. 앱은 같은 플레이어에서 처음으로 이동해 다시 듣는다.
4. **시간 측정**: 앱은 HTTP 단계와 전체 경과 시간을 기록한다. 폰은 인식 종료부터, 서버는 녹음 중단부터, 텍스트는 입력 제출부터 시작한다. 합계는 재생 요청 시점까지이며 첫 음성 도달 시점이나 재생 완료 시간은 아니다. API elapsedMs는 서버 내부 경과 시간이다.

## 파일 지도

| 파일 | 역할 |
|---|---|
| README.md | 설치, 실행 모드, 포트, API 및 개발 빌드 |
| docs/test-plan.md / test-sentences.md | 6단계 검증 계획 / 한국어 질문·답 문장 각 15개 |
| results/.gitkeep | 결과 디렉터리 자리표시자; 실제 결과는 기본적으로 Git 제외 |
| app/AGENTS.md | Expo 변경 시 SDK 버전 문서 확인, CNG/개발 빌드, 린트·타입 검사 규칙 |
| app/index.ts / App.tsx | Expo 루트 등록 / 입력 모드, 상태 전이, 요청 연결, 결과 및 재생 UI |
| app/src/sttModes.ts / usePhoneStt.ts | 모드 이름과 맥락 단어 / 권한 및 음성 인식 이벤트 |
| app/src/useServerRecorder.ts | 권한, 고음질 녹음, URI 반환 및 iOS 재생용 오디오 모드 복원 |
| app/src/api.ts | 서버 주소 분리, JSON/multipart 요청, 120초 요청 제한, 재생 URL |
| app/src/url.ts / url.test.ts | 주소, 경로, 파일명·MIME 순수 함수 / Node 테스트 4개 |
| app/package.json / package-lock.json / tsconfig.json | SDK·스크립트 / npm 해상도 / 엄격한 타입 검사(테스트 제외) |
| app/app.json / .env.example | 네이티브 식별자·권한·아이콘·LAN HTTP / 공개 빌드 변수의 주소 예시 |
| app/assets/*.png | 기본·Android 적응형 3종·웹 아이콘; splash PNG는 현재 app.json에서 미참조 |
| app/.claude/settings.json / LICENSE | Expo 플러그인 설정 / 라이선스 |
| server/pyproject.toml / uv.lock / .python-version / .env.example | 런타임·테스트·상호 배타적 모델 extras / 잠금 / Python 버전 / 엔진 설정 예시 |
| server/app/main.py | 앱 조립, health 및 요청 스키마, 제한 업로드, 최대 50개 임시 WAV 저장, 다운로드 |
| server/app/audio.py | 확장자 허용 목록 및 셸 없이 ffmpeg 실행(60초 제한) |
| server/app/settings.py / device.py | 환경변수 검증 및 기본값 / CUDA → MPS → CPU 선택과 torch dtype |
| server/app/answers.py | AnswerProvider 계약과 고정 답; 실제 LLM·DB를 연결할 지점 |
| server/app/normalize.py | 전화번호 → 금액 → 시간 → 날짜 → 단위 → 숫자 → 약어·범위 순으로 읽기 변환 |
| server/app/engines/base.py / __init__.py | 엔진 Protocol과 결과 dataclass / 설정 기반 팩토리 |
| server/app/engines/mock.py | 고정 한국어 인식문 / 440 Hz WAV 테스트음 |
| server/app/engines/qwen3_asr.py / qwen3_tts.py | 첫 요청 시 모델 로딩, ASR 텍스트 추출 / CustomVoice Sohee WAV 합성 |
| server/app/__init__.py | Python 패키지 표식 |
| server/tests/test_api.py / test_normalize.py / test_settings.py | mock API·WAV·입력 오류·캐시 / 발음 규칙 / 설정과 지연 초기화 |
| .gitignore / app/.gitignore / .idea/* | 환경 파일·캐시·생성물 제외 / Expo·네이티브 생성물 제외 / IDE 모듈과 VCS 메타데이터 |

## 실행 기준 및 다음 확인 지점

- mock은 8002 하나로 가능. 실제 ASR은 8001, 실제 TTS와 답변은 8002. 잠금 파일에서 qwen-asr 0.0.6과 qwen-tts 0.1.1이 각각 transformers 4.57.6과 4.57.3을 요구한다. 두 서버를 동시에 운영할 때는 각각 별도 가상환경을 지정해 같은 .venv를 재동기화하지 않도록 한다.
- 서버 설정은 os.environ에서만 읽는다. `.env`를 복사할 경우 실행 환경에 내보내거나 명시적으로 로드해야 한다. 폰 앱은 Expo 공개 환경변수 두 개를 사용한다. 실제 기기에서는 호스트의 LAN IP가 필요하다.
- 네이티브 음성 인식은 개발 빌드가 필요하다. 현재 진입점은 registerRootComponent이며 Expo Router는 설치되지 않았다. 새 내비게이션 작업에는 app/AGENTS.md를 확인한다.
- 현 단계는 로컬 시험용이다. HTTP 허용 및 인증 없는 엔드포인트, 프로세스별 임시 오디오 보관을 전제로 한다. /health는 엔진 설정만 보여주며 실제 모델 준비 여부는 확인하지 않는다.
- 후속 점검 후보: 연속 마이크 탭과 인식 종료 이벤트 경합, 합성 실패 후 다시 듣기 버튼이 이전 소스를 가리킬 가능성, ffmpeg 타임아웃의 HTTP 오류 매핑, 큰 숫자·겹치는 정규식의 발음 경계. 코드에서 발견한 후보이며 실제 기기에서 재현하지 않았다.
- 검증: 서버 pytest 68개 통과(ffmpeg 포함), 앱 Node 테스트 4개 통과, TypeScript 통과. 앱에 ESLint 실행 파일 및 설정이 없어 린트 미실행. 실제 Qwen 추론, 기기 권한·재생, 발음 및 응답 속도는 이번 검증 범위 밖이다.
