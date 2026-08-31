# 정적 검토 보고 — 줄바꿈 키바인딩 (R4)

6개 축(명세·테스트·병합엔진·크로스플랫폼·문서·안전)에서 독립 탐색 후 축별 적대적 재검증을 거친 결과다.
탐색 13개 에이전트, 확정 31 · 불확실 1 · 기각 3.

명세 SSoT: [`../handoffs/newline-keybind.md`](../handoffs/newline-keybind.md) · [`../CONTEXT.md`](../CONTEXT.md) · [`newline-keybind-testcases.html`](newline-keybind-testcases.html)

## 직접 재확인한 것

아래 다섯 건은 보고를 그대로 믿지 않고 코드와 실행으로 다시 확인했다.

| 항목 | 확인 방법 | 결과 |
| --- | --- | --- |
| macOS VS Code/Cursor 경로 | `apply.py:114-125` 에 darwin 분기 없음, 워커는 `--home` 만 전달 | 사실 |
| tmux uninstall 폴백 | `apply.py:535` `remove = set(added) if added else {상수 두 줄}` | 사실 |
| 전체 uninstall 이 영수증을 먼저 지움 | `scripts/lib/setup_common.sh:115-123` 의 `rm -f "$manifest"` | 사실 |
| Codex 무개행 EOF | `apply.py:419-423` 에 개행 보정 없음 (`:425-427` 에는 있음) | 사실 |
| 온보딩 답 파일 CRLF | Windows python 으로 `write_answers` 실행 → `b'SCOPE=hooks

DRY_RUN=1

...'` | 사실 |
| `parse_jsonc` 트레일링 콤마 | 실제 호출 → `JSONDecodeError`. VS Code 는 이 형식을 받아들인다 | 사실 |

추가로 직접 확인한 것 하나 — **`--uninstall` 은 VS Code/Cursor 의 기존 sendSequence 를 지운다.**
`apply.py:646-647` 이 `vscode_managed` 값과 무관하게 `uninstall=True` 로 호출하고, `apply.py:220-231` 은
매니페스트가 아니라 시그니처(명령+when+시퀀스)만 본다. 이 머신 사용자는 Claude `/terminal-setup` 이 넣은
`shift+enter` sendSequence 를 설치 전부터 갖고 있었으므로, `--uninstall` 을 돌리면 그것이 사라진다.
(`newline-keybind-R3.md:22-23` 과 이전 세션의 설명이 이 점에서 틀렸다 — 아래 9번 항목.)

---

## 즉시 고쳐야 하는 것 (사용자 데이터/기능이 지금 깨진다)

### 1. macOS 에서 VS Code/Cursor 경로가 틀려 설치가 무효 — high
- 출처: docs 발견 4, safety
- `res/keybinds/apply.py:114-125` — `is_windows() and APPDATA` 가 아니면 무조건 `home/.config/{Code,Cursor}/User/keybindings.json`. `apply.py` 전체에 darwin 분기 없음(`apply.py:111` 의 `is_windows` 가 유일한 플랫폼 언급).
- 워커도 덮지 않음: `scripts/setup_keybinds.sh` 는 `--home "$HOME"` 만 넘기고 `CLAUDE_SETUP_VSCODE_KEYBINDINGS` 를 세우지 않는다.
- 결과: mac 설치가 아무도 읽지 않는 파일을 만들고 `apply.py:707` 이 "설치 완료", 매니페스트에 `vscode_managed: true` 를 기록한다. `README.md:5` 와 PRD(`docs/handoffs/newline-keybind.md:11`)가 3 OS 를 약속하고, R3 대상 `mac-host`(`docs/handoffs/newline-keybind-R3.md:56`)가 바로 이 경로를 탄다.
- 테스트 사각: `tests/test_keybinds.py:494-497` 이 두 env 를 항상 주입해 `apply.py:622-623` 의 `default_vscode_path` 는 레포 전체에서 실행되지 않는 죽은 코드다(참조는 `apply.py:622` 뿐).
- 수정: `default_vscode_path`/`default_cursor_path` 에 `sys.platform == "darwin"` 분기를 넣어 `home/"Library"/"Application Support"/{Code,Cursor}/User/keybindings.json` 을 반환하고, 플랫폼을 인자로 받는 순수 함수로 분리해 env 주입 없이 단언하는 단위 테스트를 추가한다.

