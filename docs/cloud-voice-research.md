# 클라우드 STT·TTS 조사: 어디까지 되나, 로컬로 얼마나 따라갈 수 있나

조사 기준: 2026-11-17. Claude(파트 A: API로 쓰는 STT·TTS)와 Codex(파트 B: 우리 오픈 모델을 클라우드 GPU에 올리기, 읽기 전용·웹 검색)가 나눠 조사했다. **아직 아무것도 실제로 호출해 보지 않았다.** 정확도·속도 숫자는 업체 발표나 남의 시험 결과다. 우리 문장으로 재기 전에는 결론으로 쓰지 않는다.

## 한 줄 요약

- **STT 상한선 후보**: ElevenLabs Scribe v2, Soniox, Google Chirp 3, OpenAI gpt-transcribe. 한국어 외부 수치로는 Scribe v2가 가장 앞선다.
- **TTS 상한선 후보**: ElevenLabs, Typecast(한국어·5초 복제 API), Google Chirp 3 HD / Gemini TTS, OpenAI.
- **우리 모델 그대로 클라우드**: Qwen3-ASR-1.7B는 DeepInfra에, Qwen3-TTS는 Replicate·fal·알리바바에 이미 API가 있다. 우리 서버를 통째로 올리려면 Modal이나 GCP 서울 L4가 후보다.
- **비용**: API로 쓰면 하루 100턴 기준 월 몇 달러다. GPU를 24시간 켜 두면 월 약 $540~580이다.

## 파트 A: API 키로 쓰는 클라우드 STT

| 서비스 | 한국어 근거 | 가격(공개) | 메모 |
|---|---|---|---|
| ElevenLabs Scribe v2 / v2 Realtime | 다국어 논문(GigaSpeechBench) 한국어 WER: Scribe v2 4.48, Chirp 3 5.55, GPT-4o Transcribe 6.13 | 실시간 $0.22~0.39/시간(출처마다 다름) | 키워드 힌트(keyterm) 있음. 우리는 이미 ElevenLabs 계정이 있다(사용 때마다 사용자 허락) |
| Soniox v5 | 업체 발표 한국어 WER 1.25%(Deepgram 1.71%). 경쟁사 비교라 그대로 믿지 않음 | 약 $0.10~0.12/시간 | 실시간, 말 중간 언어 바뀜 처리 |
| Google Chirp 3 | 위 논문 한국어 5.55 | 확인 못 함 | 도쿄·서울 리전, 스트리밍 |
| OpenAI gpt-transcribe / gpt-4o-transcribe | 위 논문 한국어 6.13 | $0.0045/분, $0.006/분, 실시간 약 $0.017/분 | 새 gpt-transcribe는 키워드·언어 힌트. 일부 옛 모델은 2027년 은퇴 예정이라는 보도(확인 필요) |
| Deepgram Nova-3 | 한국어 스트리밍 300ms 미만(업체 발표), 독립 한국어 수치 없음 | 약 $0.39~0.55/시간(경쟁사 페이지 기준) | keyterm |
| 네이버 CLOVA Speech | 한국어 전용 | 콘솔에서만 확인 | 국내 서버 |

**지금 우리 기준선**: 11/13 녹음 33개 기준 Qwen3-ASR(힌트 42) CER 10.3%, Whisper turbo 12.9%(대본과 다르게 말한 문장 포함). 같은 33개를 위 API에 넣으면 우리 문장 기준 상한선을 바로 잴 수 있다.

## 파트 A: API 키로 쓰는 클라우드 TTS

| 서비스 | 한국어·목소리 | 가격(공개) | 첫 소리(업체 발표) |
|---|---|---|---|
| ElevenLabs(Flash v2.5, v3) | 자연스러움의 기준점이라는 평가가 많음. 즉시 복제(1~2분), 전문 복제(30분) | v2 Multilingual $0.08/1천 자. Flash·v3 단가는 확인 못 함 | Flash 약 75ms |
| Typecast | 한국 회사, 한국어 감정 표현. **API로 5초 즉시 복제·전문 복제** | 무료 3만 크레딧/월, Lite $15/월 | 110~200ms(출처마다 다름) |
| Supertone | 한국어. API로는 복제 못 하고, Supertone Play에서 등록한 목소리만 부름 | Starter $2.99/월 | 미공개 |
| Google Chirp 3 HD / Gemini TTS | 다국어. 즉시 맞춤 목소리 $60/100만 자 | Chirp 3 HD $30/100만 자(월 100만 자 무료) | 200~500ms |
| OpenAI gpt-4o-mini-tts | 말투 지시 가능. 2027-01 은퇴 예정이라는 보도(확인 필요) | 출력 오디오 토큰 $12/100만 | 미확인 |
| 네이버 CLOVA Voice | 한국어. 커스텀 목소리(약 40분 녹음) | 종량제(콘솔), 생성 파일 재판매·재사용 제한 | 미확인 |

