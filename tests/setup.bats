#!/usr/bin/env bats
# setup.sh 오케스트레이션 계층 테스트 (bats-core).
# 외부 라이브러리(bats-assert 등) 없이 순수 bats 만으로 동작하도록 작성했다.
#   실행: bats tests/setup.bats

setup() {
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SANDBOX="$(mktemp -d)"
    export HOME="$SANDBOX"          # 실제 ~/.claude 를 건드리지 않도록 격리

    # 테스트가 스텁 실행 파일을 둘 자리를 PATH 앞에 둔다.
    mkdir -p "$SANDBOX/bin"
    export PATH="$SANDBOX/bin:$PATH"
}

teardown() {
    [ -n "${SANDBOX:-}" ] && rm -rf "$SANDBOX"
}

@test "setup.sh --help exits 0 and prints usage" {
    run bash "$REPO_ROOT/scripts/setup.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}

@test "setup.sh -h prints usage" {
    run bash "$REPO_ROOT/scripts/setup.sh" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"--uninstall"* ]]
}

@test "setup.sh rejects unknown option with exit 1" {
    run bash "$REPO_ROOT/scripts/setup.sh" --bogus
    [ "$status" -eq 1 ]
    [[ "$output" == *"Unknown option"* ]]
}

# doctor 는 jarvis 로 옮겨 갔다. --doctor 는 안내만 내고 홈을 그대로 둔 채 exit 1 로 끝난다.
# install.sh 는 레포를 받기 전에 멈추므로 네트워크를 타지 않는다(없는 레포를 가리켜 둔다).
@test "setup.sh and install.sh --doctor point to jarvis and write nothing (covers: AI-68)" {
    pointer="Doctor is now run by jarvis; ai-setup no longer runs it. From a jarvis checkout run: python3 -m jarvis module doctor status --json."
    mkdir -p "$HOME/.agents/skills/stray"
    printf '{"version": 3, "skills": {}}\n' > "$HOME/.agents/.skill-lock.json"
    before="$(find "$HOME" | sort)"
    for args in "--doctor" "--doctor --uninstall" "--help --doctor"; do
        # shellcheck disable=SC2086
        run bash "$REPO_ROOT/scripts/setup.sh" $args
        [ "$status" -eq 1 ] || { echo "setup.sh $args -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "setup.sh $args: $output"; return 1; }
        [[ "$output" != *"stray"* ]] || { echo "setup.sh $args ran a report: $output"; return 1; }
        # shellcheck disable=SC2086
        CLAUDE_SETUP_REPO="thsvkd/does-not-exist" run sh "$REPO_ROOT/install.sh" $args
        [ "$status" -eq 1 ] || { echo "install.sh $args -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "install.sh $args: $output"; return 1; }
        [[ "$output" != *"downloading"* ]]
    done
    [ "$(find "$HOME" | sort)" = "$before" ]
}

@test "update-ai.sh passes options through to the Python implementation" {
    run bash "$REPO_ROOT/scripts/update-ai.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"--allow-interrupt"* ]]
    run bash "$REPO_ROOT/scripts/update-ai.sh" --only nope
    [ "$status" -eq 2 ]
    [[ "$output" == *"unknown target"* ]]
}

@test "update-ai.sh --check reads versions without updating (covers: AI-7)" {
    printf '#!/bin/sh\necho "agy $*" >> "%s/calls.log"\necho "agy 1.2.3"\n' "$SANDBOX" > "$SANDBOX/bin/agy"
    chmod +x "$SANDBOX/bin/agy"
    run bash "$REPO_ROOT/scripts/update-ai.sh" --check --only agy
    [ "$status" -eq 0 ]
    [[ "$output" == *"1.2.3"* ]]
    [ "$(cat "$SANDBOX/calls.log")" = "agy --version" ]
}

# 훅은 jarvis 가 맡는다. --hooks 는 안내만 내고 홈을 그대로 둔 채 exit 1 로 끝난다. 영수증의 훅 기록도 그대로다.
# install.sh 는 레포를 받기 전에 멈추므로 네트워크를 타지 않는다(없는 레포를 가리켜 둔다).
@test "setup.sh and install.sh --hooks point to jarvis and write nothing (covers: AI-69)" {
    pointer="Hooks are now managed by jarvis; ai-setup no longer installs or removes them. From a jarvis checkout run: python3 -m jarvis module hooks plan --json (uninstall: module hooks uninstall --json --dry-run)."
    mkdir -p "$HOME/.claude/hooks"
    printf '# installed hook\n' > "$HOME/.claude/hooks/danger_guard.py"
    printf '{"hook_files": ["danger_guard.py"], "added_allow": ["Bash"]}\n' > "$HOME/.claude/.claude-code-setup.json"
    before="$(find "$HOME" | sort; cat "$HOME/.claude/.claude-code-setup.json" "$HOME/.claude/hooks/danger_guard.py")"
    for args in "--hooks" "--hooks --uninstall" "--hooks --dry-run" "--keybinds --hooks" "--help --hooks"; do
        # shellcheck disable=SC2086
        run bash "$REPO_ROOT/scripts/setup.sh" $args
        [ "$status" -eq 1 ] || { echo "setup.sh $args -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "setup.sh $args: $output"; return 1; }
        # shellcheck disable=SC2086
        CLAUDE_SETUP_REPO="thsvkd/does-not-exist" run sh "$REPO_ROOT/install.sh" $args
        [ "$status" -eq 1 ] || { echo "install.sh $args -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "install.sh $args: $output"; return 1; }
        [[ "$output" != *"downloading"* ]]
    done
    # 단계식 설치기는 stages.py 가 계획 전에 같은 안내로 막는다.
    for stages in "hooks" "newline,hooks" "all,hooks"; do
        run bash "$REPO_ROOT/scripts/setup.sh" --stages "$stages"
        [ "$status" -eq 1 ] || { echo "--stages $stages -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "--stages $stages: $output"; return 1; }
    done
    [ "$(find "$HOME" | sort; cat "$HOME/.claude/.claude-code-setup.json" "$HOME/.claude/hooks/danger_guard.py")" = "$before" ]
}

@test "install.sh --help exits 0 without network" {
    run sh "$REPO_ROOT/install.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"bootstrap"* ]]
}

# Orca 는 jarvis 가 관리한다. 예전 진입점은 안내만 내고 홈을 그대로 둔 채 exit 1 로 끝난다.
# install.sh 는 레포를 받기 전에 멈추므로 네트워크를 타지 않는다(없는 레포를 가리켜 둔다).
@test "setup.sh and install.sh Orca options point to jarvis and change nothing (covers: AI-66)" {
    pointer="Orca is now managed by jarvis; ai-setup no longer installs, updates or removes it. From a jarvis checkout run: python3 -m jarvis module orca plan --json (uninstall: module orca uninstall --json --dry-run)."
    before="$(find "$HOME" | sort)"
    for args in "--tools orca" "--tools=orca" "--tools orca --uninstall" "--orca-desktop" "--stages tools --orca-desktop" "--hooks --tools orca" "--help --tools orca"; do
        # shellcheck disable=SC2086
        run bash "$REPO_ROOT/scripts/setup.sh" $args
        [ "$status" -eq 1 ] || { echo "setup.sh $args -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "setup.sh $args: $output"; return 1; }
        # shellcheck disable=SC2086
        CLAUDE_SETUP_REPO="thsvkd/does-not-exist" run sh "$REPO_ROOT/install.sh" $args
        [ "$status" -eq 1 ] || { echo "install.sh $args -> $status"; return 1; }
        [[ "$output" == *"$pointer"* ]] || { echo "install.sh $args: $output"; return 1; }
        [[ "$output" != *"downloading"* ]]
    done
    [ "$(find "$HOME" | sort)" = "$before" ]
}

# 아래는 dry-run 이 아닌 '실제 설치' 경로다. bash 3.2 (macOS 기본) 는 set -u 에서 빈 배열의
# "${arr[@]}" 확장을 unbound variable 로 취급하는데, --dry-run 일 때는 배열이 비어있지 않아
# 그 버그가 드러나지 않는다. 실제 설치를 밟는 테스트가 없으면 macOS 전체가 깨진 채로 통과한다.

@test "setup.sh with no args and no TTY installs nothing" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"No terminal, so nothing was installed."* ]]
    [ ! -e "$HOME/.claude/hooks/danger_guard.py" ]
    [ ! -e "$SANDBOX/AGENTS.md" ]
}

@test "setup.sh installs nothing when the onboarding breaks mid-prompt" {
    # 물을 수 없으면(2) 아무것도 설치하지 않는다. 프롬프트가 깨지거나(1) traceback 으로 죽으면
    # 사용자는 고르던 중이었으므로, 고르지도 않은 기본값으로 설치하면 안 된다.
    mkdir -p "$SANDBOX/repo"
    cp -R "$REPO_ROOT/scripts" "$REPO_ROOT/res" "$SANDBOX/repo/"
    printf 'import sys\nsys.exit(1)\n' > "$SANDBOX/repo/res/onboard.py"
    cd "$SANDBOX"
    run bash "$SANDBOX/repo/scripts/setup.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Aborting installation"* ]]
    [ ! -e "$HOME/.claude/settings.json" ]
    [ ! -e "$HOME/.claude/hooks/danger_guard.py" ]
    [ ! -e "$SANDBOX/AGENTS.md" ]
}

# 전체 --uninstall 은 훅을 지우지 않는다. jarvis 훅 모듈이 훅 파일과 영수증의 훅 기록(hook_files·권한 기록)을
# 이어 읽고, jarvis 의 Orca 모듈이 Orca 기록을 읽는다. 영수증을 다시 쓰는 워커가 그 키를 지우면 안 된다.
@test "setup.sh --uninstall keeps the hooks, their receipt records and the Orca records for jarvis (covers: AI-67, AI-69)" {
    _keybind_sandbox
    bash "$REPO_ROOT/scripts/setup.sh" --keybinds
    mkdir -p "$HOME/.claude/hooks/shims"
    printf '# installed hook\n' > "$HOME/.claude/hooks/danger_guard.py"
    printf '#!/bin/sh\n' > "$HOME/.claude/hooks/shims/rm"
    printf '{"permissions": {"allow": ["Bash"], "defaultMode": "auto"}, "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 danger_guard.py"}]}]}}\n' > "$HOME/.claude/settings.json"
    cp "$HOME/.claude/settings.json" "$SANDBOX/settings.before"
    receipt="$HOME/.claude/.claude-code-setup.json"
    kept='{"hook_files": ["danger_guard.py", "shims/rm"], "added_allow": ["Bash"], "default_mode_before": null, "default_mode_changed": true, "hooks": true, "tool_installs": {"orca": {"method": "deb", "version": "1.4.242", "skills_added": ["orca-cli"]}, "orca_server": {"service_manager": "systemd-user", "state": "configured"}}, "tool_attempts": {"orca": {"state": "done"}}}'
    python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); assert d.get("keybinds"), d; d.update(json.loads(sys.argv[2])); json.dump(d,open(p,"w"))' "$receipt" "$kept"
    run bash "$REPO_ROOT/scripts/setup.sh" --uninstall
    [ "$status" -eq 0 ]
    [ "$(cat "$HOME/.claude/hooks/danger_guard.py")" = "# installed hook" ]
    [ -f "$HOME/.claude/hooks/shims/rm" ]
    cmp "$SANDBOX/settings.before" "$HOME/.claude/settings.json"
    # keybinds 기록이 빠졌으니 워커가 영수증을 실제로 다시 썼다.
    run python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); k=json.loads(sys.argv[2]); print(all(d.get(x)==v for x,v in k.items()), "keybinds" in d)' "$receipt" "$kept"
    [ "$output" = "True False" ]
}