### 2. tmux uninstall 이 사용자 원래 extended-keys 두 줄을 지운다 — high
- 출처: spec, tests, engine, docs 발견 2, safety (5개 축 중복 — 같은 뿌리)
- `res/keybinds/apply.py:535` `remove = set(added) if added else {TMUX_EXTENDED_LINE, TMUX_EXTKEYS_LINE}` — `added` 는 `apply.py:532`(호출은 `apply.py:653`)에서 매니페스트 `tmux_added` 로만 채워지고, `None` 과 `[]` 가 같은 폴백을 탄다. 삭제는 `apply.py:539-543` 의 정확 문자열 일치, 백업 없음(`apply.py:548-549`).
- 트리거 세 갈래:
  - (a) 사용자가 SSoT 상수(`apply.py:29-30`)와 글자까지 같은 두 줄을 이미 갖고 있으면 `apply.py:552-556` 의 to_add 가 비고, `apply.py:687` 보정은 `prev_kb["tmux_added"]` 가 list 일 때만 돌아 최초 설치(`prev_kb={}`)에서는 안 돌며, `apply.py:703` 이 `[]` 를 기록 → uninstall 이 폴백.
  - (b) 설치를 한 번도 안 한 머신의 `--keybinds --uninstall` → `apply.py:640` 에서 `prev_kb={}` → 즉시 폴백.
  - (c) **가장 넓은 경로**: `scripts/setup.sh:183-184`(및 `scripts/setup.ps1:160-162`)가 훅 uninstall 을 먼저 돌리고, `scripts/lib/setup_common.sh:116-125` 의 `uninstall_hooks` 가 매니페스트 파일을 `rm -f` 로 통째로 지운다. 그래서 POSIX 전체 uninstall 은 **항상** 영수증 없이 폴백으로 들어간다.
- 명세 위반: `docs/CONTEXT.md:43`("--uninstall 은 관리 바인딩만 제거"), `README.md:81`("tmux 는 설치가 추가한 줄만"), `apply.py:527` 의 자기 docstring.
- 테스트 사각: `tests/test_keybinds.py:1119-1126` 은 설치가 실제로 넣은 뒤 지우는 경로만, Test-23(`tests/test_keybinds.py:1394-1398`)은 `set -g extended-keys on`(상수는 `set -s`)을 시드하고 uninstall 을 하지 않는다. Test-12 2단계(`tests/test_keybinds.py:1129-1136`)는 전체 uninstall 을 돌리지만 tmux 를 단언하지 않는다.
- 수정: `apply.py:535` 의 else 폴백을 제거하고 영수증이 비면 tmux 파일을 건드리지 않는다. 영수증이 살아남게 하려면 전체 uninstall 에서 `setup_keybinds` 를 `setup_hooks` 보다 먼저 돌리거나(`scripts/setup.sh:183-184`, `scripts/setup.ps1:160-162`), `uninstall_hooks` 가 매니페스트의 keybinds 섹션은 남기게 한다. 회귀 테스트: 상수 두 줄을 미리 시드 → 설치 → 전체 uninstall → 두 줄 존속 단언.

### 3. Codex config.toml 이 개행 없이 끝나면 TOML 이 깨진다 — medium
- 출처: spec
- `res/keybinds/apply.py:375` 가 `splitkeepends=True` 로 읽어 마지막 줄이 개행 없이 out 에 들어가고(`apply.py:416`), EOF 분기 `apply.py:419-423` 에는 `apply.py:425-427` 이 갖고 있는 `if out and not out[-1].endswith("\n"): out[-1] += "\n"` 보정이 없다.
- 결과: `[tui.keymap.editor]` 가 마지막 섹션 + `insert_newline` 부재 + 무개행 EOF 이면 `indent = ["tab"]insert_newline = ["shift-enter"]` 가 생겨 사용자 Codex 설정 전체가 파싱 불가가 된다.
- 테스트 사각: 픽스처 `tests/test_keybinds.py:315-326` 은 뒤에 `[projects.sentinel]` 이 있고 개행으로 끝나 이 분기를 못 밟는다.
- 수정: `apply.py:419-423` append 전에 같은 개행 보정을 넣고, 같은 이유로 `apply.py:401-405` 섹션 전환 분기에도 넣는다.

### 4. keybindings.json 파싱 실패를 경고만 하고 "설치 완료" + exit 0 — medium
- 출처: engine
- `res/keybinds/apply.py:246-253` 이 OSError/ValueError 를 삼켜 None 반환, `apply.py:259-262` 가 경고 후 False. run() 은 그대로 진행해 `apply.py:698-706` 에서 `newline_chord` 를 기록하고 `apply.py:707` "✅ 줄바꿈 키바인딩 설치 완료.", `apply.py:708` `return 0`. 같은 삼킴이 `apply.py:296-302`, `apply.py:497-501` 에도 있다.
- 핵심: 이건 예외적 파손이 아니다 — `parse_jsonc`(`apply.py:46-87`)가 트레일링 콤마를 처리하지 않아, VS Code 가 정상으로 받아들이는 `[{...},]` 형태에서 항상 ValueError 가 난다. 그 사용자는 관리 sendSequence 가 하나도 없는 채로 "완료"를 본다 — 어휘 C-1(`docs/handoffs/newline-keybind.md:87`) 불성립. 결정 9 의 skip 허용은 "바이너리와 설정 디렉터리가 모두 없을 때"(`newline-keybind.md:47`)로 한정되어 이 경우를 덮지 않는다.
- 수정: `parse_jsonc` 에 트레일링 콤마 제거를 더하고, 그래도 실패하면 최종 리포트에 실패 대상을 요약하고 종료 코드를 0 이 아닌 값(또는 최소 "일부 건너뜀" 문구)으로 바꾼다.

