# claude-code-setup

Claude Code를 **더 안전하게** 쓰기 위한 사용자 레벨(user-level) 설정 번들.
위험한 명령을 자동으로 막거나 휴지통 이동으로 치환하는 **가드 훅**, 합리적인 **권한(permissions)**,
프로젝트용 **AGENTS.md**, 그리고 OS·터미널·에이전트마다 제각각인 **줄바꿈 키**를 Windows / macOS / Linux에 한 번에 설치한다.

- 🛡️ **가드 훅** — 삭제를 휴지통으로 돌리는 셰임을 `PATH`/모듈로 끼워 넣고(명령 문자열은 건드리지 않는다), `git reset --hard`·`clean` 등 미커밋 변경을 날리는 명령 앞에 `refs/claude-backups/`로 스냅샷을 뜬다. 차단은 되돌릴 수단이 없는 둘뿐 — 루트/홈 전체 삭제와 디스크 파괴. 확인을 요청하는 것도 로컬 백업이 닿지 않는 원격 히스토리(기본·보호 브랜치 push, 원격 브랜치 삭제)뿐이다
- 🧩 **외과적 병합** — 권한/훅을 추가하고 `model`·`effortLevel`·`language`는 **없을 때만** 채운다. 사용자가 이미 고른 값과 그 외 키(env, statusLine 등)는 100% 보존
- ⏎ **줄바꿈 키 통일** — Claude Code / Codex / Grok CLI에서 Shift+Enter(또는 Ctrl+Enter)로 줄을 넣고, Enter는 그대로 전송. VS Code·Cursor 통합 터미널, tmux, Windows Terminal, 에이전트 키맵까지 한 번에 맞춘다
- 🔁 **멱등성 · dry-run** — 몇 번을 실행해도 안전하고, `--dry-run`으로 실제 적용 전에 바뀔 내용을 미리 확인
- 🖥️ **크로스 플랫폼** — Windows(PowerShell)와 POSIX(bash) 양쪽을 단일 소스로 관리

> ⚠️ **범위 주의**: 훅과 권한은 `~/.claude`(유저 레벨)에 설치되어 **이 사용자가 여는 모든 프로젝트**에 적용된다.

---

## 설치

> 비공개(private) 레포라서 GitHub 인증이 필요하다. `gh` CLI 설치와 토큰 발급은 [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) 참고.

인자 없이 실행하면 가드 훅/권한(전역)과 `AGENTS.md`(현재 폴더)가 모두 설치된다. `AGENTS.md`는 현재 작업 디렉터리에 생기므로 프로젝트 루트에서 실행하자.

**macOS / Linux / Git Bash**
```sh
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh
```

**Windows PowerShell**
```powershell
if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = gh auth token }
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1 | iex
```

---

## 사용법

인자 없이 실행하면 **대화형 온보딩**이 떠서 무엇을 어떻게 설치할지 고르게 한다:

```
? 무엇을 설치할까요? (↑↓ 이동, Enter 선택)
 » 전체 — 가드 훅/권한(전역) + AGENTS.md(현재 폴더)
   가드 훅 + 권한만 (~/.claude, 모든 프로젝트에 적용)
   AGENTS.md 만 (현재 폴더)
```

