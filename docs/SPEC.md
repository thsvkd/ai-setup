# SPEC

> 범위: 2026-10-13 에 승인한 ai-setup 편입 범위만 다룬다. 기존 기능의 계약은 아직 이 문서에 없다.
> 1차 자료 출처는 `.omc/research/2026-10-13-ai-setup-survey/research-{install,skills}.md` 에 URL 과 함께 있다(로컬 전용, 커밋하지 않는다).

## 스택과 구조

- 언어·런타임: 기존과 같다. 진입점은 bash(3.2 호환)와 PowerShell(5.1/7) 쌍이고, 설정을 고치는 로직은 Python 3.8+ 워커(`res/<x>/apply.py`)가 맡는다.
- 새 디렉터리:
  - `res/catalog.json` — 하네스·도구 카탈로그. doctor, 하네스·도구 설치, update-ai 가 같은 파일을 읽는다.
  - `res/plugins/plugins.json`, `res/plugins/apply.py`
  - `res/skills/sources.json` (기존 `res/skills/apply.py` 는 번들 스킬을 그대로 맡는다)
  - `res/mcp/servers.json`, `res/mcp/apply.py`
  - `res/doctor/doctor.py`
  - `res/update/update_ai.py` — update-ai 의 유일한 구현(D2). `scripts/update-ai.sh`·`scripts/Update-Ai.ps1` 은 Python 을 찾아 이 파일을 실행하는 래퍼다.
  - `scripts/setup_{install,plugins,mcp}.{sh,ps1}`. doctor 는 설치를 하지 않고 Python 하나만 실행하므로 워커 없이 `setup.sh`/`setup.ps1` 이 `res/doctor/doctor.py` 를 직접 부른다.

## 공개 인터페이스

| 이름 | 입력 | 출력·부작용 | 오류 |
| ---- | ---- | ----------- | ---- |
| `setup --doctor` / `-Doctor` | 없음 | 표준 출력에 점검 결과. 파일·설정·네트워크에 쓰지 않는다. | 점검 실패 항목이 있으면 exit 1, 점검 자체를 못 하면 exit 2 |
| `setup --install-harness L` / `-InstallHarness L` | `claude,codex,grok,opencode,gemini,agy,copilot,all` | 없는 하네스만 카탈로그의 공식 설치 명령으로 설치하고 영수증 `harness_installs` 에 기록 | 알 수 없는 이름은 exit 1, 설치 실패는 그 항목만 실패로 표시하고 exit 1 |
| `setup --tools L` / `-Tools L`, `--orca-desktop`, `update-ai orca` | 무엇이든 | Orca 는 jarvis 가 관리한다. 아무것도 쓰지 않고 jarvis 안내만 출력한다(아래 Orca) | exit 1 |
| `setup --stages L` | `all` 또는 쉼표 목록 | 아래 단계 순서로 액션 목록을 만든다. `--dry-run` 은 목록만 출력한다. 컨텍스트 맵은 CodeGraph npm 패키지 다음 MCP 다 | 같음 |
| `setup --prune-skills` / `-PruneSkills` | 없음 | `~/.agents/skills` 의 실제 디렉터리 가운데 lock 에 없는 것을 하나씩 보여 주고, 사용자가 승인한 것만 휴지통으로 옮긴다. 그 디렉터리를 가리키던 하네스 스킬 링크도 지운다. 기본 실행·온보딩 기본값에 포함되지 않는다(D7) | 표준 입력이 TTY 가 아니면 아무것도 옮기지 않고 exit 1. 휴지통으로 옮길 수 없으면 그 항목을 건너뛴다 |
| `setup --plugins` / `-Plugins` | `plugins.json` + 온보딩 선택 | `claude plugin marketplace add` + `claude plugin install --scope user`. 우리가 추가한 플러그인만 영수증 `plugins` 에, 마켓플레이스만 `marketplaces` 에 기록. 이미 user 범위로 설치된 플러그인은 설치·기록하지 않음 | `claude` 가 없으면 단계를 건너뛰고 경고 |
| `setup --skills` / `-Skills` (확장) | 번들 스킬 + `sources.json` | 번들은 기존대로. 외부 스킬은 `npx skills add <repo>#<ref> --skill <s> -g -a <agents> -y`. 영수증 `skills_external` | `npx` 가 없으면 외부 스킬만 건너뛰고 경고. lock 파일을 파싱할 수 없거나 version < 3 이면 외부 스킬 단계를 중단 |
| `setup --stages` 의 mcp 단계 | 선택된 하네스 | user scope 로 `codegraph serve --mcp` 를 등록한다. 패키지 액션보다 앞이면 안 된다. `codegraph install` 과 `codegraph upgrade` 는 쓰지 않는다 | 같음 |
| `--uninstall` (확장) | 위 범위 플래그 | 영수증에 기록된 플러그인·마켓플레이스·외부 스킬·MCP 등록·하네스·도구만 제거(D1). 마켓플레이스는 플러그인을 지운 뒤 지우고, 다른 플러그인이나 다른 범위의 설치가 아직 쓰면 남긴다. 하네스·도구는 카탈로그의 `uninstall` 명령으로 패키지·바이너리만 지우고 설정·인증 디렉터리는 남긴다(D5) | 영수증에 없는 것은 건드리지 않음 |
| `update-ai` (`scripts/update-ai.sh`, `Update-Ai.ps1`) | `--check`, `--only a,b`, `--allow-interrupt`, `--help` | 설치된 하네스·도구·플러그인 업데이트, 결과 표 출력. 실행 중 세션이 있어도 올린다(아래 실시간 업데이트) | 하나라도 실패하면 exit 1. `--check` 는 아무것도 바꾸지 않는다 |

