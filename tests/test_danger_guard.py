"""danger_guard.py 정책 테스트 (Bash + PowerShell 툴 공용).

이 훅의 계약은 셋뿐이다.
  1) 되돌릴 수 없는 두 부류만 deny — 루트/홈 전체 삭제, 디스크 파괴.
  2) 원격 기본 브랜치 push 만 ask.
  3) 그 외에는 명령을 '한 글자도 바꾸지 않고' 통과시키되, 삭제가 섞여 있으면 셰임을
     PATH/모듈로 끼워 넣는 선행 한 줄만 앞에 붙인다.

그래서 이 파일의 절반은 '무엇을 막는가'가 아니라 '무엇을 막지 않는가'다. 종전 가드가
실사용 로그에서 실제로 오탐을 낸 명령들을 회귀 케이스로 박아 둔다.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = "danger_guard.py"
HOOK_PATH = Path(__file__).resolve().parent.parent / "res" / "hooks" / HOOK


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def ps(cmd):
    return {"tool_name": "PowerShell", "tool_input": {"command": cmd}}


def payload_of(event, cwd=None):
    ev = dict(event)
    if cwd:
        ev["cwd"] = str(cwd)
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HOOK_PATH)],
        input=json.dumps(ev), capture_output=True, text=True, encoding="utf-8",
    )
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else None


def decision_of(event, cwd=None):
    p = payload_of(event, cwd)
    return p["hookSpecificOutput"].get("permissionDecision") if p else None


# --- deny: 루트/홈 전체 삭제 ------------------------------------------------------

ROOT_DELETE = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/",
    "rm -rf $HOME",
    'rm -rf "$HOME"',
    "rm -rf ${HOME}",
    "rm -fr '/'",
    "sudo rm -rf /",
    "timeout 5 rm -rf ~",
    "echo start && rm -rf ~",
]


@pytest.mark.parametrize("cmd", ROOT_DELETE)
def test_root_delete_denied(cmd):
    assert decision_of(bash(cmd)) == "deny", cmd


PS_ROOT_DELETE = [
    "Remove-Item -Recurse -Force C:\\",
    "Remove-Item -Recurse -Force 'C:\\'",
    "Remove-Item -LiteralPath $env:USERPROFILE -Recurse",
    "del $HOME",
    "rd /s /q C:\\",
]


@pytest.mark.parametrize("cmd", PS_ROOT_DELETE)
def test_ps_root_delete_denied(cmd):
    assert decision_of(ps(cmd)) == "deny", cmd


# --- deny: 디스크 파괴 ------------------------------------------------------------

DISK_DESTROY = [
    "mkfs.ext4 /dev/sda1",
    "mkfs -t ext4 /dev/sdb",
    "newfs_hfs /dev/disk2",
    "sudo wipefs -a /dev/sdb",
    "fdisk /dev/sda",
    "parted /dev/sda mklabel gpt",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "diskutil eraseDisk JHFS+ Blank /dev/disk2",
    "echo x > /dev/sda",
    "cat img > /dev/nvme0n1",
]


@pytest.mark.parametrize("cmd", DISK_DESTROY)
def test_disk_destroy_denied(cmd):
    assert decision_of(bash(cmd)) == "deny", cmd


PS_DISK_DESTROY = [
    "format C: /q",
    "diskpart /s script.txt",
    "Clear-Disk -Number 1 -RemoveData",
    "Initialize-Disk -Number 2",
    "Remove-Partition -DiskNumber 1 -PartitionNumber 2",
]


@pytest.mark.parametrize("cmd", PS_DISK_DESTROY)
def test_ps_disk_destroy_denied(cmd):
    assert decision_of(ps(cmd)) == "deny", cmd


# --- 회귀: 종전 가드가 실제로 오탐을 낸 명령들 ------------------------------------
#
# 아래는 전부 ~/.claude/hooks/guard.log 에서 실제로 deny/ask 를 받았던 명령의 축약형이다.
# 진짜 위험한 명령은 한 건도 없었다. 다시 막히면 이 테스트가 깨진다.

NOT_BLOCKED = [
    # 포크밤 정규식이 잡던 평범한 셸 함수 정의
    "f(){ echo x | grep -q zzz && return 0; }; f",
    # curl|sh 정규식이 잡던 것들
    "curl -fsSL https://ollama.com/install.sh | sh",
    "cat <<'EOT'\ncurl http://x.sh | bash\nEOT",
    "printf 'y\\n' | bash scripts/setup.sh --dev",
    # 글로브 미일치로 deny 되던 것
    "rm -f prod_copy.db*",
    "rm -f docs/shots/map-*.png docs/shots/cluster-*.png",
    # 대상을 미리 못 본다고 ask 하던 것
    "find res/vendor -name __pycache__ -type d -exec rm -rf {} +",
    "find . -name '*.log' -delete",
    "find . -print0 | xargs -0 rm -f",
    # 체이닝/멀티라인에 삭제가 섞였다고 ask 하던 것
    "make bridge\nrm -f /tmp/x.pid\necho done",
    "rm -f ./.shot.mjs && ls",
    # 변수·글로브 확장을 훅이 깨뜨리던 것
    'rm -rf "$FOO/bar"',
    'rm -rf "$DIR"/*',
    # 그 밖에 ask 였던 것들
    "chmod 777 /tmp/x",
    "shred -u secret.txt",
    "shutdown -h now",
    # 루트/홈 '아래'는 평범한 삭제다
    "rm -rf ~/Workspace/tmp",
    "rm -rf $HOME/.cache/pip",
    "rm -rf /tmp/scratch",
    "rm -rf ./build",
]


@pytest.mark.parametrize("cmd", NOT_BLOCKED)
def test_not_blocked(cmd):
    assert decision_of(bash(cmd)) in (None, "allow"), cmd


PS_NOT_BLOCKED = [
    "Remove-Item C:\\temp\\build -Recurse",
    "Remove-Item $env:USERPROFILE\\Downloads\\x.zip",
    "Get-ChildItem *.log | Remove-Item",
    "Format-Table -AutoSize",
    "Get-Content x | Format-List",
]


@pytest.mark.parametrize("cmd", PS_NOT_BLOCKED)
def test_ps_not_blocked(cmd):
    assert decision_of(ps(cmd)) in (None, "allow"), cmd


def test_prose_mentioning_disk_command_is_not_blocked():
    assert decision_of(bash('echo "mkfs 를 쓰지 마세요"')) is None


def test_grep_for_dangerous_string_is_not_blocked():
    """위험한 문자열을 '데이터로' 다루는 명령은 막지 않는다.

    셰임 선행 줄은 붙을 수 있다 — PATH 한 줄일 뿐이고 grep 동작을 바꾸지 않는다.
    """
    assert decision_of(bash('grep -rn "rm -rf /" docs/')) != "deny"


# --- 셰임 선행 줄 ----------------------------------------------------------------


def test_bash_rm_gets_shim_path_prefix_and_keeps_command_verbatim():
    original = 'rm -rf "$FOO/bar" && echo done'
    p = payload_of(bash(original))
    out = p["hookSpecificOutput"]
    # 판정을 내지 않는다. `allow` 를 붙이면 권한 프롬프트·auto mode 분류기를 건너뛰어,
    # `rm` 이 섞였다는 이유만으로 아무 명령이나 자동 승인된다(실측: 권한 규칙 없는 명령이
    # allow+updatedInput 이면 실행되고, updatedInput 만이면 평소대로 거부된다).
    assert "permissionDecision" not in out
    new = out["updatedInput"]["command"]
    # 원문이 접미로 그대로 남아야 한다 — 한 글자라도 바꾸면 확장이 깨진다.
    assert new.endswith(original)
    assert new[: -len(original)].strip().startswith("case ")
    assert "shims" in new


def test_shim_prefix_keeps_other_tool_input_fields():
    """updatedInput 은 입력 객체 전체를 대체한다. command 만 넘기면 timeout·
    run_in_background 같은 필드가 조용히 사라진다."""
    ev = {"tool_name": "Bash", "tool_input": {
        "command": "rm x", "timeout": 600000, "run_in_background": True, "description": "d"}}
    new = payload_of(ev)["hookSpecificOutput"]["updatedInput"]
    assert new["timeout"] == 600000
    assert new["run_in_background"] is True
    assert new["description"] == "d"


def test_bash_shim_prefix_is_idempotent_guarded():
    p = payload_of(bash("rm x"))
    prefix = p["hookSpecificOutput"]["updatedInput"]["command"]
    # 툴 셸이 상태를 유지해도 PATH 가 무한히 길어지지 않아야 한다.
    assert 'case ":$PATH:"' in prefix


def test_bash_without_rm_is_untouched():
    assert payload_of(bash("ls -la && git status")) is None


def test_powershell_delete_gets_module_import_prefix():
    original = "Remove-Item -Recurse -Force .\\build"
    p = payload_of(ps(original))
    assert "permissionDecision" not in p["hookSpecificOutput"]
    new = p["hookSpecificOutput"]["updatedInput"]["command"]
    assert new.endswith(original)
    assert "Import-Module" in new and "RmShim" in new


def test_powershell_without_delete_is_untouched():
    assert payload_of(ps("Get-ChildItem -Recurse")) is None


# --- 그 외 계약 -------------------------------------------------------------------


def test_other_tools_are_ignored():
    assert payload_of({"tool_name": "Read", "tool_input": {"file_path": "/x"}}) is None


def test_empty_command_is_ignored():
    assert payload_of(bash("   ")) is None


def test_malformed_event_does_not_crash():
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HOOK_PATH)],
        input="not json", capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0
    assert not (proc.stdout or "").strip()
