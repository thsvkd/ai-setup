"""res/onboard.py (대화형 온보딩) 와 그 선택이 설치에 반영되는 경로 테스트.

온보딩의 위험은 '안 뜨는 것'이 아니라 **묻지도 않고 뭔가를 골라버리는 것**이다. 실측해보면
questionary 는 stdin 이 파이프일 때(= curl | sh) 에러도 없이 첫 항목을 자동 확정한다. 그래서
여기서는 프롬프트가 뜨는 경우뿐 아니라, 띄울 수 없는 상황에서 **아무 선택도 하지 않는지**를
같은 비중으로 검증한다.

pty 를 쓰는 테스트는 실제 터미널 상호작용을 재현한다 — 느리지만, 이 기능에서 유일하게
의미 있는 검증이다. Windows 에서는 pty/POSIX 셸이 없어 건너뛴다.
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
ONBOARD = ROOT / "res" / "onboard.py"

DOWN = b"\x1b[B"
ENTER = b"\r"
CTRL_C = b"\x03"
SPACE = b" "        # 체크박스에서 항목 선택/해제

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NON_INTERACTIVE = 2
EXIT_CANCELLED = 130

posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="POSIX 전용 (pty / bash 필요)",
)


def clean_env(**extra):
    """CI 감지에 걸리지 않는 환경. 테스트 러너 자체가 CI 에서 도는 경우를 배제한다."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE")}
    env["TERM"] = "xterm-256color"
    env.update(extra)
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
            pytest.fail(f"프로세스가 끝나지 않았습니다. 화면:\n{bytes(out).decode(errors='replace')}")
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


def test_tty_없으면_아무것도_선택하지_않는다(tmp_path):
    """가장 중요한 계약. 여기서 뭔가를 골라버리면 사용자가 동의한 적 없는 설치가 일어난다."""
    out = tmp_path / "answers"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", env=clean_env(), timeout=60,
    )
    assert proc.returncode == EXIT_NON_INTERACTIVE
    assert read_answers(out) == {}


def test_ci_환경에서는_프롬프트를_띄우지_않는다(tmp_path):
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
def test_ci_환경변수는_tty가_있어도_프롬프트를_막는다(tmp_path):
    out = tmp_path / "answers"
    code, _ = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        keys=[], env=clean_env(CI="true"),
    )
    assert code == EXIT_NON_INTERACTIVE
    assert read_answers(out) == {}


# ── 실제 터미널 상호작용 ──────────────────────────────────────────────


@posix_only
def test_기본값_그대로_선택하면_전체설치_auto_적용(tmp_path):
    """covers: Test-1
    SCOPE=all 기본값: 권한 모드 다음·적용 여부 전에 줄바꿈 키를 묻고,
    Enter(기본 강조)는 Shift+Enter → NEWLINE_CHORD=shift-enter.
    질문 순서: 범위 → 권한 → 줄바꿈 키 → 하네스 → OMC → 출력 스타일 → mod → 적용.
    하네스 체크박스는 전부 체크된 상태로 뜨므로 Enter 만으로 전체가 선택된다.
    OMC·출력 스타일·mod 는 confirm 이라 Enter 가 기본값(아니오)이다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    text = screen.decode(errors="replace")
    assert code == EXIT_OK, text
    assert "Shift+Enter" in text and "Ctrl+Enter" in text, text
    assert read_answers(out) == {
        "SCOPE": "all",
        "DEFAULT_MODE": "auto",
        "OVERWRITE_AGENTSMD": "0",
        "DRY_RUN": "0",
        "NEWLINE_CHORD": "shift-enter",
        "HARNESSES": "claude,codex,grok,opencode",
        "OMC": "0",
        "OUTPUT_STYLE": "0",
        "MODS": "0",
    }


@posix_only
def test_curl_파이프_설치에서도_프롬프트가_동작한다(tmp_path):
    """`curl … | sh` 는 stdin 이 스크립트 본문이다. /dev/tty 를 열지 못하면 여기서 깨진다.

    questionary 는 이 상황에서 조용히 첫 항목을 확정해버리므로, '두 번째 항목이 제대로
    골라졌는지'까지 확인해야 진짜로 키 입력을 받은 것이다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, ENTER, DOWN, ENTER, ENTER, ENTER, ENTER, DOWN, ENTER],
        stdin_pipe=True,
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SCOPE"] == "hooks"
    assert answers["DEFAULT_MODE"] == "bypassPermissions"
    assert answers["DRY_RUN"] == "1"
    assert "NEWLINE_CHORD" not in answers


