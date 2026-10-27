"""res/onboard.py (대화형 온보딩) 와 그 선택이 설치에 반영되는 경로 테스트.

온보딩의 위험은 '안 뜨는 것'이 아니라 **묻지도 않고 뭔가를 골라버리는 것**이다. 실측해보면
questionary 는 stdin 이 파이프일 때(= curl | sh) 에러도 없이 첫 항목을 자동 확정한다. 그래서
여기서는 프롬프트가 뜨는 경우뿐 아니라, 띄울 수 없는 상황에서 **아무 선택도 하지 않는지**를
같은 비중으로 검증한다.

pty 를 쓰는 테스트는 실제 터미널 상호작용을 재현한다 — 느리지만, 이 기능에서 유일하게
의미 있는 검증이다. Windows 에서는 pty/POSIX 셸이 없어 건너뛴다.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ONBOARD = ROOT / "res" / "onboard.py"

DOWN = b"\x1b[B"
UP = b"\x1b[A"
ENTER = b"\r"
CTRL_C = b"\x03"
SPACE = b" "        # 체크박스에서 항목 선택/해제

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NON_INTERACTIVE = 2
EXIT_CANCELLED = 130

posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="POSIX only (needs pty / bash)",
)


def clean_env(**extra):
    """CI 감지에 걸리지 않는 환경. 테스트 러너 자체가 CI 에서 도는 경우를 배제한다."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE")}
    env["TERM"] = "xterm-256color"
    env.update(extra)
    if "HOME" not in extra:
        # 실제 홈에 영수증이 있으면 산책 대신 허브가 뜬다. 테스트마다 빈 홈에서 시작한다.
        # ponytail: 임시 홈은 지우지 않는다. 쌓이는 게 문제가 되면 tmp_path 를 받게 바꾼다.
        env["HOME"] = env["USERPROFILE"] = tempfile.mkdtemp(prefix="ai-setup-onboard-home-")
    return env


def run_in_pty(argv, keys, cwd=None, env=None, stdin_pipe=False, timeout=25):
    """argv 를 제어 터미널이 붙은 pty 아래에서 실행하고 keys 를 차례로 보낸다.

    stdin_pipe=True 면 stdin 을 파이프로 준다 — `curl … | sh` 재현이다. 이때 프롬프트가
    동작하려면 onboard.py 가 /dev/tty 를 직접 열어야만 한다.

    반환: (종료코드, 화면에 찍힌 raw 바이트)
    """
    import fcntl
    import pty
    import select
    import termios

    master, slave = pty.openpty()
    # termios.tcsetwinsize 는 3.11+ 라, 낮은 버전에서도 같은 폭이 되도록 ioctl 로 맞춘다.
    import struct
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))

    if stdin_pipe:
        pin_r, pin_w = os.pipe()
        os.write(pin_w, b"# leftover install.sh body\n" * 5)
        os.close(pin_w)
        child_stdin = pin_r
    else:
        child_stdin = slave

    def attach_ctty():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(
        argv, stdin=child_stdin, stdout=slave, stderr=slave,
        preexec_fn=attach_ctty, cwd=str(cwd) if cwd else None, env=env or clean_env(),
    )
    os.close(slave)
    if stdin_pipe:
        os.close(child_stdin)

    out = bytearray()

    def drain(seconds, quiet=None):
        """seconds 동안 읽는다. quiet 가 있으면 출력이 한 번 나온 뒤 그만큼 멎는 순간 일찍 끝낸다.

        실제 터미널처럼 커서 위치 요청(CPR)에 답한다. 답하지 않으면 prompt_toolkit 이
        답마다 1초씩 아무것도 찍지 않고 기다려, 무출력 판정이 그 틈에 걸린다.
        """
        end = time.time() + seconds
        last = None
        while time.time() < end:
            if quiet is not None and last is not None and time.time() - last >= quiet:
                return
            ready, _, _ = select.select([master], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:
                return
            if not chunk:
                return
            out.extend(chunk)
            last = time.time()
            if b"\x1b[6n" in chunk:
                try:
                    os.write(master, b"\x1b[1;1R")
                except OSError:
                    return

    # 고정 대기는 느린 기기에서 다음 프롬프트가 그려지기 전에 키를 보내 버린다(선행 입력).
    # 그러면 선택지가 화면에 안 나오므로, 출력이 잠잠해질 때까지 기다렸다가 보낸다.
    # 무출력은 '프롬프트가 다 그려졌다'의 근사일 뿐이다. 키마다 최대 15초까지 기다린다.
    try:
        drain(15.0, quiet=1.0)  # 첫 프롬프트가 그려질 때까지
        for key in keys:
            try:
                os.write(master, key)
            except OSError:
                break
            drain(15.0, quiet=1.0)  # 선택이 반영되고 다음 프롬프트가 그려질 때까지

        deadline = time.time() + timeout
        while proc.poll() is None and time.time() < deadline:
            drain(0.5)
        if proc.poll() is None:
            proc.kill()
            pytest.fail(f"Process did not finish. Screen:\n{bytes(out).decode(errors='replace')}")
        return proc.wait(timeout=5), bytes(out)
    finally:
        os.close(master)


def read_answers(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


# ── 대화형으로 물을 수 없는 상황: 아무것도 고르지 않아야 한다 ──────────────────


def test_no_tty_selects_nothing(tmp_path):
    """가장 중요한 계약. 여기서 뭔가를 골라버리면 사용자가 동의한 적 없는 설치가 일어난다."""
    out = tmp_path / "answers"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", env=clean_env(), timeout=60,
    )
    assert proc.returncode == EXIT_NON_INTERACTIVE
    assert read_answers(out) == {}


def test_ci_environment_shows_no_prompt(tmp_path):
    """CI 는 TTY 를 붙여주기도 한다(docker -t, tmux). TTY 검사만으로는 못 거른다."""
    out = tmp_path / "answers"
    env = clean_env(CI="true")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    assert proc.returncode == EXIT_NON_INTERACTIVE
    assert read_answers(out) == {}


@posix_only
def test_ci_env_var_blocks_prompt_even_with_tty(tmp_path):
    out = tmp_path / "answers"
    code, _ = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        keys=[], env=clean_env(CI="true"),
    )
    assert code == EXIT_NON_INTERACTIVE
    assert read_answers(out) == {}


