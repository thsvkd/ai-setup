# R3 실측 체크리스트 — 줄바꿈 키 (Shift+Enter)

R2(구현·테스트)는 끝났다. 이 문서는 **사람이 직접 키를 눌러야만 확인되는 것**만 남긴 것이다.
파일이 맞다는 것은 이미 자동 테스트가 보증한다 — 여기서 보는 것은 **TUI가 실제로 줄바꿈하는가**다.

핸드오프: [`newline-keybind.md`](newline-keybind.md) · 어휘: [`../CONTEXT.md`](../CONTEXT.md)

## 설치 상태 (2026-08-27, 이 Windows 머신)

`powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Keybinds` 로 `shift-enter` 설치 완료.

| 대상 | 결과 |
| --- | --- |
| `%APPDATA%\Code\User\keybindings.json` | 변경 없음 — 이미 같은 `sendSequence`(`ESC CR`)가 있었음 (멱등) |
| `%APPDATA%\Cursor\User\keybindings.json` | 변경 없음 — 위와 동일 |
| `~/.claude/keybindings.json` | 새로 생성 — `Chat.shift+enter = chat:newline` |
| `~/.codex/config.toml` | `[tui.keymap.editor] insert_newline = ["shift-enter"]` 추가 |
| Windows Terminal `settings.json` | 변경 없음 — 네이티브 구분 터미널이라 의도대로 건드리지 않음 |
| `~/.tmux.conf` | 대상 아님 (POSIX 전용) |

매니페스트 `~/.claude/.claude-code-setup.json` 의 `keybinds` 에 `newline_chord: shift-enter`,
`claude_keys_added`, `codex_keys_added` 가 기록됐다. `vscode_managed`/`cursor_managed` 는 `false` —
**이번 실행이 그 파일을 바꾸지 않았다는 뜻일 뿐이고, '지우지 않는다' 는 뜻이 아니다.**

> ⚠️ `--uninstall` 은 VS Code/Cursor 를 매니페스트가 아니라 **시그니처**(명령 + `when` + 시퀀스)로 판단한다.
> 이 머신의 `shift+enter` → `sendSequence` 항목은 Claude `/terminal-setup` 이 먼저 넣은 것이지만 시그니처가
> 같으므로 `--uninstall` 시 **제거된다**. 되돌리려면 백업(`keybindings.json.bak.*`) 이나 Claude 의
> `/terminal-setup` 을 다시 쓰면 된다. tmux 만 영수증 기준이라, 기록이 없으면 건드리지 않는다.

원본 백업:
`%LOCALAPPDATA%\Temp\claude\<project>\<session-id>\scratchpad\keybind-backup\`

> ⚠️ **먼저 각 CLI를 새 세션으로 다시 띄울 것.** 실행 중인 세션은 시작 시점의 키맵을 그대로 쓴다.
> 지금 이 Claude Code 세션에는 방금 넣은 바인딩이 적용돼 있지 않다.

## 합격 조건 (모든 칸 공통)

1. 고른 키(**Shift+Enter**)를 누르면 프롬프트에 **줄이 생기고 전송되지 않는다**.
2. **Enter 단독은 전송된다.**
3. 줄이 **두 번** 생기지 않는다 (이중 줄바꿈은 실패다).

## A. 로컬 터미널 × 에이전트

바이너리 위치: `claude` → `~/.local/bin/claude`, `codex` → `%APPDATA%\npm\codex`, `grok` → `~/.grok/bin/grok`

| # | 터미널 | 에이전트 | 결과 | 메모 |
| --- | --- | --- | --- | --- |
| A1 | Windows Terminal | Claude Code | ☐ | |
| A2 | Windows Terminal | Codex CLI | ☐ | |
| A3 | Windows Terminal | Grok (기본 프롬프트, multiline **꺼짐**) | ☐ | |
| A4 | Cursor 통합 터미널 | Claude Code | ☐ | |
| A5 | Cursor 통합 터미널 | Codex CLI | ☐ | |
| A6 | Cursor 통합 터미널 | Grok (multiline 꺼짐) | ☐ | |

Grok은 `/multiline` 이 켜져 있으면 의미가 **반대**가 된다 — 켜져 있다면 `/ml` 로 끄고 측정한다.
켠 상태를 맞추는 것은 범위 밖이며, 반대로 동작하는 것이 정상이다.

## B. SSH 실측 (Linux 완료 기준)

키보드·터미널은 로컬(Windows Terminal 또는 Cursor), 에이전트 프로세스는 원격이다.
원격에도 설치가 필요하다: `bash scripts/setup.sh --keybinds`

| # | 경로 | 에이전트 | 결과 | 메모 |
| --- | --- | --- | --- | --- |
| B1 | `ssh linux-host` (Ubuntu) | Claude Code | ☐ | Codex CLI 없음 |
| B2 | `ssh linux-host` | Grok | ☐ | |
| B3 | `ssh mac-host` (macOS) | Claude Code | ☐ | |
| B4 | `ssh mac-host` | Grok | ☐ | |
| B5 | 원격 tmux 안 | Claude Code | ☐ | `extended-keys` 가 들어갔는지 함께 확인 |

`mac-host` 의 tmux 는 `source-file <personal tmux config>` 를 쓴다 —
설치가 `~/.tmux.conf` 에 넣은 줄이 실제로 로드되는지 확인해야 한다. 안 되면 그 사실 자체가 결과다.

## C. 회귀 — 고르지 않은 키를 건드리지 않았는가

| # | 확인할 것 | 결과 |
| --- | --- | --- |
| C1 | Grok에서 **Ctrl+Enter** 가 원래 동작(끼어들기) 그대로인가 | ☐ |
| C2 | Claude/Codex에서 **Ctrl+J** 줄바꿈 폴백이 살아 있는가 | ☐ |
| C3 | VS Code/Cursor **에디터**(터미널 아님)에서 Shift+Enter 가 원래대로인가 | ☐ |
| C4 | Jupyter/노트북 셀에서 Shift+Enter 가 원래대로인가 | ☐ |

## D. Ctrl+Enter 로 바꿔서 재실측 (선택)

`powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Keybinds -Newline ctrl-enter`

| # | 확인할 것 | 결과 |
| --- | --- | --- |
| D1 | 세 에이전트에서 **Ctrl+Enter** 가 줄바꿈인가 | ☐ |
| D2 | 이전 코드(shift-enter)의 관리 항목이 남아 있지 않은가 | ☐ |
| D3 | Windows Terminal `settings.json` 에 `ctrl+enter` → `sendInput` 이 들어갔는가 | ☐ |

되돌리기: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Keybinds -Newline shift-enter`
전부 제거: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Keybinds -Uninstall`

## 실패했을 때 적을 것

어느 칸인지, 무엇이 일어났는지(줄이 안 생김 / 전송됨 / 두 번 생김), 그리고 그 터미널이 실제로
보낸 시퀀스. 시퀀스는 프롬프트가 아닌 셸에서 `cat -v` 를 띄우고 키를 눌러 확인한다 —
`ESC CR` 은 `^[^M` 으로, CSI u 는 `^[[13;2u` 로 보인다. 이 값이 다르면
`res/keybinds/apply.py` 의 `NEWLINE_SEQUENCE` 후보를 바꿔야 한다는 뜻이다.
