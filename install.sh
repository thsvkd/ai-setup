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
# 인자 없이 실행하면 setup.sh 가 대화형 온보딩을 띄운다. 이 스크립트는 stdin 이 파이프인
# 채로 setup.sh 를 부르지만(위 curl | sh), 온보딩이 /dev/tty 를 직접 열기 때문에 정상
# 동작한다. 터미널이 없으면 온보딩은 조용히 건너뛰고 예전처럼 전체 설치가 진행된다.
#
# 환경변수:
#   CLAUDE_SETUP_REPO=owner/repo   대상 레포 (기본 thsvkd/claude-code-setup)
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
claude-code-setup 원격 설치 부트스트랩

사용법:
  curl -fsSL .../install.sh | sh                 # 대화형 온보딩 → 고른 대로 설치
  curl -fsSL .../install.sh | sh -s -- --hooks    # 전역 가드/권한만
  curl -fsSL .../install.sh | sh -s -- --agentsmd # 현재 폴더에 AGENTS.md 만
  curl -fsSL .../install.sh | sh -s -- --dry-run  # 아무것도 바꾸지 않고 미리보기
  curl -fsSL .../install.sh | sh -s -- --no-onboard # 온보딩 없이 전체 설치
  curl -fsSL .../install.sh | sh -s -- --skills   # 번들 스킬만
  curl -fsSL .../install.sh | sh -s -- --keybinds # 줄바꿈 키바인딩만
  curl -fsSL .../install.sh | sh -s -- --newline ctrl-enter
  curl -fsSL .../install.sh | sh -s -- --help     # 이 도움말

인자 없이 실행하면 설치 범위·권한 모드(auto/bypassPermissions)를 고르는 온보딩이 뜹니다.
파이프로 실행해도(stdin 이 스크립트 본문이어도) 제어 터미널을 직접 열어 동작하며,
터미널이 없는 환경(CI 등)에서는 온보딩 없이 전체 설치로 진행합니다.

환경변수:
  CLAUDE_SETUP_REPO=owner/repo   대상 레포 (기본 thsvkd/claude-code-setup)
  CLAUDE_SETUP_REF=main          브랜치/태그 (기본 main). feature/foo 처럼 슬래시가
                                 들어가도 되고, refs/heads/feature/foo 도 된다.
  GITHUB_TOKEN / GH_TOKEN        비공개 레포용 PAT. 없으면 `gh auth token` 으로 폴백.

비공개 레포에서 404 가 나면 대부분 토큰 문제입니다 (GitHub 은 인증 실패를 404 로
위장합니다). 이 스크립트가 실패 시 원인을 진단해 알려줍니다.
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
    echo "❌ curl 또는 wget 이 필요합니다." >&2
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
    echo "❌ 다운로드 실패: $TARBALL" >&2
    echo "" >&2

    if [ -z "$TOKEN" ]; then
        echo "  토큰을 찾지 못했습니다. 비공개(private) 레포라면 인증이 필요합니다:" >&2
        echo "    gh auth login -h github.com" >&2
        echo "  로그인해 두면 이 스크립트가 gh 에서 토큰을 알아서 읽어옵니다." >&2
        return 0
    fi

    echo "  토큰이 있는데도 실패했습니다. 비공개 레포는 인증 실패를 401 이 아니라 404 로" >&2
    echo "  돌려주므로, '파일이 없다'처럼 보여도 원인은 대개 토큰입니다." >&2
    echo "" >&2
    case "$(api_status "https://api.github.com/repos/$REPO")" in
        401)
            echo "  진단: 토큰이 만료/폐기되었습니다 (GitHub API 가 401 Bad credentials)." >&2
            echo "    unset GITHUB_TOKEN GH_TOKEN" >&2
            echo "    gh auth login -h github.com" >&2
            echo "  ※ GITHUB_TOKEN 이 설정돼 있으면 gh auth login 이 거부됩니다. 먼저 unset 하세요." >&2
            ;;
        403)
            echo "  진단: 토큰은 유효하지만 이 레포에 접근할 권한이 없습니다 (403)." >&2
            echo "    classic PAT 는 repo 스코프, fine-grained PAT 는 Contents:Read 가 필요합니다." >&2
            ;;
        404)
            echo "  진단: 토큰은 인증되지만 '$REPO' 를 볼 수 없습니다 (404)." >&2
            echo "    CLAUDE_SETUP_REPO 값이 맞는지, 토큰에 이 레포 권한이 있는지 확인하세요." >&2
            ;;
        200)
            echo "  진단: 레포 접근은 되는데 ref '$REF' 를 찾지 못했습니다." >&2
            echo "    브랜치/태그 이름을 확인하세요. 완전한 형태로도 지정할 수 있습니다:" >&2
            echo "      CLAUDE_SETUP_REF=refs/heads/feature/my-branch" >&2
            ;;
        *)
            echo "  진단: GitHub API 에 닿지 못했습니다. 네트워크/프록시를 확인하세요." >&2
            ;;
    esac
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

    echo "⬇️  claude-code-setup 다운로드 중 ($REPO@$REF)..."
    # 파이프(curl | tar) 대신 파일로 받는다. 파이프였다면 pipeline 의 종료 상태가 tar 의
    # 것이라 curl 의 404 가 "Unexpected EOF" 로 둔갑해 원인을 알 수 없었다.
    if ! fetch "$TARBALL" "$TARFILE"; then
        explain_download_failure
        exit 1
    fi
    if ! tar -xzf "$TARFILE" -C "$TMP"; then
        echo "❌ 내려받은 아카이브를 풀지 못했습니다: $TARBALL" >&2
        exit 1
    fi
    rm -f "$TARFILE"

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