@posix_only
def test_bypass_선택시_경고를_보여준다(tmp_path):
    out = tmp_path / "answers"
    # 범위=전체, 권한=bypass, 줄바꿈=기본(Shift+Enter), 하네스=기본(전체), OMC=기본(아니오), 출력 스타일=기본(아니오), mod=기본(아니오), 적용=기본
    _, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER, DOWN, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    text = screen.decode(errors="replace")
    assert "권한 확인" in text and "생략" in text, text


@posix_only
def test_ctrl_c_취소는_비대화형_폴백과_구분된다(tmp_path):
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
def test_프롬프트가_깨지면_기본값_폴백이_아니라_중단한다(tmp_path):
    """렌더·입력 오류는 2(물을 수 없음)가 아니다. 사용자는 고르던 중이었으므로 1 로 멈춘다.

    첫 질문에 답한 뒤 두 번째 질문을 그리다 깨지는 tui 를 옆에 둔다.
    """
    shutil.copy(ONBOARD, tmp_path / "onboard.py")
    real_tui = (ROOT / "res" / "tui.py").read_text(encoding="utf-8")
    (tmp_path / "tui.py").write_text(
        real_tui + "\n\n_real_select = select\n_calls = []\n\n"
        "def select(*a, **k):\n"
        "    _calls.append(1)\n"
        "    if len(_calls) > 1:\n"
        "        raise RuntimeError('render broke')\n"
        "    return _real_select(*a, **k)\n",
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
    assert "아무것도 설치하지 않았습니다" in text, text
    assert read_answers(out) == {}


@posix_only
def test_콘솔을_준비하지_못하면_그리기_전이므로_기본값으로_진행한다(tmp_path):
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
    assert "무엇을 설치할까요" not in text, text
    assert read_answers(out) == {}


@posix_only
def test_stdin이_닫혀_있으면_물을_수_없음으로_끝난다(tmp_path):
    out = tmp_path / "answers"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out)],
        stdin=subprocess.DEVNULL, capture_output=True, env=clean_env(), timeout=60,
        preexec_fn=lambda: os.close(0),
    )
    assert proc.returncode == EXIT_NON_INTERACTIVE, proc.stderr
    assert read_answers(out) == {}


@posix_only
def test_기존_agentsmd가_있을때만_덮어쓰기를_묻는다(tmp_path):
    (tmp_path / "AGENTS.md").write_text("기존 프로젝트 규칙\n", encoding="utf-8")
    out = tmp_path / "answers"
    # 질문이 하나 늘어난다: 범위 → 권한 → 줄바꿈 키 → 하네스 → 덮어쓰기 → OMC → 출력 스타일 → mod → 적용
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert "덮어쓸까요" in screen.decode(errors="replace")
    # confirm 의 기본값은 '아니오' — 사용자 콘텐츠는 실수로 날아가면 안 된다.
    assert read_answers(out)["OVERWRITE_AGENTSMD"] == "0"
    assert read_answers(out)["NEWLINE_CHORD"] == "shift-enter"


@posix_only
def test_온보딩에서_CtrlEnter를_고르면_NEWLINE_CHORD는_ctrl_enter다(tmp_path):
    """covers: Test-1
    SCOPE=all 에서 줄바꿈 키 두 번째 항목(Ctrl+Enter)을 고르면 답 파일이 ctrl-enter 다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[ENTER, ENTER, DOWN, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SCOPE"] == "all"
    assert answers["NEWLINE_CHORD"] == "ctrl-enter"


@posix_only
def test_SCOPE_hooks이면_NEWLINE_CHORD를_묻지_않는다(tmp_path):
    """covers: Test-2
    SCOPE=hooks 이면 줄바꿈 키를 묻지 않고 답 파일에 NEWLINE_CHORD 가 없다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SCOPE"] == "hooks"
    assert "NEWLINE_CHORD" not in answers