# 줄바꿈 키바인드 디스패처. 실제 ~/.config/Code 를 건드리지 않도록 경로를 샌드박스로 돌린다.

_keybind_sandbox() {
    mkdir -p "$SANDBOX/vscode" "$SANDBOX/cursor" "$SANDBOX/wt"
    printf '[]\n' > "$SANDBOX/vscode/keybindings.json"
    printf '[]\n' > "$SANDBOX/cursor/keybindings.json"
    printf '{}\n' > "$SANDBOX/wt/settings.json"
    export CLAUDE_SETUP_VSCODE_KEYBINDINGS="$SANDBOX/vscode/keybindings.json"
    export CLAUDE_SETUP_CURSOR_KEYBINDINGS="$SANDBOX/cursor/keybindings.json"
    export CLAUDE_SETUP_WT_SETTINGS="$SANDBOX/wt/settings.json"
}

@test "setup.sh keeps a failing worker's exit code through the output formatter" {
    # 워커 출력은 ui_format 파이프를 지난다. pipefail 이 빠지면 실패가 0 으로 바뀌어 설치가
    # 성공한 것처럼 끝난다. 파싱할 수 없는 settings.json 은 mod 워커가 멈추는 실제 실패 경로다.
    mkdir -p "$HOME/.claude"
    printf '{broken' > "$HOME/.claude/settings.json"
    run bash "$REPO_ROOT/scripts/setup.sh" --mods
    [ "$status" -ne 0 ]
    [[ "$output" == *"failed (exit $status)"* ]]
    [ "$(cat "$HOME/.claude/settings.json")" = "{broken" ]
}

