#!/usr/bin/env bash
#
# Install the project instruction files into the current working directory,
# which is assumed to be the target project root (macOS/Linux).
#
#   Which files get written depends on the selected harnesses. Codex, Grok and
#   OpenCode read the root AGENTS.md directly, so AGENTS.md is always written.
#   Claude Code does not read AGENTS.md -- it reads CLAUDE.md -- so a one-line
#   CLAUDE.md importing @AGENTS.md is written as well when claude is selected.
#   A symlink would also work but needs Administrator rights on Windows, so the
#   import is used on every platform for parity.
#
#   An existing file is never overwritten; it is skipped. These files are meant
#   to be customised per project, so there is no surgical merge as there is for
#   settings.json -- the policy is simply "install when absent".
#
#   --force overwrites, and is only used when the user explicitly chose to
#   overwrite during onboarding. The original is kept as .bak.<timestamp>.
#
#   This is the worker that the scripts/setup.sh dispatcher calls with
#   --agentsmd. It can also be run directly from a project root.
#
# Usage:
#   bash setup_agentsmd.sh                        # install (skip existing files)
#   bash setup_agentsmd.sh --harness claude,codex # only those harnesses
#   bash setup_agentsmd.sh --force                # back up, then overwrite
#   bash setup_agentsmd.sh --dry-run              # preview, touch nothing
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(pwd)"

DRY_RUN=0
FORCE=0
# Every supported harness by default: this installer exists to set up whichever
# agent the user runs, and each artefact is additive and skipped when present.
HARNESS_ARG="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --force) FORCE=1; shift ;;
        --harness)
            if [[ -z "${2:-}" ]]; then
                echo "--harness 값이 필요합니다 (claude|codex|grok|opencode|all)" >&2
                exit 1
            fi
            HARNESS_ARG="$2"; shift 2 ;;
        --harness=*) HARNESS_ARG="${1#*=}"; shift ;;
        *) echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
    esac
done

# Expand the comma-separated selection into a space-padded list, rejecting names
# we do not know rather than silently installing something the user did not ask
# for. bash 3.2 (the macOS default) has no associative arrays, so membership is
# a substring test against a padded string.
SELECTED=""
normalize_harnesses() {
    local raw item seen
    raw="$(printf '%s' "$1" | tr 'A-Z' 'a-z' | tr ',' ' ')"
    for item in $raw; do
        case "$item" in
            all) item="claude codex grok opencode" ;;
            claude|claude-code) item="claude" ;;
            codex|grok|opencode) ;;
            *) echo "알 수 없는 하네스: $item (claude|codex|grok|opencode|all)" >&2; return 1 ;;
        esac
        for seen in $item; do
            case " $SELECTED " in
                *" $seen "*) ;;
                *) SELECTED="$SELECTED $seen" ;;
            esac
        done
    done
    SELECTED="${SELECTED# }"
    if [[ -z "$SELECTED" ]]; then
        echo "하네스를 최소 하나는 골라야 합니다 (claude|codex|grok|opencode|all)" >&2
        return 1
    fi
    return 0
}

has_harness() {
    case " $SELECTED " in
        *" $1 "*) return 0 ;;
        *) return 1 ;;
    esac
}

# Install one file, honouring skip/force/backup/dry-run identically for every
# file so a second artefact cannot acquire weaker guarantees than AGENTS.md.
install_file() {
    local source="$1" target="$2"

    if [[ ! -f "$source" ]]; then
        echo "❌ 소스 파일을 찾을 수 없습니다: $source" >&2
        return 1
    fi

    if [[ -f "$target" && "$FORCE" -eq 0 ]]; then
        echo "  ℹ️ 이미 $target 가 존재합니다 — 덮어쓰지 않고 건너뜁니다."
        return 0
    fi

    if [[ "$DRY_RUN" -eq 1 ]]; then
        if [[ -f "$target" ]]; then
            echo "  🧪 DRY RUN — 기존 $target 를 백업 후 덮어쓸 예정입니다 (실제로 쓰지 않음)."
        else
            echo "  🧪 DRY RUN — $target 에 설치될 예정입니다 (실제로 쓰지 않음)."
        fi
        return 0
    fi

    # Overwriting destroys user content, so the original is always kept.
    if [[ -f "$target" ]]; then
        local backup="$target.bak.$(date +%Y%m%d%H%M%S)"
        cp "$target" "$backup"
        echo "  💾 기존 파일 백업: $backup"
    fi
    cp "$source" "$target"
    echo "  ✅ 설치 완료: $target"
    return 0
}

normalize_harnesses "$HARNESS_ARG"

echo "🔧 프로젝트 지침 설치... (하네스: $(printf '%s' "$SELECTED" | tr ' ' ','))"

# AGENTS.md is the shared source for every harness, including Claude Code, which
# reaches it through the CLAUDE.md import.
install_file "$REPO_ROOT/res/AGENTS.md" "$PROJECT_DIR/AGENTS.md"

if has_harness claude; then
    CLAUDE_TARGET="$PROJECT_DIR/CLAUDE.md"
    HAD_CLAUDE_MD=0
    [[ -f "$CLAUDE_TARGET" ]] && HAD_CLAUDE_MD=1

    install_file "$REPO_ROOT/res/CLAUDE.md" "$CLAUDE_TARGET"

    # Skipping an existing CLAUDE.md is the right default -- it is user content.
    # But if that file does not import AGENTS.md, Claude Code never reads the
    # instructions we just installed, and staying silent would report success
    # for an install that did nothing for the harness the user selected.
    if [[ "$HAD_CLAUDE_MD" -eq 1 && "$FORCE" -eq 0 ]] && ! grep -q '@AGENTS\.md' "$CLAUDE_TARGET"; then
        echo "  ⚠️ 기존 $CLAUDE_TARGET 에 '@AGENTS.md' 가 없습니다 — Claude Code 는 방금 설치한 AGENTS.md 를 읽지 않습니다." >&2
        echo "     기존 내용을 지우지 않으려면 그 파일 맨 위에 '@AGENTS.md' 한 줄을 직접 추가하세요." >&2
    fi
fi
