# 핸드오프: OS 공통 줄바꿈 키 (Shift+Enter / Ctrl+Enter)

R1 합의. 구현·테스트 코드는 이 문서와 `docs/CONTEXT.md`, `docs/reviews/newline-keybind-testcases.html`만 입력으로 쓴다. 새 케이스를 추가·재해석하지 않는다.

## PRD

### 문제

Claude Code / Codex / Grok CLI의 줄바꿈 키가 OS·터미널·에이전트마다 다르다. 같은 손가락으로 줄을 넣고 싶은데, VS Code/Cursor는 Shift+Enter를 Enter와 구분하지 못하고, tmux는 extended-keys가 꺼져 있으면 수정 Enter가 사라지며, Grok은 키를 리맵할 수 없다.

해결하려는 것: **이 레포의 설치가, 고른 줄바꿈 키를 세 OS에서 같은 의미로 만들 것.** 줄바꿈 키의 기본은 Shift+Enter다. 온보딩에서는 Ctrl+Enter도 고를 수 있다. Enter 단독은 계속 전송이다.

### 범위

- 대상 에이전트: Claude Code CLI, Codex CLI, Grok Build CLI. Gemini 제외. Cursor/VS Code IDE 챗창 제외.
- 설치 진입점: 전체 설치에 포함. `--keybinds` / `-Keybinds` 단독 플래그. `--hooks`에는 넣지 않음.
- 온보딩: `SCOPE=all`일 때만 줄바꿈 키를 Shift+Enter / Ctrl+Enter 중 고른다. 기본 선택은 Shift+Enter. `SCOPE=hooks`/`agentsmd`면 묻지 않고 키바인딩도 설치하지 않는다.
- 비대화형(`--no-onboard`, CI, TTY 없음, `--keybinds`만): 기본 `shift-enter`. `--newline ctrl-enter`로 덮어쓴다.
- Linux 완료 기준: 로컬 gnome-terminal이 아니라 **SSH 실측 경로** (Windows Terminal/Cursor → `ssh linux-host` → 원격 에이전트). gnome-terminal은 경고만.
- 고르지 않은 키는 건드리지 않는다.

### 동작 원리 (두 층)

1. **터미널 층** — 설정 필요 터미널(VS Code, Cursor)에 고른 키 → 줄바꿈 시퀀스 바인딩을 넣는다. 네이티브 구분 터미널(Windows Terminal, iTerm2)에는 Shift+Enter용 sendInput을 넣지 않는다(이중 줄바꿈). Ctrl+Enter를 고른 경우에만 네이티브 터미널에도 Ctrl+Enter 번역을 넣는다. POSIX tmux에는 `extended-keys` + `terminal-features extkeys`를 없을 때만 추가한다.
2. **에이전트 층** — Claude `~/.claude/keybindings.json`의 Chat 컨텍스트에 고른 키 → `chat:newline`. Codex `~/.codex/config.toml`의 `[tui.keymap.editor] insert_newline`에 고른 키를 합집합으로 추가(기존 ctrl-j 등은 유지). Grok은 파일을 쓰지 않는다.

줄바꿈 시퀀스의 바이트 값은 구현 전 실측으로 고른다. 후보 우선순위:

1. CSI u Shift+Enter: `\u001b[13;2u`
2. Claude `/terminal-setup` 현재 값: `\u001b\r` (이 머신 VS Code/Cursor에 이미 있음)
3. xterm modifyOtherKeys: `\u001b[27;2;13~`

**금지:** 줄바꿈 페이로드로 단독 `\n`(Ctrl+J)을 쓰지 않는다. Grok에서 Ctrl+J는 스크롤이다.

실측 합격 조건: 고른 키를 누르면 프롬프트에 줄이 생기고 전송되지 않음. Enter는 전송됨. 세 에이전트 모두 같은 시퀀스를 줄바꿈으로 읽어야 채택.

## 핵심 결정