@test "setup.sh --help shows --keybinds and --newline (covers: Test-15)" {
    run bash "$REPO_ROOT/scripts/setup.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"--keybinds"* ]]
    [[ "$output" == *"--newline"* ]]
}

@test "setup.sh --keybinds --dry-run writes nothing and shows target paths (covers: Test-10)" {
    _keybind_sandbox
    run bash "$REPO_ROOT/scripts/setup.sh" --keybinds --dry-run
    [ "$status" -eq 0 ]
    [ ! -e "$HOME/.claude/settings.json" ]
    [[ "$output" == *"keybindings.json"* ]]
}

@test "setup.sh --keybinds --newline foo exits 1 and leaves files unchanged (covers: Test-8)" {
    _keybind_sandbox
    before="$(cat "$CLAUDE_SETUP_VSCODE_KEYBINDINGS")"
    run bash "$REPO_ROOT/scripts/setup.sh" --keybinds --newline foo
    [ "$status" -eq 1 ]
    [ "$(cat "$CLAUDE_SETUP_VSCODE_KEYBINDINGS")" = "$before" ]
    [[ "$output" != *"Unknown option"* ]]
}

@test "setup.sh --keybinds does not install hooks or AGENTS.md (covers: Test-6)" {
    _keybind_sandbox
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup.sh" --keybinds
    [ "$status" -eq 0 ]
    [ ! -f "$HOME/.claude/hooks/danger_guard.py" ]
    [ ! -f "$SANDBOX/AGENTS.md" ]
    [ -f "$HOME/.claude/.claude-code-setup.json" ]
}