# ── 실제 터미널 상호작용 ──────────────────────────────────────────────


# 산책 키 위치: 0 시작 · 1 base · 2 하네스 선택 · 3 하네스 설치 · 4 plugins · 5 skills ·
# 6 codegraph · 7 mcp · 8 줄바꿈 · 9 줄바꿈 키 · 10 Claude 전용 · 11-13 출력 스타일·mod·HUD ·
# 14 tools · 15 Jarvis · 16 herdr · 17 hooks · 18 권한 · 19 AGENTS.md · 20 허브(커서는 Apply).
ACCEPT_APPLY = [ENTER] * 21
ACCEPT_DRY = [ENTER] * 20 + [DOWN, ENTER]
# Skip 은 허브로 간다. 허브 커서는 첫 카테고리이므로 ↑ 한 번이면 맨 끝의 Quit 이다.
SKIP_THEN_QUIT = [DOWN, ENTER, UP, ENTER]


@posix_only
def test_default_choices_give_full_install_with_auto(tmp_path):
    """Enter 만으로 기본 산책: Claude Code·Codex, Shift+Enter, Claude 전용 설정은 예, Jarvis 는 설치하지 않음."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=ACCEPT_APPLY,
        timeout=90,
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_OK, text
    assert "Shift+Enter" in text and "Ctrl+Enter" in text, text
    assert "Claude Code" in text and "Codex" in text, text
    assert read_answers(out) == {
        "SKIP": "0",
        "STAGES": "base,harness,plugins,skills,codegraph,mcp,newline,claude_special,tools,hooks,agentsmd",
        "HARNESSES": "claude,codex",
        "DEFAULT_MODE": "auto",
        "JARVIS_ROLE": "none",
        "HERDR": "0",
        "DRY_RUN": "0",
        "OMC": "1",
        "OUTPUT_STYLE": "1",
        "MODS": "1",
        "OVERWRITE_AGENTSMD": "0",
        "NEWLINE_CHORD": "shift-enter",
    }


@posix_only
def test_prompt_works_under_curl_pipe_install(tmp_path):
    """`curl … | sh` 는 stdin 이 스크립트 본문이다. /dev/tty 를 열지 못하면 여기서 깨진다.

    첫 항목을 자동 확정하면 Skip 이 아니라 산책이 시작된다. Skip 뒤 허브의 Quit 이 기록돼야
    키를 받은 것이다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=SKIP_THEN_QUIT,
        stdin_pipe=True,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert read_answers(out) == {"SKIP": "1"}


