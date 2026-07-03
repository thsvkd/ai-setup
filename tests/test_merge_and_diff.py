"""merge_and_diff.py 병합 엔진 테스트 (자리표시자 치환 + 외과적 병합 + 멱등성)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGE = ROOT / "res" / "hooks" / "merge_and_diff.py"
FRAGMENT = ROOT / "res" / "settings.json"


def run_merge(target: Path, dry="0", py="python3", hooks_dir="/home/u/.claude/hooks"):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(MERGE), str(FRAGMENT), str(target), dry, py, hooks_dir],
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


def run_remove(target: Path, dry="0", scripts="danger_guard.py,secrets_guard.py"):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(MERGE), "--remove", str(target), dry, scripts],
        capture_output=True, text=True, encoding="utf-8",
    )
    result = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    return proc, result


def test_remove_deregisters_our_hooks(tmp_path):
    target = tmp_path / "settings.json"
    run_merge(target)
    proc, result = run_remove(target)
    assert proc.returncode == 0
    assert not result.get("hooks", {}).get("PreToolUse")


def test_remove_preserves_permissions(tmp_path):
    target = tmp_path / "settings.json"
    run_merge(target)
    _, result = run_remove(target)
    # uninstall 은 권한을 건드리지 않는다.
    assert "Bash" in result["permissions"]["allow"]


def test_remove_keeps_foreign_hooks(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({
        "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "python other_hook.py"}]}
        ]}
    }), encoding="utf-8")
    run_merge(target)   # 남의 훅 옆에 우리 훅 추가
    _, result = run_remove(target)
    cmds = [h["hooks"][0]["command"] for h in result["hooks"]["PreToolUse"]]
    assert any("other_hook.py" in c for c in cmds)          # 남의 훅은 보존
    assert not any("danger_guard.py" in c for c in cmds)    # 우리 것만 제거


def test_remove_dry_run_does_not_write(tmp_path):
    target = tmp_path / "settings.json"
    run_merge(target)
    before = target.read_text(encoding="utf-8")
    run_remove(target, dry="1")
    assert target.read_text(encoding="utf-8") == before
