# 클라우드 GPU에 STT(Qwen 한국어판) 올리기 — 구글 클라우드 (2026-11-19)

> 사용자 개인 구글 계정(유료 전환, 크레딧 약 40만 원)의 프로젝트 `project-d100dbdb-4028-4968-b68`.
> 다음 주 다른 프로젝트로 이식할 때 STT를 맥 밖에서 쓰려고 만들었다. 운영으로 갈 때는 회사 계정으로 옮기는 것을 검토한다.

## 지금 상태

| 항목 | 값 |
|---|---|
| 서버 | `familybot-stt-l4` · 서울 `asia-northeast3-b`(11/20 a구역 스팟 부족으로 옮김) · `g2-standard-4`(4코어·16GB) + NVIDIA L4 24GB · **스팟**(회수되면 정지로 남음) |
| 디스크 | 100GB pd-balanced · 이미지 `pytorch-2-9-cu129-ubuntu-2204-nvidia-580`(드라이버 580, CUDA) |
| 자동 켜고 끄기 | 11/20부터 요청할 때만 켬. 두 서버 모두 일정 `stop-18-23-kst`(매일 18시·23시 끄기). (처음엔 `weekday-9-18-kst` 평일 9시 켜짐/18시 꺼짐) |
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

## 11/20 오후: 일반 L4 예비 서버

- 15:45 다시 켜려 했으나 b구역도 스팟 L4 부족. 사용자 결정: 스팟은 두고, **스팟이 안 될 때만 쓰는 일반(on-demand) L4 서버**를 하나 더 둔다.
- 스팟 서버를 일반으로 바꾸기는 구글이 막음(`For preemptible, only allowed provisioning_model value is SPOT`) → 스냅샷 `familybot-stt-snap-1120b`로 새로 만듦.
- 예비 서버 `familybot-stt-l4-std`: 서울 b구역, g2-standard-4 + L4, STANDARD(회수 없음, automaticRestart), 일정 `stop-18-23-kst`(매일 18시·23시 끄기만, 켜기는 손으로). 조직 정책에 이 서버도 외부 IP 허용.
- 고정 IP 34.50.48.66 은 **켜져 있는 쪽에 붙인다**(한 번에 하나만). 지금은 예비 서버에 붙어 있고 스팟 서버에는 없다 → 스팟을 다시 쓰려면 IP를 스팟으로 옮겨야 한다(18시 이후 자동으로 옮기는 예약은 아직 없음).
- GPU 할당량이 1개라 두 서버가 동시에 켜지지 않는다(돈도 하나만).
- 예산 알림을 월 25만 원으로 올림(`familybot-monthly-250k`).
- **vLLM 동시 요청 멈춤 고침:** 바깥 주소로 3개를 동시에 보내면 2개가 30초 넘게 멈췄다(첫 부팅 때도 같은 증상). 동기 vLLM 을 여러 요청 스레드가 함께 불러서다 → `Qwen3AsrEngine` 이 받아 적기를 한 번에 하나씩 하도록 잠금(`_run_lock`). 고친 뒤 동시 5개 0.6~1.3초, 3개 0.4~0.7초 모두 성공. **예비 서버에만 올림 — 스팟 서버 디스크는 다음에 켤 때 같은 파일을 올려야 한다.**
- 일반 L4 비용: 시간당 약 1,220원(평일 9~18시면 월 약 24만 원).
- 16:10 사용자 결정(**요청할 때만 켜기**): 스팟 서버의 평일 9시 자동 켜기 일정(`weekday-9-18-kst`)을 떼고, 두 서버 모두 `stop-18-23-kst`(매일 18시·23시 끄기만)를 단다. 감시 작업 `familybot-stt-keepalive`는 멈춤. 켜 달라고 하면: 스팟 먼저 켜 보고(IP를 스팟으로 옮기고, 스팟 디스크에 `qwen3_asr.py` 잠금 수정 올리기), 자리가 없으면 예비 일반 L4를 켠다.

## 11/24 a구역으로 옮김

