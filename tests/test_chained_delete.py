"""회귀: 체이닝된 삭제가 뒤 명령의 인자를 삭제 대상으로 흡수하던 버그.

`split_commands()` 는 shlex 토큰이 구분자와 **정확히 일치**할 때만 서브커맨드를 나눈다.
그런데 shlex 는 구분자가 앞 토큰에 붙어 있으면 떼어내지 않는다:

    PowerShell  `... -Confirm:$false; git -C <repo> status`
                → ['-Confirm:$false;', 'git', '-C', '<repo>', 'status']
    Bash        `rm -rf build;ls -la`
                → ['rm', '-rf', 'build;ls', '-la']

그래서 is_chained 가 False 가 되어 "체이닝된 명령 안의 삭제는 자동 치환하지 않는다"는
방어선이 발동하지 않았고, `-` 로 시작하지 않는 토큰이 전부 휴지통 삭제 대상으로 넘어갔다.
guard.log 에 남은 실제 기록:

    send_to_trash.py '<repo>\\.probe-tmp' 'git' '<repo>' 'status'

send_to_trash.py 는 인자 하나가 실패해도 다음 인자를 계속 처리하므로 '<repo>' 에 도달한다.

수정: separate_operators() 가 토크나이즈 직전에 따옴표 밖 구분자를 떼어놓아, 기존 방어선이
의도대로 발동한다. 따옴표 안의 구분자는 파일명의 일부이므로 건드리지 않는다.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "res" / "hooks"
WIN = "danger_guard.windows.py"
REPO = r"C:\repo"


def ps(cmd):
    return {"tool_name": "PowerShell", "tool_input": {"command": cmd}}


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def _reason(payload):
    return payload["hookSpecificOutput"]["permissionDecisionReason"]


def _new_command(payload):
    return payload["hookSpecificOutput"].get("updatedInput", {}).get("command", "")


# --- 붙어 있는 구분자를 체이닝으로 인식해야 한다 ---

def test_ps_glued_semicolon_is_detected_as_a_chain(run_hook):
    """이 버그가 실제로 관측된 정확한 명령. 판정이 deny 든 뭐든, 뒤 명령의 인자가 삭제 대상
    목록에 들어가서는 안 된다."""
    cmd = (f'Remove-Item -Recurse -Force "{REPO}\\.tmp" -Confirm:$false; '
           f'git -C "{REPO}" status --short')
    d, payload, _ = run_hook(WIN, ps(cmd))
    assert d == "deny", payload
    assert "체이닝" in _reason(payload)
    # 치환이 일어나지 않았으므로 삭제 대상 목록 자체가 없어야 한다.
    assert _new_command(payload) == ""


def test_bash_glued_semicolon_is_detected_as_a_chain(run_hook):
    d, payload, _ = run_hook(WIN, bash("rm -rf build;ls -la"))
    assert d == "deny", payload
    assert "체이닝" in _reason(payload)


@pytest.mark.parametrize("cmd", [
    "rm -rf build;ls -la",                 # ';' 가 앞 토큰에 붙음
    "rm -rf build&&ls -la",                # '&&' 가 양쪽에 붙음
    "cd /tmp&&rm -rf build",               # 삭제가 체인의 두 번째
    "ls|xargs rm -rf",                     # 파이프도 붙어 있음
])
def test_glued_separators_never_leak_into_targets(run_hook, cmd):
    """어떤 형태로 붙어 있든, 뒤/앞 명령의 토큰이 휴지통 인자로 새면 안 된다."""
    d, payload, _ = run_hook(WIN, bash(cmd))
    new = _new_command(payload)
    for leaked in ("ls", "cd", "xargs"):
        assert f"'{leaked}'" not in new, f"{cmd} -> {new}"
        assert f'"{leaked}"' not in new, f"{cmd} -> {new}"


def test_root_delete_in_second_segment_denied(run_hook):
    """삭제가 체인의 첫 구간이 아니어도 루트 검사가 걸려야 한다."""
    d, *_ = run_hook(WIN, bash("echo start && rm -rf /"))
    assert d == "deny"


# --- 따옴표/이스케이프 안의 구분자는 구분자가 아니다 ---

def test_quoted_separator_is_not_a_chain(run_hook):
    """따옴표 안의 ';' 는 파일명의 일부다. 여기서 잘리면 멀쩡한 삭제가 체이닝으로 오인된다."""
    d, payload, _ = run_hook(WIN, ps(r'Remove-Item -Force "C:\tmp\odd;name.txt"'))
    assert d == "allow", payload
    assert "odd;name.txt" in _new_command(payload)


def test_escaped_semicolon_is_not_a_chain(run_hook):
    """`find -exec … \\;` 의 이스케이프된 세미콜론으로 체인이 갈라지면 안 된다."""
    d, *_ = run_hook(WIN, bash(r"find . -name '*.pyc' -print \;"))
    assert d is None


def test_separator_inside_quotes_does_not_split_a_safe_command(run_hook):
    d, *_ = run_hook(WIN, bash('grep "a;b" file.txt'))
    assert d is None


# --- 회귀 방지: 체이닝이 없는 평범한 삭제는 그대로 치환된다 ---

def test_plain_delete_still_substituted(run_hook):
    d, payload, _ = run_hook(WIN, ps(r'Remove-Item -Recurse -Force "C:\tmp\x"'))
    assert d == "allow", payload
    assert "send_to_trash.py" in _new_command(payload)


# --- posix 변종도 같은 결함을 공유했다 ---

POSIX_HOOK_PATH = HOOKS_DIR / "danger_guard.posix.py"


def _run_posix(cmd):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(POSIX_HOOK_PATH)],
        input=json.dumps(bash(cmd)),
        capture_output=True, text=True, encoding="utf-8",
    )
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else None


def test_posix_glued_semicolon_is_detected_as_a_chain():
    payload = _run_posix("rm -rf build;ls -la")
    out = payload["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny", out
    assert "체이닝" in out["permissionDecisionReason"]


def test_posix_quoted_separator_is_not_a_chain():
    """따옴표 안 ';' 로는 갈라지지 않아야 한다 — 휴지통 도구 유무와 무관하게 '체이닝' 사유는
    나오면 안 된다."""
    payload = _run_posix('rm -f "odd;name.txt"')
    if payload is None:
        return
    assert "체이닝" not in payload["hookSpecificOutput"].get("permissionDecisionReason", "")
