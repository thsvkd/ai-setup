"""OMC 설치 + HUD 캐시 TTL 표시 (res/omc/, scripts/setup_omc.sh).

실제 홈·플러그인 캐시·claude CLI 를 건드리지 않도록 임시 HOME 과 가짜 플러그인 캐시,
PATH 앞의 claude 스텁으로만 검증한다.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APPLY = ROOT / "res" / "omc" / "apply.py"
TTL = ROOT / "res" / "omc" / "omc-hud-ttl.mjs"
OMC_CMD = "sh ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hud/omc-hud-cache.sh ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hud/omc-hud.mjs"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 필요")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    lib = h / ".claude" / "plugins" / "cache" / "omc" / "oh-my-claudecode" / "5.4.0" / "scripts" / "lib"
    lib.mkdir(parents=True)
    (lib / "hud-wrapper-template.txt").write_text("// omc hud template\n", encoding="utf-8")
    (lib / "config-dir.mjs").write_text("// config dir\n", encoding="utf-8")
    return h


def apply(home, *args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(APPLY), "--home", str(home), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))


def write_settings(home, data):
    (home / ".claude" / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def test_기존_OMC_statusLine_앞에_TTL_래퍼를_끼우고_uninstall로_원복한다(home):
    before = {"model": "opus", "statusLine": {"type": "command", "command": OMC_CMD}}
    write_settings(home, before)

    proc = apply(home)
    assert proc.returncode == 0, proc.stderr
    status = settings(home)["statusLine"]
    assert status["command"].startswith('node "')
    assert status["command"].endswith(OMC_CMD)
    assert "omc-hud-ttl.mjs" in status["command"]
    assert status["refreshInterval"] == 10
    assert (home / ".claude" / "hud" / "omc-hud-ttl.mjs").is_file()

    # 멱등: 두 번 실행해도 접두가 겹치지 않는다
    assert apply(home).returncode == 0
    assert settings(home)["statusLine"]["command"].count("omc-hud-ttl.mjs") == 1

    proc = apply(home, "--uninstall")
    assert proc.returncode == 0, proc.stderr
    assert settings(home) == before
    assert not (home / ".claude" / "hud" / "omc-hud-ttl.mjs").exists()


def test_사용자가_정한_refreshInterval은_uninstall이_지우지_않는다(home):
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD, "refreshInterval": 3}})
    assert apply(home).returncode == 0
    assert settings(home)["statusLine"]["refreshInterval"] == 3
    assert apply(home, "--uninstall").returncode == 0
    assert settings(home)["statusLine"] == {"type": "command", "command": OMC_CMD, "refreshInterval": 3}


def test_statusLine이_없으면_OMC_HUD를_복사하고_설정한다(home):
    assert apply(home).returncode == 0
    hud = home / ".claude" / "hud"
    assert (hud / "omc-hud.mjs").read_text(encoding="utf-8") == "// omc hud template\n"
    assert (hud / "lib" / "config-dir.mjs").is_file()
    assert settings(home)["statusLine"]["command"].endswith('/omc-hud.mjs"')


def test_OMC가_아닌_statusLine은_건드리지_않는다(home):
    mine = {"statusLine": {"type": "command", "command": "~/my-status.sh"}}
    write_settings(home, mine)
    proc = apply(home)
    assert proc.returncode == 0
    assert settings(home) == mine
    assert not (home / ".claude" / "hud" / "omc-hud-ttl.mjs").exists()


def test_파싱할_수_없는_settings는_멈추고_쓰지_않는다(home):
    path = home / ".claude" / "settings.json"
    path.write_text("{ broken", encoding="utf-8")
    proc = apply(home)
    assert proc.returncode == 1
    assert path.read_text(encoding="utf-8") == "{ broken"


def test_dry_run은_아무것도_쓰지_않는다(home):
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    before = (home / ".claude" / "settings.json").read_text(encoding="utf-8")
    proc = apply(home, "--dry-run")
    assert proc.returncode == 0
    assert "DRY RUN" in proc.stdout
    assert (home / ".claude" / "settings.json").read_text(encoding="utf-8") == before
    assert not (home / ".claude" / "hud").exists()
    assert not (home / ".claude" / ".claude-code-setup.json").exists()


def test_영수증은_다른_섹션을_보존한다(home):
    manifest = home / ".claude" / ".claude-code-setup.json"
    manifest.write_text(json.dumps({"keybinds": {"x": 1}}), encoding="utf-8")
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    assert apply(home).returncode == 0
    assert json.loads(manifest.read_text(encoding="utf-8"))["keybinds"] == {"x": 1}
    assert apply(home, "--uninstall").returncode == 0
    assert json.loads(manifest.read_text(encoding="utf-8")) == {"keybinds": {"x": 1}}


# ── 래퍼: session:NNm → cache:... ─────────────────────────────────────


def run_ttl(stdin_obj, hud_line):
    """가짜 HUD(printf)를 안쪽 명령으로 물려 래퍼 출력을 받는다."""
    return subprocess.run(
        ["node", str(TTL), sys.executable, "-c", f"import sys; sys.stdin.read(); print({hud_line!r})"],
        input=json.dumps(stdin_obj), capture_output=True, text=True, encoding="utf-8", timeout=30,
    ).stdout


HUD = "[OMC] | thinking | session:\x1b[32m45m\x1b[0m\nctx:[#---]8%"


@needs_node
def test_남은_TTL을_분으로_보여준다():
    out = run_ttl({"prompt_cache": {"warm": True, "expires_at": time.time() + 30 * 60 + 5}}, HUD)
    assert "session:" not in out
    assert "cache:\x1b[32m30m\x1b[0m" in out
    assert out.endswith("ctx:[#---]8%\n")


@needs_node
def test_2분_이하는_노랑_1분_미만은_초로_보여준다():
    out = run_ttl({"prompt_cache": {"warm": True, "expires_at": time.time() + 45}}, HUD)
    assert "cache:\x1b[33m44s\x1b[0m" in out or "cache:\x1b[33m45s\x1b[0m" in out


@needs_node
def test_만료되면_cold로_보여준다():
    out = run_ttl({"prompt_cache": {"warm": True, "expires_at": time.time() - 10}}, HUD)
    assert "cache:\x1b[31mcold\x1b[0m" in out


@needs_node
def test_캐시_정보가_없으면_session_표시를_그대로_둔다():
    """구버전 Claude Code 처럼 prompt_cache 가 없으면 쓸모 있는 세션 시간을 지우지 않는다."""
    assert run_ttl({}, HUD) == HUD + "\n"


@needs_node
def test_안쪽_명령의_실패를_종료코드와_stderr로_전달한다():
    proc = subprocess.run(
        ["node", str(TTL), sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
        input="{}", capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 3
    assert "boom" in proc.stderr


def test_statusLine이_없던_설치는_uninstall이_만든_것을_모두_치운다(home):
    assert apply(home).returncode == 0
    assert apply(home, "--uninstall").returncode == 0
    assert not (home / ".claude" / "settings.json").exists()
    assert not (home / ".claude" / "hud").exists()
    assert not (home / ".claude" / ".claude-code-setup.json").exists()


def test_설치_뒤_사용자가_바꾼_refreshInterval은_uninstall이_남긴다(home):
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    assert apply(home).returncode == 0
    data = settings(home)
    data["statusLine"]["refreshInterval"] = 2
    write_settings(home, data)
    assert apply(home, "--uninstall").returncode == 0
    assert settings(home)["statusLine"] == {"type": "command", "command": OMC_CMD, "refreshInterval": 2}


def test_OMC가_아닌_statusLine이면_hud_파일도_만들지_않는다(home):
    write_settings(home, {"statusLine": {"type": "command", "command": "~/my-status.sh"}})
    assert apply(home).returncode == 0
    assert not (home / ".claude" / "hud").exists()


def test_깨진_매니페스트는_덮어쓰지_않고_멈춘다(home):
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    manifest = home / ".claude" / ".claude-code-setup.json"
    manifest.write_text('{ "hook_files": [', encoding="utf-8")
    assert apply(home).returncode == 1
    assert manifest.read_text(encoding="utf-8") == '{ "hook_files": ['
    assert "omc-hud-ttl" not in settings(home)["statusLine"]["command"]


def test_재실행은_settings를_다시_쓰지_않아_백업이_쌓이지_않는다(home):
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    assert apply(home).returncode == 0
    backups = set((home / ".claude").glob("settings.json.bak.*"))
    assert apply(home).returncode == 0
    assert set((home / ".claude").glob("settings.json.bak.*")) == backups


@pytest.mark.skipif(os.name == "nt", reason="find-node.sh 는 POSIX 전용")
def test_OMC의_find_node가_있으면_그것으로_node를_찾는다(home):
    """PATH 에 node 가 없는 셸에서도 OMC HUD 가 뜨던 곳이면 래퍼도 떠야 한다."""
    (home / ".claude" / "hud").mkdir()
    (home / ".claude" / "hud" / "find-node.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    assert apply(home).returncode == 0
    command = settings(home)["statusLine"]["command"]
    assert command.startswith('sh "$HOME/.claude/hud/find-node.sh" "$HOME/.claude/hud/omc-hud-ttl.mjs" ')
    assert apply(home, "--uninstall").returncode == 0
    assert settings(home)["statusLine"]["command"] == OMC_CMD


# ── setup.sh --omc: claude CLI 는 스텁 ────────────────────────────────


posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="POSIX 셸 스크립트 테스트 (bash 필요)",
)


def stub_claude(tmp_path, installed):
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir()
    log = tmp_path / "claude.log"
    listed = "  ❯ oh-my-claudecode@omc" if installed else "  ❯ other@x"
    (bin_dir / "claude").write_text(
        f'#!/bin/sh\necho "$*" >> "{log}"\n'
        f'case "$*" in "plugin list") echo "{listed}" ;; esac\n',
        encoding="utf-8",
    )
    (bin_dir / "claude").chmod(0o755)
    return bin_dir, log


def run_setup(args, home, bin_dir):
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(["bash", str(ROOT / "scripts" / "setup.sh"), *args], env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


@posix_only
def test_setup_omc는_플러그인을_설치하고_HUD를_설정한다(tmp_path, home):
    bin_dir, log = stub_claude(tmp_path, installed=False)
    proc = run_setup(["--omc"], home, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = log.read_text(encoding="utf-8")
    assert "plugin marketplace add Yeachan-Heo/oh-my-claudecode" in calls
    assert "plugin install oh-my-claudecode@omc" in calls
    assert "omc-hud-ttl.mjs" in settings(home)["statusLine"]["command"]
    # --omc 만 줬으므로 훅은 설치되지 않는다
    assert "hooks" not in settings(home)


@posix_only
def test_setup_omc_dry_run은_claude를_실행하지_않는다(tmp_path, home):
    bin_dir, log = stub_claude(tmp_path, installed=False)
    proc = run_setup(["--omc", "--dry-run"], home, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "(dry-run) claude plugin install oh-my-claudecode@omc" in proc.stdout
    assert "install" not in log.read_text(encoding="utf-8")
    assert not (home / ".claude" / "settings.json").exists()


@posix_only
def test_훅만_먼저_제거해도_OMC_영수증이_남아_나중에_refreshInterval을_되돌린다(tmp_path, home):
    bin_dir, _ = stub_claude(tmp_path, installed=True)
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    assert run_setup(["--omc"], home, bin_dir).returncode == 0
    proc = run_setup(["--uninstall", "--hooks"], home, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = run_setup(["--uninstall", "--omc"], home, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert settings(home)["statusLine"] == {"type": "command", "command": OMC_CMD}


@posix_only
def test_setup_uninstall은_TTL_HUD도_되돌린다(tmp_path, home):
    bin_dir, _ = stub_claude(tmp_path, installed=True)
    write_settings(home, {"statusLine": {"type": "command", "command": OMC_CMD}})
    assert run_setup(["--omc"], home, bin_dir).returncode == 0
    proc = run_setup(["--uninstall"], home, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert settings(home)["statusLine"] == {"type": "command", "command": OMC_CMD}