@posix_only
def test_bypass_choice_shows_warning(tmp_path):
    out = tmp_path / "answers"
    _, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 18 + [DOWN, ENTER, ENTER, ENTER],
        timeout=90,
    )
    text = screen.decode(errors="replace")
    assert "bypassPermissions skips all of Claude Code's permission prompts" in text, text


@posix_only
def test_ctrl_c_cancel_is_distinct_from_noninteractive_fallback(tmp_path):
    """covers: Test-4
    130 과 2 를 뭉뚱그리면 '취소했는데 기본값으로 설치되는' 최악의 동작이 된다.
    """
    out = tmp_path / "answers"
    code, _ = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        keys=[CTRL_C],
    )
    assert code == EXIT_CANCELLED
    assert read_answers(out) == {}
    assert not out.exists() or not out.read_text(encoding="utf-8").strip()


@posix_only
def test_broken_prompt_aborts_instead_of_falling_back_to_defaults(tmp_path):
    """렌더·입력 오류는 2(물을 수 없음)가 아니다. 사용자는 고르던 중이었으므로 1 로 멈춘다.

    첫 질문에 답한 뒤 두 번째 질문을 그리다 깨지는 tui 를 옆에 둔다.
    """
    shutil.copy(ONBOARD, tmp_path / "onboard.py")
    real_tui = (ROOT / "res" / "tui.py").read_text(encoding="utf-8")
    (tmp_path / "tui.py").write_text(
        real_tui + "\n\ndef confirm(*a, **k):\n    raise RuntimeError('render broke')\n",
        encoding="utf-8",
    )
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(tmp_path / "onboard.py"), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER],
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_FAILED, text
    assert "render broke" in text, text
    assert "nothing was installed" in text, text
    assert read_answers(out) == {}


@posix_only
def test_console_setup_failure_proceeds_with_defaults_before_drawing(tmp_path):
    """보이지 않는 콘솔·VT 미지원처럼 아무것도 그리기 전에 실패하면 '물을 수 없음'(2)이다."""
    shutil.copy(ONBOARD, tmp_path / "onboard.py")
    real_tui = (ROOT / "res" / "tui.py").read_text(encoding="utf-8")
    (tmp_path / "tui.py").write_text(
        real_tui + "\n\ndef prepare_console():\n    raise OSError('not a console')\n",
        encoding="utf-8",
    )
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(tmp_path / "onboard.py"), "--out", str(out)],
        keys=[],
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_NON_INTERACTIVE, text
    assert "What would you like to install?" not in text, text
    assert "Set up this machine?" not in text, text
    assert read_answers(out) == {}


@posix_only
def test_closed_stdin_ends_as_cannot_ask(tmp_path):
    out = tmp_path / "answers"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        stdin=subprocess.DEVNULL, capture_output=True, env=clean_env(), timeout=60,
        preexec_fn=lambda: os.close(0),
    )
    assert proc.returncode == EXIT_NON_INTERACTIVE, proc.stderr
    assert read_answers(out) == {}


@posix_only
def test_overwrite_asked_only_when_agentsmd_exists(tmp_path):
    (tmp_path / "AGENTS.md").write_text("기존 프로젝트 규칙\n", encoding="utf-8")
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 22,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert "already exists" in screen.decode(errors="replace")
    # confirm 의 기본값은 '아니오' — 사용자 콘텐츠는 실수로 날아가면 안 된다.
    assert read_answers(out)["OVERWRITE_AGENTSMD"] == "0"
    assert read_answers(out)["NEWLINE_CHORD"] == "shift-enter"


