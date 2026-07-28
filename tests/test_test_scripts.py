"""테스트 러너 스크립트(scripts/test.sh, scripts/test.ps1) 자체의 계약 검증.

러너의 가치는 '종료 코드가 정직한 것' 하나다. 러너가 없어서 스위트를 못 돌렸는데 0으로
끝나면, CI 도 사람도 "테스트 통과"로 읽는다 — 아무것도 검증되지 않았는데도. 실제로 이
스크립트의 첫 구현이 정확히 그 버그를 냈다(전부 건너뛰고 "실행된 스위트 모두 통과" 출력).
그래서 여기서는 개별 출력 문구가 아니라 종료 코드 계약을 고정한다:

  - 실행된 스위트가 모두 통과 → 0
  - 실행된 스위트 중 하나라도 실패 → 1
  - 실행된 스위트가 하나도 없음 → 1 (통과 아님)

재귀 주의: 이 테스트가 부르는 scripts/test.sh 는 pytest 를 다시 띄운다. 안쪽 pytest 가
이 테스트 함수를 '실행' 하면 무한 재귀가 된다. 그래서 (a) 안쪽 실행은 아무 테스트도 매칭되지
않는 -k 로 수집만 시키고, (b) 그래도 실행되면 멈추도록 CLAUDE_TEST_RUNNER_CHILD 가 설정된
프로세스에서는 이 모듈 전체를 skip 한다.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_PS1 = REPO_ROOT / "scripts" / "test.ps1"

# bash 에 넘기는 스크립트 경로는 '리포 루트 기준 상대 POSIX 경로' 로 고정한다. Windows 절대
# 경로를 그대로 넘기면 Git Bash 가 백슬래시를 이스케이프로 먹어 경로가 뭉개진다 — 실제로
# C:\Users\...\test.sh 가 `C:Usersthsxo...test.sh` 가 되어 exit 127 로 전부 실패했다.
TEST_SH_REL = "scripts/test.sh"

# bash 는 절대 경로로 직접 호출한다. argv[0] 을 PATH 로 해석시키면, PATH 를 비워 '아무것도
# 실행할 수 없는 상태' 를 만드는 테스트에서 bash 자체를 못 찾게 된다.
BASH = shutil.which("bash")

CHILD_ENV_FLAG = "CLAUDE_TEST_RUNNER_CHILD"

pytestmark = pytest.mark.skipif(
    os.environ.get(CHILD_ENV_FLAG) == "1",
    reason="러너가 띄운 안쪽 pytest — 재귀 방지를 위해 건너뛴다",
)


def run_test_sh(*args, env_overrides=None):
    """scripts/test.sh 를 자식으로 실행한다. 자식이 띄우는 pytest 는 이 모듈을 skip 한다."""
    env = dict(os.environ)
    env[CHILD_ENV_FLAG] = "1"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [BASH, TEST_SH_REL, *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 필요")
def test_test_sh_syntax_is_valid():
    proc = subprocess.run([BASH, "-n", TEST_SH_REL], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 필요")
def test_help_exits_zero_without_running_anything():
    proc = run_test_sh("--help")
    assert proc.returncode == 0
    assert "사용법" in proc.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 필요")
def test_failing_suite_makes_the_runner_fail():
    """pytest 가 실패하면(여기서는 매칭되는 테스트가 없어 exit 5) 러너도 1 이어야 한다.
    -k 가 아무것도 매칭하지 않으므로 안쪽 pytest 는 수집만 하고 테스트를 실행하지 않는다."""
    proc = run_test_sh("--python-only", "-k", "__no_such_test_name__")
    assert proc.returncode == 1, proc.stdout[-2000:]
    assert "실패" in proc.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 필요")
def test_nothing_runnable_is_not_success(tmp_path):
    """러너를 하나도 못 찾은 상황. python 조차 없으면 검증된 것이 0개이므로 0 으로 끝나면
    안 된다 — 이게 첫 구현의 실제 버그였다(전부 건너뛰고 '모두 통과')."""
    # bash 는 절대 경로로 부르므로 PATH 에 아무것도 없어도 스크립트 자체는 돈다. 예전에는
    # bash 를 심볼릭 링크로 남겼는데, Windows 에서는 심볼릭 링크 생성에 별도 권한이 필요해
    # 테스트가 환경 탓으로 깨진다 — 링크 없이 빈 디렉터리만 주는 편이 이식성이 높다.
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    proc = run_test_sh(env_overrides={"PATH": str(empty_bin)})
    assert proc.returncode == 1, proc.stdout[-2000:]
    assert "실행된 스위트가 없습니다" in proc.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash 필요")
def test_python_only_skips_are_not_counted_by_strict():
    """--python-only 로 '요청하지 않은' 스위트는 러너 미설치로 '못 돌린' 스위트와 다르다.
    사용자가 직접 고른 선택을 --strict 가 실패로 만들면 안 된다."""
    proc = run_test_sh("--python-only", "--strict", "-k", "test_rm_root_denied")
    assert proc.returncode == 0, proc.stdout[-2000:]


PWSH = shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(PWSH is None, reason="pwsh/powershell 을 찾지 못함")
def test_test_ps1_parses():
    """PowerShell 스크립트는 파서에 한 번이라도 통과시켜야 한다 — 문법 오류가 있으면 Windows
    에서 실행 즉시 죽는데, POSIX 개발 환경에서는 그 사실이 드러나지 않는다."""
    script = (
        "$ErrorActionPreference='Stop';"
        "$tokens=$null; $errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{TEST_PS1}', [ref]$tokens, [ref]$errors) > $null;"
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }; exit 0"
    )
    proc = subprocess.run([PWSH, "-NoProfile", "-Command", script],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 에서만 실제 실행 검증")
def test_test_ps1_help_exits_zero():
    proc = subprocess.run(
        [PWSH or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(TEST_PS1), "-Help"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert "사용법" in (proc.stdout or "")


# --- 배포되는 셸 스크립트의 실행 권한 ---

def test_shell_scripts_are_executable():
    """`.sh` 파일은 전부 git 에 실행 권한(100755)으로 기록돼야 한다.

    `bash script.sh` 로만 부르면 권한이 없어도 동작해서, 빠져 있어도 한동안 아무도 모른다.
    그러다 `./scripts/setup.sh` 처럼 직접 실행하는 순간 'Permission denied' 로 막힌다.
    모드는 커밋에 박히는 값이라 실수로 되돌아가기도 쉬우니 여기서 고정한다.

    `.ps1` 은 제외한다 — Windows 는 실행 비트를 쓰지 않고, PowerShell 스크립트는
    `powershell -File` 로 호출되므로 비트를 세워도 의미가 없다."""
    listing = subprocess.run(
        ["git", "ls-files", "-s", "--", "*.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert listing.returncode == 0, listing.stderr
    not_executable = []
    for line in listing.stdout.splitlines():
        if not line.strip():
            continue
        mode, _, _, path = line.split(maxsplit=3)
        if mode != "100755":
            not_executable.append(f"{path} ({mode})")
    assert not not_executable, (
        "실행 권한이 없는 셸 스크립트: " + ", ".join(not_executable) +
        "  → git update-index --chmod=+x <path>"
    )
