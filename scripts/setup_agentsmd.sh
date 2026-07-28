#!/usr/bin/env bash
#
# res/AGENTS.md 를 현재 작업 디렉터리(대상 프로젝트 루트로 가정)에 설치 (macOS/Linux)
#
#   이미 대상 프로젝트에 AGENTS.md 가 있으면 덮어쓰지 않고 건너뜁니다 — 이 파일은
#   프로젝트별로 커스터마이징되는 것을 전제하기 때문에, settings.json 처럼 정교한
#   외과적 병합을 하지 않고 "없을 때만 설치"라는 단순한 정책을 씁니다.
#
#   이 스크립트는 scripts/setup.sh 디스패처가 --agentsmd 로 호출하는 워커입니다.
#   프로젝트 루트에서 직접 실행할 수도 있습니다.
#
# 사용법:
#   bash setup_agentsmd.sh              # 실제 설치
#   bash setup_agentsmd.sh --dry-run    # 아무것도 건드리지 않고 미리보기만
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE="$REPO_ROOT/res/AGENTS.md"
TARGET="$(pwd)/AGENTS.md"

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        *) echo "알 수 없는 옵션: $arg" >&2; exit 1 ;;
    esac
done

echo "🔧 AGENTS.md 설치..."

if [[ ! -f "$SOURCE" ]]; then
    echo "❌ 소스 파일을 찾을 수 없습니다: $SOURCE" >&2
    exit 1
fi

if [[ -f "$TARGET" ]]; then
    echo "  ℹ️ 이미 $TARGET 가 존재합니다 — 덮어쓰지 않고 건너뜁니다."
elif [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  🧪 DRY RUN — $TARGET 에 설치될 예정입니다 (실제로 쓰지 않음)."
else
    cp "$SOURCE" "$TARGET"
    echo "  ✅ 설치 완료: $TARGET"
fi