1. 유형은 기능(feature). R1→R4.
2. Gemini CLI는 범위 밖.
3. 온보딩에서 줄바꿈 키를 Shift+Enter / Ctrl+Enter 중 고른다. 기본·비대화형은 Shift+Enter.
4. 전체 설치에 포함 + `--keybinds` 단독. `--hooks`는 키바인딩을 설치하지 않음. 온보딩 `SCOPE=all`일 때만 묻는다.
5. 고르지 않은 키는 에이전트 기본값 유지.
6. Enter는 전송 유지.
7. Linux 로컬 gnome-terminal은 불가 경고. 실측은 SSH 경로. tmux extended-keys는 설치.
8. 외과적 병합·멱등·dry-run·uninstall은 훅 설치와 같은 철학. 영수증은 기존 `~/.claude/.claude-code-setup.json`에 키바인딩 섹션을 누적한다. 훅이 아직 없어도 `--keybinds`만으로 매니페스트를 만든다.
9. 에이전트 바이너리와 설정 디렉터리가 모두 없으면 그 에이전트는 건너뛰고 설치는 성공한다.
10. Grok `/multiline`(Enter↔Shift+Enter 반전)은 완료 범위 밖. 설치기는 그 토글을 켜거나 끄지 않는다. 설치 리포트에 한 줄 경고만 한다. 켠 상태의 Grok과 Claude/Codex를 한 키로 맞추는 것은 불가능하다.
11. 관리 바인딩의 `when`은 `terminalFocus`만. 에디터·노트북·IDE 챗의 Shift+Enter는 그대로.
12. 재실행 시 `--newline`이 없으면 매니페스트의 이전 선택 유지. 기록 없으면 Shift+Enter.
13. 테스트 코드는 범용이어야 한다. 특정 SSH 호스트·이 머신에만 있는 에이전트/터미널 창을 전제하는 테스트는 작성하지 않는다. 세 디바이스 TUI 실측은 R3이며 Test-N이 아니다.

## 기각한 대안

- **Gemini 포함:** 사용자 제외.
- **Cursor/VS Code IDE 챗창 통일:** CLI 프롬프트만. IDE 챗은 이미 Shift+Enter.
- **Linux에 Kitty/WezTerm 설치:** 침습적. SSH 경로로 실측.
- **고르지 않은 키를 전송으로 뒤집기 / 언바인드:** Grok은 언바인드 불가, Enter 전송과 충돌.
- **비대화형에서 키바인딩 생략:** 기본 Shift+Enter로 설치.
- **줄바꿈 페이로드를 `\n`으로 통일:** Grok Ctrl+J가 스크롤.
- **Windows Terminal에 Shift+Enter sendInput을 항상 넣기:** 네이티브와 겹치면 이중 줄바꿈.
- **Grok `/multiline`까지 강제:** 리맵 불가 + 키 의미가 반대. 범위 밖.
- **`--hooks`에 키바인딩을 섞기:** 가드와 관심사가 다름.
- **`ssh mac-host` / `ssh linux-host` / 실제 Claude TUI를 pytest로 고정:** 그 호스트·바이너리가 없는 머신에서 항상 실패한다. 실측은 R3.
- **Grok `/multiline`까지 Shift+Enter=줄바꿈으로 강제:** Grok은 그 모드에서 Shift+Enter를 전송으로 읽고 리맵이 불가하다. Claude/Codex와 한 키로 맞출 수 없다.

## 관련 코드 포인터

