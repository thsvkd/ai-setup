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
| `setup --tools L` / `-Tools L` | `orca` | Orca 공식 패키지와 그 빌드의 번들 스킬만 설치한다. `--stages` 와 함께 쓰지 않는다 | 같음 |
| `setup --stages L` | `all` 또는 쉼표 목록 | 아래 단계 순서로 액션 목록을 만든다. `--dry-run` 은 목록만 출력한다. 컨텍스트 맵은 CodeGraph npm 패키지 다음 MCP 다 | 같음 |
| `setup --prune-skills` / `-PruneSkills` | 없음 | `~/.agents/skills` 의 실제 디렉터리 가운데 lock 에 없는 것을 하나씩 보여 주고, 사용자가 승인한 것만 휴지통으로 옮긴다. 그 디렉터리를 가리키던 하네스 스킬 링크도 지운다. 기본 실행·온보딩 기본값에 포함되지 않는다(D7) | 표준 입력이 TTY 가 아니면 아무것도 옮기지 않고 exit 1. 휴지통으로 옮길 수 없으면 그 항목을 건너뛴다 |
| `setup --plugins` / `-Plugins` | `plugins.json` + 온보딩 선택 | `claude plugin marketplace add` + `claude plugin install --scope user`. 우리가 추가한 플러그인만 영수증 `plugins` 에, 마켓플레이스만 `marketplaces` 에 기록. 이미 user 범위로 설치된 플러그인은 설치·기록하지 않음 | `claude` 가 없으면 단계를 건너뛰고 경고 |
| `setup --skills` / `-Skills` (확장) | 번들 스킬 + `sources.json` | 번들은 기존대로. 외부 스킬은 `npx skills add <repo>#<ref> --skill <s> -g -a <agents> -y`. 영수증 `skills_external` | `npx` 가 없으면 외부 스킬만 건너뛰고 경고. lock 파일을 파싱할 수 없거나 version < 3 이면 외부 스킬 단계를 중단 |
| `setup --stages` 의 mcp 단계 | 선택된 하네스 | user scope 로 `codegraph serve --mcp` 를 등록한다. 패키지 액션보다 앞이면 안 된다. `codegraph install` 과 `codegraph upgrade` 는 쓰지 않는다 | 같음 |
| `--uninstall` (확장) | 위 범위 플래그 | 영수증에 기록된 플러그인·마켓플레이스·외부 스킬·MCP 등록·하네스·도구만 제거(D1). 마켓플레이스는 플러그인을 지운 뒤 지우고, 다른 플러그인이나 다른 범위의 설치가 아직 쓰면 남긴다. 하네스·도구는 카탈로그의 `uninstall` 명령으로 패키지·바이너리만 지우고 설정·인증 디렉터리는 남긴다(D5). 도구와 함께 설치한 스킬도 함께 제거한다 | 영수증에 없는 것은 건드리지 않음 |
| `update-ai` (`scripts/update-ai.sh`, `Update-Ai.ps1`) | `--check`, `--only a,b`, `--allow-interrupt`, `--help` | 설치된 하네스·도구·플러그인 업데이트, 결과 표 출력. 실행 중 세션이 있어도 올린다(아래 실시간 업데이트) | 하나라도 실패하면 exit 1. `--check` 는 아무것도 바꾸지 않는다 |

단계 순서: base, harness, plugins, skills, codegraph, mcp, newline, claude_special, tools, hooks, agentsmd.

선택한 전체 실행의 기본 하네스는 Claude Code 와 Codex 다. 플러그인은 선택된 Claude Code 에만 `claude plugin install <id> --scope user` 로 낸다. Codex·Grok 벤더 플러그인 명령은 내지 않는다. 번들 스킬(design-lab, tailnet-report)은 Claude Code 가 선택된 일반 스킬 단계에만 있고, Orca 스킬은 Orca 도구 액션에만 있다. CodeGraph 패키지는 `npm install -g @colbymchenry/codegraph` 다. OMC HUD 가 이미 statusLine 이면 그 명령 문자열을 유지한 채 캐시 래퍼만 계획한다. Tailscale uninstall 은 `tailscale logout` 을 호출하지 않는다. Jarvis uninstall 은 이 셋업이 추가한 사용자 유닛만 끄고 `~/Workspace/jarvis` 와 `~/.local/state/jarvis` 는 지우지 않는다.

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

### Orca 설치 (2026-10-21 플랫폼별 설치 방식 적용)