@posix_only
def test_ctrl_enter_choice_makes_newline_chord_ctrl_enter(tmp_path):
    """covers: Test-1
    SCOPE=all 에서 줄바꿈 키 두 번째 항목(Ctrl+Enter)을 고르면 답 파일이 ctrl-enter 다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 9 + [DOWN, ENTER] + [ENTER] * 11,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SKIP"] == "0"
    assert answers["NEWLINE_CHORD"] == "ctrl-enter"


@posix_only
def test_scope_hooks_does_not_ask_newline_chord(tmp_path):
    """줄바꿈 단계를 끄면 줄바꿈 키를 묻지 않고 NEWLINE_CHORD 를 기록하지 않는다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 8 + [b"n"] + [ENTER] * 11,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert "newline" not in answers["STAGES"].split(",")
    assert "NEWLINE_CHORD" not in answers


@posix_only
def test_accepts_application_cursor_mode_arrows(tmp_path):
    """tmux·vim 이후의 셸 등은 화살표를 ESC [ B 가 아니라 ESC O B 로 보낸다.

    이를 놓치면 ↓ 가 무시되고 Enter 가 첫 항목(전체 설치)을 확정한다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[b"\x1bOB", ENTER, b"\x1bOA", ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert read_answers(out) == {"SKIP": "1"}


@posix_only
def test_scope_agentsmd_does_not_ask_newline_chord(tmp_path):
    """AGENTS.md 단계만 켜면 줄바꿈 키를 묻지 않는다. 하네스 기본값은 Claude Code 와 Codex 다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER, b"n", ENTER] + [b"n"] * 9 + [ENTER, ENTER],
        timeout=60,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["STAGES"] == "agentsmd"
    assert "NEWLINE_CHORD" not in answers
    assert answers["HARNESSES"] == "claude,codex"


@posix_only
def test_deselecting_harnesses_records_only_the_chosen(tmp_path):
    """체크박스는 전부 체크된 상태로 뜬다. Space 로 claude 를 해제하면 나머지만 남는다.

    이 경로가 깨지면 Codex 만 쓰는 사용자의 프로젝트에도 CLAUDE.md 가 생긴다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 2 + [SPACE, ENTER] + [ENTER] * 15,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["HARNESSES"] == "codex"
    assert answers["OMC"] == "0"


@posix_only
def test_skip_then_quit_selects_nothing(tmp_path):
    """covers: AI-47
    Skip 뒤 허브에서 Quit 하면 하네스를 고르지 않고 설치 선택도 남기지 않는다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=SKIP_THEN_QUIT,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers == {"SKIP": "1"}
    assert "HARNESSES" not in answers


@posix_only
def test_choosing_omc_records_omc_as_1(tmp_path):
    """출력 스타일과 mod 는 아니오, OMC HUD 래퍼만 예."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 11 + [b"n", b"n", b"y"] + [ENTER] * 7,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["OMC"] == "1"
    assert answers["OUTPUT_STYLE"] == "0"
    assert answers["MODS"] == "0"


@posix_only
def test_choosing_output_style_records_output_style_as_1(tmp_path):
    """출력 스타일만 예. y 는 confirm 을 곧바로 확정한다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 11 + [b"y", b"n", b"n"] + [ENTER] * 7,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["OMC"] == "0"
    assert answers["OUTPUT_STYLE"] == "1"
    assert answers["MODS"] == "0"


@posix_only
def test_choosing_mod_records_mods_as_1(tmp_path):
    """mod 만 예."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER] * 11 + [b"n", b"y", b"n"] + [ENTER] * 7,
        timeout=90,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["OUTPUT_STYLE"] == "0"
    assert answers["MODS"] == "1"
    assert answers["OMC"] == "0"


@posix_only
def test_scope_agentsmd_does_not_ask_omc(tmp_path):
    """AGENTS.md 만 고르면 Claude 전용 설정을 묻지 않는다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER, b"n", ENTER] + [b"n"] * 9 + [ENTER, ENTER],
        timeout=60,
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_OK, text
    answers = read_answers(out)
    assert answers["OMC"] == "0"
    assert answers["OUTPUT_STYLE"] == "0"
    assert answers["MODS"] == "0"
    assert "Wrap the OMC HUD" not in text


# ── 카테고리 허브 ─────────────────────────────────────────────────────


