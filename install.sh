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
# 동작한다. 터미널이 없으면 온보딩은 조용히 건너뛰고 예전처럼 전체 설치가 진행된다.
#
# 환경변수:
#   CLAUDE_SETUP_REPO=owner/repo   대상 레포 (기본 thsvkd/ai-setup)
#   CLAUDE_SETUP_REF=main          브랜치/태그 (기본 main; 배포 시 vX.Y.Z 태그 권장)
#                                  feature/foo 처럼 슬래시가 든 브랜치명도 그대로 쓸 수 있다.
#   GITHUB_TOKEN / GH_TOKEN        비공개(private) 레포 다운로드용 PAT. 둘 다 없으면
#                                  `gh auth token` 으로 폴백한다.
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
  curl -fsSL .../install.sh | sh -s -- --keybinds # newline keybinding only
  curl -fsSL .../install.sh | sh -s -- --omc      # oh-my-claudecode + cache TTL HUD
  curl -fsSL .../install.sh | sh -s -- --output-style # fluent-korean output style
  curl -fsSL .../install.sh | sh -s -- --mods     # Claude Code mod (Bash diff filter, cache TTL status line)
  curl -fsSL .../install.sh | sh -s -- --newline ctrl-enter
  curl -fsSL .../install.sh | sh -s -- --help     # this help

Run without arguments to get an onboarding that picks the install scope and permission mode (auto/bypassPermissions).
It works even when piped (stdin is the script body) by opening the controlling terminal directly;
without a terminal (CI, etc.) it does a full install without onboarding.

Environment variables:
  CLAUDE_SETUP_REPO=owner/repo   target repo (default thsvkd/ai-setup)
  CLAUDE_SETUP_REF=main          branch/tag (default main). Slashes are fine, as in
                                 feature/foo, and so is refs/heads/feature/foo.
  GITHUB_TOKEN / GH_TOKEN        PAT for private repos. Falls back to `gh auth token` if unset.

A 404 on a private repo is almost always a token problem (GitHub disguises auth failures
as 404). On failure this script diagnoses and reports the cause.
EOF
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || return 1
}

# GITHUB_TOKEN → GH_TOKEN → `gh auth token` 순으로 찾는다. gh 폴백이 있으면 사용자가
# GITHUB_TOKEN 을 셸에 export 해둘 필요가 없다 — 그 환경변수가 남아 있으면 gh 가
# "환경변수를 쓰는 중"이라며 `gh auth login` 을 거부해, 토큰이 만료된 순간 재로그인조차
# 할 수 없는 상태에 빠진다.
resolve_token() {
    if [ -n "${GITHUB_TOKEN:-}" ]; then printf '%s' "$GITHUB_TOKEN"; return 0; fi
    if [ -n "${GH_TOKEN:-}" ]; then printf '%s' "$GH_TOKEN"; return 0; fi
    if need_cmd gh; then gh auth token 2>/dev/null || true; fi
    return 0
}

# 토큰을 argv 대신 curl 설정 파일로 넘긴다 (ps aux 로 다른 사용자에게 노출되지 않도록).
write_token_conf() {
    TOKEN_CONF="$(mktemp)"
    printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" > "$TOKEN_CONF"
}

# fetch <url> <outfile>. 반드시 `if` 조건에서 호출할 것 (set -e 가 함수 안까지 번지지 않도록).
#   --proto '=https': HTTPS 만 허용(다운그레이드 차단), --tlsv1.2: TLS 1.2 이상,
#   -f: HTTP 오류 시 실패(에러 페이지를 tar 로 넘기지 않음).
fetch() {
    if need_cmd curl; then
        if [ -n "$TOKEN" ]; then
            write_token_conf
            curl --proto '=https' --tlsv1.2 -fsSL -K "$TOKEN_CONF" -o "$2" "$1"
            _rc=$?
            rm -f "$TOKEN_CONF"; TOKEN_CONF=""
            return "$_rc"
        fi
        curl --proto '=https' --tlsv1.2 -fsSL -o "$2" "$1"
        return $?
    fi
    if need_cmd wget; then
        if [ -n "$TOKEN" ]; then
            wget --https-only -q --header "Authorization: Bearer $TOKEN" -O "$2" "$1"
            return $?
        fi
        wget --https-only -q -O "$2" "$1"
        return $?
    fi
    echo "❌ curl or wget is required." >&2
    exit 1
}

