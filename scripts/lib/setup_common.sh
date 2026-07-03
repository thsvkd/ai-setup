#!/usr/bin/env bash
#
# scripts/setup_hooks.sh, scripts/setup_agentsmd.sh 가 source 하는 공용 오케스트레이션 함수 모음.
# dry-run 홈 스캐폴딩, 훅 파일 설치, settings.json 조각(res/settings.json) 병합 실행,
# 훅 셀프테스트, 매니페스트 기록/제거(uninstall), 최종 리포트 출력을 담당한다.
# OS 전용 의존성 설치(trash-cli 등)는 호출부가 하나뿐이라 setup_hooks.sh 에 그대로 둔다.

# 설치가 무엇을 남겼는지 기록하는 매니페스트 파일명 (~/.claude/ 아래).
MANIFEST_NAME=".claude-code-setup.json"

resolve_python_command() {
    if command -v python3 &>/dev/null; then
        echo "python3"
    elif command -v python &>/dev/null; then
        echo "python"
    else
        return 1
    fi
}

resolve_install_home() {
    # args: dry_run(0/1) real_home  [seed_file...]
    local dry_run="$1" real_home="$2"
    shift 2
    local seed_files=("$@")

    if [[ "$dry_run" -eq 1 ]]; then
        local work_home
        work_home="$(mktemp -d)"
        mkdir -p "$work_home/.claude"
        local seed src dst
        for seed in "${seed_files[@]}"; do
            src="$real_home/.claude/$seed"
            if [[ -f "$src" ]]; then
                dst="$work_home/.claude/$seed"
                mkdir -p "$(dirname "$dst")"
                cp "$src" "$dst"
            fi
        done
        echo "$work_home"
    else
        echo "$real_home"
    fi
}

install_hook_files() {
    # args: hooks_dir  "source1:dest1" ["source2:dest2" ...]
    # 설치된 절대 경로를 한 줄씩 stdout으로 출력한다.
    local hooks_dir="$1"
    shift
    mkdir -p "$hooks_dir"
    local pair src dest
    for pair in "$@"; do
        src="${pair%%:*}"
        dest="${pair#*:}"
        cp "$src" "$hooks_dir/$dest"
        chmod +x "$hooks_dir/$dest"
        echo "$hooks_dir/$dest"
    done
}

invoke_settings_merge() {
    # args: py_exe merge_script fragment settings_path dry_run(0/1) py_invoke hooks_dir
    # res/settings.json 조각(SSoT)의 자리표시자를 치환하고 대상 settings.json에 외과적으로 병합.
    local py_exe="$1" merge_script="$2" fragment="$3" settings_path="$4"
    local dry_run="$5" py_invoke="$6" hooks_dir="$7"
    "$py_exe" -X utf8 "$merge_script" "$fragment" "$settings_path" "$dry_run" "$py_invoke" "$hooks_dir"
}

write_hook_manifest() {
    # args: py_exe manifest_path hooks_dir settings_path  file1 [file2 ...]
    # 설치된 훅 파일 목록을 JSON 매니페스트로 기록한다 (uninstall 이 참조).
    local py_exe="$1" manifest_path="$2" hooks_dir="$3" settings_path="$4"
    shift 4
    "$py_exe" - "$manifest_path" "$hooks_dir" "$settings_path" "$@" <<'PYEOF'
import json
import sys
manifest_path, hooks_dir, settings_path, *files = sys.argv[1:]
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump({
        "version": 1,
        "hooks_dir": hooks_dir,
        "settings_path": settings_path,
        "hook_files": files,
    }, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYEOF
}

uninstall_hooks() {
    # args: py_exe merge_script claude_dir hooks_dir settings_path dry_run(0/1)
    # settings.json 에서 우리 훅 등록을 해제하고(백업 후), 설치했던 훅 파일을 제거한다.
    # 권한(allow/deny/defaultMode)은 건드리지 않는다 — 예측 가능한 최소 되돌리기.
    local py_exe="$1" merge_script="$2" claude_dir="$3" hooks_dir="$4" settings_path="$5" dry_run="$6"
    local manifest="$claude_dir/$MANIFEST_NAME"

    # tr -d '\r': Windows python 의 print 는 \n 을 \r\n 으로 변환하므로 CR 을 제거해야
    # 파일명에 캐리지리턴이 붙어 rm 대상이 어긋나는 것을 막는다.
    local files=""
    if [[ -f "$manifest" ]]; then
        files="$("$py_exe" -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1],encoding='utf-8')).get('hook_files',[])))" "$manifest" 2>/dev/null | tr -d '\r' || true)"
    fi
    if [[ -z "${files:-}" ]]; then
        files=$'danger_guard.py\nsecrets_guard.py\nsend_to_trash.py'
    fi

    echo "[1/2] settings.json 에서 훅 등록 해제..."
    "$py_exe" -X utf8 "$merge_script" --remove "$settings_path" "$dry_run" "danger_guard.py,secrets_guard.py"

    echo ""
    echo "[2/2] 훅 파일 제거..."
    local f target
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        target="$hooks_dir/$f"
        [[ -f "$target" ]] || continue
        if [[ "$dry_run" -eq 1 ]]; then
            echo "  🧪 (dry-run) 제거 예정: $target"
        else
            rm -f "$target"
            echo "  🗑️  제거: $target"
        fi
    done <<< "$files"

    if [[ "$dry_run" -ne 1 && -f "$manifest" ]]; then
        rm -f "$manifest"
    fi
}

run_hook_self_test() {
    # args: py_exe hook_path  "label1:::json1" ["label2:::json2" ...]
    local py_exe="$1" hook_path="$2"
    shift 2
    local pair label json
    for pair in "$@"; do
        label="${pair%%:::*}"
        json="${pair#*:::}"
        echo "  🧪 $label"
        echo "     $(echo "$json" | "$py_exe" -X utf8 "$hook_path")"
    done
}

print_setup_report() {
    # args: dry_run(0/1) settings_path guard_log_path dependency_warning  [installed_file...]
    local dry_run="$1" settings_path="$2" guard_log_path="$3" dependency_warning="$4"
    shift 4
    local installed=("$@")

    echo ""
    if [[ "$dry_run" -eq 1 ]]; then
        echo "🧪 DRY RUN 완료 — 실제 파일은 하나도 바뀌지 않았습니다."
        echo "   실제로 적용하려면: --dry-run 옵션 없이 다시 실행하세요."
        return 0
    fi

    echo "🎉 초기화 완료!"
    echo ""
    echo "  생성/수정된 파일 (유저 레벨):"
    local f
    for f in "${installed[@]}"; do
        echo "    $f"
    done
    echo "    $settings_path"
    echo ""
    if [[ -n "$dependency_warning" ]]; then
        echo "  ⚠️ $dependency_warning"
    fi
    echo "  ⚠️ 범위 변경 안내: 이 훅과 defaultMode(auto)는 이제 이 사용자가 여는 모든"
    echo "     프로젝트에 적용됩니다 (특정 프로젝트 한정이 아님)."
    echo "  ℹ️ defaultMode를 'auto'로 설정했지만, 실제로 auto 모드가 켜지려면 계정이"
    echo "     Claude Code v2.1.83+, Team/Enterprise/API 플랜, Sonnet 4.6 이상 모델 등"
    echo "     자격 요건을 충족해야 합니다 (아직 research preview). 세션에서 Shift+Tab 으로"
    echo "     모드를 순환시켜 auto 가 뜨는지 직접 확인해보세요."
    echo "  감사 로그: $guard_log_path"
}