- 디스패처: `scripts/setup.sh`, `scripts/setup.ps1` — 온보딩 KEY=VALUE, `--hooks`/`--agentsmd` 분기. 여기에 `--keybinds`와 `--newline`, `SCOPE=all`일 때 키바인딩 워커 호출을 더한다.
- 온보딩: `res/onboard.py` — `ask_all()`이 SCOPE/DEFAULT_MODE/OVERWRITE/DRY_RUN을 묻는다. `SCOPE=all`일 때 줄바꿈 키 질문을 권한 모드 다음에 추가. 결과 키 이름: `NEWLINE_CHORD=shift-enter|ctrl-enter`.
- 온보딩 테스트: `tests/test_onboard.py` — pty로 실제 키 입력. 새 질문이 끼면 DOWN/ENTER 시퀀스를 맞춰야 한다. 묻지 않는 SCOPE에서는 질문이 없어야 한다.
- 외과적 병합 패턴: `res/hooks/merge_and_diff.py` — 합집합, 없을 때만 추가, 영수증 fold, uninstall. 키바인딩 병합은 이 철학을 따르되 **settings.json이 아닌** VS Code keybindings.json / Claude keybindings.json / Codex TOML / tmux.conf / (필요 시) Windows Terminal settings.json을 다룬다. 기존 merge_and_diff에 키바인딩을 끼워 넣지 않는다.
- 훅 워커 패턴: `scripts/setup_hooks.sh`, `scripts/setup_hooks.ps1`, `scripts/lib/setup_common.sh`, `scripts/lib/SetupCommon.ps1` — dry-run 홈 격리, 매니페스트. 새 워커 `scripts/setup_keybinds.sh` / `scripts/setup_keybinds.ps1` + `res/keybinds/` 병합 스크립트.
- 설치 경로 테스트: `tests/test_setup_scripts.py`, `tests/setup.bats`, `tests/Setup.Tests.ps1` — 격리 HOME, dry-run/실제 설치/uninstall.
- 현재 이 Windows 머신의 기존 바인딩(교체 대상이 아니라 시그니처 참고):
  - `%APPDATA%\Code\User\keybindings.json` — `shift+enter` + `workbench.action.terminal.sendSequence` + `\u001b\r` + `when: terminalFocus`
  - `%APPDATA%\Cursor\User\keybindings.json` — 동일
  - Windows Terminal `settings.json` — Shift+Enter 바인딩 없음 (네이티브)
- 원격:
  - `ssh linux-host` — Ubuntu, gnome-terminal만, tmux.conf에 extended-keys 없음, `~/.local/bin/{claude,grok,agent}`, Codex CLI 없음
  - `ssh mac-host` — iTerm2 + VS Code, tmux는 `source-file <personal tmux config>`, `~/.local/bin/{claude,grok,agent}`

## 어휘 — 줄바꿈 설치 결과(C)

`C` ∈ `shift-enter` | `ctrl-enter`. 아래를 모두 만족해야 “C로 설치됐다”고 단언한다. 파일이 맞다고 TUI가 줄바꿈된다고 말하지 않는다(그건 R3).

1. VS Code와 Cursor 픽스처: 관리 `sendSequence` 하나. key는 `C=shift-enter` → `shift+enter`, `C=ctrl-enter` → `ctrl+enter`. `when`은 `terminalFocus`를 포함하고 에디터/노트북 절은 없다. 시퀀스는 같은 SSoT 상수이며 `{ \u001b[13;2u, \u001b\r, \u001b[27;2;13~ }` 중 하나. 단독 `\n` 금지. Ctrl 변종 시퀀스(`13;5u` 등) 금지.
2. Claude `keybindings.json` Chat: 고른 키는 Claude 표기(`shift+enter` / `ctrl+enter`) → `chat:newline`. 다른 context/bindings 보존.
3. Codex `config.toml`: `insert_newline`에 고른 키를 Codex 표기(`shift-enter` / `ctrl-enter`)로 합집합. 기존 `ctrl-j` 등 유지. 다른 키/테이블 보존.
4. Grok: 키맵 파일을 만들지 않음. multiline 설정을 쓰거나 지우지 않음.
5. 네이티브 쓰기 대상은 **Windows Terminal settings.json만**. `C=shift-enter`면 shift+enter sendInput 없음. `C=ctrl-enter`면 ctrl+enter → 같은 SSoT 시퀀스. iTerm2 등 다른 에뮬레이터 설정 파일은 만들지 않음.
6. 관리 바인딩 key에 고르지 않은 수정 Enter 없음, 단독 `enter` 없음.
7. 에디터/노트북 Shift+Enter 항목과 외래 VS Code/Cursor 항목 보존.

