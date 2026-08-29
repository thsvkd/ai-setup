# claude-code-setup

Claude Code를 **더 안전하게** 쓰기 위한 사용자 레벨(user-level) 설정 번들.
위험한 명령을 자동으로 막거나 휴지통 이동으로 치환하는 **가드 훅**, 합리적인 **권한(permissions)**,
프로젝트용 **AGENTS.md**, 그리고 OS·터미널·에이전트마다 제각각인 **줄바꿈 키**를 Windows / macOS / Linux에 한 번에 설치한다.

- 🛡️ **가드 훅** — `rm`을 휴지통 이동으로 치환, 디스크 포맷·`curl | bash` 등 되돌릴 수 없는 명령을 차단, `git push`는 브랜치 이름으로 판단(곁다리 브랜치는 통과, 보호 브랜치는 확인), `git reset --hard`/`clean`/`stash drop` 등 되돌릴 수 없는 git 명령은 `refs/claude-backups/`에 백업한 뒤 그대로 실행, 시크릿 파일 접근 시 확인 요청
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
| `--agentsmd` / `-AgentsMd`   | 현재 폴더에 `AGENTS.md`만 설치                                                                    |
| `--keybinds` / `-Keybinds`   | 줄바꿈 키바인딩만 설치 (VS Code·Cursor·Claude·Codex·tmux·Windows Terminal)                        |
| `--newline <값>` / `-Newline <값>` | 줄바꿈 키를 고른다 — `shift-enter`(기본) 또는 `ctrl-enter`                                  |
| `--dry-run` / `-DryRun`      | 아무것도 바꾸지 않고 변경 계획만 출력                                                             |
| `--no-onboard` / `-NoOnboard`| 온보딩을 띄우지 않고 기본값(전체 설치)으로 실행                                                   |
| `--uninstall` / `-Uninstall` | 설치가 추가한 것만 정밀 복원 (아래 참고)                                                          |
| `--help` / `-Help`           | 도움말                                                                                             |

`--newline`은 다른 플래그와 조합할 수 있다 — `--keybinds --newline ctrl-enter`는 키바인딩만 Ctrl+Enter로, `--no-onboard --newline ctrl-enter`는 전체 설치를 Ctrl+Enter로 한다. 재실행 시 `--newline`을 주지 않으면 매니페스트에 기록된 이전 선택을 그대로 쓰고, 기록이 없으면 `shift-enter`다. 값이 둘 중 하나가 아니면 아무것도 쓰지 않고 종료 코드 1로 끝난다.

온보딩이 직접 쓰는 하위 옵션도 워커에 그대로 열려 있다 — `setup_hooks`의 `--default-mode <모드>`(`auto`/`bypassPermissions`/`default`/`acceptEdits`/`plan`)와 `setup_agentsmd`의 `--force`(기존 `AGENTS.md`를 `.bak.<타임스탬프>`로 백업한 뒤 덮어쓰기)다.

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

- **시그니처로 식별**(VS Code·Cursor·Windows Terminal·Claude·Codex): 명령 + `when` + 시퀀스가 우리가 쓰는 것과 정확히 같은 항목만 제거한다. 이 조합은 이 설치가 만들어내는 형태라, 누가 먼저 넣었든 같은 항목이다 — 예컨대 Claude `/terminal-setup`이 넣어둔 `shift+enter` → `sendSequence` 항목도 제거 대상이다. 시퀀스가 다른 사용자 항목(에디터·노트북의 Shift+Enter, WT에 직접 건 다른 `sendInput`)은 그대로 둔다.
- **영수증으로만 식별**(tmux): `extended-keys` 같은 줄은 사용자가 직접 쓰는 흔한 설정이라 문자열만 같다고 우리 것이라 볼 수 없다. 매니페스트에 '설치가 넣었다'는 기록이 있는 줄만 지우고, 기록이 없으면 `~/.tmux.conf`를 건드리지 않는다.

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
| `~/.claude/hooks/secrets_guard.py` | 시크릿 파일 접근 가드 (Read·Write·Edit)                                              |
| `~/.claude/hooks/send_to_trash.py` | (Windows) 휴지통 이동 헬퍼                                                           |
| `~/.claude/settings.json`          | 권한 + PreToolUse 훅 등록 + `model`/`effortLevel`/`language`·`env.CLAUDE_CODE_SCROLL_SPEED` 기본값(없을 때만) |
| `./AGENTS.md`                      | (`--agentsmd` 시) 현재 폴더에 프로젝트 워크플로 규칙 — 이미 있으면 건너뜀 (`--force`면 백업 후 덮어쓰기) |
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

