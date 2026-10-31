# PRD

> 범위: 2026-10-13 에 승인한 ai-setup 편입 범위만 다룬다. 기존 기능(가드 훅, AGENTS.md, 키바인딩, 번들 스킬, OMC HUD, outputStyle, mods)은 아직 이 문서에 없다.
> 근거: `.omc/research/2026-10-13-ai-setup-survey/` (장비 3대 조사와 1차 자료 확인, 로컬 전용이라 커밋하지 않는다).

## 문제

AI 하네스와 그 주변 도구의 설정이 장비마다 손으로 관리되고 있어서 서로 어긋난다.

- 업데이트 스크립트가 장비(Linux·macOS·Windows)마다 따로 있어서, 버전과 기능이 서로 다르다.
- 플러그인과 스킬 구성이 장비마다 다르고, 이름이 바뀌기 전의 mattpocock 스킬 복사본이 lock 파일 밖에 남아 있다.
- 새 장비를 셋업할 때 어떤 하네스·도구·플러그인·스킬·MCP 를 깔아야 하는지 기록이 없다.
- 설정이 어긋났는지(중복 설치, 은퇴한 훅의 잔존, 평문 시크릿)를 확인할 수단이 없다.

비용은 장비를 여러 대 운용하는 사용자 한 명이 치른다. 장비를 오갈 때마다 차이를 기억하고 손으로 맞춰야 한다.

## 목표

- 한 레포에서 하네스·도구·플러그인·스킬·MCP 기본 구성을 선언하고, 어느 장비에서든 같은 명령으로 그 구성을 재현한다.
- 업데이트 절차를 한 벌로 통합해 세 장비가 같은 동작을 한다.
- 현재 장비의 상태와 선언된 구성의 차이를 아무것도 바꾸지 않고 확인할 수 있다.

## 비목표

- 다른 앱이 생성·관리하는 파일(Orca, herdr, Paseo, Aside, ahakey 의 훅·스킬·플러그인)은 관리하지 않는다. 그 앱이 재설치할 때 덮어쓰기 때문이다. 컨텍스트 맵은 CodeGraph 만 설치·갱신한다. 이 셋업이 기록하지 않은 예전 컨텍스트 맵 훅은 지우지 않는다.
- 장비·계정 전용 구성(개인 MCP 서버, Codex·Grok 프로젝트 신뢰 목록, 로컬 모델 게이트웨이, 개인 스킬·에이전트)은 넣지 않는다. Jarvis 는 예외다. gateway 또는 core 를 명시했을 때만 사용자 유닛을 등록하고, 호스트 이름으로 역할을 고르지 않는다.
- Codex·Grok 플러그인은 벤더가 관리하므로 넣지 않는다.
- 영수증 드리프트 버그 수정은 이번 범위가 아니다. jarvis 의 doctor 가 보고만 한다.
- 시크릿 값을 저장·이동·출력하지 않는다.
- Orca 패키지·서버·스킬의 설치·업데이트·제거는 jarvis 가 맡는다(jarvis 결정 D11·D16, ORCA-12). R9 참고.
- 하네스·도구 점검(doctor)은 jarvis 가 맡는다(jarvis 결정 D11, DOCTOR-1~7). R1 참고.

## 사용자와 시나리오

- 새 장비: 사용자가 `install.sh`/`install.ps1` 원라이너를 실행하고 온보딩에서 하네스·도구·플러그인·스킬·MCP 를 고르면, 선택한 구성이 설치된다.
- 정기 업데이트: 사용자가 `update-ai` 를 실행하면 설치된 하네스·도구·플러그인이 최신으로 올라가고, 실행 중인 세션을 끊지 않는다.
- 점검: 사용자가 jarvis 체크아웃에서 `python3 -m jarvis module doctor status --json` 을 실행하면 설치 상태, 버전, 중복 설치, 드리프트, 평문 시크릿 위치(키 이름만)를 본다. `setup --doctor` 는 이 명령을 안내한다.
- 되돌리기: 사용자가 `--uninstall` 을 실행하면 이 레포가 추가한 플러그인·스킬·MCP 등록만 제거된다.

## 요구사항

