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

# resolve_python_command 가 실패했을 때 이 환경에서 Python 3 을 설치하는 명령을 stderr 로 안내한다.
# 설치는 하지 않는다 — 런타임 설치는 되돌리기 어렵고 uninstall 대칭 밖이라 사용자가 직접 한다.
print_python_install_hint() {
    local cmd=""
    if [[ "$(uname -s)" == "Darwin" ]]; then
        cmd="brew install python"
    elif command -v apt-get &>/dev/null; then
        cmd="sudo apt-get update && sudo apt-get install -y python3"
    elif command -v dnf &>/dev/null; then
        cmd="sudo dnf install -y python3"
    elif command -v yum &>/dev/null; then
        cmd="sudo yum install -y python3"
    elif command -v pacman &>/dev/null; then
        cmd="sudo pacman -S --needed python"
    elif command -v zypper &>/dev/null; then
        cmd="sudo zypper install -y python3"
    elif command -v apk &>/dev/null; then
        cmd="sudo apk add python3"
    fi
    {
        echo "   How to install Python 3:"
        if [[ -n "$cmd" ]]; then
            echo "     $cmd"
        else
            echo "     Install python3 with your distribution package manager (https://www.python.org/downloads/)."
        fi
        echo "   Run again after installing."
    } >&2
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
        mkdir -p "$(dirname "$hooks_dir/$dest")"
        cp "$src" "$hooks_dir/$dest"
        chmod +x "$hooks_dir/$dest"
        echo "$hooks_dir/$dest"
    done
}

invoke_settings_merge() {
    # args: py_exe merge_script fragment settings_path dry_run(0/1) py_invoke hooks_dir [manifest_path] [hook_files_csv] [default_mode]
    # res/settings.json 조각(SSoT)의 자리표시자를 치환하고 대상 settings.json에 외과적으로 병합한다.
    # manifest_path 를 주면 (비 dry-run) merge 가 설치 영수증까지 기록한다.
    # default_mode 를 주면 조각의 permissions.defaultMode 를 그 값으로 바꿔 병합한다 (온보딩 선택).
    local py_exe="$1" merge_script="$2" fragment="$3" settings_path="$4"
    local dry_run="$5" py_invoke="$6" hooks_dir="$7" manifest_path="${8:-}" hook_files_csv="${9:-}"
    local default_mode="${10:-}"

    # bash 3.2 (macOS 기본) 는 set -u 에서 빈 배열 확장을 unbound variable 로 본다.
    local mode_flag=()
    [[ -n "$default_mode" ]] && mode_flag=(--default-mode "$default_mode")

    "$py_exe" -X utf8 "$merge_script" ${mode_flag[@]+"${mode_flag[@]}"} \
        "$fragment" "$settings_path" "$dry_run" "$py_invoke" "$hooks_dir" "$manifest_path" "$hook_files_csv"
}

