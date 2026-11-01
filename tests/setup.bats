#!/usr/bin/env bats
# ai-setup 의 기능은 모두 jarvis 로 옮겼다. 남은 POSIX 진입점은 아무것도 바꾸지 않고 jarvis 를 안내한 뒤
# 종료 코드 1 로 끝나야 한다(covers: AI-70).
#   실행: bats tests/setup.bats

setup() {
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SANDBOX="$(mktemp -d)"
    export HOME="$SANDBOX"
}

teardown() {
    [ -n "${SANDBOX:-}" ] && rm -rf "$SANDBOX"
}

@test "every POSIX entry point points to jarvis, exits 1 and writes nothing (covers: AI-70)" {
    mkdir -p "$HOME/.claude"
    printf '{"keybinds": true}\n' > "$HOME/.claude/.claude-code-setup.json"
    cd "$SANDBOX"
    before="$(find "$HOME" | sort; cat "$HOME/.claude/.claude-code-setup.json")"
    for entry in "sh $REPO_ROOT/install.sh" "bash $REPO_ROOT/scripts/setup.sh" "bash $REPO_ROOT/scripts/update-ai.sh"; do
        for args in "" "--help" "--stages all" "--keybinds" "--uninstall" "--check"; do
            # shellcheck disable=SC2086
            run $entry $args
            [ "$status" -eq 1 ] || { echo "$entry $args -> $status"; return 1; }
            [[ "$output" == *"ai-setup has moved into jarvis"* ]] || { echo "$entry $args: $output"; return 1; }
            [[ "$output" == *"python3 -m jarvis module setup plan --json"* ]]
        done
    done
    [ "$(find "$HOME" | sort; cat "$HOME/.claude/.claude-code-setup.json")" = "$before" ]
}
