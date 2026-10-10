"""clack 스타일 인라인 프롬프트 — 표준 라이브러리만 쓴다.

`npx skills` 등이 쓰는 @clack/prompts 의 화면 관용구를 그대로 따른다:

    ┌  제목
    │
    ◇  답한 질문          ← 답하면 한 줄로 접힌다
    │  고른 답
    │
    ◆  지금 묻는 질문
    │  ● 강조된 항목 (설명)
    │  ○ 다른 항목
    └

의존성을 두지 않는 이유: 예전에 벤더링한 prompt_toolkit 3.0.53 은 Python 3.10+ 문법을 써서
macOS 기본 python3(3.9)에서 import 단계에 죽었고, 온보딩은 아무 말 없이 건너뛰어졌다.
필요한 것은 select·multiselect·confirm 세 가지뿐이라 직접 그리는 쪽이 싸다.

입력: POSIX 는 fd 0 을 termios 로 cbreak(+ISIG 끔) 상태로 읽는다. 호출부가 이미 /dev/tty 를
fd 0 에 얹어 둔다. Windows 는 msvcrt.getwch 가 stdin 과 무관하게 콘솔을 직접 읽는다.

각 프롬프트는 값을 반환하고, 사용자가 Ctrl+C 로 취소하면 None 을 반환한다. 단독 Esc 는 무시한다.
"""

import os
import shutil
import sys
import unicodedata

_WIN = os.name == "nt"


def _unicode_ok():
    # is-unicode-supported (clack 이 쓰는 판정) 과 같은 규칙.
    if not _WIN:
        return os.environ.get("TERM") != "linux"
    env = os.environ
    return bool(
        env.get("WT_SESSION")
        or env.get("TERMINUS_SUBLIME")
        or env.get("ConEmuTask") == "{cmd::Cmder}"
        or env.get("TERM_PROGRAM") in ("Terminus-Sublime", "vscode")
        or env.get("TERM") in ("xterm-256color", "alacritty", "rxvt-unicode", "rxvt-unicode-256color")
        or env.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"
    )


if _unicode_ok():
    BAR, BAR_START, BAR_END = "│", "┌", "└"
    STEP_ACTIVE, STEP_SUBMIT, STEP_CANCEL, STEP_WARN = "◆", "◇", "■", "▲"
    RADIO_ON, RADIO_OFF = "●", "○"
    CHECK_ON, CHECK_OFF = "◼", "◻"
else:
    BAR, BAR_START, BAR_END = "|", "T", "-"
    STEP_ACTIVE, STEP_SUBMIT, STEP_CANCEL, STEP_WARN = "*", "o", "x", "!"
    RADIO_ON, RADIO_OFF = ">", " "
    CHECK_ON, CHECK_OFF = "[+]", "[ ]"

_COLOR = not os.environ.get("NO_COLOR")
_SGR = {"dim": "2", "bold": "1", "cyan": "36", "green": "32", "yellow": "33", "red": "31",
        "gray": "90", "strike": "9"}


def _paint(style, text):
    if not _COLOR or not style:
        return text
    codes = ";".join(_SGR[s] for s in style.split())
    return "\x1b[%sm%s\x1b[0m" % (codes, text)


def char_width(ch):
    if unicodedata.combining(ch) or ch in "​‍️":
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _layout_width(ch):
    # 줄을 감쌀 때는 모호 폭(│ ◆ ● · — 등)을 2칸으로 넉넉히 센다. CJK 터미널은 이들을 2칸으로
    # 그리기도 하는데, 실제보다 넓게 그려지면 터미널이 따로 접어 다시 그릴 줄 수가 틀어진다.
    if unicodedata.east_asian_width(ch) == "A":
        return 2
    return char_width(ch)


def width(segments):
    return sum(char_width(ch) for _, text in segments for ch in text)


def wrap(segments, cols):
    """(style, text) 조각들을 cols 칸 이하의 화면 행들로 나눈다. 이어지는 행은 거터로 시작한다.

    터미널에게 접게 맡기면 다시 그릴 때 올라갈 행 수를 정확히 알 수 없다(넓은 글자가 끝 칸에
    걸릴 때의 빈칸, conhost 의 즉시 줄바꿈). 그래서 행을 직접 나누고 그 개수만 센다.
    """
    prefix = ("gray", BAR + "  ")
    rows, row, used = [], [], 0
    for style, text in segments:
        chunk = []
        for ch in text:
            w = _layout_width(ch)
            if used + w > cols and used > 0:
                if chunk:
                    row.append((style, "".join(chunk)))
                rows.append(row)
                row, chunk, used = [prefix], [], sum(_layout_width(c) for c in prefix[1])
            chunk.append(ch)
            used += w
        if chunk:
            row.append((style, "".join(chunk)))
    rows.append(row)
    return rows


