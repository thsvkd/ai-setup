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
#   bash setup.sh --omc                  # oh-my-claudecode + 캐시 TTL HUD 만 (온보딩 없음)
#   bash setup.sh --output-style         # fluent-korean 출력 스타일만 (온보딩 없음)
#   bash setup.sh --mods                 # Claude Code mod 만 (온보딩 없음)
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
  --skills      번들 스킬만 설치 (~/.claude/skills)
  --keybinds    줄바꿈 키바인딩만 설치 (VS Code/Cursor/Claude/Codex/tmux)
  --newline VAL 줄바꿈 키 (shift-enter | ctrl-enter). 기본 shift-enter
  --omc         oh-my-claudecode 플러그인 설치 + HUD 에 캐시 TTL 표시
                (범위 지정이 없는 기본 설치에는 포함되지 않는다)
  --output-style
                fluent-korean 플러그인 설치 + outputStyle 을 fluent-korean 으로 지정
                (범위 지정이 없는 기본 설치에는 포함되지 않는다)
  --mods        Claude Code mod 설치 (~/.claude/mods, v2.1.290 이상)
                · bash-diff-filter: Bash 변경 파일 표시에서 OMC HUD 캐시 파일을 뺀다
                · cache-ttl-status: 프롬프트 캐시 잔여 시간을 프롬프트 아래 상태 줄에 띄운다
                (범위 지정이 없는 기본 설치에는 포함되지 않는다)
  --uninstall   가드 훅 + 관리 키바인딩·스킬 + 캐시 TTL HUD + outputStyle + mod 설정 제거
                (권한·사용자 항목·OMC/fluent-korean 플러그인은 보존)
  --dry-run     아무것도 바꾸지 않고 변경 계획만 출력
  --no-onboard  대화형 온보딩을 띄우지 않고 기본값으로 실행
  --help, -h    이 도움말

온보딩에서 고를 수 있는 것:
  · 설치 범위 (전체(번들 스킬 포함) / 가드 훅+권한만 / AGENTS.md만)
  · 권한 모드 (auto / bypassPermissions)
  · 줄바꿈 키 (Shift+Enter / Ctrl+Enter) — 범위=전체일 때만
  · oh-my-claudecode 설치 여부 — 범위=전체/훅일 때만
  · fluent-korean 출력 스타일 설치 여부 — 범위=전체/훅일 때만
  · Claude Code mod 설치 여부 — 범위=전체/훅일 때만
  · 기존 AGENTS.md 덮어쓰기 여부 (파일이 이미 있을 때만 물음)
  · 지금 적용할지, 변경 계획(--dry-run)만 먼저 볼지
EOF
}

RUN_HOOKS=0
RUN_AGENTSMD=0
RUN_KEYBINDS=0
RUN_SKILLS=0
RUN_OMC=0
RUN_OUTPUT_STYLE=0
RUN_MODS=0
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
        --skills) RUN_SKILLS=1; HAD_ARGS=1; shift ;;
        --keybinds) RUN_KEYBINDS=1; HAD_ARGS=1; shift ;;
        --omc) RUN_OMC=1; HAD_ARGS=1; shift ;;
        --output-style) RUN_OUTPUT_STYLE=1; HAD_ARGS=1; shift ;;
        --mods) RUN_MODS=1; HAD_ARGS=1; shift ;;
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

# ── 출력 서식 ────────────────────────────────────────────────────────
# 워커는 단독으로도 실행되므로 각자 이모지 마커(🔧 ✅ ⚠️ 🧪 …)로 줄을 찍는다. 여기서 그 출력을
# 한 줄씩 받아 온보딩과 같은 clack 거터 모양(◇ │ ✓ ▲ └)으로 바꾼다. 문구는 그대로 둔다.
# stderr 는 손대지 않는다 — 오류는 그 스트림 그대로 보여야 한다.
UI_COLOR=0
[[ -t 1 && -z "${NO_COLOR:-}" ]] && UI_COLOR=1
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) UI_UNICODE=1 ;;
    *) UI_UNICODE=0 ;;
esac
[[ "${TERM:-}" == "linux" ]] && UI_UNICODE=0
if [[ "$UI_UNICODE" -eq 1 ]]; then
    G_BAR="│"; G_START="┌"; G_END="└"; G_SECTION="◇"
    G_OK="✓"; G_WARN="▲"; G_ERR="✗"; G_DRY="○"; G_DOT="•"
else
    G_BAR="|"; G_START="T"; G_END="-"; G_SECTION="o"
    G_OK="+"; G_WARN="!"; G_ERR="x"; G_DRY="o"; G_DOT="-"
fi

ui_paint() {    # SGR 코드, 문자열
    if [[ "$UI_COLOR" -eq 1 ]]; then
        printf '\033[%sm%s\033[0m' "$1" "$2"
    else
        printf '%s' "$2"
    fi
}

