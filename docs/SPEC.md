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
| `setup --tools L` / `-Tools L` | `orca,herdr,graft,all` | 없는 도구만 설치하고 영수증 `tool_installs` 에 기록. 카탈로그 항목에 `skills` 가 있으면(Orca) 그 스킬도 `skills` CLI 로 함께 설치하고 기록한다(D6) | 같음 |
| `setup --prune-skills` / `-PruneSkills` | 없음 | `~/.agents/skills` 의 실제 디렉터리 가운데 lock 에 없는 것을 하나씩 보여 주고, 사용자가 승인한 것만 휴지통으로 옮긴다. 그 디렉터리를 가리키던 하네스 스킬 링크도 지운다. 기본 실행·온보딩 기본값에 포함되지 않는다(D7) | 표준 입력이 TTY 가 아니면 아무것도 옮기지 않고 exit 1. 휴지통으로 옮길 수 없으면 그 항목을 건너뛴다 |
| `setup --plugins` / `-Plugins` | `plugins.json` + 온보딩 선택 | `claude plugin marketplace add` + `claude plugin install --scope user`. 영수증 `plugins` 에 우리가 추가한 마켓플레이스·플러그인만 기록 | `claude` 가 없으면 단계를 건너뛰고 경고 |
| `setup --skills` / `-Skills` (확장) | 번들 스킬 + `sources.json` | 번들은 기존대로. 외부 스킬은 `npx skills add <repo>#<ref> --skill <s> -g -a <agents> -y`. 영수증 `skills_external` | `npx` 가 없으면 외부 스킬만 건너뛰고 경고. lock 파일을 파싱할 수 없거나 version < 3 이면 외부 스킬 단계를 중단 |
| `setup --mcp` / `-Mcp` | `servers.json` | 설치된 하네스마다 user scope 로 등록. 영수증 `mcp` 에 하네스별 서버 이름 기록 | 서버 실행 파일(`graft`)이 없으면 건너뛰고 경고 |
| `--uninstall` (확장) | 위 범위 플래그 | 영수증에 기록된 플러그인·외부 스킬·MCP 등록·하네스·도구만 제거(D1). 하네스·도구는 카탈로그의 `uninstall` 명령으로 패키지·바이너리만 지우고 설정·인증 디렉터리는 남긴다(D5). 도구와 함께 설치한 스킬도 함께 제거한다 | 영수증에 없는 것은 건드리지 않음 |
| `update-ai` (`scripts/update-ai.sh`, `Update-Ai.ps1`) | `--check`, `--only a,b`, `--allow-interrupt`, `--help` | 설치된 하네스·도구·플러그인 업데이트, 결과 표 출력 | 하나라도 실패하면 exit 1. `--check` 는 아무것도 바꾸지 않는다 |

하네스별 MCP 등록·제거 명령 (graft 기준, user scope):

| 하네스 | 등록 | 제거 |
| ------ | ---- | ---- |
| claude | `claude mcp add -s user graft -- graft mcp` | `claude mcp remove graft -s user` |
| codex | `codex mcp add graft -- graft mcp` | `codex mcp remove graft` |
| gemini | `gemini mcp add -s user graft graft mcp` | `gemini mcp remove -s user graft` |
| grok | `grok mcp add graft -- graft mcp` | `grok mcp remove graft` |
| copilot | `copilot mcp add graft -- graft mcp` (문서 기준, 미실측) | `copilot mcp remove graft` |
| agy | `agy mcp add graft graft mcp` | `agy mcp remove graft` |
| opencode | `~/.config/opencode/opencode.json(c)` 의 `mcp.graft` 를 외과적으로 병합 (`opencode mcp add` 는 대화형 전용) | 같은 키 제거 |

## 데이터 계약

