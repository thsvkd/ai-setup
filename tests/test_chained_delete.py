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
import os
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


@pytest.mark.parametrize("cmd", [
    'echo $(date; uptime)',            # 서브셸 안 세미콜론
    'ls 2>&1',                         # 리다이렉트의 '&' 는 구분자가 아니다
    'grep "a|rm -rf /" file.txt',      # 따옴표 안 파이프 + 위험해 보이는 문자열
])
def test_separators_that_are_not_separators(run_hook, cmd):
    """잘못 쪼개면 멀쩡한 명령이 체이닝으로 오인돼 불필요하게 막힌다. 오탐 방향의 회귀 방지."""
    d, *_ = run_hook(WIN, bash(cmd))
    assert d is None, cmd


def test_unbalanced_open_paren_is_a_known_gap(run_hook):
    """알려진 한계를 고정해 둔다: 짝 없는 여는 괄호 뒤의 구분자는 떼어내지 않는다.

    수정 전에도 놓치던 경우라 회귀가 아니고, 이런 줄은 bash/PowerShell 양쪽에서 문법 오류라
    실행되지 않는다. 나중에 이 한계를 없애면 이 테스트가 실패하면서 알려줄 것이다."""
    d, *_ = run_hook(WIN, bash("echo (;rm -rf /"))
    assert d is None
    # 같은 명령을 띄어쓰기만 하면 잡힌다 — 한계가 '괄호'에 있지 '삭제 탐지'에 있지 않음을 못박는다.
    d2, *_ = run_hook(WIN, bash("echo ( ; rm -rf /"))
    assert d2 == "deny"


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
        # 판정이 없다는 건 이 훅이 rm 을 아예 못 봤다는 뜻이다. 조용히 통과시키면 이 테스트가
        # 무엇도 검증하지 않으므로, 건너뛴 사실을 사유와 함께 드러낸다 (러너는 -rs 로 돈다).
        pytest.skip("posix 훅이 판정을 내지 않았다 — 이 환경에서는 검증할 수 없다")
    assert "체이닝" not in payload["hookSpecificOutput"].get("permissionDecisionReason", "")


# --- 회귀: Git Bash(MSYS) 드라이브 표기로 홈/루트를 지우려는 시도 ---
#
# 이 훅의 Bash 툴은 Git Bash 이고, 거기서 홈은 `/c/Users/<이름>` 으로 적는다. 정규화가 없던
# 동안 같은 디렉터리인데도 `~`, `$HOME`, `"C:\Users\<이름>"` 은 전부 막히고 이 표기만 통과했다.

HOME = os.path.expanduser("~")
_drive, _tail = os.path.splitdrive(HOME)
MSYS_HOME = "/" + _drive[0].lower() + _tail.replace("\\", "/")


@pytest.mark.skipif(not _drive, reason="드라이브 문자가 있는 홈 경로에서만 의미가 있다")
@pytest.mark.parametrize("target", [
    MSYS_HOME,                    # /c/Users/<이름>
    MSYS_HOME + "/",              # 끝 슬래시
    "/" + _drive[0].lower(),      # 드라이브 루트 자체: /c
    "/" + _drive[0].lower() + "/",
])
def test_msys_style_home_and_root_denied(run_hook, target):
    d, *_ = run_hook(WIN, bash(f"rm -rf {target}"))
    assert d == "deny", target


@pytest.mark.skipif(not _drive, reason="드라이브 문자가 있는 홈 경로에서만 의미가 있다")
def test_msys_path_below_home_still_allowed(run_hook):
    """정규화가 과하게 걸려 홈 '하위' 삭제까지 막으면 안 된다."""
    d, *_ = run_hook(WIN, bash(f"rm -rf {MSYS_HOME}/scratch"))
    assert d != "deny"


def test_posix_looking_paths_are_not_mistaken_for_drives(run_hook):
    """`/tmp` 처럼 첫 성분이 한 글자가 아닌 경로를 드라이브로 오인하면 안 된다."""
    for target in ("/tmp/build", "/usr/local/share"):
        d, *_ = run_hook(WIN, bash(f"rm -rf {target}"))
        assert d != "deny", target
