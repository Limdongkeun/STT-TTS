# STT-TTS project context

Read [docs/project-sync.md](docs/project-sync.md) for the file map, request flows, and verified baseline.

The user requested that the shared policy at `/Users/teddy/Desktop/UPTIVE/LLM-코딩/core_instructions.md` and every Markdown file under its `packs/` directory be consulted and retained. Use the current originals when available; [docs/shared-instructions-snapshot.md](docs/shared-instructions-snapshot.md) contains the complete reference copy. Apply relevant rules within the active instruction hierarchy. For work inside `app/`, also read `app/AGENTS.md`.

## 공유 작업판 (Claude · Codex)

Claude와 Codex는 [docs/WORKBOARD.md](docs/WORKBOARD.md) 하나를 같이 보며 진행한다. Claude는 루트 `CLAUDE.md`(`@AGENTS.md`)로 이 파일을 읽는다.

1. 작업을 시작하기 전에 `docs/WORKBOARD.md`를 읽는다.
2. 작업을 잡으면 "진행 중"에 `누가 · 무엇 · 시작 시각(KST) · 건드리는 파일`을 적는다. 다른 쪽이 잡은 파일은 건드리지 않는다.
3. 끝나면 "진행 중"에서 그 줄을 지우고, "작업 기록" 맨 위에 한 줄(날짜 시각 · 누가 · 한 일 · 검증 결과)을 더한다. 바뀐 상태가 있으면 "다음 할 일", "정한 것", "검증 기준선"도 고친다.
4. 작업판에는 비밀값을 적지 않는다.

## Agent skills

### Issue tracker

이슈와 스펙은 `.scratch/`에 마크다운으로 둔다(로컬 마크다운). 커밋하고 푸시해서 공유한다. See `docs/agents/issue-tracker.md`.

### Triage labels

기본 다섯 가지 상태 이름(`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`)을 쓰고, 이슈 파일의 `Status:` 줄에 적는다. See `docs/agents/triage-labels.md`.

### Domain docs

단일 구성(single-context): 루트 `GLOSSARY.md` + `docs/adr/`. 필요해질 때 만든다. See `docs/agents/domain.md`.