키 철자: VS Code/Cursor/Claude는 `shift+enter`, Codex TOML은 `shift-enter` (공식 예시를 따름).

Windows 테스트는 `HOME`/`USERPROFILE`뿐 아니라 `APPDATA`·`LOCALAPPDATA`(또는 워커의 명시적 대상 경로)를 픽스처로 돌린다. 개발자 본인 VS Code/Cursor/WT 파일을 읽거나 쓰지 않는다.

## 테스트 케이스 리스트

번호 매긴 인수 기준은 `docs/reviews/newline-keybind-testcases.html`이 SSoT다. 별도 리뷰어가 34개를 줄인 결과다. 충돌하면 HTML 검수에서 확정한 쪽을 따른다.

### A. CLI · 온보딩

- **Test-1** 인자 없는 온보딩, SCOPE=all이면 권한 모드 다음·적용 여부 전에 줄바꿈 키를 Shift+Enter / Ctrl+Enter 중 고른다. 기본 선택은 Shift+Enter. 답 파일에 `NEWLINE_CHORD=shift-enter|ctrl-enter`.
- **Test-2** SCOPE=hooks 또는 agentsmd이면 묻지 않고 키바인딩을 설치하지 않는다.
- **Test-3** 온보딩에서 Ctrl+Enter를 고르면 **줄바꿈 설치 결과(ctrl-enter)** 다.
- **Test-4** 온보딩 Ctrl+C → 종료 130, 키바인드 포함 아무 파일도 쓰지 않는다.
- **Test-5** TTY 없음/CI → 온보딩 생략, 전체 설치는 **줄바꿈 설치 결과(shift-enter)**.
- **Test-6** `--keybinds` / `-Keybinds`는 키바인딩만 설치하고 훅·AGENTS.md는 건드리지 않는다. 훅이 없어도 매니페스트를 만든다.
- **Test-7** `--keybinds --newline ctrl-enter`와 `--newline shift-enter`(POSIX와 PowerShell)는 각각 **줄바꿈 설치 결과(C)**. `--no-onboard --newline ctrl-enter` 전체 설치도 ctrl-enter 결과다.
- **Test-8** `--newline` 허용 값이 아니면 exit 1, 대상 파일 불변.
- **Test-9** `--hooks`, `--agentsmd`, `--hooks --newline ctrl-enter`는 키바인드 대상 파일을 쓰지 않는다.
- **Test-10** `--keybinds --dry-run`은 쓰지 않고, 계획에 키바인드 대상 경로가 보인다.
- **Test-11** 온보딩 스킵 전체 설치 = 훅 + AGENTS.md + **줄바꿈 설치 결과(shift-enter)**.
- **Test-12** `setup.sh --uninstall` / `setup.ps1 -Uninstall`은 훅과 관리 키바인드를 제거한다. `--keybinds --uninstall`은 키바인드만. 사용자 원래 항목은 남긴다. tmux는 우리가 넣은 줄만, VS Code/Cursor는 관리 sendSequence만 지운다.
- **Test-13** 두 번 설치해도 관리 바인딩이 늘지 않는다. 설치 전에 동일 바인딩이 있어도 재추가하지 않는다. 영수증이 빈 값으로 덮이지 않는다.
- **Test-14** 재실행에 `--newline`이 없으면 매니페스트의 이전 선택. `--keybinds`만으로도 선택이 기록된다. 기록 없으면 Shift+Enter.
- **Test-15** `setup.sh --help`와 `setup.ps1 -Help`에 `--keybinds`/`-Keybinds`와 `--newline`이 보인다.
- **Test-16** 한 코드로 설치한 뒤 다른 `--newline`으로 재실행하면 관리 바인딩이 교체된다. 이전 코드의 관리 항목이 남지 않는다.
- **Test-17** `install.ps1` param과 setup 전달 목록에 `Keybinds`가 있고, `-Newline` 값이 setup까지 전달된다.