# 프로젝트 지침 설치는 고른 하네스에 따라 산출물이 달라진다. Codex/Grok/OpenCode 는
# 루트 AGENTS.md 를 직접 읽고, Claude Code 는 CLAUDE.md 를 통해서만 읽는다.
# Windows 쪽 같은 계약은 tests/Setup.Tests.ps1 의 "project instructions harness selection" 에 있다.

@test "setup_agentsmd.sh with no args installs every harness artifact" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh"
    [ "$status" -eq 0 ]
    [ -f "$SANDBOX/AGENTS.md" ]
    [ -f "$SANDBOX/CLAUDE.md" ]
}

@test "setup_agentsmd.sh --harness codex leaves CLAUDE.md alone" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness codex
    [ "$status" -eq 0 ]
    [ -f "$SANDBOX/AGENTS.md" ]
    [ ! -f "$SANDBOX/CLAUDE.md" ]
}

@test "setup_agentsmd.sh --harness agy,gemini,copilot writes AGENTS.md" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness agy,gemini,copilot
    [ "$status" -eq 0 ]
    [ -f "$SANDBOX/AGENTS.md" ]
    [ ! -f "$SANDBOX/CLAUDE.md" ]
}

@test "setup_agentsmd.sh --harness grok,opencode leaves CLAUDE.md alone" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness grok,opencode
    [ "$status" -eq 0 ]
    [ -f "$SANDBOX/AGENTS.md" ]
    [ ! -f "$SANDBOX/CLAUDE.md" ]
}

@test "setup_agentsmd.sh --harness claude,codex installs both artifacts" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness claude,codex
    [ "$status" -eq 0 ]
    [ -f "$SANDBOX/AGENTS.md" ]
    [ -f "$SANDBOX/CLAUDE.md" ]
    grep -q "@AGENTS.md" "$SANDBOX/CLAUDE.md"
}

