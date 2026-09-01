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
#   bash setup.sh --keybinds             # 줄바꿈 키바인딩만 (온보딩 없음)
#   bash setup.sh --newline ctrl-enter   # 줄바꿈 키를 Ctrl+Enter 로
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
  --agentsmd    현재 폴더에 프로젝트 지침만 설치
  --harness L   지침을 설치할 하네스 (쉼표 구분: claude,codex,grok,opencode,all)
                claude 를 고르면 CLAUDE.md 도 함께 설치된다. 기본값은 all.
  --keybinds    줄바꿈 키바인딩만 설치 (VS Code/Cursor/Claude/Codex/tmux)
  --newline VAL 줄바꿈 키 (shift-enter | ctrl-enter). 기본 shift-enter
  --uninstall   가드 훅 + 관리 키바인딩 제거 (권한·사용자 항목은 보존)
  --dry-run     아무것도 바꾸지 않고 변경 계획만 출력
  --no-onboard  대화형 온보딩을 띄우지 않고 기본값으로 실행
  --help, -h    이 도움말

온보딩에서 고를 수 있는 것:
  · 설치 범위 (전체 / 가드 훅+권한만 / AGENTS.md만)
  · 권한 모드 (auto / bypassPermissions)
  · 줄바꿈 키 (Shift+Enter / Ctrl+Enter) — 범위=전체일 때만
  · 기존 AGENTS.md 덮어쓰기 여부 (파일이 이미 있을 때만 물음)
  · 지금 적용할지, 변경 계획(--dry-run)만 먼저 볼지
EOF
}

RUN_HOOKS=0
RUN_AGENTSMD=0
RUN_KEYBINDS=0
DRY_RUN=0
UNINSTALL=0
NO_ONBOARD=0
# 온보딩이 채우는 값들. 비어 있으면 워커가 각자의 기본값을 쓴다.
DEFAULT_MODE=""
FORCE_AGENTSMD=0
HARNESSES=""
NEWLINE_CHORD=""
NEWLINE_GIVEN=0

HAD_ARGS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hooks) RUN_HOOKS=1; HAD_ARGS=1; shift ;;
        --agentsmd) RUN_AGENTSMD=1; HAD_ARGS=1; shift ;;
        --keybinds) RUN_KEYBINDS=1; HAD_ARGS=1; shift ;;
        --harness)
            if [[ -z "${2:-}" ]]; then
                echo "--harness 값이 필요합니다 (claude|codex|grok|opencode|all)" >&2
                exit 1
            fi
            HARNESSES="$2"; HAD_ARGS=1; shift 2 ;;
        --harness=*) HARNESSES="${1#*=}"; HAD_ARGS=1; shift ;;
        --newline)
            if [[ -z "${2:-}" ]]; then
                echo "--newline 값은 shift-enter 또는 ctrl-enter 여야 합니다." >&2
                exit 1
            fi
            NEWLINE_CHORD="$2"; NEWLINE_GIVEN=1; HAD_ARGS=1; shift 2 ;;
        --newline=*) NEWLINE_CHORD="${1#*=}"; NEWLINE_GIVEN=1; HAD_ARGS=1; shift ;;
        --uninstall) UNINSTALL=1; HAD_ARGS=1; shift ;;
        --dry-run) DRY_RUN=1; HAD_ARGS=1; shift ;;
        --no-onboard) NO_ONBOARD=1; HAD_ARGS=1; shift ;;
        --help|-h) print_usage; exit 0 ;;
        *) echo "알 수 없는 옵션: $1" >&2; echo ""; print_usage >&2; exit 1 ;;
    esac
done

# 값이 비었는지가 아니라 '플래그가 주어졌는지' 로 판정한다. --newline= 처럼 빈 값을 준 경우도
# 잘못된 값이며, 조용히 기본값으로 흘려보내면 PowerShell 쪽(-Newline "")과 동작이 갈린다.
if [[ "$NEWLINE_GIVEN" -eq 1 ]]; then
    case "$NEWLINE_CHORD" in
        shift-enter|ctrl-enter) ;;
        *)
            echo "--newline 값은 shift-enter 또는 ctrl-enter 여야 합니다 (받은 값: $NEWLINE_CHORD)." >&2
            exit 1 ;;
    esac
