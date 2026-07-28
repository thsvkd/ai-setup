#!/usr/bin/env bash
#
# 전체 테스트 스위트 실행 (macOS/Linux)
#
#   이 저장소는 서로 다른 러너 세 개로 테스트한다 — pytest(훅 정책·git 실측·병합 엔진·셋업
#   스크립트), bats(bash 셋업 스크립트), Pester(PowerShell 셋업 스크립트). 러너마다 설치
#   여부가 달라서, 하나가 없다고 전체가 멈추거나 반대로 "없어서 안 돌았는데 통과처럼 보이는"
#   일이 없도록 통과/실패/건너뜀을 구분해 마지막에 한 번에 보고한다.
#
#   첫 실패에서 멈추지 않고 가능한 스위트를 전부 돌린다 — 실패가 하나뿐인지 여럿인지 알아야
#   원인을 좁힐 수 있기 때문이다. 종료 코드는 '실행된' 스위트 중 하나라도 실패하면 1이다.
#
# 사용법:
#   bash scripts/test.sh                    # 있는 러너로 전부 실행
#   bash scripts/test.sh --python-only      # pytest 만
#   bash scripts/test.sh --strict           # 러너가 없어 건너뛴 것도 실패로 취급 (CI용)
#   bash scripts/test.sh -k git_guard       # 남은 인자는 pytest 로 그대로 전달
#
#   CLAUDE_TEST_PYTHON=/path/to/python bash scripts/test.sh
#       pytest 를 돌릴 인터프리터를 직접 지정한다. venv 안이거나 pytest 가 python3/python
#       이라는 이름으로 잡히지 않는 환경에서 필요하다.
#
# set -e 는 쓰지 않는다: 스위트 하나가 실패해도 나머지를 계속 돌려야 한다.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=lib/setup_common.sh
source "$SCRIPT_DIR/lib/setup_common.sh"

print_usage() {
    cat <<'EOF'
claude-code-setup — 테스트 스위트 실행

사용법: bash scripts/test.sh [옵션] [pytest 인자...]
  (옵션 없음)     설치된 러너로 pytest + bats + Pester 전부 실행
  --python-only   pytest 만 실행
  --strict        러너 미설치로 건너뛴 스위트도 실패로 취급 (종료 코드 1)
  --help, -h      이 도움말

옵션이 아닌 나머지 인자는 pytest 에 그대로 전달된다 (예: -k, -x, --lf).

환경 변수:
  CLAUDE_TEST_PYTHON   pytest 를 돌릴 인터프리터 경로 (지정하면 자동 탐색을 건너뛴다)
EOF
}

PYTHON_ONLY=0
STRICT=0
PYTEST_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --python-only) PYTHON_ONLY=1 ;;
        --strict) STRICT=1 ;;
        --help|-h) print_usage; exit 0 ;;
        *) PYTEST_ARGS+=("$arg") ;;
    esac
done

# 스위트별 결과. 이름을 순서대로 모으고 상태(pass/fail/skip)와 사유를 나란히 쌓는다
# (bash 3.2 는 연관 배열이 없어 인덱스가 맞물린 배열 세 개를 쓴다).
SUITE_NAMES=()
SUITE_STATES=()
SUITE_NOTES=()

record() {
    SUITE_NAMES+=("$1")
    SUITE_STATES+=("$2")
    SUITE_NOTES+=("$3")
}

section() {
    echo ""
    echo "── $1 ─────────────────────────────────────"
}