이어서 **권한 모드**(`auto` / `bypassPermissions`), **줄바꿈 키**(`Shift+Enter` / `Ctrl+Enter` — 범위가 '전체'일 때만), 기존 `AGENTS.md`가 있다면 **덮어쓸지**, 그리고 **지금 적용할지 변경 계획만 먼저 볼지**를 묻는다. `curl … | sh`로 실행해도 프롬프트가 정상 동작한다 — 자세한 사정은 [아래 절](#curl--sh에서-대화형-프롬프트가-동작하는-이유)에 있다.

플래그를 하나라도 주면 온보딩을 건너뛰고 예전과 똑같이 동작하므로, 기존 자동화 호출은 그대로 쓰면 된다. PowerShell에서 `irm | iex`는 인자를 넘기기 어려우므로, 플래그가 필요하면 `scriptblock` 형태로 감싸서 쓴다:

```powershell
& ([scriptblock]::Create((irm -Headers @{Authorization="Bearer $(gh auth token)"} `
    https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -Keybinds -Newline ctrl-enter
```

| 플래그 (POSIX / PowerShell)  | 동작                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------- |
| (없음)                       | 대화형 온보딩 → 고른 대로 설치 (터미널이 없으면 전체 설치로 폴백)                                 |
| `--hooks` / `-Hooks`         | 가드 훅 + 권한만 설치 (전역, `~/.claude`)                                                         |
| `--agentsmd` / `-AgentsMd`   | 현재 폴더에 프로젝트 지침만 설치                                                                  |
| `--harness <목록>` / `-Harness <목록>` | 지침을 설치할 하네스 (쉼표 구분: `claude`,`codex`,`grok`,`opencode`,`all`). 기본 `all`   |
| `--keybinds` / `-Keybinds`   | 줄바꿈 키바인딩만 설치 (VS Code·Cursor·Claude·Codex·tmux·Windows Terminal)                        |
| `--newline <값>` / `-Newline <값>` | 줄바꿈 키를 고른다 — `shift-enter`(기본) 또는 `ctrl-enter`                                  |
| `--omc` / `-Omc`             | oh-my-claudecode 플러그인 설치 + HUD에 프롬프트 캐시 TTL 표시 ([아래 참고](#omc와-캐시-ttl-hud)). 기본 전체 설치에는 포함되지 않는다 |
| `--dry-run` / `-DryRun`      | 아무것도 바꾸지 않고 변경 계획만 출력                                                             |
| `--no-onboard` / `-NoOnboard`| 온보딩을 띄우지 않고 기본값(전체 설치)으로 실행                                                   |
| `--uninstall` / `-Uninstall` | 설치가 추가한 것만 정밀 복원 (아래 참고)                                                          |
| `--help` / `-Help`           | 도움말                                                                                             |

`--newline`은 다른 플래그와 조합할 수 있다 — `--keybinds --newline ctrl-enter`는 키바인딩만 Ctrl+Enter로, `--no-onboard --newline ctrl-enter`는 전체 설치를 Ctrl+Enter로 한다. 재실행 시 `--newline`을 주지 않으면 매니페스트에 기록된 이전 선택을 그대로 쓰고, 기록이 없으면 `shift-enter`다. 값이 둘 중 하나가 아니면 아무것도 쓰지 않고 종료 코드 1로 끝난다.

온보딩이 직접 쓰는 하위 옵션도 워커에 그대로 열려 있다 — `setup_hooks`의 `--default-mode <모드>`(`auto`/`bypassPermissions`/`default`/`acceptEdits`/`plan`)와 `setup_agentsmd`의 `--force`(기존 지침 파일을 `.bak.<타임스탬프>`로 백업한 뒤 덮어쓰기)다.

`--harness`는 **무엇을 쓸지**가 아니라 **무엇을 읽는지**로 갈린다. Codex·Grok·OpenCode는 루트 `AGENTS.md`를 직접 읽으므로 그 파일 하나면 되고, Claude Code는 `AGENTS.md`를 읽지 않고 `CLAUDE.md`를 읽으므로 `@AGENTS.md` 한 줄짜리 `CLAUDE.md`가 추가로 필요하다(Windows에서 심볼릭 링크는 관리자 권한을 요구해서 import를 쓴다). 그래서 `AGENTS.md`는 항상 설치되고, `CLAUDE.md`는 선택에 `claude`가 있을 때만 생긴다. 여러 하네스를 함께 쓰는 프로젝트가 흔하므로 다중 선택이 기본이며 — `--harness claude,codex` — 온보딩에서도 체크박스로 고른다. 모르는 이름을 주면 아무것도 쓰지 않고 종료 코드 1로 끝난다.

예시 (macOS/Linux/Git Bash — Windows는 위 `scriptblock` 패턴에 `-Hooks`/`-DryRun`/`-Uninstall` 등을 붙이면 된다):

```sh
# 전역 가드/권한만, 미리보기
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --hooks --dry-run

# 제거
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --uninstall
```

`--uninstall`은 설치 시 기록한 매니페스트(`~/.claude/.claude-code-setup.json`)를 근거로 우리가 추가한 훅·allow/deny 항목·`model`/`effortLevel`/`language`만 제거하고, `defaultMode`를 이전 값으로 원복하며, 설치가 제거했던 구버전 규칙이 있다면 다시 넣어 준다. 사용자가 원래 갖고 있던 설정과 그 외 키는 그대로 보존되며 변경 전 `settings.json.bak.<타임스탬프>`를 남긴다. `settings.json`을 설치가 새로 만든 경우, 되돌린 뒤 비면 파일도 제거한다. 줄바꿈 키바인딩도 함께 되돌리는데, **무엇을 '우리 것'으로 볼지는 대상마다 다르다.**

- **시그니처로 식별**(VS Code·Cursor): 명령 + `when` + 시퀀스가 우리가 쓰는 것과 정확히 같은 항목만 제거한다. 이 조합은 이 설치가 만들어내는 형태라, 누가 먼저 넣었든 같은 항목이다 — 예컨대 Claude `/terminal-setup`이 넣어둔 `shift+enter` → `sendSequence` 항목도 제거 대상이다. 시퀀스가 다른 사용자 항목(에디터·노트북의 Shift+Enter)은 그대로 둔다.
- **영수증으로 식별**(tmux·Claude·Codex·Windows Terminal): `extended-keys` 줄, Claude의 `chat:newline`, Codex의 `shift-enter`는 전부 사용자가 직접 쓰는 값과 글자까지 같다. 값이 같다는 이유로 지우면 남의 설정을 지우는 것이므로, 매니페스트에 '설치가 넣었다'는 기록이 있는 항목만 되돌린다. 기록이 없으면 건드리지 않는다. 설치가 기존 값을 덮어썼다면 그 값도 기록해 두었다가 되돌린다.

Codex의 기존 `ctrl-j` 처럼 우리가 넣지 않은 키는 남는다. 우리 키만 빠져 `insert_newline`이 비면 그 줄과 빈 `[tui.keymap.editor]` 테이블까지 지운다 — 빈 배열을 남기면 설치 전에 없던 '줄바꿈 전면 언바인드'라는 새 설정을 만드는 셈이기 때문이다. `--keybinds --uninstall`이면 키바인딩만 제거하고 훅은 건드리지 않는다.

레포를 clone해서 로컬로 실행할 수도 있다:

```sh
git clone https://github.com/thsvkd/claude-code-setup.git && cd claude-code-setup
bash scripts/setup.sh --dry-run   # 또는 .\scripts\setup.ps1 -DryRun
```

---

## 무엇이 설치되나

| 위치                                | 내용                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------ |
| `~/.claude/hooks/danger_guard.py`  | 위험 명령 가드 (Bash·PowerShell 툴)                                                  |
| `~/.claude/hooks/send_to_trash.py` | (Windows) 휴지통 이동 헬퍼                                                           |
| `~/.claude/hooks/shims/rm`         | 삭제를 휴지통으로 돌리는 `rm` 셰임 (Bash·Git Bash)                                   |
| `~/.claude/hooks/shims/RmShim.psm1`| 같은 역할의 `Remove-Item` 프록시 (PowerShell, Windows 설치본만)                       |
| `~/.claude/settings.json`          | 권한 + PreToolUse 훅 등록 + `model`/`effortLevel`/`language`·`env.CLAUDE_CODE_SCROLL_SPEED` 기본값(없을 때만) |
| `./AGENTS.md`                      | (`--agentsmd` 시) 현재 폴더에 프로젝트 워크플로 규칙 — 이미 있으면 건너뜀 (`--force`면 백업 후 덮어쓰기) |
| `./CLAUDE.md`                      | (`--agentsmd` + 하네스에 `claude` 포함 시) `@AGENTS.md` 한 줄 — Claude Code는 `AGENTS.md`를 직접 읽지 않는다. 이미 있으면 건너뜀 |
| `~/.claude/keybindings.json`       | (줄바꿈 키) Claude Code의 `Chat` 컨텍스트에 고른 키 → `chat:newline`                     |
| `~/.codex/config.toml`             | (줄바꿈 키) `[tui.keymap.editor] insert_newline`에 고른 키를 **합집합**으로 추가         |
| VS Code / Cursor `keybindings.json` | (줄바꿈 키) 통합 터미널(`when: terminalFocus`)에 고른 키 → `sendSequence`. 경로는 OS별 — Windows `%APPDATA%\Code\User\`, macOS `~/Library/Application Support/Code/User/`, Linux `~/.config/Code/User/` |
| `~/.tmux.conf`                     | (줄바꿈 키, POSIX) `extended-keys on` + `terminal-features …extkeys` — 없을 때만 추가    |
| Windows Terminal `settings.json`   | (줄바꿈 키, `ctrl-enter`를 고른 경우만) `Ctrl+Enter` → `sendInput`                        |

`settings.json`에는 `permissions.defaultMode: "auto"`, 핵심 툴 `allow`(`Bash`, `PowerShell`, `Read(*)`, `Edit(*)`, `Write(*)`, `Agent(*)`, `WebFetch(*)` 등), `ask`(위험 스킬만 — git 관련 규칙은 없음), `hooks.PreToolUse` 등록, 그리고 없을 때만 채우는 `model: "opus"` / `effortLevel: "xhigh"` / `language: "korean"` 과 `env.CLAUDE_CODE_SCROLL_SPEED: "3"`(마우스 휠 스크롤 속도, `/scroll-speed` 대응)이 병합된다. git 관련 deny/ask를 `permissions`에 두지 않는 이유와 그 대가는 [아래 절](#git-정책을-permissions가-아니라-훅이-담당하는-이유-그리고-그-대가)에서 설명한다. 사용자가 이미 고른 값과 그 외 최상위 키(`statusLine` 등), 그리고 사용자의 기존 `env` 키/값은 건드리지 않는다(우리가 관리하는 `env` 키만 없을 때 추가). 단일 소스는 [`res/settings.json`](res/settings.json)이며, 설치 시 python 실행 명령과 훅 경로만 치환된다.

---

## 줄바꿈 키

CLI 에이전트의 프롬프트에서 **줄을 넣고 전송하지 않는** 키를 세 OS에서 같은 의미로 만든다. 값은 `shift-enter`(기본) 또는 `ctrl-enter` 하나다. **Enter 단독은 계속 전송**이고, 고르지 않은 쪽 수정 Enter는 각 에이전트 기본값 그대로 둔다.

대상은 Claude Code CLI · Codex CLI · Grok Build CLI다. Gemini CLI와 Cursor/VS Code의 IDE 챗 입력창은 범위 밖이다(그쪽은 이미 Shift+Enter가 줄바꿈이다).

### 두 층으로 맞춘다

1. **터미널 층** — Shift+Enter를 Enter와 구분하지 못하는 터미널(VS Code·Cursor 통합 터미널)에 `고른 키 → 줄바꿈 시퀀스` 바인딩을 넣는다. 시퀀스는 `ESC` + `CR` (바이트 `0x1B 0x0D`) 하나로 고정돼 있고, `when`은 `terminalFocus`만 걸어 에디터·노트북의 Shift+Enter는 건드리지 않는다. POSIX에서는 `~/.tmux.conf`에 `extended-keys`가 없을 때만 추가한다 — 이게 꺼져 있으면 tmux가 수정 Enter를 통째로 삼킨다.
2. **에이전트 층** — Claude `~/.claude/keybindings.json`의 `Chat` 컨텍스트에 `chat:newline`을, Codex `~/.codex/config.toml`의 `insert_newline`에 고른 키를 **합집합**으로 넣는다. Grok은 키맵을 리맵할 수 없으므로 파일을 만들지 않는다 — 터미널이 보내는 시퀀스에만 의존한다.

Windows Terminal·iTerm2·Ghostty·Kitty·WezTerm 같은 터미널은 Shift+Enter를 이미 Enter와 다르게 보낸다. 여기에 Shift+Enter 시퀀스를 **덧붙이면 줄바꿈이 두 번** 생기므로, `shift-enter`를 고른 경우 Windows Terminal에는 줄바꿈 바인딩을 **넣지 않는다**(이전 설치가 넣어둔 관리 항목이 있으면 그것만 정리한다). `ctrl-enter`를 고른 경우에만 `Ctrl+Enter` 번역을 넣는다.

### 파일을 어떻게 고치나

바꾸기 전 원본을 `<파일>.bak.<타임스탬프>`로 남기고, 임시 파일에 쓴 뒤 교체한다 — 쓰기 도중 끊겨도 원본이 반쯤 잘리지 않는다. 대상이 심볼릭 링크면(dotfile 관리자를 쓰는 경우) 링크를 갈아치우지 않고 가리키는 실체를 고치며, 기존 파일 권한을 그대로 옮긴다. `keybindings.json`은 파싱 후 다시 직렬화하므로 **파일 안의 주석과 들여쓰기 서식은 사라진다**(설정 값과 항목은 전부 보존된다). VS Code가 허용하는 트레일링 콤마는 우리도 읽는다. 그래도 읽지 못한 대상이 있으면 그 사실을 목록으로 알리고 **0이 아닌 종료 코드**로 끝낸다 — 적용되지 않았는데 '완료'라고 말하지 않기 위해서다.

### 안 되는 것

- **gnome-terminal 등 Shift+Enter를 구분하지 못하는 터미널** — 로컬 세션에서는 맞출 수 없다. 설치는 실패하지 않고 경고만 남긴다. Linux는 로컬 gnome-terminal 대신 Windows Terminal/Cursor에서 `ssh`로 붙는 경로를 쓰면 그대로 동작한다.
- **Grok의 `/multiline`(`/ml`, `Ctrl+M`) 모드** — 이 토글이 켜지면 Enter와 Shift+Enter의 의미가 **반대**가 된다(Enter=줄바꿈, Shift+Enter=전송). Grok은 키를 리맵할 수 없어 이 상태를 Claude/Codex와 한 키로 맞추는 것이 불가능하다. 설치기는 그 토글을 켜거나 끄지 않고 리포트에 한 줄 경고만 한다. 기준은 **Grok 기본 프롬프트(multiline 꺼짐)** 다.
- **에이전트가 아예 없을 때** — 바이너리와 설정 디렉터리가 **둘 다** 없으면 그 에이전트는 건너뛰고 설치는 성공한다. 하나라도 있으면 키맵을 쓴다.

---

## OMC와 캐시 TTL HUD

`--omc`(또는 온보딩의 OMC 질문에 '예')를 고르면 [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 플러그인을 `claude plugin marketplace add` / `claude plugin install`로 설치하고, OMC HUD의 세션 경과 시간(`session:45m`) 자리에 **프롬프트 캐시 TTL 잔여 시간**(`cache:57m`)을 띄운다. 서드파티 플러그인이므로 범위를 지정하지 않은 기본 전체 설치에는 포함하지 않는다.

- 값은 Claude Code가 statusLine stdin으로 넘기는 `prompt_cache.expires_at`에서 매 렌더마다 계산한다. 2분 이하면 노랑, 만료되면 `cache:cold`(빨강)이다. 캐시 정보가 없으면(구버전 Claude Code) `session:` 표시를 그대로 둔다. OMC HUD 프리셋에서 session 요소를 끈 경우에는 바꿀 자리가 없어 표시되지 않는다.
- `~/.claude/hud/omc-hud-ttl.mjs`를 복사하고 기존 `statusLine.command` 앞에 래퍼 실행 명령을 끼운다. node는 OMC와 같은 방식으로 찾는다 — POSIX는 OMC의 `find-node.sh`, Windows는 `~/.claude/.omc-config.json`의 `nodeBinary`, 둘 다 없으면 PATH의 `node`. 입력이 없어도 카운트다운이 흐르도록 `statusLine.refreshInterval`이 없으면 `10`(초)을 넣는다.
- `statusLine`이 없으면 플러그인의 정본 템플릿으로 OMC HUD를 먼저 설치한다. OMC가 아닌 다른 `statusLine`이 있으면 사용자 설정이므로 파일 하나 만들지 않는다. `settings.json`이나 매니페스트를 파싱할 수 없으면 쓰지 않고 멈춘다.
- `--uninstall`은 이 설치가 만든 것만 되돌린다 — 래퍼, 우리가 넣은 값 그대로인 `refreshInterval`, 그리고 설치가 새로 만든 `statusLine`·`settings.json`. 설치가 복사한 HUD 파일은 그 `statusLine`도 함께 치울 때, 복사 당시 내용 그대로인 경우에만 지운다 — `omc-setup`이 다시 쓴 파일은 OMC 것이다. 원래 있던 OMC 플러그인과 OMC HUD는 남긴다.
- CLAUDE.md 등 OMC의 나머지 설정은 Claude Code 안에서 `/oh-my-claudecode:omc-setup`으로 진행한다. 그 과정에서 `statusLine`이 다시 써지면 `--omc`를 한 번 더 실행하면 된다.

---

## 온보딩

### `curl | sh`에서 대화형 프롬프트가 동작하는 이유

`curl -fsSL install.sh | sh`는 **stdin이 스크립트 본문**이다. 이 상태에서 프롬프트가 stdin을 읽으면 스크립트의 나머지를 삼키거나 EOF를 만난다. 후보 라이브러리 네 개를 pty 위에서 실측해보면 결과가 이렇다:

| 라이브러리 | 일반 실행 | `curl \| sh` | `/dev/tty` 재바인딩 후 |
| --- | --- | --- | --- |
| **questionary** (채택) | ✅ | ❌ **조용히 첫 항목 확정** | ✅ |
| InquirerPy | ✅ | ❌ `EOFError` | ✅ |
| beaupy | ✅ | ❌ | ❌ 멈춤 |
| cutie | ✅ | ❌ | ✅ |

주목할 건 questionary의 실패 방식이다 — 에러도 경고도 없이 **첫 항목("전체 설치")을 자동으로 확정**한다. 사용자가 아무것도 고르지 않았는데 전역 설치가 진행되는, 가장 위험한 실패 모드다.

그래서 `res/onboard.py`는 프롬프트를 띄우기 전에 제어 터미널(POSIX `/dev/tty`, Windows `CONIN$`/`CONOUT$`)을 직접 열어 fd 0/1에 얹는다. 터미널을 못 열면 대화형을 **아예 포기한다** — 라이브러리에게 판단을 맡기지 않는다.

### 물어볼 수 없을 때와 사용자가 거부했을 때는 다르다

온보딩은 종료 코드로 세 상황을 구분하고, 호출부는 이를 다르게 처리한다:

| 코드 | 상황 | 설치 동작 |
| --- | --- | --- |
| `0` | 사용자가 선택을 마침 | 고른 대로 실행 |
| `2` | 물어볼 수 없음 (TTY 없음 / CI / 벤더 깨짐) | **예전 기본값으로 그대로 진행** — 실패가 아니다 |
| `130` | 사용자가 `Ctrl+C`로 취소 | **아무것도 설치하지 않고 중단** |

`2`와 `130`을 뭉뚱그리면 "취소했는데 기본값으로 설치되는" 동작이 된다. CI 감지는 TTY 검사와 별도로 둔다 — `docker -t`나 tmux처럼 CI가 TTY를 붙여주는 경우가 있어 TTY 유무만으로는 못 거른다.

### 의존성을 설치하지 않고 레포에 넣어둔 이유

온보딩은 `questionary`(+`prompt_toolkit`, `wcwidth`)를 쓰는데, 이를 [`res/vendor/`](res/vendor/)에 벤더링해 둔다. 설치 중에 `pip install`을 하지 않기 위해서다 — 최신 배포판은 PEP 668(`externally-managed-environment`)로 시스템 Python에 대한 `pip install`을 거부하고, 네트워크가 막힌 환경에서는 설치가 통째로 실패한다. 설치 스크립트가 사용자의 파이썬 환경을 바꾸는 것 자체도 적절하지 않다.

벤더링 갱신 방법과 주의사항(특히 `prompt_toolkit`의 `dist-info/METADATA`를 지우면 프롬프트를 띄우는 순간 죽는다)은 [`res/vendor/README.md`](res/vendor/README.md)에 있다.

온보딩은 [`tests/test_onboard.py`](tests/test_onboard.py)가 **pty 위에서 실제 키 입력까지 재현해** 검증한다 — 일반 실행, 파이프 설치, `Ctrl+C` 취소, TTY 없는 환경, 기존 `AGENTS.md`가 있는 경우까지. 프롬프트가 "뜨는지"보다 **띄울 수 없을 때 아무것도 고르지 않는지**가 더 중요하므로 양쪽을 같은 비중으로 고정한다.

---

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

1. **명령 문자열을 재작성하지 않는다.** 삭제를 휴지통으로 돌리는 일은 셰임(shim)이 하고, 훅은 셰임을 끼워 넣는 **선행 한 줄**만 앞에 붙인다. 인자 해석은 전적으로 셸/PowerShell 몫이다.
2. **git 백업도 명령을 건드리지 않는다.** 훅 프로세스가 직접 스냅샷 커밋을 만들고 원본 명령은 그대로 흘려보낸다.
3. **deny 는 되돌릴 수단이 아예 없는 두 부류뿐이다.** 루트/홈 전체 삭제와 디스크 파괴. 파싱하지 않고 명령 문자열의 꼴만 본다.

### 삭제 → 휴지통: PATH·모듈 셰임

| 툴 | 방식 |
| --- | --- |
| Bash (POSIX 셸·Git Bash) | `PATH` 맨 앞에 `~/.claude/hooks/shims` 를 끼워 넣는 한 줄을 붙인다. `shims/rm` 이 셸의 확장이 **끝난 뒤의 argv** 를 받는다 |
| PowerShell | `shims/RmShim.psm1` 을 `Import-Module` 하는 한 줄을 붙인다. 명령 우선순위가 별칭 > 함수 > cmdlet 이라 같은 이름의 함수가 `Remove-Item` cmdlet 을 가리고, `rm`/`del`/`erase`/`ri`/`rd`/`rmdir` 별칭이 전부 그 함수로 해석된다 |

셸이 이미 확장을 끝낸 뒤에 받으므로 **원본 명령과 해석이 어긋날 수 없다.** 종전에 확인을 요구하거나 차단하던 것들이 그냥 동작한다.

| 종전 | 지금 |
| --- | --- |
| `rm -rf "$FOO/bar"` → 확장이 깨져 실패 | ✅ 그대로 동작, 휴지통으로 |
| `rm -f *.nomatch` → 매칭 0개라 차단 | ✅ `rm -f` 의미 그대로 성공 |
| `find … -exec rm -rf {} +` → 확인 | ✅ 셰임을 타므로 휴지통으로 |
| `find … \| xargs rm -f` → 확인 | ✅ 같음 |
| 여러 줄·체이닝에 `rm` 이 섞임 → 확인 | ✅ 파싱하지 않으므로 무관 |
| 스크립트 내부의 `rm` → 훅이 못 봄 | ✅ `PATH` 로 해석되므로 커버 |
| 히어독 본문의 `rm -rf /` → 오탐 | ✅ 데이터로 남음 |

셰임이 **원본 `rm` 에게 그대로 넘기는** 경우 — 셰임이 흉내 내면 의미가 달라지는 것들이다.

- `-i`/`-I` — 치환하면 프롬프트가 사라진다
- `.`/`..` 로 끝나는 대상 — `rm` 이 거부하는 형태다. 치환이 원본보다 더 지우면 안 된다
- 대상이 **전부** `/tmp` 등 tmpfs 아래 — 휴지통 자리도 같은 램이라 옮겨봐야 회수되지 않는다 (실측: 1.4GB 가 이렇게 묶여 스왑을 소진시킨 적이 있다). 하나라도 tmpfs 밖이면 전부 휴지통으로 간다
- 휴지통 도구 부재 — 경고를 남기고 실제 삭제한다. `rm` 자체를 못 쓰게 만드는 쪽이 더 해롭다는 판단이다
- `CLAUDE_NO_TRASH` 가 설정됨 — 명시적 탈출구

루트/홈 전체 삭제는 셰임도 argv 수준에서 한 번 더 거부한다. `bash -c "rm -rf /"` 처럼 훅의 텍스트 규칙을 비껴가는 형태를 여기서 잡는다.

**한계**: `sudo rm` 은 sudo 의 `secure_path` 가 `PATH` 를 버려 셰임을 타지 않는다(실사용 10,329건 중 2건). `find … -delete` 처럼 `rm` 을 거치지 않는 삭제도 커버 밖이다.

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
| **원격의 기본·보호 브랜치**로 `git push` (`git symbolic-ref refs/remotes/origin/HEAD` 로 판정, 없으면 `main`/`master`), `--all`/`--mirror` | ❓ **확인** — 원격 히스토리는 로컬 백업이 닿지 않는다 |
| 원격 브랜치 **삭제** (`--delete`/`-d`, `origin :branch`) | ❓ **확인** — 브랜치 이름과 무관하게 |
| 곁다리 브랜치 push (force 포함) | ✅ 통과 |
| 그 외 전부 | ✅ 통과 (판단 안 함) |

차단 규칙은 **명령 자리**에서 시작할 때만 잡는다. `grep -rn "rm -rf /" docs/` 처럼 위험한 문자열을 데이터로 다루는 명령은 막지 않는다 — 종전 오탐이 대부분 이 부류였다.

**종전에 있었으나 실측 근거로 제거한 것**: 포크밤 패턴, `curl … | bash` 패턴, `find`/`xargs` 대량 삭제 확인, 체이닝 삭제 확인, 글로브 미일치 차단, `.`/`..` 차단, 대상 100개 초과 확인, `chmod 777` 확인, `shred` 확인, `shutdown`/`reboot` 확인, 훅 내부 오류 확인, 그리고 시크릿 파일 접근 확인(`secrets_guard`) — 파괴가 아니라 유출 위험이고, 그쪽은 auto mode 분류기가 맡는다. 기존 설치본에 남아 있으면 설치 중에 훅 파일과 `settings.json` 등록을 함께 걷어낸다.

**이 목록은 완전하지 않고, 완전할 수도 없다.** 셸은 임의의 프로그램을 실행할 수 있어서 `python3 -c "shutil.rmtree('.')"` 같은 경로를 명령 문자열만 보고 판정하는 건 불가능하다. 그래서 이 훅은 차단을 목표로 하지 않는다 — 되돌릴 수 있게 만드는 것이 목표다. 배경은 [docs/2026-07-31-delete-guard-architecture.md](docs/2026-07-31-delete-guard-architecture.md) 참고.

### git 정책을 permissions가 아니라 훅이 담당하는 이유 (그리고 그 대가)

Claude Code에서 `permissions`의 `deny`/`ask` 규칙은 PreToolUse 훅의 `allow` 판정보다 항상 우선한다. 따라서 `Bash(git push *)` 같은 규칙을 `settings.json`에 두면 위의 세밀한 판단(곁다리 브랜치 통과)이 전부 무력화된다. 그래서 git 정책은 전적으로 훅이 담당한다.

**업그레이드 시 자동 마이그레이션**: 예전 버전은 `Bash(git push *)`·`Bash(git reset --hard *)`(및 PowerShell 짝)을 `deny`로 배포했다. 병합 엔진은 원래 '추가만' 하므로 그 규칙들이 기존 설치본에 그대로 남고, deny가 훅보다 우선하니 **새로 설치한 사람에게는 동작하고 업그레이드한 사람에게는 조용히 죽는** 상태가 된다. 그래서 설치 중에 *우리가 배포했던 문자열과 정확히 일치하는* 그 규칙들만 제거하고, 무엇을 지웠는지 설치 리포트에 출력한다. 문자열이 조금이라도 다른(=사용자가 직접 넣은) 규칙은 건드리지 않으며, 제거 사실은 매니페스트에 기록돼 `--uninstall` 시 원래대로 복원된다.

그 대가로 훅이 유일한 방어선이 되지만, **훅이 죽어도 잃는 것은 복구 수단이지 실행 권한이 아니다.** 훅이 예외로 죽으면 Claude Code는 판정 없이 명령을 실행한다(fail-open). 종전에는 이때 확인으로 승격했지만 실측상 그 확인은 전부 마찰이기만 했으므로, 이제 내부 오류는 `guard.log`에 `guard-error`로 남기고 조용히 통과시킨다. 설치 후 셀프테스트가 통과했는지 확인하는 것이 그만큼 더 중요하다.

## 보안 고려사항

`CLAUDE_SETUP_REPO` 환경변수를 설정하면 지정한 레포의 스크립트를 다운로드해 그대로 실행한다. 신뢰할 수 없는 입력(CI 환경변수, 공유 환경 등)이 이 변수를 제어할 수 있으면 임의 코드 실행(RCE)으로 이어질 수 있다. `CLAUDE_SETUP_REPO`/`CLAUDE_SETUP_REF`는 신뢰된 환경에서만 설정하고, 공유 CI에서는 외부에서 덮어쓸 수 없도록 접근을 제한하자.

---

## 요구사항

- **Python 3.9+** (필수) — 훅은 `settings.json`에 `python3`로 등록되므로, Claude Code가 PATH에서 처음 찾는 python3에서 반드시 돌아야 한다 (macOS 기본 `/usr/bin/python3` 포함).
- **macOS**: 추가 설치 불필요. 14.4+는 `/usr/bin/trash`를 기본 제공. (Homebrew `trash-cli`는 keg-only라 `brew install` 해도 PATH에 안 잡힌다.)
- **Linux**: `bash`, `trash-cli`(pip로 자동 설치 시도 — 없으면 `rm` 은 경고를 남기고 실제로 삭제된다)
- **Windows**: `send2trash`(pip로 자동 설치 시도 — Git Bash 의 `rm` 폴백에 쓰인다. PowerShell 셰임은 OS 휴지통 API 를 직접 쓴다)

> `auto` 모드는 계정/버전 자격 요건을 충족해야 켜진다. 설치 후 세션에서 `Shift+Tab`으로 모드를 순환시켜 확인할 수 있다.

---

## 저장소 구조

```
res/
  AGENTS.md                 # 배포될 프로젝트 워크플로 규칙
  settings.json             # 실제 settings.json 조각 (SSoT, {{PY}}·{{HOOKS_DIR}} 자리표시자)
  onboard.py                # 대화형 온보딩 TUI (인자 없이 실행할 때만 뜸)
  vendor/                   # 온보딩 의존성 (questionary·prompt_toolkit·wcwidth, 벤더링)
  keybinds/
    apply.py                # 줄바꿈 키바인딩 외과적 병합 (VS Code·Cursor·Claude·Codex·WT·tmux)
  omc/
    apply.py                # OMC HUD statusLine 에 캐시 TTL 래퍼 연결 / uninstall
    omc-hud-ttl.mjs         # OMC HUD 출력의 session:NNm 을 cache:NNm 으로 바꾸는 래퍼
  hooks/
    danger_guard.py         # 위험 명령 가드 (Bash + PowerShell, 전 플랫폼 공용)
    shims/rm                # 삭제 → 휴지통 (POSIX 셸·Git Bash)
    shims/RmShim.psm1       # 삭제 → 휴지통 (PowerShell)
    send_to_trash.py        # Windows 휴지통 헬퍼
    merge_and_diff.py       # 자리표시자 치환 + 외과적 병합 엔진
scripts/
  setup.{ps1,sh}            # CLI 디스패처 (엔트리포인트)
  setup_hooks.{ps1,sh}      # 가드 훅 + 권한 설치 / uninstall 워커
  setup_agentsmd.{ps1,sh}   # AGENTS.md 설치 워커
  setup_keybinds.{ps1,sh}   # 줄바꿈 키바인딩 설치 / uninstall 워커
  setup_omc.{ps1,sh}        # oh-my-claudecode 설치 + 캐시 TTL HUD 워커
  test.{ps1,sh}             # 테스트 러너 (pytest + bats + Pester 통합 실행)
  lib/                      # 공용 오케스트레이션 함수
install.{ps1,sh}            # 원격 설치 부트스트랩 (curl | sh / irm | iex)
docs/                       # 인증 등 부가 문서
tests/                      # pytest(훅·병합) + bats(bash) + Pester(PowerShell)
```

---

## 개발 · 테스트

가드 훅과 병합 엔진은 블랙박스로 테스트한다 (JSON을 stdin으로 넣고 판정을 검증). git 정책은
판정뿐 아니라 **실제 git 저장소에서 실측**한다 — 자동치환(stash-prepend)이 진짜로 작업을
보존·복구하는지, 안전 판정한 명령이 정말 안전한지까지 확인한다 ([`tests/test_git_guard_realworld.py`](tests/test_git_guard_realworld.py)).

러너가 세 개(pytest / bats / Pester)라 하나씩 기억해 돌리기 번거롭다. `scripts/test.sh`(POSIX)와
`scripts/test.ps1`(Windows)이 **설치된 러너를 찾아 전부 실행하고 통과·실패·건너뜀을 구분해 보고**한다.

```sh
bash scripts/test.sh                     # 있는 러너로 전부
bash scripts/test.sh --python-only       # pytest 만
bash scripts/test.sh --strict            # 러너 미설치로 건너뛴 것도 실패 취급 (CI용)
bash scripts/test.sh -k git_guard        # 남은 인자는 pytest 로 전달

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
python -m pytest tests/ -rs              # 훅 정책 + git 실측 + 병합 엔진 + 셋업 스크립트
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