- `res/catalog.json` 항목: `id`, `kind`(`harness`/`tool`), `skills`(선택, 도구와 함께 설치할 `sources.json` 형식 항목), `detect`(실행 파일 이름과 버전 인자), `install`·`uninstall`(플랫폼별 명령 목록, 설치 방식별로 짝을 이룬다), `update`, `plugin_update`(선택), `requires`(예: `node>=20`), `sudo`(bool).
- 영수증 `harness_installs`·`tool_installs` 는 항목마다 실제로 쓴 설치 방식을 기록하고, uninstall 은 그 방식에 짝지은 `uninstall` 명령을 쓴다.
- `res/plugins/plugins.json` 항목: `marketplace`(github `owner/repo`), `plugin`(`name@marketplace`), `default`(bool), `provides_skills`(선택, 플러그인으로 옮겨 간 스킬 이름).
- `res/skills/sources.json` 항목: `repo`(`owner/repo`), `ref`(태그·브랜치·SHA), `skills`(목록), `default`(bool).
- `res/mcp/servers.json` 항목: `name`, `command`, `args`, `env_names`(값이 아니라 이름), `requires`(실행 파일).
- 영수증: 기존 `~/.claude/.claude-code-setup.json` 에 키를 추가한다 — `plugins`, `skills_external`, `mcp`, `harness_installs`, `tool_installs`. 파일 이름은 바꾸지 않는다.
- 마이그레이션: 새 키가 없으면 빈 값으로 본다. 기존 키의 형식은 바꾸지 않는다.

## 불변식

- 이미 있던 하네스·도구·플러그인·스킬·MCP 등록은 영수증에 기록하지 않고, uninstall 이 제거하지 않는다.
- dry-run 과 doctor 는 파일·설정·lock·패키지를 바꾸지 않는다. `skills check`/`update`(실제 업데이트를 적용함)와 설치 스크립트를 호출하지 않는다.
- 파싱할 수 없는 설정·lock 을 만나면 그 단계는 쓰기 전에 멈춘다.
- 다른 도구가 넣은 훅·스킬·플러그인(Orca, herdr, graft, Paseo, Aside, ahakey)은 읽기만 한다. Codex `hooks.json` 은 신뢰 해시가 깨지므로 쓰지 않는다.
- `--prune-skills` 는 심볼릭 링크·junction 인 스킬(앱이 관리하는 ego-browser 등)과 lock 에 있는 스킬을 후보로 삼지 않으며, 삭제하지 않고 휴지통으로만 옮긴다.
- 시크릿 값은 출력·로그·영수증에 남기지 않는다. doctor 는 키 이름과 파일 위치만 보고한다.
- 한 실행은 그 실행 환경(Windows 네이티브, WSL, Linux, macOS 중 하나)의 홈만 고친다.
- update-ai 는 설치되지 않은 도구를 설치하지 않는다.
- sudo 가 필요한 명령은 실행 전에 명령 전체를 출력하고, 표준 입력이 TTY 가 아니면 실행하지 않고 건너뛴다(D3).
- 인자 없이 실행할 때 새 단계(하네스·도구 설치, 플러그인, 외부 스킬, MCP)는 기본으로 꺼져 있다(D4).

## 호환성

- 지원 대상: Windows 네이티브(PowerShell 5.1/7), WSL, Linux x64/arm64(Raspberry Pi 5 포함), macOS arm64.
- 하네스별 선행 조건: gemini·graft 는 Node 20+, copilot(npm)은 Node 22+.
- 기존 플래그 `--omc`, `--output-style`, `--skills` 의 의미는 유지한다. `--skills` 는 외부 스킬이 추가될 뿐 번들 스킬 동작은 그대로다.
- 기존 영수증 파일 이름과 키 형식은 폴백 없이 깨지 않는다.
- 기존 `update-ai.sh`(pi, mac)와 `Update-Ai.ps1`(Windows)의 옵션 이름(`--check`, `--only`, `--allow-interrupt` / `-Check`, `-Only`)을 유지한다.
