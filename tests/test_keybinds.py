"""줄바꿈 키바인딩 설치 계약 (Test-1..Test-27 중 CLI·파일 쪽).

이 모듈은 구현이 아니라 **공개 계약**을 고정한다. setup.sh / setup.ps1 에
`--keybinds`/`-Keybinds`, `--newline`/`-Newline` 이 아직 없으면 RED 가 맞다.

구현자가 존중해야 하는 경로 주입 환경 변수:

- ``CLAUDE_SETUP_VSCODE_KEYBINDINGS`` — VS Code keybindings.json
- ``CLAUDE_SETUP_CURSOR_KEYBINDINGS`` — Cursor keybindings.json
- ``CLAUDE_SETUP_WT_SETTINGS`` — Windows Terminal settings.json
  (비우거나 대상 파일이 없으면 WT skip, Test-27)
- ``CLAUDE_SETUP_DETECTED_TERMINAL`` — 감지된 터미널 이름 (예: gnome-terminal, Test-24)

매니페스트 필드: ``~/.claude/.claude-code-setup.json`` 의
``keybinds.newline_chord`` = ``shift-enter`` | ``ctrl-enter``.

HOME/USERPROFILE/APPDATA/LOCALAPPDATA 를 샌드박스로 돌린다. 실제 사용자
프로필·SSH·TUI·실제 Windows Terminal 창은 쓰지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import test_onboard as onboard_tests  # noqa: E402

SETUP_SH = ROOT / "scripts" / "setup.sh"
SETUP_PS1 = ROOT / "scripts" / "setup.ps1"

# 줄바꿈 시퀀스 SSoT 후보. 구현은 이 셋 중 하나를 고른다. 단독 \\n 과 Ctrl 변종 CSI 는 금지.
SSOT_SEQUENCES = (
    "\u001b[13;2u",
    "\u001b\r",
    "\u001b[27;2;13~",
)
SSOT_ESCAPED = (
    r"\u001b[13;2u",
    r"\u001b\r",
    r"\u001b[27;2;13~",
    r"\x1b[13;2u",
    r"\x1b\r",
    r"\x1b[27;2;13~",
)

AGENT_FILE_NAMES = (
    "claude", "claude.exe", "claude.cmd", "claude.bat", "claude.ps1",
    "codex", "codex.exe", "codex.cmd", "codex.bat", "codex.ps1",
    "grok", "grok.exe", "grok.cmd", "grok.bat", "grok.ps1",
)

FOREIGN_VSCODE_KEY = "ctrl+alt+f9"
FOREIGN_VSCODE_COMMAND = "workbench.action.terminal.clear"
FOREIGN_CURSOR_COMMAND = "aichat.newchataction"
EDITOR_SHIFT_ENTER_COMMAND = "editor.action.insertLineAfter"
NOTEBOOK_SHIFT_ENTER_COMMAND = "notebook.cell.executeAndFocusContainer"
CLAUDE_PRESERVE_COMMAND = "chat:compact"
CLAUDE_PRESERVE_KEY = "ctrl+g"
CODEX_SENTINEL_MODEL = "sentinel-model"
TMUX_SENTINEL = "# user-sentinel-tmux"
GROK_SENTINEL = 'sentinel_multiline_key = "keep-me"'
WT_FOREIGN_KEYS = "ctrl+shift+c"
# 사용자가 수정 Enter 에 직접 걸어둔 sendInput. 우리 SSoT 시퀀스가 아니므로 살아남아야 한다.
WT_FOREIGN_SENDINPUT = "user-owned-payload"

posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="POSIX 전용 (pty / bash 필요)",
)
tmux_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="tmux.conf 는 POSIX 설치 대상",
)


def _powershell_exe():
    return shutil.which("pwsh") or shutil.which("powershell")


def posix_available():
    return sys.platform != "win32" and shutil.which("bash") is not None


def powershell_available():
    return _powershell_exe() is not None


def native_worker():
    if sys.platform == "win32":
        if not powershell_available():
            pytest.skip("PowerShell 필요")
        return "powershell"
    if not posix_available():
        pytest.skip("POSIX bash 필요")
    return "posix"


def skip_if_worker_missing(worker):
    if worker == "posix" and not posix_available():
        pytest.skip("POSIX bash 필요")
    if worker == "powershell" and not powershell_available():
        pytest.skip("PowerShell 필요")


# ── JSONC / 시퀀스 / 키 표기 ──────────────────────────────────────────


def parse_jsonc(text: str):
    """VS Code/Cursor keybindings.json 은 // 와 /* */ 주석을 허용한다."""
    if text.startswith("\ufeff"):
        text = text[1:]
    out = []
    i = 0
    n = len(text)
    in_str = False
    escape = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            continue
        out.append(ch)
        i += 1
    stripped = "".join(out).strip()
    if not stripped:
        return []
    return json.loads(stripped)


def load_keybindings(path: Path):
    assert path.exists(), f"키바인딩 파일이 없다: {path}"
    data = parse_jsonc(path.read_text(encoding="utf-8"))
    assert isinstance(data, list), f"keybindings.json 최상위는 배열이어야 한다: {path}"
    return data


def vscode_key(chord: str) -> str:
    return "shift+enter" if chord == "shift-enter" else "ctrl+enter"


def vscode_other_key(chord: str) -> str:
    return "ctrl+enter" if chord == "shift-enter" else "shift+enter"


def codex_key(chord: str) -> str:
    return chord  # shift-enter / ctrl-enter


def normalize_seq(text) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if text in SSOT_SEQUENCES or text in SSOT_ESCAPED:
        return text
    try:
        decoded = text.encode("utf-8").decode("unicode_escape")
    except Exception:
        decoded = text
    return decoded


def is_allowed_sequence(text: str) -> bool:
    raw = text if isinstance(text, str) else str(text)
    if raw in SSOT_SEQUENCES or raw in SSOT_ESCAPED:
        return True
    return normalize_seq(raw) in SSOT_SEQUENCES


def is_forbidden_sequence(text: str) -> bool:
    raw = text if isinstance(text, str) else str(text)
    if raw in ("\n", "\\n", "\r\n"):
        return True
    if normalize_seq(raw) in ("\n", "\r\n"):
        return True
    if "13;5u" in raw or "13;5~" in raw:
        return True
    return False


def sendsequence_text(entry: dict) -> str:
    args = entry.get("args") or {}
    if isinstance(args, dict):
        return args.get("text") or args.get("sequence") or ""
    return ""