@posix_only
def test_애플리케이션_커서_모드의_화살표도_받는다(tmp_path):
    """tmux·vim 이후의 셸 등은 화살표를 ESC [ B 가 아니라 ESC O B 로 보낸다.

    이를 놓치면 ↓ 가 무시되고 Enter 가 첫 항목(전체 설치)을 확정한다.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[b"\x1bOB", ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert read_answers(out)["SCOPE"] == "hooks"


@posix_only
def test_SCOPE_agentsmd이면_NEWLINE_CHORD를_묻지_않는다(tmp_path):
    """covers: Test-2
    SCOPE=agentsmd 이면 줄바꿈 키를 묻지 않고 답 파일에 NEWLINE_CHORD 가 없다.
    질문 순서: 범위 → 하네스 → 적용.
    """
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, DOWN, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SCOPE"] == "agentsmd"
    assert "NEWLINE_CHORD" not in answers
    assert answers["HARNESSES"] == "claude,codex,grok,opencode"


@posix_only
def test_하네스를_해제하면_고른_것만_기록된다(tmp_path):
    """체크박스는 전부 체크된 상태로 뜬다. Space 로 claude 를 해제하면 나머지만 남는다.

    이 경로가 깨지면 Codex 만 쓰는 사용자의 프로젝트에도 CLAUDE.md 가 생긴다.
    """
    out = tmp_path / "answers"
    # 범위=AGENTS.md만 → 하네스에서 첫 항목(claude) 을 Space 로 해제 → 확정 → 적용
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, DOWN, ENTER, SPACE, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["HARNESSES"] == "codex,grok,opencode"


@posix_only
def test_SCOPE_hooks이면_하네스를_묻지_않는다(tmp_path):
    """훅은 프로젝트 지침과 무관하다. 범위가 훅뿐이면 하네스 질문이 끼면 안 된다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, ENTER, ENTER, ENTER, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SCOPE"] == "hooks"
    assert "HARNESSES" not in answers


@posix_only
def test_OMC_설치를_고르면_OMC가_1로_기록된다(tmp_path):
    """범위=훅 → 권한=기본 → OMC 에서 y → 출력 스타일=기본 → mod=기본 → 적용. y 는 confirm 을 곧바로 확정한다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, ENTER, ENTER, b"y", ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["SCOPE"] == "hooks"
    assert answers["OMC"] == "1"


@posix_only
def test_출력_스타일을_고르면_OUTPUT_STYLE이_1로_기록된다(tmp_path):
    """범위=훅 → 권한=기본 → OMC=기본(아니오) → 출력 스타일에서 y → mod=기본 → 적용."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, ENTER, ENTER, ENTER, b"y", ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["OMC"] == "0"
    assert answers["OUTPUT_STYLE"] == "1"