- 13:25 새 앱(secretary-ai-test) 시험용으로 켜 달라는 요청(사용자 확인 '스팟 먼저'). b구역은 **스팟도 일반 L4도 자리 없음**(`ZONE_RESOURCE_POOL_EXHAUSTED`, 일반은 STOCKOUT).
- 사용자 결정 'a구역에 복사': 예비 서버 디스크 스냅샷 `familybot-stt-snap-1124` → a구역에 같은 이름 `familybot-stt-l4-std`(디스크 `familybot-stt-l4-std-a`, 100GB pd-balanced, 같은 설정·태그·`stop-18-23-kst`·ssh 열쇠). 고정 IP 34.50.48.66 을 b구역 예비 서버에서 떼어 a구역 서버에 붙임(같은 리전이라 주소 그대로).
- 확인: `/health` 열쇠 있으면 200·없으면 401, `/stt` wav·m4a 모두 맞게 받아 적음(학습 모델 ft1120, 받아 적기 0.23초, 왕복 0.3~0.5초). **스냅샷에서 만든 디스크는 처음 읽힐 때 느려서 첫 1~2번이 60초 초과·13초**, 그 뒤 정상.
- 남은 것: b구역 예비 서버(꺼짐, IP 없음)와 그 디스크(월 약 1.7만 원)는 그대로 둠. 스팟 서버는 b구역 그대로(원래 모델, IP 없음). 정리할지는 사용자 결정 대기.
- 15:20 새 앱 세션이 "/health 의 sttModel 이 원래 모델"이라고 물음 → 서버에서 확인하니 실제로는 학습 모델(ft1120, vLLM)로 돈다. `/health`가 코드에 박힌 이름을 보여 준 표시 버그. 맥 코드는 고침(로컬 폴더면 폴더 이름, `main.py` `stt_model_label`). 사용자 결정: **다음에 켤 때 `app/main.py`를 서버에 올린다**(지금 올리면 1~2분 멈춤). 새 서버라 SSH 접속 지문이 바뀜 → 시리얼 콘솔 지문과 같은지 확인 후 등록.
- 지금 서버 목록: a `familybot-stt-l4-std`(일반, IP 있음) · b `familybot-stt-l4-std`(일반, 꺼짐) · b `familybot-stt-l4`(스팟, 꺼짐). GPU 할당량 1개라 하나만 켜진다.

## 11/20 첫 실제 녹음 학습 (시험 학습)

- 와치 '음성 모으기' 녹음 80개(6.5분, 5명)를 keep=1 로 받음(서버에 남김). 맥 검사로 26개 걸림(앞 잘림 의심 다수 — 와치 앱 녹음 앞 여유가 아직 0초인 것들), 제외 목록 1개 → 학습 53개(약 4분).
- 예비 일반 L4에서 ms-swift 4.6.1(`venv-swift`) LoRA: r16, lr 1e-4, 2 epoch, 14걸음, 54초, 메모리 4.7GB. 실행 파일 `~/ft/train.sh`, 결과 `~/ft/run/`.
- 평가 76개(같은 L4, transformers): 학습 전 **0.1468** → 1 epoch 0.1477 → **2 epoch 0.1396**(나아짐 6·나빠짐 1·같음 69). 나아짐: C2 '보여'→'뭐야'(3번), D7 '사업비'→'생활비', D15 '남편의'→'남편이', C5 숫자 꼴. 나빠짐: D8 '팔만 사천 원'→'84000원'(숫자 꼴). C3 그대로.
- 판단 기준(CER 낮아짐·C3 안 나빠짐)을 넘어 **예비 서버 STT 를 학습 모델로 바꿈**: `~/stt/.models/qwen3_asr_1.7b_ko_ft1120`, `run.sh` 에 `ASR_KO_MODEL_ID`(원래 것은 `run.sh.base`). vLLM 으로 0.24초 확인.
- 학습 정답에 물음표가 없어 학습 모델은 문장 끝 물음표를 안 붙인다(CER 에는 영향 없음, 화면 글만 다름).
- 주의: 데이터가 4분뿐이라 효과가 작고 흔들릴 수 있다. 녹음이 쌓이면 다시 학습한다. 서버의 녹음은 아직 안 지웠다(--final 안 함).
- `run_stt_train.sh` 의 마지막 체크포인트 고르기(`sort -t- -k2 -n`)가 폴더 이름의 날짜 때문에 틀린 것(checkpoint-7)을 골랐다 → 이번엔 checkpoint-14 를 따로 합쳐 잼. 스크립트 고칠 것.
- **스팟 서버 디스크는 아직 원래 모델·옛 코드다.** 스팟을 켜면 학습 모델 폴더, `run.sh`, `qwen3_asr.py` 잠금 수정을 옮겨야 한다.
- 16:25 두 서버 모두 끔(감시 작업도 멈춤).

## 학습 기록 내보내기(새 앱 어드민, 11/24)

- 학습 한 번의 재료는 맥 `server/.train/stt-ko/runs/<id>/`: `run.json`(언제·어디서·데이터 묶음·평가 파일·배포), ms-swift `trainer_state.json`·`args.json`·`logging.jsonl`, `eval/*.json`. 11/20 1차는 클라우드 `~/ft/`, `~/stt/.train/stt-ko/eval/`에서 받아 옴.
- `cd server && .venv/bin/python -m finetune.export_admin all` → `secretary-ai-test/out/stt/runs.jsonl`(학습 한 번에 한 줄)·`data/<묶음>.json`. 어드민은 `npm run admin:sync`로 사내 서버에 올린다. 소리·정답 글·사람 이름은 넣지 않는다.
- 다음 학습부터: 학습이 끝나면 `runs/<id>/`에 같은 재료를 모으고 `run.json`을 쓴 뒤 내보낸다(학습 스크립트에 붙이는 건 체크포인트 고르기 버그와 함께 고칠 때).

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