def is_managed_sendsequence(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("command") != "workbench.action.terminal.sendSequence":
        return False
    when = str(entry.get("when") or "")
    if "terminalFocus" not in when:
        return False
    if re.search(r"editor|notebook", when, re.I):
        return False
    seq = sendsequence_text(entry)
    if not is_allowed_sequence(seq) or is_forbidden_sequence(seq):
        return False
    return True


def managed_sendsequences(entries):
    return [e for e in entries if is_managed_sendsequence(e)]


def norm_key(value) -> str:
    return str(value or "").lower().replace(" ", "")


# ── 픽스처 본문 ──────────────────────────────────────────────────────


DEFAULT_VSCODE_JSONC = """\
// Place your key bindings in this file to override the defaults
[
    {
        "key": "%s",
        "command": "%s",
        "when": "terminalFocus"
    },
    {
        "key": "shift+enter",
        "command": "%s",
        "when": "editorTextFocus && !editorReadonly"
    },
    {
        "key": "shift+enter",
        "command": "%s",
        "when": "notebookEditorFocused && !inputFocus"
    },
    {
        "key": "ctrl+alt+k",
        "command": "workbench.action.terminal.sendSequence",
        "args": {"text": "keep-me"},
        "when": "terminalFocus"
    }
]
""" % (FOREIGN_VSCODE_KEY, FOREIGN_VSCODE_COMMAND,
       EDITOR_SHIFT_ENTER_COMMAND, NOTEBOOK_SHIFT_ENTER_COMMAND)

DEFAULT_CURSOR_JSONC = """\
// Cursor user keybindings
[
    {
        "key": "%s",
        "command": "%s",
        "when": "terminalFocus"
    },
    {
        "key": "ctrl+shift+u",
        "command": "%s",
        "when": "editorTextFocus"
    },
    {
        "key": "shift+enter",
        "command": "%s",
        "when": "editorTextFocus && !editorReadonly"
    },
    {
        "key": "shift+enter",
        "command": "%s",
        "when": "notebookEditorFocused && !inputFocus"
    },
    {
        "key": "ctrl+alt+k",
        "command": "workbench.action.terminal.sendSequence",
        "args": {"text": "keep-me"},
        "when": "terminalFocus"
    }
]
""" % (FOREIGN_VSCODE_KEY, FOREIGN_VSCODE_COMMAND, FOREIGN_CURSOR_COMMAND,
       EDITOR_SHIFT_ENTER_COMMAND, NOTEBOOK_SHIFT_ENTER_COMMAND)

DEFAULT_CLAUDE_KEYBINDINGS = {
    "User": {"f9": "app:toggleHelp"},
    "Chat": {
        CLAUDE_PRESERVE_KEY: CLAUDE_PRESERVE_COMMAND,
        "escape": "chat:cancel",
    },
}

DEFAULT_CODEX_TOML = """\
model = "%s"

[mcp]
enabled = true

[tui.keymap.editor]
insert_newline = ["ctrl-j"]
indent = ["tab"]

[projects.sentinel]
trust = true
""" % CODEX_SENTINEL_MODEL

DEFAULT_GROK_TOML = """\
# grok user config
multiline = false
%s

[ui]
multiline = false
""" % GROK_SENTINEL

DEFAULT_TMUX = """\
%s
set -g mouse on
""" % TMUX_SENTINEL

DEFAULT_WT_SETTINGS = """\
{
    "actions": [
        {
            "command": "copy",
            "keys": "%s"
        },
        {
            "command": { "action": "sendInput", "input": "%s" },
            "keys": "ctrl+enter"
        }
    ],
    "profiles": {
        "defaults": {},
        "list": []
    }
}
""" % (WT_FOREIGN_KEYS, WT_FOREIGN_SENDINPUT)


def _dir_has_agent(path: Path) -> bool:
    try:
        return any((path / name).exists() for name in AGENT_FILE_NAMES)
    except OSError:
        return False


def isolated_path(stub: Path) -> str:
    """claude/codex/grok 가 잡히지 않는 PATH. 셸·파이썬만 남긴다."""
    keep = [str(stub.resolve())]
    seen = set(keep)
    needed = ["bash", "pwsh", "powershell", "python", "python3", "py"]
    # 시스템 디렉터리라도 claude/codex/grok 이 거기 설치돼 있으면 PATH 에 넣으면 안 된다.
    # 그러면 "에이전트가 없는 환경" 을 전제한 skip 테스트가 그 머신에서만 깨진다 (범용 테스트).
    def _keep_if_clean(d: str):
        if not d or d in seen:
            return
        if _dir_has_agent(Path(d)):
            return
        keep.append(d)
        seen.add(d)

    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        _keep_if_clean(str(Path(windir) / "System32"))
        _keep_if_clean(windir)
    else:
        for d in ("/usr/bin", "/bin"):
            _keep_if_clean(d)

    for exe in needed:
        found = shutil.which(exe)
        if not found:
            continue
        parent = Path(found).resolve().parent
        if _dir_has_agent(parent):
            dest = stub / Path(found).name
            if not dest.exists():
                try:
                    os.symlink(found, dest)
                except OSError:
                    shutil.copy2(found, dest)
        else:
            s = str(parent)
            if s not in seen:
                keep.append(s)
                seen.add(s)
    return os.pathsep.join(keep)


def write_stub_agent(stub: Path, name: str):
    if sys.platform == "win32":
        p = stub / f"{name}.cmd"
        p.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        p = stub / name
        p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        p.chmod(0o755)
    return p


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def kb_sandbox(tmp_path):
    """격리 HOME + APPDATA/LOCALAPPDATA + 키바인드 픽스처."""
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    localappdata = tmp_path / "localappdata"
    project = tmp_path / "project"
    stub = tmp_path / "stubbin"
    home.mkdir()
    appdata.mkdir()
    localappdata.mkdir()
    project.mkdir()
    stub.mkdir()

    (home / ".claude").mkdir()
    (home / ".codex").mkdir()
    (home / ".grok").mkdir()

    win_vscode = appdata / "Code" / "User" / "keybindings.json"
    win_cursor = appdata / "Cursor" / "User" / "keybindings.json"
    posix_vscode = home / ".config" / "Code" / "User" / "keybindings.json"
    posix_cursor = home / ".config" / "Cursor" / "User" / "keybindings.json"
    wt = (localappdata / "Packages" / "Microsoft.WindowsTerminal_8wekyb3d8bbwe"
          / "LocalState" / "settings.json")

    if sys.platform == "win32":
        vscode, cursor = win_vscode, win_cursor
    else:
        vscode, cursor = posix_vscode, posix_cursor

    for path in (win_vscode, posix_vscode):
        _write(path, DEFAULT_VSCODE_JSONC)
    for path in (win_cursor, posix_cursor):
        _write(path, DEFAULT_CURSOR_JSONC)
    _write(wt, DEFAULT_WT_SETTINGS)

    _write(home / ".claude" / "keybindings.json",
           json.dumps(DEFAULT_CLAUDE_KEYBINDINGS, indent=2) + "\n")
    _write(home / ".codex" / "config.toml", DEFAULT_CODEX_TOML)
    _write(home / ".grok" / "config.toml", DEFAULT_GROK_TOML)
    _write(home / ".tmux.conf", DEFAULT_TMUX)

    trash = stub / "trash-put"
    trash.write_text('#!/bin/sh\necho "[stub trash-put] $*"\n', encoding="utf-8")
    try:
        trash.chmod(0o755)
    except OSError:
        pass

    return SimpleNamespace(
        root=tmp_path,
        home=home,
        appdata=appdata,
        localappdata=localappdata,
        project=project,
        stub=stub,
        vscode=vscode,
        cursor=cursor,
        wt=wt,
        win_vscode=win_vscode,
        win_cursor=win_cursor,
        posix_vscode=posix_vscode,
        posix_cursor=posix_cursor,
    )


def sandbox_env(sb, extra=None, include_wt=True):
    # 개발자가 실제로 gnome-terminal/konsole 안에서 테스트를 돌리면 그 변수가 상속돼
    # 불가 터미널 경고가 항상 뜬다 — 주입 테스트가 상속값 덕에 통과하고, 대조군은 깨진다.
    drop = ("CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE",
            "CLAUDE_SETUP_DETECTED_TERMINAL",
            "GNOME_TERMINAL_SERVICE", "GNOME_TERMINAL_SCREEN",
            "KONSOLE_VERSION", "KONSOLE_DBUS_SESSION")
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env["HOME"] = str(sb.home)
    env["USERPROFILE"] = str(sb.home)
    env["APPDATA"] = str(sb.appdata)
    env["LOCALAPPDATA"] = str(sb.localappdata)
    env["CLAUDE_SETUP_VSCODE_KEYBINDINGS"] = str(sb.vscode)
    env["CLAUDE_SETUP_CURSOR_KEYBINDINGS"] = str(sb.cursor)
    if include_wt:
        env["CLAUDE_SETUP_WT_SETTINGS"] = str(sb.wt)
    else:
        env.pop("CLAUDE_SETUP_WT_SETTINGS", None)
    env["PATH"] = isolated_path(sb.stub)
    env["TERM"] = "xterm-256color"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


def to_ps_args(posix_args):
    mapping = {
        "--keybinds": "-Keybinds",
        "--uninstall": "-Uninstall",
        "--dry-run": "-DryRun",
        "--no-onboard": "-NoOnboard",
        "--hooks": "-Hooks",
        "--agentsmd": "-AgentsMd",
        "--help": "-Help",
        "-h": "-Help",
    }
    out = []
    i = 0
    while i < len(posix_args):
        a = posix_args[i]
        if a == "--newline" and i + 1 < len(posix_args):
            out.extend(["-Newline", posix_args[i + 1]])
            i += 2
            continue
        if a.startswith("--newline="):
            out.extend(["-Newline", a.split("=", 1)[1]])
            i += 1
            continue
        if a in mapping:
            out.append(mapping[a])
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def load_apply_module():
    """res/keybinds/apply.py 를 직접 import 한다 (플랫폼 분기 같은 순수 함수 검증용)."""
    import importlib.util
    path = ROOT / "res" / "keybinds" / "apply.py"
    spec = importlib.util.spec_from_file_location("_kb_apply_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_setup(args, sb, worker=None, extra=None, include_wt=True, timeout=180):
    worker = worker or native_worker()
    skip_if_worker_missing(worker)
    env = sandbox_env(sb, extra=extra, include_wt=include_wt)
    if worker == "posix":
        cmd = ["bash", str(SETUP_SH), *args]
    else:
        cmd = [_powershell_exe(), "-NoProfile", "-File", str(SETUP_PS1), *to_ps_args(args)]
    return subprocess.run(
        cmd, cwd=str(sb.project), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def assert_ok(proc):
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def combined_output(proc) -> str:
    return f"{proc.stdout or ''}\n{proc.stderr or ''}"


def target_paths(sb):
    return {
        "vscode": sb.vscode,
        "cursor": sb.cursor,
        "wt": sb.wt,
        "claude_kb": sb.home / ".claude" / "keybindings.json",
        "codex": sb.home / ".codex" / "config.toml",
        "grok": sb.home / ".grok" / "config.toml",
        "tmux": sb.home / ".tmux.conf",
        "manifest": sb.home / ".claude" / ".claude-code-setup.json",
        "settings": sb.home / ".claude" / "settings.json",
        "agentsmd": sb.project / "AGENTS.md",
    }


def snapshot_targets(sb):
    out = {}
    for name, path in target_paths(sb).items():
        out[name] = path.read_bytes() if path.exists() else None
    return out


def snapshot_tree(root: Path):
    files = {}
    if not root.exists():
        return files
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # pwsh -File 이 USERPROFILE 아래에 프로세스 종료 시 남기는 엔진 캐시.
        # 설치 대상이 아니며 구현이 막을 수 없다 (호스트가 스크립트 종료 후에 씀).
        if p.name.startswith("StartupProfileData"):
            continue
        files[str(p.relative_to(root))] = p.read_bytes()
    return files


def read_manifest(home: Path) -> dict:
    path = home / ".claude" / ".claude-code-setup.json"
    assert path.exists(), f"매니페스트가 없다: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_chord(data: dict) -> str:
    kb = data.get("keybinds")
    assert isinstance(kb, dict), f"매니페스트에 keybinds 섹션이 없다: {data!r}"
    chord = kb.get("newline_chord")
    assert chord in ("shift-enter", "ctrl-enter"), (
        f"keybinds.newline_chord 값이 허용 목록이 아니다: {chord!r}"
    )
    return chord


def load_toml(path: Path):
    import tomllib
    text = path.read_text(encoding="utf-8")
    return tomllib.loads(text), text


def claude_chat_map(data) -> dict:
    assert isinstance(data, dict), f"Claude keybindings.json 은 객체여야 한다: {data!r}"
    chat = data.get("Chat")
    assert isinstance(chat, dict), f"Chat 컨텍스트가 없다: {data!r}"
    return chat


def wt_send_bindings(settings: dict):
    actions = settings.get("actions") or settings.get("keybindings") or []
    found = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        keys = item.get("keys") or item.get("key") or ""
        if isinstance(keys, list):
            keys = " ".join(str(k) for k in keys)
        keys_n = norm_key(keys)
        cmd = item.get("command")
        payload = ""
        is_send = False
        if isinstance(cmd, dict):
            action = str(cmd.get("action") or "").lower()
            if action in ("sendinput", "send"):
                is_send = True
                payload = cmd.get("input") or cmd.get("text") or ""
        elif isinstance(cmd, str) and cmd.lower() in ("sendinput", "send"):
            is_send = True
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            payload = item.get("input") or args.get("input") or args.get("text") or ""
        if is_send:
            found.append((keys_n, payload, item))
    return found


def assert_ide_install(path: Path, chord: str) -> str:
    entries = load_keybindings(path)
    managed = managed_sendsequences(entries)
    assert len(managed) == 1, (
        f"{path.name}: 관리 sendSequence 는 하나여야 한다 (got {len(managed)}): {managed!r}"
    )
    entry = managed[0]
    assert norm_key(entry.get("key")) == vscode_key(chord), (
        f"{path.name}: 관리 바인딩 key 가 {vscode_key(chord)} 가 아니다: {entry.get('key')!r}"
    )
    when = str(entry.get("when") or "")
    assert "terminalFocus" in when
    assert not re.search(r"editor|notebook", when, re.I), (
        f"{path.name}: 관리 바인딩 when 에 에디터/노트북 절이 있다: {when!r}"
    )
    seq = sendsequence_text(entry)
    assert not is_forbidden_sequence(seq), f"{path.name}: 금지 시퀀스: {seq!r}"
    assert is_allowed_sequence(seq), (
        f"{path.name}: 시퀀스가 SSoT 후보가 아니다: {seq!r}"
    )
    # 관리 항목만 다시 도는 것은 위 단언을 되풀이할 뿐이다 (항상 참).
    # 어휘 6 은 파일 전체에 대한 조건이므로 외래 항목까지 포함해 본다.
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("command") != "workbench.action.terminal.sendSequence":
            continue
        if not is_allowed_sequence(sendsequence_text(e)):
            continue
        k = norm_key(e.get("key"))
        assert k != vscode_other_key(chord), (
            f"{path.name}: 고르지 않은 수정 Enter 에 SSoT 시퀀스가 걸려 있다: {k}"
        )
        assert k not in ("enter", "return"), (
            f"{path.name}: 단독 enter 에 SSoT 시퀀스가 걸려 있다"
        )
    return seq


def assert_foreign_preserved(path: Path):
    entries = load_keybindings(path)
    ids = {(norm_key(e.get("key")), e.get("command"), e.get("when")) for e in entries
           if isinstance(e, dict)}
    assert (FOREIGN_VSCODE_KEY, FOREIGN_VSCODE_COMMAND, "terminalFocus") in ids, (
        f"{path.name}: 외래 항목 {FOREIGN_VSCODE_KEY} 가 사라졌다"
    )
    editor = [e for e in entries if isinstance(e, dict)
              and e.get("command") == EDITOR_SHIFT_ENTER_COMMAND
              and norm_key(e.get("key")) == "shift+enter"]
    assert editor, f"{path.name}: 에디터 Shift+Enter 항목이 사라졌다"
    notebook = [e for e in entries if isinstance(e, dict)
                and e.get("command") == NOTEBOOK_SHIFT_ENTER_COMMAND
                and norm_key(e.get("key")) == "shift+enter"]
    assert notebook, f"{path.name}: 노트북 Shift+Enter 항목이 사라졌다"
    keep = [e for e in entries if isinstance(e, dict)
            and e.get("command") == "workbench.action.terminal.sendSequence"
            and sendsequence_text(e) == "keep-me"]
    assert keep, f"{path.name}: 사용자 sendSequence(keep-me) 가 사라졌다"


def assert_no_other_emulators(home: Path):
    forbidden = [
        Path("Library") / "Application Support" / "iTerm2",
        Path("Library") / "Preferences" / "com.googlecode.iterm2.plist",
        Path(".config") / "kitty",
        Path(".config") / "wezterm",
        Path(".config") / "ghostty",
        Path(".config") / "alacritty",
        Path(".config") / "iterm2",
        Path(".iterm2"),
        Path(".warp"),
        Path(".wezterm.lua"),
    ]
    for rel in forbidden:
        p = home / rel
        assert not p.exists(), f"네이티브 대상이 아닌 에뮬레이터 경로를 만들었다: {p}"


def assert_newline_install_result(
    sb,
    chord: str,
    *,
    expect_claude=True,
    expect_codex=True,
    expect_tmux=None,
    expect_wt=True,
):
    """어휘 '줄바꿈 설치 결과(C)' 일곱 항을 모두 단언한다."""
    assert chord in ("shift-enter", "ctrl-enter")
    if expect_tmux is None:
        expect_tmux = sys.platform != "win32"

    vs_seq = assert_ide_install(sb.vscode, chord)
    cur_seq = assert_ide_install(sb.cursor, chord)
    # 같은 설치의 SSoT 상수는 하나다. (예전의 "or 둘 다 SSoT" 절은 항상 참이라 지웠다 —
    #  두 값 모두 assert_ide_install 에서 이미 is_allowed_sequence 를 통과했기 때문이다.)
    assert normalize_seq(vs_seq) == normalize_seq(cur_seq), (
        f"VS Code 와 Cursor 가 다른 시퀀스를 쓴다: {vs_seq!r} vs {cur_seq!r}"
    )
    assert_foreign_preserved(sb.vscode)
    assert_foreign_preserved(sb.cursor)
    cursor_entries = load_keybindings(sb.cursor)
    assert any(isinstance(e, dict) and e.get("command") == FOREIGN_CURSOR_COMMAND
               for e in cursor_entries), "Cursor 외래 항목이 사라졌다"

    if expect_claude:
        claude_path = sb.home / ".claude" / "keybindings.json"
        data = json.loads(claude_path.read_text(encoding="utf-8"))
        chat = claude_chat_map(data)
        assert chat.get(vscode_key(chord)) == "chat:newline", (
            f"Claude Chat 에 {vscode_key(chord)} → chat:newline 이 없다: {chat!r}"
        )
        assert chat.get(CLAUDE_PRESERVE_KEY) == CLAUDE_PRESERVE_COMMAND, (
            "Claude Chat 의 기존 바인딩이 사라졌다"
        )
        assert chat.get("escape") == "chat:cancel"
        assert data.get("User", {}).get("f9") == "app:toggleHelp", (
            "Claude 의 다른 context 가 사라졌다"
        )
        assert chat.get(vscode_other_key(chord)) != "chat:newline", (
            f"고르지 않은 {vscode_other_key(chord)} 가 Claude Chat 관리 줄바꿈으로 들어갔다"
        )

    if expect_codex:
        toml_path = sb.home / ".codex" / "config.toml"
        parsed, text = load_toml(toml_path)
        assert parsed.get("model") == CODEX_SENTINEL_MODEL, "Codex 다른 키가 훼손됐다"
        assert parsed.get("mcp", {}).get("enabled") is True
        editor = ((parsed.get("tui") or {}).get("keymap") or {}).get("editor") or {}
        insert = editor.get("insert_newline") or []
        if isinstance(insert, str):
            insert = [insert]
        assert codex_key(chord) in insert, (
            f"Codex insert_newline 에 {codex_key(chord)} 가 없다: {insert!r}"
        )
        assert "ctrl-j" in insert, f"기존 ctrl-j 가 사라졌다: {insert!r}"
        assert editor.get("indent") == ["tab"] or "tab" in (editor.get("indent") or []), (
            "Codex 다른 키맵 항목이 사라졌다"
        )
        assert (parsed.get("projects") or {}).get("sentinel", {}).get("trust") is True, (
            "Codex 다른 테이블이 사라졌다"
        )
        other_codex = "ctrl-enter" if chord == "shift-enter" else "shift-enter"
        assert other_codex not in insert, (
            f"고르지 않은 {other_codex} 가 Codex insert_newline 에 추가됐다: {insert!r}"
        )

    grok_dir = sb.home / ".grok"
    keymap_names = {
        "keybindings.json", "keymap.json", "keymap.toml", "keys.toml",
        "keys.json", "keybinds.toml", "keybindings.toml",
    }
    if grok_dir.exists():
        for p in grok_dir.rglob("*"):
            if p.is_file():
                assert p.name not in keymap_names, f"Grok 키맵 파일을 만들었다: {p}"
        grok_cfg = grok_dir / "config.toml"
        if grok_cfg.exists():
            grok_text = grok_cfg.read_text(encoding="utf-8")
            assert GROK_SENTINEL.split(" = ")[0] in grok_text, (
                "Grok multiline 관련 키가 지워졌다"
            )
            assert 'sentinel_multiline_key = "keep-me"' in grok_text

    if expect_wt:
        assert sb.wt.exists(), f"WT settings.json 이 없다: {sb.wt}"
        settings = json.loads(sb.wt.read_text(encoding="utf-8"))
        sends = wt_send_bindings(settings)
        # 어휘 5 는 *우리가 넣은* sendInput 에 대한 조건이다. 사용자가 같은 키에 걸어둔
        # 남의 sendInput 까지 없어야 한다고 단언하면, 그 삭제(결정 5 위반)를 테스트가 굳힌다.
        managed = [x for x in sends if is_allowed_sequence(x[1])]
        shift_sends = [x for x in managed if x[0] in ("shift+enter", "shift+return")]
        ctrl_sends = [x for x in managed if x[0] in ("ctrl+enter", "ctrl+return")]
        if chord == "shift-enter":
            assert not shift_sends, (
                f"C=shift-enter 인데 WT 에 관리 shift+enter sendInput 이 있다: {shift_sends!r}"
            )
            assert not ctrl_sends, (
                f"C=shift-enter 인데 WT 에 고르지 않은 관리 ctrl+enter sendInput 이 있다: {ctrl_sends!r}"
            )
        else:
            assert ctrl_sends, "C=ctrl-enter 인데 WT 에 관리 ctrl+enter sendInput 이 없다"
            assert not shift_sends, (
                f"C=ctrl-enter 인데 WT 에 이전 shift+enter 관리 sendInput 이 남았다: {shift_sends!r}"
            )
            payloads = [s[1] for s in ctrl_sends]
            assert any(is_allowed_sequence(p) and not is_forbidden_sequence(p)
                       for p in payloads), (
                f"WT ctrl+enter 시퀀스가 SSoT 가 아니다: {payloads!r}"
            )
            assert any(normalize_seq(p) == normalize_seq(vs_seq) for p in payloads), (
                f"WT 시퀀스가 VS Code SSoT 와 다르다: {payloads!r} vs {vs_seq!r}"
            )
        # 외래 WT 항목 보존 — 키만 겹치는 사용자 sendInput 도 살아 있어야 한다.
        raw = sb.wt.read_text(encoding="utf-8")
        assert WT_FOREIGN_KEYS in raw, "WT 외래 키가 사라졌다"
        assert WT_FOREIGN_SENDINPUT in raw, (
            "사용자가 수정 Enter 에 걸어둔 sendInput 이 사라졌다 (핵심 결정 5)"
        )

    if expect_tmux:
        tmux = sb.home / ".tmux.conf"
        assert tmux.exists(), "tmux.conf 가 없다"
        text = tmux.read_text(encoding="utf-8")
        assert "extended-keys" in text, "tmux extended-keys 가 없다"
        assert "extkeys" in text, "tmux terminal-features extkeys 가 없다"
        assert TMUX_SENTINEL in text, "tmux 사용자 줄이 사라졌다"

    assert_no_other_emulators(sb.home)

    man = read_manifest(sb.home)
    assert manifest_chord(man) == chord


def hooks_installed(sb) -> bool:
    return (sb.home / ".claude" / "hooks" / "danger_guard.py").exists()


def agentsmd_installed(sb) -> bool:
    return (sb.project / "AGENTS.md").exists()


# ── A. CLI · 온보딩 (설치 경로) ───────────────────────────────────────


@posix_only
def test_온보딩_hooks_범위는_키바인드를_설치하지_않는다(kb_sandbox):
    """covers: Test-2
    SCOPE=hooks 로 온보딩을 마치면 키바인드 대상 파일에 관리 바인딩이 생기지 않는다.
    """
    before = snapshot_targets(kb_sandbox)
    env = sandbox_env(kb_sandbox)
    code, screen = onboard_tests.run_in_pty(
        ["bash", str(SETUP_SH)],
        keys=[onboard_tests.DOWN, onboard_tests.ENTER,  # hooks
              onboard_tests.ENTER,                      # auto
              onboard_tests.ENTER],                     # apply
        cwd=kb_sandbox.project, env=env, timeout=90,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert managed_sendsequences(load_keybindings(kb_sandbox.vscode)) == []
    assert managed_sendsequences(load_keybindings(kb_sandbox.cursor)) == []
    claude = json.loads(
        (kb_sandbox.home / ".claude" / "keybindings.json").read_text(encoding="utf-8")
    )
    assert claude_chat_map(claude).get("shift+enter") != "chat:newline"
    assert claude_chat_map(claude).get("ctrl+enter") != "chat:newline"
    assert snapshot_targets(kb_sandbox)["vscode"] == before["vscode"]
    assert snapshot_targets(kb_sandbox)["cursor"] == before["cursor"]


@posix_only
def test_온보딩_agentsmd_범위는_키바인드를_설치하지_않는다(kb_sandbox):
    """covers: Test-2
    SCOPE=agentsmd 이면 AGENTS.md 만 설치하고 키바인드는 쓰지 않는다.
    """
    before = snapshot_targets(kb_sandbox)
    env = sandbox_env(kb_sandbox)
    code, screen = onboard_tests.run_in_pty(
        ["bash", str(SETUP_SH)],
        keys=[onboard_tests.DOWN, onboard_tests.DOWN, onboard_tests.ENTER,  # agentsmd
              onboard_tests.ENTER],                                          # apply
        cwd=kb_sandbox.project, env=env, timeout=90,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert agentsmd_installed(kb_sandbox)
    assert managed_sendsequences(load_keybindings(kb_sandbox.vscode)) == []
    assert not hooks_installed(kb_sandbox)
    after = snapshot_targets(kb_sandbox)
    for name in ("vscode", "cursor", "wt", "claude_kb", "codex"):
        assert after[name] == before[name], f"agentsmd 범위가 {name} 를 바꿨다"


@posix_only
def test_온보딩에서_ctrl_enter를_고르면_설치결과_ctrl_enter(kb_sandbox):
    """covers: Test-3
    SCOPE=all 에서 Ctrl+Enter 를 고르면 줄바꿈 설치 결과(ctrl-enter) 다.
    """
    env = sandbox_env(kb_sandbox)
    code, screen = onboard_tests.run_in_pty(
        ["bash", str(SETUP_SH)],
        keys=[onboard_tests.ENTER,                 # all
              onboard_tests.ENTER,                 # auto
              onboard_tests.DOWN, onboard_tests.ENTER,  # Ctrl+Enter
              onboard_tests.ENTER],                # apply
        cwd=kb_sandbox.project, env=env, timeout=90,
    )
    text = screen.decode(errors="replace")
    assert code == 0, text
    assert_newline_install_result(kb_sandbox, "ctrl-enter")


@posix_only
def test_온보딩_Ctrl_C는_종료130_아무_파일도_안_쓴다(kb_sandbox):
    """covers: Test-4
    온보딩 중 Ctrl+C 는 종료 130, 키바인드 포함 아무 파일도 쓰지 않는다.
    """
    before = snapshot_tree(kb_sandbox.root)
    env = sandbox_env(kb_sandbox)
    code, _ = onboard_tests.run_in_pty(
        ["bash", str(SETUP_SH)],
        keys=[onboard_tests.CTRL_C],
        cwd=kb_sandbox.project, env=env, timeout=90,
    )
    assert code == 130
    assert snapshot_tree(kb_sandbox.root) == before


def test_CI면_온보딩생략_전체설치_shift_enter(kb_sandbox):
    """covers: Test-5
    TTY 없음/CI 에서는 온보딩을 생략하고 전체 설치가 줄바꿈 설치 결과(shift-enter) 다.
    """
    proc = run_setup([], kb_sandbox, extra={"CI": "true"})
    assert_ok(proc)
    assert hooks_installed(kb_sandbox)
    assert agentsmd_installed(kb_sandbox)
    assert_newline_install_result(kb_sandbox, "shift-enter")


def test_keybinds만_설치하고_훅과_AGENTS는_안_건드린다(kb_sandbox):
    """covers: Test-6
    --keybinds / -Keybinds 는 키바인딩만 설치한다. 훅이 없어도 매니페스트를 만든다.
    """
    settings = kb_sandbox.home / ".claude" / "settings.json"
    assert not settings.exists()
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert_newline_install_result(kb_sandbox, "shift-enter")
    assert not hooks_installed(kb_sandbox)
    assert not agentsmd_installed(kb_sandbox)
    assert not settings.exists()
    man = read_manifest(kb_sandbox.home)
    assert manifest_chord(man) == "shift-enter"


@pytest.mark.parametrize("worker", ["posix", "powershell"])
@pytest.mark.parametrize(
    "args,chord,keybinds_only",
    [
        (["--keybinds", "--newline", "ctrl-enter"], "ctrl-enter", True),
        (["--keybinds", "--newline", "shift-enter"], "shift-enter", True),
        (["--newline", "shift-enter"], "shift-enter", False),
        (["--no-onboard", "--newline", "ctrl-enter"], "ctrl-enter", False),
    ],
)
def test_newline_플래그는_코드별_설치결과_C(kb_sandbox, worker, args, chord, keybinds_only):
    """covers: Test-7
    --keybinds --newline ctrl-enter 와 --newline shift-enter (POSIX/PowerShell),
    --no-onboard --newline ctrl-enter 전체 설치가 각각 줄바꿈 설치 결과(C) 다.
    """
    skip_if_worker_missing(worker)
    proc = run_setup(args, kb_sandbox, worker=worker)
    assert_ok(proc)
    assert_newline_install_result(kb_sandbox, chord)
    if keybinds_only:
        assert not hooks_installed(kb_sandbox)
        assert not agentsmd_installed(kb_sandbox)
    if args[:1] == ["--no-onboard"]:
        assert hooks_installed(kb_sandbox)
        assert agentsmd_installed(kb_sandbox)


@pytest.mark.parametrize("worker", ["posix", "powershell"])
@pytest.mark.parametrize("bad", ["enter", "shift+enter", "ctrl+enter", "foo", "Shift-Enter"])
def test_잘못된_newline은_exit1_파일불변(kb_sandbox, worker, bad):
    """covers: Test-8
    --newline 허용 값이 아니면 exit 1, 대상 파일 불변.
    """
    skip_if_worker_missing(worker)
    before = snapshot_tree(kb_sandbox.root)
    proc = run_setup(["--keybinds", "--newline", bad], kb_sandbox, worker=worker)
    assert proc.returncode == 1, combined_output(proc)
    assert snapshot_tree(kb_sandbox.root) == before
    text = combined_output(proc)
    # 플래그 미구현(알 수 없는 옵션) 이 아니라, 값은 받았지만 허용 목록이 아닌 거절이어야 한다.
    assert "알 수 없는 옵션" not in text, text
    assert re.search(r"newline|shift-enter|ctrl-enter", text, re.I), text


def test_hooks와_agentsmd는_키바인드_파일을_쓰지_않는다(kb_sandbox):
    """covers: Test-9
    --hooks, --agentsmd, --hooks --newline ctrl-enter 는 키바인드 대상 파일을 쓰지 않는다.
    """
    before = snapshot_targets(kb_sandbox)

    proc = run_setup(["--hooks"], kb_sandbox)
    assert_ok(proc)
    assert hooks_installed(kb_sandbox)
    assert snapshot_targets(kb_sandbox)["vscode"] == before["vscode"]
    assert snapshot_targets(kb_sandbox)["cursor"] == before["cursor"]
    assert snapshot_targets(kb_sandbox)["wt"] == before["wt"]
    assert snapshot_targets(kb_sandbox)["codex"] == before["codex"]
    claude = json.loads(
        (kb_sandbox.home / ".claude" / "keybindings.json").read_text(encoding="utf-8")
    )
    assert claude_chat_map(claude).get("shift+enter") != "chat:newline"
    assert claude_chat_map(claude).get("ctrl+enter") != "chat:newline"

    proc = run_setup(["--agentsmd"], kb_sandbox)
    assert_ok(proc)
    assert agentsmd_installed(kb_sandbox)
    after_agents = snapshot_targets(kb_sandbox)
    assert after_agents["vscode"] == before["vscode"]
    assert after_agents["cursor"] == before["cursor"]

    # 시드를 다시 깔고 hooks + newline 이 키바인드를 쓰는지 본다.
    _write(kb_sandbox.vscode, DEFAULT_VSCODE_JSONC)
    _write(kb_sandbox.cursor, DEFAULT_CURSOR_JSONC)
    before_combo = snapshot_targets(kb_sandbox)
    proc = run_setup(["--hooks", "--newline", "ctrl-enter"], kb_sandbox)
    assert_ok(proc)
    after_combo = snapshot_targets(kb_sandbox)
    for name in ("vscode", "cursor", "wt", "claude_kb", "codex", "tmux", "grok"):
        assert after_combo[name] == before_combo[name], (
            f"--hooks --newline 이 {name} 를 바꿨다"
        )
    assert managed_sendsequences(load_keybindings(kb_sandbox.vscode)) == []
    assert managed_sendsequences(load_keybindings(kb_sandbox.cursor)) == []


@pytest.mark.parametrize("worker", ["posix", "powershell"])
def test_keybinds_dry_run은_안_쓰고_계획에_경로가_보인다(kb_sandbox, worker):
    """covers: Test-10
    --keybinds --dry-run 은 쓰지 않고, 계획에 키바인드 대상 경로가 보인다.
    """
    skip_if_worker_missing(worker)
    before = snapshot_tree(kb_sandbox.root)
    proc = run_setup(["--keybinds", "--dry-run"], kb_sandbox, worker=worker)
    assert_ok(proc)
    assert snapshot_tree(kb_sandbox.root) == before
    text = combined_output(proc)
    assert "keybindings.json" in text, text
    assert ("config.toml" in text) or ("codex" in text.lower()), text


def test_온보딩스킵_전체설치는_훅_AGENTS_shift_enter(kb_sandbox):
    """covers: Test-11
    온보딩 스킵 전체 설치 = 훅 + AGENTS.md + 줄바꿈 설치 결과(shift-enter).
    """
    proc = run_setup(["--no-onboard"], kb_sandbox)
    assert_ok(proc)
    assert hooks_installed(kb_sandbox)
    assert agentsmd_installed(kb_sandbox)
    assert_newline_install_result(kb_sandbox, "shift-enter")


def test_uninstall은_훅과_관리키바인드를_제거하고_사용자항목은_남긴다(kb_sandbox):
    """covers: Test-12
    setup --uninstall 은 훅과 관리 키바인드를 제거한다.
    --keybinds --uninstall 은 키바인드만. 사용자 원래 항목은 남긴다.
    """
    proc = run_setup(["--no-onboard"], kb_sandbox)
    assert_ok(proc)
    assert hooks_installed(kb_sandbox)
    assert_newline_install_result(kb_sandbox, "shift-enter")

    proc = run_setup(["--keybinds", "--uninstall"], kb_sandbox)
    assert_ok(proc)
    assert hooks_installed(kb_sandbox), "키바인드 uninstall 이 훅까지 지웠다"
    assert managed_sendsequences(load_keybindings(kb_sandbox.vscode)) == []
    assert managed_sendsequences(load_keybindings(kb_sandbox.cursor)) == []
    assert_foreign_preserved(kb_sandbox.vscode)
    claude = json.loads(
        (kb_sandbox.home / ".claude" / "keybindings.json").read_text(encoding="utf-8")
    )
    chat = claude_chat_map(claude)
    assert chat.get("shift+enter") != "chat:newline"
    assert chat.get(CLAUDE_PRESERVE_KEY) == CLAUDE_PRESERVE_COMMAND
    parsed, _ = load_toml(kb_sandbox.home / ".codex" / "config.toml")
    insert = ((parsed.get("tui") or {}).get("keymap") or {}).get("editor", {}).get(
        "insert_newline") or []
    if isinstance(insert, str):
        insert = [insert]
    assert "shift-enter" not in insert
    assert "ctrl-j" in insert
    if sys.platform != "win32":
        tmux = (kb_sandbox.home / ".tmux.conf").read_text(encoding="utf-8")
        assert TMUX_SENTINEL in tmux
        assert "extended-keys" not in tmux
        assert "extkeys" not in tmux

    # 다시 설치한 뒤 전체 uninstall.
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    proc = run_setup(["--uninstall"], kb_sandbox)
    assert_ok(proc)
    assert not hooks_installed(kb_sandbox)
    assert managed_sendsequences(load_keybindings(kb_sandbox.vscode)) == []
    assert_foreign_preserved(kb_sandbox.vscode)
    assert_foreign_preserved(kb_sandbox.cursor)


def test_두번_설치해도_관리바인딩이_늘지_않고_영수증이_비지_않는다(kb_sandbox):
    """covers: Test-13
    두 번 설치해도 관리 바인딩이 늘지 않는다. 설치 전에 동일 바인딩이 있어도
    재추가하지 않는다. 영수증이 빈 값으로 덮이지 않는다.
    """
    proc = run_setup(["--hooks"], kb_sandbox)
    assert_ok(proc)
    proc = run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox)
    assert_ok(proc)
    first = read_manifest(kb_sandbox.home)
    assert first.get("added_allow"), "훅 영수증 added_allow 가 없다"
    assert manifest_chord(first) == "shift-enter"
    n1 = len(managed_sendsequences(load_keybindings(kb_sandbox.vscode)))
    c1 = len(managed_sendsequences(load_keybindings(kb_sandbox.cursor)))

    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    second = read_manifest(kb_sandbox.home)
    assert second.get("added_allow") == first.get("added_allow"), (
        "재실행이 훅 영수증을 지웠다"
    )
    assert manifest_chord(second) == "shift-enter"
    n2 = len(managed_sendsequences(load_keybindings(kb_sandbox.vscode)))
    c2 = len(managed_sendsequences(load_keybindings(kb_sandbox.cursor)))
    assert n1 == n2 == 1
    assert c1 == c2 == 1

    # 이미 같은 관리 바인딩이 있는 픽스처에 설치해도 하나.
    seeded = parse_jsonc(DEFAULT_VSCODE_JSONC)
    seeded.append({
        "key": "shift+enter",
        "command": "workbench.action.terminal.sendSequence",
        "args": {"text": "\u001b\r"},
        "when": "terminalFocus",
    })
    _write(kb_sandbox.vscode, json.dumps(seeded, indent=2) + "\n")
    proc = run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox)
    assert_ok(proc)
    assert len(managed_sendsequences(load_keybindings(kb_sandbox.vscode))) == 1
    assert read_manifest(kb_sandbox.home).get("keybinds"), "영수증 keybinds 가 비었다"


def test_재실행에_newline없으면_매니페스트_이전선택(kb_sandbox):
    """covers: Test-14
    재실행에 --newline 이 없으면 매니페스트의 이전 선택.
    --keybinds 만으로도 선택이 기록된다. 기록 없으면 Shift+Enter.
    """
    proc = run_setup(["--keybinds", "--newline", "ctrl-enter"], kb_sandbox)
    assert_ok(proc)
    assert manifest_chord(read_manifest(kb_sandbox.home)) == "ctrl-enter"
    assert_newline_install_result(kb_sandbox, "ctrl-enter")

    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert manifest_chord(read_manifest(kb_sandbox.home)) == "ctrl-enter"
    assert_newline_install_result(kb_sandbox, "ctrl-enter")

    # 기록 없음: 매니페스트와 관리 대상을 시드로 되돌린 뒤 --keybinds 만 → shift-enter.
    man_path = kb_sandbox.home / ".claude" / ".claude-code-setup.json"
    man_path.unlink()
    _write(kb_sandbox.vscode, DEFAULT_VSCODE_JSONC)
    _write(kb_sandbox.cursor, DEFAULT_CURSOR_JSONC)
    _write(kb_sandbox.home / ".claude" / "keybindings.json",
           json.dumps(DEFAULT_CLAUDE_KEYBINDINGS, indent=2) + "\n")
    _write(kb_sandbox.home / ".codex" / "config.toml", DEFAULT_CODEX_TOML)
    _write(kb_sandbox.wt, DEFAULT_WT_SETTINGS)
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert manifest_chord(read_manifest(kb_sandbox.home)) == "shift-enter"
    assert_newline_install_result(kb_sandbox, "shift-enter")


@pytest.mark.parametrize("worker", ["posix", "powershell"])
def test_help에_keybinds와_newline이_보인다(kb_sandbox, worker):
    """covers: Test-15
    setup.sh --help 와 setup.ps1 -Help 에 --keybinds/-Keybinds 와 --newline 이 보인다.
    """
    skip_if_worker_missing(worker)
    proc = run_setup(["--help"], kb_sandbox, worker=worker)
    assert_ok(proc)
    text = combined_output(proc)
    if worker == "posix":
        assert "--keybinds" in text, text
        assert "--newline" in text, text
    else:
        assert "-Keybinds" in text or "Keybinds" in text, text
        assert "-Newline" in text or "Newline" in text, text


def test_다른_newline으로_재실행하면_관리바인딩이_교체된다(kb_sandbox):
    """covers: Test-16
    한 코드로 설치한 뒤 다른 --newline 으로 재실행하면 관리 바인딩이 교체된다.
    이전 코드의 관리 항목이 남지 않는다.
    """
    proc = run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox)
    assert_ok(proc)
    assert_newline_install_result(kb_sandbox, "shift-enter")

    proc = run_setup(["--keybinds", "--newline", "ctrl-enter"], kb_sandbox)
    assert_ok(proc)
    assert_newline_install_result(kb_sandbox, "ctrl-enter")
    for path in (kb_sandbox.vscode, kb_sandbox.cursor):
        for e in managed_sendsequences(load_keybindings(path)):
            assert norm_key(e.get("key")) != "shift+enter", (
                f"{path.name}: 이전 shift+enter 관리 항목이 남았다"
            )


# ── B. 파일 · 스킵 ───────────────────────────────────────────────────


def test_VSCode_Cursor_기존_다른_키바인딩은_보존된다(kb_sandbox):
    """covers: Test-18
    VS Code/Cursor 픽스처의 기존 다른 키바인딩은 설치 후에도 그대로다.
    """
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert_foreign_preserved(kb_sandbox.vscode)
    assert_foreign_preserved(kb_sandbox.cursor)
    cursor = load_keybindings(kb_sandbox.cursor)
    assert any(isinstance(e, dict) and e.get("command") == FOREIGN_CURSOR_COMMAND
               for e in cursor)


def test_기존_Claude_keybindings는_Chat에만_합친다(kb_sandbox):
    """covers: Test-19
    기존 Claude keybindings.json 이면 Chat 에 고른 키 → chat:newline 만 합치고
    나머지 context/bindings 는 보존한다.
    """
    proc = run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox)
    assert_ok(proc)
    data = json.loads(
        (kb_sandbox.home / ".claude" / "keybindings.json").read_text(encoding="utf-8")
    )
    chat = claude_chat_map(data)
    assert chat["shift+enter"] == "chat:newline"
    assert chat.get("ctrl+enter") != "chat:newline"
    assert chat[CLAUDE_PRESERVE_KEY] == CLAUDE_PRESERVE_COMMAND
    assert chat["escape"] == "chat:cancel"
    assert data["User"]["f9"] == "app:toggleHelp"


def test_Codex_다른키와_테이블을_보존하고_insert_newline은_합집합(kb_sandbox):
    """covers: Test-20
    Codex 다른 키/테이블 보존, insert_newline 에 고른 키 합집합, 기존 ctrl-j 등 삭제 금지.
    """
    proc = run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox)
    assert_ok(proc)
    parsed, _ = load_toml(kb_sandbox.home / ".codex" / "config.toml")
    assert parsed["model"] == CODEX_SENTINEL_MODEL
    assert parsed["mcp"]["enabled"] is True
    editor = parsed["tui"]["keymap"]["editor"]
    insert = editor["insert_newline"]
    if isinstance(insert, str):
        insert = [insert]
    assert "shift-enter" in insert
    assert "ctrl-j" in insert
    assert editor["indent"] == ["tab"] or "tab" in editor["indent"]
    assert parsed["projects"]["sentinel"]["trust"] is True


