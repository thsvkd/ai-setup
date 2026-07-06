#!/bin/sh
# install.sh — claude-code-setup 원격 설치 부트스트랩 (macOS / Linux / Git Bash)
#
# 이 한 파일만 curl 로 받아 실행하면, GitHub 에서 레포 전체를 임시 디렉터리로
# 내려받아 scripts/setup.sh 를 실행한다. (setup.sh 는 res/ 와 scripts/lib/ 등
# 형제 파일이 있어야 동작하므로, 단일 파일 실행이 아니라 이 부트스트랩이 필요하다.)
#
# 사용법 (버전 태그로 고정 권장):
#   curl --proto '=https' --tlsv1.2 -fsSL \
#     https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh
#   curl ... | sh -s -- --dry-run     # 미리보기
#   curl ... | sh -s -- --hooks       # 전역 가드/권한만
#
# 환경변수:
#   CLAUDE_SETUP_REPO=owner/repo   대상 레포 (기본 thsvkd/claude-code-setup)
#   CLAUDE_SETUP_REF=main          브랜치/태그 (기본 main; 배포 시 vX.Y.Z 태그 권장)
#   GITHUB_TOKEN / GH_TOKEN        비공개(private) 레포 다운로드용 PAT (있으면 자동 사용)
#
# 이 스크립트는 전체 로직을 main() 안에 넣고 마지막 줄에서만 호출한다. curl 다운로드가
# 중간에 끊겨도 셸은 "함수 정의"까지만 파싱하고 main 을 실행하지 않으므로, 잘린
# 스크립트가 파괴적 명령을 부분 실행하는 사고를 막는다 (rustup 등이 쓰는 표준 기법).
set -eu

print_help() {
    cat <<'EOF'
claude-code-setup 원격 설치 부트스트랩

사용법:
  curl -fsSL .../install.sh | sh                 # 전체 설치 (가드/권한 + AGENTS.md)
  curl -fsSL .../install.sh | sh -s -- --hooks    # 전역 가드/권한만
  curl -fsSL .../install.sh | sh -s -- --agentsmd # 현재 폴더에 AGENTS.md 만
  curl -fsSL .../install.sh | sh -s -- --dry-run  # 아무것도 바꾸지 않고 미리보기
  curl -fsSL .../install.sh | sh -s -- --help     # 이 도움말

환경변수:
  CLAUDE_SETUP_REPO=owner/repo   대상 레포 (기본 thsvkd/claude-code-setup)
  CLAUDE_SETUP_REF=main          브랜치/태그 (기본 main)
EOF
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || return 1
}

main() {
    for a in "$@"; do
        case "$a" in
            -h|--help) print_help; exit 0 ;;
        esac
    done

    REPO="${CLAUDE_SETUP_REPO:-thsvkd/claude-code-setup}"
    REF="${CLAUDE_SETUP_REF:-main}"

    if ! need_cmd bash; then
        echo "❌ bash 가 필요합니다 (setup.sh 는 bash 문법을 씁니다). bash 설치 후 다시 실행하세요." >&2
        exit 1
    fi

    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT INT TERM

    TARBALL="https://github.com/$REPO/archive/$REF.tar.gz"
    echo "⬇️  claude-code-setup 다운로드 중 ($REPO@$REF)..."
    # 비공개 레포면 PAT 로 인증한다. github.com 아카이브 URL 은 Authorization 헤더를 받아준다.
    TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
    # --proto '=https': HTTPS 만 허용(다운그레이드 차단), --tlsv1.2: TLS 1.2 이상,
    # -f: HTTP 오류 시 실패(에러 페이지를 tar 로 넘기지 않음).
    if need_cmd curl; then
        if [ -n "$TOKEN" ]; then
            curl --proto '=https' --tlsv1.2 -fsSL -H "Authorization: Bearer $TOKEN" "$TARBALL" | tar -xz -C "$TMP"
        else
            curl --proto '=https' --tlsv1.2 -fsSL "$TARBALL" | tar -xz -C "$TMP"
        fi
    elif need_cmd wget; then
        if [ -n "$TOKEN" ]; then
            wget --https-only -qO- --header "Authorization: Bearer $TOKEN" "$TARBALL" | tar -xz -C "$TMP"
        else
            wget --https-only -qO- "$TARBALL" | tar -xz -C "$TMP"
        fi
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
}

main "$@"