ui_format() {
    local line body pad mark color
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ -z "${line//[[:space:]]/}" ]]; then
            printf '%s\n' "$(ui_paint 90 "$G_BAR")"
            continue
        fi
        body="${line#"${line%%[! ]*}"}"
        pad="$(( ${#line} - ${#body} - 2 ))"
        [[ "$pad" -lt 0 ]] && pad=0
        mark=""
        color=""
        case "$body" in
            "🔧 "*|"🧹 "*)
                body="${body#* }"
                body="${body//.../}"
                body="${body% 시작}"
                printf '%s\n%s  %s\n' "$(ui_paint 90 "$G_BAR")" "$(ui_paint 32 "$G_SECTION")" "$(ui_paint 1 "$body")"
                continue ;;
            "── "*)
                body="${body#── }"
                body="${body%% ─*}"
                printf '%s  %s\n' "$(ui_paint 90 "$G_BAR")" "$(ui_paint 1 "$body")"
                continue ;;
            "["[0-9]"/"[0-9]"] "*)
                printf '%s  %s\n' "$(ui_paint 90 "$G_BAR")" "$(ui_paint 1 "${body%...}")"
                continue ;;
            "✅ "*|"🎉 "*) mark="$G_OK"; color=32 ;;
            "⚠️ "*|"⚠ "*) mark="$G_WARN"; color=33 ;;
            "❌ "*) mark="$G_ERR"; color=31 ;;
            "🧪 "*) mark="$G_DRY"; color=36 ;;
            "ℹ️ "*|"💾 "*|"🗑️ "*|"📦 "*|"🐍 "*|"🧾 "*|"🔁 "*|"• "*) mark="$G_DOT"; color=90 ;;
        esac
        # 닫는 가로줄(──────)만 있는 줄은 거터가 대신하므로 버린다.
        [[ -z "${body//─/}" ]] && continue
        if [[ -n "$mark" ]]; then
            body="${body#* }"
            body="${body#"${body%%[! ]*}"}"
            body="$(ui_paint "$color" "$mark") $body"
        fi
        printf '%s  %*s%s\n' "$(ui_paint 90 "$G_BAR")" "$pad" "" "$body"
    done
}

# 워커가 찍는 python 출력이 파이프 너머에서 블록 버퍼링되면 stderr 경고와 순서가 뒤바뀐다.
export PYTHONUNBUFFERED=1

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
                    all) RUN_HOOKS=1; RUN_AGENTSMD=1; RUN_KEYBINDS=1; RUN_SKILLS=1 ;;
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
            OMC) [[ "$value" == "1" ]] && RUN_OMC=1 ;;
            OUTPUT_STYLE) [[ "$value" == "1" ]] && RUN_OUTPUT_STYLE=1 ;;
            MODS) [[ "$value" == "1" ]] && RUN_MODS=1 ;;
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

# 설치 출력은 온보딩과 같은 모양의 블록 하나로 묶는다. 끝줄은 어떤 경로로 끝나든(set -e 로
# 워커 실패에 끊겨도) 종료 코드를 보고 찍는다.
ui_close() {
    local rc=$?
    local what="설치"
    [[ "$UNINSTALL" -eq 1 ]] && what="제거"
    printf '%s\n' "$(ui_paint 90 "$G_BAR")"
    if [[ "$rc" -ne 0 ]]; then
        printf '%s  %s\n\n' "$(ui_paint 90 "$G_END")" "$(ui_paint 31 "$what 실패 (exit $rc) — 위 메시지를 확인하세요.")"
    elif [[ "$DRY_RUN" -eq 1 ]]; then
        printf '%s  %s\n\n' "$(ui_paint 90 "$G_END")" "DRY RUN 완료 — 아무것도 바꾸지 않았습니다."
    else
        printf '%s  %s\n\n' "$(ui_paint 90 "$G_END")" "$what 완료"
    fi
}
printf '\n%s  %s\n' "$(ui_paint 90 "$G_START")" "$(ui_paint 1 "claude-code-setup")"
trap ui_close EXIT