def test_Grok_설정이_있어도_키맵을_만들지_않는다(kb_sandbox):
    """covers: Test-21
    Grok 설정 디렉터리가 있어도 키맵 파일을 만들지 않는다.
    multiline 관련 키를 쓰거나 지우지 않는다.
    """
    grok_cfg = kb_sandbox.home / ".grok" / "config.toml"
    original = grok_cfg.read_bytes()
    before_names = {p.name for p in (kb_sandbox.home / ".grok").rglob("*") if p.is_file()}
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert grok_cfg.read_bytes() == original
    after_names = {p.name for p in (kb_sandbox.home / ".grok").rglob("*") if p.is_file()}
    assert after_names == before_names
    for p in (kb_sandbox.home / ".grok").rglob("*"):
        if p.is_file():
            assert p.name not in {
                "keybindings.json", "keymap.json", "keymap.toml",
                "keys.toml", "keys.json", "keybinds.toml", "keybindings.toml",
            }


def test_바이너리와_설정이_둘_다_없으면_에이전트_skip(kb_sandbox):
    """covers: Test-22
    바이너리와 설정 디렉터리가 둘 다 없으면 그 에이전트 skip, exit 0.
    """
    shutil.rmtree(kb_sandbox.home / ".claude", ignore_errors=True)
    shutil.rmtree(kb_sandbox.home / ".codex", ignore_errors=True)
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert not (kb_sandbox.home / ".claude" / "keybindings.json").exists()
    assert not (kb_sandbox.home / ".codex" / "config.toml").exists()
    # 매니페스트는 --keybinds 만으로도 만든다.
    assert (kb_sandbox.home / ".claude" / ".claude-code-setup.json").exists()
    # 터미널 층은 에이전트 skip 과 무관하게 설치된다.
    assert len(managed_sendsequences(load_keybindings(kb_sandbox.vscode))) == 1


