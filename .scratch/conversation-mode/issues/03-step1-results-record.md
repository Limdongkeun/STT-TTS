# 03 1단계 결과 기록

Resolution: 완료
Blocked by: (없음)
Spec: `.scratch/conversation-mode/spec.md`

## 할 일

1. `results/2026-11-04-단계1.md`를 만든다. 양식은 `docs/test-plan.md` "기록 양식"을 따른다.
   - 기기: iPhone 14 Pro, 개발 빌드(`npm run ios:device`), 서버 mock 8002(`192.168.29.179`)
   - 폰 기본 STT: "가나다라마바사아자차카타파하" 인식, 맞음
   - 답(화면용·읽기용) 고정 답이 보임. 읽기용 변환이 맞음(세 시 삼십 분, 일곱 시, 네 명)
   - 걸린 시간: 답 54ms · TTS 22ms · 합계 219ms
   - '삐' 소리: 사용자에게 들렸는지 확인한다. 사용자가 통과로 보면 통과로 적는다.
   - 참고: `results/*`는 `.gitignore`에 있어서 기본으로 커밋되지 않는다.
2. `docs/WORKBOARD.md`
   - "다음 할 일"의 1단계에 체크한다.
   - "지금 목표"를 2단계(폰 기본 STT 문장 A1~A15)나 대화 모드로 바꾼다.
   - 이미 커밋이 끝난 "정리: 커밋할지 확인" 항목을 지운다.

## Comments

- 2026-11-04 15:01 KST · Codex · iPhone 14 Pro의 mock TTS 소리를 사용자가 들었다고 확인했다. 1단계 통과를 results/2026-11-04-단계1.md와 작업판에 기록했다.