| ID  | 요구사항 | 필수/선택 |
| --- | -------- | --------- |
| R1  | doctor 는 jarvis 가 맡는다(jarvis `module doctor`, DOCTOR-1~7). `--doctor`(`-Doctor`) 는 아무것도 바꾸지 않고 jarvis 를 안내한 뒤 exit 1 로 끝난다. | 필수 |
| R2  | update-ai: 설치된 하네스(claude, codex, grok, agy, gemini, opencode, copilot)와 플러그인, 도구(CodeGraph, herdr)를 업데이트한다. CodeGraph 는 npm-release 배치로 올리고 `codegraph upgrade` 는 호출하지 않는다. `--check`, `--only`, `--allow-interrupt`, lock, 전후 버전 비교를 유지한다. 실행 중 세션이 있어도 업데이트하며, 그 세션이 쓰는 파일을 지우거나 바꾸지 않는다(버전별 배치). 세션을 실제로 끊는 단계만 `--allow-interrupt` 를 요구한다. 없는 것은 설치하지 않는다. | 필수 |
| R3  | 하네스 설치: 선택한 하네스 가운데 없는 것을 공식 설치 방법으로 설치한다. 있는 것은 건드리지 않는다. | 필수 |
| R4  | 도구 설치: Tailscale(패키지만), herdr, CodeGraph, Jarvis 가운데 선택한 것을 설치한다. CodeGraph 는 `npm install -g @colbymchenry/codegraph` 만 쓰고 OMC HUD statusLine 을 바꾸지 않는다. herdr 는 목록에 있으나 기본은 꺼져 있다. Jarvis 는 gateway 또는 core 를 고른 뒤에만 클론·사용자 유닛을 등록하고, `ss` 능력 부여는 추가 확인이 있을 때만 한다. Tailscale 은 인증 키나 `tailscale up` 을 실행하지 않는다. | 필수 |
| R5  | 플러그인: 선언 목록의 Claude Code 마켓플레이스·플러그인을 user scope 로 설치한다. 기존 `--omc`, `--output-style` 은 호환을 유지한다. 플러그인으로 옮겨 간 스킬(mattpocock-skills, korean-skills)은 이 단계가 맡는다. | 필수 |
| R6  | 스킬: 플러그인이 없는 외부 스킬(archify, find-skills, microsoft-foundry)을 `skills` CLI 로 `~/.agents/skills` 에 설치하고 Claude Code 등 필요한 하네스에 연결한다. 번들 design-lab 은 현재 위치를 유지한다. | 필수 |
| R7  | MCP: CodeGraph(`codegraph serve --mcp`)를 선택된 하네스마다 user scope 로 등록한다. 패키지 설치 다음이다. `codegraph install` 은 쓰지 않는다. 토큰이 필요한 서버는 환경 변수 이름으로만 참조한다. | 필수 |
| R8  | 모든 쓰기 단계는 dry-run 과 uninstall 대칭을 지키고, 이 레포가 추가한 것만 영수증에 기록해 그것만 되돌린다. | 필수 |
| R9  | Orca 는 jarvis 가 관리한다. `--tools orca`(`-Tools orca`)·`--orca-desktop`·`update-ai orca` 는 아무것도 바꾸지 않고 jarvis 를 안내한 뒤 exit 1 로 끝난다. tools 단계와 `--stages all --uninstall` 은 Orca 를 건드리지 않고, 영수증의 `tool_installs.orca`·`tool_installs.orca_server` 는 jarvis 의 Orca 모듈이 읽고 제거하도록 남긴다. | 필수 |
| R10 | `--prune-skills`: `~/.agents/skills` 에서 lock 에 없는 실제 디렉터리를 하나씩 확인받아 휴지통으로 옮긴다. 기본 실행에는 포함되지 않는다. | 필수 |

## 성공 지표

- 세 장비에서 `update-ai --check` 의 대상 목록과 동작이 같다.
- 새 장비 하나를 원라이너와 온보딩만으로 기존 장비와 같은 플러그인·스킬·MCP 구성으로 맞출 수 있다.
- jarvis 의 doctor 가 이번 조사에서 손으로 찾은 드리프트(중복 Claude 설치, 은퇴 훅 잔존, lock 밖 스킬, 평문 시크릿 위치)를 모두 보고한다.

