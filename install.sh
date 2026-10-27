#!/bin/sh
# install.sh — ai-setup 원격 설치 부트스트랩 (macOS / Linux / Git Bash)
#
# 이 한 파일만 curl 로 받아 실행하면, GitHub 에서 레포 전체를 임시 디렉터리로
# 내려받아 scripts/setup.sh 를 실행한다. (setup.sh 는 res/ 와 scripts/lib/ 등
# 형제 파일이 있어야 동작하므로, 단일 파일 실행이 아니라 이 부트스트랩이 필요하다.)
#
# 사용법 (버전 태그로 고정 권장):
#   curl --proto '=https' --tlsv1.2 -fsSL \
#     https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.sh | sh
#   curl ... | sh -s -- --dry-run     # 미리보기
#   curl ... | sh -s -- --hooks       # 전역 가드/권한만
#
# 인자 없이 실행하면 setup.sh 가 대화형 온보딩을 띄운다. 이 스크립트는 stdin 이 파이프인
# 채로 setup.sh 를 부르지만(위 curl | sh), 온보딩이 /dev/tty 를 직접 열기 때문에 정상
# 동작한다. 터미널이 없으면 아무것도 설치하지 않는다. 예전 기본 설치는 --no-onboard 로 한다.
#
# 환경변수:
#   CLAUDE_SETUP_REPO=owner/repo   대상 레포 (기본 thsvkd/ai-setup)
#   CLAUDE_SETUP_REF=main          브랜치/태그 (기본 main; 배포 시 vX.Y.Z 태그 권장)
#                                  feature/foo 처럼 슬래시가 든 브랜치명도 그대로 쓸 수 있다.
#
# 이 스크립트는 전체 로직을 main() 안에 넣고 마지막 줄에서만 호출한다. curl 다운로드가
# 중간에 끊겨도 셸은 "함수 정의"까지만 파싱하고 main 을 실행하지 않으므로, 잘린
# 스크립트가 파괴적 명령을 부분 실행하는 사고를 막는다 (rustup 등이 쓰는 표준 기법).
set -eu

print_help() {
    cat <<'EOF'
ai-setup remote install bootstrap

Usage:
  curl -fsSL .../install.sh | sh                 # interactive onboarding → install what you pick
  curl -fsSL .../install.sh | sh -s -- --hooks    # global guards/permissions only
  curl -fsSL .../install.sh | sh -s -- --agentsmd # AGENTS.md in the current folder only
  curl -fsSL .../install.sh | sh -s -- --dry-run  # preview without changing anything
  curl -fsSL .../install.sh | sh -s -- --no-onboard # full install without onboarding
  curl -fsSL .../install.sh | sh -s -- --skills   # bundled skills only
  curl -fsSL .../install.sh | sh -s -- --tools orca --dry-run # preview official Orca install
  curl -fsSL .../install.sh | sh -s -- --keybinds # newline keybinding only
  curl -fsSL .../install.sh | sh -s -- --omc      # oh-my-claudecode + cache TTL HUD
  curl -fsSL .../install.sh | sh -s -- --output-style # fluent-korean output style
  curl -fsSL .../install.sh | sh -s -- --mods     # Claude Code mod (Bash diff filter, cache TTL status line)
  curl -fsSL .../install.sh | sh -s -- --newline ctrl-enter
  curl -fsSL .../install.sh | sh -s -- --stages all --dry-run # preview the staged installer
  curl -fsSL .../install.sh | sh -s -- --doctor   # read-only health report
  curl -fsSL .../install.sh | sh -s -- --help     # this help

Run without arguments to get an onboarding that picks the install scope and permission mode (auto/bypassPermissions).
It works even when piped (stdin is the script body) by opening the controlling terminal directly;
without a terminal (CI, etc.) nothing is installed. --no-onboard keeps the old default install.
Other options (--orca-desktop, --jarvis-role, --herdr, --ss-caps, ...) are passed to scripts/setup.sh as is.

Environment variables:
  CLAUDE_SETUP_REPO=owner/repo   target repo (default thsvkd/ai-setup)
  CLAUDE_SETUP_REF=main          branch/tag (default main). Slashes are fine, as in
                                 feature/foo, and so is refs/heads/feature/foo.
EOF
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || return 1
}

# fetch <url> <outfile>. 반드시 `if` 조건에서 호출할 것 (set -e 가 함수 안까지 번지지 않도록).
#   --proto '=https': HTTPS 만 허용(다운그레이드 차단), --tlsv1.2: TLS 1.2 이상,
#   -f: HTTP 오류 시 실패(에러 페이지를 tar 로 넘기지 않음).
fetch() {
    if need_cmd curl; then
        curl --proto '=https' --tlsv1.2 -fsSL -o "$2" "$1"
        return $?
    fi
    if need_cmd wget; then
        wget --https-only -q -O "$2" "$1"
        return $?
    fi
    echo "❌ curl or wget is required." >&2
    exit 1
}

explain_download_failure() {
    echo "" >&2
    echo "❌ Download failed: $TARBALL" >&2
    echo "  Check CLAUDE_SETUP_REPO ('$REPO'), CLAUDE_SETUP_REF ('$REF') and your network/proxy." >&2
    echo "  A branch name can also be given in the fully qualified form:" >&2
    echo "    CLAUDE_SETUP_REF=refs/heads/feature/my-branch" >&2
}

main() {
    for a in "$@"; do
        case "$a" in
            -h|--help) print_help; exit 0 ;;
        esac
    done

    REPO="${CLAUDE_SETUP_REPO:-thsvkd/ai-setup}"
    REF="${CLAUDE_SETUP_REF:-main}"

    if ! need_cmd bash; then
        echo "❌ bash is required (setup.sh uses bash syntax). Install bash and run again." >&2
        exit 1
    fi

    TMP="$(mktemp -d)"
    # EXIT 트랩의 종료 상태가 스크립트의 종료 상태가 된다. 진입 시점의 $? 를 붙잡아
    # 그대로 돌려주지 않으면, 정리 작업의 마지막 명령이 실패했다는 이유만으로 설치가
    # 성공해도 exit 1 이 된다.
    cleanup() {
        _status=$?
        rm -rf "$TMP"
        return "$_status"
    }
    trap 'cleanup' EXIT
    trap 'cleanup; exit 130' INT
    trap 'cleanup; exit 143' TERM

    TARBALL="https://github.com/$REPO/archive/$REF.tar.gz"
    TARFILE="$TMP/repo.tar.gz"

    echo "⬇️  ai-setup downloading ($REPO@$REF)..."
    # 파이프(curl | tar) 대신 파일로 받는다. 파이프였다면 pipeline 의 종료 상태가 tar 의
    # 것이라 curl 의 404 가 "Unexpected EOF" 로 둔갑해 원인을 알 수 없었다.
    if ! fetch "$TARBALL" "$TARFILE"; then
        explain_download_failure
        exit 1
    fi
    if ! tar -xzf "$TARFILE" -C "$TMP"; then
        echo "❌ Could not extract the downloaded archive: $TARBALL" >&2
        exit 1
    fi
    rm -f "$TARFILE"

    DIR="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
    if [ -z "$DIR" ] || [ ! -f "$DIR/scripts/setup.sh" ]; then
        echo "❌ scripts/setup.sh was not found in the downloaded archive." >&2
        exit 1
    fi

    # setup_agentsmd 는 현재 작업 디렉터리에 AGENTS.md 를 설치하므로, 사용자가 curl 을
    # 실행한 원래 위치(cwd)를 그대로 유지한 채 실행한다.
    bash "$DIR/scripts/setup.sh" "$@"
}

main "$@"