@posix_only
def test_skip_opens_hub_and_apply_records_the_edited_selection(tmp_path):
    """covers: AI-45
    Skip 은 설치하지 않고 허브로 간다. 허브에서 Base 를 끄고 Apply 하면 나머지 기본값이 기록된다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        # Skip → 허브(Base) → Base 끔 → 허브 커서는 Base → ↓10 번이면 Apply.
        keys=[DOWN, ENTER, ENTER, b"n"] + [DOWN] * 10 + [ENTER],
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_OK, text
    assert "Choose a category to change" in text, text
    answers = read_answers(out)
    assert answers["SKIP"] == "0"
    assert answers["DRY_RUN"] == "0"
    assert answers["STAGES"] == "harness,plugins,skills,codegraph,mcp,newline,claude_special,tools,hooks,agentsmd"
    assert answers["HARNESSES"] == "claude,codex"


@posix_only
def test_apply_with_every_stage_off_selects_nothing(tmp_path):
    """covers: AI-47
    모든 단계를 끄고 Apply 하면 Quit 과 같다. 빈 STAGES 는 setup 스크립트에서 예전 전체 설치가 된다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        # 시작 · base n · 하네스 선택 · 하네스 설치 n · 나머지 9 단계 n · 허브 Apply.
        keys=[ENTER, b"n", ENTER] + [b"n"] * 10 + [ENTER],
        timeout=60,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert read_answers(out) == {"SKIP": "1"}


@posix_only
def test_receipt_opens_hub_without_the_walk(tmp_path):
    """covers: AI-46
    영수증이 있는 머신은 산책 질문 없이 허브부터 연다. 허브의 Quit 은 아무것도 설치하지 않는다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".claude-code-setup.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[UP, ENTER],
        env=clean_env(HOME=str(home)),
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_OK, text
    assert "Set up this machine?" not in text, text
    assert "Choose a category to change" in text, text
    assert read_answers(out) == {"SKIP": "1"}


@posix_only
@pytest.mark.parametrize("mode", ["bypassPermissions", "acceptEdits"])
def test_untouched_hub_apply_does_not_change_the_recorded_mode_or_newline_key(tmp_path, monkeypatch, mode):
    """기록된 값을 메뉴가 보여 줄 수 없어도(acceptEdits), 손대지 않은 Apply 는 그 값을 바꾸지 않는다.
    답이 다른 값을 담으면 setup 이 명시한 값으로 넘기고, stages 가 훅을 다시 깔아 사용자의 값을 되돌린다.
    답을 실제 stages 계획에 넣어 본다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".claude-code-setup.json").write_text(
        json.dumps({"hooks": True, "keybinds": {"newline_chord": "ctrl-enter"}}), encoding="utf-8")
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": mode}}), encoding="utf-8")
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[UP, UP, UP, ENTER],
        env=clean_env(HOME=str(home)),
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SKIP"] == "0" and "hooks" in answers["STAGES"] and "newline" in answers["STAGES"]
    spec = importlib.util.spec_from_file_location("stages_under_test", ROOT / "res" / "stages.py")
    stages = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, stages)    # dataclass 가 자기 모듈을 찾는다
    spec.loader.exec_module(stages)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    selection = {"stages": ["hooks", "newline"]}
    if "DEFAULT_MODE" in answers:
        selection["permission_mode"] = answers["DEFAULT_MODE"]
    if "NEWLINE_CHORD" in answers:
        selection["newline"] = answers["NEWLINE_CHORD"]
    actions = stages.plan_actions(selection, stages.probe_world(str(tmp_path)))
    assert not any(action.writes for action in actions), [action.detail for action in actions]


@posix_only
def test_untouched_hub_apply_forwards_a_recorded_mode_when_hooks_are_not_installed_yet(tmp_path):
    """영수증은 있지만 훅은 아직 깔지 않은 머신. 메뉴가 보여 준 bypassPermissions 를 넘기지 않으면
    stages 가 기본값 auto 로 훅을 깔아 사용자의 값을 바꾼다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".claude-code-setup.json").write_text(json.dumps({"keybinds": {}}), encoding="utf-8")
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "bypassPermissions"}}), encoding="utf-8")
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[UP, UP, UP, ENTER],
        env=clean_env(HOME=str(home)),
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert read_answers(out)["DEFAULT_MODE"] == "bypassPermissions"


def test_recorded_choices_read_a_settings_file_with_a_bom(tmp_path, monkeypatch):
    """Windows 의 메모장·PS 5.1 Set-Content 는 BOM 을 붙인다. stages 는 utf-8-sig 로 읽으므로 같아야 한다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"defaultMode": "bypassPermissions"}}), encoding="utf-8-sig")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    spec = importlib.util.spec_from_file_location("onboard_under_test", ONBOARD)
    onboard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(onboard)
    assert onboard.recorded_choices() == {"mode": "bypassPermissions"}