## 결정됨 (2026-10-13)

- D1 (Q1). uninstall 은 완전 대칭이다. 이 레포가 설치해 영수증에 기록한 하네스·도구도 제거한다. 원래 있던 것은 제거하지 않는다.
- D2 (Q2). update-ai 는 Python 한 벌로 구현하고, `update-ai.sh`·`Update-Ai.ps1` 은 얇은 래퍼로 둔다.
- D3 (Q6). sudo 가 필요한 단계는 허용한다. 실행 전에 명령을 보여 주고 sudo 프롬프트로 승인받으며, 대화형이 아니면 건너뛴다.
- D4 (Q8, 2026-10-23 개정). 인자 없이 TTY 에서 실행하면 단계를 순서대로 걷고, 각 단계는 기본 예다. 하네스 기본은 Claude Code 와 Codex 이고 grok·agy·opencode·gemini·copilot 은 목록에만 있다. Skip 하거나 산책을 마치면 카테고리 허브가 열리고, 영수증이 있는 머신은 허브부터 연다(2026-10-23 추가). 허브의 Apply 만 설치하고, Quit 이거나 TTY 가 없으면 아무것도 설치하지 않는다. 마우스 조작은 이번 범위 밖이다. `--no-onboard` 는 예전 기본 설치(훅, AGENTS.md, 키바인드, 번들 스킬)를 유지한다.
- D5 (Q9). 하네스·도구를 제거할 때 설정·인증 디렉터리(`~/.claude`, `~/.codex` 등)는 남긴다. 패키지·바이너리만 제거한다.
- D8 (Q3). 플러그인 단계를 켰을 때 기본으로 선택되는 목록은 oh-my-claudecode, fluent-korean, ponytail, codex, commit-commands, context7, typescript-lsp, pyright-lsp 이다.
- D7 (Q7). lock 밖에 남은 스킬은 doctor(지금은 jarvis)가 보고만 한다. 정리는 사용자가 명시적으로 고르는 별도 옵션(`--prune-skills`)으로만 제공한다.
- D9 (Q5). grok 1.0.50 은 Pi 5 에서 qemu 없이 동작한다(아래 메모). update-ai 에 qemu 분기를 넣지 않고, 장비 전용 래퍼도 이 레포로 가져오지 않는다.

## 미결정

- Q10. 기본 8개 밖의 플러그인 후보(i-have-adhd, mattpocock-skills, korean-skills, firecrawl, caveman, rust-analyzer-lsp 등)를 목록에 남겨 기본으로 끌지, 그리고 외부 스킬 기본값(초안: archify, find-skills, microsoft-foundry)을 무엇으로 할지. 사용자가 셋업 재료 전체 목록(inventory 보고서)을 보고 정한다. 플러그인·외부 스킬 단계를 구현하기 전에 닫는다.

### Q5 메모 — Pi 5 grok SIGILL 확인 (2026-10-13, pi5-server2)

- CPU 플래그: `sha1 sha2` 는 있고 `sha512`·`sha3` 는 없다(Cortex-A76). 하드웨어 조건은 그대로다.
- 설치된 1.0.46 과 최신 stable 1.0.50 바이너리 모두 SHA-512 명령어(`sha512h/h2/su0/su1`)를 432 개씩 담고 있다(`objdump -d`).
- 두 버전을 qemu 없이 직접 실행해도 다음은 SIGILL 없이 끝났다: `--version`, `update --check --json`, 격리 HOME 에서 `update --force-reinstall`(다운로드·검증·설치), `models`, `login`(장치 코드 발급 후 승인 대기까지).
- 사용자가 격리 HOME 에서 1.0.50 `login` 을 승인했다. 토큰 교환과 자격 증명 저장까지 `login rc=0`, 이어진 `models rc=0` 으로 SIGILL 없이 끝났다. 임시 HOME 은 실행 직후 지웠다.
- 결론: 1.0.50 에서는 해결되었다. SHA-512 명령어는 남아 있지만 런타임 디스패치로 실행되지 않는 것으로 보인다(추론). 1.0.46 은 승인 이후 경로를 확인하지 않았다.
