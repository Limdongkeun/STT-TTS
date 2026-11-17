# Maestro 시험 흐름

앱 화면 흐름을 자동으로 누르고 확인한다(2026-11-17, expo/examples `with-maestro` 방식). 앱 ID `com.uptive.stttts`.

| 파일 | 확인하는 것 | 필요한 것 |
|---|---|---|
| `home.yml` | 메인 화면(제목·대화 모드·말하기 버튼) | 앱 |
| `typed_ask.yml` | 글로 묻기 → 가스비 답 | 8002 켜짐 |
| `conversation.yml` | 대화 모드 열기 → 끝내기 → 메인으로 | 앱 |

```sh
npx expo run:ios            # 시뮬레이터에 개발 빌드 설치(처음·네이티브 바뀐 뒤)
npx expo start              # Metro
maestro test maestro/       # 전부
```

시뮬레이터에는 마이크가 없어 말하기·받아쓰기는 시험하지 않는다. 버튼 이름은 `testID`(main-title, mic-button, start-conversation, typed-question, typed-ask, conversation-face, conversation-end)로 찾는다.