def test_하나만_있으면_키맵을_쓴다(kb_sandbox):
    """covers: Test-22
    바이너리와 설정 디렉터리 중 하나만 있으면 skip 하지 않고 키맵을 쓴다.
    """
    # 설정 디렉터리만 (기본 픽스처). PATH 에는 에이전트 스텁 없음.
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert (kb_sandbox.home / ".claude" / "keybindings.json").exists()
    chat = claude_chat_map(json.loads(
        (kb_sandbox.home / ".claude" / "keybindings.json").read_text(encoding="utf-8")
    ))
    assert chat.get("shift+enter") == "chat:newline"
    parsed, _ = load_toml(kb_sandbox.home / ".codex" / "config.toml")
    insert = parsed["tui"]["keymap"]["editor"]["insert_newline"]
    if isinstance(insert, str):
        insert = [insert]
    assert "shift-enter" in insert

    # 바이너리만: 설정 디렉터리를 지우고 스텁 바이너리를 둔다.
    shutil.rmtree(kb_sandbox.home / ".claude", ignore_errors=True)
    shutil.rmtree(kb_sandbox.home / ".codex", ignore_errors=True)
    write_stub_agent(kb_sandbox.stub, "claude")
    write_stub_agent(kb_sandbox.stub, "codex")
    _write(kb_sandbox.vscode, DEFAULT_VSCODE_JSONC)
    _write(kb_sandbox.cursor, DEFAULT_CURSOR_JSONC)
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert (kb_sandbox.home / ".claude" / "keybindings.json").exists()
    assert (kb_sandbox.home / ".codex" / "config.toml").exists()
    chat = claude_chat_map(json.loads(
        (kb_sandbox.home / ".claude" / "keybindings.json").read_text(encoding="utf-8")
    ))
    assert chat.get("shift+enter") == "chat:newline"