def test_hub_rows_show_each_category_selection():
    """허브 줄은 카테고리마다 현재 선택을 보여 주고, 끝은 Apply·Preview·Quit 이다."""
    sys.path.insert(0, str(ROOT / "res"))
    import onboard
    import stages

    assert onboard.STAGE_ORDER == stages.STAGE_ORDER
    state = onboard.default_state()
    state["stages"] -= {"mcp", "plugins"}
    state["harnesses"] = ["codex"]
    state["mode"] = "bypassPermissions"
    rows = {value: label for value, label, _ in onboard.hub_options(state)}
    assert rows["harness"] == "Harnesses · Codex"
    assert rows["plugins"] == "Plugins · off"
    assert rows["codegraph"] == "CodeGraph · package"
    assert rows["claude_special"] == "Claude extras · on · needs Claude Code"
    assert rows["hooks"] == "Guard hooks · bypassPermissions"
    assert [value for value, _, _ in onboard.hub_options(state)][-3:] == ["apply", "dry", "quit"]


# ── 렌더러 회귀 방지 ─────────────────────────────────────────────────


def test_renderer_builds_frames_without_console():
    """res/tui.py 는 import 와 프레임 계산에 터미널을 요구하지 않는다.

    예전 벤더(prompt_toolkit 3.0.53)는 Python 3.10+ 문법이라 3.9 에서 import 단계에 죽었고,
    온보딩은 아무 말 없이 건너뛰어졌다. 이 테스트는 실행한 인터프리터 하나만 검사하므로,
    낮은 버전 회귀는 CLAUDE_TEST_PYTHON 을 3.9 로 두고 돌려야 잡힌다.
    한글은 2칸이므로, 폭 계산이 틀리면 다시 그릴 때 올라갈 행 수가 어긋난다.
    """
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import tui\n"
        "assert tui.width([('', '한글a')]) == 5\n"
        "rows = [''.join(t for _, t in r) for r in tui.wrap([('', '가나다라마')], 8)]\n"
        "assert rows == ['가나다라', tui.BAR + '  마'], rows\n"
        "opts = [('a', '첫째', '설명'), ('b', '둘째', '')]\n"
        "text = ''.join(t for line in tui.select_lines('active', '질문', opts, 1) for _, t in line)\n"
        "assert '질문' in text and '둘째' in text and '첫째' in text\n"
        "print('OK')\n" % str(ROOT / "res")
    )
    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_install_ps1_forwards_stage_flags_to_setup():
    """Windows 원라이너도 setup.ps1 과 같은 단계 선택을 넘긴다.

    --stages 는 스위치가 아니라 남은 인자다. 부트스트랩이 모르는 옵션으로 거절하면
    POSIX install.sh 만 단계 계획을 실행할 수 있다.
    """
    source = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")
    assert "'^--stages=(.*)$'" in source
    assert "--stages', $stagesValue" in source
    assert "@extra" in source
    assert "nothing is installed" in source


