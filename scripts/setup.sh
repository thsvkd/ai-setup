#!/usr/bin/env bash
#
# Claude Code 사용자 레벨 설정 CLI 엔트리포인트 (macOS/Linux)
#
#   인자 없이 실행하면 훅/권한 설정(setup_hooks.sh)과 AGENTS.md 설치(setup_agentsmd.sh)를
#   모두 실행합니다. --hooks 또는 --agentsmd 를 지정하면 지정한 것만 실행합니다.
#
# 사용법:
#   bash setup.sh                       # 전체 실행
#   bash setup.sh --hooks                # 훅/권한만
#   bash setup.sh --agentsmd             # AGENTS.md만
#   bash setup.sh --dry-run              # 미리보기 (전체)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RUN_HOOKS=0
RUN_AGENTSMD=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --hooks) RUN_HOOKS=1 ;;
        --agentsmd) RUN_AGENTSMD=1 ;;
        --dry-run) DRY_RUN=1 ;;
        *) echo "알 수 없는 옵션: $arg" >&2; exit 1 ;;
    esac
done

if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 ]]; then
    RUN_HOOKS=1
    RUN_AGENTSMD=1
fi

DRY_FLAG=()
[[ "$DRY_RUN" -eq 1 ]] && DRY_FLAG=(--dry-run)

if [[ "$RUN_HOOKS" -eq 1 ]]; then
    "$SCRIPT_DIR/setup_hooks.sh" "${DRY_FLAG[@]}"
fi

if [[ "$RUN_AGENTSMD" -eq 1 ]]; then
    "$SCRIPT_DIR/setup_agentsmd.sh" "${DRY_FLAG[@]}"
fi