def paint(segments):
    return "".join(_paint(style, text) for style, text in segments)


# ── 터미널 입출력 ───────────────────────────────────────────────────

_console_ready = False


def prepare_console():
    """Windows 콘솔에서 ANSI 이스케이프를 켠다. 프로세스당 한 번, 종료할 때 되돌린다.

    프롬프트 사이에 찍는 intro·warn·outro 도 색을 쓰므로 프롬프트마다 켰다 끄면 안 된다.
    켤 수 없으면(Windows 10 1511 이전) 이스케이프가 그대로 찍히므로 예외를 올려 대화형을 포기한다.
    """
    global _console_ready
    if _console_ready or not _WIN:
        _console_ready = True
        return
    import atexit
    import ctypes

    k32 = ctypes.windll.kernel32
    handle = k32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
        raise OSError("not a console")
    if not k32.SetConsoleMode(handle, mode.value | 0x0004):
        raise OSError("VT processing unavailable")
    old_cp = k32.GetConsoleOutputCP()
    # stdout 이 CONOUT$ 를 dup 한 일반 파일이면(setup.ps1 은 stdout 을 캡처한다) UTF-8 바이트가
    # 그대로 나간다. 콘솔 코드 페이지가 949 면 한글이 깨지므로 그동안만 UTF-8 로 둔다.
    k32.SetConsoleOutputCP(65001)
    atexit.register(k32.SetConsoleOutputCP, old_cp)
    atexit.register(k32.SetConsoleMode, handle, mode.value)
    _console_ready = True


def _columns():
    """줄을 감쌀 폭. 마지막 칸은 비워 둔다(conhost 는 끝 칸을 채우면 바로 줄을 넘긴다)."""
    cols = shutil.get_terminal_size().columns
    # 크기 정보가 없는 pty 는 0 을 돌려준다. Python 3.10 이하의 shutil 은 이때 기본값으로 바꾸지 않는다.
    if cols <= 0:
        cols = 80
    return max(20, cols - 1)


def _emit(lines):
    """프롬프트 밖에서 줄들을 찍는다. 감싼 화면 행 수를 반환한다."""
    prepare_console()
    cols = _columns()
    rows = [row for segs in lines for row in wrap(segs, cols)]
    sys.stdout.write("\r\n".join(paint(r) for r in rows))
    sys.stdout.flush()
    return len(rows)


