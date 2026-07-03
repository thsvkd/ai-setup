#!/bin/sh
# install.sh — claude-code-setup 원격 설치 부트스트랩 (macOS / Linux / Git Bash)
#
# 이 한 파일만 curl 로 받아 실행하면, GitHub 에서 레포 전체를 임시 디렉터리로
# 내려받아 scripts/setup.sh 를 실행한다. (setup.sh 는 res/ 와 scripts/lib/ 등
# 형제 파일이 있어야 동작하므로, 단일 파일 실행이 아니라 이 부트스트랩이 필요하다.)
#
# 사용법:
#   curl -fsSL https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --dry-run
#   curl -fsSL https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --hooks
#
# 환경변수로 대상 레포/브랜치를 바꿀 수 있다:
#   CLAUDE_SETUP_REPO=owner/repo  CLAUDE_SETUP_REF=main
set -eu

REPO="${CLAUDE_SETUP_REPO:-thsvkd/claude-code-setup}"
REF="${CLAUDE_SETUP_REF:-main}"

if ! command -v bash >/dev/null 2>&1; then
    echo "❌ bash 가 필요합니다 (setup.sh 는 bash 문법을 씁니다). bash 설치 후 다시 실행하세요." >&2
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

TARBALL="https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"
echo "⬇️  claude-code-setup 다운로드 중 ($REPO@$REF)..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$TARBALL" | tar -xz -C "$TMP"
elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$TARBALL" | tar -xz -C "$TMP"
else
    echo "❌ curl 또는 wget 이 필요합니다." >&2
    exit 1
fi

DIR="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [ -z "$DIR" ] || [ ! -f "$DIR/scripts/setup.sh" ]; then
    echo "❌ 다운로드한 아카이브에서 scripts/setup.sh 를 찾지 못했습니다." >&2
    exit 1
fi

# setup_agentsmd 는 현재 작업 디렉터리에 AGENTS.md 를 설치하므로, 사용자가 curl 을
# 실행한 원래 위치(cwd)를 그대로 유지한 채 실행한다.
bash "$DIR/scripts/setup.sh" "$@"