@tmux_only
def test_tmux_conf에_extended_keys를_없을때만_추가한다(kb_sandbox):
    """covers: Test-23
    tmux.conf 에 extended-keys / extkeys terminal-features 가 없으면 추가,
    있으면 중복하지 않는다.
    """
    tmux = kb_sandbox.home / ".tmux.conf"
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    first = tmux.read_text(encoding="utf-8")
    assert "extended-keys" in first
    assert "extkeys" in first
    n_ext = first.count("extended-keys")
    n_feat = first.count("extkeys")

    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    second = tmux.read_text(encoding="utf-8")
    assert second.count("extended-keys") == n_ext
    assert second.count("extkeys") == n_feat

    # 이미 있는 파일에는 추가하지 않는다.
    seeded = TMUX_SENTINEL + "\nset -g extended-keys on\nset -as terminal-features 'xterm*:extkeys'\n"
    _write(tmux, seeded)
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    after = tmux.read_text(encoding="utf-8")
    assert after.count("extended-keys") == 1
    assert after.count("extkeys") == 1
    assert TMUX_SENTINEL in after


@pytest.mark.parametrize("injected", [
    # 감지 결과를 그대로 주입 (테스트 전용 통로)
    {"CLAUDE_SETUP_DETECTED_TERMINAL": "gnome-terminal"},
    # gnome-terminal 이 스스로 남기는 환경변수 — 실사용 경로가 죽어 있지 않은지 본다
    {"GNOME_TERMINAL_SERVICE": ":1.42"},
    # konsole 짝
    {"KONSOLE_VERSION": "230804"},
])
def test_불가_터미널은_실패하지_않고_경고한다(kb_sandbox, injected):
    """covers: Test-24
    불가 터미널 감지는 픽스처로 주입. 설치는 실패하지 않고 SSH/외부 터미널 경고.
    실제 gnome-terminal 불필요.
    """
    proc = run_setup(["--keybinds"], kb_sandbox, extra=injected)
    assert_ok(proc)
    text = combined_output(proc)
    assert ("SSH" in text) or ("외부 터미널" in text), text
    assert_newline_install_result(kb_sandbox, "shift-enter")