uninstall_hooks() {
    # args: py_exe merge_script claude_dir hooks_dir settings_path dry_run(0/1)
    # 설치 영수증(매니페스트)을 근거로 '설치가 건드린 부분만' 정밀 복원한다:
    #   settings.json 훅 등록 해제 + 우리가 추가한 권한 항목만 제거 + defaultMode 원복(merge --uninstall),
    #   그리고 설치했던 훅 파일 + guard.log + 매니페스트 제거.
    local py_exe="$1" merge_script="$2" claude_dir="$3" hooks_dir="$4" settings_path="$5" dry_run="$6"
    local manifest="$claude_dir/$MANIFEST_NAME"

    # tr -d '\r': Windows python 의 print 는 \n 을 \r\n 으로 변환하므로 CR 을 제거한다.
    local files=""
    if [[ -f "$manifest" ]]; then
        files="$("$py_exe" -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1],encoding='utf-8')).get('hook_files',[])))" "$manifest" 2>/dev/null | tr -d '\r' || true)"
    fi
    if [[ -z "${files:-}" ]]; then
        files=$'danger_guard.py\nsecrets_guard.py\nsend_to_trash.py\nshims/rm\nshims/RmShim.psm1'
    fi

    echo "[1/2] Precisely restoring settings.json (only what the install touched)..."
    "$py_exe" -X utf8 "$merge_script" --uninstall "$settings_path" "$dry_run" "$manifest"

    echo ""
    echo "[2/2] Removing hook files + guard.log + manifest..."
    local f target
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        target="$hooks_dir/$f"
        [[ -f "$target" ]] || continue
        if [[ "$dry_run" -eq 1 ]]; then
            echo "  🧪 (dry-run) would remove: $target"
        else
            rm -f "$target"
            echo "  🗑️  Removed: $target"
        fi
    done <<< "$files"

    # 셰임 디렉터리는 파일을 다 걷어낸 뒤 비어 있을 때만 지운다.
    if [[ "$dry_run" -eq 0 && -d "$hooks_dir/shims" ]]; then
        rmdir "$hooks_dir/shims" 2>/dev/null || true
    fi

    # guard.log(설치 셀프테스트가 생성) 제거.
    for target in "$hooks_dir/guard.log"; do
        [[ -f "$target" ]] || continue
        if [[ "$dry_run" -eq 1 ]]; then
            echo "  🧪 (dry-run) would remove: $target"
        else
            rm -f "$target"
            echo "  🗑️  Removed: $target"
        fi
    done

    # 매니페스트: 다른 워커의 영수증(keybinds, omc_hud, output_style, mods)이 남아 있으면 그 섹션만 남기고 훅 흔적만 지운다.
    # 단계식 설치의 하네스·플러그인·MCP·Jarvis 유닛·AGENTS.md·스킬 기록도 남긴다. 이 제거는 앞의 것들을
    # 되돌리지 않고, 스킬은 범위에 따라 지우지 않을 수도 있다(스킬 소유는 스킬 영수증과 교차 확인). 그래서
    # 지우면 --uninstall --stages all 이 무엇을 이 셋업이 깔았는지 알 수 없다.
    # 통째로 지우면 키바인드 uninstall 이 '우리가 넣은 tmux 줄' 을, OMC uninstall 이 '우리가 넣은
    # refreshInterval' 을 식별할 근거를 잃는다.
    if [[ -f "$manifest" ]]; then
        if [[ "$dry_run" -eq 1 ]]; then
            echo "  🧪 (dry-run) would remove: $manifest"
        else
            "$py_exe" -c "import json,os,sys; p=sys.argv[1]; d=json.load(open(p,encoding='utf-8')); kept={k:d[k] for k in ('keybinds','omc_hud','output_style','mods','tool_installs','tool_attempts','harness_installs','plugins','mcp','jarvis_unit','agentsmd','skills','marketplaces') if isinstance(d,dict) and d.get(k)}; json.dump(kept,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2) if kept else os.remove(p)" "$manifest" 2>/dev/null || rm -f "$manifest"
            if [[ -f "$manifest" ]]; then
                echo "  🧾 Kept: $manifest (only other workers' manifests remain)"
            else
                echo "  🗑️  Removed: $manifest"
            fi
        fi
    fi
}