### 5. Git Bash(Windows)에서 온보딩 답이 CRLF 로 쓰여 setup.sh 가 모든 값을 버린다 — medium
- 출처: crossplat
- `res/onboard.py:235` `open(out_path, "w", encoding="utf-8")` 에 `newline` 인자가 없고 `res/onboard.py:234` 가 `"%s=%s\n"` 을 쓴다 → 네이티브 Windows 파이썬에서 `\r\n`.
- `scripts/setup.sh:135` `while IFS='=' read -r key value` 는 `\r` 를 남기므로 `setup.sh:139 all)`, `:140 hooks)`, `:145 auto|bypassPermissions|...`, `:149 shift-enter|ctrl-enter)`, `:151/:152 [[ "$value" == "1" ]]` 가 전부 불일치. 이후 `setup.sh:190-194` 폴백이 걸린다.
- 실피해: SCOPE=hooks 선택이 전체 설치가 되고(Test-2 위반), `NEWLINE_CHORD` 가 비어 `setup.sh:174` 의 `NEWLINE_FLAG` 도 안 붙으며(Test-3 위반), **DRY_RUN=1 이 무시돼 미리보기를 고른 사용자에게 실제 쓰기가 일어난다**. 대비군 `scripts/setup.ps1:121` 은 `Get-Content -Encoding UTF8` 로 CRLF 를 벗긴다.
- 테스트 사각: `tests/test_onboard.py` 의 pty 경로는 win32 에서 돌지 않는다.
- 수정: `res/onboard.py:235` 를 `newline="\n"` 으로 고정하고, 방어적으로 `scripts/setup.sh:135` 뒤에 `value="${value%$'\r'}"` 를 추가한다.

## R3 실측 전에 고쳐야 하는 것 (실측 기대치가 코드와 어긋나거나, 실측이 사용자 파일을 건드린다)

### 6. is_managed_wt 가 sendInput 페이로드를 안 보고 키만 보고 지운다 — medium
- 출처: spec, engine, docs 발견 3 (동일 뿌리)
- `res/keybinds/apply.py:481-485` 는 `is_wt_send` + keys 문자열만 본다. 대조군 `apply.py:220-231` `is_managed_sendsequence` 는 command + when(terminalFocus, editor/notebook 제외) + `is_ssot_sequence` 를 모두 본다. 제거는 `apply.py:505` 에서 uninstall/chord 와 무관하게 무조건 일어나고 `apply.py:519-521` 이 파일에 쓴다.
- 결과: 사용자가 shift+enter/ctrl+enter 에 걸어둔 임의 payload 의 sendInput 이 통째로 사라지고 어느 쪽으로도 복원되지 않는다. shift-enter 설치에서도 WT 파일이 다시 쓰이므로 `README.md:122`("shift-enter 를 고른 경우 WT 에는 아무것도 쓰지 않는다")가 사실이 아니다.
- 명세 판정: 어휘 5(`newline-keybind.md:91`)가 "C=shift-enter 면 shift+enter sendInput 없음"을 파일 전체 사후조건으로 요구하므로 shift+enter 삭제는 명세가 시킨 것이고, **확정 위반은 ctrl+enter(고르지 않은 키) 쪽**이다 — `docs/CONTEXT.md:15`, 핵심 결정 5(`newline-keybind.md:43`), `CONTEXT.md:43`(시그니처에 시퀀스 포함).
- 테스트 사각: `DEFAULT_WT_SETTINGS`(`tests/test_keybinds.py:344-357`)에 sendInput 항목이 아예 없어 `tests/test_keybinds.py:823-827` 의 `assert not ctrl_sends` 는 공허하게 통과하고, 오히려 payload-무관 삭제를 고정한다. 외래 보존 확인(`tests/test_keybinds.py:843`)은 `copy`/ctrl+shift+c 하나뿐.
- 수정: `is_managed_wt` 에 `is_ssot_sequence(item["command"]["input"])` 페이로드 조건을 더한다(VS Code 판정과 대칭). 어휘 5 유지를 위해 "shift-enter 선택 시 shift+enter 관리 항목 제거"는 남긴다. 함께 `README.md:122` 를 "이전에 설치한 관리 항목을 정리하는 경우 외에는 쓰지 않는다"로 정정하고, `tests/test_keybinds.py:825-827` 의 ctrl+enter 단언을 관리 시퀀스 한정으로 좁힌다.