def test_관리바인딩_when은_terminalFocus이고_에디터항목은_그대로(kb_sandbox):
    """covers: Test-25
    관리 바인딩 when 은 terminalFocus 를 포함한다. 에디터/노트북 Shift+Enter 는 그대로다.
    """
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    for path in (kb_sandbox.vscode, kb_sandbox.cursor):
        managed = managed_sendsequences(load_keybindings(path))
        assert managed
        for e in managed:
            assert "terminalFocus" in str(e.get("when") or "")
            assert not re.search(r"editor|notebook", str(e.get("when") or ""), re.I)
        assert_foreign_preserved(path)


def test_WT_픽스처_shift면_sendInput없고_ctrl면_SSoT(kb_sandbox):
    """covers: Test-26
    격리 WT settings.json: Shift+Enter 면 shift+enter sendInput 없음.
    Ctrl+Enter 면 ctrl+enter → SSoT 시퀀스.
    WT·VS Code·Cursor·tmux·에이전트 키맵 외에 에뮬레이터 설정 파일을 만들지 않는다.
    """
    proc = run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox)
    assert_ok(proc)
    assert_newline_install_result(kb_sandbox, "shift-enter")
    assert_no_other_emulators(kb_sandbox.home)

    proc = run_setup(["--keybinds", "--newline", "ctrl-enter"], kb_sandbox)
    assert_ok(proc)
    assert_newline_install_result(kb_sandbox, "ctrl-enter")
    assert_no_other_emulators(kb_sandbox.home)


def test_WT_대상없으면_skip_exit0(kb_sandbox):
    """covers: Test-27
    WT settings.json 대상 파일이 없으면 WT skip, exit 0.
    """
    if kb_sandbox.wt.exists():
        kb_sandbox.wt.unlink()
    # env 는 여전히 그 경로를 가리킨다. 파일이 없을 때 skip 이지, env 를 빼는 분기가 아니다.
    proc = run_setup(["--keybinds"], kb_sandbox, include_wt=True)
    assert_ok(proc)
    assert not kb_sandbox.wt.exists(), "없는 WT settings.json 을 만들어 버렸다"
    # 나머지 설치는 성공해야 한다.
    assert len(managed_sendsequences(load_keybindings(kb_sandbox.vscode))) == 1


# ── R4 회귀 — docs/reviews/newline-keybind-static-review.md 의 확정 결함 ────────
#
# 새 인수 기준이 아니다. Test-1..27 이 이미 요구하지만 픽스처가 그 분기를 밟지 않아
# 통과해 버린 지점들을, 그 분기를 실제로 시드해서 다시 고정한다.


def test_기본_IDE경로는_세_OS를_각각_따른다():
    """covers: R4 회귀 (어휘 1 — macOS 설치가 무효였다)

    경로가 env 주입으로만 검증되면 default_*_path 는 한 번도 실행되지 않는 죽은 코드가
    된다. 실제로 darwin 분기가 없어 mac 은 아무도 읽지 않는 ~/.config 에 파일을 만들었다.
    """
    apply = load_apply_module()
    home = Path("/home/u")

    mac = apply.default_vscode_path(home, platform="darwin", appdata=None)
    assert mac.parts[-5:] == ("Library", "Application Support", "Code", "User",
                              "keybindings.json"), mac
    mac_cur = apply.default_cursor_path(home, platform="darwin", appdata=None)
    assert mac_cur.parts[-5:] == ("Library", "Application Support", "Cursor", "User",
                                  "keybindings.json"), mac_cur

    lin = apply.default_vscode_path(home, platform="linux", appdata=None)
    assert lin.parts[-4:] == (".config", "Code", "User", "keybindings.json"), lin

    win = apply.default_cursor_path(home, platform="win32", appdata="X:/AppData")
    assert win.parts[-4:] == ("AppData", "Cursor", "User", "keybindings.json"), win


def test_트레일링콤마_keybindings도_읽는다():
    """covers: R4 회귀 (어휘 1)

    VS Code 는 `[{...},]` 를 정상으로 받아들인다. 우리가 못 읽으면 그 사용자에게는
    관리 sendSequence 가 하나도 안 들어간 채 '설치 완료' 만 보인다.
    """
    apply = load_apply_module()
    assert apply.parse_jsonc('[\n  {"key": "a", "command": "b"},\n]\n') == [
        {"key": "a", "command": "b"}
    ]
    # 문자열 안의 콤마는 건드리지 않는다.
    assert apply.parse_jsonc('[{"key": "a,]"}]') == [{"key": "a,]"}]