run_hook_self_test() {
    # args: py_exe hook_path  "label1:::json1" ["label2:::json2" ...]
    # 판정 규칙은 SetupCommon.ps1 의 Invoke-HookSelfTest 와 같다. '출력이 비어 있음' 을 성공으로
    # 읽지 않는다 — 훅이 죽었거나 stdin 이 전달되지 않아도 출력은 비기 때문이다. 판정 없이
    # 통과하는 게 맞는 케이스는 라벨에 'expect pass' 를 넣어 구분한다. 성공한 케이스는 한 줄 요약으로
    # 접고, 실패한 케이스만 사유와 함께 보여 준다. 실패 건수를 종료 코드로 돌려준다.
    local py_exe="$1" hook_path="$2"
    shift 2
    local pair label json out rc decision failures=0 errf
    errf="$(mktemp)"
    for pair in "$@"; do
        label="${pair%%:::*}"
        json="${pair#*:::}"
        rc=0
        out="$(printf '%s' "$json" | "$py_exe" -X utf8 "$hook_path" 2>"$errf")" || rc=$?
        if [[ "$rc" -ne 0 ]]; then
            echo "  ❌ $label"
            echo "     Hook exited abnormally (exit $rc): $(cat "$errf")"
            failures=$((failures + 1))
            continue
        fi
        if [[ -z "$out" ]]; then
            if [[ "$label" != *"expect pass"* ]]; then
                echo "  ❌ $label"
                echo "     Empty decision — the guard lets this command through unchecked."
                failures=$((failures + 1))
            fi
            continue
        fi
        decision="$(printf '%s' "$out" | "$py_exe" -X utf8 -c 'import json, sys
h = json.load(sys.stdin).get("hookSpecificOutput", {})
print(h.get("permissionDecision") or ("updatedInput" if "updatedInput" in h else ""))' 2>/dev/null)" || decision=""
        if [[ -z "$decision" ]]; then
            echo "  ❌ $label"
            echo "     Could not parse the decision: $out"
            failures=$((failures + 1))
        fi
    done
    rm -f "$errf"
    if [[ "$failures" -eq 0 ]]; then
        echo "  ✅ Self-test $#/$# passed"
    fi
    return "$failures"
}

print_setup_report() {
    # args: dry_run(0/1) settings_path guard_log_path dependency_warning default_mode [installed_file...]
    # default_mode 가 비면 조각의 기본값(auto)이 쓰인 것으로 본다.
    local dry_run="$1" settings_path="$2" guard_log_path="$3" dependency_warning="$4"
    # 빈 문자열로 넘어와도(호출부가 변수를 그대로 전달) auto 로 본다.
    local default_mode="${5:-}"
    [[ -n "$default_mode" ]] || default_mode="auto"
    shift 5
    local installed=("$@")

    echo ""
    if [[ "$dry_run" -eq 1 ]]; then
        echo "🧪 DRY RUN complete — no real files were changed."
        echo "   To actually apply: run again without the --dry-run option."
        return 0
    fi

    echo "🎉 Setup complete!"
    echo ""
    echo "  Created/modified files (user level):"
    local f
    for f in "${installed[@]}"; do
        echo "    $f"
    done
    echo "    $settings_path"
    echo ""
    if [[ -n "$dependency_warning" ]]; then
        echo "  ⚠️ $dependency_warning"
    fi
    echo "  🔁 Important: the permissions/mode just changed apply from a 'new Claude Code session'. A running"
    echo "     session keeps the permission snapshot from its start (no live reload), so items just added to the allow"
    echo "     list, such as Artifact, may keep showing confirmation prompts in this session."
    echo "     Quit and restart Claude Code (new session) and the prompts go away."
    echo "  ⚠️ Scope change notice: these hooks and defaultMode($default_mode) now apply to every"
    echo "     project this user opens (not limited to one project)."
    if [[ "$default_mode" == "auto" ]]; then
        echo "  ℹ️ defaultMode is set to 'auto', but for auto mode to actually turn on, the account must meet"
        echo "     eligibility requirements such as Claude Code v2.1.83+, a Team/Enterprise/API plan, and Sonnet 4.6"
        echo "     or later (still a research preview). Cycle modes with Shift+Tab in a session"
        echo "     to check that auto shows up."
    elif [[ "$default_mode" == "bypassPermissions" ]]; then
        echo "  ⚠️ defaultMode is set to 'bypassPermissions' — all Claude Code permission checks"
        echo "     are skipped. The guard hooks just installed (rm to trash, git backup, secret checks)"
        echo "     still work, but commands the hooks do not judge run without confirmation."
        echo "     To revert, set permissions.defaultMode in $settings_path to 'auto'."
    fi
    echo "  Audit log: $guard_log_path"
}