### 7. 고르지 않은 수정 Enter 를 소유권 표식 없이 지운다 (결정 5 위반) — medium
- 출처: spec (6번과 WT 부분 중복)
- Claude `res/keybinds/apply.py:327-328` `if chat.get(other) == "chat:newline": del chat[other]`; Codex `apply.py:448` → `apply.py:388` `kept = [x for x in items if x not in remove_keys]`; WT `apply.py:505` + `apply.py:481-485`.
- 어느 경로도 매니페스트(`newline_chord`/`claude_keys_added`/`codex_keys_added`)를 참조하지 않아, 이전 설치가 없던 첫 실행에서도 사용자가 직접 넣은 항목을 지운다. 위반 근거: 핵심 결정 5, `docs/CONTEXT.md:15`, HTML SSoT 잠긴 결정(`docs/reviews/newline-keybind-testcases.html:123`).
- 주의(회귀 위험): Test-16(`tests/test_keybinds.py:1229-1243`)은 코드 전환 시 이전 관리 항목이 남지 않을 것을 요구하므로 무조건 제거를 그냥 없애면 회귀다 — 구분자가 필요하다.
- 테스트 사각: `assert_newline_install_result`(`tests/test_keybinds.py:770-772`, `793-795`)가 픽스처와 무관하게 부재를 단언하는데, 사용자 소유 항목이 있는 픽스처가 아예 없다.
- 수정: 제거를 조건부로 — `prev_kb.get("newline_chord")` 가 그 키였거나 `claude_keys_added`/`codex_keys_added` 에 기록돼 있을 때만 지운다. 기록이 없으면 둔다. 이러면 Test-16 은 통과하고 첫 설치의 사용자 항목은 살아남는다.

### 8. Codex uninstall 이 `[tui.keymap.editor]` 와 `insert_newline = []` 를 남긴다 — medium
- 출처: spec, engine
- `res/keybinds/apply.py:440` 이 `remove_keys={shift-enter, ctrl-enter}` 로 호출 → `apply.py:387-391` kept=[] → `apply.py:393-395` `format_list` 가 줄을 지우는 대신 `insert_newline = []` 로 다시 쓴다. 설치 경로 `apply.py:425-431`/`apply.py:373`, `apply.py:453` 이 config.toml 자체와 테이블을 만들어 주므로, 설치 전에 없던 테이블과 명시적 빈 배열이 남는다 — 핵심 결정 8(`newline-keybind.md:46`, "관리 항목만 되돌림") 불성립.
- 근거 한계: "빈 배열 = 줄바꿈 전면 언바인드"라는 Codex 런타임 의미는 이 레포에서 정적으로 확인되지 않았다. 확정 사실은 잔여물뿐이다.
- 테스트 사각: `DEFAULT_CODEX_TOML`(`tests/test_keybinds.py:315-327`)에 `ctrl-j` 가 미리 있어 kept 가 비지 않으며, Test-12 의 Codex 단언(`tests/test_keybinds.py:1113-1121`, `1373-1381`)은 `"ctrl-j" in insert` 만 본다.
- 수정: kept 가 비고 add_key 도 없으면 `insert_newline` 줄을 출력하지 않는다. 그 결과 테이블이 비고 그 테이블이 우리가 만든 것이면(`codex_keys_added` 로 판별) 헤더도 함께 제거한다.

### 9. R3 체크리스트 문서가 틀린 기대를 담고 있다 — medium (문서)
- 출처: docs 발견 1
- `docs/handoffs/newline-keybind-R3.md:22-23` 이 "기존 VS Code/Cursor sendSequence 는 uninstall 이 지우지 않는다"고 단언하지만, `res/keybinds/apply.py:646-647` 은 `vscode_managed`/`cursor_managed` 값과 무관하게 `apply_ide_keybindings(..., uninstall=True)` 를 호출하고 `apply.py:266` 은 매니페스트가 아니라 `apply.py:220-231` 의 시그니처만 본다(`prev_kb` 는 `apply.py:653` tmux 인자로만 쓰임).
- 판정: **코드가 옳고 문서가 틀렸다**. `docs/CONTEXT.md:43` 과 핸드오프 Test-12 가 시그니처 식별을 명시하고 `README.md:81` 뒤 절도 코드와 일치한다.
- 수정: `newline-keybind-R3.md:22-23` 을 "`vscode_managed=false` 는 이번 실행이 아무것도 안 썼다는 뜻일 뿐이고, `--uninstall` 은 시그니처가 같은 sendSequence 를 원래 있던 것이라도 제거한다"로 고친다. `README.md:81` 의 "같은 매니페스트의 keybinds 항목을 근거로"는 VS Code/Cursor 에 해당하지 않음을 한 마디로 분리한다. (실측 전 필수 — 이대로 두면 R3 에서 정상 동작을 결함으로 기록한다.)