@test "setup_agentsmd.sh rejects an unknown harness without writing anything" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness cursor
    [ "$status" -eq 1 ]
    [ ! -f "$SANDBOX/AGENTS.md" ]
    [ ! -f "$SANDBOX/CLAUDE.md" ]
}

@test "setup_agentsmd.sh --dry-run writes nothing whichever harness is chosen" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness claude,codex --dry-run
    [ "$status" -eq 0 ]
    [ ! -f "$SANDBOX/AGENTS.md" ]
    [ ! -f "$SANDBOX/CLAUDE.md" ]
}

@test "setup_agentsmd.sh keeps an existing CLAUDE.md without --force" {
    cd "$SANDBOX"
    printf 'user content\n' > "$SANDBOX/CLAUDE.md"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness claude
    [ "$status" -eq 0 ]
    grep -q "user content" "$SANDBOX/CLAUDE.md"
}

@test "setup_agentsmd.sh warns when an existing CLAUDE.md does not import AGENTS.md" {
    # 건너뛰기 자체는 옳다 — 사용자 콘텐츠다. 다만 그 파일이 AGENTS.md 를 불러오지
    # 않으면 Claude Code 는 방금 설치한 지침을 영영 읽지 않는다.
    cd "$SANDBOX"
    printf 'project rules only\n' > "$SANDBOX/CLAUDE.md"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness claude
    [ "$status" -eq 0 ]
    [[ "$output" == *"@AGENTS.md"* ]]
    [[ "$output" == *"will not read"* ]]
    grep -q "project rules only" "$SANDBOX/CLAUDE.md"
}

@test "setup_agentsmd.sh stays quiet when the existing CLAUDE.md already imports it" {
    cd "$SANDBOX"
    printf '@AGENTS.md\n\n## project specific\n' > "$SANDBOX/CLAUDE.md"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness claude
    [ "$status" -eq 0 ]
    [[ "$output" != *"will not read"* ]]
}

@test "setup_agentsmd.sh --force backs CLAUDE.md up before overwriting it" {
    cd "$SANDBOX"
    printf 'user content\n' > "$SANDBOX/CLAUDE.md"
    run bash "$REPO_ROOT/scripts/setup_agentsmd.sh" --harness claude --force
    [ "$status" -eq 0 ]
    grep -q "@AGENTS.md" "$SANDBOX/CLAUDE.md"
    ls "$SANDBOX"/CLAUDE.md.bak.* >/dev/null
    grep -q "user content" "$SANDBOX"/CLAUDE.md.bak.*
}

@test "setup.sh --agentsmd --harness codex passes the selection through" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup.sh" --agentsmd --harness codex
    [ "$status" -eq 0 ]
    [ -f "$SANDBOX/AGENTS.md" ]
    [ ! -f "$SANDBOX/CLAUDE.md" ]
    [ ! -f "$HOME/.claude/hooks/danger_guard.py" ]
}

# Python 이 없을 때는 설치하지 않고, 이 환경에서 Python 3 을 설치하는 명령만 안내한다.
# PATH 를 스텁 디렉터리 하나로 좁혀 어떤 패키지 관리자가 보이는지를 고정한다.
python_hint_with() {
    local stub="$SANDBOX/hintbin"
    mkdir -p "$stub"
    printf '#!/bin/sh\necho %s\n' "$1" > "$stub/uname"
    chmod +x "$stub/uname"
    shift
    local pm
    for pm in "$@"; do
        printf '#!/bin/sh\nexit 0\n' > "$stub/$pm"
        chmod +x "$stub/$pm"
    done
    source "$REPO_ROOT/scripts/lib/setup_common.sh"
    PATH="$stub" print_python_install_hint 2>&1
}

@test "python install hint suggests brew on macOS" {
    run python_hint_with Darwin
    [[ "$output" == *"brew install python"* ]]
}

@test "python install hint suggests apt-get on Debian-family Linux" {
    run python_hint_with Linux apt-get
    [[ "$output" == *"sudo apt-get install -y python3"* ]]
}

@test "python install hint suggests dnf on Fedora-family Linux" {
    run python_hint_with Linux dnf
    [[ "$output" == *"sudo dnf install -y python3"* ]]
}

@test "python install hint falls back to a generic message without a known package manager" {
    run python_hint_with Linux
    [[ "$output" == *"python.org"* ]]
}