### B. 파일 · 스킵

- **Test-18** VS Code/Cursor 픽스처의 기존 다른 키바인딩은 설치 후에도 그대로다.
- **Test-19** 기존 Claude `keybindings.json`이면 Chat에 고른 키 → `chat:newline`만 합치고 나머지 context/bindings는 보존한다.
- **Test-20** Codex 다른 키/테이블 보존, `insert_newline`에 고른 키 합집합, 기존 `ctrl-j` 등 삭제 금지.
- **Test-21** Grok 설정 디렉터리가 있어도 키맵 파일을 만들지 않는다. multiline 관련 키를 쓰거나 지우지 않는다.
- **Test-22** 바이너리와 설정 디렉터리가 **둘 다** 없으면 그 에이전트 skip, exit 0. **하나만** 있으면 skip하지 않고 키맵을 쓴다.
- **Test-23** tmux.conf에 extended-keys / extkeys terminal-features가 없으면 추가, 있으면 중복하지 않는다.
- **Test-24** 불가 터미널 감지는 픽스처로 주입. 설치는 실패하지 않고 SSH/외부 터미널 경고. 실제 gnome-terminal 불필요.
- **Test-25** 관리 바인딩 `when`은 `terminalFocus`를 포함한다. 에디터/노트북 Shift+Enter 바인딩은 그대로다.
- **Test-26** 격리 WT `settings.json` 픽스처: Shift+Enter 선택이면 shift+enter sendInput 없음. Ctrl+Enter 선택이면 ctrl+enter → SSoT 시퀀스. WT·VS Code·Cursor·tmux·에이전트 키맵 외에 에뮬레이터 설정 파일을 만들지 않는다.
- **Test-27** WT `settings.json` 대상 파일이 없으면 WT skip, exit 0.

### R3 실측 (Test-N 아님 · 테스트 코드 작성 금지)

- Windows Terminal + Claude / Codex / Grok **기본 프롬프트**(multiline 꺼짐): 고른 키 줄바꿈, Enter 전송.
- Cursor 통합 터미널 + 위 세 에이전트: 동일.
- `ssh linux-host` / `ssh mac-host` 원격 에이전트: 로컬 터미널에서 고른 키가 줄바꿈.
- Ctrl+Enter 선택 설치 후 세 에이전트에서 Ctrl+Enter 줄바꿈.
- Shift+Enter 선택 후 Grok Ctrl+Enter 기본(끼어들기) 유지, Claude/Codex Ctrl+J 폴백 유지.
- Grok `/multiline`이 켜진 상태는 맞추지 않는다. 키가 반대인 것이 정상이다.

## R2에게

1. 테스트 코드를 Test-1..Test-27에 1:1로 작성. `covers: Test-N` 태그. 새 케이스 추가 금지.
2. “줄바꿈 설치 결과(C)”는 위 어휘 묶음이다. VS Code key만 보고 통과시키지 마라.
3. 테스트는 격리 HOME **및** APPDATA/LOCALAPPDATA(또는 명시적 대상 경로) 픽스처만 사용한다. `ssh`, 호스트 이름, 실제 TUI, 실제 터미널 창을 전제하지 않는다.
4. OS 능력 skip만 허용 (Windows에서 POSIX pty, bash 없음 등).
5. POSIX + PowerShell 워커를 기존 setup_hooks 패턴으로 맞춘다. `setup.sh --uninstall`이 키바인드도 지우게 디스패치를 고친다. 지금 `exec setup_hooks.sh --uninstall`만 하면 Test-12가 실패하는 게 맞다.
6. 테스트를 약화·skip·삭제해 green 만들지 말 것.
