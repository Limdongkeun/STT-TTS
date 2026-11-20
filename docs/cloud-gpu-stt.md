# 클라우드 GPU에 STT(Qwen 한국어판) 올리기 — 구글 클라우드 (2026-11-19)

> 사용자 개인 구글 계정(유료 전환, 크레딧 약 40만 원)의 프로젝트 `project-d100dbdb-4028-4968-b68`.
> 다음 주 다른 프로젝트로 이식할 때 STT를 맥 밖에서 쓰려고 만들었다. 운영으로 갈 때는 회사 계정으로 옮기는 것을 검토한다.

## 지금 상태

| 항목 | 값 |
|---|---|
| 서버 | `familybot-stt-l4` · 서울 `asia-northeast3-b`(11/20 a구역 스팟 부족으로 옮김) · `g2-standard-4`(4코어·16GB) + NVIDIA L4 24GB · **스팟**(회수되면 정지로 남음) |
| 디스크 | 100GB pd-balanced · 이미지 `pytorch-2-9-cu129-ubuntu-2204-nvidia-580`(드라이버 580, CUDA) |
| 자동 켜고 끄기 | 일정 `weekday-9-18-kst`: 평일 9시 켜짐 / 18시 꺼짐(Asia/Seoul) |
| STT | `~/stt`(우리 `server/app` 그대로) + 모델 `~/stt/.models/qwen3_asr_1.7b_ko`(4.4GB). systemd `familybot-stt`가 `run.sh`로 `127.0.0.1:8002`에 띄운다. 11/20부터 `venv-vllm`(qwen-asr[vllm] 0.0.6, vLLM 0.14.0, torch 2.9.1 cu128) + `ASR_BACKEND=vllm`. 옛 방식 `venv`(transformers)도 남겨 둠. `familybot-stt-warmup`이 켤 때 한 번 불러 모델을 미리 읽힌다 |
| 바깥 주소 | `https://34-50-48-66.sslip.io/stt`·`/health`만(Caddy, 인증서 자동). 머리 `X-Stt-Key` 필요(없거나 틀리면 401, 다른 주소 404). 열쇠는 맥 키체인 `familybot-stt-api-key`, 서버 `/etc/caddy/stt.env`(root:caddy 640). Caddy 접속 기록은 끔(열쇠가 기록에 남지 않게) |
| 감시 | Cloud Scheduler(서울) `familybot-stt-keepalive`: 평일 9~17시 10분마다 start(꺼져 있으면 켬, 9시 켜기 실패도 다시 시도) / `familybot-stt-night-stop`: 매일 23시 stop. 서비스 계정 `familybot-vm-scheduler`(이 서버에만 instanceAdmin) |
| 접속 | SSH 사용자 `teddy`, 맥 열쇠 `~/.ssh/gcp_familybot`. 고정 외부 IP `34.50.48.66`(예약 `familybot-stt-ip`, 서울 리전) |
| 방화벽 | `familybot-stt-https`: 태그 `familybot-stt` 서버에 80·443 열기(HTTPS 앞단용, 아직 그 포트에서 듣는 프로그램 없음). SSH 22는 기본 규칙 |
| 예산 | 결제 계정 예산 `familybot-monthly-50k`: 월 5만 원, 50·90·100%에서 메일(알림만, 자동으로 멈추지 않음) |

## 11/19 시험

- 평가 녹음 12개를 맥에서 SSH 터널로 보냄: **맥과 글자까지 같은 결과 12/12**, 한 문장 서버 처리 중앙 **0.66초**, 맥에서 왕복 0.7초(맥 M4 0.76초와 비슷). 첫 요청은 모델 읽기로 15.8초.
- 처음엔 GPU 커널을 만들 파이썬 헤더가 없어 500 오류 → `python3.10-dev`·`build-essential` 설치로 해결.
- 같은 L4로 더 빠르게 하려면 vLLM으로 돌린다(실시간 받아쓰기도 vLLM에서만 됨).
- 17:30~17:39 다시 켜기 10번 모두 실패: "zone does not have enough resources"(서울 a구역 스팟 L4 없음). 사용자 결정: 오늘은 두고 다음 날 9시 자동 켜기를 기다린다. 계속 실패하면 일반 L4(평일 9~18시 월 약 24만 원) 또는 b구역 이동을 다시 고른다.

## 11/20 시험

