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

def test_setup_help_lists_keybinds_and_newline(sandbox_home, stub_bin):
    """covers: Test-15
    setup.sh --help 에 --keybinds 와 --newline 이 보여야 한다.
    """
    proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--help"], sandbox_home, stub_bin)
    assert proc.returncode == 0, proc.stderr
    assert "--keybinds" in proc.stdout, proc.stdout
    assert "--newline" in proc.stdout, proc.stdout


def test_setup_hooks_installs_for_real(sandbox_home, stub_bin):
    proc = run_script(["bash", str(ROOT / "scripts" / "setup.sh"), "--hooks"], sandbox_home, stub_bin)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    hooks = sandbox_home / ".claude" / "hooks"
    assert (hooks / "danger_guard.py").exists()
    assert (hooks / "shims" / "rm").exists()
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
    """레포를 tarball 로 말아, curl 스텁이 그것을 내려받은 척한다 (`-o` 를 존중)."""
    tarball = tmp_path / "repo.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for item in ("install.sh", "scripts", "res"):
            tar.add(ROOT / item, arcname=f"claude-code-setup-main/{item}")
    curl = stub_bin / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "out=''; prev=''\n"
        'for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done\n'
        f'if [ -n "$out" ]; then cp "{tarball}" "$out"; else cat "{tarball}"; fi\n',
        encoding="utf-8",
    )
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


# --- 다운로드 실패 진단 ---
#
# 비공개 레포는 인증 실패를 401 이 아니라 404 로 위장한다. 그래서 만료된 토큰으로 설치하면
# "install.sh 가 없다"처럼 보이는 404 가 나고, 진짜 원인(재로그인 필요)을 알 수 없다.
# install.sh 는 실패 시 GitHub API 를 한 번 찔러 원인을 특정해야 한다.


def failing_curl(bin_dir, api_status):
    """아카이브 다운로드는 실패하고, API 프로브는 지정한 상태코드를 돌려주는 curl 스텁."""
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "for a in \"$@\"; do\n"
        "  case \"$a\" in\n"
        f"    *api.github.com*) printf '%s' '{api_status}'; exit 0 ;;\n"
        "  esac\n"
        "done\n"
        "echo 'curl: (22) The requested URL returned error: 404' >&2\n"
        "exit 22\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    # gh 폴백이 실환경 토큰을 집어오지 않도록 PATH 에서 가린다.
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    gh.chmod(0o755)
    return bin_dir


def install_with(sandbox_home, bin_dir, token=None):
    env = dict(os.environ)
    env["HOME"] = str(sandbox_home)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    if token:
        env["GITHUB_TOKEN"] = token
    return subprocess.run(
        ["sh", str(ROOT / "install.sh"), "--dry-run"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def test_install_sh_diagnoses_expired_token(sandbox_home, stub_bin):
    proc = install_with(sandbox_home, failing_curl(stub_bin, 401), token="ghp_dead")
    assert proc.returncode != 0
    assert "만료" in proc.stderr
    assert "unset GITHUB_TOKEN" in proc.stderr      # gh auth login 이 거부되는 함정까지 안내


def test_install_sh_diagnoses_missing_token(sandbox_home, stub_bin):
    proc = install_with(sandbox_home, failing_curl(stub_bin, 401), token=None)
    assert proc.returncode != 0
    assert "토큰을 찾지 못했습니다" in proc.stderr
    assert "gh auth login" in proc.stderr


def test_install_sh_diagnoses_insufficient_scope(sandbox_home, stub_bin):
    proc = install_with(sandbox_home, failing_curl(stub_bin, 403), token="ghp_weak")
    assert proc.returncode != 0
    assert "권한이 없습니다" in proc.stderr
    assert "Contents:Read" in proc.stderr


def test_install_sh_diagnoses_bad_ref(sandbox_home, stub_bin):
    # API 는 200 (레포 접근 OK) 인데 아카이브만 실패 → ref 가 잘못된 것이다.
    proc = install_with(sandbox_home, failing_curl(stub_bin, 200), token="ghp_ok")
    assert proc.returncode != 0
    assert "ref" in proc.stderr
    assert "refs/heads/" in proc.stderr             # 슬래시 브랜치명 해법 안내


def test_install_sh_falls_back_to_gh_auth_token(sandbox_home, stub_bin):
    """GITHUB_TOKEN 을 export 하지 않아도 gh 에서 토큰을 읽어와야 한다.

    GITHUB_TOKEN 을 셸에 영구 export 하면 gh 가 `gh auth login` 을 거부하게 되므로,
    스크립트가 알아서 gh 를 읽는 편이 안전하다.
    """
    curl = stub_bin / "curl"
    # 토큰이 실제로 전달됐는지 -K 설정 파일 내용으로 확인한 뒤 실패시킨다.
    curl.write_text(
        "#!/bin/sh\n"
        "for a in \"$@\"; do\n"
        "  case \"$a\" in\n"
        "    *api.github.com*) printf '%s' 401; exit 0 ;;\n"
        "  esac\n"
        "done\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = '-K' ]; then grep -q 'gh_token_from_cli' \"$2\" && echo 'TOKEN_FORWARDED' >&2; fi\n"
        "  shift\n"
        "done\n"
        "exit 22\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    gh = stub_bin / "gh"
    gh.write_text("#!/bin/sh\n[ \"$1\" = auth ] && [ \"$2\" = token ] && echo gh_token_from_cli\n", encoding="utf-8")
    gh.chmod(0o755)

    proc = install_with(sandbox_home, stub_bin, token=None)
    assert "TOKEN_FORWARDED" in proc.stderr, proc.stderr