- `--tools orca` / `-Tools orca`는 공식 Orca 패키지·번들 스킬과 함께 `res/tools/orca_server.py`를 통해 지속 서버와 데스크톱 클라이언트를 설정한다. 다른 도구의 설정 범위와 혼합하지 않는다.
- macOS는 공식 zip의 `/Applications/Orca.app`, Windows는 공식 `orca-windows-setup.exe /S /CURRENTUSER`, Debian/Ubuntu는 공식 `orca-ide_<version>_<arch>.deb`를 선택한다. Homebrew cask·winget을 새 설치의 소유자로 추가하지 않는다.
- 공식 stable 매니페스트에서 현재 아키텍처의 파일을 선택하고, 다운로드 크기·SHA-512를 검증한 뒤 설치한다. Mac은 서명·Gatekeeper를 확인한다. Linux sudo는 기존 D3 규칙을 따른다.
- 기존 패키지·프로필·페어링·워크스페이스는 보존한다. 기존 Orca 패키지에도 서버 설정을 적용한다. 같은 원본 프로필이 이미 실행 중이면 ai-setup 소유 서비스·영수증과 데스크톱 연결을 검증해 연결이 살아 있는 구성을 재사용한다. 그 밖의 활성 서버는 수정하거나 재시작하지 않고 설정을 실패 처리해 종료하며, 사용자가 해당 런타임을 중단한 뒤 재시도하도록 안내한다. 페어링 오퍼를 시작하기 전에 `pairing` 상태의 영수증을 기록하고, 8자리 임의 접미사가 붙은 고유 데스크톱 이름과 이름 충돌 검사에 통과한 환경 ID 목록을 오퍼 시작 전에 기록한다. 데스크톱 환경 ID를 얻는 즉시 영수증을 갱신한다. CLI 성공 뒤 응답 파싱 전에 끊기면 기록한 목록과 새 이름 일치 항목으로 ID를 복구한다. 복구는 이 임의 이름을 다른 사용자가 동시에 만든 환경이 아니라는 운영 가정을 둔다. 임시 서버가 종료되지 않으면 영수증을 보존하고 지속 서비스를 시작하지 않는다. 재시도는 저장된 데스크톱 ID로 이어가며 링크를 다시 발급하지 않는다. 서비스 시작 전 `configuring` 상태의 소유권 영수증을 기록하고, 재실행은 해당 서비스와 데스크톱 연결을 검증해 이어서 완료한다. 같은 이름의 기존 데스크톱 환경은 서버 주소를 검증할 수 없으므로 재사용하지 않고 중단한다. 새 패키지·버전 확인 후 `tool_installs.orca`에 `method`, `version`, `skills_added`, `skills_state`를 기록하고 ai-setup이 만든 서비스는 `tool_installs.orca_server`에 별도로 기록한다. 다른 영수증 키는 보존한다. 패키지 단계는 `tool_attempts.orca`로 추적하며, 중단 뒤 설치 경로가 남아 있으면 성공으로 간주하지 않고 점검을 요구한다.
- 서버는 플랫폼의 기본 Orca 프로필을 사용하고 데스크톱 클라이언트는 별도 `orca-desktop` 프로필을 사용한다. Orca는 새 링크를 만들면 이전 미사용 링크를 교체하므로, 런타임 범위 링크를 먼저 데스크톱 클라이언트에 등록한다. 페어링 주소를 명시하지 않으면 Tailscale IPv4 만 쓴다. 서버는 모든 인터페이스에서 수신하므로 Tailscale 주소를 찾지 못하면 기본 경로 IP 로 폴백하지 않고, 패키지·스킬은 유지한 채 서버 설정만 경고와 함께 건너뛴다(종료 코드 0, 서버 영수증 없음). `--tools orca` 재실행이 서버 설정을 다시 시도한다. 지속 서비스는 `--mobile-pairing`으로 실행해 현재 유효한 모바일 링크를 서비스 디렉터리의 `pairing-codes.txt`에 기록하며, 서버가 재시작되면 새 링크로 파일을 교체한다. 데스크톱은 저장된 페어링으로 계속 연결한다.
- Windows 서비스 작업은 S4U 로그온과 지연된 BootTrigger로 부팅 후 시작하고 사용자 로그인 시에도 시작한다. S4U 는 암호를 저장하지 않지만 Windows 암호화 파일이나 네트워크 자격 증명에는 접근할 수 없다. macOS LaunchAgent 와 Linux systemd 사용자 서비스는 사용자 세션 시작 시 서버를 시작한다. 서버 로그에서는 페어링 링크·QR·웹 클라이언트 링크를 제거한다. 페어링 파일은 서비스 디렉터리에만 저장하고 영수증에는 저장하지 않는다.
- Windows 예약 작업의 등록·삭제만 같은 사용자 계정의 UAC 동의로 승격한다. 프로필·영수증 쓰기는 일반 권한에서 수행한다. 취소·조회 오류는 복구 영수증과 파일을 보존한다. 재사용·제거 전에 실행 파일, runner/config 인수, 작업 디렉터리, 사용자 SID와 최소 권한 S4U 설정을 확인하며 변경된 작업은 보존한다. 무제한 실행과 배터리 중 실행을 명시하고, 모바일 링크 파일은 예약 작업과 데스크톱의 같은 사용자 SID가 읽을 수 있게 보호한다.
- Windows 서버는 Orca 설치 폴더(`%LOCALAPPDATA%\Programs\orca`)가 아니라 서비스 디렉터리의 `app\build-<식별자>` 복사본에서 실행한다. Orca 설치기(electron-builder NSIS, 앱 내 업데이트 포함)는 경로가 설치 폴더로 시작하는 모든 프로세스를 강제 종료하려 하고, 세션 0 의 S4U 서버는 High 무결성이라 사용자 권한 설치기가 끝낼 수 없어 업데이트가 멈추기 때문이다. 식별자는 `Orca.exe`·`resources\app.asar`·`Uninstall Orca.exe` 의 크기·수정 시각이며, 셋 중 하나라도 없으면 설치 중으로 본다. 복사 전후 식별자가 다르거나 복사가 실패하면 마지막 완성 복사본을, 그것도 없으면 경고와 함께 설치 폴더를 쓴다. 다만 설치 중(식별 파일 일부 없음)이고 완성 복사본이 없으면 반쯤 쓰인 설치 폴더에서 띄우지 않고 30초마다 다시 본다. 서버 실행 파일을 띄우지 못해도 러너는 끝나지 않고 30초 뒤 다시 시도한다. 터미널 0개를 확인한 직후 새 복사본으로 옮길 때는 Windows 에서 처음부터 `taskkill /F /T` 로 멈춘다(창이 없는 콘솔 서버는 /F 없이 끝나지 않아, 기다리는 사이 새 터미널이 생길 수 있다). 망가진 복사본(실행 파일 없음)은 지우고 다시 만든다. 러너는 자신을 kill-on-close Job 에 넣어 어떤 이유로 끝나든 서버 트리(터미널 호스트 포함)를 함께 끝내고, 서버만 비정상 종료하면 30초 뒤 다시 띄운다. 러너는 1분마다 설치본을 확인해 바뀐 식별자가 한 주기 동안 유지되면 서버를 둔 채 새 복사본을 만들고, 복사가 끝난 뒤 `orca terminal list --json` 의 `totalCount` 가 0일 때만 새 복사본으로 재시작한다. 복사에 실패한 빌드는 설치본이 다시 바뀌거나 1시간이 지날 때까지 재시도하지 않으며, 설치 폴더에서 돌던 서버도 복사가 되면 같은 조건으로 옮긴다. 러너는 Job 을 건 뒤 서비스 디렉터리의 `runner-state.json` 에 자기 PID·생성 시각·Job 여부·실행 중인 복사본을 기록하고, ai-setup 은 파일이 아니라 이 기록과 PID 생존으로 실행 중인 러너를 판정하며 터미널 조회도 그 복사본의 CLI 로 한다. 이 기록이 없는(Job 이 없는 예전) 러너는 `/End` 뒤 서버 트리를 남기므로 승격한 `end` 로만 멈추며, 재실행은 파일이 이미 최신이어도 이런 러너를 유휴일 때 다시 띄운다. 서버 재시작을 기다리는 사이 서비스가 제거됐으면 러너는 디렉터리를 다시 만들지 않고 끝난다. 승격 경로는 작업을 멈추기 전에 러너(python, 명령줄에 러너 경로)와 그 자손(부모보다 늦게 생긴 프로세스)을 기록해 두고 그 트리만 끝낸다. 재실행은 러너·헬퍼·설정(`app_copies`)만 갱신하고 예약 작업 정의는 다시 쓰지 않는다.
- Windows 의 `update-ai orca` 는 공식 매니페스트의 설치 파일을 크기·SHA-512 로 검증한 뒤 앱 내 업데이트와 같은 `/S --updated` 로 실행하고 설치본 버전을 확인한다. `--updated` 가 없으면 이전 버전의 언인스톨러가 업데이트가 아닌 제거로 돌아 Orca 터미널 호스트를 끝내고 `daemon-host-profiles` 를 지운다. 설치 폴더의 데스크톱 앱은 설치기가 닫으며 다시 열지 않는다. 이미 최신이면 아무것도 하지 않는다. 새 버전이 있고 ai-setup 서버가 실행 중인데 러너 상태에 복사본이 없으면(설치 폴더에서 실행) 설치기를 띄우지 않고 `setup --tools orca` 를 안내한다. 설치기 종료 코드가 실패면 실패로 보고하고, 서버 전환을 미루면 그 이유(터미널 수·셀 수 없음·시간 초과)를 알린다. 설치 뒤에는 러너가 새 복사본으로 옮기는지 최대 5분 지켜보고, 터미널이 있으면 기다리지 않고 나중에 스스로 옮긴다고 보고한다. 세션 판정에서 ai-setup 서버 복사본(`\ai-setup\orca-server\app\`)과 Orca 터미널 호스트(`\Orca\daemon-host-profiles\`)는 업데이트가 끝내지 않으므로 세션이 아니다.
- 별도 데스크톱 프로필에 기존 원격 환경을 병합하고 원본과 충돌 항목은 보존한다. 기존 클라이언트가 실행 중이면 종료 후 다시 시도하도록 안내한다. Windows 바로가기 변경은 원본·변경 후 인수를 별도 영수증에 기록하며, 제거 시 사용자가 나중에 바꾸지 않은 바로가기만 복구한다.
- 데스크톱 앱 실행은 선택이다. `--orca-desktop`(`orca.py --desktop-app`)을 주면 설치 완료 후 `orca open --environment <id>`로 페어링된 서버를 데스크톱 앱에서 열고, Windows 바로가기를 데스크톱 프로필로 바꾼다. 주지 않으면 서버 실행과 데스크톱·모바일 페어링까지만 한다. 제거 시 ai-setup 소유 서비스만 제거하고 서버·클라이언트 프로필과 Orca 워크스페이스 데이터는 남긴다. 그 서비스가 실행 중이면 서비스 관리자(systemd·launchd·작업 스케줄러)로 먼저 멈춘다. 서비스를 멈추면 Orca 터미널 호스트도 끝날 수 있으므로, 모든 플랫폼에서 서버 런타임이 활성이고 살아 있는 터미널이 있거나 확인할 수 없으면 멈추지 않고 거부한다. 런타임이 꺼져 있으면(크래시 뒤 재시작 대기 등) 터미널을 묻지 않고 멈춘다. 러너 상태 파일은 러너의 PID 와 생성 시각을 남기며, 생성 시각이 다르면(PID 재사용) 그 상태를 러너로 보지 않는다. 멈춘 뒤에도 같은 프로필의 서버가 남아 있으면 ai-setup 이 띄운 것이 아니므로 끊지 않고 제거를 거부한다.
- 스킬은 설치본 CLI의 번들 목록에서 공용 디렉터리·universal 링크·lock 항목이 모두 없는 이름만 선택하고 `skills install --skill <name> --agent universal`로 같은 빌드의 고정된 원본을 사용한다. 기존 lock은 version 3 이상이며 파싱할 수 있어야 한다. 중단 시 부분 설치를 기록하고 `skills_state=pending`으로 남겨 재실행 때 스킬만 재시도한다.
- 제거는 기록된 설치 방식에만 적용하며 사용자 설정·인증·프로젝트·페어링 파일은 보존한다. 스킬은 새로 추가했고 내용 해시가 그대로인 것만 제거하며, 그 설치가 만든 universal 링크와 일치하는 lock 항목도 정리한다.
- `--dry-run`은 릴리스·스킬 네트워크 요청, 설치, 영수증 쓰기를 하지 않는다.

- `res/catalog.json` 항목: `id`, `kind`(`harness`/`tool`), `skills`(선택, 도구와 함께 설치할 `sources.json` 형식 항목), `detect`(실행 파일 이름과 버전 인자), `install`·`uninstall`(플랫폼별 명령 목록, 설치 방식별로 짝을 이룬다), `update`, `plugin_update`(선택), `requires`(예: `node>=20`), `sudo`(bool).
  - `packages`: 설치 방식별 패키지 이름(`npm`, `winget`, `brew`, `brew_cask`, `deb`). update-ai 는 찾은 실행 파일이 실제로 그 방식으로 깔린 것일 때만 그 방식으로 올린다(npm 은 `node_modules/<pkg>` 안에 있을 때, winget 은 `WinGet` 경로, brew 는 brew prefix 아래). 패키지 목록 조회는 기본 `update` 명령이 없는 도구의 마지막 확인에만 쓴다.
  - `install` 의 `npm-release` 방식: npm 외의 공식 설치 방식이 없는 대상(gemini·codegraph 전 플랫폼, opencode·copilot 의 Windows)은 `python3 res/tools/npm_release.py install|uninstall <id>` 로 설치·제거한다. 카탈로그 명령은 저장소 루트에서 실행하고, 맨 앞의 `python3`/`python` 은 지금 인터프리터로 바꾼다. copilot 의 Linux·macOS 는 공식 native(`gh.io/copilot-install`, 갱신 `copilot update`)다. 제거는 예전 영수증(npm -g 설치)을 위해 같은 패키지의 npm -g 사본도 지운다. npm-release 의 uninstall 도 배치가 없으면 같은 방식으로 예전 npm -g 사본을 지우고, Windows 에서는 카탈로그의 winget 패키지 사본(예전 copilot)도 지운다. 실패하면 exit 1 로 영수증을 남긴다.
  - `detect.sessions`(선택): 실행 중인 세션 판정 보정. 제자리 교체 방식의 사용 중 판정과 `--allow-interrupt` 단계에만 쓴다. `match` 는 실행 파일 이름이 다른 세션(`/opt/Orca/orca-ide`, qemu 로 도는 grok)을, `ignore` 는 세션이 아닌 상주 프로세스(데몬·데스크톱 앱: `herdr server`, `serve --mcp`, codex app-server 데몬, Claude Desktop)를 명령줄 부분 문자열로 적는다.
- npm-release 배치(`res/tools/npm_release.py`):
  - 루트는 `~/.local/share/ai-setup/npm/<id>/`(Windows `%LOCALAPPDATA%\ai-setup\npm\<id>\`). 버전마다 `<ver>/` 에 `npm install --prefix` 로 설치하고, 완료 표시(`.complete`)가 있어야 버전으로 친다.
  - `current`(지금 버전)·`previous`(직전 버전)는 임시 파일을 만든 뒤 원자적으로 교체한다. 새 버전이 완성된 뒤에만 `current` 를 바꾸고, 설치가 실패하면 미완성 디렉터리를 지운다.
  - 셔임은 POSIX `~/.local/bin/<bin>`(sh), Windows `%LOCALAPPDATA%\ai-setup\bin\<bin>.cmd` 이다. Windows 셔임 디렉터리는 사용자 PATH 맨 앞에 둔다. 셔임 내용은 고정이라 다시 쓰지 않고, `current` 를 읽어 구체적인 버전 경로를 실행한다. 이미 뜬 세션은 자기 버전 경로를 계속 쓴다.
  - 셔임 경로에 ai-setup 셔임도 그 패키지의 npm 링크도 아닌 파일이 있으면 설치하기 전에 멈춘다.
  - 정리는 current·previous 를 남기고, 명령줄(앞 단어의 realpath 포함)이 그 버전 경로를 가리키는 프로세스가 있는 버전도 남긴다. 프로세스 목록을 읽지 못하거나 Windows 에서 이름을 바꿀 수 없으면 지우지 않는다.
  - PATH 의 npm 이 전역으로 깐 같은 패키지(이전 설치)는 셔임을 바꾸기 전에 사용 여부를 보고, 쓰는 프로세스가 없을 때만 `npm uninstall -g` 로 지운다. 쓰고 있으면 남기고 부분 실패로 보고한다.
  - uninstall 은 ai-setup 셔임과 사용 중이 아닌 버전만 지운다. 남긴 버전이 있으면 exit 1 로 끝나 영수증을 남기고, 다시 실행하면 이어서 지운다.
- update-ai 실시간 업데이트:
  - 버전별 배치(native self-update, npm-release, brew)는 세션 유무와 상관없이 올린다. brew 는 `HOMEBREW_NO_INSTALL_CLEANUP=1` 로 실행해 formula 의 이전 버전을 남긴다(cask 는 이 값과 상관없이 이전 버전을 지울 수 있다. macOS 실측 전).
  - 파일을 제자리에서 바꾸거나 세션을 끝내는 방식(npm -g, winget portable, Orca deb, 설치 폴더의 데스크톱 앱을 끝내는 Windows Orca 설치기)은 그 대상의 세션이 돌면 `--allow-interrupt` 없이는 바꾸지 않고 보류(실패)로 보고하며, 카탈로그 설치 방식이 다르면 그 설치 명령을 안내한다. codex 관리형 데몬 교체도 실행 중이면 `--allow-interrupt` 를 요구한다.
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
