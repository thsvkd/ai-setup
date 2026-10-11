"""merge_and_diff.py 병합 엔진 테스트 (자리표시자 치환 + 외과적 병합 + 멱등성)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGE = ROOT / "res" / "hooks" / "merge_and_diff.py"
FRAGMENT = ROOT / "res" / "settings.json"


def run_merge(target: Path, dry="0", py="python3", hooks_dir="/home/u/.claude/hooks",
              manifest_path=None, hook_files="danger_guard.py,shims/rm", windows=False):
    args = [sys.executable, "-X", "utf8", str(MERGE)] + (["--windows"] if windows else [])
    args += [str(FRAGMENT), str(target), dry, py, hooks_dir]
    if manifest_path is not None:
        args += [str(manifest_path), hook_files]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    result = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    return proc, result


def run_uninstall(target: Path, manifest: Path, dry="0"):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(MERGE), "--uninstall", str(target), dry, str(manifest)],
        capture_output=True, text=True, encoding="utf-8",
    )
    result = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    return proc, result


def hook_commands(result):
    return [h["hooks"][0]["command"] for h in result["hooks"]["PreToolUse"]]


def test_merge_into_empty(tmp_path):
    proc, result = run_merge(tmp_path / "settings.json")
    assert proc.returncode == 0
    assert result["permissions"]["defaultMode"] == "auto"
    assert "Bash" in result["permissions"]["allow"]
    # force push/reset --hard 를 permissions.deny 로 막지 않는다 — 훅(danger_guard.py)이 브랜치
    # 이름 기준 ask/통과와 백업-후-허용을 직접 판단하므로, 여기서 deny/ask 로 선점하면 훅의
    # 판정(allow)이 permission 규칙에 의해 항상 밀린다(Claude Code 는 deny/ask 규칙이 훅보다
    # 우선한다). 그래서 settings.json 자체에는 git 관련 deny/ask 항목이 없어야 한다.
    assert "deny" not in result["permissions"] or not any(
        "git" in rule for rule in result["permissions"].get("deny", [])
    )
    assert not any("git" in rule for rule in result["permissions"].get("ask", []))


def test_placeholders_substituted(tmp_path):
    _, result = run_merge(tmp_path / "settings.json")
    cmds = hook_commands(result)
    assert any("danger_guard.py" in c for c in cmds)
    for c in cmds:
        assert "{{PY}}" not in c and "{{HOOKS_DIR}}" not in c
        assert "/home/u/.claude/hooks/" in c


def test_preserves_other_keys(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({
        "model": "sonnet",
        "env": {"X": "1"},
        "statusLine": {"type": "command", "command": "foo"},
        "permissions": {"allow": ["CustomTool"]},
    }), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0
    assert result["model"] == "sonnet"
    assert result["env"]["X"] == "1"                            # 사용자 env 키는 보존
    assert result["env"]["CLAUDE_CODE_SCROLL_SPEED"] == "3"     # 우리가 관리하는 env 키는 추가
    assert result["statusLine"]["command"] == "foo"
    assert "CustomTool" in result["permissions"]["allow"]   # 사용자 항목 보존
    assert "Bash" in result["permissions"]["allow"]         # 우리 항목 추가


def test_comment_not_propagated(tmp_path):
    _, result = run_merge(tmp_path / "settings.json")
    assert "_comment" not in result


def test_idempotent(tmp_path):
    target = tmp_path / "settings.json"
    run_merge(target)
    proc2, _ = run_merge(target)
    assert "no changes" in proc2.stdout


def test_dry_run_does_not_write(tmp_path):
    target = tmp_path / "settings.json"
    proc, result = run_merge(target, dry="1")
    assert proc.returncode == 0
    assert result is None   # 파일이 생성되지 않아야 함


def test_no_duplicate_hooks_on_rerun(tmp_path):
    target = tmp_path / "settings.json"
    run_merge(target)
    run_merge(target)
    _, result = run_merge(target)
    matchers = [h["matcher"] for h in result["hooks"]["PreToolUse"]]
    # 세 번 실행해도 훅은 한 번씩만 등록되어야 한다.
    assert matchers.count("Bash|PowerShell") == 1
    assert matchers == ["Bash|PowerShell"]


def test_backup_created_on_change(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"model": "sonnet"}), encoding="utf-8")
    run_merge(target)  # 변경 발생 → 백업 생성
    backups = list(tmp_path.glob("settings.json.bak.*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == {"model": "sonnet"}


def test_uninstall_deregisters_our_hooks(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"model": "x"}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    proc, result = run_uninstall(target, manifest)
    assert proc.returncode == 0
    assert not result.get("hooks", {}).get("PreToolUse")


def test_uninstall_deletes_settings_it_created(tmp_path):
    # 설치 전 settings.json 이 없었고 되돌린 뒤 빈 {} 만 남으면 파일 자체를 제거 → 설치 전 상태로 정확히 복원.
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    assert not target.exists()
    run_merge(target, manifest_path=manifest)
    assert target.exists()
    run_uninstall(target, manifest)
    assert not target.exists()


def test_uninstall_keeps_settings_it_did_not_create(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"model": "sonnet"}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    run_uninstall(target, manifest)
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"model": "sonnet"}


def test_uninstall_precisely_restores_prior_state(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({
        "model": "sonnet",
        "permissions": {"allow": ["CustomTool"], "defaultMode": "default"},
    }), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    installed = json.loads(target.read_text(encoding="utf-8"))
    assert "Bash" in installed["permissions"]["allow"]
    assert installed["permissions"]["defaultMode"] == "auto"

    _, result = run_uninstall(target, manifest)
    assert result["model"] == "sonnet"                          # 무관 키 보존
    assert result["permissions"]["allow"] == ["CustomTool"]     # 정확히 원복 (우리 항목만 제거)
    assert result["permissions"]["defaultMode"] == "default"    # defaultMode 원복
    assert not result["permissions"].get("deny")               # 우리가 추가한 deny 제거
    assert not result.get("hooks", {}).get("PreToolUse")       # 훅 제거


def test_uninstall_removes_defaultmode_when_absent_before(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"permissions": {"allow": ["X"]}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    assert "defaultMode" not in result.get("permissions", {})   # 설치 전 없었으므로 제거
    assert result["permissions"]["allow"] == ["X"]


def test_uninstall_does_not_clobber_user_changed_defaultmode(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)                   # auto 로 설정, before=None
    s = json.loads(target.read_text(encoding="utf-8"))
    s["permissions"]["defaultMode"] = "acceptEdits"             # 설치 후 사용자가 바꿈
    target.write_text(json.dumps(s), encoding="utf-8")
    _, result = run_uninstall(target, manifest)
    assert result["permissions"]["defaultMode"] == "acceptEdits"  # 우리 값이 아니므로 안 건드림


def test_uninstall_keeps_preexisting_item_we_also_use(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)                   # Bash 는 이미 있어 추가 안 됨
    _, result = run_uninstall(target, manifest)
    assert "Bash" in result["permissions"]["allow"]            # 사용자가 원래 갖고 있던 Bash 보존


def test_uninstall_keeps_foreign_hooks(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({
        "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "python other_hook.py"}]}
        ]}
    }), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    cmds = [h["hooks"][0]["command"] for h in result["hooks"]["PreToolUse"]]
    assert any("other_hook.py" in c for c in cmds)             # 남의 훅 보존
    assert not any("danger_guard.py" in c for c in cmds)       # 우리 것만 제거


def test_uninstall_without_manifest_only_removes_hooks(tmp_path):
    # 매니페스트가 없으면(구버전 설치) 권한은 되돌리지 못하고 훅 등록만 해제한다.
    target, manifest = tmp_path / "settings.json", tmp_path / "missing.json"
    run_merge(target)   # 매니페스트 없이 설치
    _, result = run_uninstall(target, manifest)
    assert not result.get("hooks", {}).get("PreToolUse")       # 훅은 제거됨
    assert "Bash" in result["permissions"]["allow"]            # 권한은 그대로 (영수증 없음)


def test_uninstall_dry_run_does_not_write(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    run_merge(target, manifest_path=manifest)
    before = target.read_text(encoding="utf-8")
    run_uninstall(target, manifest, dry="1")
    assert target.read_text(encoding="utf-8") == before


def test_install_writes_manifest_receipt(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"permissions": {"defaultMode": "default"}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest, hook_files="danger_guard.py,shims/rm")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["hook_files"] == ["danger_guard.py", "shims/rm"]
    assert "Bash" in m["added_allow"]
    assert m["default_mode_before"] == "default"
    assert m["default_mode_after"] == "auto"
    assert m["default_mode_changed"] is True


# --- ask 규칙 병합 (스킬 게이팅) — allow/deny 와 동일한 union + 정밀 복원 ---

def test_ask_merged_from_fragment(tmp_path):
    # 조각(res/settings.json)의 ask 항목(스킬 게이팅)이 빈 settings 에 합쳐진다.
    _, result = run_merge(tmp_path / "settings.json")
    perms = result["permissions"]
    assert "Skill(loop)" in perms.get("ask", [])   # 위험 스킬은 ask 로 게이팅
    assert "Skill" in perms["allow"]               # 그 외 스킬은 전체 자동 허용
    assert "Artifact" in perms["allow"]


def test_ask_union_preserves_user_items(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({
        "permissions": {"ask": ["Skill(my-own *)"]},
    }), encoding="utf-8")
    _, result = run_merge(target)
    ask = result["permissions"]["ask"]
    assert "Skill(my-own *)" in ask                # 사용자 항목 보존
    assert "Skill(loop)" in ask                    # 우리 항목 추가


def test_install_manifest_records_added_ask(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    run_merge(target, manifest_path=manifest)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert "Skill(loop)" in m["added_ask"]


def test_uninstall_removes_only_added_ask(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({
        "permissions": {"ask": ["Skill(my-own *)"]},
    }), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    assert result["permissions"].get("ask", []) == ["Skill(my-own *)"]  # 우리 것만 제거


# --- 스칼라 최상위 설정(model/effortLevel/language) — '없을 때만 추가' ---

def test_scalars_set_when_absent(tmp_path):
    # 아무 값도 없던 settings.json 에는 우리의 오피니언 기본값이 설치된다.
    _, result = run_merge(tmp_path / "settings.json")
    assert result["model"] == "opus"
    assert result["effortLevel"] == "xhigh"
    assert result["language"] == "korean"


def test_scalars_preserve_existing(tmp_path):
    # 사용자가 이미 고른 값은 절대 덮어쓰지 않는다. 없는 것만 채운다.
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"model": "sonnet", "effortLevel": "high"}), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0
    assert result["model"] == "sonnet"        # 보존
    assert result["effortLevel"] == "high"    # 보존
    assert result["language"] == "korean"     # 없던 것만 추가


def test_scalars_idempotent(tmp_path):
    target = tmp_path / "settings.json"
    run_merge(target)
    proc2, _ = run_merge(target)
    assert "no changes" in proc2.stdout   # 두 번째 실행은 이미 다 있어 변경 없음


def test_install_manifest_records_added_scalars(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"model": "sonnet"}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert "model" not in m["added_scalars"]              # 이미 있던 model 은 추가 목록에 없음
    assert m["added_scalars"]["effortLevel"] == "xhigh"
    assert m["added_scalars"]["language"] == "korean"


def test_uninstall_removes_only_added_scalars(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"model": "sonnet"}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    assert result["model"] == "sonnet"                   # 사용자 것 보존
    assert "effortLevel" not in result                   # 우리가 추가한 것만 제거
    assert "language" not in result


def test_uninstall_does_not_clobber_user_changed_scalar(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)            # effortLevel=xhigh 설치 (없던 값)
    s = json.loads(target.read_text(encoding="utf-8"))
    s["effortLevel"] = "high"                            # 설치 후 사용자가 바꿈
    target.write_text(json.dumps(s), encoding="utf-8")
    _, result = run_uninstall(target, manifest)
    assert result["effortLevel"] == "high"              # 우리 값이 아니므로 안 건드림
    assert "language" not in result                      # 안 바꾼 것은 정상 제거


# --- env 하위 관리 키(CLAUDE_CODE_SCROLL_SPEED) — scalar 와 동일한 '없을 때만 추가' + 정밀 복원 ---

def test_env_scroll_speed_set_when_absent(tmp_path):
    # env 가 아예 없던 settings 에는 우리의 스크롤 속도 env 키가 설치된다.
    _, result = run_merge(tmp_path / "settings.json")
    assert result["env"]["CLAUDE_CODE_SCROLL_SPEED"] == "3"


def test_env_preserves_user_value(tmp_path):
    # 사용자가 이미 값을 갖고 있으면 절대 덮어쓰지 않는다.
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"CLAUDE_CODE_SCROLL_SPEED": "10"}}), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0
    assert result["env"]["CLAUDE_CODE_SCROLL_SPEED"] == "10"   # 보존


def test_env_preserves_other_env_keys(tmp_path):
    # 우리 키는 추가하되, 사용자의 다른 env 키는 그대로 둔다 (returncode 0 — env 위반 아님).
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"MY_VAR": "keep"}}), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0
    assert result["env"]["MY_VAR"] == "keep"
    assert result["env"]["CLAUDE_CODE_SCROLL_SPEED"] == "3"


def test_install_manifest_records_added_env(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"env": {"CLAUDE_CODE_SCROLL_SPEED": "10"}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    # 이미 있던 값은 추가 목록에 없어야 한다 (없을 때만 추가하므로 이번엔 추가한 게 없다).
    assert "CLAUDE_CODE_SCROLL_SPEED" not in m["added_env"]


def test_uninstall_removes_only_added_env(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"env": {"MY_VAR": "keep"}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    assert result["env"] == {"MY_VAR": "keep"}                # 우리가 추가한 스크롤 키만 제거


def test_uninstall_deletes_env_object_when_it_only_held_our_key(tmp_path):
    # env 가 원래 없었고 우리 키만 넣었다면, 되돌린 뒤 env 객체 자체가 사라져야 한다.
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"model": "x"}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    assert json.loads(target.read_text(encoding="utf-8"))["env"]["CLAUDE_CODE_SCROLL_SPEED"] == "3"
    _, result = run_uninstall(target, manifest)
    assert "env" not in result


def test_uninstall_does_not_clobber_user_changed_env(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)            # scroll=3 설치 (없던 값)
    s = json.loads(target.read_text(encoding="utf-8"))
    s["env"]["CLAUDE_CODE_SCROLL_SPEED"] = "7"            # 설치 후 사용자가 바꿈
    target.write_text(json.dumps(s), encoding="utf-8")
    _, result = run_uninstall(target, manifest)
    assert result["env"]["CLAUDE_CODE_SCROLL_SPEED"] == "7"   # 우리 값이 아니므로 안 건드림


# --- Windows 전용 env 키(GRAFT_TEST_SYNC_RUN) — Windows 설치기(--windows)에서만 병합 ---

def test_windows_sets_graft_sync_wrapper_env(tmp_path):
    # graft 의 Stop 훅이 sync-run.js 대신 숨김 콘솔 래퍼를 띄우도록 훅 디렉터리의 래퍼를 가리킨다.
    _, result = run_merge(tmp_path / "settings.json", windows=True)
    assert result["env"]["GRAFT_TEST_SYNC_RUN"] == "/home/u/.claude/hooks/graft_sync_hidden.cjs"


def test_posix_skips_graft_sync_wrapper_env(tmp_path):
    # POSIX 에는 래퍼가 설치되지 않으므로, 키를 넣으면 graft 동기화가 멈춘다 — 넣지 않는다.
    _, result = run_merge(tmp_path / "settings.json")
    assert "GRAFT_TEST_SYNC_RUN" not in result["env"]


# --- 재실행(멱등)이 설치 영수증을 파괴하지 않는다 ---
#
# 두 번째 실행의 merge() 는 "추가한 것이 없다"는 빈 영수증을 낸다. 그걸 매니페스트에 그대로
# 덮어쓰면 첫 설치가 무엇을 바꿨는지 기억이 사라져, --uninstall 이 아무것도 되돌리지 못한다.

def test_rerun_keeps_added_allow_in_manifest(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    run_merge(target, manifest_path=manifest)
    run_merge(target, manifest_path=manifest)            # 멱등 재실행
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert "Bash" in m["added_allow"]
    assert not m["added_deny"]           # git 관련 deny 규칙은 더 이상 없다(훅이 직접 판단)
    assert "Skill(loop)" in m["added_ask"]


def test_rerun_keeps_default_mode_before(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"permissions": {"defaultMode": "acceptEdits"}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    run_merge(target, manifest_path=manifest)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["default_mode_before"] == "acceptEdits"     # 두 번째 실행은 auto->auto 라 changed=False 였다
    assert m["default_mode_changed"] is True


def test_rerun_keeps_added_scalars(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    run_merge(target, manifest_path=manifest)
    run_merge(target, manifest_path=manifest)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["added_scalars"] == {"model": "opus", "effortLevel": "xhigh", "language": "korean"}
    # env 하위 관리 키도 재실행(멱등) 후에도 영수증에 보존돼야 uninstall 이 되돌릴 수 있다.
    assert m["added_env"] == {"CLAUDE_CODE_SCROLL_SPEED": "3"}


def test_rerun_keeps_settings_existed_before(tmp_path):
    # 첫 설치 시점에 settings.json 이 없었다는 사실이 유지되어야 uninstall 이 파일을 지운다.
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    assert not target.exists()
    run_merge(target, manifest_path=manifest)
    run_merge(target, manifest_path=manifest)            # 이제는 존재한다
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["settings_existed_before"] is False
    run_uninstall(target, manifest)
    assert not target.exists()


def test_uninstall_after_rerun_restores_prior_state(tmp_path):
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({
        "model": "sonnet",
        "permissions": {"allow": ["CustomTool"], "defaultMode": "acceptEdits"},
    }), encoding="utf-8")
    for _ in range(3):
        run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    assert result["model"] == "sonnet"
    assert result["permissions"]["allow"] == ["CustomTool"]
    assert result["permissions"]["defaultMode"] == "acceptEdits"
    assert "effortLevel" not in result
    assert not result.get("hooks", {}).get("PreToolUse")


def test_reinstall_after_uninstall_starts_fresh_receipt(tmp_path):
    # uninstall 이 매니페스트를 지우므로, 재설치는 그 시점의 상태를 새 기준선으로 삼는다.
    target, manifest = tmp_path / "settings.json", tmp_path / "manifest.json"
    target.write_text(json.dumps({"permissions": {"defaultMode": "plan"}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    run_uninstall(target, manifest)
    manifest.unlink(missing_ok=True)                     # setup_hooks.sh 가 실제로 지운다
    run_merge(target, manifest_path=manifest)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["default_mode_before"] == "plan"


# --- 구버전 git deny/ask 규칙 마이그레이션 ---
# 배경: 예전 res/settings.json 은 Bash(git push *) 등을 permissions.deny·ask 로 막았다. 지금은
# 훅이 브랜치 이름을 보고 판단하지만, Claude Code 는 deny/ask 를 훅 판정보다 우선 적용하므로
# 기존 설치본에 그 규칙이 남아 있으면 새 git 정책이 통째로 죽는다. merge 는 원래 '추가만'
# 하므로, 이 규칙만은 설치 중에 제거해야 업그레이드한 사용자에게도 기능이 살아난다.

LEGACY = {
    "deny": [
        "Bash(git push *)",
        "Bash(git push --force*)",
        "Bash(git push -f*)",
        "Bash(git reset --hard *)",
        "PowerShell(git push *)",
        "PowerShell(git push --force*)",
        "PowerShell(git push -f*)",
        "PowerShell(git reset --hard *)",
    ],
    "ask": [
        "Bash(git push *)",
        "PowerShell(git push *)",
    ],
}


def legacy_settings():
    return json.dumps({"permissions": {k: list(v) for k, v in LEGACY.items()}})


def test_legacy_git_deny_rules_are_removed_on_install(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(legacy_settings(), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0
    for key in LEGACY:
        assert not any("git" in rule for rule in result["permissions"].get(key, [])), \
            "a leftover legacy git %s rule would defeat the hook's git policy" % key


def test_legacy_removal_leaves_user_own_deny_rules(tmp_path):
    """정확히 일치하는 문자열만 지운다. 사용자가 직접 넣은 규칙은 비슷해도 남아야 한다."""
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"permissions": {"deny": [
        "Bash(git push *)",            # 우리가 배포했던 것 → 제거
        "Bash(git push --force *)",     # 사용자가 직접 넣은 것 → 보존
        "Bash(rm -rf /*)",              # 무관 → 보존
    ]}}), encoding="utf-8")
    _, result = run_merge(target)
    deny = result["permissions"]["deny"]
    assert "Bash(git push *)" not in deny
    assert "Bash(git push --force *)" in deny
    assert "Bash(rm -rf /*)" in deny


def test_legacy_removal_when_no_such_rules_is_a_noop(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"permissions": {"deny": ["Bash(curl *)"]}}), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0
    assert result["permissions"]["deny"] == ["Bash(curl *)"]


def test_legacy_removal_is_recorded_in_manifest(tmp_path):
    target = tmp_path / "settings.json"
    manifest = tmp_path / "manifest.json"
    target.write_text(legacy_settings(), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    recorded = json.loads(manifest.read_text(encoding="utf-8"))["removed_legacy"]
    assert {k: sorted(v) for k, v in recorded.items()} == {k: sorted(v) for k, v in LEGACY.items()}


def test_legacy_removal_survives_reinstall_in_manifest(tmp_path):
    """멱등 재실행은 제거할 것이 없어 빈 결과를 낸다. 영수증이 덮어쓰이면 uninstall 이
    무엇을 되돌려야 하는지 잊는다 — added_* 와 동일하게 누적돼야 한다."""
    target = tmp_path / "settings.json"
    manifest = tmp_path / "manifest.json"
    target.write_text(legacy_settings(), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    run_merge(target, manifest_path=manifest)
    recorded = json.loads(manifest.read_text(encoding="utf-8"))["removed_legacy"]
    assert {k: sorted(v) for k, v in recorded.items()} == {k: sorted(v) for k, v in LEGACY.items()}


def test_uninstall_restores_removed_legacy_rules(tmp_path):
    """uninstall 은 '설치가 바꾼 것'을 되돌린다. 설치가 지운 규칙이라면 복원까지가 그 계약이다."""
    target = tmp_path / "settings.json"
    manifest = tmp_path / "manifest.json"
    target.write_text(legacy_settings(), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    for key, rules in LEGACY.items():
        assert sorted(result["permissions"][key]) == sorted(rules)


def test_dry_run_reports_legacy_removal_without_writing(tmp_path):
    target = tmp_path / "settings.json"
    original = legacy_settings()
    target.write_text(original, encoding="utf-8")
    proc, _ = run_merge(target, dry="1")
    assert proc.returncode == 0
    assert "legacy rule" in proc.stdout, proc.stdout
    assert target.read_text(encoding="utf-8") == original, "dry-run must not modify the file"


def test_retired_hook_registration_is_pruned(tmp_path):
    """우리가 배포했다가 그만둔 훅은 설치 중에 등록을 걷어낸다.

    그러지 않으면 새로 설치한 사람에게는 없고 업그레이드한 사람에게만 남는 유령 훅이 된다.
    """
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({
        "hooks": {"PreToolUse": [
            {"matcher": "Read|Write|Edit|MultiEdit",
             "hooks": [{"type": "command", "command": "python -X utf8 \"/h/secrets_guard.py\""}]},
            {"matcher": "Notification",
             "hooks": [{"type": "command", "command": "python /h/mine.py"}]},
        ]}
    }), encoding="utf-8")

    _, result = run_merge(target)
    cmds = hook_commands(result)
    assert not any("secrets_guard.py" in c for c in cmds)
    # 사용자가 직접 넣은 훅은 그대로 둔다.
    assert any("mine.py" in c for c in cmds)
    assert any("danger_guard.py" in c for c in cmds)


# --- autoMode.allow ---
# 훅이 가역성을 확인한 force push 를 auto mode 분류기가 다시 막지 않도록 허용 예외를 더한다.
# 목록에 "$defaults" 가 없으면 Claude Code 가 기본 allow 목록을 통째로 대체한다.

def _frag_auto_allow():
    return json.loads(FRAGMENT.read_text(encoding="utf-8"))["autoMode"]["allow"]


def test_auto_allow_is_created_with_defaults_when_absent(tmp_path):
    proc, result = run_merge(tmp_path / "settings.json")
    assert proc.returncode == 0, proc.stdout
    assert result["autoMode"]["allow"] == _frag_auto_allow()
    assert result["autoMode"]["allow"][0] == "$defaults"


def test_auto_allow_keeps_user_list_and_choice_to_drop_defaults(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"autoMode": {"allow": ["mine"], "environment": ["env"]}}),
                      encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0, proc.stdout      # 기존 autoMode 를 '예상 밖 변경'으로 보면 설치가 실패한다
    rules = [r for r in _frag_auto_allow() if r != "$defaults"]
    assert result["autoMode"]["allow"] == ["mine"] + rules
    assert result["autoMode"]["environment"] == ["env"]


def test_uninstall_removes_only_auto_allow_it_added_even_after_reinstall(tmp_path):
    target = tmp_path / "settings.json"
    manifest = tmp_path / "manifest.json"
    target.write_text(json.dumps({"autoMode": {"environment": ["env"]}}), encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    run_merge(target, manifest_path=manifest)            # 멱등 재실행도 영수증을 잊지 않아야 한다
    _, result = run_uninstall(target, manifest)
    assert result["autoMode"] == {"environment": ["env"]}

    target.write_text("{}", encoding="utf-8")
    manifest.unlink()
    run_merge(target, manifest_path=manifest)
    _, result = run_uninstall(target, manifest)
    assert "autoMode" not in result


def test_uninstall_keeps_defaults_when_user_added_rules_after_install(tmp_path):
    """"$defaults" 가 빠지면 남은 사용자 규칙이 기본 allow 목록을 통째로 대체한다."""
    target = tmp_path / "settings.json"
    manifest = tmp_path / "manifest.json"
    target.write_text("{}", encoding="utf-8")
    run_merge(target, manifest_path=manifest)
    s = json.loads(target.read_text(encoding="utf-8"))
    s["autoMode"]["allow"].append("mine")
    target.write_text(json.dumps(s), encoding="utf-8")
    _, result = run_uninstall(target, manifest)
    assert result["autoMode"]["allow"] == ["$defaults", "mine"]


def test_malformed_auto_mode_is_left_untouched(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"autoMode": {"allow": "not a list"}}), encoding="utf-8")
    proc, result = run_merge(target)
    assert proc.returncode == 0, proc.stdout
    assert result["autoMode"] == {"allow": "not a list"}
