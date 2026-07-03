#!/usr/bin/env bats
# setup.sh / setup_hooks.sh 오케스트레이션 계층 테스트 (bats-core).
# 외부 라이브러리(bats-assert 등) 없이 순수 bats 만으로 동작하도록 작성했다.
#   실행: bats tests/setup.bats

setup() {
    REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    SANDBOX="$(mktemp -d)"
    export HOME="$SANDBOX"          # 실제 ~/.claude 를 건드리지 않도록 격리
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