바꾸기 전 원본을 `<파일>.bak.<타임스탬프>`로 남기고, 임시 파일에 쓴 뒤 교체한다 — 쓰기 도중 끊겨도 원본이 반쯤 잘리지 않는다. `keybindings.json`은 파싱 후 다시 직렬화하므로 **파일 안의 주석과 들여쓰기 서식은 사라진다**(설정 값과 항목은 전부 보존된다). VS Code가 허용하는 트레일링 콤마는 우리도 읽는다. 그래도 읽지 못한 대상이 있으면 그 사실을 목록으로 알리고 **0이 아닌 종료 코드**로 끝낸다 — 적용되지 않았는데 '완료'라고 말하지 않기 위해서다.

### 안 되는 것

- **gnome-terminal 등 Shift+Enter를 구분하지 못하는 터미널** — 로컬 세션에서는 맞출 수 없다. 설치는 실패하지 않고 경고만 남긴다. Linux는 로컬 gnome-terminal 대신 Windows Terminal/Cursor에서 `ssh`로 붙는 경로를 쓰면 그대로 동작한다.
- **Grok의 `/multiline`(`/ml`, `Ctrl+M`) 모드** — 이 토글이 켜지면 Enter와 Shift+Enter의 의미가 **반대**가 된다(Enter=줄바꿈, Shift+Enter=전송). Grok은 키를 리맵할 수 없어 이 상태를 Claude/Codex와 한 키로 맞추는 것이 불가능하다. 설치기는 그 토글을 켜거나 끄지 않고 리포트에 한 줄 경고만 한다. 기준은 **Grok 기본 프롬프트(multiline 꺼짐)** 다.
- **에이전트가 아예 없을 때** — 바이너리와 설정 디렉터리가 **둘 다** 없으면 그 에이전트는 건너뛰고 설치는 성공한다. 하나라도 있으면 키맵을 쓴다.

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

### danger_guard — 위험 명령