단계 순서: base, harness, plugins, skills, codegraph, mcp, newline, claude_special, tools, hooks, agentsmd.

선택한 전체 실행의 기본 하네스는 Claude Code 와 Codex 다. 플러그인은 선택된 Claude Code 에만 `claude plugin install <id> --scope user` 로 낸다. Codex·Grok 벤더 플러그인 명령은 내지 않는다. 번들 스킬(design-lab, tailnet-report)은 Claude Code 가 선택된 일반 스킬 단계에만 있다. CodeGraph 패키지는 `npm install -g @colbymchenry/codegraph` 다. OMC HUD 가 이미 statusLine 이면 그 명령 문자열을 유지한 채 캐시 래퍼만 계획한다. Tailscale uninstall 은 `tailscale logout` 을 호출하지 않는다. Jarvis uninstall 은 이 셋업이 추가한 사용자 유닛만 끄고 `~/Workspace/jarvis` 와 `~/.local/state/jarvis` 는 지우지 않는다.

하네스별 MCP 등록·제거 명령 (CodeGraph, user scope, 인자 `codegraph serve --mcp`):

| 하네스 | 등록 | 제거 |
| ------ | ---- | ---- |
| claude | `claude mcp add -s user codegraph -- codegraph serve --mcp` | `claude mcp remove codegraph -s user` |
| codex | `codex mcp add codegraph -- codegraph serve --mcp` | `codex mcp remove codegraph` |
| gemini | `gemini mcp add -s user codegraph codegraph serve --mcp` | `gemini mcp remove -s user codegraph` |
| grok | `grok mcp add codegraph -- codegraph serve --mcp` | `grok mcp remove codegraph` |
| copilot | `copilot mcp add codegraph -- codegraph serve --mcp` (문서 기준, 미실측) | `copilot mcp remove codegraph` |
| agy | `agy mcp add codegraph codegraph serve --mcp` | `agy mcp remove codegraph` |
| opencode | `~/.config/opencode/opencode.json(c)` 의 `mcp.codegraph` 를 외과적으로 병합 (`opencode mcp add` 는 대화형 전용) | 같은 키 제거 |

## 데이터 계약

### Orca (jarvis 이관)

