"""setup.sh / install.sh 의 '실제 설치' 경로 테스트 (dry-run 이 아닌 쪽).

기존 테스트는 --dry-run 과 --help 만 밟았다. 그 두 경로는 macOS 기본 bash 3.2 에서
멀쩡히 통과하는데, 정작 실제 설치는 전부 죽었다:

  * setup.sh 는 인자를 배열로 넘긴다. bash < 4.4 는 `set -u` 에서 빈 배열의 "${arr[@]}"
    확장을 unbound variable 로 취급한다. --dry-run 일 때는 배열이 비어있지 않아 통과하고,
    실제 설치일 때만 죽는다.
  * install.sh 의 EXIT 트랩은 성공해도 exit 1 을 반환했다.
  * 설치를 두 번 하면 매니페스트(설치 영수증)가 빈 값으로 덮어써져 --uninstall 이
    defaultMode 와 권한을 되돌리지 못했다.

그래서 여기서는 항상 non-dry-run 경로를 격리된 HOME 에 대고 실행한다.
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="POSIX 셸 스크립트 테스트 (bash 필요)",
)


@pytest.fixture
def stub_bin(tmp_path):
    """PATH 앞에 끼울 스텁 디렉터리. 실제 휴지통 도구/네트워크를 쓰지 않게 한다."""
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir()
    trash = bin_dir / "trash-put"
    trash.write_text('#!/bin/sh\necho "[stub trash-put] $*"\n', encoding="utf-8")
    trash.chmod(0o755)
    return bin_dir


@pytest.fixture
def sandbox_home(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    return home


def run_script(args, home, stub_bin, cwd=None):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = f"{stub_bin}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        args, cwd=str(cwd or ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))


def manifest(home):
    return json.loads((home / ".claude" / ".claude-code-setup.json").read_text(encoding="utf-8"))


# --- setup.sh: 실제 설치 경로 (빈 배열 확장 회귀) ---

def test_setup_hooks_installs_for_real(sandbox_home, stub_bin):
    proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--hooks"], sandbox_home, stub_bin)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    hooks = sandbox_home / ".claude" / "hooks"
    assert (hooks / "danger_guard.py").exists()
    assert (hooks / "secrets_guard.py").exists()
    assert settings(sandbox_home)["hooks"]["PreToolUse"]


def test_setup_no_args_installs_hooks_and_agentsmd(sandbox_home, stub_bin, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh")], sandbox_home, stub_bin, cwd=project)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert (sandbox_home / ".claude" / "hooks" / "danger_guard.py").exists()
    assert (project / "AGENTS.md").exists()


def test_setup_uninstall_runs_for_real(sandbox_home, stub_bin):
    run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--hooks"], sandbox_home, stub_bin)
    proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--uninstall"], sandbox_home, stub_bin)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert not (sandbox_home / ".claude" / "hooks" / "danger_guard.py").exists()


def test_setup_dry_run_writes_nothing(sandbox_home, stub_bin):
    proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--hooks", "--dry-run"], sandbox_home, stub_bin)
    assert proc.returncode == 0
    assert not (sandbox_home / ".claude" / "settings.json").exists()


# --- 멱등 재실행이 설치 영수증을 파괴하지 않는다 ---

def test_rerun_preserves_uninstall_receipt(sandbox_home, stub_bin):
    (sandbox_home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls *)"], "defaultMode": "acceptEdits"}}),
        encoding="utf-8",
    )
    for _ in range(3):
        proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--hooks"], sandbox_home, stub_bin)
        assert proc.returncode == 0, proc.stderr

    receipt = manifest(sandbox_home)
    assert "Bash" in receipt["added_allow"], "재실행이 added_allow 영수증을 지웠습니다"
    assert receipt["default_mode_before"] == "acceptEdits", "재실행이 defaultMode 원본을 지웠습니다"
    assert receipt["default_mode_changed"] is True


def test_uninstall_after_rerun_restores_prior_state(sandbox_home, stub_bin):
    (sandbox_home / ".claude" / "settings.json").write_text(
        json.dumps({
            "env": {"MY_VAR": "keep-me"},
            "model": "sonnet",
            "permissions": {"allow": ["Bash(ls *)"], "defaultMode": "acceptEdits"},
        }),
        encoding="utf-8",
    )
    for _ in range(2):
        run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--hooks"], sandbox_home, stub_bin)
    run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--uninstall"], sandbox_home, stub_bin)

    result = settings(sandbox_home)
    assert result["env"] == {"MY_VAR": "keep-me"}
    assert result["model"] == "sonnet"
    assert result["permissions"]["allow"] == ["Bash(ls *)"]
    assert result["permissions"]["defaultMode"] == "acceptEdits"
    assert "effortLevel" not in result
    assert not result.get("hooks", {}).get("PreToolUse")


# --- install.sh 부트스트랩 (네트워크는 curl 스텁으로 대체) ---

@pytest.fixture
def curl_stub(tmp_path, stub_bin):
    """레포를 tarball 로 말아, curl 스텁이 그것을 stdout 으로 뱉게 한다."""
    tarball = tmp_path / "repo.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for item in ("install.sh", "scripts", "res"):
            tar.add(ROOT / item, arcname=f"claude-code-setup-main/{item}")
    curl = stub_bin / "curl"
    curl.write_text(f'#!/bin/sh\ncat "{tarball}"\n', encoding="utf-8")
    curl.chmod(0o755)
    return stub_bin


def test_install_sh_help_exits_zero(sandbox_home, stub_bin):
    proc = run_script(["sh", str(ROOT / "install.sh"), "--help"], sandbox_home, stub_bin)
    assert proc.returncode == 0
    assert "부트스트랩" in proc.stdout


def test_install_sh_dry_run_exits_zero(sandbox_home, curl_stub):
    """EXIT 트랩이 종료 상태를 오염시키면 성공해도 exit 1 이 된다."""
    proc = run_script(["sh", str(ROOT / "install.sh"), "--dry-run"], sandbox_home, curl_stub)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert not (sandbox_home / ".claude" / "settings.json").exists()


def test_install_sh_hooks_installs_end_to_end(sandbox_home, curl_stub):
    proc = run_script(["sh", str(ROOT / "install.sh"), "--hooks"], sandbox_home, curl_stub)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert (sandbox_home / ".claude" / "hooks" / "danger_guard.py").exists()
    assert settings(sandbox_home)["hooks"]["PreToolUse"]


def test_install_sh_propagates_failure(sandbox_home, curl_stub):
    proc = run_script(["sh", str(ROOT / "install.sh"), "--bogus"], sandbox_home, curl_stub)
    assert proc.returncode != 0
