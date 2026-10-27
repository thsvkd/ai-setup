# ai-setup

Claude Code·Codex 같은 AI 코딩 에이전트의 작업 환경을 명령 한 줄로 설치한다. 중심은 **에이전트가 실수해도 되돌릴 수 있게 만드는 안전 장치**이고, 줄바꿈 키 통일과 플러그인·도구 설치를 함께 묶었다. Windows·macOS·Linux에서 동작한다.

작성자가 실제로 쓰는 구성을 공개한 것이라, 기본값은 **한국어로 Claude Code를 쓰는 사용자**에게 맞춰져 있다(한국어 응답, 한국어 출력 스타일 등). 설치하기 전에 [미리보기](#빠른-시작)로 바뀌는 내용을 확인하고, 필요 없는 단계는 끄고 설치하기를 권한다.

## 무엇을 해 주나

- 🗑️ **삭제는 휴지통으로**: Claude Code가 `rm`·`Remove-Item`으로 지운 파일을 휴지통에서 되살릴 수 있다.
- 💾 **git 작업 자동 백업**: Claude Code가 `git reset --hard`·`git clean` 같은 명령을 실행하기 전에, 커밋하지 않은 변경을 스냅샷으로 남긴다.
- ⛔ **되돌릴 수 없는 것만 차단**: 루트·홈 디렉터리 전체 삭제와 디스크 포맷만 막고, 그 밖의 작업은 막지 않는다.
- ⏎ **줄바꿈 키 통일**: Claude Code·Codex·Grok CLI에서 Shift+Enter(또는 Ctrl+Enter)를 줄바꿈 키로 맞춘다.
- 🧩 **에이전트·플러그인·도구 설치**: Claude Code와 Codex, Claude Code 플러그인, CodeGraph, Orca 등을 고른 만큼 설치한다.
- 📄 **AGENTS.md**: 현재 프로젝트에 에이전트가 따를 작업 규칙 템플릿 [`res/AGENTS.md`](res/AGENTS.md)를 복사한다. 작성자의 규칙을 한국어로 쓴 것으로, 변경 원칙, 승인이 필요한 작업, "식별자와 문자열은 영어로, 한국어는 주석에만" 같은 코드 규칙, `docs/PRD.md`·`docs/SPEC.md` 등을 가리키는 문서 구조가 들어 있다. 그 문서들은 함께 만들지 않으므로(틀은 [`res/docs/`](res/docs)에 있다) 필요하면 직접 복사하고, `<채워 넣기>` 칸과 함께 프로젝트에 맞게 고쳐 쓴다.

**한계**

- 위의 안전 장치(휴지통·git 백업·차단)는 **Claude Code에만** 적용된다. Codex·Grok 같은 다른 에이전트가 지운 파일은 복구되지 않는다.
- 휴지통 복구는 `rm`·`Remove-Item`을 거치는 삭제에만 적용된다. `sudo rm`, `find … -delete`, `python -c "shutil.rmtree(...)"` 같은 삭제와 메모리 위에 있는 경로(tmpfs로 마운트된 `/tmp` 등)의 삭제는 복구되지 않는다.
- 휴지통 도구(`trash-cli` 등)를 설치하지 못하면 `rm`은 경고만 남기고 실제로 지운다. 설치 출력에 휴지통 관련 `⚠️`(또는 `▲`) 경고가 없는지 확인하고, 경고가 있으면 그 경고에 적힌 명령(예: `sudo apt-get install trash-cli`)으로 직접 설치한다.
- `git push`는 force push를 포함해 훅이 판정하지 않는다. 공유 브랜치 보호는 Claude Code의 `auto` 권한 모드(계정에 따라 쓸 수 없을 수 있다)나 원격 저장소의 브랜치 보호에 맡긴다.
- 훅이 오류로 멈추면 Claude Code는 명령을 그대로 실행한다. 그래서 설치할 때 자체 테스트가 통과했는지 확인해야 한다.
- 설치하기 전부터 열려 있던 Claude Code 세션에는 적용되지 않으므로, 설치 후 Claude Code를 다시 시작해야 한다.

**되살리는 법**: 지운 파일은 OS의 휴지통(Linux는 `trash-list`·`trash-restore`)에서 되살린다. git 스냅샷은 `git for-each-ref refs/claude-backups/`로 찾는다(가장 최근 것이 맨 아래). 되돌리기 전에 `git diff <ref>`로 차이를 확인한다. `git checkout <ref> -- .`는 스냅샷 이후의 변경을 덮어쓰기 때문이다.

자세한 내용은 [가드 정책](#가드-정책)에 정리해 두었다.

## 설치 전에 알아 둘 것

> [!WARNING]
> **에이전트의 권한이 넓어진다.** 가드 훅 단계는 `~/.claude/settings.json`에 셸 실행(`Bash`·`PowerShell`), 파일 쓰기(`Write`·`Edit`), 웹 접근(`WebFetch`·`WebSearch`), 하위 에이전트 실행(`Agent`) 등을 묻지 않고 허용하는 규칙을 추가하고, 기본 권한 모드를 `auto`로 바꾼다. 온보딩에서는 `bypassPermissions`도 고를 수 있다. 이 설정은 **이 사용자가 여는 모든 프로젝트**에 적용된다. 가드는 루트·홈 전체 삭제와 디스크 파괴만 막으므로, 그 밖의 명령은 확인 없이 실행된다고 생각해야 한다.
>
> **사용량과 비용에 영향을 주는 기본값이 있다.** `model`·`effortLevel`·`language`가 비어 있으면 각각 `opus`·`xhigh`·`korean`으로 채운다(이미 값이 있으면 건드리지 않는다). claude_special 단계가 설치하는 mod `korean-reply-rewrite`는 한국어로 물었는데 영어로 답한 응답을 Haiku로 번역해 대화 기록에 저장하므로, 그만큼 호출이 늘고 기록에 남는 응답이 바뀐다.
>
> **sudo와 pip를 쓴다.** Linux에서 git이 없으면 패키지 관리자로 설치하고(sudo), 휴지통 도구 `trash-cli`는 pip로 설치하고(필요하면 `--break-system-packages`를 붙인다), 그래도 실패하면 터미널에서 실행한 경우에만 `sudo apt-get`으로 설치한다. Orca는 sudo로 deb 패키지를 설치하고, Tailscale은 공식 설치 스크립트로 설치하므로 Linux에서는 Tailscale 패키지 저장소도 추가된다.

인자 없이 실행하면 **단계형 설치**가 시작된다. 아래 11개 단계를 차례로 보여 주며, 모든 단계가 기본으로 켜져 있다. 이미 설치된 프로그램은 다시 설치하지 않는다. 새 장비에서 기본값 그대로 설치하면 다음이 설치된다.

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
| tools | 여러 에이전트를 데스크톱·모바일·원격에서 함께 다루는 도구 Orca와 Tailscale을 설치한다. Tailscale에 로그인되어 있으면 Orca 상시 실행 서버도 설정한다 | Linux에서는 **sudo**가 필요하다. Orca는 Linux에서 **Debian·Ubuntu만** 지원하므로 다른 배포판에서는 이 단계를 끈다. Orca 서버는 **6768 포트**를 연다 |
| hooks | 가드 훅을 설치하고 권한 규칙과 권한 모드를 설정한다. 비어 있는 `model`·`effortLevel`·`language`도 이 단계에서 채운다 | 위 경고를 참고한다 |
| agentsmd | 현재 폴더에 `AGENTS.md`(와 `CLAUDE.md`)를 만든다. 내용은 위 [AGENTS.md](#무엇을-해-주나) 설명을 참고한다 | 이미 있으면 온보딩에서 덮어쓸지 묻고, 기본은 그대로 둔다 |

- Orca 서버는 모든 네트워크 인터페이스의 6768 포트에서 연결을 받고, 페어링 토큰으로만 보호된다. 그래서 설치기는 Tailscale 주소를 찾을 수 있을 때만 서버를 설정한다. 자세한 내용은 [Orca](#orca)에 있다.
- Tailscale은 설치만 하며, 로그인(`tailscale up`)은 하지 않는다.
- Jarvis(작성자의 [홈 서버 모니터링 대시보드](https://github.com/thsvkd/jarvis))와 herdr은 직접 골랐을 때만 설치한다.
- 단계 하나가 실패하면 **거기서 멈추고** 뒤 단계는 실행하지 않는다. tools 단계는 hooks 단계보다 앞에 있으므로, 예를 들어 Orca 설치가 실패하면 가드 훅도 설치되지 않는다. 원인을 고치거나 실패한 단계를 끈 뒤, 남은 단계만 `--stages hooks,agentsmd`처럼 지정해 이어서 실행한다.
- 각 용어의 뜻은 [용어](#용어)에 정리해 두었다.

---

## 빠른 시작

**0. 준비**

| 환경 | 필요한 것 |
| --- | --- |
| 공통 | Python 3.9 이상(설치기와 훅이 Python으로 동작하므로 미리 설치해 둔다), 인터넷 연결(GitHub·npm 등에서 내려받는다). GitHub 로그인은 필요 없다 |
| macOS | `bash`·`curl`·`tar`(기본 포함), Homebrew(git·Tailscale 설치에 쓴다. 없으면 tools 단계가 실패하므로 그 단계를 끈다). 새 Mac에서는 `xcode-select --install`로 Command Line Tools를 먼저 설치해야 `python3`가 생긴다 |
| Linux | `bash`, `curl` 또는 `wget`, `tar`, `sudo`(git·`trash-cli`·Orca·Tailscale 설치에 쓴다) |
| Windows | PowerShell 5.1 이상, winget(Git·Node·Tailscale 설치에 쓴다). Python은 python.org 설치본을 쓴다(Microsoft Store의 `python.exe` 바로가기로는 실행되지 않는다) |

**1. 미리보기**: 아무것도 바꾸지 않고, 기본 설치가 실행할 작업 목록만 출력한다. 이 목록은 단계별 작업 이름만 보여 주므로, 권한 규칙처럼 `settings.json`에 실제로 들어갈 내용은 `--hooks --dry-run`으로 따로 확인한다. 이미 설치된 프로그램은 `present, not claimed`(이미 있으므로 설치하지 않고 설치 기록에도 넣지 않음)로 표시된다.

macOS / Linux:
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages all --dry-run
```
Windows(PowerShell):
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) --stages all --dry-run
```

**2. 설치**: `AGENTS.md`가 현재 폴더에 생기므로 프로젝트 루트로 이동한 뒤 실행한다. 새 터미널을 열자마자(홈 디렉터리에서) 실행하면 `~/AGENTS.md`·`~/CLAUDE.md`가 생기고, Claude Code가 홈 아래의 모든 프로젝트에서 이 파일을 읽는다. 원하지 않으면 온보딩에서 agentsmd 단계를 끈다.

하네스·플러그인·도구 없이 **가드 훅과 권한 규칙만** 설치하려면 단계를 `hooks` 하나로 지정한다. 이 단계는 [위 경고](#설치-전에-알아-둘-것)의 권한 확대(`auto` 모드와 넓은 허용 규칙)와, 비어 있는 `model`·`effortLevel`·`language`를 `opus`·`xhigh`·`korean`으로 채우는 일을 함께 적용한다. 공개된 옵션으로는 이것들을 나눌 수 없으므로, 원하지 않으면 설치 뒤 `~/.claude/settings.json`을 직접 고친다. 단, 나중에 `--hooks`로 업데이트하면 `auto` 모드와 허용 규칙이 다시 적용되므로 그때마다 다시 고쳐야 한다.
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages hooks
```
Windows(PowerShell):
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) --stages hooks
```

전체 단계를 고르며 설치하려면 인자 없이 실행한다.

macOS / Linux:
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh
```

Windows에서는 Git Bash가 아니라 PowerShell에서 실행한다. Git Bash로 설치하면 Windows 휴지통 연동이 빠진다.
```powershell
irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1 | iex
```

위 명령을 실행하면 온보딩 화면이 뜬다. 화면은 영어이며, 방향키로 고르고 Enter로 확정한다.

1. 첫 화면에서 **Walk**를 고르면 위 11개 단계를 하나씩 켤지 묻는다. **Skip**을 고르면 바로 허브로 간다.
2. **허브**는 단계별 선택을 한 화면에 모아 보여 주는 메뉴다. 여기서 선택을 고친 뒤 **Apply**로 설치하거나, **Preview**로 계획만 보거나, **Quit**으로 아무것도 하지 않고 끝낸다.
3. 이미 설치한 적이 있는 장비에서는 첫 화면 없이 허브부터 열린다.

**3. 마무리**: 설치가 끝나면 출력에 휴지통 관련 `⚠️`(또는 `▲`) 경고가 없고 `Self-test 5/5 passed`가 있는지 확인한 뒤, Claude Code를 다시 시작한다. 훅과 권한은 새 세션부터 적용된다. `--doctor`로 설치 상태를 다시 점검할 수 있다.

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
| 가드 훅 | `--hooks`. 권한 모드를 `auto`로, 허용 규칙을 기본값으로 다시 적용한다. 온보딩에서 `bypassPermissions`를 골랐거나 권한을 직접 고쳤다면 다시 바꿔야 한다. `--hooks`와 `--stages hooks`는 같은 설치 기록을 남기므로, 어느 쪽으로 설치했든 `--uninstall`과 `--stages hooks --uninstall` 둘 다 쓸 수 있다 |
| 줄바꿈 키 | `--keybinds` |
| 번들 스킬 | `--skills`. 사용자가 고친 스킬은 바꾸지 않는다 |
| mod | `--mods`. 사용자가 고친 mod 파일은 바꾸지 않는다 |
| 하네스·도구·플러그인 | 저장소를 clone한 뒤 [update-ai](#update-ai)를 실행한다 |

```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --hooks
```

---

## 제거

제거는 설치 기록(`~/.claude/.claude-code-setup.json`)에 남은 항목만 되돌리고, 원래 있던 설정은 그대로 둔다. 바뀌는 설정 파일은 `<파일>.bak.<타임스탬프>`로 백업된다. 설치한 방식(단계형 설치와 개별 옵션 설치의 차이는 [옵션](#옵션)에 있다)에 따라 명령이 다르다.

| 설치한 방식 | 제거 명령 |
| --- | --- |
| 단계형 설치(인자 없이 실행, `--stages`) | `--stages <단계 목록> --uninstall` |
| 개별 옵션 설치(`--hooks`, `--keybinds`, `--no-onboard` 등) | `--uninstall`. `--omc`·`--output-style`로 설치한 플러그인은 남긴다 |
| `--tools orca` | `--tools orca --uninstall`. 위의 `--uninstall`은 Orca를 건드리지 않는다 |

**1. 먼저 미리보기로 무엇이 빠지는지 확인한다.**
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages all --uninstall --dry-run
```

**2. 설정만 되돌린다.** 가드 훅·권한 규칙, 줄바꿈 키, 출력 스타일·mod를 되돌리고, 설치한 프로그램은 남긴다. 가드 훅만 빼려면 목록을 `hooks` 하나로 쓴다. 플러그인·MCP 등록·번들 스킬도 빼려면 목록에 `plugins,mcp,skills`를 더한다. 이렇게 제거해도 **Orca 서버는 계속 6768 포트에서 연결을 받는다**. 서버도 멈추려면 `tools`를 더한다(이때는 Orca·Tailscale 패키지도 지운다).
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages hooks,newline,claude_special --uninstall
```

> [!WARNING]
> `--stages all --uninstall`은 이 설치기가 **설치한 프로그램 자체를 지운다**. Claude Code·Codex 같은 하네스, Claude Code 플러그인과 마켓플레이스, CodeGraph와 MCP 등록, Orca·Tailscale 패키지(`sudo apt-get remove` 등)가 여기에 해당한다. 원격에서 Tailscale로 접속한 채 제거하면 그 연결이 끊긴다.

**3. 설치한 프로그램까지 모두 지운다.**
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --stages all --uninstall
```

PowerShell에서는 같은 인자를 scriptblock 형태로 넘긴다. 예: `& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) --stages all --uninstall --dry-run`

다음은 남는다.

- 설치하기 전부터 있던 프로그램과 설정, 그리고 nvm으로 설치한 Node
- 프로젝트의 `AGENTS.md`·`CLAUDE.md`(필요하면 직접 지운다)
- 설치가 새로 만든 키바인딩 파일 중 우리 항목만 빠진 빈 파일(`[]` 등). VS Code·Cursor가 없어도 그 `keybindings.json`을 만들기 때문에, 이 빈 파일이 남을 수 있다
- Orca의 프로필·페어링·워크스페이스 데이터

자세한 규칙은 [제거가 되돌리는 것](#제거가-되돌리는-것)에 있다.

---

## 옵션

설치 방식은 두 가지다.

- **단계형 설치**: 인자 없이 실행하거나 `--stages`를 준다. 위 11개 단계를 계획하고 설치 기록에 남긴다.
- **개별 옵션 설치**: `--hooks`, `--keybinds` 같은 옵션으로 원하는 부분만 설치한다. `--no-onboard`는 질문 없이 가드 훅·`AGENTS.md`·키바인딩·번들 스킬을 설치한다. 옵션을 하나라도 주면 질문 없이 바로 실행한다.

`--dry-run`만 주면 `--no-onboard`의 계획을 보여 준다. 단계형 설치의 계획은 `--stages all --dry-run`으로 본다.

| POSIX | PowerShell | 동작 |
| --- | --- | --- |
| `--stages <목록>` | `--stages <목록>` | 단계형 설치. `all` 또는 쉼표로 구분한 단계 이름(예: `hooks,newline`) |
| `--jarvis-role <역할>` | `--jarvis-role <역할>` | `--stages`와 함께 Jarvis를 `gateway` 또는 `core` 역할로 설치 |
| `--herdr` | `--herdr` | `--stages`와 함께 herdr 설치 |
| `--ss-caps` | `--ss-caps` | `--stages`와 함께, Jarvis용 `ss` 복사본에 `cap_sys_ptrace`·`cap_dac_read_search` 권한을 준다(sudo). 이 복사본은 모든 파일을 읽을 수 있으므로 필요할 때만 쓴다 |
| `--orca-desktop` | `--orca-desktop` | `--tools orca`나 `--stages`와 함께, 설치 뒤 페어링된 Orca 데스크톱 앱을 연다 |
| `--dry-run` | `-DryRun` | 아무것도 바꾸지 않고 변경 계획만 출력 |
| `--no-onboard` | `-NoOnboard` | 질문 없이 가드 훅·`AGENTS.md`·키바인딩·번들 스킬 설치 |
| `--hooks` | `-Hooks` | 가드 훅과 권한 규칙만 설치(`~/.claude`) |
| `--agentsmd` | `-AgentsMd` | 현재 폴더에 `AGENTS.md`만 설치 |
| `--harness <목록>` | `-Harness <목록>` | 대상 하네스: `claude`·`codex`·`grok`·`opencode`·`agy`·`gemini`·`copilot`. 개별 옵션 설치에서는 `AGENTS.md`를 읽게 할 하네스를 고르며, `all`(기본)은 `claude`·`codex`·`grok`·`opencode`를 뜻한다. 단계형 설치에서는 설치할 하네스를 고르며, 기본은 Claude Code와 Codex다 |
| `--skills` | `-Skills` | 번들 스킬만 설치(`~/.claude/skills`) |
| `--tools orca` | `-Tools orca` | Orca 패키지·번들 스킬 설치와 서버 설정만 실행 |
| `--keybinds` | `-Keybinds` | 줄바꿈 키바인딩만 설치 |
| `--newline <값>` | `-Newline <값>` | 줄바꿈 키: `shift-enter`(기본) 또는 `ctrl-enter` |
| `--omc` | `-Omc` | oh-my-claudecode 플러그인 설치와 HUD 캐시 표시 래퍼 |
| `--mods` | `-Mods` | Claude Code mod 3개 설치(Claude Code v2.1.290 이상) |
| `--output-style` | `-OutputStyle` | [fluent-korean](https://github.com/snflkd/fluent-korean) 플러그인 설치와 출력 스타일 지정 |
| `--uninstall` | `-Uninstall` | 설치한 것만 골라 되돌리기. 단계형 설치는 `--stages <목록>`과 함께 쓴다 |
| `--doctor` | `-Doctor` | 읽기 전용 점검: 설치된 하네스·도구와 버전, 중복 설치, 남아 있는 옛 훅, 설정 파일의 평문 시크릿 위치(키 이름만), 스킬 잠금 파일 밖의 스킬. 다른 옵션과 함께 쓸 수 없다 |
| `--help` | `-Help` | 도움말 |

옵션을 넘기는 방법은 다음과 같다. POSIX에서는 `sh -s --` 뒤에 붙인다.
```sh
curl -fsSL https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh -s -- --hooks --dry-run
```

PowerShell에서는 `| iex`로 인자를 넘길 수 없으므로 scriptblock으로 감싼다. PowerShell은 `-DryRun` 같은 PowerShell 형식과 `--dry-run` 같은 긴 형식을 모두 받으며, `--stages`처럼 PowerShell 형식이 없는 옵션은 긴 형식으로 쓴다.
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) -Hooks -DryRun
```

저장소를 clone했다면 `bash scripts/setup.sh --dry-run`이나 `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -DryRun`처럼 직접 실행해도 된다. Windows 기본 실행 정책은 내려받은 스크립트 파일을 막으므로 `-ExecutionPolicy Bypass`를 붙인다(원라이너는 이 처리를 스스로 한다).

---

## 무엇이 설치되나

| 위치 | 내용 |
| --- | --- |
| `~/.claude/settings.json` | 권한 규칙, 훅 등록, 비어 있을 때만 채우는 기본값(`model`·`effortLevel`·`language` 등) |
| `~/.claude/hooks/` | 가드 훅 `danger_guard.py`, 삭제를 휴지통으로 돌리는 shim(`shims/rm`, `shims/RmShim.psm1`), Windows 휴지통 헬퍼, graft 동기화 래퍼 |
| `~/.claude/.claude-code-setup.json` | 설치 기록. 제거할 때 이 기록에 남은 것만 되돌린다 |
| `./AGENTS.md`, `./CLAUDE.md` | 프로젝트 작업 규칙. `CLAUDE.md`는 `@AGENTS.md` 한 줄짜리 파일이며, 하네스에 `claude`가 있을 때만 만든다. 이미 있으면 건너뛴다 |
| `~/.claude/skills/design-lab/`, `~/.claude/skills/tailnet-report/` | 번들 스킬 |
| 줄바꿈 키 | `~/.claude/keybindings.json`, `~/.codex/config.toml`, VS Code·Cursor `keybindings.json`(에디터가 없어도 만든다), `~/.tmux.conf`(POSIX만), Windows Terminal(`ctrl-enter`일 때만) |
| OMC HUD 래퍼 | `~/.claude/hud/omc-hud-ttl.mjs`, `settings.json`의 `statusLine` 래퍼와 `refreshInterval` |
| mod | `~/.claude/mods/bash-diff-filter/`, `~/.claude/mods/cache-ttl-status/`, `~/.claude/mods/korean-reply-rewrite/`, `settings.json`의 `env.CLAUDE_CODE_PLUGIN_DIRS` |
| 출력 스타일 | `settings.json`의 `outputStyle` = `fluent-korean:fluent-korean`. 원래 값은 설치 기록에 남긴다 |

휴지통 도구는 macOS 14.4 이상의 기본 `/usr/bin/trash`, Linux의 `trash-cli`, Windows의 `send2trash`를 쓴다. 없으면 설치 중에 pip로 설치를 시도한다. 훅은 POSIX에서 `python3`, Windows에서 `python`으로 실행된다.

> `auto` 권한 모드는 계정과 Claude Code 버전이 자격 요건을 충족해야 켜진다. 설치 후 세션에서 `Shift+Tab`으로 모드를 바꿔 보며 확인할 수 있다.

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
| 가드 훅 | Claude Code가 명령을 실행하기 전에 부르는 `danger_guard.py`. 위험한 삭제를 막고 git 스냅샷을 남긴다 |
| shim | `rm`·`Remove-Item` 대신 먼저 실행되어, 삭제 대상을 휴지통으로 옮기는 작은 대리 프로그램 |
| OMC, HUD | [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 플러그인과, 그 플러그인이 Claude Code 화면 아래에 띄우는 상태 표시줄(`statusLine`) |
| mod | Claude Code의 화면과 동작을 바꾸는 확장. [공식 문서](https://code.claude.com/docs/en/plugins/mods/overview) |
| CodeGraph, MCP | 코드베이스를 미리 색인해 두는 로컬 지식 그래프 도구와, 그 색인을 에이전트가 쓰게 해 주는 MCP(Model Context Protocol) 서버 |
| Orca | 여러 코딩 에이전트를 데스크톱·모바일·원격 런타임에서 함께 다루는 도구. [stablyai/orca](https://github.com/stablyai/orca) |
| Tailscale, tailnet | 기기들을 사설 네트워크로 묶는 VPN과, 그렇게 묶인 내 네트워크 |
| Jarvis, herdr | 작성자의 홈 서버 모니터링 대시보드와, 코딩 에이전트를 실행하는 런타임 도구([herdr.dev](https://herdr.dev)). 직접 골랐을 때만 설치한다 |

---

## 상세

설치해서 쓰는 데는 여기까지면 충분하다. 아래는 동작 원리와 설계 이유다.

<details>
<summary><b>Orca</b> — 설치 방식, 서버, 네트워크 노출, 제거</summary>

## Orca

`bash scripts/setup.sh --tools orca --dry-run`으로 설치 계획을 확인하고, 실제 설치에는 `--dry-run`을 뺀다. Windows에서는 `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Tools orca -DryRun`을 사용한다. 기존 Orca 설치가 있으면 그대로 두고, 설치 기록에 새로 넣지 않는다.

새로 설치할 때는 Debian/Ubuntu의 공식 deb(`/opt/Orca`), macOS의 공식 `/Applications/Orca.app`, Windows의 공식 사용자 설치본(`%LOCALAPPDATA%\Programs\orca`)을 쓴다. Orca 공식 stable 릴리스 매니페스트(`latest*.yml`)에 적힌 크기와 SHA-512가 일치하는 패키지만 실행한다. Mac 앱은 서명과 Gatekeeper 검사를 거친 뒤 설치한다. Linux의 sudo 설치는 대화형 터미널에서만 실행한다. 번들 스킬은 기존 디렉터리·링크·잠금 파일 항목이 없는 것만 추가한다. 사용자 설정·프로젝트·페어링 데이터는 유지한다.

설치는 기존 Orca 프로필로 상시 실행 서버(Linux systemd 사용자 서비스, macOS LaunchAgent, Windows 예약 작업)를 띄우고, 별도 `orca-desktop` 프로필에 데스크톱 연결을 등록하며, 모바일 페어링 링크를 서비스 디렉터리의 `pairing-codes.txt`에 보관한다. 데스크톱 앱은 `--orca-desktop`을 줄 때만 연다. 이 옵션이 없으면 Windows 바로가기를 바꾸지 않으므로, 평소처럼 연 Orca 앱은 서버와 같은 기본 프로필을 쓴다.

> **네트워크 노출**: `orca serve`는 바인드 주소를 고를 수 없어 모든 인터페이스의 6768 포트에서 연결을 받고, 접속은 페어링 링크의 토큰으로만 보호된다. 그래서 설치기는 Tailscale IPv4 주소를 페어링 주소로 쓸 수 있을 때만 서버를 설정한다. 주소를 찾지 못하면 다른 IP로 대신하지 않고, 서버 설정만 경고와 함께 건너뛴다(나머지 설치는 계속된다). `tailscale up` 뒤 `--tools orca`로 다시 실행하면 서버를 설정한다. 공인 IP가 붙은 서버라면 방화벽으로 6768 포트를 막아 두고, `pairing-codes.txt`는 비밀번호처럼 다룬다.

`--tools orca --uninstall`은 이 설치기가 기록한 패키지·서버 서비스와 새로 추가한 스킬만 제거한다. 실행 중인 ai-setup 서버 서비스는 먼저 멈춘다. ai-setup이 띄우지 않은 서버가 같은 프로필로 돌고 있으면 끊지 않고 제거를 멈춘다. 변경된 스킬은 보존한다. Mac에서는 앱 자체 업데이터를 쓰며, Homebrew cask를 추가로 설치하지 않는다.

공식 자료: [릴리스](https://github.com/stablyai/orca/releases/latest), [번들 스킬 설치](https://www.onorca.dev/docs/cli/reference).

</details>

<details>
<summary><b>update-ai</b> — 설치된 하네스·도구를 한 번에 최신으로</summary>

## update-ai

저장소를 clone해 두면, 설치된 하네스(claude, codex, grok, opencode, gemini, agy, copilot)와 도구(Orca, herdr, CodeGraph), 그 플러그인을 한 번에 최신으로 올릴 수 있다. 설치되지 않은 것은 건너뛰고 새로 설치하지 않으며, npm·winget·brew·deb 중 실제로 설치한 방식으로 올린다. npm 외의 공식 설치 방식이 없는 gemini·CodeGraph(와 Windows의 opencode·copilot)는 버전마다 디렉터리를 따로 두는 npm-release 배치(`res/tools/npm_release.py`)로 깔고 올린다. CodeGraph의 `codegraph upgrade`는 호출하지 않는다.

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

실행 중인 세션이 있어도 올린다. 새 버전은 다른 디렉터리에 깔리고 진입점만 바뀌므로, 이미 떠 있는 세션은 재시작할 때까지 이전 버전으로 계속 돈다. 파일을 제자리에서 바꾸는 예전 설치(npm -g, winget, Orca deb), 데스크톱 앱을 닫는 Windows Orca 설치기, codex 데몬 교체만 세션이 돌면 보류로 남기며, 세션을 끊어도 되면 `--allow-interrupt`(PowerShell `-AllowInterrupt`)를 준다. 하나가 실패해도 나머지를 계속하고, 마지막에 종료 코드 1로 끝난다.

</details>

<details>
<summary><b>가드 정책</b> — 왜 막지 않고 복구하는가, 무엇을 차단하는가</summary>

## 가드 정책

### 설계 원칙 — 차단이 아니라 복구

이 훅의 가치는 위험한 명령을 막는 데 있지 않다. 실사용 로그 `~/.claude/hooks/guard.log` 10,329건을 전수 분석한 결과가 근거다.

| 판정 | 발동 | 진짜 위험한 명령 | 오탐·무의미 |
| --- | ---: | ---: | --- |
| `deny-fork-bomb` | 8 | **0** | 8 — 평범한 셸 함수 정의 `f(){ … \| grep … && … }` |
| `deny-pipe-to-shell` | 14 | **0** | 8 테스트 픽스처, 5 히어독 본문 오탐, 1 의도한 설치 스크립트 차단 |
| `deny-root-delete` | 13 | **0** | 13 전부 테스트 픽스처 |
| `deny-unexpandable-target` | 4 | **0** | 4 전부 글로브 미일치(`rm -f *.png`) |
| `ask-chained-delete` | 9 | **0** | 9 전부 임시 파일 정리 |
| `ask-find-delete` | 5 | **0** | 5 전부 `__pycache__` 정리 |
| **휴지통 치환** | **311** | — | 실제로 작동한 복구 기능 |
| **git 백업** | **22** | — | 실제로 작동한 복구 기능 |

deny/ask 53건 중 진짜 위험한 명령은 **0건**이었다. 반대로 복구 기능은 333건 작동했다. 게다가 오탐의 상당수는 훅이 **명령 문자열을 재작성하다** 생겼다 — 훅은 셸이 아니라서 `$VAR`·글로브·따옴표 확장을 흉내 낼 수 없는데도 인자를 다시 따옴표로 감싸 넘겼고(`rm -rf "$FOO/bar"` → `trash-put '$FOO/bar'`), 확장이 막혀 명령이 실패했다.

그래서 현재 설계는 셋뿐이다.

1. **명령 문자열을 재작성하지 않는다.** 삭제를 휴지통으로 돌리는 일은 shim이 한다. Bash 는 세션 시작 때 `PATH` 에 shim을 한 번 끼워 두고 명령은 건드리지 않는다. PowerShell 만 모듈을 불러오는 **선행 한 줄**을 붙인다. 인자 해석은 전적으로 셸/PowerShell 몫이다.
2. **git 백업도 명령을 건드리지 않는다.** 훅 프로세스가 직접 스냅샷 커밋을 만들고 원본 명령은 그대로 흘려보낸다.
3. **deny 는 되돌릴 수단이 아예 없는 두 부류뿐이다.** 루트/홈 전체 삭제와 디스크 파괴. 파싱하지 않고 명령 문자열의 꼴만 본다.

### 삭제 → 휴지통: PATH·모듈 shim

| 툴 | 방식 |
| --- | --- |
| Bash (POSIX 셸·Git Bash) | `SessionStart` 훅이 `CLAUDE_ENV_FILE` 에 `PATH` 맨 앞으로 `~/.claude/hooks/shims` 를 넣는 줄을 적는다. Claude Code 가 매 Bash 명령 전에 이 파일을 source 하므로 명령 문자열도 권한 판정도 건드리지 않는다. `shims/rm` 이 셸의 확장이 **끝난 뒤의 argv** 를 받는다 |
| PowerShell | `CLAUDE_ENV_FILE` 은 Bash 전용이라, `shims/RmShim.psm1` 을 `Import-Module` 하는 한 줄을 `updatedInput` 으로 붙인다(권한 판정 없이 — `allow` 를 붙이면 권한 프롬프트와 auto mode 분류기를 건너뛴다). 명령 우선순위가 별칭 > 함수 > cmdlet 이라 같은 이름의 함수가 `Remove-Item` cmdlet 을 가리고, `rm`/`del`/`erase`/`ri`/`rd`/`rmdir` 별칭이 전부 그 함수로 해석된다 |

셸이 이미 확장을 끝낸 뒤에 받으므로 **원본 명령과 해석이 어긋날 수 없다.** 종전에 확인을 요구하거나 차단하던 것들이 그냥 동작한다.

| 종전 | 지금 |
| --- | --- |
| `rm -rf "$FOO/bar"` → 확장이 깨져 실패 | ✅ 그대로 동작, 휴지통으로 |
| `rm -f *.nomatch` → 매칭 0개라 차단 | ✅ `rm -f` 의미 그대로 성공 |
| `find … -exec rm -rf {} +` → 확인 | ✅ shim을 타므로 휴지통으로 |
| `find … \| xargs rm -f` → 확인 | ✅ 같음 |
| 여러 줄·체이닝에 `rm` 이 섞임 → 확인 | ✅ 파싱하지 않으므로 무관 |
| 스크립트 내부의 `rm` → 훅이 못 봄 | ✅ `PATH` 로 해석되므로 커버 |
| 히어독 본문의 `rm -rf /` → 오탐 | ✅ 데이터로 남음 |

shim이 **원본 `rm` 에게 그대로 넘기는** 경우 — shim이 흉내 내면 의미가 달라지는 것들이다.

- `-i`/`-I` — 치환하면 프롬프트가 사라진다
- `.`/`..` 로 끝나는 대상 — `rm` 이 거부하는 형태다. 치환이 원본보다 더 지우면 안 된다
- 대상이 **전부** `/tmp` 등 tmpfs 아래 — 휴지통 자리도 같은 램이라 옮겨봐야 회수되지 않는다 (실측: 1.4GB 가 이렇게 묶여 스왑을 소진시킨 적이 있다). 하나라도 tmpfs 밖이면 전부 휴지통으로 간다
- 휴지통 도구 부재 — 경고를 남기고 실제 삭제한다. `rm` 자체를 못 쓰게 만드는 쪽이 더 해롭다는 판단이다
- `CLAUDE_NO_TRASH` 가 설정됨 — 명시적 탈출구

루트/홈 전체 삭제는 shim도 argv 수준에서 한 번 더 거부한다. `bash -c "rm -rf /"` 처럼 훅의 텍스트 규칙을 비껴가는 형태를 여기서 잡는다. 이때 홈은 환경 변수 `$HOME` 이 아니라 사용자 DB 의 홈이다 — 테스트가 `HOME` 을 임시 디렉터리로 바꿔 두고 `rm -rf "$HOME"` 으로 정리하는 것까지 막으면 안 된다.

**Bash 에 선행 줄을 붙이지 않는 이유**: 명령 앞에 줄을 붙이면 Claude Code 는 **바뀐 명령**에 대해 권한 규칙을 평가한다. 그래서 `Bash(rm *)` 같은 사용자 허용 규칙이 더 이상 맞지 않고, 그렇다고 `allow` 를 붙이면 `rm` 이라는 낱말만 섞여도 어떤 명령이든 자동 승인된다(둘 다 Claude Code 2.1.283 에서 실측).

**한계**: 세션 도중에 설치하면 다음 세션부터 shim이 적용된다(`SessionStart` 가 다시 불려야 한다). `sudo rm` 은 sudo 의 `secure_path` 가 `PATH` 를 버려 shim을 타지 않는다(실사용 10,329건 중 2건). `find … -delete` 처럼 `rm` 을 거치지 않는 삭제도 커버 밖이다.

### git — 미커밋 변경만 스냅샷

Claude Code 의 체크포인팅(`/rewind`)은 [공식 문서상](https://code.claude.com/docs/en/checkpointing) **"bash 명령이 바꾼 파일을 추적하지 않는다."** `git reset --hard` 로 날아간 작업은 `/rewind` 로 못 되돌린다. 그래서 이 부분은 훅이 계속 맡는다.

훅 프로세스가 임시 `GIT_INDEX_FILE` 에 `git add -A` → `git write-tree` → `git commit-tree` 로 스냅샷 커밋을 만들고 `refs/claude-backups/<timestamp>` 에 고정한 뒤, **원본 명령은 한 글자도 바꾸지 않고** 통과시킨다. `git stash create` 는 추적 안 된 파일을 담지 못해서(실측 확인) 스크래치 인덱스를 쓴다.

| 대상 | 근거 |
| --- | --- |
| `reset --hard`, `checkout`/`restore` (워킹트리), `clean -f*`, `worktree remove`, `checkout`/`switch --force` | 미커밋 변경은 git 어디에도 남지 않는다 |
| ~~`rebase`, `branch -D`, `commit --amend`, `filter-branch`, `gc --prune`, `tag -d`~~ | **제외** — reflog·`ORIG_HEAD` 가 이미 되돌려 준다 |
| ~~`stash drop`/`clear`~~ | **제외** — gc 유예기간 안에서 `git fsck --unreachable` 로 살릴 수 있다 |

- `clean -x`/`-X` 는 `.gitignore` 대상(`.env`, 로컬 설정)까지 지우므로 이 경우에만 `git add -Af` 로 무시된 파일까지 담는다. 단 **10,000개 또는 100MB 를 넘으면 무시된 파일은 포기**하고 추적/미추적만 담는다 — 실측(라즈베리파이 5)에서 한 저장소의 `.gitignore` 대상이 52,722개 1,244MB 였고, 이 기기의 해싱 처리량(100MB/2,000파일당 4.4초)으로는 훅이 1~2분을 잡아먹고 SD 카드에 1.2GB 를 쓴다. 규모 측정 자체는 169ms 로 싸다.
- 워킹트리가 `HEAD` 와 같거나 직전 스냅샷과 트리가 같으면 ref 를 만들지 않는다. `refs/claude-backups/` 는 14일이 지나면 정리된다.
- `cd <경로> && git reset --hard` 는 그 경로에서 백업한다. `cd "$VAR"` 처럼 대상을 특정할 수 없으면 엉뚱한 저장소를 백업하느니 아무것도 하지 않는다.
- `git worktree remove <경로>` 의 대상은 cwd 가 아니라 인자다 — 사라질 워크트리 쪽에서 스냅샷을 뜬다.

오탐의 대가가 **쓸데없는 백업 ref 한 개**뿐이라 패턴을 느슨하게 잡아도 안전하다. 이것이 문자열 재작성 방식과의 결정적인 차이다.

- **조회**: `git for-each-ref refs/claude-backups/`
- **복구**: `git checkout <ref> -- .`

### 차단·확인 목록

| 명령 | 조치 |
| --- | --- |
| `rm -rf /`, `/*`, `~`, `$HOME` (따옴표 유무 무관, `sudo`/`timeout` 접두어 포함) | ⛔ **차단** |
| `Remove-Item`/`del`/`rd` + 드라이브 루트(`C:\`)·`$env:USERPROFILE`·`$HOME` | ⛔ **차단** |
| `mkfs*`/`newfs_*`/`fdisk`/`gdisk`/`sgdisk`/`parted`/`wipefs`, `dd of=/dev/*`, `diskutil erase*`, `/dev/sd*` 리다이렉트 | ⛔ **차단** |
| `format <드라이브>:`, `diskpart`, `Clear-Disk`/`Initialize-Disk`/`Remove-Partition`/`Clear-Volume` | ⛔ **차단** |
| `git push` — force push·원격 브랜치 삭제·`--mirror` 포함 | ✅ **판정하지 않음** — auto mode 분류기의 `Git Destructive` 규칙이 공유 브랜치(`main`, 기본 브랜치, `release/*` 등)의 맨 force push 와 원격 브랜치·태그 삭제를 막는다. 자기 커밋만 있는 개인 브랜치의 force push 는 허용하고, `--force-with-lease` 는 파괴로 간주하지 않되 남의 작업을 지우는 것이 분명하면 막는다. 사용자가 대상을 명시하면 풀리는 soft-deny 다. 원격 히스토리를 확실히 지키려면 원격의 브랜치 보호(GitHub rulesets 의 force push·삭제 차단)를 쓴다 |
| 그 외 전부 | ✅ 통과 (판단 안 함) |

차단 규칙은 **명령 자리**에서 시작할 때만 잡는다. `grep -rn "rm -rf /" docs/` 처럼 위험한 문자열을 데이터로 다루는 명령은 막지 않는다 — 종전 오탐이 대부분 이 부류였다.

**종전에 있었으나 실측 근거로 제거한 것**: 포크밤 패턴, `curl … | bash` 패턴, `find`/`xargs` 대량 삭제 확인, 체이닝 삭제 확인, 글로브 미일치 차단, `.`/`..` 차단, 대상 100개 초과 확인, `chmod 777` 확인, `shred` 확인, `shutdown`/`reboot` 확인, 훅 내부 오류 확인, 그리고 시크릿 파일 접근 확인(`secrets_guard`) — 파괴가 아니라 유출 위험이고, 그쪽은 auto mode 분류기가 맡는다. 기존 설치본에 남아 있으면 설치 중에 훅 파일과 `settings.json` 등록을 함께 걷어낸다.

**이 목록은 완전하지 않고, 완전할 수도 없다.** 셸은 임의의 프로그램을 실행할 수 있어서 `python3 -c "shutil.rmtree('.')"` 같은 경로를 명령 문자열만 보고 판정하는 건 불가능하다. 그래서 이 훅은 차단을 목표로 하지 않는다 — 되돌릴 수 있게 만드는 것이 목표다. 배경은 [docs/2026-07-31-delete-guard-architecture.md](docs/2026-07-31-delete-guard-architecture.md) 참고.

### push 를 훅이 판정하지 않는 이유

예전 버전은 명령 문자열을 읽어 "이 push 가 로컬에 없는 원격 커밋을 지우는가"를 가리고, 되돌릴 수 있는 force push 는 원격 커밋을 `refs/claude-backups/` 에 고정한 뒤 통과시켰다. 그 판정을 두 차례 다시 만들었지만 두 번 다 적대적 리뷰에서 무너졌다(2026-10-11). 셸은 임의의 코드를 실행할 수 있어서, 같은 명령 줄의 앞선 `git checkout`·`git config`, 셸 확장, `bash -c`·heredoc, git·셸 별칭 같은 형태가 판정을 비껴가 원격 커밋을 조용히 지웠다. 실행 전에 문자열만 보는 판정기는 이 계층에서 완성될 수 없다.

그래서 push 는 auto mode 분류기에 맡긴다. 기본 규칙 `Git Destructive` 가 의미 수준에서 공유 브랜치 force push 와 원격 브랜치 삭제를 막는다(`claude auto-mode defaults` 로 규칙 원문을 확인할 수 있다). 다른 권한 모드에서는 push 를 확인하는 것이 없으므로, 중요한 저장소는 원격의 브랜치 보호로 지킨다. 훅이 남기는 것은 되돌리는 수단(휴지통, git 스냅샷)과 되돌릴 수 없는 두 부류의 차단뿐이다.

**업그레이드 시 자동 마이그레이션**: 예전 버전은 `Bash(git push *)`·`Bash(git push --force*)`·`Bash(git push -f*)`·`Bash(git reset --hard *)`(및 PowerShell 짝)을 `deny`로, `Bash(git push *)`(및 PowerShell 짝)을 `ask`로 배포했다. 병합 엔진은 원래 '추가만' 하므로 그 규칙들이 기존 설치본에 그대로 남고, deny/ask가 훅보다 우선하니 **새로 설치한 사람에게는 동작하고 업그레이드한 사람에게는 조용히 죽는** 상태가 된다. 그래서 설치 중에 설치 기록이 *이 설치가 넣었다*고 적은 규칙만 제거하고, 무엇을 지웠는지 설치 리포트에 출력한다. 같은 문자열이라도 설치 기록에 없으면 사용자가 직접 넣은 규칙일 수 있으므로 지우지 않는다(설치 기록이 없던 2026-07-04 이전 설치본이 여기에 해당한다). 그중 스냅샷 백업을 막는 `reset --hard` deny 규칙만 경고를 출력한다 — push 규칙은 이제 훅과 충돌하지 않는다. 예전 버전이 `autoMode.allow` 에 넣은 'danger_guard 가 확인한 push 는 허용' 예외도 같은 방식으로 걷어낸다 — 훅이 push 를 판정하지 않게 된 지금 그 예외는 거짓 전제로 `Git Destructive` 규칙을 약하게 만든다. 예전 설치기가 설치 기록 근거 없이 지운 규칙은 설치 기록의 `removed_legacy` 에 남아 있어 `--uninstall` 시 복원된다.

**훅이 죽어도 잃는 것은 복구 수단이지 실행 권한이 아니다.** 훅이 예외로 죽으면 Claude Code는 판정 없이 명령을 실행한다(fail-open). 종전에는 이때 확인으로 승격했지만 실측상 그 확인은 전부 마찰이기만 했으므로, 이제 내부 오류는 `guard.log`에 `guard-error`로 남기고 조용히 통과시킨다. 설치 후 셀프테스트가 통과했는지 확인하는 것이 그만큼 더 중요하다.

</details>

<details>
<summary><b>settings.json에 병합되는 것</b></summary>

### settings.json 병합

`permissions.defaultMode: "auto"`, 핵심 툴 `allow`(`Bash`, `PowerShell`, `Read(*)`, `Edit(*)`, `Write(*)`, `Agent(*)`, `WebFetch(*)` 등), `ask`(위험 스킬만 — git 관련 규칙은 없음), `hooks.SessionStart`·`hooks.PreToolUse` 등록, 그리고 없을 때만 채우는 `model: "opus"` / `effortLevel: "xhigh"` / `language: "korean"` 과 `env.CLAUDE_CODE_SCROLL_SPEED: "3"`(마우스 휠 스크롤 속도, `/scroll-speed` 대응)이 병합된다. Windows에서는 `env.GRAFT_TEST_SYNC_RUN`도 없을 때만 채운다 — [graft](https://github.com/NanoNets/context-graph-engine)의 Stop 훅이 턴 종료 때 돌리는 `graft build`가 빈 콘솔 창을 띄우지 않도록, 원래 동기화 스크립트를 숨김 콘솔로 다시 실행하는 `~/.claude/hooks/graft_sync_hidden.cjs`를 가리킨다(graft가 없으면 쓰이지 않는다). git 관련 deny/ask를 `permissions`에 두지 않는 이유는 [push 를 훅이 판정하지 않는 이유](#push-를-훅이-판정하지-않는-이유)에 있다.

`permissions.defaultMode`는 설치할 때마다 고른 모드(기본 `auto`)로 바꾸고, 설치 전 값은 설치 기록에 남겨 제거할 때 되돌린다. `allow`·`ask`는 합집합으로 병합하므로, 사용자가 지운 규칙도 다시 설치하면 다시 들어간다. 그 밖에 사용자가 이미 고른 값(`model` 등)과 최상위 키(`statusLine` 등), 기존 `env` 키·값은 건드리지 않는다(이 설치기가 관리하는 `env` 키만 없을 때 추가한다). 단일 소스는 [`res/settings.json`](res/settings.json)이며, 설치 시 python 실행 명령과 훅 경로만 치환된다.

</details>

<details>
<summary><b>AGENTS.md와 하네스 선택</b></summary>

### AGENTS.md와 `--harness`

`--harness`는 **무엇을 쓸지**가 아니라 **무엇을 읽는지**로 갈린다. Codex·Grok·OpenCode는 루트 `AGENTS.md`를 직접 읽으므로 그 파일 하나면 되고, Claude Code는 `AGENTS.md`를 읽지 않고 `CLAUDE.md`를 읽으므로 `@AGENTS.md` 한 줄짜리 `CLAUDE.md`가 추가로 필요하다(Windows에서 심볼릭 링크는 관리자 권한을 요구해서 import를 쓴다). 그래서 `AGENTS.md`는 항상 설치되고, `CLAUDE.md`는 선택에 `claude`가 있을 때만 생긴다. 여러 하네스를 함께 쓰는 프로젝트가 흔하므로 다중 선택이 기본이며 — `--harness claude,codex` — 온보딩에서도 체크박스로 고른다. 모르는 이름을 주면 아무것도 쓰지 않고 종료 코드 1로 끝난다.

기존 `AGENTS.md`가 있으면 건너뛴다. 워커 `setup_agentsmd`의 `--force`는 기존 파일을 `.bak.<타임스탬프>`로 백업한 뒤 덮어쓴다. 마찬가지로 `setup_hooks`의 `--default-mode <모드>`(`auto`/`bypassPermissions`/`default`/`acceptEdits`/`plan`)도 직접 쓸 수 있다 — 둘 다 온보딩이 내부적으로 쓰는 옵션이다.

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

`--uninstall`은 설치 기록(`~/.claude/.claude-code-setup.json`)을 근거로 우리가 추가한 훅·allow/deny 항목·`model`/`effortLevel`/`language`만 제거하고, `defaultMode`를 이전 값으로 원복하며, 설치가 제거했던 구버전 규칙이 있다면 다시 넣어 준다. 사용자가 원래 갖고 있던 설정과 그 외 키는 그대로 보존되며 변경 전 `settings.json.bak.<타임스탬프>`를 남긴다. `settings.json`을 설치가 새로 만든 경우, 되돌린 뒤 비면 파일도 제거한다. 줄바꿈 키바인딩도 함께 되돌리는데, **무엇을 '우리 것'으로 볼지는 대상마다 다르다.**

- **시그니처로 식별**(VS Code·Cursor): 명령 + `when` + 시퀀스가 우리가 쓰는 것과 정확히 같은 항목만 제거한다. 이 조합은 이 설치가 만들어내는 형태라, 누가 먼저 넣었든 같은 항목이다 — 예컨대 Claude `/terminal-setup`이 넣어둔 `shift+enter` → `sendSequence` 항목도 제거 대상이다. 시퀀스가 다른 사용자 항목(에디터·노트북의 Shift+Enter)은 그대로 둔다.
- **설치 기록으로 식별**(tmux·Claude·Codex·Windows Terminal): `extended-keys` 줄, Claude의 `chat:newline`, Codex의 `shift-enter`는 전부 사용자가 직접 쓰는 값과 글자까지 같다. 값이 같다는 이유로 지우면 남의 설정을 지우는 것이므로, 설치 기록에 '설치가 넣었다'고 적힌 항목만 되돌린다. 기록이 없으면 건드리지 않는다. 설치가 기존 값을 덮어썼다면 그 값도 기록해 두었다가 되돌린다.

Codex의 기존 `ctrl-j` 처럼 우리가 넣지 않은 키는 남는다. 우리 키만 빠져 `insert_newline`이 비면 그 줄과 빈 `[tui.keymap.editor]` 테이블까지 지운다 — 빈 배열을 남기면 설치 전에 없던 '줄바꿈 전면 언바인드'라는 새 설정을 만드는 셈이기 때문이다. `--keybinds --uninstall`이면 키바인딩만 제거하고 훅은 건드리지 않는다.

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

예전에는 `questionary`(+`prompt_toolkit`)를 벤더링했는데, `prompt_toolkit` 3.0.53 이 Python 3.10+ 문법을 써서 **macOS 기본 `python3`(3.9)에서 import 단계에 죽었다**. 그때 온보딩은 종료 코드 `2`로 빠졌고 호출부가 기본 설치로 이어졌다. 지금은 코드 `2`에서 아무것도 설치하지 않는다. 의존성이 없으므로 훅과 같은 Python 버전에서 그대로 돈다. 온보딩을 띄우려고 `pip install`을 하지 않는다는 원칙도 그대로 지켜진다.

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
  settings.json             # settings.json 에 병합되는 조각 ({{PY}}·{{HOOKS_DIR}} 자리표시자)
  stages.py                 # 단계형 설치의 계획·실행·제거
  catalog.json              # 하네스·도구의 설치·갱신 명령 목록
  plugins/plugins.json      # 단계형 설치의 Claude Code 플러그인·마켓플레이스 목록
  onboard.py                # 대화형 온보딩 (인자 없이 실행할 때만 뜸)
  tui.py                    # 온보딩이 쓰는 clack 스타일 프롬프트 (표준 라이브러리만 사용)
  hooks/
    danger_guard.py         # 위험 명령 가드 (Bash + PowerShell, 전 플랫폼 공용)
    shims/rm                # 삭제 → 휴지통 (POSIX 셸·Git Bash)
    shims/RmShim.psm1       # 삭제 → 휴지통 (PowerShell)
    send_to_trash.py        # Windows 휴지통 헬퍼
    graft_sync_hidden.cjs   # Windows: graft 턴 종료 동기화를 숨김 콘솔로 실행
    merge_and_diff.py       # 자리표시자 치환 + settings.json 병합 엔진
  keybinds/apply.py         # 줄바꿈 키바인딩 병합 (VS Code·Cursor·Claude·Codex·Windows Terminal·tmux)
  skills/                   # 번들 스킬과 설치기
  omc/                      # OMC HUD 캐시 표시 래퍼
  output_style/apply.py     # outputStyle 지정 / 제거
  mods/                     # 번들 Claude Code mod 와 설치기
  tools/                    # Orca 설치·서버 설정
  update/update_ai.py       # update-ai 구현
  doctor/doctor.py          # --doctor 읽기 전용 점검
scripts/
  setup.{ps1,sh}            # 진입점 (옵션 해석, 온보딩, 단계형 설치 호출)
  setup_*.{ps1,sh}          # 개별 옵션 설치 / 제거 워커 (hooks, agentsmd, skills, keybinds, omc, output_style, mods)
  update-ai.sh, Update-Ai.ps1  # update-ai 실행기
  test.{ps1,sh}             # 테스트 러너 (pytest + bats + Pester 통합 실행)
  lib/                      # 공용 함수
install.{ps1,sh}            # 원격 설치 부트스트랩 (curl | sh / irm | iex)
docs/                       # 요구사항·설계 계약·수용 기준과 설계 기록
tests/                      # pytest + bats(bash) + Pester(PowerShell)
```

### 테스트

가드 훅과 병합 엔진은 블랙박스로 테스트한다 (JSON을 stdin으로 넣고 판정을 검증). git 백업은 판정뿐 아니라 **실제 git 저장소에서** 스냅샷이 작업을 보존·복구하는지까지 확인한다 ([`tests/test_git_snapshot.py`](tests/test_git_snapshot.py)).

러너가 세 개(pytest / bats / Pester)라 `scripts/test.sh`(POSIX)와 `scripts/test.ps1`(Windows)이 **설치된 러너를 찾아 전부 실행하고 통과·실패·건너뜀을 구분해 보고**한다.

```sh
bash scripts/test.sh                     # 있는 러너로 전부
bash scripts/test.sh --python-only       # pytest 만
bash scripts/test.sh --strict            # 러너 미설치로 건너뛴 것도 실패 취급 (CI용)
bash scripts/test.sh -k git_snapshot     # 남은 인자는 pytest 로 전달

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
python -m pytest tests/ -rs              # 훅 정책 + git 스냅샷 + 병합 엔진 + 셋업 스크립트
bats tests/setup.bats                    # 셋업 스크립트 (선택 — bats-core 필요)
```
```powershell
Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed   # 셋업 스크립트 (PowerShell)
```

`-rs`를 붙이면 **스킵된 테스트의 사유**까지 보인다(러너 스크립트는 항상 붙인다). 이 저장소의
스킵은 전부 환경 조건부다 — macOS 전용 경로(`/usr/bin/trash` 폴백)와, 3.9.x python3가 PATH에
있을 때만 도는 구버전 인터프리터 실행 테스트. 후자는 OS가 아니라 **인터프리터 유무** 조건이라
Linux에 python3.9를 설치하면 그쪽에서도 돈다.

`pytest`만으로도 셋업 스크립트의 실제 설치 경로(`--dry-run`이 아닌 쪽)까지 커버한다
([`tests/test_setup_scripts.py`](tests/test_setup_scripts.py)). [`tests/test_hook_compat.py`](tests/test_hook_compat.py)는
훅이 구버전 python3(macOS 3.9.x)에서도 죽지 않는지 확인한다 — 훅이 예외로 죽으면 Claude Code는
가드 없이 명령을 실행하므로(fail-open), 최신 인터프리터로만 테스트하면 위험하다.

</details>

---

## 라이선스

[MIT](LICENSE)