def test_install_ps1_forwards_every_received_switch_to_setup():
    """install.ps1 은 param 블록의 스위치를 해시테이블 스플랫으로 setup.ps1 에 넘기는데,
    그 목록이 param 블록과 따로 적혀 있다. 한쪽에만 추가하면 플래그가 조용히 무시된다 —
    실제로 -NoOnboard 를 추가할 때 이 함정에 빠졌다.

    install.sh 는 "$@" 로 전부 넘기므로 POSIX 쪽에서는 이 비대칭이 드러나지 않는다.
    pwsh 없이도 잡아야 하므로 소스를 정적으로 검사한다.
    """
    import re

    source = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")

    # 최상위 param 블록의 [switch]$Name 들 (Help 는 부트스트랩이 직접 처리하므로 제외)
    param_block = source.split("Set-StrictMode", 1)[0]
    declared = set(re.findall(r"\[switch\]\$(\w+)", param_block)) - {"Help"}
    assert declared, "could not find the switches in install.ps1's param block"

    # setup.ps1 로 넘기는 목록: foreach ($k in 'A', 'B', ...)
    forward_line = re.search(r"foreach \(\$k in ([^)]+)\)", source)
    assert forward_line, "could not find the switch forwarding list in install.ps1"
    forwarded = set(re.findall(r"'(\w+)'", forward_line.group(1)))

    missing = declared - forwarded
    assert not missing, (
        f"switches install.ps1 accepts but does not pass to setup.ps1: {sorted(missing)} — "
        "they are silently ignored even when the user sets them"
    )


def test_install_ps1_forwards_keybinds_and_newline_to_setup():
    """covers: Test-17
    install.ps1 param 에 -Keybinds 스위치와 -Newline 문자열이 있고,
    둘 다 setup.ps1 로 전달돼야 한다. Newline 은 스위치가 아니라 값이다.
    """
    import re

    source = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")
    param_block = source.split("Set-StrictMode", 1)[0]
    assert re.search(r"\[switch\]\s*\$Keybinds\b", param_block), (
        "install.ps1 param has no [switch]$Keybinds"
    )
    assert re.search(r"\[string\]\s*\$Newline\b", param_block), (
        "install.ps1 param has no [string]$Newline"
    )

    forward_line = re.search(r"foreach \(\$k in ([^)]+)\)", source)
    assert forward_line, "could not find the switch forwarding list in install.ps1"
    forwarded = set(re.findall(r"'(\w+)'", forward_line.group(1)))
    assert "Keybinds" in forwarded, (
        "install.ps1 does not put $Keybinds in the setup.ps1 forwarding list"
    )

    # 문자열 값은 스위치 foreach 로 못 넘긴다. BoundParameters 로 값을 실어야 한다.
    assert re.search(
        r"\$PSBoundParameters\.ContainsKey\(\s*['\"]Newline['\"]\s*\)",
        source,
    ) or re.search(r"\$fwd\[\s*['\"]Newline['\"]\s*\]\s*=", source), (
        "install.ps1 does not pass the -Newline value to setup.ps1"
    )


# ── 선택이 실제 설치로 이어지는가 ───────────────────────────────────────


