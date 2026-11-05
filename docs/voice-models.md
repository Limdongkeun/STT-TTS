# 음성 모델 정리 (STT · TTS · 음성 LLM)

- 확인일: **2026-11-04**. 공식 모델 카드, 공식 GitHub README, 기술 보고서만 봤다. 공식 출처에 없는 항목은 "명시 없음"으로 적었다.
- 결정 배경과 시험 흐름은 [handoff-voice.md](handoff-voice.md)에 있다. 직접 잰 결과는 `results/`에 남기고, 이 문서의 "직접 잰 값" 칸에 옮긴다.
- 모델 카드는 자주 바뀐다. 다시 쓸 때는 출처 링크를 열어 확인한다.

## 1. 한눈에

| 역할 | 지금 | 다음 / 비교 | 제외 |
|---|---|---|---|
| STT | **폰 기본 STT** (실기기 동작 확인) | **Qwen3-ASR 1.7B / 0.6B**, 한국어 파인튜닝판 `TeamUNIVA/qwen3_asr_1.7b_ko` | — |
| TTS | mock('삐') | **Qwen3-TTS CustomVoice Sohee 1.7B / 0.6B** (1순위), **Fun-CosyVoice3-0.5B** (비교), Chatterbox Multilingual (참고) | Fish S1-mini, Kokoro, Supertonic 3 |
| 음성 LLM | 안 씀 | 나중에 검토: A.X K2 Raon-Speech, HyperCLOVA X SEED Omni 8B, Qwen3-Omni | — |

**이번 확인에서 새로 알게 된 것**
1. **Qwen3-TTS 스트리밍은 공개 패키지로는 안 된다.** 첫 소리 97~101ms는 Qwen 내부 vLLM 엔진에서 잰 값이다. `qwen-tts` 예제는 완성된 음성만 돌려준다. vLLM-Omni도 아직 오프라인 추론만 된다. 그래서 6단계 "첫 소리까지 시간"은 **문장 단위로 끊어 읽기**로 줄여야 한다.
2. **CosyVoice3 Hugging Face 페이지에 "for academic purposes only"라는 문구가 있다.** 라이선스 표기는 Apache-2.0이다. 상업 서비스에 쓰기 전에 이 문구의 뜻을 확인해야 한다.
3. **Supertonic 3은 제외한다.** GitHub 레포가 2026-09-09에 아카이브되어 지원이 끝났다. 회사 청산은 이데일리(2026-07-27) 보도로 확인했다.
4. **Kokoro는 한국어를 지원하지 않는다.** 공식 목소리 목록 9개 언어에 한국어가 없다.
5. **Qwen3-ASR 스트리밍은 vLLM 백엔드에서만 된다.** NVIDIA GPU 서버가 필요하다. 맥미니에서는 녹음을 다 받고 한 번에 인식하는 방식만 시험한다.
6. **TeamUNIVA 한국어판에 후속 `qwen3_asr_1.7b_ko`가 나왔다.** 한국어 CER은 기본 6.86% → beta 5.37% → ko 4.83%다. 만든 쪽이 직접 잰 값이다.

## 2. STT

| 모델 | 크기 | 한국어 | 라이선스 | 스트리밍 | 한국어 성능 (출처 기준) | 상태 |
|---|---|---|---|---|---|---|
| 폰 기본 STT (`expo-speech-recognition`) | — | 됨(ko-KR) | iOS·안드로이드 OS 기능 | 중간 결과 바로 표시 | 직접 잴 것(2단계) | **지금 사용** |
| Qwen3-ASR-1.7B | 이름 1.7B (HF 표시 2B) | 됨(30개 언어 중 ko) | Apache-2.0 | 오프라인 + 스트리밍(vLLM만, 배치·타임스탬프 없음) | 한국어 단독 수치 명시 없음. Fleurs 12개 언어 평균 WER 4.90 | 4단계 |
| Qwen3-ASR-0.6B | 이름 0.6B (HF 표시 0.9B) | 됨 | Apache-2.0 | 위와 같음 | 한국어 단독 명시 없음. Fleurs 평균 7.57 | 4단계 비교 |
| `TeamUNIVA/qwen3_asr_1.7b_ko` | 1.7B 기반 | 한국어 특화 | Apache-2.0 | 명시 없음 | 한국어 합계 CER **4.83%** (기본 6.86%) | 4단계 후보 |

**STT 메모**
- TeamUNIVA 데이터셋별 CER(기본 → ko): clova_call 4.48 → 2.83%, ksponspeech 8.65 → 5.94%, common_voice_ko 7.19 → 6.03%. 영어는 조금 나빠진다(LibriSpeech 2.50 → 2.77%).
  - clova_call은 전화 음성이라 자동 전화 대비에 참고가 된다.
  - 학습 데이터는 "Korean speech data"라고만 적혀 있다.
- 폰 기본 STT: 품질을 우리가 고칠 수 없다. 음성이 애플·구글로 간다. 자동 전화에는 쓸 수 없다.

출처
- https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- https://huggingface.co/Qwen/Qwen3-ASR-0.6B
- https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko
- https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko_beta

## 3. TTS 비교표