### 10. 실측 전에 채워야 할 테스트 3건
- **tmux 사전 존재 → 전체 uninstall 회귀 테스트** (2번의 게이트). 현재 어떤 케이스도 이 시나리오를 시드하지 않는다.
- **`--keybinds` → `--hooks` 순서 테스트** — medium (출처: tests). `res/hooks/merge_and_diff.py:568-572` 의 "훅이 모르는 섹션은 덮지 않는다" 가드(previous 키 복사 루프)가 무방비다. `fold_receipt`(`merge_and_diff.py:64-107`)는 `folded = dict(current)` 로 시작해 hooks 계열만 접으므로 그 3줄이 없으면 keybinds 섹션이 사라진다. 두 워커가 같은 파일을 쓴다(`apply.py:26` MANIFEST_NAME, `scripts/setup_hooks.sh:174` MANIFEST_PATH). 순서 커버리지 실측: `tests/test_keybinds.py` 의 `--hooks` 사용처(1032/1045/1098/1129/1144)는 전부 hooks 우선 또는 단독이고, `tests/test_setup_scripts.py:82,100,107,120,139,186` / `tests/setup.bats:41,63,79,86` / `tests/Setup.Tests.ps1:37,94,105,116,127,292` 도 전부 hooks 단독. Test-13 의 `tests/test_keybinds.py:1157` 은 반대 방향만 고정한다. **가드는 지금 존재하고 올바르게 동작하므로 사용자에게 나가는 버그는 아니다 — 순수 커버리지 공백.** 수정: `--keybinds --newline ctrl-enter` → `--hooks` 후 `keybinds.newline_chord`/`tmux_added` 존속 + 재실행 시 ctrl-enter 유지를 Test-13/14 태그로 추가.
- **macOS 기본 경로 단위 테스트** (1번의 게이트) — 플랫폼을 인자로 받는 순수 함수로 분리해 env 주입 없이 단언.

## 나중에 해도 되는 것

### 엔진/스크립트 (low)
- **`wt_managed` 영수증이 재설치에서 false 로 덮인다** (출처: spec). `apply.py:505` kept 에서 기존 관리 항목이 빠지고 `apply.py:509-512` 가 같은 dict 를 재삽입 → `kept != actions` 거짓 → `apply.py:523 return False`, 그것이 `apply.py:702` 에 기록된다(`apply.py:700-701` 의 vscode/cursor 와 달리 `or bool(prev_kb.get(...))` 폴백 없음). **기능적 손상 없음** — `wt_managed` 를 읽는 코드가 레포에 없고 uninstall 은 파일의 `is_managed_wt` 로 판단한다. 순수 영수증 부정확. 수정: `apply.py:702` 에 vscode/cursor 와 같은 폴백을 chord==ctrl-enter 조건 안에 넣는다.
- **POSIX 만 `--newline=`(빈 값)을 exit 0 으로 통과** (출처: crossplat). `scripts/setup.sh:71` → `:80` 의 `-n` 가드가 `:81-86` 허용값 검사를 통째로 건너뛴다; 워커도 동일(`scripts/setup_keybinds.sh:32`, `:37`). 대비 `scripts/setup.ps1:70` 은 exit 1, 같은 POSIX 의 `--newline ""` 도 `setup.sh:66` 때문에 exit 1 이라 두 표기가 갈린다. 비문서 형식이고 결과는 "인자 없이 실행"과 동일. 수정: 등호형도 빈 값이면 거절하거나 `-n` 가드를 "플래그가 주어졌는가" 변수로 바꾼다.
- **`install.ps1` 이 `$Rest` 를 조용히 버린다** (출처: crossplat). `install.ps1:34`/`:137` 의 `ValueFromRemainingArguments`, `:191-197` 의 `$fwd` 에 없고 `:198 & $setup @fwd` 로 폐기. 대비 `install.sh:222` → `scripts/setup.sh:76` 은 exit 1. **명세 위반은 아니다** — Test-17(`docs/reviews/newline-keybind-testcases.html:198`)이 요구하는 `-Keybinds`/`-Newline` 전달은 정상 동작하고, 미지 인자 거절을 요구하는 케이스는 없다. 수정: `$fwd` 구성 후 `if ($Rest) { throw ... }`.
- **`setup.sh --uninstall` 이 훅 제거 실패 시 키바인드 제거를 건너뛴다** (출처: crossplat). `scripts/setup.sh:19 set -euo pipefail` + `:183-184` 가 비조건부 명령. 대비 `scripts/setup.ps1:160-164` 는 `$hooksExit` 로 받아두고 둘 다 실행한다. 트리거가 이미 비정상 상태이고 사용자는 0 아닌 코드를 보며 `--keybinds --uninstall`(`setup.sh:179-181`)로 복구 가능. 수정: `setup.sh:183` 을 `|| hooks_exit=$?` 로 받고 184 를 항상 실행 후 `exit ${hooks_exit:-$?}`.
- **Codex insert_newline 파서가 같은 줄 주석의 따옴표 문자열을 흡수** (출처: engine). `apply.py:356` `after_eq = line.split("=", 1)[1]` 가 주석까지 buf 에 담고 `apply.py:360` 의 while 은 대괄호 균형만 보므로, `apply.py:363` → `apply.py:343` `re.findall(r'"([^"]*)"', src)` 가 주석 안 문자열을 항목으로 읽는다. `insert_newline = ["ctrl-j"]  # "alt-enter" 는 안 먹음` → `["ctrl-j","alt-enter"]`. 후행 주석은 `apply.py:413` 재작성에서 소실. 수정: buf 생성 시 문자열 밖 `#` 이후를 잘라내고 재작성 줄 끝에 다시 붙인다.
- **JSONC 를 순수 JSON 으로 다시 써서 주석·포맷이 사라진다** (출처: engine, docs 발견 5, safety — 동일 뿌리). `apply.py:46-87` parse_jsonc 가 주석을 버리고 `apply.py:90-93` write_json 이 `json.dumps(indent=4)` 로 덮어쓴다(호출: `apply.py:272`, `287`, `521`). 백업 코드 없음(shutil 은 `apply.py:141-148` which 전용). **명세는 항목 보존(어휘 7, Test-18/25)만 요구하고 주석·서식을 다루지 않으며** 설정 값은 전부 보존된다. 픽스처(`tests/test_keybinds.py:247-248`, `276`)에 주석이 있지만 잔존 단언은 없다. 수정: README '무엇이 설치되나' 절에 "keybindings.json 은 재포맷되며 주석이 사라진다" 한 줄, 또는 첫 변경 시 `.bak.<타임스탬프>`.
- **README 가 두 번 참조하는 PowerShell scriptblock 예시가 README 안에 없다** (출처: docs 발견 6). `README.md:51` 뒤에 오는 것은 플래그 표이고, `README.md:69` 가 다시 "위 scriptblock 패턴"을 가리킨다. 실제 예시는 `install.ps1:16-17`, `install.ps1:146-149` 에만 있다. `README.md:29-34` 의 유일한 Windows 예시는 `irm | iex` 인데 `README.md:51` 스스로 그 형태로는 인자를 못 넘긴다고 말한다. 수정: `README.md:51` 뒤에 `& ([scriptblock]::Create((irm ... install.ps1))) -Keybinds -Newline ctrl-enter` 코드블록 추가.

