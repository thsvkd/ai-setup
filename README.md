# ai-setup

ai-setup 의 기능(하네스·플러그인·스킬·MCP 설치, update-ai, 줄바꿈 키, 출력 스타일·mod·OMC HUD, AGENTS.md, 가드 훅, Orca, doctor)은 모두 [jarvis](https://github.com/thsvkd/jarvis) 로 옮겼다(2026-11-01). 이 저장소에 남은 설치 스크립트(`install.sh`·`install.ps1`·`scripts/setup.*`·`scripts/update-ai.sh`·`scripts/Update-Ai.ps1`)는 아무것도 바꾸지 않고 jarvis 를 안내한 뒤 종료 코드 1 로 끝난다.

| 하던 일 | jarvis 에서 |
| --- | --- |
| 설치(`install.sh`, 온보딩, `--stages`) | core 홈의 AI 셋업 화면, 또는 `python3 -m jarvis module setup plan --json` → `apply --json --plan-id <id>` |
| 개별 옵션(`--keybinds`·`--skills`·`--mods`·`--omc`·`--output-style`) | `bash jarvis/modules/setup/scripts/setup.sh <옵션>`(Windows 는 `setup.ps1`) |
| update-ai | `python3 -m jarvis module harness plan --json` |
| AGENTS.md | 프로젝트 폴더에서 `python3 -m jarvis agentsmd` |
| 가드 훅 · Orca · doctor | `module hooks` · `module orca` · `module doctor` |

설치 전에 알아 둘 것(사용량에 영향을 주는 mod 등)과 각 기능의 설명은 jarvis 의 `docs/setup-guide.md` 로 옮겼다. 설치 기록(`~/.claude/.claude-code-setup.json`)은 같은 키로 jarvis 가 이어서 읽으므로, ai-setup 으로 설치한 기기도 그대로 관리된다.

## 개발 · 테스트

남은 진입점의 안내는 `bash scripts/test.sh`(pytest·bats·Pester)로 확인한다.

## 라이선스

MIT. `LICENSE` 를 본다.