| 명령                                                                                                                    | 조치                                                                  |
| ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `rm`, `del`, `Remove-Item`, `rd`, `rmdir`                                                                               | 🗑️ 휴지통 이동으로 **치환** (macOS `trash` / `trash-put` / send2trash) |
| ↳ 드라이브·홈 루트 삭제 (`C:\`, `/`, `~`, 그리고 `$HOME` 값을 그대로 적은 절대경로)                                     | ⛔ **차단**                                                            |
| ↳ `.`/`..` 형태 (`rm -rf .`, `rm -rf ./`, `rm -rf ..`, `rm -rf sub/.`)                                                  | ⛔ **차단** — rm 자신이 거부하는 형태다 ([아래 절](#치환은-원래-명령보다-위험해지면-안-된다)) |
| ↳ cwd 기준으로 풀면 루트·홈이 되는 상대경로 (`../../../home/me`)                                                        | ⛔ **차단**                                                            |
| ↳ 와일드카드(`rm -rf *.log`)                                                                                            | 🔍 훅이 cwd 기준으로 **확장해 구체 경로로 치환**. 매칭 0개거나 중괄호 확장(`{a,b}`)이면 차단, 100개 초과면 확인 |
| ↳ 래퍼·경로·확장자로 감싼 형태 (`sudo`/`command`/`env`/`exec`/`busybox` 접두어, `/bin/rm`, `rm.exe`)                    | 벗겨내고 위 규칙을 **동일하게** 적용                                   |
| ↳ 휴지통 도구 미설치 / 여러 줄 스크립트에 섞임                                                                          | ⛔ **차단** (fail-closed)                                              |
| **git** — 전역 옵션(`-C`/`-c` 등)을 건너뛰고 **실제 서브커맨드**를 판정해 세분화 (`git stash push` 같은 안전 명령 오탐 방지) | ↓ 아래 세분화 |
| `git push` — 대상 브랜치 이름에 `/`가 있으면(`feature/*`, `fix/*` 등 곁다리 브랜치) 통과. `/`가 없으면(`main`/`master`/`develop` 등) 브랜치 이름을 명시하며 확인. `--all`/`--mirror` 처럼 특정 브랜치로 못 좁히면 확인 (force 여부는 통과/확인 판정에 영향 없음) | ✅ 통과 또는 ❓ **확인** |
| ↳ `git push --delete`/`-d`, `git push origin :<브랜치>` (원격 브랜치 **삭제**)                                           | ❓ **확인** (브랜치 이름에 `/`가 있어도 — 원격은 로컬 백업으로 못 되돌린다) |
| `reset --hard`, `clean -f*`(`-n`/`--dry-run` 제외), `stash drop`/`clear`, `branch -D`/`-M`(대상 있었으면), `tag -d`/`-f`(대상 있었으면), `rebase`(새로 시작), `commit --amend`, `filter-branch`/`filter-repo`, `reflog expire`/`delete`, `gc --prune=now`/`all`, `checkout`/`switch --force`(강제 전환) | 🗂️ **`refs/claude-backups/<timestamp>/<대상>`에 백업 후 그대로 실행** (자동치환) |
| `git checkout -- <경로>` / `checkout .` / `restore`(워킹트리)                                                            | 🗂️ 위와 동일하게 백업 후 실행 (**자동치환**)          |
| ↳ 위 백업 대상 명령이 `-C`/`--git-dir`/`--work-tree`로 **다른 저장소**를 가리키거나 여러 줄·체이닝에 섞임                | ❓ **확인** (백업 대상을 안전하게 특정할 수 없음)      |
| `git stash push`/`pop`/`apply`/`list`, `reset --soft`/`--mixed`, `clean -n`, `branch -d`, `checkout`/`switch <브랜치>`, `restore --staged`, `rebase --continue`/`--abort`/`--skip` | ✅ 통과 (안전) |
| `format` / `diskpart` / `mkfs*` / `newfs_*` / `fdisk` / `parted` / `wipefs` / `Clear-Disk` / `Format-Volume` / `dd of=` | ⛔ **차단**                                                            |
| `diskutil` 파괴적 서브커맨드 (`eraseDisk`, `eraseVolume`, `secureErase`, `partitionDisk`, `apfs deleteContainer` 등)    | ⛔ **차단**                                                            |
| `/dev/sd*`·`/dev/disk*` 등 블록 디바이스로의 리다이렉트, 포크밤 `:(){ :\|:& };:`                                        | ⛔ **차단**                                                            |
| `curl … \| bash`, `irm … \| iex` (원격 출력을 셸로 파이프 — 공백이 없어도)                                              | ⛔ **차단**                                                            |
| `shutdown` / `reboot` / `Restart-Computer`, `chmod 777`, `shred`, `Clear-Content`, `reg delete`                         | ❓ **확인**                                                            |
| `find … -delete`, `find … -exec`/`-execdir`/`-ok` + 삭제 명령                                                            | ❓ **확인** — 대상을 미리 볼 수 없어 휴지통 치환이 불가능하다          |
| `xargs`/`parallel` + 삭제 명령 (`find … \| xargs rm` 처럼 파이프 하류여도)                                              | ❓ **확인** — 대상이 표준입력이라 훅이 볼 수 없다                      |
| 그 외                                                                                                                   | ✅ 통과 (판단 안 함)                                                   |

`sudo`/`command`/`env`/`exec`/`builtin`/`nohup`/`time`/`busybox`/`doas` 접두어는 벗겨 실제 명령을 위 규칙으로 검사한다(`sudo env rm …` 처럼 중첩된 것도 반복해서 벗긴다). 실행 파일을 경로나 확장자로 적은 형태(`/bin/rm`, `rm.exe`)도 같은 명령으로 판정한다. 모든 판정은 `~/.claude/hooks/guard.log`에 감사 기록으로 남는다.

자기 인자를 먼저 받는 래퍼(`timeout 5 rm …`, `nice -n 5 rm …`, `ionice`/`stdbuf`/`setsid`/`taskset`/`chrt`)도 벗겨낸다. 이 형태는 첫 인자(`5`)를 명령으로 오인해 **rm 보호가 통째로 무력화됐던** 경로다. 두 종류의 래퍼는 번갈아 벗기므로 `timeout 5 sudo rm -rf .` 처럼 섞인 형태도 잡힌다.

**이 목록은 완전하지 않다.** 블랙리스트는 원리적으로 완성될 수 없다 — 셸은 임의의 프로그램을 실행할 수 있어서 `python3 -c "shutil.rmtree('.')"` 같은 경로를 명령 문자열만 보고 판정하는 건 불가능하다. 실측 결과 삭제 경로 35가지 중 이 훅이 잡는 건 일부다. 그래서 이 훅의 역할은 **완전 차단이 아니라 흔한 실수에 대한 확인**이다. 근거와 대안(OS 수준 샌드박스, 섀도 스냅샷)은 [docs/2026-07-31-delete-guard-architecture.md](docs/2026-07-31-delete-guard-architecture.md) 참고.

### 치환은 원래 명령보다 위험해지면 안 된다

`rm`을 휴지통 이동으로 바꾸면 편해지지만, **rm이 원래 갖고 있던 보호 장치까지 같이 사라진다.** GNU rm은 `rm -rf .`을 거부한다(`refusing to remove '.' or '..' directory`). 반면 `trash-put`은 거부하지 않는다. 그래서 아무 검사 없이 치환하면, rm이었다면 아무 일도 없었을 명령이 **현재 디렉터리를 통째로 휴지통에 넣는다.** 저장소 루트에서 실행되면 저장소 전체가 사라진다.

같은 이유로 와일드카드도 그대로 넘길 수 없다. 훅이 `*`를 인용해서 넘기면 셸이 확장하지 못해 명령이 조용히 실패하고(사용자에게는 "치환 완료"로 보인다), 인용하지 않으면 무엇이 지워질지 모르는 채로 통과시키게 된다. 그래서 훅이 직접 `cwd` 기준으로 확장하고, **확장된 경로 하나하나에 루트·홈 검사를 다시 적용한 뒤** 절대경로로 고정해서 넘긴다.

원칙은 하나다 — **치환된 명령이 원래 명령보다 더 많이 지울 수 있으면 안 된다.**

### 왜 git 명령을 막지 않고 백업 후 실행하는가

되돌릴 수 없는 git 명령이라도 실행 자체를 막으면 에이전트가 정상적인 작업(재작업, 정리, 리베이스 등)을 진행하지 못하고 매번 사용자 승인을 기다리게 된다. 대신 실행 **직전**에 되돌릴 대상(현재 HEAD, uncommitted 변경, 삭제될 브랜치/태그/스태시, 도달 불가능해질 커밋 등)을 `refs/claude-backups/<timestamp>/<대상>` 아래에 커밋 객체로 고정해두고 원본 명령은 그대로 실행한다.

- **조회**: `git for-each-ref refs/claude-backups/`
- **복구**: 백업 종류에 따라 `git stash apply <hash>`(uncommitted 변경/스냅샷), `git branch <name> <hash>`(브랜치/태그), `git reset --hard <hash>`(HEAD 위치) 중 알맞은 걸 사용

`git clean`처럼 추적 안 된 파일까지 지우는 명령은 `git stash create`가 추적 안 된 파일을 담지 못하는 한계가 있어(실측 확인), 별도 스크래치 인덱스로 추적/미추적 파일 전체를 스냅샷 커밋으로 백업한다. `clean -x`/`-X`는 `.gitignore` 대상(`.env`, `node_modules/`, 빌드 산출물)까지 지우는데 기본 `git add -A`는 그것들을 담지 못하므로, 이 경우에만 `git add -Af`로 무시된 파일까지 스냅샷에 넣는다.

**백업 실패는 곧 명령 중단이다(fail-closed).** 백업 스니펫은 bash에선 전부 `&&`로, PowerShell에선 단계마다 `$LASTEXITCODE` 확인 후 `exit 1`로 이어져, 한 단계라도 실패하면 뒤에 붙은 원본 파괴적 명령이 실행되지 않고 `claude-guard: 백업에 실패해 원본 명령을 실행하지 않았습니다`를 남기고 끝난다. 백업 대상을 애초에 특정할 수 없는 경우 — 멀티라인·`&&`/`;` 체이닝, 또는 `-C`/`--git-dir`/`--work-tree`로 **현재 디렉터리가 아닌 다른 저장소**를 가리키는 경우(백업 스니펫은 cwd에서 실행되므로 엉뚱한 저장소를 백업하게 된다) — 는 자동치환 대신 확인을 요청한다.

`git push`만 이 백업 메커니즘 대신 브랜치 이름 기반 정책을 쓴다 — 원격 히스토리는 로컬 백업으로 보호할 수 있는 대상이 아니고, 어떤 브랜치로 반영되는지가 사용자가 알아야 할 핵심 정보이기 때문이다. 같은 이유로 원격 브랜치 **삭제**(`--delete`/`-d`/`origin :<브랜치>`)는 곁다리 브랜치여도 확인을 요청한다.

### git 정책을 permissions가 아니라 훅이 담당하는 이유 (그리고 그 대가)

Claude Code에서 `permissions`의 `deny`/`ask` 규칙은 PreToolUse 훅의 `allow` 판정보다 항상 우선한다. 따라서 `Bash(git push *)` 같은 규칙을 `settings.json`에 두면 위의 세밀한 판단(곁다리 브랜치 통과, 백업 후 실행)이 전부 무력화된다. 그래서 git 정책은 전적으로 훅이 담당한다.

**업그레이드 시 자동 마이그레이션**: 예전 버전은 `Bash(git push *)`·`Bash(git reset --hard *)`(및 PowerShell 짝)을 `deny`로 배포했다. 병합 엔진은 원래 '추가만' 하므로 그 규칙들이 기존 설치본에 그대로 남고, deny가 훅보다 우선하니 **새로 설치한 사람에게는 동작하고 업그레이드한 사람에게는 조용히 죽는** 상태가 된다. 그래서 설치 중에 *우리가 배포했던 문자열과 정확히 일치하는* 그 규칙들만 제거하고, 무엇을 지웠는지 설치 리포트에 출력한다. 문자열이 조금이라도 다른(=사용자가 직접 넣은) 규칙은 건드리지 않으며, 제거 사실은 매니페스트에 기록돼 `--uninstall` 시 원래대로 복원된다.

그 대가로 **훅이 유일한 방어선**이 된다. 훅이 예외로 죽으면 Claude Code는 판정 없이 명령을 실행하므로(fail-open), 예상 못 한 내부 오류는 조용히 흘려보내지 않고 ❓ 확인으로 승격해 사용자에게 판단을 넘긴다(`guard.log`에 `ask-guard-error`로 기록). 훅 파일 자체가 없거나 python을 못 찾는 상황은 이 장치로도 막을 수 없으므로, 설치 후 `bash scripts/setup.sh`의 셀프테스트가 통과했는지 확인하는 것이 중요하다.

### secrets_guard — 시크릿 파일

`.env`, `id_rsa`/`id_dsa`/`id_ecdsa`/`id_ed25519`, `*.pem`/`*.pfx`/`*.p12`/`*.p8`/`*.ppk`/`*.jks`/`*.keystore`,
`credentials.json`, `secrets.y(a)ml`, `.npmrc`/`.pypirc`/`.netrc`/`.git-credentials`, `~/.aws/credentials` 를
**Read / Write / Edit / MultiEdit**로 접근하면 ❓ 확인을 요청한다 (완전 차단이 아닌 확인 게이트).

판정 기준은 "**이 이름이면 내용이 시크릿일 수밖에 없는가**"다. 이름만으로 알 수 없는 패턴은 오탐이 실탐보다 훨씬 많아 게이트 자체를 무의미하게 만든다. 그래서 예전에 있던 `*_secret*` 과 `*.key` 는 제거했다 — 워크스페이스 전수 검사에서 이 두 패턴의 히트가 전부 라이브러리·테스트 소스코드(`crypto_secretbox.py`, `nested_secrets.py`, `test_secrets_guard.py` 등)였다. 시크릿이 커밋·PR·외부 전송으로 **새는** 방향은 auto mode 분류기가 별도로 막으므로, 이 훅은 이름만으로 확실한 파일에만 집중한다.

단, `.env.example`/`.env.sample`/`.env.template`/`.env.dist` 처럼 자리표시자(placeholder)만 담고 커밋을 전제로 하는
**예시/템플릿 파일은 시크릿이 아니므로 확인 없이 통과**시킨다 (`.env.local.example` 같은 변형도 마지막 확장자로 판정). 실제
시크릿을 담는 `.env`/`.env.local`/`.env.production` 은 그대로 확인 게이트가 걸린다.

---

## 보안 고려사항

`CLAUDE_SETUP_REPO` 환경변수를 설정하면 지정한 레포의 스크립트를 다운로드해 그대로 실행한다. 신뢰할 수 없는 입력(CI 환경변수, 공유 환경 등)이 이 변수를 제어할 수 있으면 임의 코드 실행(RCE)으로 이어질 수 있다. `CLAUDE_SETUP_REPO`/`CLAUDE_SETUP_REF`는 신뢰된 환경에서만 설정하고, 공유 CI에서는 외부에서 덮어쓸 수 없도록 접근을 제한하자.

---

## 요구사항

- **Python 3.9+** (필수) — 훅은 `settings.json`에 `python3`로 등록되므로, Claude Code가 PATH에서 처음 찾는 python3에서 반드시 돌아야 한다 (macOS 기본 `/usr/bin/python3` 포함).
- **macOS**: 추가 설치 불필요. 14.4+는 `/usr/bin/trash`를 기본 제공. (Homebrew `trash-cli`는 keg-only라 `brew install` 해도 PATH에 안 잡힌다.)
- **Linux**: `bash`, `trash-cli`(pip로 자동 설치 시도 — 없으면 `rm` 계열이 차단됨)
- **Windows**: `send2trash`(pip로 자동 설치 시도 — 없으면 `rm`/`del` 계열이 차단됨)

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
  hooks/
    danger_guard.windows.py # Windows용 (Bash + PowerShell)
    danger_guard.posix.py   # macOS/Linux용 (Bash)
    secrets_guard.py        # 공용
    send_to_trash.py        # Windows 휴지통 헬퍼
    merge_and_diff.py       # 자리표시자 치환 + 외과적 병합 엔진
scripts/
  setup.{ps1,sh}            # CLI 디스패처 (엔트리포인트)
  setup_hooks.{ps1,sh}      # 가드 훅 + 권한 설치 / uninstall 워커
  setup_agentsmd.{ps1,sh}   # AGENTS.md 설치 워커
  setup_keybinds.{ps1,sh}   # 줄바꿈 키바인딩 설치 / uninstall 워커
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