@posix_only
def test_mod를_고르면_MODS가_1로_기록된다(tmp_path):
    """범위=훅 → 권한=기본 → OMC=기본 → 출력 스타일=기본 → mod 에서 y → 적용."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, ENTER, ENTER, ENTER, ENTER, b"y", ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    answers = read_answers(out)
    assert answers["OUTPUT_STYLE"] == "0"
    assert answers["MODS"] == "1"


@posix_only
def test_SCOPE_agentsmd이면_OMC를_묻지_않는다(tmp_path):
    """OMC 는 전역 설치다. 현재 폴더만 고른 사용자에게 전역 변경을 묻지 않는다."""
    out = tmp_path / "answers"
    code, screen = run_in_pty(
        [sys.executable, "-X", "utf8", str(ONBOARD), "--out", str(out),
         "--project-dir", str(tmp_path)],
        keys=[DOWN, DOWN, ENTER, ENTER, ENTER],
    )
    assert code == EXIT_OK, screen.decode(errors="replace")
    assert "OMC" not in read_answers(out)
    assert "OUTPUT_STYLE" not in read_answers(out)
    assert "MODS" not in read_answers(out)


# ── 렌더러 회귀 방지 ─────────────────────────────────────────────────


def test_렌더러가_콘솔_없이_프레임을_만든다():
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


def test_install_ps1이_받은_스위치를_전부_setup에_넘긴다():
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
    assert declared, "install.ps1 의 param 블록에서 스위치를 찾지 못했다"

    # setup.ps1 로 넘기는 목록: foreach ($k in 'A', 'B', ...)
    forward_line = re.search(r"foreach \(\$k in ([^)]+)\)", source)
    assert forward_line, "install.ps1 에서 스위치 전달 목록을 찾지 못했다"
    forwarded = set(re.findall(r"'(\w+)'", forward_line.group(1)))

    missing = declared - forwarded
    assert not missing, (
        f"install.ps1 이 받기만 하고 setup.ps1 에 넘기지 않는 스위치: {sorted(missing)} — "
        "사용자가 지정해도 조용히 무시된다"
    )


def test_install_ps1이_Keybinds와_Newline을_setup에_넘긴다():
    """covers: Test-17
    install.ps1 param 에 -Keybinds 스위치와 -Newline 문자열이 있고,
    둘 다 setup.ps1 로 전달돼야 한다. Newline 은 스위치가 아니라 값이다.
    """
    import re

    source = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")
    param_block = source.split("Set-StrictMode", 1)[0]
    assert re.search(r"\[switch\]\s*\$Keybinds\b", param_block), (
        "install.ps1 param 에 [switch]$Keybinds 가 없다"
    )
    assert re.search(r"\[string\]\s*\$Newline\b", param_block), (
        "install.ps1 param 에 [string]$Newline 가 없다"
    )

    forward_line = re.search(r"foreach \(\$k in ([^)]+)\)", source)
    assert forward_line, "install.ps1 에서 스위치 전달 목록을 찾지 못했다"
    forwarded = set(re.findall(r"'(\w+)'", forward_line.group(1)))
    assert "Keybinds" in forwarded, (
        "install.ps1 이 $Keybinds 를 setup.ps1 전달 목록에 넣지 않았다"
    )

    # 문자열 값은 스위치 foreach 로 못 넘긴다. BoundParameters 로 값을 실어야 한다.
    assert re.search(
        r"\$PSBoundParameters\.ContainsKey\(\s*['\"]Newline['\"]\s*\)",
        source,
    ) or re.search(r"\$fwd\[\s*['\"]Newline['\"]\s*\]\s*=", source), (
        "install.ps1 이 -Newline 값을 setup.ps1 로 넘기지 않는다"
    )


# ── 선택이 실제 설치로 이어지는가 ───────────────────────────────────────


@posix_only
def test_setup_sh가_온보딩_선택대로_dry_run을_수행한다(tmp_path):
    """온보딩에서 '훅만 + dry-run' 을 고르면 AGENTS.md 는 건드리지 않고 미리보기만 나와야 한다."""
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
    # 범위=훅만(↓), 권한=auto(기본), OMC=아니오(기본), 출력 스타일=아니오(기본), mod=아니오(기본), 적용=dry-run 먼저(↓).
    # SCOPE=hooks 이므로 줄바꿈 키 질문은 끼지 않는다 (covers: Test-2).
    code, screen = run_in_pty(
        ["bash", str(ROOT / "scripts" / "setup.sh")],
        keys=[DOWN, ENTER, ENTER, ENTER, ENTER, ENTER, DOWN, ENTER],
        cwd=project, env=env, timeout=90,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert "DRY RUN" in text, text
    # dry-run 이므로 실제 설정은 하나도 쓰이지 않는다.
    assert not (home / ".claude" / "settings.json").exists(), text
    # 범위가 '훅만' 이므로 AGENTS.md 도 설치되지 않는다.
    assert not (project / "AGENTS.md").exists(), text


@posix_only
def test_파이프로_실행된_setup_sh에서도_온보딩이_동작한다(tmp_path):
    """`curl … | sh` 의 실제 모양 — setup.sh 자체가 stdin 을 파이프로 받은 채 온보딩을 띄운다.

    install.sh 는 curl 파이프 안에서 setup.sh 를 부른다. 여기서 stdin 은 여전히 스크립트
    본문이므로, 온보딩이 /dev/tty 를 열지 못하면 이 경로 전체가 깨진다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()

    env = clean_env(HOME=str(home))
    # 범위=AGENTS.md만(↓↓), 하네스=전부(Enter), 적용=dry-run 먼저(↓) — 권한 모드는 묻지 않는 범위다.
    code, screen = run_in_pty(
        ["bash", str(ROOT / "scripts" / "setup.sh")],
        keys=[DOWN, DOWN, ENTER, ENTER, DOWN, ENTER],
        cwd=project, env=env, stdin_pipe=True, timeout=90,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert "무엇을 설치할까요" in text, text
    assert "DRY RUN" in text, text
    # AGENTS.md 만 고르고 dry-run 이므로 훅도 파일도 설치되지 않는다.
    assert not (home / ".claude" / "settings.json").exists(), text
    assert not (project / "AGENTS.md").exists(), text


@posix_only
def test_플래그를_주면_온보딩을_건너뛴다(tmp_path):
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
    assert "무엇을 설치할까요" not in proc.stdout


# ── 온보딩이 고른 값이 settings.json 까지 도달하는가 ──────────────────────


@posix_only
def test_default_mode_옵션이_settings에_반영된다(tmp_path):
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
def test_알수없는_default_mode는_거부된다(tmp_path):
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
    assert "알 수 없는 defaultMode" in proc.stderr


def test_merge가_default_mode를_조각보다_우선한다(tmp_path):
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


def test_merge의_잘못된_default_mode는_병합을_막는다(tmp_path):
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
def test_force는_기존_agentsmd를_백업한_뒤_덮어쓴다(tmp_path):
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
def test_force가_없으면_기존_agentsmd를_건드리지_않는다(tmp_path):
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