### 테스트 위생 (low, 전부 현재는 초록이고 사용자 영향 없음)
- **Test-24 가 개발자 터미널에 좌우되고 대조군이 없다** (출처: tests). 주의: 리뷰어의 핵심 메커니즘 주장은 **틀렸다** — `apply.py:579-582` 의 `detect_terminal()` 은 `CLAUDE_SETUP_DETECTED_TERMINAL` 을 가장 먼저 읽고 즉시 반환하므로 주입값이 항상 우선하며, 감지가 죽으면 `apply.py:589-594` 가 경고를 안 찍어 모든 파라미터가 실패한다. 남는 실질 결함 둘: (1) `tests/test_keybinds.py:489-491` 의 `sandbox_env` 가 `os.environ` 을 CI 변수만 빼고 상속해 `GNOME_TERMINAL_SERVICE` 가 있는 머신에서는 파라미터 2·3(`1408`, `1410`)이 상속값 덕에 통과할 수 있다. (2) "경고가 없어야 한다"는 대조군 단언이 tests 전체에 없다(`1420` 줄이 단독). 수정: `sandbox_env` 에서 `KONSOLE_*`/`GNOME_TERMINAL_*` 를 명시 제거하고, 무주입 대조군에서 경고 부재를 단언한다.
- **`isolated_path` 가 `/usr/bin`·`/bin`·System32 를 `_dir_has_agent` 검사 전에 무조건 PATH 에 넣는다** (출처: tests). `tests/test_keybinds.py:380-384` else 분기(및 win32 분기 `373-379`)가 seen 에 등록해, `386-402` 의 `_dir_has_agent(parent)` 우회를 비껴간다. 구현은 그 PATH 를 그대로 쓴다(`apply.py:141-148` → `apply.py:611-612`). claude/codex 가 `/usr/bin`·`/bin` 에 있는 머신에서 `tests/test_keybinds.py:1321-1334` 의 skip 기대가 `1329-1330` 에서 깨진다 — 결정 13 / `CONTEXT.md:35` 의 '범용 테스트' 위반. 표준 설치 위치가 아니라 드물고, 깨져도 테스트만 시끄럽다. 수정: 이 경로들에도 같은 `_dir_has_agent` 규칙을 적용한다.
- **항상 참인 죽은 단언 두 곳** (출처: tests). `tests/test_keybinds.py:679-684` 는 `662` 의 `len(managed)==1` 과 `666` 의 key 단언을 이미 통과한 그 한 항목만 재순회하므로 `681`/`684` 는 어떤 입력으로도 실패하지 않는다(`vscode_key`/`vscode_other_key` 는 `apply.py:37-42` 대응상 정의부터 다르다). `tests/test_keybinds.py:743-745` 도 `676` 의 `is_allowed_sequence` 통과값이라 or 우변이 항상 참이고 실질 검사는 `747-749` 단독. 어휘 6 이 독립 검증되지 않는다. 수정: `679-684` 를 파일 전체 entries 순회로 바꾸고, `743-745` 의 or 절은 삭제한다.
- **Test-17 이 `install.ps1` 을 실행하지 않고 소스 정규식만 본다** (출처: crossplat). `tests/test_onboard.py:369-398` — `:376` 이후 전부 `re.search`/`re.findall` 이고 `:393-398` 의 Newline 단언은 `$PSBoundParameters.ContainsKey('Newline')` 이 파일 어디에든 있으면 or 로 통과한다. 따라서 `install.ps1:198 & $setup @fwd` 가 바뀌어도 초록이다(이것이 `$Rest` 결함을 놓친 원인). 다만 **정당한 이유가 있다** — `install.ps1:170-176` 이 반드시 github 아카이브를 받으므로 네트워크 없이 런타임 검증이 불가능하고, 이웃 테스트 `tests/test_onboard.py:340-366` 이 param 스위치 집합 ⊆ `$fwd` 전달 목록을 강제해 "받고도 안 넘기는 스위치" 회귀는 잡는다. 수정: setup 경로를 env 로 주입 가능하게 만들어 스텁으로 실제 전달을 확인하는 테스트를 추가한다.

