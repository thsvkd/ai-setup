"""테스트 러너 스크립트(scripts/test.sh, scripts/test.ps1) 자체의 계약 검증.

러너의 가치는 '종료 코드가 정직한 것' 하나다. 러너가 없어서 스위트를 못 돌렸는데 0으로
끝나면, CI 도 사람도 "테스트 통과"로 읽는다 — 아무것도 검증되지 않았는데도. 실제로 이
스크립트의 첫 구현이 정확히 그 버그를 냈다(전부 건너뛰고 "실행된 스위트 모두 통과" 출력).
그래서 여기서는 개별 출력 문구가 아니라 종료 코드 계약을 고정한다:

  - 실행된 스위트가 모두 통과 → 0
  - 실행된 스위트 중 하나라도 실패 → 1
  - 실행된 스위트가 하나도 없음 → 1 (통과 아님)

인터프리터 선택 계약도 같이 고정한다:

  - CLAUDE_TEST_PYTHON 미지정 → 러너가 스스로 pytest 가 import 되는 python 을 찾는다
  - CLAUDE_TEST_PYTHON 지정, 그런데 그걸로 pytest 를 못 쓴다 → '건너뜀' 이 아니라 실패
    (지정해 놓고 아무것도 안 돈 상태를 --strict 없는 CI 가 통과로 읽으면 안 되므로)

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
# C:\Users\...\test.sh 가 `C:Usersuser...test.sh` 가 되어 exit 127 로 전부 실패했다.
TEST_SH_REL = "scripts/test.sh"

CHILD_ENV_FLAG = "CLAUDE_TEST_RUNNER_CHILD"

# bash 후보를 고르는 유일한 기준은 '우리가 넘긴 환경 변수를 그대로 받는가' 다. 이 모듈의 모든
# 테스트는 env 로 상황을 만들어 낸다 — PATH 를 비워 '러너가 하나도 없는 상태' 를,
# CLAUDE_TEST_PYTHON 으로 인터프리터를, CLAUDE_TEST_RUNNER_CHILD 로 재귀 방지를 건다.
# 환경이 전달되지 않는 bash 에서는 그 셋업이 통째로 사라지고, 테스트는 의도한 계약 대신
# 그 bash 가 사는 환경을 측정한다.
#
# Windows 의 PATH 위 `bash` 는 대개 WSL 런처(System32\bash.exe)다. WSL 은 별개의 리눅스
# 환경으로 넘어가면서 WSLENV 에 등재되지 않은 변수를 전부 버린다 — 실제로 PATH 를 비운
# 테스트가 WSL 안의 python3 으로 pytest 를 돌려 버렸고, 재귀 방지 플래그까지 사라져 안쪽
# pytest 가 이 모듈을 다시 실행했다. 그래서 PATH 를 믿지 않고 실측으로 고른다.
PROBE_VAR = "CLAUDE_TEST_BASH_PROBE"


def _bash_candidates():
    """우선순위대로 bash 후보 경로. Windows 에서는 Git Bash 를 PATH 보다 앞에 둔다."""
    if sys.platform == "win32":
        git = shutil.which("git")
        if git:
            # ...\Git\cmd\git.exe → ...\Git, ...\Git\bin\bash.exe 가 같은 설치본이다.
            git_root = Path(git).resolve().parent.parent
            yield git_root / "bin" / "bash.exe"
            yield git_root / "usr" / "bin" / "bash.exe"
        yield Path(r"C:\Program Files\Git\bin\bash.exe")
    found = shutil.which("bash")
    if found:
        yield Path(found)


def _passes_env_probe(bash):
    try:
        proc = subprocess.run(
            [str(bash), "-c", f'printf %s "${PROBE_VAR}"'],
            env={**os.environ, PROBE_VAR: "1"},
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "1"


def _resolve_bash():
    for candidate in _bash_candidates():
        if candidate.exists() and _passes_env_probe(candidate):
            return str(candidate)
    return None


# bash 는 절대 경로로 직접 호출한다. argv[0] 을 PATH 로 해석시키면, PATH 를 비워 '아무것도
# 실행할 수 없는 상태' 를 만드는 테스트에서 bash 자체를 못 찾게 된다.
BASH = _resolve_bash()

requires_bash = pytest.mark.skipif(
    BASH is None, reason="환경 변수를 전달받는 bash 를 찾지 못함 (Windows: Git Bash 필요)"
)

pytestmark = pytest.mark.skipif(
    os.environ.get(CHILD_ENV_FLAG) == "1",
    reason="러너가 띄운 안쪽 pytest — 재귀 방지를 위해 건너뛴다",
)


def run_test_sh(*args, env_overrides=None):
    """scripts/test.sh 를 자식으로 실행한다. 자식이 띄우는 pytest 는 이 모듈을 skip 한다."""
    env = dict(os.environ)
    env[CHILD_ENV_FLAG] = "1"
    # 자식 러너가 '지금 이 pytest' 를 쓰도록 인터프리터를 못박는다. 러너의 자동 탐색은
    # python3/python 만 뒤지므로, 바깥 pytest 가 venv 나 그 이름으로 안 잡히는 인터프리터에서
    # 돌고 있으면 자식은 pytest 를 못 찾아 스위트를 통째로 건너뛴다 — 그러면 '실행된 스위트
    # 없음' 이 되어, 여기서 검증하려는 실패/성공 계약이 아니라 환경을 측정하게 된다.
    # 백슬래시는 슬래시로 바꾼다: Git Bash 에 Windows 절대 경로를 넘기면 경로가 뭉개진다.
    env["CLAUDE_TEST_PYTHON"] = sys.executable.replace("\\", "/")
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [BASH, TEST_SH_REL, *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )


@requires_bash
def test_test_sh_syntax_is_valid():
    proc = subprocess.run([BASH, "-n", TEST_SH_REL], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@requires_bash
def test_help_exits_zero_without_running_anything():
    proc = run_test_sh("--help")
    assert proc.returncode == 0
    assert "사용법" in proc.stdout


@requires_bash
def test_failing_suite_makes_the_runner_fail():
    """pytest 가 실패하면(여기서는 매칭되는 테스트가 없어 exit 5) 러너도 1 이어야 한다.
    -k 가 아무것도 매칭하지 않으므로 안쪽 pytest 는 수집만 하고 테스트를 실행하지 않는다."""
    proc = run_test_sh("--python-only", "-k", "__no_such_test_name__")
    assert proc.returncode == 1, proc.stdout[-2000:]
    assert "실패" in proc.stdout


@requires_bash
def test_nothing_runnable_is_not_success(tmp_path):
    """러너를 하나도 못 찾은 상황. python 조차 없으면 검증된 것이 0개이므로 0 으로 끝나면
    안 된다 — 이게 첫 구현의 실제 버그였다(전부 건너뛰고 '모두 통과')."""
    # bash 는 절대 경로로 부르므로 PATH 에 아무것도 없어도 스크립트 자체는 돈다. 예전에는
    # bash 를 심볼릭 링크로 남겼는데, Windows 에서는 심볼릭 링크 생성에 별도 권한이 필요해
    # 테스트가 환경 탓으로 깨진다 — 링크 없이 빈 디렉터리만 주는 편이 이식성이 높다.
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    # CLAUDE_TEST_PYTHON 도 비운다 — 절대 경로로 인터프리터를 못박아 두면 PATH 를 비워도
    # pytest 가 돌아버려서, 정작 재현하려는 '아무 러너도 못 찾은 상황' 이 만들어지지 않는다.
    proc = run_test_sh(env_overrides={"PATH": str(empty_bin), "CLAUDE_TEST_PYTHON": ""})
    assert proc.returncode == 1, proc.stdout[-2000:]
    assert "실행된 스위트가 없습니다" in proc.stdout


@requires_bash
def test_python_only_skips_are_not_counted_by_strict():
    """--python-only 로 '요청하지 않은' 스위트는 러너 미설치로 '못 돌린' 스위트와 다르다.
    사용자가 직접 고른 선택을 --strict 가 실패로 만들면 안 된다."""
    proc = run_test_sh("--python-only", "--strict", "-k", "test_rm_root_denied")
    assert proc.returncode == 0, proc.stdout[-2000:]


@requires_bash
def test_unusable_explicit_interpreter_fails_instead_of_skipping():
    """CLAUDE_TEST_PYTHON 으로 지정한 인터프리터를 못 쓰면 '건너뜀' 이 아니라 실패여야 한다.
    지정한 인터프리터가 안 돈다는 것은 아무것도 검증되지 않았다는 뜻이라, skip 으로 삼키면
    --strict 없이 돌리는 CI 에서 통과로 읽힌다."""
    proc = run_test_sh("--python-only", env_overrides={"CLAUDE_TEST_PYTHON": "/no/such/python"})
    assert proc.returncode == 1, proc.stdout[-2000:]
    assert "실패" in proc.stdout
    assert "건너뜀" not in proc.stdout


@requires_bash
def test_auto_discovery_finds_pytest_when_not_pinned():
    """CLAUDE_TEST_PYTHON 없이도 러너가 스스로 pytest 가 도는 인터프리터를 찾아야 한다.

    run_test_sh 는 이제 항상 인터프리터를 못박으므로, 이 테스트가 없으면 자동 탐색
    (resolve_pytest_python)을 성공적으로 타는 경로가 하나도 남지 않는다. 실제로 그 함수를
    통째로 `return 1` 로 망가뜨려도 이 모듈의 나머지 테스트는 전부 통과했다 — 정작 사람이
    `bash scripts/test.sh` 를 그냥 치면 pytest 가 멀쩡히 깔려 있는데도 'pytest 미설치' 로
    스위트 전체를 건너뛴다."""
    proc = run_test_sh("--python-only", "-k", "test_rm_root_denied",
                       env_overrides={"CLAUDE_TEST_PYTHON": ""})
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert "인터프리터:" in proc.stdout, proc.stdout[-2000:]


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


def test_pester_실패가_러너의_종료코드에_반영된다():
    """Invoke-Pester 는 테스트가 실패해도 종료 코드 0 을 낸다 (Pester 5 엔 -EnableExit 도 없다).

    그래서 러너가 결과 객체의 FailedCount 를 직접 종료 코드로 만들지 않으면, 깨진 Pester
    테스트가 영원히 '통과' 로 보고된다 — 이 파일이 막으려는 바로 그 거짓 통과다. 실제로
    test.sh 가 이 버그를 갖고 있었다(실패 1건인데 '✅ Pester 통과' 출력).

    pwsh 없이도 회귀를 잡아야 하므로 소스를 정적으로 검사한다.
    """
    for runner in (REPO_ROOT / TEST_SH_REL, TEST_PS1):
        source = runner.read_text(encoding="utf-8")
        if "Invoke-Pester" not in source:
            continue
        assert "FailedCount" in source, (
            f"{runner.name} 이 Invoke-Pester 결과를 FailedCount 로 판정하지 않는다 — "
            "Pester 실패가 통과로 보고된다"
        )
        assert "-PassThru" in source, (
            f"{runner.name} 은 -PassThru 로 결과 객체를 받아야 FailedCount 를 볼 수 있다"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 에서만 실제 실행 검증")
def test_test_ps1_help_exits_zero():
    proc = subprocess.run(
        [PWSH or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(TEST_PS1), "-Help"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert "사용법" in (proc.stdout or "")


@pytest.mark.skipif(PWSH is None, reason="pwsh/powershell 을 찾지 못함")
def test_ps_unusable_explicit_interpreter_fails_instead_of_skipping():
    """PowerShell 러너도 bash 러너와 같은 계약을 지켜야 한다 — 지정한 인터프리터를 못 쓰면
    '건너뜀' 이 아니라 실패.

    두 러너는 같은 정책을 각자의 방언으로 따로 구현하고 있어서 한쪽만 고쳐도 티가 안 난다.
    이번 세션에서 PowerShell 경로만 조용히 어긋난 사례가 이미 두 번 있었다(설치 셀프테스트가
    PS 백업 스니펫을 한 번도 생성하지 않던 것, clean/stash drop 의 마지막 update-ref 가
    검사 없이 지나가던 것). -PythonOnly 로 부르므로 안쪽 pytest 는 시작조차 하지 않아
    재귀 걱정이 없다."""
    env = dict(os.environ)
    env[CHILD_ENV_FLAG] = "1"
    env["CLAUDE_TEST_PYTHON"] = "X:/no/such/python.exe"
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TEST_PS1), "-PythonOnly"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1, (proc.stdout or "") + (proc.stderr or "")
    assert "실패" in (proc.stdout or "")


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
