#!/usr/bin/env bash
# update-ai — 설치된 AI 하네스·도구·플러그인을 한 번에 최신으로 (macOS/Linux).
# 구현은 res/update/update_ai.py 하나다. 이 파일은 PATH 를 보강하고 Python 을 찾아 넘기기만 한다.
#   bash scripts/update-ai.sh [--check] [--only a,b] [--allow-interrupt] [target ...]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/setup_common.sh
source "$SCRIPT_DIR/lib/setup_common.sh"

# cron·ssh 에서는 로그인 셸의 PATH 가 빠진다. 사용자 bin 과 nvm 의 node 를 앞에 붙인다.
# nvm 은 높은 버전이 먼저 오게 숫자로 정렬한다(사전순이면 v24.9.0 이 v24.19.0 보다 앞선다).
# bash 3.2 의 set -e 는 루프의 마지막 '[[ ]] && ...' 실패로도 끝날 수 있어 if 로 쓴다.
extra=''
for d in "$HOME/.local/bin" "$HOME/.grok/bin" "$HOME/.opencode/bin" "$HOME/.npm-global/bin"; do
    if [[ -d "$d" ]]; then extra="${extra:+$extra:}$d"; fi
done
if [[ -d "$HOME/.nvm/versions/node" ]]; then
    while IFS= read -r v; do
        if [[ -n "$v" && -d "$HOME/.nvm/versions/node/v$v/bin" ]]; then extra="${extra:+$extra:}$HOME/.nvm/versions/node/v$v/bin"; fi
    done < <(cd "$HOME/.nvm/versions/node" && for d in v*; do printf '%s\n' "${d#v}"; done | sort -t. -k1,1nr -k2,2nr -k3,3nr)
fi
for d in /opt/homebrew/bin /usr/local/bin; do
    if [[ -d "$d" ]]; then extra="${extra:+$extra:}$d"; fi
done
export PATH="${extra:+$extra:}$PATH"

if ! PY="$(resolve_python_command)"; then
    echo "Python 3 is required." >&2
    print_python_install_hint
    exit 2
fi
exec "$PY" -X utf8 "$REPO_ROOT/res/update/update_ai.py" "$@"