class _Terminal:
    """프롬프트 하나가 떠 있는 동안 키 입력 모드를 바꾸고, 어떤 경로로 나가든 되돌린다."""

    def __enter__(self):
        prepare_console()
        self._saved = None
        self._signals = {}
        if not _WIN:
            import signal
            import termios

            self._saved = termios.tcgetattr(0)
            mode = termios.tcgetattr(0)
            # ISIG 를 꺼서 Ctrl+C 를 시그널이 아니라 키로 받는다 — 취소 처리를 한 곳에 모은다.
            mode[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG)
            mode[6][termios.VMIN] = 1
            mode[6][termios.VTIME] = 0
            termios.tcsetattr(0, termios.TCSANOW, mode)

            # 종료 시그널에도 __exit__ 를 거치게 해, 에코가 꺼진 터미널을 남기지 않는다.
            def interrupt(*_):
                raise KeyboardInterrupt

            for sig in (signal.SIGTERM, signal.SIGHUP):
                self._signals[sig] = signal.signal(sig, interrupt)
        self.write("\x1b[?25l")
        self.lines = 0
        return self

    def __exit__(self, *exc):
        try:
            self.write("\x1b[?25h")
        except OSError:
            pass
        if self._saved is not None:
            import signal
            import termios

            for sig, old in self._signals.items():
                signal.signal(sig, old)
            # 터미널이 끊긴 뒤면 복원도 실패한다(termios.error). 그 예외가 취소를 덮으면 안 된다.
            try:
                termios.tcsetattr(0, termios.TCSANOW, self._saved)
            except Exception:
                pass
        return False

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def draw(self, lines):
        """직전 프레임을 지우고 lines 를 그린다. 커서는 마지막 행 끝에 남는다."""
        cols = _columns()
        rows = [row for segs in lines for row in wrap(segs, cols)]
        buf = "\r"
        if self.lines > 1:
            buf += "\x1b[%dA" % (self.lines - 1)
        buf += "\x1b[J" + "\r\n".join(paint(r) for r in rows)
        self.write(buf)
        self.lines = len(rows)

    def key(self):
        """'up' 'down' 'left' 'right' 'enter' 'space' 'cancel' 또는 글자 하나."""
        if _WIN:
            import msvcrt

            try:
                ch = msvcrt.getwch()
            except KeyboardInterrupt:
                return "cancel"
            if ch in ("\x00", "\xe0"):
                return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch(), "")
        else:
            ch = self._read_posix()
        return {"\r": "enter", "\n": "enter", " ": "space", "\x03": "cancel", "\x04": "cancel",
                "k": "up", "j": "down", "h": "left", "l": "right",
                # 한글 자판 상태에서 y / n 을 누르면 ㅛ / ㅜ 가 들어온다.
                "ㅛ": "y", "ㅜ": "n"}.get(ch, ch)

    @staticmethod
    def _read_posix():
        import select

        def more(timeout):
            if not select.select([0], [], [], timeout)[0]:
                return ""
            return os.read(0, 1).decode("latin-1")

        try:
            first = os.read(0, 1)
        except OSError:
            return "\x04"
        if not first:
            return "\x04"           # 터미널이 끊겼다(EOF). 계속 읽으면 빈 문자열로 헛돈다.
        lead = first[0]
        if lead >= 0xC0:            # UTF-8 다바이트 글자 (한글 자판의 ㅛ / ㅜ 등)
            extra = 1 if lead < 0xE0 else 2 if lead < 0xF0 else 3
            try:
                first += os.read(0, extra)
            except OSError:
                pass
            return first.decode("utf-8", "replace")
        ch = first.decode("latin-1")
        if ch != "\x1b":
            return ch
        # 화살표는 ESC [ B (일반) 또는 ESC O B (애플리케이션 커서 모드) 로 온다. SSH 처럼 바이트가
        # 나뉘어 도착할 수 있어 첫 바이트는 넉넉히 기다린다. 단독 ESC 는 아무 일도 하지 않는다 —
        # 느린 화살표 하나가 설치 전체를 취소하면 안 된다.
        intro = more(0.15)
        if intro == "O":
            final = more(0.15)
        elif intro == "[":
            final = more(0.15)
            while final and not ("\x40" <= final <= "\x7e"):
                final = more(0.15)
        else:
            return ""
        return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(final, "")


def _run(render, handle):
    """render(state) -> lines, handle(key) -> 'submit' | 'cancel' | None 로 프롬프트를 돌린다."""
    with _Terminal() as term:
        term.draw(render("active"))
        while True:
            outcome = handle(term.key())
            if outcome is None:
                term.draw(render("active"))
                continue
            term.draw(render(outcome))
            term.write("\r\n")
            return outcome


def _header(state, message):
    sym = {"active": (STEP_ACTIVE, "cyan"), "submit": (STEP_SUBMIT, "green"),
           "cancel": (STEP_CANCEL, "red"), "error": (STEP_WARN, "yellow")}[state]
    return [[("gray", BAR)], [(sym[1], sym[0]), ("", "  " + message)]]


def _done(state, message, answer):
    lines = _header(state, message)
    if state == "cancel":
        lines.append([("gray", BAR + "  "), ("dim strike", answer)])
    else:
        lines.append([("gray", BAR + "  "), ("dim", answer)])
    return lines


# ── 공개 API ──────────────────────────────────────────────────────


def intro(title):
    sys.stdout.write("\r\n")
    _emit([[("gray", BAR_START), ("", "  "), ("bold", title)]])
    sys.stdout.write("\r\n")


def outro(message):
    _emit([[("gray", BAR)], [("gray", BAR_END), ("", "  " + message)]])
    sys.stdout.write("\r\n\r\n")


def cancel(message):
    _emit([[("gray", BAR_END), ("red", "  " + message)]])
    sys.stdout.write("\r\n\r\n")


def warn(lines):
    """선택 사이에 끼는 경고. clack 의 log.warn 과 같은 모양."""
    out = [[("gray", BAR)], [("yellow", STEP_WARN), ("", "  " + lines[0])]]
    out += [[("gray", BAR), ("", "  " + line)] for line in lines[1:]]
    _emit(out)
    sys.stdout.write("\r\n")