- Orca 패키지·서버·스킬의 설치·업데이트·제거는 jarvis 가 맡는다(jarvis 결정 D11·D16, ORCA-12). ai-setup 은 Orca 를 설치·갱신·제거하지 않는다.
- 예전 진입점 `setup.sh`·`install.sh` 의 `--tools`·`--tools=`·`--orca-desktop`, `setup.ps1`·`install.ps1` 의 `-Tools`·`--tools`·`--orca-desktop`, `stages.py --orca-desktop`, `update-ai orca`(`--only` 에 orca 가 들어간 경우 포함)는 아무것도 쓰지 않고 `Orca is now managed by jarvis; ai-setup no longer installs or updates it. Use: python3 -m jarvis module orca plan --json` 을 출력한 뒤 exit 1 로 끝난다. `install.*` 은 레포를 내려받기 전에 멈춘다.
- 카탈로그에 orca 항목이 없으므로 대상을 주지 않은 update-ai 와 doctor 는 Orca 를 보지 않는다.
- tools 단계와 `--stages all --uninstall` 은 Orca 액션을 내지 않는다. 영수증의 `tool_installs.orca`·`tool_installs.orca_server` 는 jarvis 의 Orca 모듈이 같은 키를 읽고 제거하므로 그대로 둔다.

- `res/catalog.json` 항목: `id`, `kind`(`harness`/`tool`), `skills`(선택, 도구와 함께 설치할 `sources.json` 형식 항목), `detect`(실행 파일 이름과 버전 인자), `install`·`uninstall`(플랫폼별 명령 목록, 설치 방식별로 짝을 이룬다), `update`, `plugin_update`(선택), `requires`(예: `node>=20`), `sudo`(bool).
  - `packages`: 설치 방식별 패키지 이름(`npm`, `winget`, `brew`, `brew_cask`, `deb`). update-ai 는 찾은 실행 파일이 실제로 그 방식으로 깔린 것일 때만 그 방식으로 올린다(npm 은 `node_modules/<pkg>` 안에 있을 때, winget 은 `WinGet` 경로, brew 는 brew prefix 아래). 패키지 목록 조회는 기본 `update` 명령이 없는 도구의 마지막 확인에만 쓴다.
  - `install` 의 `npm-release` 방식: npm 외의 공식 설치 방식이 없는 대상(gemini·codegraph 전 플랫폼, opencode·copilot 의 Windows)은 `python3 res/tools/npm_release.py install|uninstall <id>` 로 설치·제거한다. 카탈로그 명령은 저장소 루트에서 실행하고, 맨 앞의 `python3`/`python` 은 지금 인터프리터로 바꾼다. copilot 의 Linux·macOS 는 공식 native(`gh.io/copilot-install`, 갱신 `copilot update`)다. 제거는 예전 영수증(npm -g 설치)을 위해 같은 패키지의 npm -g 사본도 지운다. npm-release 의 uninstall 도 배치가 없으면 같은 방식으로 예전 npm -g 사본을 지우고, Windows 에서는 카탈로그의 winget 패키지 사본(예전 copilot)도 지운다. 실패하면 exit 1 로 영수증을 남긴다.
  - `detect.sessions`(선택): 실행 중인 세션 판정 보정. 제자리 교체 방식의 사용 중 판정과 `--allow-interrupt` 단계에만 쓴다. `match` 는 실행 파일 이름이 다른 세션(qemu 로 도는 grok)을, `ignore` 는 세션이 아닌 상주 프로세스(데몬·데스크톱 앱: `herdr server`, `serve --mcp`, codex app-server 데몬, Claude Desktop)를 명령줄 부분 문자열로 적는다.