| 모델 | 크기 | 한국어 | 라이선스 / 상업 이용 | 목소리 방식 | 스트리밍 · 지연 (출처 기준) | 출력 | 주의 | 상태 |
|---|---|---|---|---|---|---|---|---|
| **Qwen3-TTS-12Hz-1.7B-CustomVoice** | 이름 1.7B (HF 2B) | 됨(10개 언어). 한국어 목소리 **Sohee**("Warm Korean female voice with rich emotion") | Apache-2.0 / 가능 | 정해진 목소리 9개 + 말투 지시(instruct). 복제는 Base, 목소리 설계는 VoiceDesign이라는 다른 모델 | 첫 소리 101ms·RTF 0.313(Qwen 내부 vLLM, GPU 이름 없음). **공개 패키지는 스트리밍 없음** | 샘플레이트 명시 없음 | 예제는 CUDA·bf16·FlashAttention2 기준. 한국어 WER **1.741**(README 표에서 최고) | **1순위** |
| **Qwen3-TTS-12Hz-0.6B-CustomVoice** | 이름 0.6B (HF 0.9B) | 됨. Sohee | Apache-2.0 / 가능 | 위와 같음 | 첫 소리 97ms·RTF 0.288(같은 조건) | 명시 없음 | 한국어 WER **3.053**(1.7B보다 나쁨) | 1순위 비교 |
| **Fun-CosyVoice3-0.5B-2512** | 0.5B | 됨(9개 언어) | Apache-2.0 표기. **HF 페이지에 "for academic purposes only" 문구 있음** → 상업 이용 확인 필요 | 제로샷 복제 + 지시(언어·감정·속도·크기). 정해진 목소리 없음 | 양방향 스트리밍, "as low as 150ms"(조건 없음) | 명시 없음 | 빠른 실행은 vLLM·TensorRT(NVIDIA). 한국어 벤치마크 명시 없음. 정해진 목소리가 없어 쓰려면 기준 목소리 녹음이 필요하다 | 비교 |
| **Chatterbox Multilingual** (Resemble AI) | 0.5B | 됨(23개 언어) | MIT / 가능 | 참조 음성으로 제로샷 복제 | 오픈 모델 수치 명시 없음("sub 200ms"는 유료 서비스) | 24kHz(소스 코드) | **모든 출력에 Perth 워터마크.** 참조 음성 언어가 다르면 억양이 따라온다 | 참고 |
| Supertonic 3 (Supertone) | 약 99M (ONNX) | 됨(31개 언어) | 코드 MIT, 가중치 OpenRAIL-M(사용 제한 조항) | 정해진 목소리만 | 스트리밍 명시 없음. CPU에서 RTF 0.3(e-reader) | 44.1kHz | **레포 아카이브(2026-09-09), 회사 청산** → 지원 없음 | **제외** |
| OpenAudio S1-mini (Fish Audio) | 0.5B | 됨(13개 언어) | 가중치 CC-BY-NC-SA-4.0 → **상업 불가** | 카드에 명시 없음 | 명시 없음 | 명시 없음 | 로그인·동의 필요(gated). 공식 문서가 S2-Pro로 넘어감 | **제외** |
| Kokoro-82M | 82M | **안 됨**(9개 언어에 한국어 없음) | Apache-2.0 / 가능 | 정해진 목소리 54개 | 명시 없음 | 24kHz | espeak-ng·misaki 필요 | **제외** |

**TTS 메모**
- Qwen3-TTS의 "12Hz"는 음성 토큰 속도이고, 출력 샘플레이트가 아니다. 실제 샘플레이트는 3단계에서 `/tts` 응답의 `sampleRate`로 확인한다.
- 목소리 정책: 자녀 목소리 복제는 하지 않는다(보이스피싱 오해). 그래서 정해진 목소리가 있는 CustomVoice를 우선한다. CosyVoice3이나 Chatterbox를 쓰려면 동의받은 성우 목소리가 필요하다.

출처
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
- https://github.com/QwenLM/Qwen3-TTS
- https://arxiv.org/html/2601.15621v1 (Table 2)
- https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512
- https://github.com/FunAudioLLM/CosyVoice
- https://huggingface.co/ResembleAI/chatterbox
- https://github.com/resemble-ai/chatterbox
- https://huggingface.co/Supertone/supertonic-3
- https://github.com/supertone-inc/supertonic
- https://en.edaily.co.kr/news/eda202607275504/
- https://huggingface.co/fishaudio/openaudio-s1-mini
- https://huggingface.co/hexgrad/Kokoro-82M
- https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

### 3단계 직접 잰 값 (맥미니, 같은 문장 B1~B15)

| 모델 | 평균 elapsedMs | RTF | 틀린 발음 수 | 자연스러움(1~5) | 샘플레이트 | 메모 |
|---|---|---|---|---|---|---|
| Qwen3-TTS 1.7B Sohee | | | | | | |
| Qwen3-TTS 0.6B Sohee | | | | | | |
| CosyVoice3 0.5B | | | | | | 기준 목소리 필요 |

맥미니(mps)는 느리다. 여기서는 품질만 비교하고, 속도는 NVIDIA 서버에서 다시 잰다.

## 4. 통합 음성 LLM (나중에 검토, 이번에 모델 카드는 확인 안 함)

| 모델 | 메모 (handoff 조사 기준) |
|---|---|
| A.X K2 Raon-Speech 21B-A3B (크래프톤+SKT, 2026-07) | 한국어 점수 0.72로 1위(회사 발표). 라이선스 확인 필요 |
| HyperCLOVA X SEED Omni 8B (네이버) | 한국어에 강하다. 네이버와 경쟁하는 서비스면 별도 허가가 필요하다는 조항이 있다 |
| Qwen3-Omni 30B-A3B | Apache-2.0. 말 출력 10개 언어에 한국어가 있다. Instruct만 말로 답한다 |

상시 듣기, 끼어들기, 자동 전화는 파이프라인(VAD + ASR + LLM + TTS)으로도 만들 수 있다. 음성 LLM은 지연과 자연스러움이 문제가 될 때 비교한다.