# GitHub API 는 인증 실패를 정직하게 401 로 알려준다. 아카이브/raw URL 과 달리.
api_status() {
    need_cmd curl || { printf '%s' ""; return 0; }
    if [ -n "$TOKEN" ]; then
        write_token_conf
        _code="$(curl -s -o /dev/null -w '%{http_code}' -K "$TOKEN_CONF" "$1" || true)"
        rm -f "$TOKEN_CONF"; TOKEN_CONF=""
    else
        _code="$(curl -s -o /dev/null -w '%{http_code}' "$1" || true)"
    fi
    printf '%s' "$_code"
}

# 비공개 레포는 인증 실패를 401 이 아니라 404 로 위장한다 (레포의 존재 자체를 숨기려고).
# 그래서 "install.sh 가 없다"처럼 보이는 오류의 진짜 원인은 대개 죽은 토큰이다.
# API 를 한 번 찔러 실제 원인을 특정해준다.
explain_download_failure() {
    echo "" >&2
    echo "❌ Download failed: $TARBALL" >&2
    echo "" >&2

    if [ -z "$TOKEN" ]; then
        echo "  No token found. A private repo requires authentication:" >&2
        echo "    gh auth login -h github.com" >&2
        echo "  Once logged in, this script reads the token from gh automatically." >&2
        return 0
    fi

    echo "  Failed even with a token. Private repos report auth failures as 404, not 401," >&2
    echo "  so even when it looks like 'file not found', the cause is usually the token." >&2
    echo "" >&2
    case "$(api_status "https://api.github.com/repos/$REPO")" in
        401)
            echo "  Diagnosis: the token is expired/revoked (GitHub API returned 401 Bad credentials)." >&2
            echo "    unset GITHUB_TOKEN GH_TOKEN" >&2
            echo "    gh auth login -h github.com" >&2
            echo "  ※ gh auth login refuses to run while GITHUB_TOKEN is set. Unset it first." >&2
            ;;
        403)
            echo "  Diagnosis: the token is valid but has no permission for this repo (403)." >&2
            echo "    A classic PAT needs the repo scope; a fine-grained PAT needs Contents:Read." >&2
            ;;
        404)
            echo "  Diagnosis: the token authenticates but cannot see '$REPO' (404)." >&2
            echo "    Check that CLAUDE_SETUP_REPO is correct and that the token has access to this repo." >&2
            ;;
        200)
            echo "  Diagnosis: the repo is reachable but ref '$REF' was not found." >&2
            echo "    Check the branch/tag name. You can also give the fully qualified form:" >&2
            echo "      CLAUDE_SETUP_REF=refs/heads/feature/my-branch" >&2
            ;;
        *)
            echo "  Diagnosis: could not reach the GitHub API. Check your network/proxy." >&2
            ;;
    esac
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
    TOKEN_CONF=""
    # EXIT 트랩의 종료 상태가 스크립트의 종료 상태가 된다. 진입 시점의 $? 를 붙잡아
    # 그대로 돌려주지 않으면, 정리 작업의 마지막 명령이 실패했다는 이유만으로 설치가
    # 성공해도 exit 1 이 된다 (예: TOKEN_CONF 가 비어 `[ -n "" ]` 가 1 을 반환).
    cleanup() {
        _status=$?
        rm -rf "$TMP"
        if [ -n "$TOKEN_CONF" ]; then
            rm -f "$TOKEN_CONF"
        fi
        return "$_status"
    }
    trap 'cleanup' EXIT
    trap 'cleanup; exit 130' INT
    trap 'cleanup; exit 143' TERM

    # 비공개 레포면 PAT 로 인증한다. github.com 아카이브 URL 은 Authorization 헤더를 받아준다.
    TOKEN="$(resolve_token)"
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