fi

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
        # 답 파일이 CRLF 로 쓰였을 때 값 끝의 CR 이 모든 매칭을 깨뜨린다 (Git Bash + Windows python).
        # onboard.py 가 LF 를 고정하지만, 여기서도 벗겨서 한쪽만 고쳐도 조용히 깨지지 않게 한다.
        key="${key%$'\r'}"
        value="${value%$'\r'}"
        case "$key" in
            SCOPE)
                case "$value" in
                    all) RUN_HOOKS=1; RUN_AGENTSMD=1; RUN_KEYBINDS=1 ;;
                    hooks) RUN_HOOKS=1 ;;
                    agentsmd) RUN_AGENTSMD=1 ;;
                esac ;;
            DEFAULT_MODE)
                case "$value" in
                    auto|bypassPermissions|default|acceptEdits|plan) DEFAULT_MODE="$value" ;;
                esac ;;
            NEWLINE_CHORD)
                case "$value" in
                    shift-enter|ctrl-enter) NEWLINE_CHORD="$value" ;;
                esac ;;
            HARNESSES)
                # onboard.py writes a controlled set, but a stray value must not
                # reach the worker as a shell word.
                case "$value" in
                    ""|*[!a-z,-]*) ;;
                    *) HARNESSES="$value" ;;
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

HARNESS_FLAG=()
[[ -n "$HARNESSES" ]] && HARNESS_FLAG=(--harness "$HARNESSES")

NEWLINE_FLAG=()
[[ -n "$NEWLINE_CHORD" ]] && NEWLINE_FLAG=(--newline "$NEWLINE_CHORD")

# uninstall: --keybinds --uninstall 은 키바인드만. 아니면 훅 다음 키바인드.
# exec 하면 키바인드 uninstall 이 실행되지 않는다.
if [[ "$UNINSTALL" -eq 1 ]]; then
    # 제거도 설치와 같은 범위 규칙을 따른다. 범위를 지정했으면 그것만 지운다 —
    # --hooks --uninstall 이 키바인딩까지 지우면 "--hooks 는 키바인딩을 건드리지
    # 않는다"(핵심 결정 4)를 제거 쪽에서만 어기는 것이 된다.
    UN_KEYBINDS="$RUN_KEYBINDS"
    UN_HOOKS="$RUN_HOOKS"
    if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 && "$RUN_KEYBINDS" -eq 0 ]]; then
        UN_KEYBINDS=1
        UN_HOOKS=1
    fi
    # 키바인드를 '먼저' 지운다. 훅 uninstall 이 매니페스트를 손보는데, 키바인드 제거는
    # 그 영수증(tmux_added 등)이 있어야 '우리가 넣은 것' 과 사용자 것을 구분할 수 있다.
    # set -e 아래라 한쪽이 실패해도 나머지가 돌도록 종료 코드를 받아 둔다.
    kb_exit=0
    hooks_exit=0
    if [[ "$UN_KEYBINDS" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_keybinds.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} || kb_exit=$?
    fi
    if [[ "$UN_HOOKS" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_hooks.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} || hooks_exit=$?
    fi
    [[ "$hooks_exit" -ne 0 ]] && exit "$hooks_exit"
    exit "$kb_exit"
fi

# 범위 플래그가 하나도 없으면 전체 설치 (훅 + AGENTS.md + 키바인드).
# --hooks 만 / --agentsmd 만 / --keybinds 만이면 그 범위만.
if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 && "$RUN_KEYBINDS" -eq 0 ]]; then
    RUN_HOOKS=1
    RUN_AGENTSMD=1
    RUN_KEYBINDS=1
fi

if [[ "$RUN_HOOKS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_hooks.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${MODE_FLAG[@]+"${MODE_FLAG[@]}"}
fi

if [[ "$RUN_AGENTSMD" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_agentsmd.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${FORCE_FLAG[@]+"${FORCE_FLAG[@]}"} ${HARNESS_FLAG[@]+"${HARNESS_FLAG[@]}"}
fi

if [[ "$RUN_KEYBINDS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_keybinds.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${NEWLINE_FLAG[@]+"${NEWLINE_FLAG[@]}"}
fi