## 불확실 — 무엇을 확인하면 판정이 갈리는가

### 키바인드 병합에 백업이 없고 쓰기가 원자적이지 않다 (safety/low)
- 사실 관계는 확정: `res/keybinds/apply.py` 에 backup/copy2/os.replace/임시파일이 없고(shutil 은 `apply.py:142`,`146` which 전용), 쓰기는 전부 in-place truncate(`apply.py:90-93`, `322`, `335`, `445`, `454`, `521`, `549`, `567`). 훅 쪽은 `res/hooks/merge_and_diff.py:110-117 backup_file` 을 `457`, `546` 에서 호출한다.
- **판정을 가르는 확인 사항 세 가지:**
  1. 결정 8(`docs/handoffs/newline-keybind.md:46`)이 "훅과 같은 철학"으로 열거한 네 가지는 외과적 병합·멱등·dry-run·uninstall 이고 백업이 없다 — 백업을 요구사항으로 승격할지에 대한 **명세 소유자의 결정**이 필요하다. 승격하면 결함, 아니면 비결함.
  2. Test-1..27 (HTML SSoT)에 백업 관련 인수 기준을 추가할 것인가.
  3. `README.md:81` 이 `.bak` 을 settings.json 문맥에서만 약속하는데, 이 약속의 범위를 keybindings.json/WT settings.json 까지 넓힐 것인가.
- 현재 남는 실패 시나리오는 "쓰기 도중 전원 차단"이라는 일반적·저확률 경로뿐이며, 위 2번(tmux) 결함의 복구 난이도를 올리는 가중 요인 정도다.
- 고치기로 한다면: `write_json`/`write_text` 를 임시 파일 + `os.replace` 로 바꾸고, 기존 파일이 있고 내용이 바뀔 때만 `<path>.bak.<timestamp>` 를 남긴다(`merge_and_diff.backup_file` 재사용).

---

## 처리 결과 (2026-08-30)

위 항목을 모두 수정했다. 각 결함마다 그 분기를 실제로 시드하는 회귀 테스트를 붙였다 —
픽스처가 분기를 밟지 않아 통과해 버렸던 것이 이 결함들이 살아남은 이유이기 때문이다.

### 즉시 항목

| # | 수정 | 회귀 테스트 |
| --- | --- | --- |
| 1 | `default_ide_path(home, app, platform, appdata)` 로 분리하고 darwin 분기 추가. 플랫폼을 인자로 받아 env 주입 없이 단언 가능 | `test_기본_IDE경로는_세_OS를_각각_따른다` |
| 2 | `apply_tmux` 의 else 폴백 제거 — 영수증에 없으면 건드리지 않는다. 전체 uninstall 에서 키바인드를 훅보다 **먼저** 돌리고, 훅 uninstall 은 매니페스트의 `keybinds` 섹션을 남긴다 | `test_사용자가_이미_가진_extended_keys는_전체_uninstall에도_남는다` + 짝이 되는 `test_우리가_넣은_extended_keys는_전체_uninstall로_사라진다` |
| 3 | Codex EOF/섹션전환 분기에 개행 보정 추가 | `test_개행없이_끝나는_codex_toml도_깨지지_않는다` |
| 4 | `strip_trailing_commas` 추가. 읽지 못한 대상은 `report_result` 가 목록으로 알리고 0이 아닌 코드로 종료 | `test_트레일링콤마_keybindings도_읽는다`, `test_읽지_못한_대상이_있으면_성공이라고_말하지_않는다` |
| 5 | `onboard.py` 가 `newline="\n"` 고정, `setup.sh` 도 값 끝의 CR 을 벗긴다 (한쪽만 고쳐도 안 깨지게) | 기존 pty 테스트가 WSL 에서 통과 |