- 9시 자동 켜기와 손으로 4번 모두 a구역 스팟 부족 → 사용자 결정으로 b구역으로 옮김(스냅샷 `familybot-stt-snap-1120`에서 같은 이름·같은 고정 IP로 새로 만들고 a구역 서버·디스크는 지움). b구역은 바로 켜짐.
- 바깥 주소(HTTPS+열쇠)로 맥에서 12개: transformers 때 전체 0.76초(서버 0.66초) → **vLLM 전체 0.50초(서버 0.29초)**, 글자는 맥과 12/12 같음.
- 같은 서버 안에서 받아 적기만: transformers 0.63초 → vLLM 0.20초(약 3배). 서버 0.29초에는 ffmpeg 변환·파일 읽기가 더 들어 있다.
- vLLM 처음 실행 오류 두 가지: 스크립트에 `if __name__ == "__main__"`이 없으면 엔진 프로세스가 못 뜸 / 기본 최대 길이(65536)는 KV 캐시가 모자람 → `max_model_len=4096`.
- 맥 서버 STT 고르기에 `qwen3-asr-ko-cloud`(클라우드 Qwen 한국어) 추가: 맥 8012 임시 서버로 끝까지 확인(0.40~0.51초).

- 11/20 12:15 사용자 요청으로 끔: 서버 정지 + 감시 작업 멈춤(`familybot-stt-keepalive` PAUSED). 월요일 9시 일정은 그대로라 그때 켜지지만, 다시 켤 때 감시 작업도 다시 켜야(resume) 낮에 회수돼도 다시 켜진다.

## 비용(서울, 원화 가격표 기준)

| 구성 | 시간당 |
|---|---|
| g2-standard-4 + L4 일반 | 약 1,220원 |
| g2-standard-4 + L4 스팟(지금) | 약 370원 |
| n1-standard-4 + T4 일반 | 약 820원 |
| 디스크 100GB | 월 약 1만 7천 원(꺼 둬도 나감) |

- 평일 9~18시 스팟: 월 약 8만 원. 24시간 일반 L4: 월 약 90만 원.

## 바꾼 설정(이 프로젝트)

- API 켬: Compute Engine, Cloud Billing, Cloud Quotas, Billing Budgets, Cloud Resource Manager, Org Policy
- GPU 할당량 `GPUS_ALL_REGIONS` 0 → 1(무료 체험일 때 자동 거절 → 유료 전환 뒤 승인)
- 조직 정책 `compute.vmExternalIpAccess`: 이 프로젝트에서 **이 서버 한 대만** 외부 IP 허용
- Compute 서비스 에이전트에 `roles/compute.instanceAdmin.v1`(일정이 켜고 끄려면 필요)
- 로그인: 관리 계정 새로 고침 토큰은 맥 키체인 `google-cloud-admin-refresh-token`(STT용 `google-stt-refresh-token`과 따로)

## 쓰는 법

- 켜기·끄기: 콘솔 → Compute Engine → VM 인스턴스 → `familybot-stt-l4`. 또는 Claude에게 "STT 서버 켜/꺼"(평일 낮에 끌 땐 감시 작업도 멈춘다).
- 다른 프로젝트에서 부르기: `POST https://34-50-48-66.sslip.io/stt`, 머리 `X-Stt-Key`, multipart `audio`(wav·m4a 등 ffmpeg가 읽는 꼴, 20MB까지) + `engine=qwen3-asr-ko` → `{"text","language","engine","elapsedMs"}`. 서버가 꺼져 있으면 연결 실패.
- 맥에서 시험: `ssh -i ~/.ssh/gcp_familybot -N -L 18002:127.0.0.1:8002 teddy@<외부 IP>` 를 열고 `http://127.0.0.1:18002/stt`로 보낸다.
- 서버 로그: `journalctl -u familybot-stt -f`

## 이식 전에 할 일

- [x] 고정 외부 IP 예약(34.50.48.66)
- [x] 바깥에서 부를 STT 주소: Caddy HTTPS + 열쇠 + `/stt`·`/health`만(11/20)
- [x] 스팟 감시 10분 + 매일 23시 안전 끄기(11/20). 평일 낮에 일부러 끌 땐 `familybot-stt-keepalive`를 멈춘다
- [ ] 앱 안내 문구: "STT 서버는 평일 9~18시에만 켜져요"(그 밖의 시간은 요청하면 켬)
- [x] 켤 때 미리 부르기(11/20)
- [ ] 폰에서 실제 걸리는 시간 재기(앱에서 '클라우드 Qwen 한국어' 고르기). 11/20부터 앱이 맥을 거치지 않고 클라우드로 바로 보낸다(`app/src/cloudStt.ts`, `.env`의 EXPO_PUBLIC_STT_CLOUD_URL·KEY). 목록 자체는 맥 8002 /health 에서 온다
- [x] vLLM(11/20): 별도 venv, `ASR_BACKEND=vllm`, GPU 45%·길이 4096. 실시간 스트리밍은 그다음(앱 수정 필요)
- [ ] 운영이면 스팟 대신 일반 L4, 회사 계정으로 옮기기 검토
- [ ] 학습(LoRA)도 이 서버에서: 다음 주 팀원 녹음이 쌓이면 `server/finetune` 도구 사용
