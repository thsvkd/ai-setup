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

print_usage() {
    cat <<'EOF'
claude-code-setup — Claude Code 사용자 레벨 설정

사용법: bash setup.sh [옵션]
  (옵션 없음)   가드/권한 + AGENTS.md 모두 설치
  --hooks       전역 가드 훅 + 권한만 설치 (~/.claude)
  --agentsmd    현재 폴더에 AGENTS.md 만 설치
  --uninstall   가드 훅 제거 + settings.json 등록 해제 (권한은 보존)
  --dry-run     아무것도 바꾸지 않고 변경 계획만 출력
  --help, -h    이 도움말
EOF
}

RUN_HOOKS=0
RUN_AGENTSMD=0
DRY_RUN=0
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --hooks) RUN_HOOKS=1 ;;
        --agentsmd) RUN_AGENTSMD=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --dry-run) DRY_RUN=1 ;;
        --help|-h) print_usage; exit 0 ;;
        *) echo "알 수 없는 옵션: $arg" >&2; echo ""; print_usage >&2; exit 1 ;;
    esac
done

# bash 3.2 (macOS 기본) 는 set -u 에서 빈 배열의 "${arr[@]}" 확장을 unbound variable 로
# 취급한다. ${arr[@]+"${arr[@]}"} 형태로 감싸야 빈 배열이 안전하게 0개 인자로 펼쳐진다.
DRY_FLAG=()
[[ "$DRY_RUN" -eq 1 ]] && DRY_FLAG=(--dry-run)

# uninstall 은 훅 전용 (프로젝트 AGENTS.md 는 사용자 콘텐츠라 건드리지 않음).
if [[ "$UNINSTALL" -eq 1 ]]; then
    exec bash "$SCRIPT_DIR/setup_hooks.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"}
fi

if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 ]]; then
    RUN_HOOKS=1
    RUN_AGENTSMD=1
fi

if [[ "$RUN_HOOKS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_hooks.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"}
fi

if [[ "$RUN_AGENTSMD" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_agentsmd.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"}
fi