def test_읽지_못한_대상이_있으면_성공이라고_말하지_않는다(kb_sandbox):
    """covers: R4 회귀 (핵심 결정 9 는 '에이전트가 없을 때' 의 skip 만 허용한다)"""
    kb_sandbox.vscode.write_text("{ not json at all", encoding="utf-8")
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert proc.returncode != 0, f"읽지 못한 대상이 있는데 성공했다:\n{combined_output(proc)}"
    assert "건너뛰" in combined_output(proc), combined_output(proc)


@tmux_only
def test_사용자가_이미_가진_extended_keys는_전체_uninstall에도_남는다(kb_sandbox):
    """covers: Test-12 (tmux 는 우리가 넣은 줄만 지운다)

    사용자가 SSoT 상수와 글자까지 같은 두 줄을 이미 갖고 있으면 설치는 아무것도 넣지
    않는다. 그때 uninstall 이 '문자열이 같으니 우리 것' 이라고 지우면 남의 설정을 지운다.
    """
    apply = load_apply_module()
    tmux = kb_sandbox.home / ".tmux.conf"
    tmux.write_text(
        TMUX_SENTINEL + "\n" + apply.TMUX_EXTENDED_LINE + "\n"
        + apply.TMUX_EXTKEYS_LINE + "\n", encoding="utf-8")

    assert_ok(run_setup([], kb_sandbox))
    assert_ok(run_setup(["--uninstall"], kb_sandbox))

    after = tmux.read_text(encoding="utf-8")
    assert apply.TMUX_EXTENDED_LINE in after, "사용자가 직접 쓴 extended-keys 줄이 사라졌다"
    assert apply.TMUX_EXTKEYS_LINE in after, "사용자가 직접 쓴 extkeys 줄이 사라졌다"
    assert TMUX_SENTINEL in after


@tmux_only
def test_우리가_넣은_extended_keys는_전체_uninstall로_사라진다(kb_sandbox):
    """covers: Test-12 (순서 회귀)

    훅 uninstall 이 매니페스트를 먼저 지우면 키바인드 제거가 영수증을 잃고, 우리가
    넣은 줄이 그대로 남는다. 위 테스트와 짝이다 — 한쪽만 보면 반대 방향으로 틀린다.
    """
    tmux = kb_sandbox.home / ".tmux.conf"
    tmux.write_text(TMUX_SENTINEL + "\n", encoding="utf-8")

    assert_ok(run_setup([], kb_sandbox))
    assert "extended-keys" in tmux.read_text(encoding="utf-8")

    assert_ok(run_setup(["--uninstall"], kb_sandbox))
    after = tmux.read_text(encoding="utf-8")
    assert "extended-keys" not in after, f"우리가 넣은 줄이 남았다:\n{after}"
    assert TMUX_SENTINEL in after, "사용자 줄까지 지웠다"


def test_훅_설치가_키바인드_영수증을_덮지_않는다(kb_sandbox):
    """covers: Test-13/14 (영수증이 빈 값으로 덮이지 않는다)

    두 워커가 같은 매니페스트 파일을 쓴다. 훅 병합이 keybinds 섹션을 날리면 재실행에서
    이전 선택이 사라져 조용히 shift-enter 로 되돌아간다.
    """
    manifest = kb_sandbox.home / ".claude" / ".claude-code-setup.json"
    assert_ok(run_setup(["--keybinds", "--newline", "ctrl-enter"], kb_sandbox))
    assert_ok(run_setup(["--hooks"], kb_sandbox))

    kb = json.loads(manifest.read_text(encoding="utf-8")).get("keybinds") or {}
    assert kb.get("newline_chord") == "ctrl-enter", f"영수증이 사라졌다: {kb!r}"

    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    assert_newline_install_result(kb_sandbox, "ctrl-enter")


def test_사용자가_직접_넣은_고르지_않은_키는_설치가_지우지_않는다(kb_sandbox):
    """covers: R4 회귀 (핵심 결정 5 · CONTEXT.md '고르지 않은 키')

    영수증이 없다는 것은 우리가 넣지 않았다는 뜻이다. 그런데도 지우면 사용자가 직접
    건 Ctrl+Enter 줄바꿈이 첫 설치에서 조용히 사라진다.
    """
    claude_kb = kb_sandbox.home / ".claude" / "keybindings.json"
    claude_kb.write_text(json.dumps({"Chat": {"ctrl+enter": "chat:newline"}}, indent=2),
                         encoding="utf-8")
    codex = kb_sandbox.home / ".codex" / "config.toml"
    codex.write_text('[tui.keymap.editor]\ninsert_newline = ["ctrl-enter", "ctrl-j"]\n',
                     encoding="utf-8")

    assert_ok(run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox))

    chat = claude_chat_map(json.loads(claude_kb.read_text(encoding="utf-8")))
    assert chat.get("shift+enter") == "chat:newline"
    assert chat.get("ctrl+enter") == "chat:newline", (
        f"사용자가 직접 넣은 ctrl+enter 가 사라졌다: {chat!r}"
    )

    parsed, text = load_toml(codex)
    insert = (((parsed.get("tui") or {}).get("keymap") or {}).get("editor") or {}
              ).get("insert_newline") or []
    for key in ("shift-enter", "ctrl-enter", "ctrl-j"):
        assert key in insert, f"{key} 가 insert_newline 에 없다: {insert!r}\n{text}"


def test_개행없이_끝나는_codex_toml도_깨지지_않는다(kb_sandbox):
    """covers: Test-20 (다른 키/테이블 보존)

    파일이 개행 없이 끝나고 [tui.keymap.editor] 가 마지막 섹션이면, 보정이 없을 때
    `indent = ["tab"]insert_newline = [...]` 가 만들어져 TOML 전체가 파싱 불가가 된다.
    """
    codex = kb_sandbox.home / ".codex" / "config.toml"
    codex.write_text('model = "%s"\n[tui.keymap.editor]\nindent = ["tab"]'
                     % CODEX_SENTINEL_MODEL, encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))

    parsed, text = load_toml(codex)
    assert parsed.get("model") == CODEX_SENTINEL_MODEL, text
    editor = ((parsed.get("tui") or {}).get("keymap") or {}).get("editor") or {}
    assert editor.get("indent") == ["tab"], text
    assert "shift-enter" in (editor.get("insert_newline") or []), text


def test_codex_같은_줄_주석을_항목으로_읽지_않는다(kb_sandbox):
    """covers: Test-20 (다른 키 보존)

    정규식이 주석 안의 따옴표 문자열까지 항목으로 흡수하면 없는 키가 생기고 주석은 사라진다.
    """
    codex = kb_sandbox.home / ".codex" / "config.toml"
    codex.write_text(
        '[tui.keymap.editor]\n'
        'insert_newline = ["ctrl-j"]  # "alt-enter" 는 안 먹음\n',
        encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))

    parsed, text = load_toml(codex)
    insert = (((parsed.get("tui") or {}).get("keymap") or {}).get("editor") or {}
              ).get("insert_newline") or []
    assert "alt-enter" not in insert, f"주석 속 문자열을 항목으로 읽었다: {insert!r}"
    assert set(insert) == {"ctrl-j", "shift-enter"}, insert
    assert "안 먹음" in text, f"같은 줄 주석이 사라졌다:\n{text}"


def test_codex_uninstall은_빈_insert_newline을_남기지_않는다(kb_sandbox):
    """covers: Test-12 (사용자 원래 항목은 남기고 우리 것만 되돌린다)

    빈 배열을 남기면 설치 전에 없던 '줄바꿈 전면 언바인드' 라는 새 설정을 만드는 것이다.
    """
    codex = kb_sandbox.home / ".codex" / "config.toml"
    codex.write_text('model = "%s"\n' % CODEX_SENTINEL_MODEL, encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    assert "shift-enter" in codex.read_text(encoding="utf-8")

    assert_ok(run_setup(["--keybinds", "--uninstall"], kb_sandbox))

    text = codex.read_text(encoding="utf-8")
    assert "insert_newline" not in text, f"빈 insert_newline 이 남았다:\n{text}"
    assert "[tui.keymap.editor]" not in text, f"빈 테이블이 남았다:\n{text}"
    parsed, _ = load_toml(codex)
    assert parsed.get("model") == CODEX_SENTINEL_MODEL, text


def test_바꾸기_전_원본을_백업하고_임시파일을_남기지_않는다(kb_sandbox):
    """covers: R4 회귀 (핵심 결정 8 — 훅 설치와 같은 철학)"""
    assert_ok(run_setup(["--keybinds"], kb_sandbox))

    backups = sorted(kb_sandbox.vscode.parent.glob(kb_sandbox.vscode.name + ".bak.*"))
    assert backups, "VS Code keybindings.json 을 바꾸면서 백업을 남기지 않았다"
    assert FOREIGN_VSCODE_COMMAND in backups[0].read_text(encoding="utf-8"), "백업이 원본이 아니다"
    assert not list(kb_sandbox.vscode.parent.glob("*.tmp-claude-code-setup")), "임시 파일이 남았다"


def test_재실행은_백업을_쌓지_않는다(kb_sandbox):
    """covers: Test-13 (두 번 설치해도 늘어나지 않는다)

    백업은 '바꿀 때만' 남겨야 한다. 내용이 같은데도 다시 쓰면 재실행마다 .bak 이 쌓여
    사용자 디렉터리를 어지럽힌다 — 멱등의 의미는 파일을 건드리지 않는 것이다.
    """
    def backup_count():
        n = 0
        for d in (kb_sandbox.vscode.parent, kb_sandbox.cursor.parent,
                  kb_sandbox.home / ".claude", kb_sandbox.home / ".codex"):
            n += len(list(d.glob("*.bak.*"))) if d.is_dir() else 0
        return n

    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    first = backup_count()
    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    assert backup_count() == first, "멱등 재실행이 백업을 더 남겼다"
    assert_newline_install_result(kb_sandbox, "shift-enter")


def test_불가_터미널_주입이_없으면_경고하지_않는다(kb_sandbox):
    """covers: Test-24 대조군

    감지가 무조건 참이면 주입 테스트는 아무것도 검증하지 못한다. 무주입 대조군이 필요하다.
    """
    proc = run_setup(["--keybinds"], kb_sandbox)
    assert_ok(proc)
    assert "구분하지 못합니다" not in combined_output(proc), combined_output(proc)


# ── Codex 리뷰 회귀 — docs/reviews/newline-keybind-codex-review.md ──────────────
#
# 앞선 정적 검토와 같은 패턴이 반복됐다: 확정 결함 아홉 개가 전부 어떤 픽스처도
# 시드하지 않는 분기에 있었다. 아래는 그 분기를 직접 만들어 고정한다.


def test_설치가_덮어쓴_Claude값을_uninstall이_되돌린다(kb_sandbox):
    """covers: Test-12 (사용자 원래 항목은 남긴다)

    고른 키에 사용자가 다른 명령을 걸어두었으면 설치는 그것을 덮어쓴다. 되돌릴 기록을
    남기지 않으면 uninstall 이 원상 복구가 아니라 삭제가 된다.
    """
    claude_kb = kb_sandbox.home / ".claude" / "keybindings.json"
    claude_kb.write_text(json.dumps({"Chat": {
        "shift+enter": "chat:submit",
        "ctrl+enter": "chat:newline",
    }}, indent=2), encoding="utf-8")

    assert_ok(run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox))
    assert_ok(run_setup(["--keybinds", "--uninstall"], kb_sandbox))

    chat = claude_chat_map(json.loads(claude_kb.read_text(encoding="utf-8")))
    assert chat.get("shift+enter") == "chat:submit", (
        f"설치가 덮어쓴 값을 되돌리지 않았다: {chat!r}"
    )
    assert chat.get("ctrl+enter") == "chat:newline", (
        f"사용자가 직접 넣은 고르지 않은 키를 지웠다: {chat!r}"
    )