## 파트 B: 우리 오픈 모델을 클라우드에 (Codex 조사 요약)

| 길 | 내용 | 비용·주의 |
|---|---|---|
| **이미 있는 API** | DeepInfra Qwen3-ASR-1.7B($0.00045/분, ZDR 표시) · Replicate qwen3-tts($0.02/1천 자, voice_clone 입력, 결과 1시간 뒤 삭제) · fal Qwen3-TTS 1.7B($0.09/1천 자) · 알리바바 Qwen3-ASR/TTS-Flash(같은 가중치인지 확인 안 됨) | 힌트 42개·견본 전달이 우리와 같게 되는지 확인 필요 |
| **우리 서버 통째로** | Modal(L4 $0.80/시간, 0으로 줄이기 가능. 기본 라우팅이 미국이라 한국에서 빠르다고 가정하면 안 됨) · RunPod Serverless(24GB $0.75/시간) · HF Endpoints(L4 $0.80/시간) · GCP 서울 G2/L4(직접 운영) | 24시간 켜 두면 월 약 $540~580 |

**월 비용 예시**: 하루 100턴, 한 턴에 STT 5초·TTS 30자로 잡았어요.

| 구성 | 월 비용 |
|---|---|
| DeepInfra STT + Replicate TTS | 약 $1.9 |
| 알리바바 ASR + TTS Flash | 약 $1.4 |
| 우리 서버 GPU 1개를 24시간 켜 둠 | 약 $540~580 |

## 실측 결과 (2026-11-17, ElevenLabs, 사용자 허락)

키는 키체인 `elevenlabs-api-key`(Starter, 월 4만 크레딧)에서 읽었고 어디에도 남기지 않았다. 처음에는 키에 speech_to_text 권한이 없어 401이 났고, 사용자가 권한을 켰다.

**STT**: 11/13 녹음 33개, 같은 채점(CER·핵심어 71개)

| 설정 | CER | 핵심어 /71 | 한 문장 |
|---|---|---|---|
| **Qwen3-ASR 힌트 42 (로컬, 지금)** | **0.103** | **69** | 1.01초 |
| ElevenLabs Scribe v3 키워드 42 | 0.120 | 68 | 0.72초(네트워크 포함) |
| Qwen 힌트 없음 | 0.120 | 65 | 0.80초 |
| Whisper turbo 힌트 42 | 0.123 | 64 | 1.09초 |
| Scribe v3 힌트 없음 | 0.166 | 58 | 0.73초 |

- 우리 가족 문장에서는 로컬 Qwen이 더 정확했다. Scribe는 문장 끝('냈어', '먹여야', '뭐야')과 C3 '계열'을 맞혔지만, D12 '아내가 했다고'를 '안 했다고'로(뜻이 반대), C1 '우리 집'을 '어린이집'으로 적었다. 숫자는 숫자로 적는다.

**TTS**: 지수 목소리, 입말 답 10문장(약 400자), 스트리밍 첫 소리까지

| 모델 | 첫 소리 | 크레딧 |
|---|---|---|
| v4 | 약 0.85초 | 1자=1 |
| v4 Turbo | 약 0.25초 | 1자=0.5 |
| Flash v2.5 | 약 0.27초(전체 0.3~0.5초) | 1자=0.5 |
| 107 H2-D(참고) | 약 2.3초 | - |

- 자연스러움은 사용자 청취로 판단한다. 이날 107은 GPU가 모자라(남은 2.1GB) H2-D를 새로 만들지 못해 11/16에 만든 5문장으로 비교했다.
- 크레딧 약 800 사용. 실제 사용(월 약 12만 자)은 Turbo로도 6만 크레딧이라 Starter로는 모자란다.

## "로컬로 얼마나 비슷하게"를 정하는 방법