def select_lines(state, message, options, cursor):
    """select 프레임. options 는 (value, label, hint) 목록이다. 테스트가 직접 부른다."""
    if state != "active":
        return _done(state, message, options[cursor][1])
    lines = _header(state, message)
    for i, (_, label, hint) in enumerate(options):
        if i == cursor:
            row = [("cyan", BAR + "  "), ("green", RADIO_ON), ("", " " + label)]
            if hint:
                row.append(("dim", " (%s)" % hint))
        else:
            row = [("cyan", BAR + "  "), ("dim", RADIO_OFF + " " + label)]
        lines.append(row)
    lines.append([("cyan", BAR_END), ("dim", "  ↑↓ 이동 · Enter 선택")])
    return lines


def select(message, options, initial=0):
    pos = [initial]

    def handle(key):
        if key == "up":
            pos[0] = (pos[0] - 1) % len(options)
        elif key == "down":
            pos[0] = (pos[0] + 1) % len(options)
        elif key in ("enter", "cancel"):
            return "submit" if key == "enter" else "cancel"
        return None

    outcome = _run(lambda st: select_lines(st, message, options, pos[0]), handle)
    return options[pos[0]][0] if outcome == "submit" else None


def multiselect(message, options, initial_values=(), required=True):
    pos = [0]
    picked = set(initial_values)
    error = [""]

    def render(state):
        if state != "active":
            chosen = [label for value, label, _ in options if value in picked]
            return _done(state, message, ", ".join(chosen) or "(없음)")
        bar = "yellow" if error[0] else "cyan"
        lines = _header("error" if error[0] else "active", message)
        for i, (value, label, hint) in enumerate(options):
            box = CHECK_ON if value in picked else CHECK_OFF
            box_style = "green" if value in picked else "dim"
            row = [(bar, BAR + "  "), (box_style, box)]
            row.append(("" if i == pos[0] else "dim", " " + label))
            if hint and i == pos[0]:
                row.append(("dim", " (%s)" % hint))
            lines.append(row)
        if error[0]:
            lines.append([("yellow", BAR_END + "  " + error[0])])
        else:
            lines.append([(bar, BAR_END), ("dim", "  ↑↓ 이동 · Space 선택/해제 · a 전체 · Enter 확정")])
        return lines

    def handle(key):
        error[0] = ""
        if key == "up":
            pos[0] = (pos[0] - 1) % len(options)
        elif key == "down":
            pos[0] = (pos[0] + 1) % len(options)
        elif key == "space":
            picked.symmetric_difference_update({options[pos[0]][0]})
        elif key == "a":
            everything = {o[0] for o in options}
            if picked == everything:
                picked.clear()
            else:
                picked.update(everything)
        elif key == "cancel":
            return "cancel"
        elif key == "enter":
            if required and not picked:
                error[0] = "최소 하나는 선택해야 합니다."
                return None
            return "submit"
        return None

    outcome = _run(render, handle)
    if outcome != "submit":
        return None
    return [value for value, _, _ in options if value in picked]


def confirm(message, default=False):
    """좌우 화살표로 고르고 Enter 로 확정한다. y / n 은 곧바로 확정한다."""
    yes = [default]

    def render(state):
        if state != "active":
            return _done(state, message, "예" if yes[0] else "아니오")
        on = [("green", RADIO_ON), ("", " 예")] if yes[0] else [("dim", RADIO_OFF + " 예")]
        off = [("dim", RADIO_OFF + " 아니오")] if yes[0] else [("green", RADIO_ON), ("", " 아니오")]
        lines = _header(state, message)
        lines.append([("cyan", BAR + "  ")] + on + [("dim", " / ")] + off)
        lines.append([("cyan", BAR_END), ("dim", "  ←→ 이동 · y/n · Enter 확정")])
        return lines

    def handle(key):
        if key in ("left", "right", "up", "down"):
            yes[0] = not yes[0]
        elif key in ("y", "Y"):
            yes[0] = True
            return "submit"
        elif key in ("n", "N"):
            yes[0] = False
            return "submit"
        elif key in ("enter", "cancel"):
            return "submit" if key == "enter" else "cancel"
        return None

    outcome = _run(render, handle)
    return yes[0] if outcome == "submit" else None
