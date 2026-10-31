# ai-setup

Claude Code·Codex 같은 AI 코딩 에이전트의 작업 환경을 명령 한 줄로 설치한다. 줄바꿈 키 통일, 프로젝트 작업 규칙, 플러그인·도구 설치를 묶었다. 에이전트가 실수해도 되돌릴 수 있게 만드는 안전 장치(가드 훅)는 [jarvis](https://github.com/thsvkd/jarvis)가 관리한다([훅](#훅은-jarvis가-관리한다)). Windows·macOS·Linux에서 동작한다.

작성자가 실제로 쓰는 구성을 공개한 것이라, 기본값은 **한국어로 Claude Code를 쓰는 사용자**에게 맞춰져 있다(한국어 응답, 한국어 출력 스타일 등). 설치하기 전에 [미리보기](#빠른-시작)로 바뀌는 내용을 확인하고, 필요 없는 단계는 끄고 설치하기를 권한다.

## 무엇을 해 주나

- ⏎ **줄바꿈 키 통일**: Claude Code·Codex·Grok CLI에서 Shift+Enter(또는 Ctrl+Enter)를 줄바꿈 키로 맞춘다.
- 🧩 **에이전트·플러그인·도구 설치**: Claude Code와 Codex, Claude Code 플러그인, CodeGraph 등을 고른 만큼 설치한다.
- 📄 **AGENTS.md**: 현재 프로젝트에 에이전트가 따를 작업 규칙 템플릿 [`res/AGENTS.md`](res/AGENTS.md)를 복사한다. 작성자의 규칙을 한국어로 쓴 것으로, 변경 원칙, 승인이 필요한 작업, "식별자와 문자열은 영어로, 한국어는 주석에만" 같은 코드 규칙, `docs/PRD.md`·`docs/SPEC.md` 등을 가리키는 문서 구조가 들어 있다. 그 문서들은 함께 만들지 않으므로(틀은 [`res/docs/`](res/docs)에 있다) 필요하면 직접 복사하고, `<채워 넣기>` 칸과 함께 프로젝트에 맞게 고쳐 쓴다.

## 설치 전에 알아 둘 것

> [!WARNING]
> **사용량과 비용에 영향을 주는 기본값이 있다.** claude_special 단계가 설치하는 mod `korean-reply-rewrite`는 한국어로 물었는데 영어로 답한 응답을 Haiku로 번역해 대화 기록에 저장하므로, 그만큼 호출이 늘고 기록에 남는 응답이 바뀐다.
>
> **sudo를 쓴다.** Linux에서 git이 없으면 패키지 관리자로 설치한다(sudo). Tailscale은 공식 설치 스크립트로 설치하므로 Linux에서는 Tailscale 패키지 저장소도 추가된다.

인자 없이 실행하면 **단계형 설치**가 시작된다. 아래 10개 단계를 차례로 보여 주며, 모든 단계가 기본으로 켜져 있다. 이미 설치된 프로그램은 다시 설치하지 않는다. 새 장비에서 기본값 그대로 설치하면 다음이 설치된다.

| 단계 | 기본으로 하는 일 | 주의할 점 |
| --- | --- | --- |
| base | git이 없으면 설치하고, 뒤 단계에 필요하면 Node 20을 nvm으로 설치한다 | Linux에서는 sudo를 쓴다 |
| harness | Claude Code와 Codex를 각 공식 설치 스크립트로 설치한다 | Grok·OpenCode·Gemini·Antigravity·Copilot은 직접 골라야 설치한다 |
| plugins | Claude Code 플러그인 8개를 사용자 범위로 설치한다: oh-my-claudecode, fluent-korean, ponytail, codex, commit-commands, context7, typescript-lsp, pyright-lsp | 서드파티 마켓플레이스가 포함된다 |
| skills | 번들 스킬 design-lab, tailnet-report를 설치한다 | |
| codegraph | 코드 그래프 도구 CodeGraph를 `npm install -g`로 설치한다 | |
| mcp | Claude Code와 Codex에 CodeGraph MCP 서버를 등록한다 | |
| newline | 줄바꿈 키를 설정한다(기본 Shift+Enter) | |
| claude_special | 출력 스타일을 fluent-korean으로 지정하고, Claude Code mod 3개를 설치하며, OMC HUD를 쓰고 있으면 캐시 표시 래퍼를 붙인다 | |
| tools | 기기들을 사설 네트워크로 묶는 Tailscale을 설치한다. Orca는 jarvis가 관리한다([Orca](#orca는-jarvis가-관리한다)) | Linux에서는 **sudo**가 필요하다 |
| agentsmd | 현재 폴더에 `AGENTS.md`(와 `CLAUDE.md`)를 만든다. 내용은 위 [AGENTS.md](#무엇을-해-주나) 설명을 참고한다 | 이미 있으면 온보딩에서 덮어쓸지 묻고, 기본은 그대로 둔다 |

- Tailscale은 설치만 하며, 로그인(`tailscale up`)은 하지 않는다.
- Jarvis(작성자의 [홈 서버 모니터링 대시보드](https://github.com/thsvkd/jarvis))와 herdr은 직접 골랐을 때만 설치한다.
- 단계 하나가 실패하면 **거기서 멈추고** 뒤 단계는 실행하지 않는다. tools 단계는 agentsmd 단계보다 앞에 있으므로, 예를 들어 Tailscale 설치가 실패하면 `AGENTS.md`도 만들지 않는다. 원인을 고치거나 실패한 단계를 끈 뒤, 남은 단계만 `--stages agentsmd`처럼 지정해 이어서 실행한다.
- 가드 훅과 권한 규칙·권한 모드는 이 설치기가 아니라 jarvis가 설치한다([훅](#훅은-jarvis가-관리한다)).
- 각 용어의 뜻은 [용어](#용어)에 정리해 두었다.

---

## 빠른 시작

**0. 준비**

| 환경 | 필요한 것 |
| --- | --- |
| 공통 | Python 3.9 이상(설치기가 Python으로 동작하므로 미리 설치해 둔다), 인터넷 연결(GitHub·npm 등에서 내려받는다). GitHub 로그인은 필요 없다 |
| macOS | `bash`·`curl`·`tar`(기본 포함), Homebrew(git·Tailscale 설치에 쓴다. 없으면 tools 단계가 실패하므로 그 단계를 끈다). 새 Mac에서는 `xcode-select --install`로 Command Line Tools를 먼저 설치해야 `python3`가 생긴다 |
| Linux | `bash`, `curl` 또는 `wget`, `tar`, `sudo`(git·Tailscale 설치에 쓴다) |
| Windows | PowerShell 5.1 이상, winget(Git·Node·Tailscale 설치에 쓴다). Python은 python.org 설치본을 쓴다(Microsoft Store의 `python.exe` 바로가기로는 실행되지 않는다) |

**1. 미리보기**: 아무것도 바꾸지 않고, 기본 설치가 실행할 작업 목록만 출력한다. 이 목록은 단계별 작업 이름만 보여 준다. 이미 설치된 프로그램은 `present, not claimed`(이미 있으므로 설치하지 않고 설치 기록에도 넣지 않음)로 표시된다.

macOS / Linux:
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages all --dry-run
```
Windows(PowerShell):
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) --stages all --dry-run
```

**2. 설치**: `AGENTS.md`가 현재 폴더에 생기므로 프로젝트 루트로 이동한 뒤 실행한다. 새 터미널을 열자마자(홈 디렉터리에서) 실행하면 `~/AGENTS.md`·`~/CLAUDE.md`가 생기고, Claude Code가 홈 아래의 모든 프로젝트에서 이 파일을 읽는다. 원하지 않으면 온보딩에서 agentsmd 단계를 끈다.

전체 단계를 고르며 설치하려면 인자 없이 실행한다.

macOS / Linux:
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh
```

Windows에서는 Git Bash가 아니라 PowerShell에서 실행한다.
```powershell
irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1 | iex
```

위 명령을 실행하면 온보딩 화면이 뜬다. 화면은 영어이며, 방향키로 고르고 Enter로 확정한다.

1. 첫 화면에서 **Walk**를 고르면 위 10개 단계를 하나씩 켤지 묻는다. **Skip**을 고르면 바로 허브로 간다.
2. **허브**는 단계별 선택을 한 화면에 모아 보여 주는 메뉴다. 여기서 선택을 고친 뒤 **Apply**로 설치하거나, **Preview**로 계획만 보거나, **Quit**으로 아무것도 하지 않고 끝낸다.
3. 이미 설치한 적이 있는 장비에서는 첫 화면 없이 허브부터 열린다.

**3. 마무리**: 설치가 끝나면 Claude Code를 다시 시작한다. 바뀐 설정은 새 세션부터 적용된다. 가드 훅은 jarvis로 설치하고([훅](#훅은-jarvis가-관리한다)), 설치 상태 점검도 jarvis가 맡는다([doctor](#doctor는-jarvis가-맡는다)).

> 터미널이 없는 환경(CI, 다른 에이전트 안에서 실행하는 경우 등)에서 인자 없이 실행하면 묻지 않고 **아무것도 설치하지 않는다**. `--stages`나 개별 옵션을 주면 터미널이 없어도 그대로 설치한다.

특정 버전으로 고정하려면 [태그 목록](https://github.com/thsvkd/ai-setup/tags)에서 버전을 골라, 그 버전의 설치 스크립트를 받고 `CLAUDE_SETUP_REF`를 함께 준다(`<태그>`를 바꿔 넣는다).
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/<태그>/install.sh | CLAUDE_SETUP_REF=<태그> sh
```

---

## 업데이트

단계형 설치를 다시 실행하면 이미 설치한 항목은 건너뛰므로 파일이 최신으로 바뀌지 않는다. 항목별로 아래 옵션을 주고 다시 실행한다(옵션 넘기는 법은 [옵션](#옵션)에 있다).

| 업데이트할 것 | 방법 |
| --- | --- |
| 가드 훅 | jarvis가 관리한다([훅](#훅은-jarvis가-관리한다)) |
| 줄바꿈 키 | `--keybinds` |
| 번들 스킬 | `--skills`. 사용자가 고친 스킬은 바꾸지 않는다 |
| mod | `--mods`. 사용자가 고친 mod 파일은 바꾸지 않는다 |
| 하네스·도구·플러그인 | 저장소를 clone한 뒤 [update-ai](#update-ai)를 실행한다 |

```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --keybinds
```

---

## 제거

제거는 설치 기록(`~/.claude/.claude-code-setup.json`)에 남은 항목만 되돌리고, 원래 있던 설정은 그대로 둔다. 바뀌는 설정 파일은 `<파일>.bak.<타임스탬프>`로 백업된다. 설치한 방식(단계형 설치와 개별 옵션 설치의 차이는 [옵션](#옵션)에 있다)에 따라 명령이 다르다.

| 설치한 방식 | 제거 명령 |
| --- | --- |
| 단계형 설치(인자 없이 실행, `--stages`) | `--stages <단계 목록> --uninstall` |
| 개별 옵션 설치(`--keybinds`, `--no-onboard` 등) | `--uninstall`. `--omc`·`--output-style`로 설치한 플러그인은 남긴다 |

**1. 먼저 미리보기로 무엇이 빠지는지 확인한다.**
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages all --uninstall --dry-run
```

**2. 설정만 되돌린다.** 줄바꿈 키, 출력 스타일·mod를 되돌리고, 설치한 프로그램은 남긴다. 플러그인·MCP 등록·번들 스킬도 빼려면 목록에 `plugins,mcp,skills`를 더한다. Tailscale 패키지도 지우려면 `tools`를 더한다.
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages newline,claude_special --uninstall
```

> [!WARNING]
> `--stages all --uninstall`은 이 설치기가 **설치한 프로그램 자체를 지운다**. Claude Code·Codex 같은 하네스, Claude Code 플러그인과 마켓플레이스, CodeGraph와 MCP 등록, Tailscale 패키지(`sudo apt-get remove` 등)가 여기에 해당한다. 원격에서 Tailscale로 접속한 채 제거하면 그 연결이 끊긴다.

**3. 설치한 프로그램까지 모두 지운다.**
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages all --uninstall
```

PowerShell에서는 같은 인자를 scriptblock 형태로 넘긴다. 예: `& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) --stages all --uninstall --dry-run`

다음은 남는다.

- 설치하기 전부터 있던 프로그램과 설정, 그리고 nvm으로 설치한 Node
- 프로젝트의 `AGENTS.md`·`CLAUDE.md`(필요하면 직접 지운다)
- 설치가 새로 만든 키바인딩 파일 중 우리 항목만 빠진 빈 파일(`[]` 등). VS Code·Cursor가 없어도 그 `keybindings.json`을 만들기 때문에, 이 빈 파일이 남을 수 있다
- Orca와 그 설치 기록(`tool_installs.orca`·`tool_installs.orca_server`). 아래처럼 jarvis가 지운다
- 가드 훅(`~/.claude/hooks/`), `settings.json`의 훅 등록·권한 규칙·권한 모드, 그 설치 기록(`hook_files`·`added_allow`·`default_mode_*` 등). 아래처럼 jarvis가 지운다

자세한 규칙은 [제거가 되돌리는 것](#제거가-되돌리는-것)에 있다.

### Orca는 jarvis가 관리한다

`--tools orca`(`-Tools orca`), `--orca-desktop`, `update-ai orca`는 아무것도 바꾸지 않고 안내만 출력한 뒤 종료 코드 1로 끝난다. 설치·업데이트는 jarvis 체크아웃이나 게이트웨이의 현재 버전 폴더에서 실행한다(PATH 래퍼는 없다). `python3 -m jarvis module orca plan --json`으로 계획을 보고, 그 출력의 plan_id로 `python3 -m jarvis module orca apply --json --plan-id <id>`를 실행한다. 예전에 ai-setup이 설치한 Orca는 `python3 -m jarvis module orca uninstall --json --dry-run`으로 먼저 확인하고, 그 dry-run의 plan_id로 `python3 -m jarvis module orca uninstall --json --plan-id <id>`를 실행해 지운다. jarvis는 ai-setup의 Windows S4U 기록을 자기 것으로 보고 예약 작업·러너·서비스 폴더를 예전 ai-setup 제거와 똑같이 지우며, Linux·macOS에서 채택한(`adopted: true`) 유닛만 남긴다.

### 훅은 jarvis가 관리한다

가드 훅(삭제를 휴지통으로 돌리는 shim, git 작업 전 스냅샷, 루트·홈 전체 삭제와 디스크 파괴 차단)과 그 권한 규칙·권한 모드는 jarvis 훅 모듈이 설치·갱신·제거한다. 설계 배경은 [docs/2026-07-31-delete-guard-architecture.md](docs/2026-07-31-delete-guard-architecture.md)에 남아 있다. `--hooks`(`-Hooks`)와 `--stages`에 든 `hooks`는 `--uninstall`과 함께여도 아무것도 바꾸지 않고 안내만 출력한 뒤 종료 코드 1로 끝난다. 전체 설치·전체 제거(`--no-onboard`, `--uninstall`, `--stages all`, `--stages all --uninstall`)는 훅을 건너뛰고 설치 기록의 훅 항목을 그대로 둔다. 설치는 jarvis 체크아웃이나 게이트웨이의 현재 버전 폴더에서 `python3 -m jarvis module hooks plan --json`으로 계획을 보고, 그 출력의 plan_id로 `python3 -m jarvis module hooks apply --json --plan-id <id>`를 실행한다(Windows는 `py -3 -m jarvis ...`). 제거는 `python3 -m jarvis module hooks uninstall --json --dry-run`으로 먼저 확인하고, 그 dry-run의 plan_id로 `python3 -m jarvis module hooks uninstall --json --plan-id <id>`를 실행한다. jarvis는 ai-setup이 남긴 설치 기록(`~/.claude/.claude-code-setup.json`의 `hook_files`·권한 기록)을 그대로 읽어, 예전에 ai-setup으로 설치한 훅도 이어서 관리한다.

### doctor는 jarvis가 맡는다

`--doctor`(`-Doctor`)는 아무것도 바꾸지 않고 안내만 출력한 뒤 종료 코드 1로 끝난다. 설치된 하네스·도구와 버전, 중복 설치, 남아 있는 옛 훅, 설정 파일의 평문 시크릿 위치(키 이름만), 스킬 잠금 파일 밖의 스킬을 읽기 전용으로 점검하려면 jarvis 체크아웃이나 게이트웨이의 현재 버전 폴더에서 `python3 -m jarvis module doctor status --json`(Windows는 `py -3 -m jarvis ...`)을 실행한다.

---

## 옵션

설치 방식은 두 가지다.

- **단계형 설치**: 인자 없이 실행하거나 `--stages`를 준다. 위 10개 단계를 계획하고 설치 기록에 남긴다.
- **개별 옵션 설치**: `--keybinds`, `--skills` 같은 옵션으로 원하는 부분만 설치한다. `--no-onboard`는 질문 없이 `AGENTS.md`·키바인딩·번들 스킬을 설치한다. 옵션을 하나라도 주면 질문 없이 바로 실행한다.

`--dry-run`만 주면 `--no-onboard`의 계획을 보여 준다. 단계형 설치의 계획은 `--stages all --dry-run`으로 본다.

| POSIX | PowerShell | 동작 |
| --- | --- | --- |
| `--stages <목록>` | `--stages <목록>` | 단계형 설치. `all` 또는 쉼표로 구분한 단계 이름(예: `newline,agentsmd`) |
| `--jarvis-role <역할>` | `--jarvis-role <역할>` | `--stages`와 함께 Jarvis를 `gateway` 또는 `core` 역할로 설치 |
| `--herdr` | `--herdr` | `--stages`와 함께 herdr 설치 |
| `--ss-caps` | `--ss-caps` | `--stages`와 함께, Jarvis용 `ss` 복사본에 `cap_sys_ptrace`·`cap_dac_read_search` 권한을 준다(sudo). 이 복사본은 모든 파일을 읽을 수 있으므로 필요할 때만 쓴다 |
| `--dry-run` | `-DryRun` | 아무것도 바꾸지 않고 변경 계획만 출력 |
| `--no-onboard` | `-NoOnboard` | 질문 없이 `AGENTS.md`·키바인딩·번들 스킬 설치 |
| `--hooks` | `-Hooks` | jarvis로 옮겨 갔다. 아무것도 바꾸지 않고 안내만 출력한 뒤 종료 코드 1로 끝난다([훅](#훅은-jarvis가-관리한다)) |
| `--agentsmd` | `-AgentsMd` | 현재 폴더에 `AGENTS.md`만 설치 |
| `--harness <목록>` | `-Harness <목록>` | 대상 하네스: `claude`·`codex`·`grok`·`opencode`·`agy`·`gemini`·`copilot`. 개별 옵션 설치에서는 `AGENTS.md`를 읽게 할 하네스를 고르며, `all`(기본)은 `claude`·`codex`·`grok`·`opencode`를 뜻한다. 단계형 설치에서는 설치할 하네스를 고르며, 기본은 Claude Code와 Codex다 |
| `--skills` | `-Skills` | 번들 스킬만 설치(`~/.claude/skills`) |
| `--keybinds` | `-Keybinds` | 줄바꿈 키바인딩만 설치 |
| `--newline <값>` | `-Newline <값>` | 줄바꿈 키: `shift-enter`(기본) 또는 `ctrl-enter` |
| `--omc` | `-Omc` | oh-my-claudecode 플러그인 설치와 HUD 캐시 표시 래퍼 |
| `--mods` | `-Mods` | Claude Code mod 3개 설치(Claude Code v2.1.290 이상) |
| `--output-style` | `-OutputStyle` | [fluent-korean](https://github.com/snflkd/fluent-korean) 플러그인 설치와 출력 스타일 지정 |
| `--uninstall` | `-Uninstall` | 설치한 것만 골라 되돌리기. 단계형 설치는 `--stages <목록>`과 함께 쓴다 |
| `--doctor` | `-Doctor` | jarvis로 옮겨 갔다. 아무것도 바꾸지 않고 안내만 출력한 뒤 종료 코드 1로 끝난다([doctor](#doctor는-jarvis가-맡는다)) |
| `--help` | `-Help` | 도움말 |

옵션을 넘기는 방법은 다음과 같다. POSIX에서는 `sh -s --` 뒤에 붙인다.
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --keybinds --dry-run
```

PowerShell에서는 `| iex`로 인자를 넘길 수 없으므로 scriptblock으로 감싼다. PowerShell은 `-DryRun` 같은 PowerShell 형식과 `--dry-run` 같은 긴 형식을 모두 받으며, `--stages`처럼 PowerShell 형식이 없는 옵션은 긴 형식으로 쓴다.
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) -Keybinds -DryRun
```

저장소를 clone했다면 `bash scripts/setup.sh --dry-run`이나 `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -DryRun`처럼 직접 실행해도 된다. Windows 기본 실행 정책은 내려받은 스크립트 파일을 막으므로 `-ExecutionPolicy Bypass`를 붙인다(원라이너는 이 처리를 스스로 한다).

---

## 무엇이 설치되나

| 위치 | 내용 |
| --- | --- |
| `~/.claude/.claude-code-setup.json` | 설치 기록. 제거할 때 이 기록에 남은 것만 되돌린다 |
| `./AGENTS.md`, `./CLAUDE.md` | 프로젝트 작업 규칙. `CLAUDE.md`는 `@AGENTS.md` 한 줄짜리 파일이며, 하네스에 `claude`가 있을 때만 만든다. 이미 있으면 건너뛴다 |
| `~/.claude/skills/design-lab/`, `~/.claude/skills/tailnet-report/` | 번들 스킬 |
| 줄바꿈 키 | `~/.claude/keybindings.json`, `~/.codex/config.toml`, VS Code·Cursor `keybindings.json`(에디터가 없어도 만든다), `~/.tmux.conf`(POSIX만), Windows Terminal(`ctrl-enter`일 때만) |
| OMC HUD 래퍼 | `~/.claude/hud/omc-hud-ttl.mjs`, `settings.json`의 `statusLine` 래퍼와 `refreshInterval` |
| mod | `~/.claude/mods/bash-diff-filter/`, `~/.claude/mods/cache-ttl-status/`, `~/.claude/mods/korean-reply-rewrite/`, `settings.json`의 `env.CLAUDE_CODE_PLUGIN_DIRS` |
| 출력 스타일 | `settings.json`의 `outputStyle` = `fluent-korean:fluent-korean`. 원래 값은 설치 기록에 남긴다 |

가드 훅(`~/.claude/hooks/`)과 `settings.json`의 훅 등록·권한 규칙은 jarvis가 설치한다([훅](#훅은-jarvis가-관리한다)).

**보안 주의**: `CLAUDE_SETUP_REPO`·`CLAUDE_SETUP_REF` 환경 변수는 내려받아 실행할 저장소와 버전을 바꾼다. 신뢰할 수 없는 입력이 이 변수를 바꿀 수 있는 환경(공유 CI 등)에서는 설정하지 않는다.

---

## 번들 스킬

- [design-lab](res/skills/design-lab/SKILL.md): 디자인 시안마다 동작하는 앱을 만들어 비교하고, 선택과 의견을 남기는 갤러리를 만든다. Claude Code에서 `/design-lab 예약 앱 시안 3개를 비교할 갤러리를 만들어줘`처럼 부르거나, 시안 비교를 요청하면 자동으로 불러온다.
- [tailnet-report](res/skills/tailnet-report/SKILL.md): 서버를 실제로 조사한 근거로 보고서 페이지를 만들고, `tailscale serve`로 자신의 Tailscale 네트워크(tailnet)에만 게시한다. 페이지 디자인은 외부 스킬 [visual-explainer](https://github.com/nicobailon/visual-explainer)(MIT)에 맡기므로, 먼저 `npx skills add nicobailon/visual-explainer#v0.12.0 -g`로 설치해 둔다. 이 설치기는 외부 스킬을 설치하지 않는다.

스킬 설치 기록은 `~/.claude/.claude-code-setup-skills.json`에 파일 해시로 남긴다. 같은 이름의 기존 사용자 스킬이나 설치 후 사용자가 고친 스킬은 덮어쓰거나 지우지 않고, 종료 코드 1로 알린다. `--skills --uninstall`(PowerShell `-Skills -Uninstall`)은 이 설치기가 관리하는 스킬만 제거한다. 개인 스킬 경로와 호출 방식은 [Claude Code 공식 문서](https://code.claude.com/docs/en/skills)를 따른다.

---

## 용어

| 용어 | 뜻 |
| --- | --- |
| 하네스 | 모델을 실행하는 에이전트 프로그램. Claude Code, Codex CLI, Grok CLI 등 |
| 단계형 설치, Walk, 허브 | 인자 없이 실행했을 때의 설치 방식. Walk는 단계를 하나씩 묻는 진행 방식이고, 허브는 단계별 선택을 모아 보여 주는 메뉴다 |
| 설치 기록 | 이 설치기가 무엇을 넣었는지 적어 두는 `~/.claude/.claude-code-setup.json`. 제거는 이 기록에 있는 것만 되돌린다 |
| 가드 훅 | Claude Code가 명령을 실행하기 전에 부르는 `danger_guard.py`. 위험한 삭제를 막고 git 스냅샷을 남긴다. jarvis가 관리한다 |
| OMC, HUD | [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 플러그인과, 그 플러그인이 Claude Code 화면 아래에 띄우는 상태 표시줄(`statusLine`) |
| mod | Claude Code의 화면과 동작을 바꾸는 확장. [공식 문서](https://code.claude.com/docs/en/plugins/mods/overview) |
| CodeGraph, MCP | 코드베이스를 미리 색인해 두는 로컬 지식 그래프 도구와, 그 색인을 에이전트가 쓰게 해 주는 MCP(Model Context Protocol) 서버 |
| Tailscale, tailnet | 기기들을 사설 네트워크로 묶는 VPN과, 그렇게 묶인 내 네트워크 |
| Jarvis, herdr | 작성자의 홈 서버 모니터링 대시보드와, 코딩 에이전트를 실행하는 런타임 도구([herdr.dev](https://herdr.dev)). 직접 골랐을 때만 설치한다 |

---

## 상세

설치해서 쓰는 데는 여기까지면 충분하다. 아래는 동작 원리와 설계 이유다.

<details>
<summary><b>update-ai</b> — 설치된 하네스·도구를 한 번에 최신으로</summary>

## update-ai

저장소를 clone해 두면, 설치된 하네스(claude, codex, grok, opencode, gemini, agy, copilot)와 도구(herdr, CodeGraph), 그 플러그인을 한 번에 최신으로 올릴 수 있다. 설치되지 않은 것은 건너뛰고 새로 설치하지 않으며, npm·winget·brew 중 실제로 설치한 방식으로 올린다. npm 외의 공식 설치 방식이 없는 gemini·CodeGraph(와 Windows의 opencode·copilot)는 버전마다 디렉터리를 따로 두는 npm-release 배치(`res/tools/npm_release.py`)로 깔고 올린다. CodeGraph의 `codegraph upgrade`는 호출하지 않는다.

```sh
git clone https://github.com/thsvkd/ai-setup.git && cd ai-setup
bash scripts/update-ai.sh --check            # 현재 버전과 최신 버전만 본다
bash scripts/update-ai.sh                    # 전부 올린다
bash scripts/update-ai.sh --only claude,codex
```
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Update-Ai.ps1 -Check
powershell -ExecutionPolicy Bypass -File .\scripts\Update-Ai.ps1 -Only claude,codex
```

실행 중인 세션이 있어도 올린다. 새 버전은 다른 디렉터리에 깔리고 진입점만 바뀌므로, 이미 떠 있는 세션은 재시작할 때까지 이전 버전으로 계속 돈다. 파일을 제자리에서 바꾸는 예전 설치(npm -g, winget)와 codex 데몬 교체만 세션이 돌면 보류로 남기며, 세션을 끊어도 되면 `--allow-interrupt`(PowerShell `-AllowInterrupt`)를 준다. 하나가 실패해도 나머지를 계속하고, 마지막에 종료 코드 1로 끝난다.

</details>

<details>
<summary><b>AGENTS.md와 하네스 선택</b></summary>

### AGENTS.md와 `--harness`

`--harness`는 **무엇을 쓸지**가 아니라 **무엇을 읽는지**로 갈린다. Codex·Grok·OpenCode는 루트 `AGENTS.md`를 직접 읽으므로 그 파일 하나면 되고, Claude Code는 `AGENTS.md`를 읽지 않고 `CLAUDE.md`를 읽으므로 `@AGENTS.md` 한 줄짜리 `CLAUDE.md`가 추가로 필요하다(Windows에서 심볼릭 링크는 관리자 권한을 요구해서 import를 쓴다). 그래서 `AGENTS.md`는 항상 설치되고, `CLAUDE.md`는 선택에 `claude`가 있을 때만 생긴다. 여러 하네스를 함께 쓰는 프로젝트가 흔하므로 다중 선택이 기본이며 — `--harness claude,codex` — 온보딩에서도 체크박스로 고른다. 모르는 이름을 주면 아무것도 쓰지 않고 종료 코드 1로 끝난다.

기존 `AGENTS.md`가 있으면 건너뛴다. 워커 `setup_agentsmd`의 `--force`는 기존 파일을 `.bak.<타임스탬프>`로 백업한 뒤 덮어쓴다 — 온보딩이 내부적으로 쓰는 옵션이다.

</details>

<details>
<summary><b>줄바꿈 키</b> — 어떻게 맞추고 무엇이 안 되는가</summary>

## 줄바꿈 키

CLI 에이전트의 프롬프트에서 **줄을 넣고 전송하지 않는** 키를 세 OS에서 같은 의미로 만든다. 값은 `shift-enter`(기본) 또는 `ctrl-enter` 하나다. **Enter 단독은 계속 전송**이고, 고르지 않은 쪽 수정 Enter는 각 에이전트 기본값 그대로 둔다.

대상은 Claude Code CLI · Codex CLI · Grok Build CLI다. Gemini CLI와 Cursor/VS Code의 IDE 챗 입력창은 범위 밖이다(그쪽은 이미 Shift+Enter가 줄바꿈이다).

`--newline`은 다른 플래그와 조합할 수 있다 — `--keybinds --newline ctrl-enter`는 키바인딩만 Ctrl+Enter로, `--no-onboard --newline ctrl-enter`는 질문 없는 기본 설치를 Ctrl+Enter로 한다. 재실행 시 `--newline`을 주지 않으면 설치 기록에 남은 이전 선택을 그대로 쓰고, 기록이 없으면 `shift-enter`다. 값이 둘 중 하나가 아니면 아무것도 쓰지 않고 종료 코드 1로 끝난다.

### 두 층으로 맞춘다

1. **터미널 층** — Shift+Enter를 Enter와 구분하지 못하는 터미널(VS Code·Cursor 통합 터미널)에 `고른 키 → 줄바꿈 시퀀스` 바인딩을 넣는다. 시퀀스는 `ESC` + `CR` (바이트 `0x1B 0x0D`) 하나로 고정돼 있고, `when`은 `terminalFocus`만 걸어 에디터·노트북의 Shift+Enter는 건드리지 않는다. POSIX에서는 `~/.tmux.conf`에 `extended-keys`가 없을 때만 추가한다 — 이게 꺼져 있으면 tmux가 수정 Enter를 통째로 삼킨다.
2. **에이전트 층** — Claude `~/.claude/keybindings.json`의 `bindings` 배열 안 `Chat` 컨텍스트에 `chat:newline`을(예전 설치기가 남긴 최상위 `Chat` 키는 이 배열로 옮긴다), Codex `~/.codex/config.toml`의 `insert_newline`에 고른 키를 **합집합**으로 넣는다. Grok은 키맵을 리맵할 수 없으므로 파일을 만들지 않는다 — 터미널이 보내는 시퀀스에만 의존한다.

Windows Terminal·iTerm2·Ghostty·Kitty·WezTerm 같은 터미널은 Shift+Enter를 이미 Enter와 다르게 보낸다. 여기에 Shift+Enter 시퀀스를 **덧붙이면 줄바꿈이 두 번** 생기므로, `shift-enter`를 고른 경우 Windows Terminal에는 줄바꿈 바인딩을 **넣지 않는다**(이전 설치가 넣어둔 관리 항목이 있으면 그것만 정리한다). `ctrl-enter`를 고른 경우에만 `Ctrl+Enter` 번역을 넣는다.

VS Code / Cursor `keybindings.json` 경로는 OS별로 다르다 — Windows `%APPDATA%\Code\User\`, macOS `~/Library/Application Support/Code/User/`, Linux `~/.config/Code/User/`.

### 파일을 어떻게 고치나

바꾸기 전 원본을 `<파일>.bak.<타임스탬프>`로 남기고, 임시 파일에 쓴 뒤 교체한다 — 쓰기 도중 끊겨도 원본이 반쯤 잘리지 않는다. 대상이 심볼릭 링크면(dotfile 관리자를 쓰는 경우) 링크를 갈아치우지 않고 가리키는 실체를 고치며, 기존 파일 권한을 그대로 옮긴다. VS Code·Cursor `keybindings.json`은 우리 항목만 텍스트로 넣고 빼므로 주석과 서식이 유지된다. 배열이 없는(주석만 있는) 파일은 다시 직렬화하므로 그때는 주석이 사라진다. VS Code가 허용하는 트레일링 콤마는 우리도 읽는다. 그래도 읽지 못한 대상이 있으면 그 사실을 목록으로 알리고 **0이 아닌 종료 코드**로 끝낸다 — 적용되지 않았는데 '완료'라고 말하지 않기 위해서다.

### 안 되는 것

- **gnome-terminal 등 Shift+Enter를 구분하지 못하는 터미널** — 로컬 세션에서는 맞출 수 없다. 설치는 실패하지 않고 경고만 남긴다. Linux는 로컬 gnome-terminal 대신 Windows Terminal/Cursor에서 `ssh`로 붙는 경로를 쓰면 그대로 동작한다.
- **Grok의 `/multiline`(`/ml`, `Ctrl+M`) 모드** — 이 토글이 켜지면 Enter와 Shift+Enter의 의미가 **반대**가 된다(Enter=줄바꿈, Shift+Enter=전송). Grok은 키를 리맵할 수 없어 이 상태를 Claude/Codex와 한 키로 맞추는 것이 불가능하다. 설치기는 그 토글을 켜거나 끄지 않고 리포트에 한 줄 경고만 한다. 기준은 **Grok 기본 프롬프트(multiline 꺼짐)** 다.
- **에이전트가 아예 없을 때** — 바이너리와 설정 디렉터리가 **둘 다** 없으면 그 에이전트는 건너뛰고 설치는 성공한다. 하나라도 있으면 키맵을 쓴다.

</details>

<details>
<summary><b>OMC와 캐시 TTL HUD</b> — <code>--omc</code>가 하는 일</summary>

## OMC와 캐시 TTL HUD

`--omc`를 주면 [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 플러그인을 `claude plugin marketplace add` / `claude plugin install`로 설치하고, OMC HUD의 세션 경과 시간(`session:45m`) 자리에 **프롬프트 캐시 TTL 잔여 시간**(`cache:57m`)을 띄운다. 단계형 설치에서는 plugins 단계가 OMC 플러그인을 설치하고, claude_special 단계가 이미 OMC HUD를 쓰는 `statusLine`에만 이 래퍼를 붙인다. 서드파티 플러그인이므로 `--no-onboard`에는 포함하지 않는다.

- 값은 Claude Code가 statusLine stdin으로 넘기는 `prompt_cache.expires_at`에서 매 렌더마다 계산한다. 2분 이하면 노랑, 만료되면 `cache:cold`(빨강)이다. 캐시 정보가 없으면(구버전 Claude Code) `session:` 표시를 그대로 둔다. OMC HUD 프리셋에서 session 요소를 끈 경우에는 바꿀 자리가 없어 표시되지 않는다.
- `~/.claude/hud/omc-hud-ttl.mjs`를 복사하고 기존 `statusLine.command` 앞에 래퍼 실행 명령을 끼운다. node는 OMC와 같은 방식으로 찾는다 — POSIX는 OMC의 `find-node.sh`, Windows는 `~/.claude/.omc-config.json`의 `nodeBinary`, 둘 다 없으면 PATH의 `node`. 입력이 없어도 카운트다운이 흐르도록 `statusLine.refreshInterval`이 없으면 `10`(초)을 넣는다.
- `statusLine`이 없으면 플러그인의 정본 템플릿으로 OMC HUD를 먼저 설치한다. OMC가 아닌 다른 `statusLine`이 있으면 사용자 설정이므로 파일 하나 만들지 않는다. `settings.json`이나 설치 기록을 파싱할 수 없으면 쓰지 않고 멈춘다.
- `--uninstall`은 이 설치가 만든 것만 되돌린다 — 래퍼, 우리가 넣은 값 그대로인 `refreshInterval`, 그리고 설치가 새로 만든 `statusLine`·`settings.json`. 설치가 복사한 HUD 파일은 그 `statusLine`도 함께 치울 때, 복사 당시 내용 그대로인 경우에만 지운다 — `omc-setup`이 다시 쓴 파일은 OMC 것이다. 원래 있던 OMC 플러그인과 OMC HUD는 남긴다.
- OMC HUD는 렌더할 때마다(위 `refreshInterval`이면 10초마다) 프로젝트의 `.omc/state/hud-stdin-cache.json`을 다시 쓴다. 그래서 Claude Code가 Bash 실행 뒤 보여 주는 '바뀐 파일' diff에 이 파일이 거의 매번 끼어든다. 이 항목을 빼려면 `--mods`의 `bash-diff-filter`를 함께 설치한다.
- CLAUDE.md 등 OMC의 나머지 설정은 Claude Code 안에서 `/oh-my-claudecode:omc-setup`으로 진행한다. 그 과정에서 `statusLine`이 다시 써지면 `--omc`를 한 번 더 실행하면 된다.

</details>

<details>
<summary><b>Claude Code mod</b> — <code>--mods</code>가 하는 일</summary>

## Claude Code mod

`--mods`를 주거나 단계형 설치의 claude_special 단계를 켜면 `res/mods/` 의 번들 [mod](https://code.claude.com/docs/en/plugins/mods/overview)를 `~/.claude/mods/<이름>/`에 복사하고, `~/.claude/settings.json`의 `env.CLAUDE_CODE_PLUGIN_DIRS`에 그 경로를 넣어 매 세션 로드되게 한다. mod는 Claude Code v2.1.290 이상에서만 동작하므로 `--no-onboard`에는 포함하지 않는다.

| mod | 하는 일 |
| --- | --- |
| `bash-diff-filter` | Bash 실행 뒤 보여 주는 '바뀐 파일' diff에서 OMC HUD가 렌더마다 다시 쓰는 `.omc/state/hud-stdin-cache.json`(세션별 경로 포함)을 뺀다. 걸러내는 대상은 Bash 결과의 `bashEditDiff` 필드이며, 이 필드는 원래 모델에 전달되지 않으므로 화면 표시만 바뀐다. `OMC_STATE_DIR`로 OMC 상태를 프로젝트 밖에 두면 이 파일은 애초에 표시되지 않으므로 거르지 않는다. |
| `cache-ttl-status` | 프롬프트 캐시 잔여 시간(`cache:57m`, 1분 미만은 초, 만료되면 `cache:cold`)을 **프롬프트 아래 상태 줄**에 띄운다. mod API는 statusLine의 `prompt_cache.expires_at`을 주지 않으므로, 메인 대화의 요청이 캐시를 읽거나 쓴 시각에 TTL을 더해 계산한다(서브에이전트 요청은 제외). TTL은 mod 설정 `ttl`(`1h` 기본, `5m`)로 시작하고, 모델을 바꾸면 엔진이 알려 주는 실제 값으로 갱신한다. 계산값이므로 실제 만료 시각과 몇 초 어긋날 수 있다. |
| `korean-reply-rewrite` | 한국어로 물었는데 메인 루프가 영어로 답하면, 그 응답 블록을 저장 직전에 Haiku로 한국어로 번역해 기록과 다음 요청에 넣는다. 영어 응답이 기록에 쌓이면 이후 응답도 영어로 굳기 때문에, 영어 선례를 남기지 않는 것이 목적이다. 프롬프트에서 한글 단어가 영어 단어보다 적거나 영어·영작·번역·커밋·PR을 언급했으면 바꾸지 않는다. 화면이 없는 `claude -p` 실행, 서브에이전트 응답, thinking은 건드리지 않는다. 짝이 맞는 ```` ``` ```` 펜스 코드와 인라인 코드는 자리표시자로 빼 두었다가 그대로 되돌리며(`~~~` 펜스·들여쓰기 코드·닫히지 않은 펜스는 번역 지시로만 보호한다), 번역이 실패하거나 잘리거나 자리표시자가 어긋나면 원문을 그대로 둔다. 터미널에는 스트리밍과 번역이 끝날 때까지(긴 답은 수십 초) 영어 원문이 보였다가 저장되면 번역본으로 바뀐다. 영어 블록마다 Haiku 호출이 한 번 늘어난다. |

- `--omc`의 HUD 래퍼(`session:` 자리에 `cache:`)와는 별개다. 둘 다 설치하면 TTL이 HUD 안과 프롬프트 아래 두 곳에 보인다.
- 테스트(`*.test.ts`)와 엔진이 로드 때 만드는 타입(`.claude-plugin/types/`)은 복사하지 않는다. 같은 이름의 폴더에 내용이 다른 파일이 있으면 덮어쓰지 않고 멈춘다.
- `--uninstall`은 우리가 넣은 경로와 복사 당시 그대로인 파일, 그리고 엔진이 만든 타입 폴더만 치운다. 사용자가 고친 mod 파일은 남긴다(env에서 빠지므로 더는 로드되지 않는다).
- 셸에서 `CLAUDE_CODE_PLUGIN_DIRS`를 따로 export하고 있다면 그 값이 `settings.json`의 값보다 우선할 수 있으니, 그 경우에는 경로를 직접 합쳐 준다.
- mod 하나를 고치려면 `res/mods/<이름>/`에서 `claude plugin validate .`와 `claude plugin test .`로 확인한다.

</details>

<details>
<summary><b>제거가 되돌리는 것</b></summary>

### 제거가 되돌리는 것

`--uninstall`은 설치 기록(`~/.claude/.claude-code-setup.json`)을 근거로 이 설치기가 넣은 것만 되돌린다. 훅·권한 항목·`defaultMode`는 jarvis가 되돌리므로 건드리지 않고, 그 설치 기록도 남긴다([훅](#훅은-jarvis가-관리한다)). 사용자가 원래 갖고 있던 설정과 그 외 키는 그대로 보존되며 변경 전 `settings.json.bak.<타임스탬프>`를 남긴다. `settings.json`을 설치가 새로 만든 경우, 되돌린 뒤 비면 파일도 제거한다. 줄바꿈 키바인딩도 함께 되돌리는데, **무엇을 '우리 것'으로 볼지는 대상마다 다르다.**

- **시그니처로 식별**(VS Code·Cursor): 명령 + `when` + 시퀀스가 우리가 쓰는 것과 정확히 같은 항목만 제거한다. 이 조합은 이 설치가 만들어내는 형태라, 누가 먼저 넣었든 같은 항목이다 — 예컨대 Claude `/terminal-setup`이 넣어둔 `shift+enter` → `sendSequence` 항목도 제거 대상이다. 시퀀스가 다른 사용자 항목(에디터·노트북의 Shift+Enter)은 그대로 둔다.
- **설치 기록으로 식별**(tmux·Claude·Codex·Windows Terminal): `extended-keys` 줄, Claude의 `chat:newline`, Codex의 `shift-enter`는 전부 사용자가 직접 쓰는 값과 글자까지 같다. 값이 같다는 이유로 지우면 남의 설정을 지우는 것이므로, 설치 기록에 '설치가 넣었다'고 적힌 항목만 되돌린다. 기록이 없으면 건드리지 않는다. 설치가 기존 값을 덮어썼다면 그 값도 기록해 두었다가 되돌린다.

Codex의 기존 `ctrl-j` 처럼 우리가 넣지 않은 키는 남는다. 우리 키만 빠져 `insert_newline`이 비면 그 줄과 빈 `[tui.keymap.editor]` 테이블까지 지운다 — 빈 배열을 남기면 설치 전에 없던 '줄바꿈 전면 언바인드'라는 새 설정을 만드는 셈이기 때문이다. `--keybinds --uninstall`이면 키바인딩만 제거한다.

</details>

<details>
<summary><b>온보딩</b> — 파이프 설치에서 프롬프트가 동작하는 이유</summary>

## 온보딩

### `curl | sh`에서 대화형 프롬프트가 동작하는 이유

`curl -fsSL install.sh | sh`는 **stdin이 스크립트 본문**이다. 이 상태에서 프롬프트가 stdin을 읽으면 스크립트의 나머지를 삼키거나 EOF를 만난다. 후보 라이브러리 네 개를 pty 위에서 실측해보면 결과가 이렇다:

| 라이브러리 | 일반 실행 | `curl \| sh` | `/dev/tty` 재바인딩 후 |
| --- | --- | --- | --- |
| questionary (예전 채택) | ✅ | ❌ **조용히 첫 항목 확정** | ✅ |
| InquirerPy | ✅ | ❌ `EOFError` | ✅ |
| beaupy | ✅ | ❌ | ❌ 멈춤 |
| cutie | ✅ | ❌ | ✅ |

주목할 건 예전에 쓰던 questionary의 실패 방식이다 — 에러도 경고도 없이 **첫 항목("전체 설치")을 자동으로 확정**한다. 사용자가 아무것도 고르지 않았는데 전역 설치가 진행되는, 가장 위험한 실패 모드다.

그래서 `res/onboard.py`는 프롬프트를 띄우기 전에 제어 터미널(POSIX `/dev/tty`, Windows `CONIN$`/`CONOUT$`)을 직접 열어 fd 0/1에 얹는다. 터미널을 못 열면 대화형을 **아예 포기한다** — 라이브러리에게 판단을 맡기지 않는다.

### 물어볼 수 없을 때와 사용자가 거부했을 때는 다르다

온보딩은 종료 코드로 네 상황을 구분하고, 호출부는 이를 다르게 처리한다:

| 코드 | 상황 | 설치 동작 |
| --- | --- | --- |
| `0` | 사용자가 선택을 마침 | 고른 대로 실행 |
| `1` | 프롬프트가 도중에 깨짐 (렌더·입력 오류, 파이썬 traceback) | **아무것도 설치하지 않고 중단** |
| `2` | 물어볼 수 없음 (TTY 없음 / CI / Git Bash / 콘솔 준비 실패) — 프롬프트를 띄우기 전에 판정 | **아무것도 설치하지 않고 끝낸다** — 실패가 아니다 |
| `130` | 사용자가 `Ctrl+C`로 취소 | **아무것도 설치하지 않고 중단** |

질문 없이 예전 기본 설치를 하는 경로는 `--no-onboard` 뿐이다. 코드 `2` 와 Skip 은 설치하지 않는다. CI 감지는 TTY 검사와 별도로 둔다 — `docker -t`나 tmux처럼 CI가 TTY를 붙여주는 경우가 있어 TTY 유무만으로는 못 거른다.

### 프롬프트를 직접 그리는 이유

화면은 [`@clack/prompts`](https://github.com/bombshell-dev/clack)(`npx skills` 등이 쓰는 것)의 관용구 — `┌ │ ◆ ◇ └` 거터, `●/○` 라디오, `◼/◻` 체크박스 — 를 따르되, [`res/tui.py`](res/tui.py)가 **표준 라이브러리만으로** 그린다. 필요한 것은 select·multiselect·confirm 세 가지뿐이다.

예전에는 `questionary`(+`prompt_toolkit`)를 벤더링했는데, `prompt_toolkit` 3.0.53 이 Python 3.10+ 문법을 써서 **macOS 기본 `python3`(3.9)에서 import 단계에 죽었다**. 그때 온보딩은 종료 코드 `2`로 빠졌고 호출부가 기본 설치로 이어졌다. 지금은 코드 `2`에서 아무것도 설치하지 않는다. 의존성이 없으므로 설치기와 같은 Python 버전에서 그대로 돈다. 온보딩을 띄우려고 `pip install`을 하지 않는다는 원칙도 그대로 지켜진다.

- 입력: POSIX는 `termios`, Windows는 `msvcrt.getwch`(stdin 과 무관하게 콘솔을 직접 읽는다).
- 출력: Windows는 `SetConsoleMode`로 VT 처리를 켠다. 켤 수 없으면 대화형을 포기하고 그 사실을 알린다.
- 기호: clack 과 같은 규칙으로 유니코드 지원을 판정해, 기본 conhost 에서는 ASCII(`| * o`)로 대체한다. `NO_COLOR`를 따른다.
- 폭: 한글은 2칸으로 센다(`unicodedata.east_asian_width`). 다시 그릴 때 올라갈 줄 수가 여기서 정해진다.

온보딩은 [`tests/test_onboard.py`](tests/test_onboard.py)가 **pty 위에서 실제 키 입력까지 재현해** 검증한다 — 일반 실행, 파이프 설치, `Ctrl+C` 취소, TTY 없는 환경, 기존 `AGENTS.md`가 있는 경우까지. 프롬프트가 "뜨는지"보다 **띄울 수 없을 때 아무것도 고르지 않는지**가 더 중요하므로 양쪽을 같은 비중으로 고정한다.

</details>

<details>
<summary><b>개발 · 테스트</b> — 저장소 구조와 테스트 실행</summary>

## 개발 · 테스트

### 저장소 구조

```
res/
  AGENTS.md, CLAUDE.md        # 프로젝트에 깔리는 작업 규칙
  docs/                     # AGENTS.md 가 가리키는 문서 틀 (설치하지 않으므로 필요하면 직접 복사한다)
  stages.py                 # 단계형 설치의 계획·실행·제거
  catalog.json              # 하네스·도구의 설치·갱신 명령 목록
  plugins/plugins.json      # 단계형 설치의 Claude Code 플러그인·마켓플레이스 목록
  onboard.py                # 대화형 온보딩 (인자 없이 실행할 때만 뜸)
  tui.py                    # 온보딩이 쓰는 clack 스타일 프롬프트 (표준 라이브러리만 사용)
  keybinds/apply.py         # 줄바꿈 키바인딩 병합 (VS Code·Cursor·Claude·Codex·Windows Terminal·tmux)
  skills/                   # 번들 스킬과 설치기
  omc/                      # OMC HUD 캐시 표시 래퍼
  output_style/apply.py     # outputStyle 지정 / 제거
  mods/                     # 번들 Claude Code mod 와 설치기
  tools/npm_release.py      # npm-release 배치 (버전별 디렉터리)
  tools/host.py             # 실행 환경 보조 함수 (PATH 위치, 프로세스 트리 종료)
  tools/json_files.py       # 설정 파일 백업·JSON 쓰기 (mods·omc·output_style 워커 공용)
  update/update_ai.py       # update-ai 구현
scripts/
  setup.{ps1,sh}            # 진입점 (옵션 해석, 온보딩, 단계형 설치 호출)
  setup_*.{ps1,sh}          # 개별 옵션 설치 / 제거 워커 (agentsmd, skills, keybinds, omc, output_style, mods)
  update-ai.sh, Update-Ai.ps1  # update-ai 실행기
  test.{ps1,sh}             # 테스트 러너 (pytest + bats + Pester 통합 실행)
  lib/                      # 공용 함수
install.{ps1,sh}            # 원격 설치 부트스트랩 (curl | sh / irm | iex)
docs/                       # 요구사항·설계 계약·수용 기준과 설계 기록
tests/                      # pytest + bats(bash) + Pester(PowerShell)
```

### 테스트

가드 훅·병합 엔진과 그 테스트는 jarvis로 옮겨 갔다.

러너가 세 개(pytest / bats / Pester)라 `scripts/test.sh`(POSIX)와 `scripts/test.ps1`(Windows)이 **설치된 러너를 찾아 전부 실행하고 통과·실패·건너뜀을 구분해 보고**한다.

```sh
bash scripts/test.sh                     # 있는 러너로 전부
bash scripts/test.sh --python-only       # pytest 만
bash scripts/test.sh --strict            # 러너 미설치로 건너뛴 것도 실패 취급 (CI용)
bash scripts/test.sh -k stages           # 남은 인자는 pytest 로 전달

CLAUDE_TEST_PYTHON=.venv/bin/python bash scripts/test.sh   # 인터프리터 직접 지정
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

첫 실패에서 멈추지 않고 가능한 스위트를 전부 돌린 뒤 마지막에 한 번에 보고한다. 종료 코드는
**실행된 스위트가 하나라도 실패하면 1, 하나도 실행하지 못했어도 1**이다 — 러너가 없어서 아무것도
검증되지 않은 상태를 "통과"로 읽으면 안 되기 때문이다. `--strict`는 그보다 더 엄격하게, 건너뛴
스위트가 하나라도 있으면 실패로 만든다. 러너는 `python3`/`python` 순으로 **pytest 가 실제로
import 되는** 인터프리터를 찾는데, venv 안이거나 pytest 가 그 이름으로 잡히지 않으면
`CLAUDE_TEST_PYTHON` 으로 못박을 수 있다 — 지정한 인터프리터로 pytest 를 import 하지 못하면
건너뛰지 않고 실패로 보고한다. 이 종료 코드 계약 자체를
[`tests/test_test_scripts.py`](tests/test_test_scripts.py)가 고정한다.

개별 러너를 직접 부를 수도 있다.

```sh
python -m pytest tests/ -rs              # 단계식 설치기 + 워커 + 셋업 스크립트
bats tests/setup.bats                    # 셋업 스크립트 (선택 — bats-core 필요)
```
```powershell
Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed   # 셋업 스크립트 (PowerShell)
```

`-rs`를 붙이면 **스킵된 테스트의 사유**까지 보인다(러너 스크립트는 항상 붙인다). 이 저장소의
스킵은 전부 환경 조건부다 — OS 전용 경로(POSIX·Windows)와, 러너·도구(`pwsh`, `node`, `bash`)가
있을 때만 도는 테스트.

`pytest`만으로도 셋업 스크립트의 실제 설치 경로(`--dry-run`이 아닌 쪽)까지 커버한다
([`tests/test_setup_scripts.py`](tests/test_setup_scripts.py)).

</details>

---

## 라이선스

[MIT](LICENSE)