- npm-release 배치(`res/tools/npm_release.py`):
  - 루트는 `~/.local/share/ai-setup/npm/<id>/`(Windows `%LOCALAPPDATA%\ai-setup\npm\<id>\`). 버전마다 `<ver>/` 에 `npm install --prefix` 로 설치하고, 완료 표시(`.complete`)가 있어야 버전으로 친다. npm 12 는 허용하지 않은 install 스크립트를 막으므로, 그 버전 디렉터리의 `.npmrc` 에 설치하는 패키지 하나만 `allow-scripts` 로 허용한다(의존성 스크립트는 계속 막힌다). 새 버전은 진입점 `--version` 이 성공해야 `current` 가 된다.
  - `current`(지금 버전)·`previous`(직전 버전)는 임시 파일을 만든 뒤 원자적으로 교체한다. 새 버전이 완성된 뒤에만 `current` 를 바꾸고, 설치가 실패하면 미완성 디렉터리를 지운다.
  - 셔임은 POSIX `~/.local/bin/<bin>`(sh), Windows `%LOCALAPPDATA%\ai-setup\bin\<bin>.cmd` 이다. Windows 셔임 디렉터리는 사용자 PATH 맨 앞에 둔다. 셔임 내용은 고정이라 다시 쓰지 않고, `current` 를 읽어 구체적인 버전 경로를 실행한다. 이미 뜬 세션은 자기 버전 경로를 계속 쓴다.
  - 셔임 경로에 ai-setup 셔임도 그 패키지의 npm 링크도 아닌 파일이 있으면 설치하기 전에 멈춘다.
  - 정리는 current·previous 를 남기고, 명령줄(앞 단어의 realpath 포함)이 그 버전 경로를 가리키는 프로세스가 있는 버전도 남긴다. 프로세스 목록을 읽지 못하거나 Windows 에서 이름을 바꿀 수 없으면 지우지 않는다.
  - PATH 의 npm 이 전역으로 깐 같은 패키지(이전 설치)는 셔임을 바꾸기 전에 사용 여부를 보고, 쓰는 프로세스가 없을 때만 `npm uninstall -g` 로 지운다. 쓰고 있으면 남기고 부분 실패로 보고한다.
  - uninstall 은 ai-setup 셔임과 사용 중이 아닌 버전만 지운다. 남긴 버전이 있으면 exit 1 로 끝나 영수증을 남기고, 다시 실행하면 이어서 지운다.
- update-ai 실시간 업데이트:
  - 버전별 배치(native self-update, npm-release, brew)는 세션 유무와 상관없이 올린다. brew 는 `HOMEBREW_NO_INSTALL_CLEANUP=1` 로 실행해 formula 의 이전 버전을 남긴다(cask 는 이 값과 상관없이 이전 버전을 지울 수 있다. macOS 실측 전).
  - 파일을 제자리에서 바꾸거나 세션을 끝내는 방식(npm -g, winget portable)은 그 대상의 세션이 돌면 `--allow-interrupt` 없이는 바꾸지 않고 보류(실패)로 보고하며, 카탈로그 설치 방식이 다르면 그 설치 명령을 안내한다. codex 관리형 데몬 교체도 실행 중이면 `--allow-interrupt` 를 요구한다.
  - 설치본이 최신 릴리스와 같거나 더 새로우면(앱 안에서 받은 prerelease, 매니페스트 지연) 최신으로 판정한다. `--check` 와 갱신 뒤 검사가 모두 이 규칙을 쓴다.
  - 갱신한 뒤에도 이전 버전으로 도는 세션은 실패가 아니라 결과 표 아래 안내(재시작하면 새 버전)로 남긴다.
  - 프로세스 목록은 명령줄을 자르지 않고 읽는다(`ps -ww`).
- 영수증 `harness_installs`·`tool_installs` 는 항목마다 실제로 쓴 설치 방식을 기록하고, uninstall 은 그 방식에 짝지은 `uninstall` 명령을 쓴다.
- `res/plugins/plugins.json` 항목: `marketplace`(github `owner/repo`), `plugin`(`name@marketplace`), `default`(bool), `provides_skills`(선택, 플러그인으로 옮겨 간 스킬 이름).
- `res/skills/sources.json` 항목: `repo`(`owner/repo`), `ref`(태그·브랜치·SHA), `skills`(목록), `default`(bool).
- `res/mcp/servers.json` 항목: `name`, `command`, `args`, `env_names`(값이 아니라 이름), `requires`(실행 파일).
- 영수증: 기존 `~/.claude/.claude-code-setup.json` 에 키를 추가한다 — `plugins`, `marketplaces`, `skills_external`, `mcp`, `harness_installs`, `tool_installs`. 파일 이름은 바꾸지 않는다.
- 마이그레이션: 새 키가 없으면 빈 값으로 본다. 기존 키의 형식은 바꾸지 않는다.

## 불변식

- 이미 있던 하네스·도구·플러그인·스킬·MCP 등록은 영수증에 기록하지 않고, uninstall 이 제거하지 않는다.
- dry-run 과 doctor 는 파일·설정·lock·패키지를 바꾸지 않는다. `skills check`/`update`(실제 업데이트를 적용함)와 설치 스크립트를 호출하지 않는다.
- 파싱할 수 없는 설정·lock 을 만나면 그 단계는 쓰기 전에 멈춘다.
- 다른 도구가 넣은 훅·스킬·플러그인(Orca, herdr, Paseo, Aside, ahakey)은 읽기만 한다. Codex `hooks.json` 은 신뢰 해시가 깨지므로 쓰지 않는다. CodeGraph 설치는 OMC HUD statusLine 명령을 바꾸지 않는다.
- `--prune-skills` 는 심볼릭 링크·junction 인 스킬(앱이 관리하는 ego-browser 등)과 lock 에 있는 스킬을 후보로 삼지 않으며, 삭제하지 않고 휴지통으로만 옮긴다.
- 시크릿 값은 출력·로그·영수증에 남기지 않는다. doctor 는 키 이름과 파일 위치만 보고한다.
- 한 실행은 그 실행 환경(Windows 네이티브, WSL, Linux, macOS 중 하나)의 홈만 고친다.
- update-ai 는 설치되지 않은 도구를 설치하지 않는다.
- sudo 가 필요한 명령은 실행 전에 명령 전체를 출력하고, 표준 입력이 TTY 가 아니면 실행하지 않고 건너뛴다(D3).
- 인자 없이 TTY 에서 실행하면 첫 실행은 단계 산책이 뜨고 기본은 켜져 있다. 산책을 마치거나 Skip 하면 카테고리 허브가 열리고, 영수증이 있는 머신은 허브부터 연다. 설치는 허브의 Apply 에서만 일어나며 Preview 는 dry-run 이다. 허브의 Quit 과 TTY 없음은 아무것도 설치하지 않는다(D4). 허브는 키보드로만 조작한다. `--no-onboard` 만 예전 전체 설치다.

## 호환성

- 지원 대상: Windows 네이티브(PowerShell 5.1/7), WSL, Linux x64/arm64(Raspberry Pi 5 포함), macOS arm64.
- 선행 조건: base 는 git, Python 3.9+. Node 는 뒤에 고른 항목이 요구하는 가장 높은 주 버전만 설치한다. gemini 와 CodeGraph 는 Node 20+, copilot(npm)은 Node 22+. Linux·macOS 에서는 Node 를 nvm 으로 사용자 홈에 설치하고, 이미 있는 Node 의 전역 npm 경로에 쓸 수 없을 때(apt 판 Node)도 같은 방식으로 사용자 Node 를 더한다. `npm install -g` 와 update-ai 가 sudo 없이 돌아야 하기 때문이다. CodeGraph 갱신은 카탈로그 `update` 명령이 아니라 npm-release 다.
- 기존 플래그 `--omc`, `--output-style`, `--skills` 의 의미는 유지한다. `--skills` 는 외부 스킬이 추가될 뿐 번들 스킬 동작은 그대로다.
- 기존 영수증 파일 이름과 키 형식은 폴백 없이 깨지 않는다.
- 기존 `update-ai.sh`(pi, mac)와 `Update-Ai.ps1`(Windows)의 옵션 이름(`--check`, `--only`, `--allow-interrupt` / `-Check`, `-Only`)을 유지한다.
