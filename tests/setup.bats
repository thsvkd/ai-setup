#!/usr/bin/env bats
# setup.sh / setup_hooks.sh 오케스트레이션 계층 테스트 (bats-core).
# 외부 라이브러리(bats-assert 등) 없이 순수 bats 만으로 동작하도록 작성했다.
#   실행: bats tests/setup.bats

setup() {
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SANDBOX="$(mktemp -d)"
    export HOME="$SANDBOX"          # 실제 ~/.claude 를 건드리지 않도록 격리

    # 실제 휴지통 도구를 설치하려 들지 않도록 스텁을 PATH 앞에 둔다.
    mkdir -p "$SANDBOX/bin"
    printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/bin/trash-put"
    chmod +x "$SANDBOX/bin/trash-put"
    export PATH="$SANDBOX/bin:$PATH"
}

teardown() {
    [ -n "${SANDBOX:-}" ] && rm -rf "$SANDBOX"
}

@test "setup.sh --help exits 0 and prints usage" {
    run bash "$REPO_ROOT/scripts/setup.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"사용법"* ]]
}

@test "setup.sh -h prints usage" {
    run bash "$REPO_ROOT/scripts/setup.sh" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"--uninstall"* ]]
}

@test "setup.sh rejects unknown option with exit 1" {
    run bash "$REPO_ROOT/scripts/setup.sh" --bogus
    [ "$status" -eq 1 ]
    [[ "$output" == *"알 수 없는 옵션"* ]]
}

@test "setup.sh --hooks --dry-run does not create ~/.claude/settings.json" {
    run bash "$REPO_ROOT/scripts/setup.sh" --hooks --dry-run
    [ "$status" -eq 0 ]
    [ ! -e "$HOME/.claude/settings.json" ]
}

@test "setup_hooks.sh --uninstall --dry-run on clean HOME succeeds and writes nothing" {
    run bash "$REPO_ROOT/scripts/setup_hooks.sh" --uninstall --dry-run
    [ "$status" -eq 0 ]
    [ ! -e "$HOME/.claude/settings.json" ]
}

@test "install.sh --help exits 0 without network" {
    run sh "$REPO_ROOT/install.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"부트스트랩"* ]]
}

# 아래는 dry-run 이 아닌 '실제 설치' 경로다. bash 3.2 (macOS 기본) 는 set -u 에서 빈 배열의
# "${arr[@]}" 확장을 unbound variable 로 취급하는데, --dry-run 일 때는 배열이 비어있지 않아
# 그 버그가 드러나지 않는다. 실제 설치를 밟는 테스트가 없으면 macOS 전체가 깨진 채로 통과한다.

@test "setup.sh --hooks actually installs the guard hooks" {
    run bash "$REPO_ROOT/scripts/setup.sh" --hooks
    [ "$status" -eq 0 ]
    [ -f "$HOME/.claude/hooks/danger_guard.py" ]
    [ -f "$HOME/.claude/hooks/secrets_guard.py" ]
    [ -f "$HOME/.claude/settings.json" ]
}

@test "setup.sh with no args installs hooks and AGENTS.md" {
    cd "$SANDBOX"
    run bash "$REPO_ROOT/scripts/setup.sh"
    [ "$status" -eq 0 ]
    [ -f "$HOME/.claude/hooks/danger_guard.py" ]
    [ -f "$SANDBOX/AGENTS.md" ]
}

@test "setup.sh --uninstall removes the hooks it installed" {
    bash "$REPO_ROOT/scripts/setup.sh" --hooks
    run bash "$REPO_ROOT/scripts/setup.sh" --uninstall
    [ "$status" -eq 0 ]
    [ ! -f "$HOME/.claude/hooks/danger_guard.py" ]
}

@test "setup.sh --hooks is idempotent across repeated real installs" {
    bash "$REPO_ROOT/scripts/setup.sh" --hooks
    run bash "$REPO_ROOT/scripts/setup.sh" --hooks
    [ "$status" -eq 0 ]
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
    [[ "$output" != *"알 수 없는 옵션"* ]]
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
