"""Native Windows boundaries that must hold without administrator consent."""
import base64
import json
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location("orca_windows_native", Path(__file__).resolve().parents[1] / "res/tools/orca_windows.py")
orca_windows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orca_windows)


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows security boundary")


def test_elevated_worker_refuses_a_different_account_before_task_access():
    payload = base64.b64encode(json.dumps({"callerSid": "S-1-5-18"}).encode()).decode()
    worker = orca_windows.WORKER.replace("__PAYLOAD__", payload)
    encoded = base64.b64encode(worker.encode("utf-16-le")).decode()
    result = subprocess.run(
        [str(orca_windows.powershell_path()), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode != 0
    assert "must match the original Windows user" in result.stderr


def test_private_pairing_file_has_an_explicit_current_user_rule(tmp_path):
    path = tmp_path / "pairing.txt"
    path.write_text("fixture only", encoding="utf-8")
    orca_windows.protect_file(path)
    script = r'''
$path = [Console]::In.ReadToEnd()
$acl = [IO.File]::GetAccessControl($path)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.Access | Where-Object {
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -eq $sid -and
    $_.AccessControlType -eq 'Allow' -and -not $_.IsInherited
})
if ($rules.Count -eq 0) { exit 1 }
'''
    result = subprocess.run(
        [str(orca_windows.powershell_path()), "-NoProfile", "-NonInteractive", "-Command", script],
        input=str(path), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert path.read_text(encoding="utf-8") == "fixture only"


def _alive(pid):
    listed = subprocess.run(["tasklist", "/FI", "PID eq {}".format(pid), "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=30)
    return '"{}"'.format(pid) in listed.stdout


def test_runner_process_tree_ends_when_the_runner_is_terminated():
    """covers: AI-50 — schtasks /End 는 러너만 TerminateProcess 한다. 자손이 남으면 안 된다."""
    import time
    runner_code = (
        "import subprocess, sys, time\n"
        "sys.path.insert(0, {!r})\n"
        "import orca_windows\n"
        "orca_windows.contain_process_tree()\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],\n"
        "                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(120)\n"
    ).format(str(Path(spec.origin).parent))
    runner = subprocess.Popen([sys.executable, "-c", runner_code], stdout=subprocess.PIPE, text=True)
    try:
        grandchild = int(runner.stdout.readline())
        assert _alive(grandchild)
        runner.kill()
        runner.wait(timeout=30)
        deadline = time.monotonic() + 10
        while _alive(grandchild) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert not _alive(grandchild)
    finally:
        if runner.poll() is None:
            runner.kill()