def test_uninstall은_영수증에_없는_Codex코드를_지우지_않는다(kb_sandbox):
    """covers: Test-12 (사용자 원래 항목은 남긴다)

    insert_newline 의 "shift-enter" 는 사용자가 직접 쓰는 값과 글자까지 같다.
    영수증 없이 값만 보고 지우면 남의 설정을 지운다.
    """
    codex = kb_sandbox.home / ".codex" / "config.toml"
    codex.write_text(
        '[tui.keymap.editor]\ninsert_newline = ["shift-enter", "ctrl-enter", "ctrl-j"]\n',
        encoding="utf-8")

    assert_ok(run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox))
    assert_ok(run_setup(["--keybinds", "--uninstall"], kb_sandbox))

    parsed, text = load_toml(codex)
    insert = (((parsed.get("tui") or {}).get("keymap") or {}).get("editor") or {}
              ).get("insert_newline") or []
    for key in ("shift-enter", "ctrl-enter", "ctrl-j"):
        assert key in insert, f"사용자가 갖고 있던 {key} 가 사라졌다: {insert!r}\n{text}"


@pytest.mark.parametrize("source", [
    'tui.keymap.editor.insert_newline = ["ctrl-j"]\n',
    '[tui]\nkeymap.editor.insert_newline = ["ctrl-j"]\n',
    '[tui.keymap]\neditor.insert_newline = ["ctrl-j"]\n',
    'tui.keymap.editor.indent = ["tab"]\n',
])
def test_점표기_codex_toml도_유효하게_남는다(kb_sandbox, source):
    """covers: Test-20 (다른 키/테이블 보존)

    TOML 에서 `a.b.c.key = ...` 는 그 테이블을 만든다. 헤더 형태만 알아보면 이미 만들어진
    테이블에 [tui.keymap.editor] 헤더를 덧붙이게 되고, 같은 테이블 이중 선언이라 파서가
    파일 전체를 거부한다.
    """
    codex = kb_sandbox.home / ".codex" / "config.toml"
    codex.write_text(source, encoding="utf-8")

    assert_ok(run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox))

    parsed, text = load_toml(codex)
    assert parsed is not None, f"TOML 이 깨졌다:\n{text}"
    insert = (((parsed.get("tui") or {}).get("keymap") or {}).get("editor") or {}
              ).get("insert_newline") or []
    assert "shift-enter" in insert, f"{insert!r}\n{text}"


def test_고르지_않은_키의_WT_사용자항목은_남는다(kb_sandbox):
    """covers: Test-26 / 핵심 결정 5

    시퀀스만 보면 사용자가 Ctrl+Enter 에 직접 건 항목도 '우리 것' 으로 읽힌다.
    지금 쓰는 키도 아니고 영수증에도 없으면 우리 것이 아니다.
    """
    kb_sandbox.wt.write_text(json.dumps({"actions": [
        {"command": {"action": "sendInput", "input": "\u001b\r"}, "keys": "ctrl+enter"},
        {"command": "copy", "keys": WT_FOREIGN_KEYS},
    ]}, indent=2), encoding="utf-8")

    assert_ok(run_setup(["--keybinds", "--newline", "shift-enter"], kb_sandbox))

    raw = kb_sandbox.wt.read_text(encoding="utf-8")
    settings = json.loads(raw)
    sends = wt_send_bindings(settings)
    assert any(entry[0] in ("ctrl+enter", "ctrl+return") for entry in sends), (
        f"사용자가 직접 건 ctrl+enter sendInput 이 사라졌다:\n{raw}"
    )
    assert WT_FOREIGN_KEYS in raw


def test_WT_기본경로는_Stable말고도_찾는다():
    """covers: R4 회귀 (Test-26/27 은 env 주입으로만 돌아 실제 해석기를 못 본다)"""
    apply = load_apply_module()
    # LOCALAPPDATA 를 인자로 준다 — 플랫폼과 무관하게 해석기 자체를 본다.
    names = [str(p) for p in apply.default_wt_paths(local="X:/Local")]
    assert any("WindowsTerminalPreview" in n for n in names), names
    assert any("WindowsTerminalCanary" in n for n in names), names
    assert any(n.endswith(str(Path("Microsoft") / "Windows Terminal" / "settings.json"))
               for n in names), names


def test_tmux_주석은_설정으로_세지_않는다(kb_sandbox):
    """covers: Test-23 (없으면 추가, 있으면 중복하지 않는다)

    문자열 검사가 주석까지 세면 `# extended-keys disabled` 한 줄이 설치를 통째로 막는다.
    """
    if sys.platform == "win32":
        pytest.skip("tmux.conf 는 POSIX 설치 대상")
    apply = load_apply_module()
    tmux = kb_sandbox.home / ".tmux.conf"
    tmux.write_text("# extended-keys disabled\n# extkeys experiment\nset -g mouse on\n",
                    encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))

    text = tmux.read_text(encoding="utf-8")
    assert apply.TMUX_EXTENDED_LINE in text, f"주석이 설치를 막았다:\n{text}"
    assert apply.TMUX_EXTKEYS_LINE in text, f"주석이 설치를 막았다:\n{text}"


@tmux_only
def test_부분_복구_뒤에도_영수증이_두_줄을_모두_기억한다(kb_sandbox):
    """covers: Test-12/13 (영수증이 빈 값으로 덮이지 않는다)

    사용자가 우리 줄 하나만 지운 뒤 재실행하면 그 한 줄만 다시 넣는다. 영수증을 덮어쓰면
    나머지 한 줄의 소유권 기록을 잃고, uninstall 이 우리 줄을 남긴다.
    """
    apply = load_apply_module()
    tmux = kb_sandbox.home / ".tmux.conf"
    tmux.write_text(TMUX_SENTINEL + "\n", encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    kept = [ln for ln in tmux.read_text(encoding="utf-8").splitlines()
            if ln != apply.TMUX_EXTKEYS_LINE]
    tmux.write_text("\n".join(kept) + "\n", encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    assert_ok(run_setup(["--keybinds", "--uninstall"], kb_sandbox))

    text = tmux.read_text(encoding="utf-8")
    assert apply.TMUX_EXTENDED_LINE not in text, f"우리가 넣은 줄이 남았다:\n{text}"
    assert apply.TMUX_EXTKEYS_LINE not in text, f"우리가 넣은 줄이 남았다:\n{text}"
    assert TMUX_SENTINEL in text, "사용자 줄까지 지웠다"


@tmux_only
def test_tmux도_백업을_남긴다(kb_sandbox):
    """covers: R4 회귀 (핵심 결정 8 — 백업은 tmux.conf 에도 적용된다)"""
    tmux = kb_sandbox.home / ".tmux.conf"
    tmux.write_text(TMUX_SENTINEL + "\n", encoding="utf-8")

    assert_ok(run_setup(["--keybinds"], kb_sandbox))

    backups = list(tmux.parent.glob(".tmux.conf.bak.*"))
    assert backups, "tmux.conf 를 바꾸면서 백업을 남기지 않았다"
    assert TMUX_SENTINEL in backups[0].read_text(encoding="utf-8")


@posix_only
def test_심볼릭_링크를_끊지_않고_권한을_보존한다(kb_sandbox):
    """covers: R4 회귀 (핵심 결정 8)

    dotfile 관리자는 설정을 링크로 건다. 링크를 os.replace 로 갈아치우면 일반 파일이 되어
    관리에서 떨어져 나가고, 새 파일의 기본 권한이 0600 설정을 0644 로 넓힌다.
    """
    codex = kb_sandbox.home / ".codex" / "config.toml"
    real = kb_sandbox.home / ".codex" / "real-config.toml"
    if codex.exists():
        codex.unlink()
    real.write_text('model = "%s"\n' % CODEX_SENTINEL_MODEL, encoding="utf-8")
    os.chmod(real, 0o600)
    os.symlink(str(real), str(codex))

    assert_ok(run_setup(["--keybinds"], kb_sandbox))

    assert codex.is_symlink(), "심볼릭 링크가 일반 파일로 바뀌었다"
    assert "shift-enter" in real.read_text(encoding="utf-8"), "링크가 가리키는 실체가 안 바뀌었다"
    assert oct(real.stat().st_mode & 0o777) == "0o600", (
        f"권한이 넓어졌다: {oct(real.stat().st_mode & 0o777)}"
    )


def test_hooks_uninstall은_키바인딩을_건드리지_않는다(kb_sandbox):
    """covers: Test-9 / 핵심 결정 4

    --hooks 는 키바인딩을 설치하지 않는다. 제거 쪽에서만 그 경계를 무시하면 안 된다.
    """
    assert_ok(run_setup(["--keybinds"], kb_sandbox))
    before = len(managed_sendsequences(load_keybindings(kb_sandbox.vscode)))
    assert before == 1

    assert_ok(run_setup(["--hooks", "--uninstall"], kb_sandbox))

    after = len(managed_sendsequences(load_keybindings(kb_sandbox.vscode)))
    assert after == before, "--hooks --uninstall 이 관리 키바인딩을 지웠다"