1. **같은 재료로 상한선부터 잰다.**
   - STT: 11/13 녹음 33개를 클라우드 STT 3~4곳에 넣고, 지금 Qwen(10.3%)과 같은 방식으로 CER을 잰다.
   - TTS: 같은 답 문장 10개를 클라우드 TTS 3~4곳과 우리 TTS(107 H2-D, LFM3, 학습한 0.6B)로 만들어 함께 듣는다.
2. **차이를 보고 로컬 방법을 고른다.**
   - **STT**: 클라우드와 Qwen의 차이가 작으면 힌트·보정 규칙으로 메운다. 차이가 크면 우리 가족 문장으로 Qwen3-ASR을 추가 학습한다. 학습 데이터는 우리가 녹음한 소리만 쓴다.
   - **TTS**: 원하는 목소리와 억양 수준을 정한 뒤 Qwen3-TTS 0.6B/1.7B를 학습한다. 오늘 밤 하는 H2-D 학습이 그 첫 단계다.
3. **주의: 클라우드 TTS가 만든 소리로 우리 모델을 학습시키는 건 대개 약관상 안 된다.** ElevenLabs 사용 정책 12항이 그렇다. OpenAI·Google도 비슷한 조항이 있을 수 있어 확인이 필요하다. 그래서 클라우드 TTS는 **비교 기준(듣기)으로만** 쓴다. 로컬 학습 재료는 우리 목소리(H2-D)나 권리를 확보한 녹음(계약한 성우, AI Hub)이다.

## 실제로 재려면 필요한 것 (사용자 확인)

- **API 키**: 어느 업체를 시험할지 정하고 키를 받는다. 키는 환경변수나 키체인으로만 쓰고 코드와 문서에는 적지 않는다.
- **녹음을 밖으로 보내도 되는지**: 11/13 녹음은 사용자 목소리다. 보낼 업체마다 저장·학습 사용 조건을 확인한다. Replicate는 1시간 뒤 삭제, DeepInfra는 ZDR 표시가 있다.
- **ElevenLabs**: 계정과 키는 있지만, 쓸 때마다 사용자 허락을 받는다.

## 출처

- 파트 A: [GigaSpeechBench(한국어 포함)](https://arxiv.org/pdf/2606.28884), [AssemblyAI 2026 정확도](https://www.assemblyai.com/blog/how-accurate-speech-to-text), [ElevenLabs 가격](https://elevenlabs.io/pricing/api), [ElevenLabs 실시간 STT](https://elevenlabs.io/realtime-speech-to-text), [Soniox 한국어 비교](https://soniox.com/compare-stt/soniox-vs-deepgram/korean), [Deepgram 한국어](https://deepgram.com/product/speech-to-text/korean), [OpenAI 가격](https://developers.openai.com/api/docs/pricing?no_head=1), [Google TTS 가격](https://cloud.google.com/text-to-speech/pricing), [Chirp 3 HD](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd?hl=ko), [Typecast API](https://typecast.ai/kr/developers/api/), [Typecast 복제 API](https://typecast.ai/kr/learn/voice-cloning-api/), [Supertone API](https://www.supertone.ai/ko/api), [CLOVA Voice](https://guide.ncloud-docs.com/docs/clovavoice-overview), [ElevenLabs 금지 사용 정책](https://elevenlabs.io/use-policy)
- 파트 B(Codex): [Modal 가격](https://modal.com/pricing), [Modal 지역](https://modal.com/docs/guide/region-selection), [RunPod Serverless](https://www.runpod.io/product/serverless), [HF 가격](https://huggingface.co/docs/inference-endpoints/pricing), [Baseten 가격](https://www.baseten.co/pricing/), [GCP GPU 지역](https://docs.cloud.google.com/compute/docs/regions-zones/gpu-regions-zones), [DeepInfra ASR](https://deepinfra.com/models/automatic-speech-recognition), [Replicate qwen3-tts](https://replicate.com/qwen/qwen3-tts), [Replicate 데이터 보관](https://replicate.com/docs/topics/predictions/data-retention), [fal Qwen3-TTS](https://fal.ai/models/fal-ai/qwen-3-tts/text-to-speech/1.7b), [알리바바 Model Studio 가격](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/model-pricing), [vLLM-Omni 음성 API](https://docs.vllm.ai/projects/vllm-omni/en/stable/serving/speech_api/)

## 관련 문서

- [TTS 학습 후보와 데이터](tts-training-research.md)
- [음성 모델 비교](voice-models.md)
- [공유 작업판](WORKBOARD.md)