@posix_only
def test_setup_sh_dry_run_follows_onboarding_choices(tmp_path):
    """온보딩에서 기본값 + Preview(dry-run) 를 고르면 미리보기만 나오고 아무것도 쓰지 않는다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()

    stub_bin = tmp_path / "stubbin"
    stub_bin.mkdir()
    trash = stub_bin / "trash-put"
    trash.write_text('#!/bin/sh\necho "[stub] $*"\n', encoding="utf-8")
    trash.chmod(0o755)

    env = clean_env(HOME=str(home), PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    code, screen = run_in_pty(
        ["bash", str(ROOT / "scripts" / "setup.sh")],
        keys=ACCEPT_DRY,
        cwd=project, env=env, timeout=120,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert "DRY RUN" in text, text
    assert "CodeGraph" in text, text
    assert "graft" not in text.lower(), text
    assert "Claude Code" in text and "Codex" in text, text
    # dry-run 이므로 실제 설정은 하나도 쓰이지 않는다.
    assert not (home / ".claude" / "settings.json").exists(), text
    # dry-run 이므로 AGENTS.md 도 생기지 않는다.
    assert not (project / "AGENTS.md").exists(), text


@posix_only
def test_onboarding_works_in_piped_setup_sh(tmp_path):
    """`curl … | sh` 의 실제 모양 — setup.sh 자체가 stdin 을 파이프로 받은 채 온보딩을 띄운다.

    install.sh 는 curl 파이프 안에서 setup.sh 를 부른다. 여기서 stdin 은 여전히 스크립트
    본문이므로, 온보딩이 /dev/tty 를 열지 못하면 이 경로 전체가 깨진다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()

    env = clean_env(HOME=str(home))
    code, screen = run_in_pty(
        ["bash", str(ROOT / "scripts" / "setup.sh")],
        keys=ACCEPT_DRY,
        cwd=project, env=env, stdin_pipe=True, timeout=120,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert "Set up this machine?" in text, text
    assert "DRY RUN" in text, text
    # dry-run 이므로 훅도 파일도 설치되지 않는다.
    assert not (home / ".claude" / "settings.json").exists(), text
    assert not (project / "AGENTS.md").exists(), text


@posix_only
def test_flags_skip_onboarding(tmp_path):
    """자동화/CI 가 쓰던 기존 호출은 온보딩 때문에 멈추면 안 된다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = clean_env(HOME=str(home))
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup.sh"), "--agentsmd", "--dry-run"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DRY RUN" in proc.stdout
    assert "What would you like to install?" not in proc.stdout


# ── 온보딩이 고른 값이 settings.json 까지 도달하는가 ──────────────────────


@posix_only
def test_default_mode_option_is_reflected_in_settings(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = clean_env(HOME=str(home))
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup_hooks.sh"), "--dry-run",
         "--default-mode", "bypassPermissions"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    # dry-run 은 병합 결과 전체를 찍지 않고 변경 계획만 보인다. 빈 홈이라 계획에 항상 나온다.
    assert "permissions.defaultMode: None -> 'bypassPermissions'" in proc.stdout, proc.stdout


@posix_only
def test_unknown_default_mode_is_rejected(tmp_path):
    """오타가 그대로 settings.json 에 박히면 사용자는 모드가 왜 안 켜지는지 알 길이 없다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = clean_env(HOME=str(home))
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup_hooks.sh"), "--dry-run",
         "--default-mode", "bypass"],   # 그럴듯한 오타
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=120,
    )
    assert proc.returncode != 0
    assert "Unknown defaultMode" in proc.stderr


def test_merge_prefers_default_mode_over_fragment(tmp_path):
    """조각(res/settings.json) 파일 자체는 건드리지 않고 값만 갈아끼워야 한다."""
    settings = tmp_path / "settings.json"
    manifest = tmp_path / "manifest.json"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "res" / "hooks" / "merge_and_diff.py"),
         "--default-mode", "bypassPermissions",
         str(ROOT / "res" / "settings.json"), str(settings), "0", "python3",
         str(tmp_path / "hooks"), str(manifest), "danger_guard.py"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(settings.read_text(encoding="utf-8"))
    assert written["permissions"]["defaultMode"] == "bypassPermissions"

    # 조각 원본은 그대로 auto 여야 한다 (SSoT 훼손 방지).
    fragment = json.loads((ROOT / "res" / "settings.json").read_text(encoding="utf-8"))
    assert fragment["permissions"]["defaultMode"] == "auto"


def test_merge_blocks_on_invalid_default_mode(tmp_path):
    settings = tmp_path / "settings.json"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "res" / "hooks" / "merge_and_diff.py"),
         "--default-mode", "nonsense",
         str(ROOT / "res" / "settings.json"), str(settings), "0", "python3",
         str(tmp_path / "hooks")],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode != 0
    assert not settings.exists()


# ── AGENTS.md 덮어쓰기 ──────────────────────────────────────────────


@posix_only
def test_force_backs_up_existing_agentsmd_then_overwrites(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("사용자가 손댄 내용\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup_agentsmd.sh"), "--force"],
        cwd=str(tmp_path), env=clean_env(), capture_output=True, text=True,
        encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert target.read_text(encoding="utf-8") != "사용자가 손댄 내용\n"

    backups = list(tmp_path.glob("AGENTS.md.bak.*"))
    assert len(backups) == 1, list(tmp_path.iterdir())
    assert backups[0].read_text(encoding="utf-8") == "사용자가 손댄 내용\n"


@posix_only
def test_without_force_existing_agentsmd_is_untouched(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("사용자가 손댄 내용\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup_agentsmd.sh")],
        cwd=str(tmp_path), env=clean_env(), capture_output=True, text=True,
        encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0
    assert target.read_text(encoding="utf-8") == "사용자가 손댄 내용\n"
    assert not list(tmp_path.glob("AGENTS.md.bak.*"))