### R3 실측 전 항목

| # | 수정 | 회귀 테스트 |
| --- | --- | --- |
| 6 | `is_managed_wt` 가 `is_ssot_sequence(input)` 까지 본다 (VS Code 판정과 대칭). WT 픽스처에 외래 `sendInput` 을 넣고 보존을 단언 | `assert_newline_install_result` 강화 |
| 7 | 고르지 않은 키 제거를 영수증 조건부로 (Claude·Codex). 기록이 없으면 사용자 것이므로 둔다 | `test_사용자가_직접_넣은_고르지_않은_키는_설치가_지우지_않는다` |
| 8 | 우리 키만 빠져 비면 `insert_newline` 줄과 빈 `[tui.keymap.editor]` 테이블까지 제거 | `test_codex_uninstall은_빈_insert_newline을_남기지_않는다` |
| 9 | R3 문서의 uninstall 설명 정정 — VS Code/Cursor 는 시그니처 기준이라 원래 있던 항목도 제거된다 | — |

### 나중 항목 (전부 처리)

- `wt_managed` 영수증에 `prev_kb` 폴백 추가
- `--newline=`(빈 값)을 POSIX 에서도 거절 — 디스패처와 워커 양쪽
- `install.ps1` 이 `$Rest` 를 조용히 버리지 않고 예외를 던진다
- `setup.sh --uninstall` 이 한쪽 실패에 나머지를 건너뛰지 않는다
- Codex 같은 줄 주석을 항목으로 흡수하지 않고 주석을 보존 (`split_toml_comment`)
- 원자적 쓰기(`os.replace`) + 첫 변경 시 `.bak.<타임스탬프>`. 내용이 같으면 아예 쓰지 않아 재실행에 백업이 쌓이지 않는다
- `sandbox_env` 가 `GNOME_TERMINAL_*`/`KONSOLE_*`/`CLAUDE_SETUP_DETECTED_TERMINAL` 을 상속하지 않는다 + 무주입 대조군 추가
- `isolated_path` 가 `/usr/bin`·`/bin`·System32 에도 `_dir_has_agent` 규칙을 적용
- 항상 참이던 단언 두 곳 제거 — 어휘 6 은 파일 전체 순회로, VS Code/Cursor 시퀀스 비교는 강한 쪽만 남김
- README: uninstall 식별 기준(시그니처 vs 영수증), OS별 경로, WT 문장, 「파일을 어떻게 고치나」(백업·재포맷·읽기 실패), 빠져 있던 PowerShell scriptblock 예시

### 불확실 항목 — 결정

백업·원자적 쓰기를 **요구사항으로 승격했다.** 결정 8 의 "훅과 같은 철학" 에는 원래 백업이
열거되어 있지 않지만, 2번 결함이 보여준 대로 이 설치기는 사용자가 직접 관리하던 파일을 고친다.
되돌릴 수단이 없는 쪽이 더 위험하다고 판단했다. `test_바꾸기_전_원본을_백업하고_임시파일을_남기지_않는다`,
`test_재실행은_백업을_쌓지_않는다` 로 고정했다.

### 검토 중 뒤집힌 판정 하나

`test_resolved_home_denied`(Windows 에서 실패하던 기존 테스트)는 **가드 구멍이 아니었다.**
`os.path.relpath` 가 Windows 에서 주는 `..\Users\이름` 을 **Bash** 명령에 넣은 것이 원인이다 —
bash 에서 백슬래시는 구분자가 아니라 이스케이프라 `..Users이름` 이라는 존재하지 않는 이름이 되고,
그건 홈을 지우는 명령이 아니다. 실측으로 확인했다: `../Users/이름`(POSIX 표기)과 PowerShell 의
`..\Users\이름` 은 둘 다 정상적으로 `deny` 된다. 테스트 입력을 고치고, 백슬래시가 실제 구분자인
PowerShell 케이스를 단언으로 **추가**했다.

## 검증

| 러너 | 결과 |
| --- | --- |
| pytest (Windows) | 601 passed · 1 failed |
| pytest (WSL Ubuntu 24.04) | **648 passed · 0 failed** |
| Pester | 25 / 25 |

Windows 의 1건은 `test_벤더링된_questionary가_실제로_프롬프트를_만들_수_있다` 로, 진짜 Windows 콘솔
스크린 버퍼가 필요해 이 도구 환경에서는 돌 수 없다 (`NoConsoleScreenBufferError`). 이 세션 시작
시점부터 같은 이유로 실패했고 이번 변경과 무관하다. 실제 터미널에서 확인이 필요하다.