resolve_pytest_python() {
    # setup_common.sh 의 resolve_python_command 는 '아무 python' 이면 되지만(병합 스크립트를
    # 돌리는 용도), 테스트 러너는 'pytest 가 설치된 python' 이 필요하다 — 요구사항이 다르다.
    # 실제로 python3=Homebrew 3.14(pytest 없음), python=/usr/bin 3.11(pytest 있음) 처럼
    # 갈리는 머신이 흔해서, 첫 번째로 찾은 python 을 그냥 쓰면 "pytest 미설치"로 오판한다.
    local candidate
    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null && "$candidate" -c "import pytest" 2>/dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# --- pytest: 이 저장소의 핵심 스위트 (훅 정책 + git 실측 + 병합 엔진 + 셋업 스크립트) ---
run_pytest_suite() {
    local py
    if [[ -n "${CLAUDE_TEST_PYTHON:-}" ]]; then
        # 명시적으로 지정한 인터프리터를 쓸 수 없는 것은 '러너가 없어 건너뜀' 이 아니라 오류다.
        # 조용히 skip 하면 pytest 를 돌리라고 지정해 놓고 아무것도 안 돈 상태가 통과처럼 보인다.
        py="$CLAUDE_TEST_PYTHON"
        if ! "$py" -c "import pytest" 2>/dev/null; then
            echo "CLAUDE_TEST_PYTHON=$py 로 pytest 를 import 하지 못했습니다."
            record "pytest" "fail" "지정한 인터프리터에 pytest 없음"
            return
        fi
    else
        py="$(resolve_pytest_python)" || py=""
    fi

    if [[ -z "$py" ]]; then
        if resolve_python_command >/dev/null 2>&1; then
            echo "python 은 있으나 pytest 가 설치돼 있지 않습니다. ($(resolve_python_command) -m pip install pytest)"
            echo "  (pytest 가 다른 인터프리터에 있다면 CLAUDE_TEST_PYTHON 으로 지정할 수 있습니다.)"
            record "pytest" "skip" "pytest 미설치"
        else
            echo "python3/python 을 찾지 못했습니다."
            record "pytest" "skip" "python 없음"
        fi
        return
    fi

    echo "인터프리터: $py ($("$py" -V 2>&1))"
    # -rs: 스킵된 테스트의 '사유'까지 출력한다. 이 저장소의 스킵은 대부분 환경 조건부라
    # (macOS 전용 경로, 3.9.x 인터프리터 유무) 무엇이 검증되지 '않았는지' 보이는 게 중요하다.
    "$py" -m pytest "$REPO_ROOT/tests" -rs ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
    if [[ $? -eq 0 ]]; then record "pytest" "pass" ""; else record "pytest" "fail" ""; fi
}

section "pytest"
run_pytest_suite

# --python-only 는 '요청하지 않은' 것이므로 아예 기록하지 않는다 — 러너가 없어서 못 돌린
# skip 과 섞이면 --strict 가 사용자가 직접 고른 선택까지 실패로 만든다.
if [[ "$PYTHON_ONLY" -eq 1 ]]; then
    echo ""
    echo "(--python-only: bats/Pester 는 요청되지 않아 실행하지 않습니다)"
else
    # --- bats: bash 셋업 스크립트. pytest 도 셋업 스크립트를 커버하지만 bats 는 셸 관점에서 본다 ---
    section "bats"
    if ! command -v bats &>/dev/null; then
        echo "bats 가 없어 건너뜁니다. (brew install bats-core / npm i -g bats)"
        record "bats (setup.bats)" "skip" "bats 미설치"
    else
        bats "$REPO_ROOT/tests/setup.bats"
        if [[ $? -eq 0 ]]; then record "bats (setup.bats)" "pass" ""; else record "bats (setup.bats)" "fail" ""; fi
    fi

    # --- Pester: PowerShell 셋업 스크립트. POSIX 머신에도 pwsh 가 있으면 돌릴 가치가 있다 ---
    section "Pester"
    PWSH=""
    for candidate in pwsh powershell; do
        command -v "$candidate" &>/dev/null && { PWSH="$candidate"; break; }
    done
    if [[ -z "$PWSH" ]]; then
        echo "pwsh/powershell 이 없어 건너뜁니다. — Windows 훅의 PowerShell 경로는 이 스위트로만 실행 검증된다."
        record "Pester (Setup.Tests.ps1)" "skip" "pwsh 미설치"
    else
        "$PWSH" -NoProfile -Command "Invoke-Pester '$REPO_ROOT/tests/Setup.Tests.ps1' -Output Detailed"
        if [[ $? -eq 0 ]]; then record "Pester (Setup.Tests.ps1)" "pass" ""; else record "Pester (Setup.Tests.ps1)" "fail" ""; fi
    fi
fi

# --- 종합 리포트 ---
echo ""
echo "══ 결과 ═══════════════════════════════════════"
failed=0
skipped=0
ran=0
for i in "${!SUITE_NAMES[@]}"; do
    name="${SUITE_NAMES[$i]}"
    state="${SUITE_STATES[$i]}"
    note="${SUITE_NOTES[$i]}"
    case "$state" in
        pass) printf '  ✅ %-26s 통과\n' "$name"; ran=$((ran + 1)) ;;
        fail) printf '  ❌ %-26s 실패\n' "$name"; failed=$((failed + 1)); ran=$((ran + 1)) ;;
        skip) printf '  ⏭️  %-26s 건너뜀 (%s)\n' "$name" "$note"; skipped=$((skipped + 1)) ;;
    esac
done

if [[ "$skipped" -gt 0 ]]; then
    echo ""
    echo "  건너뛴 스위트는 '통과'가 아니라 '검증 안 됨' 이다."
fi

echo ""
if [[ "$failed" -gt 0 ]]; then
    echo "실패한 스위트: ${failed}개"
    exit 1
fi
# 하나도 못 돌린 것은 통과가 아니다 — 테스트를 요청했는데 아무것도 검증되지 않은 상태다.
if [[ "$ran" -eq 0 ]]; then
    echo "실행된 스위트가 없습니다. 최소한 pytest 는 돌 수 있어야 합니다."
    exit 1
fi
if [[ "$STRICT" -eq 1 && "$skipped" -gt 0 ]]; then
    echo "--strict: 건너뛴 스위트 ${skipped}개를 실패로 취급합니다."
    exit 1
fi
echo "실행된 스위트 ${ran}개 모두 통과."
exit 0
