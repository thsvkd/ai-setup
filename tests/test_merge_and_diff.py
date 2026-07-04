"""merge_and_diff.py 병합 엔진 테스트 (자리표시자 치환 + 외과적 병합 + 멱등성)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGE = ROOT / "res" / "hooks" / "merge_and_diff.py"
FRAGMENT = ROOT / "res" / "settings.json"


def run_merge(target: Path, dry="0", py="python3", hooks_dir="/home/u/.claude/hooks",
              manifest_path=None, hook_files="danger_guard.py,secrets_guard.py"):
    args = [sys.executable, "-X", "utf8", str(MERGE), str(FRAGMENT), str(target), dry, py, hooks_dir]
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
    assert "Bash(git push *)" in result["permissions"]["deny"]


def test_placeholders_substituted(tmp_path):
    _, result = run_merge(tmp_path / "settings.json")
    cmds = hook_commands(result)
    assert any("danger_guard.py" in c for c in cmds)
    assert any("secrets_guard.py" in c for c in cmds)
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
    assert result["env"] == {"X": "1"}
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
    assert "변경 사항 없음" in proc2.stdout


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
    # 세 번 실행해도 각 훅은 한 번씩만 등록되어야 한다.
    assert matchers.count("Bash|PowerShell") == 1
    assert matchers.count("Read|Write|Edit|MultiEdit") == 1


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
    run_merge(target, manifest_path=manifest, hook_files="danger_guard.py,secrets_guard.py")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["hook_files"] == ["danger_guard.py", "secrets_guard.py"]
    assert "Bash" in m["added_allow"]
    assert m["default_mode_before"] == "default"
    assert m["default_mode_after"] == "auto"
    assert m["default_mode_changed"] is True


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
    assert "변경 사항 없음" in proc2.stdout   # 두 번째 실행은 이미 다 있어 변경 없음


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
