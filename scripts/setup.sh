#!/usr/bin/env bash
#
# Claude Code 사용자 레벨 설정 CLI 엔트리포인트 (macOS/Linux)
#
#   인자 없이 실행하면 대화형 온보딩(res/onboard.py)이 떠서 설치 범위·권한 모드 등을
#   고르게 합니다. 플래그를 하나라도 주면 사용자가 이미 뜻을 밝힌 것이므로 온보딩을
#   건너뛰고 예전과 똑같이 동작합니다. 온보딩을 띄울 수 없는 환경(TTY 없음/CI)에서도
#   예전 기본값(훅+권한 설치 + AGENTS.md 설치)으로 그대로 진행합니다.
#
# 사용법:
#   bash setup.sh                       # 온보딩 → 선택대로 실행
#   bash setup.sh --hooks                # 훅/권한만 (온보딩 없음)
#   bash setup.sh --agentsmd             # AGENTS.md만 (온보딩 없음)
#   bash setup.sh --dry-run              # 미리보기 (전체, 온보딩 없음)
#   bash setup.sh --no-onboard           # 온보딩을 끄고 예전 기본 동작
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

print_usage() {
    cat <<'EOF'
claude-code-setup — Claude Code 사용자 레벨 설정

사용법: bash setup.sh [옵션]
  (옵션 없음)   대화형 온보딩으로 설치 범위/권한 모드를 고른 뒤 실행
  --hooks       전역 가드 훅 + 권한만 설치 (~/.claude)
  --agentsmd    현재 폴더에 AGENTS.md 만 설치
  --uninstall   가드 훅 제거 + settings.json 등록 해제 (권한은 보존)
  --dry-run     아무것도 바꾸지 않고 변경 계획만 출력
  --no-onboard  대화형 온보딩을 띄우지 않고 기본값으로 실행
  --help, -h    이 도움말

온보딩에서 고를 수 있는 것:
  · 설치 범위 (전체 / 가드 훅+권한만 / AGENTS.md만)
  · 권한 모드 (auto / bypassPermissions)
  · 기존 AGENTS.md 덮어쓰기 여부 (파일이 이미 있을 때만 물음)
  · 지금 적용할지, 변경 계획(--dry-run)만 먼저 볼지
EOF
}

RUN_HOOKS=0
RUN_AGENTSMD=0
DRY_RUN=0
UNINSTALL=0
NO_ONBOARD=0
# 온보딩이 채우는 값들. 비어 있으면 워커가 각자의 기본값을 쓴다.
DEFAULT_MODE=""
FORCE_AGENTSMD=0

HAD_ARGS=0
for arg in "$@"; do
    case "$arg" in
        --hooks) RUN_HOOKS=1; HAD_ARGS=1 ;;
        --agentsmd) RUN_AGENTSMD=1; HAD_ARGS=1 ;;
        --uninstall) UNINSTALL=1; HAD_ARGS=1 ;;
        --dry-run) DRY_RUN=1; HAD_ARGS=1 ;;
        --no-onboard) NO_ONBOARD=1; HAD_ARGS=1 ;;
        --help|-h) print_usage; exit 0 ;;
        *) echo "알 수 없는 옵션: $arg" >&2; echo ""; print_usage >&2; exit 1 ;;
    esac
done

resolve_python_command() {
    if command -v python3 &>/dev/null; then
        echo "python3"
    elif command -v python &>/dev/null; then
        echo "python"
    else
        return 1
    fi
}

# 인자가 하나도 없을 때만 온보딩을 띄운다.
#
# 온보딩 종료 코드: 0=선택 완료, 2=대화형 불가(TTY 없음/CI), 130=사용자 취소.
# 2 와 130 을 구분하는 게 중요하다 — 2 는 "물어볼 수 없었다"라서 예전 기본값으로 계속
# 진행해야 하고, 130 은 사용자가 명시적으로 거부한 것이라 아무것도 설치하면 안 된다.
run_onboarding() {
    local onboard="$REPO_ROOT/res/onboard.py"
    [[ -f "$onboard" ]] || return 0

    local py
    py="$(resolve_python_command)" || return 0

    # python 이 2.x 면 onboard.py 는 파싱 단계에서 SyntaxError 로 죽고, 그 traceback 이
    # 그대로 사용자에게 보여 설치가 실패한 것처럼 읽힌다. 먼저 조용히 걸러낸다.
    if ! "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
        return 0
    fi

    local answers status
    answers="$(mktemp)"
    set +e
    "$py" -X utf8 "$onboard" --out "$answers" --project-dir "$(pwd)"
    status=$?
    set -e

    if [[ "$status" -eq 130 ]]; then
        rm -f "$answers"
        exit 130
    fi
    if [[ "$status" -ne 0 ]]; then
        rm -f "$answers"
        return 0    # 대화형 불가 — 예전 기본값 그대로
    fi

    # eval 대신 한 줄씩 읽어 아는 키만 받는다.
    local key value
    while IFS='=' read -r key value; do
        case "$key" in
            SCOPE)
                case "$value" in
                    all) RUN_HOOKS=1; RUN_AGENTSMD=1 ;;
                    hooks) RUN_HOOKS=1 ;;
                    agentsmd) RUN_AGENTSMD=1 ;;
                esac ;;
            DEFAULT_MODE)
                case "$value" in
                    auto|bypassPermissions|default|acceptEdits|plan) DEFAULT_MODE="$value" ;;
                esac ;;
            OVERWRITE_AGENTSMD) [[ "$value" == "1" ]] && FORCE_AGENTSMD=1 ;;
            DRY_RUN) [[ "$value" == "1" ]] && DRY_RUN=1 ;;
        esac
    done < "$answers"
    rm -f "$answers"
}

if [[ "$HAD_ARGS" -eq 0 && "$NO_ONBOARD" -eq 0 ]]; then
    run_onboarding
fi

# bash 3.2 (macOS 기본) 는 set -u 에서 빈 배열의 "${arr[@]}" 확장을 unbound variable 로
# 취급한다. ${arr[@]+"${arr[@]}"} 형태로 감싸야 빈 배열이 안전하게 0개 인자로 펼쳐진다.
DRY_FLAG=()
[[ "$DRY_RUN" -eq 1 ]] && DRY_FLAG=(--dry-run)

MODE_FLAG=()
[[ -n "$DEFAULT_MODE" ]] && MODE_FLAG=(--default-mode "$DEFAULT_MODE")

FORCE_FLAG=()
[[ "$FORCE_AGENTSMD" -eq 1 ]] && FORCE_FLAG=(--force)

# uninstall 은 훅 전용 (프로젝트 AGENTS.md 는 사용자 콘텐츠라 건드리지 않음).
if [[ "$UNINSTALL" -eq 1 ]]; then
    exec bash "$SCRIPT_DIR/setup_hooks.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"}
fi

if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 ]]; then
    RUN_HOOKS=1
    RUN_AGENTSMD=1
fi

if [[ "$RUN_HOOKS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_hooks.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${MODE_FLAG[@]+"${MODE_FLAG[@]}"}
fi

if [[ "$RUN_AGENTSMD" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_agentsmd.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${FORCE_FLAG[@]+"${FORCE_FLAG[@]}"}
fi