# uninstall: --keybinds --uninstall 은 키바인드만. 아니면 훅 다음 키바인드.
# exec 하면 키바인드 uninstall 이 실행되지 않는다.
if [[ "$UNINSTALL" -eq 1 ]]; then
    # 제거도 설치와 같은 범위 규칙을 따른다. 범위를 지정했으면 그것만 지운다 —
    # --hooks --uninstall 이 키바인딩까지 지우면 "--hooks 는 키바인딩을 건드리지
    # 않는다"(핵심 결정 4)를 제거 쪽에서만 어기는 것이 된다.
    UN_KEYBINDS="$RUN_KEYBINDS"
    UN_HOOKS="$RUN_HOOKS"
    UN_SKILLS="$RUN_SKILLS"
    UN_OMC="$RUN_OMC"
    UN_OUTPUT_STYLE="$RUN_OUTPUT_STYLE"
    UN_MODS="$RUN_MODS"
    if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 && "$RUN_KEYBINDS" -eq 0 && "$RUN_SKILLS" -eq 0 && "$RUN_OMC" -eq 0 && "$RUN_OUTPUT_STYLE" -eq 0 && "$RUN_MODS" -eq 0 ]]; then
        UN_KEYBINDS=1
        UN_HOOKS=1
        UN_SKILLS=1
        UN_OMC=1
        UN_OUTPUT_STYLE=1
        UN_MODS=1
    fi
    # 키바인드를 '먼저' 지운다. 훅 uninstall 이 매니페스트를 손보는데, 키바인드 제거는
    # 그 영수증(tmux_added 등)이 있어야 '우리가 넣은 것' 과 사용자 것을 구분할 수 있다.
    # set -e 아래라 한쪽이 실패해도 나머지가 돌도록 종료 코드를 받아 둔다.
    kb_exit=0
    hooks_exit=0
    skills_exit=0
    if [[ "$UN_SKILLS" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_skills.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format || skills_exit=$?
    fi
    # mod·출력 스타일·캐시 TTL HUD 영수증도 매니페스트에 있으므로 훅 uninstall 보다 먼저 되돌린다.
    # 이 셋은 설치(OMC → 출력 스타일 → mod)의 역순으로 되돌린다 — settings.json 을 처음 만든
    # 워커가 마지막에 와야, 다른 워커의 키가 다 빠진 뒤 빈 파일을 지울 수 있다.
    mods_exit=0
    if [[ "$UN_MODS" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_mods.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format || mods_exit=$?
    fi
    style_exit=0
    if [[ "$UN_OUTPUT_STYLE" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_output_style.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format || style_exit=$?
    fi
    omc_exit=0
    if [[ "$UN_OMC" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_omc.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format || omc_exit=$?
    fi
    if [[ "$UN_KEYBINDS" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_keybinds.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format || kb_exit=$?
    fi
    if [[ "$UN_HOOKS" -eq 1 ]]; then
        bash "$SCRIPT_DIR/setup_hooks.sh" --uninstall ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format || hooks_exit=$?
    fi
    [[ "$hooks_exit" -ne 0 ]] && exit "$hooks_exit"
    [[ "$skills_exit" -ne 0 ]] && exit "$skills_exit"
    [[ "$omc_exit" -ne 0 ]] && exit "$omc_exit"
    [[ "$style_exit" -ne 0 ]] && exit "$style_exit"
    [[ "$mods_exit" -ne 0 ]] && exit "$mods_exit"
    exit "$kb_exit"
fi

# 범위 플래그가 하나도 없으면 전체 설치 (훅 + AGENTS.md + 키바인드 + 스킬).
# --hooks 만 / --agentsmd 만 / --keybinds 만 / --omc 만이면 그 범위만.
# OMC·fluent-korean 은 서드파티 플러그인이라, mod 는 최신 Claude Code 에서만 동작해서 기본 전체
# 설치에 끼우지 않는다 — 명시적으로 고른 경우에만.
if [[ "$RUN_HOOKS" -eq 0 && "$RUN_AGENTSMD" -eq 0 && "$RUN_KEYBINDS" -eq 0 && "$RUN_SKILLS" -eq 0 && "$RUN_OMC" -eq 0 && "$RUN_OUTPUT_STYLE" -eq 0 && "$RUN_MODS" -eq 0 ]]; then
    RUN_HOOKS=1
    RUN_AGENTSMD=1
    RUN_KEYBINDS=1
    RUN_SKILLS=1
fi

if [[ "$RUN_HOOKS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_hooks.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${MODE_FLAG[@]+"${MODE_FLAG[@]}"} | ui_format
fi

if [[ "$RUN_AGENTSMD" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_agentsmd.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${FORCE_FLAG[@]+"${FORCE_FLAG[@]}"} ${HARNESS_FLAG[@]+"${HARNESS_FLAG[@]}"} | ui_format
fi

if [[ "$RUN_KEYBINDS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_keybinds.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} ${NEWLINE_FLAG[@]+"${NEWLINE_FLAG[@]}"} | ui_format
fi

if [[ "$RUN_OMC" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_omc.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format
fi

if [[ "$RUN_OUTPUT_STYLE" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_output_style.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format
fi

if [[ "$RUN_MODS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_mods.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format
fi

if [[ "$RUN_SKILLS" -eq 1 ]]; then
    bash "$SCRIPT_DIR/setup_skills.sh" ${DRY_FLAG[@]+"${DRY_FLAG[@]}"} | ui_format
fi
