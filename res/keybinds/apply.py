#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""줄바꿈 키바인딩을 VS Code / Cursor / Claude / Codex / WT / tmux 에 외과적으로 설치한다.

훅 병합(merge_and_diff.py)과 같은 철학: 합집합, 없을 때만 추가, 관리 항목만 되돌림.
settings.json 은 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

NEWLINE_SEQUENCE = "\u001b\r"
# 관리 바인딩 식별용. 설치는 NEWLINE_SEQUENCE 만 쓰지만, 이전 후보 시퀀스도 우리 것으로 본다.
SSOT_SEQUENCES = (
    "\u001b[13;2u",
    "\u001b\r",
    "\u001b[27;2;13~",
)
VALID_CHORDS = ("shift-enter", "ctrl-enter")
SEND_SEQUENCE_CMD = "workbench.action.terminal.sendSequence"
MANIFEST_NAME = ".claude-code-setup.json"

TMUX_EXTENDED_LINE = "set -s extended-keys on"
TMUX_EXTKEYS_LINE = "set -as terminal-features 'xterm*:extkeys'"

VSCODE_ENV = "CLAUDE_SETUP_VSCODE_KEYBINDINGS"
CURSOR_ENV = "CLAUDE_SETUP_CURSOR_KEYBINDINGS"
WT_ENV = "CLAUDE_SETUP_WT_SETTINGS"
DETECTED_TERM_ENV = "CLAUDE_SETUP_DETECTED_TERMINAL"


def vscode_key(chord: str) -> str:
    return "shift+enter" if chord == "shift-enter" else "ctrl+enter"


def vscode_other_key(chord: str) -> str:
    return "ctrl+enter" if chord == "shift-enter" else "shift+enter"


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
    stripped = strip_trailing_commas("".join(out)).strip()
    if not stripped:
        return []
    return json.loads(stripped)


def strip_trailing_commas(text: str) -> str:
    """VS Code 는 `[{...},]` 같은 트레일링 콤마를 정상으로 받아들인다.

    json.loads 는 거부하므로, 문자열 밖의 콤마 중 뒤따르는 것이 ] 또는 } 뿐인 것만 지운다.
    """
    out = []
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == chr(34):
                in_str = False
            continue
        if ch == chr(34):
            in_str = True
            out.append(ch)
            continue
        if ch == ",":
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] in "]}":
                continue
        out.append(ch)
    return "".join(out)


BACKUP_SUFFIX = ".bak."
TMP_SUFFIX = ".tmp-claude-code-setup"


def backup_file(path: Path) -> None:
    """바꾸기 전 원본을 .bak.<타임스탬프> 로 남긴다 (훅 설치와 같은 철학)."""
    if not path.is_file():
        return
    stamp = time.strftime("%Y%m%d%H%M%S")
    target = path.with_name(path.name + BACKUP_SUFFIX + stamp)
    n = 1
    while target.exists():
        target = path.with_name(path.name + BACKUP_SUFFIX + stamp + "-" + str(n))
        n += 1
    target.write_bytes(path.read_bytes())


def write_text_atomic(path: Path, text: str) -> None:
    """임시 파일에 쓰고 교체한다 — 쓰기 도중 끊겨도 원본이 반쯤 잘리지 않는다.

    바꾸기 전 백업을 남긴다. 사용자가 직접 관리하던 설정 파일이므로 되돌릴 수단이 있어야 한다.
    """
    # 내용이 같으면 아무것도 하지 않는다. 이 검사가 없으면 멱등 재실행마다 백업이 쌓인다.
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def write_json(path: Path, data) -> None:
    text = json.dumps(data, ensure_ascii=True, indent=4)
    write_text_atomic(path, text + "\n")


def resolve_home(cli_home: str | None) -> Path:
    if cli_home:
        return Path(cli_home)
    raw = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(raw)


def env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    return Path(value)


def is_windows() -> bool:
    return os.name == "nt" or sys.platform == "win32"


_UNSET = object()


def current_platform() -> str:
    return "win32" if is_windows() else sys.platform


def default_ide_path(home: Path, app: str, platform=_UNSET, appdata=_UNSET) -> Path:
    """VS Code/Cursor 사용자 keybindings.json 의 기본 경로.

    platform/appdata 를 인자로 받는다 — 테스트가 env 주입 없이 세 OS 를 단언할 수 있어야
    이 함수가 "실행되지 않는 죽은 코드" 가 되지 않는다.
    """
    plat = current_platform() if platform is _UNSET else platform
    data = os.environ.get("APPDATA") if appdata is _UNSET else appdata
    if plat == "win32" and data:
        return Path(data) / app / "User" / "keybindings.json"
    if plat == "darwin":
        # macOS 의 VS Code/Cursor 는 XDG 가 아니라 Application Support 를 쓴다.
        return home / "Library" / "Application Support" / app / "User" / "keybindings.json"
    return home / ".config" / app / "User" / "keybindings.json"


def default_vscode_path(home: Path, platform=_UNSET, appdata=_UNSET) -> Path:
    return default_ide_path(home, "Code", platform, appdata)


def default_cursor_path(home: Path, platform=_UNSET, appdata=_UNSET) -> Path:
    return default_ide_path(home, "Cursor", platform, appdata)


def default_wt_path() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    return (
        Path(local)
        / "Packages"
        / "Microsoft.WindowsTerminal_8wekyb3d8bbwe"
        / "LocalState"
        / "settings.json"
    )


def binary_on_path(name: str) -> bool:
    if shutil.which(name):
        return True
    if is_windows():
        for ext in (".exe", ".cmd", ".bat", ".ps1"):
            if shutil.which(name + ext):
                return True
    return False


def load_manifest(home: Path) -> dict:
    path = home / ".claude" / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_manifest(home: Path, data: dict) -> None:
    path = home / ".claude" / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + TMP_SUFFIX)
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


def merge_manifest_keybinds(home: Path, keybinds: dict) -> None:
    data = load_manifest(home)
    data["keybinds"] = keybinds
    write_manifest(home, data)


def strip_keybinds_from_manifest(home: Path) -> None:
    path = home / ".claude" / MANIFEST_NAME
    if not path.is_file():
        return
    data = load_manifest(home)
    if "keybinds" not in data:
        return
    data.pop("keybinds", None)
    write_manifest(home, data)


def invalid_newline_message(value: str) -> str:
    return (
        f"--newline 값은 shift-enter 또는 ctrl-enter 여야 합니다 "
        f"(받은 값: {value!s})."
    )


SKIPPED_TARGETS = []


def note_skipped(path, reason: str) -> None:
    """읽지 못해 건너뛴 대상. run() 이 마지막에 요약하고 종료 코드를 바꾼다."""
    SKIPPED_TARGETS.append((str(path), reason))
    print(f"  ⚠️ {reason}: {path}")


def desired_ide_binding(chord: str) -> dict:
    return {
        "key": vscode_key(chord),
        "command": SEND_SEQUENCE_CMD,
        "args": {"text": NEWLINE_SEQUENCE},
        "when": "terminalFocus",
    }


def sendsequence_text(entry: dict) -> str:
    args = entry.get("args") or {}
    if isinstance(args, dict):
        return args.get("text") or args.get("sequence") or ""
    return ""


def is_ssot_sequence(text: str) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if text in SSOT_SEQUENCES:
        return True
    try:
        decoded = text.encode("utf-8").decode("unicode_escape")
    except Exception:
        decoded = text
    return decoded in SSOT_SEQUENCES


def is_managed_sendsequence(entry) -> bool:
    """우리가 넣은 터미널 줄바꿈 sendSequence. 사용자 sendSequence(keep-me 등)는 제외."""
    if not isinstance(entry, dict):
        return False
    if entry.get("command") != SEND_SEQUENCE_CMD:
        return False
    when = str(entry.get("when") or "")
    if "terminalFocus" not in when:
        return False
    if re.search(r"editor|notebook", when, re.I):
        return False
    return is_ssot_sequence(sendsequence_text(entry))


def bindings_equivalent(entry: dict, desired: dict) -> bool:
    if str(entry.get("key") or "").lower().replace(" ", "") != desired["key"]:
        return False
    if entry.get("command") != desired["command"]:
        return False
    if str(entry.get("when") or "") != desired["when"]:
        return False
    return sendsequence_text(entry) == desired["args"]["text"]


def load_ide_entries(path: Path):
    if not path.is_file():
        return []
    try:
        data = parse_jsonc(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, list):
        return data
    return None


def apply_ide_keybindings(path: Path, chord: str, uninstall: bool, dry_run: bool) -> bool:
    """관리 sendSequence 하나를 넣거나 뺀다. 외래 항목은 보존. 변경했으면 True."""
    existed = path.is_file()
    entries = load_ide_entries(path)
    if entries is None:
        note_skipped(path, "keybindings.json 을 읽지 못해 건너뜁니다")
        return False

    desired = desired_ide_binding(chord)
    if uninstall:
        new_entries = [e for e in entries if not is_managed_sendsequence(e)]
        changed = new_entries != entries
        if dry_run:
            print(f"  {path} (keybindings.json) — 관리 sendSequence 제거")
            return False
        if changed:
            write_json(path, new_entries)
        return changed

    managed = [e for e in entries if is_managed_sendsequence(e)]
    foreign = [e for e in entries if not is_managed_sendsequence(e)]
    if len(managed) == 1 and bindings_equivalent(managed[0], desired):
        if dry_run:
            print(f"  {path} (keybindings.json) — 이미 {desired['key']}")
        return False
    new_entries = foreign + [desired]
    if dry_run:
        print(f"  {path} (keybindings.json) — {desired['key']} sendSequence")
        return False
    if not existed:
        path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, new_entries)
    return True


def apply_claude_keybindings(path: Path, chord: str, uninstall: bool, dry_run: bool,
                             prev_keys=None) -> list:
    """Chat 에 고른 키 → chat:newline. 다른 context/bindings 보존."""
    added = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            note_skipped(path, "Claude keybindings.json 을 읽지 못해 건너뜁니다")
            return []
        if not isinstance(data, dict):
            note_skipped(path, "Claude keybindings.json 최상위가 객체가 아니라 건너뜁니다")
            return []
    else:
        data = {}

    chat = data.get("Chat")
    if not isinstance(chat, dict):
        chat = {}
        data["Chat"] = chat

    if uninstall:
        changed = False
        for key in ("shift+enter", "ctrl+enter"):
            if chat.get(key) == "chat:newline":
                del chat[key]
                changed = True
        if dry_run:
            print(f"  {path} (Claude keybindings.json) — chat:newline 관리 키 제거")
            return []
        if changed:
            write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return []

    want = vscode_key(chord)
    other = vscode_other_key(chord)
    # 고르지 않은 수정 Enter 는 우리가 넣은 기록이 있을 때만 뺀다 (핵심 결정 5).
    # 기록이 없으면 사용자가 직접 넣은 것이므로 그대로 둔다.
    if other in set(prev_keys or []) and chat.get(other) == "chat:newline":
        del chat[other]
    chat[want] = "chat:newline"
    added = [want]
    if dry_run:
        print(f"  {path} (Claude keybindings.json) — Chat[{want}]=chat:newline")
        return added
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return added


def _parse_toml_str_list(src: str) -> list:
    src = src.strip()
    if src.startswith("#"):
        return []
    strings = re.findall(r'"([^"]*)"', src)
    if strings:
        return strings
    strings = re.findall(r"'([^']*)'", src)
    if strings:
        return strings
    return []


def split_toml_comment(line: str):
    """문자열 밖의 첫 # 앞뒤로 나눈다 — (코드, 주석). 주석에는 개행이 없다."""
    in_str = False
    quote = ""
    escape = False
    for i, ch in enumerate(line):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in (chr(34), chr(39)):
            in_str = True
            quote = ch
            continue
        if ch == "#":
            return line[:i], line[i:].rstrip("\r\n")
    return line, ""


def _consume_insert_newline(lines: list, start: int):
    """insert_newline = VALUE 를 읽어 (items, indent, next_index, 주석) 을 반환.

    주석을 먼저 떼어낸다 — 안 그러면 `# "alt-enter" 는 안 먹음` 같은 주석 속 문자열이
    항목으로 읽히고, 재작성할 때 주석이 통째로 사라진다.
    """
    line = lines[start]
    indent = re.match(r"^(\s*)", line).group(1)
    code, comment = split_toml_comment(line.split("=", 1)[1])
    buf = code
    i = start + 1
    while buf.count("[") > buf.count("]") and i < len(lines):
        code, tail = split_toml_comment(lines[i])
        buf += code
        if tail:
            comment = tail
        i += 1
    items = _parse_toml_str_list(buf)
    return items, indent, i, comment


def edit_codex_insert_newline(text: str, add_key: str | None, remove_keys) -> str:
    """[tui.keymap.editor] insert_newline 만 고친다. 다른 키/테이블은 그대로."""
    remove_keys = set(remove_keys or [])
    if not text.strip():
        if not add_key:
            return text
        return f'[tui.keymap.editor]\ninsert_newline = ["{add_key}"]\n'

    lines = text.splitlines(keepends=True)
    out = []
    i = 0
    in_editor = False
    found_insert = False

    def current_section(raw: str) -> str | None:
        stripped = raw.split("#", 1)[0].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return stripped
        return None

    def updated_items(items: list) -> list:
        kept = [x for x in items if x not in remove_keys]
        if add_key and add_key not in kept:
            kept.append(add_key)
        return kept

    def format_list(items: list, indent: str, comment: str = "") -> str:
        inner = ", ".join(f'"{x}"' for x in items)
        tail = ("  " + comment) if comment else ""
        return f"{indent}insert_newline = [{inner}]{tail}\n"

    while i < len(lines):
        line = lines[i]
        section = current_section(line)
        if section is not None:
            if in_editor and not found_insert:
                items = updated_items([])
                if add_key or items:
                    if out and not out[-1].endswith("\n"):
                        out[-1] += "\n"
                    out.append(format_list(items, ""))
                    found_insert = True
            in_editor = section == "[tui.keymap.editor]"
            out.append(line)
            i += 1
            continue
        if in_editor and re.match(r"^\s*insert_newline\s*=", line):
            items, indent, i, comment = _consume_insert_newline(lines, i)
            items = updated_items(items)
            # 빈 리스트를 남기면 "줄바꿈 전면 언바인드" 라는 새 설정을 만드는 것이다.
            # 우리 키만 빠지고 남은 게 없으면 줄 자체를 지운다 (원상 복구).
            if items or add_key:
                out.append(format_list(items, indent, comment))
            found_insert = True
            continue
        out.append(line)
        i += 1

    if in_editor and not found_insert:
        items = updated_items([])
        if add_key or items:
            # 파일이 개행 없이 끝나면 마지막 줄에 붙어버려 TOML 이 깨진다.
            if out and not out[-1].endswith("\n"):
                out[-1] += "\n"
            out.append(format_list(items, ""))
            found_insert = True

    if not found_insert and add_key:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        if out and out[-1].strip():
            out.append("\n")
        out.append("[tui.keymap.editor]\n")
        out.append(format_list([add_key], ""))

    return "".join(out)


def drop_empty_editor_table(text: str) -> str:
    """내용이 하나도 없는 [tui.keymap.editor] 헤더를 지운다.

    설치가 이 테이블을 새로 만들 수 있으므로, 제거 후 빈 껍데기를 남기면 원상 복구가 아니다.
    """
    lines = text.splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        head, _ = split_toml_comment(lines[i])
        if head.strip() == "[tui.keymap.editor]":
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            nxt = split_toml_comment(lines[j])[0].strip() if j < len(lines) else ""
            if j >= len(lines) or (nxt.startswith("[") and nxt.endswith("]")):
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def apply_codex_toml(path: Path, chord: str, uninstall: bool, dry_run: bool,
                     prev_keys=None) -> list:
    existed = path.is_file()
    text = path.read_text(encoding="utf-8") if existed else ""
    if uninstall:
        new_text = drop_empty_editor_table(
            edit_codex_insert_newline(text, None, {"shift-enter", "ctrl-enter"})
        )
        if dry_run:
            print(f"  {path} (codex config.toml) — insert_newline 관리 키 제거")
            return []
        if new_text != text and existed:
            write_text_atomic(path, new_text)
        return []

    # 고르지 않은 코드는 우리가 넣은 기록이 있을 때만 뺀다 (핵심 결정 5).
    other = vscode_other_codex(chord)
    remove = {other} if other in set(prev_keys or []) else set()
    new_text = edit_codex_insert_newline(text, chord, remove)
    if dry_run:
        print(f"  {path} (codex config.toml) — insert_newline += {chord}")
        return [chord]
    if new_text != text or not existed:
        write_text_atomic(path, new_text)
    return [chord]


def vscode_other_codex(chord: str) -> str:
    return "ctrl-enter" if chord == "shift-enter" else "shift-enter"


def _wt_keys(item: dict) -> str:
    keys = item.get("keys") or item.get("key") or ""
    if isinstance(keys, list):
        keys = " ".join(str(k) for k in keys)
    return str(keys or "").lower().replace(" ", "")


def is_wt_send(item) -> bool:
    if not isinstance(item, dict):
        return False
    cmd = item.get("command")
    if isinstance(cmd, dict):
        action = str(cmd.get("action") or "").lower()
        return action in ("sendinput", "send")
    if isinstance(cmd, str):
        return cmd.lower() in ("sendinput", "send")
    return False


def _wt_input(item) -> str:
    cmd = item.get("command")
    if isinstance(cmd, dict):
        return str(cmd.get("input") or cmd.get("sequence") or "")
    return ""


def is_managed_wt(item) -> bool:
    """키만 보면 사용자가 같은 키에 걸어둔 남의 sendInput 까지 지운다.

    VS Code 판정(is_managed_sendsequence)과 같이 시퀀스까지 봐야 우리 것이다.
    """
    if not is_wt_send(item):
        return False
    keys = _wt_keys(item)
    if keys not in ("shift+enter", "ctrl+enter", "shift+return", "ctrl+return"):
        return False
    return is_ssot_sequence(_wt_input(item))


def apply_wt_settings(path: Path | None, chord: str, uninstall: bool, dry_run: bool) -> bool:
    """대상 파일이 없으면 skip. Shift+Enter 선택 시 shift+enter sendInput 을 넣지 않는다."""
    if path is None or not path.is_file():
        if dry_run:
            print("  Windows Terminal settings.json — 대상 없음, skip")
        return False
    try:
        data = parse_jsonc(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        note_skipped(path, "WT settings.json 을 읽지 못해 건너뜁니다")
        return False
    if not isinstance(data, dict):
        note_skipped(path, "WT settings.json 최상위가 객체가 아니라 건너뜁니다")
        return False

    actions_key = "actions" if "actions" in data else ("keybindings" if "keybindings" in data else "actions")
    actions = list(data.get(actions_key) or [])
    kept = [a for a in actions if not is_managed_wt(a)]
    managed = False

    if not uninstall and chord == "ctrl-enter":
        kept.append({
            "command": {"action": "sendInput", "input": NEWLINE_SEQUENCE},
            "keys": "ctrl+enter",
        })
        managed = True

    if dry_run:
        print(f"  {path} (Windows Terminal settings.json)")
        return False

    if kept != actions:
        data[actions_key] = kept
        write_json(path, data)
        return managed or True
    return False


def apply_tmux(path: Path, uninstall: bool, dry_run: bool, previously_added) -> list:
    """POSIX 전용. 없을 때만 extended-keys / extkeys 를 붙인다. 우리가 넣은 줄만 지운다."""
    if is_windows():
        return []
    existed = path.is_file()
    text = path.read_text(encoding="utf-8") if existed else ""
    added = list(previously_added or [])

    if uninstall:
        if not existed:
            return []
        # 영수증에 없으면 우리가 넣은 줄이 아니다. extended-keys 는 사용자가 직접 쓰는
        # 흔한 설정이라, 기록 없이 문자열만 같다고 지우면 남의 설정을 지운다.
        remove = set(added)
        if not remove:
            if dry_run:
                print(f"  {path} (tmux.conf) — 우리가 넣은 줄 기록이 없어 건드리지 않습니다")
            return []
        new_lines = []
        for line in text.splitlines(True):
            stripped = line.rstrip("\r\n")
            if stripped in remove:
                continue
            new_lines.append(line)
        new_text = "".join(new_lines)
        if dry_run:
            print(f"  {path} (tmux.conf) — 설치가 넣은 extended-keys 줄 제거")
            return []
        if new_text != text:
            write_text_atomic(path, new_text)
        return []

    to_add = []
    if "extended-keys" not in text:
        to_add.append(TMUX_EXTENDED_LINE)
    if "extkeys" not in text:
        to_add.append(TMUX_EXTKEYS_LINE)
    if dry_run:
        print(f"  {path} (tmux.conf)")
        return to_add
    if not to_add:
        return []
    new_text = text
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    new_text += "\n".join(to_add) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return to_add


def detect_terminal() -> str:
    """불가 터미널(Shift+Enter 를 Enter 와 구분하지 못하는 터미널) 이름.

    테스트는 CLAUDE_SETUP_DETECTED_TERMINAL 로 주입한다 (실제 gnome-terminal 없이 검증하려고).
    실사용에서는 터미널 에뮬레이터가 스스로 남기는 환경변수로 판단한다 — 주입이 없을 때만.
    """
    injected = (os.environ.get(DETECTED_TERM_ENV) or "").strip().lower()
    if injected:
        return injected
    env = os.environ
    if env.get("KONSOLE_VERSION") or env.get("KONSOLE_DBUS_SESSION"):
        return "konsole"
    if env.get("GNOME_TERMINAL_SERVICE") or env.get("GNOME_TERMINAL_SCREEN"):
        return "gnome-terminal"
    return ""


def print_warnings() -> None:
    detected = detect_terminal()
    if detected in ("gnome-terminal", "konsole"):
        print(
            "⚠️ 이 터미널은 Shift+Enter 를 구분하지 못합니다. "
            "Linux 완료 기준은 SSH 또는 외부 터미널 경로입니다."
        )
    print(
        "⚠️ Grok /multiline 이 켜지면 Enter 와 Shift+Enter 의미가 반대입니다. "
        "설치기는 그 토글을 바꾸지 않습니다."
    )


def resolve_chord(explicit: str | None, manifest: dict) -> str:
    if explicit:
        return explicit
    kb = manifest.get("keybinds") if isinstance(manifest.get("keybinds"), dict) else {}
    previous = kb.get("newline_chord") if isinstance(kb, dict) else None
    if previous in VALID_CHORDS:
        return previous
    return "shift-enter"


def should_apply_agent(name: str, config_dir: Path) -> bool:
    return binary_on_path(name) or config_dir.is_dir()


def report_result(done_message: str) -> int:
    """건너뛴 대상이 있으면 성공이라고 말하지 않는다.

    파일을 읽지 못해 건너뛴 것은 "에이전트가 없어서 skip"(핵심 결정 9)과 다르다 —
    사용자는 줄바꿈 키가 적용된 줄 알지만 실제로는 아무것도 설치되지 않았다.
    """
    if not SKIPPED_TARGETS:
        print("✅ " + done_message)
        return 0
    print("⚠️ 아래 대상은 파일을 읽지 못해 건너뛰었습니다 — 줄바꿈 키가 적용되지 않았습니다:")
    for target, reason in SKIPPED_TARGETS:
        print(f"  - {target} ({reason})")
    print("   JSON 문법을 고친 뒤 다시 실행하세요. 나머지 대상은 처리했습니다.")
    return 1


def run(args) -> int:
    home = resolve_home(args.home)
    explicit = args.newline
    if explicit is not None and explicit not in VALID_CHORDS:
        print(invalid_newline_message(explicit), file=sys.stderr)
        return 1

    vscode_path = env_path(VSCODE_ENV) or default_vscode_path(home)
    cursor_path = env_path(CURSOR_ENV) or default_cursor_path(home)
    wt_override = WT_ENV in os.environ
    if wt_override:
        wt_path = env_path(WT_ENV)
    else:
        wt_path = default_wt_path()

    claude_dir = home / ".claude"
    codex_dir = home / ".codex"
    # 매니페스트용 .claude 를 만들기 전에 스킵 여부를 고정한다.
    claude_apply = should_apply_agent("claude", claude_dir)
    codex_apply = should_apply_agent("codex", codex_dir)
    claude_kb = claude_dir / "keybindings.json"
    codex_toml = codex_dir / "config.toml"
    tmux_conf = home / ".tmux.conf"

    manifest = load_manifest(home)
    prev_kb = manifest.get("keybinds") if isinstance(manifest.get("keybinds"), dict) else {}

    if args.uninstall:
        print("🧹 줄바꿈 키바인딩 제거 (관리 항목만)...")
        if args.dry_run:
            print("  🧪 DRY RUN — 실제 파일은 전혀 제거되지 않습니다.")
        apply_ide_keybindings(vscode_path, "shift-enter", True, args.dry_run)
        apply_ide_keybindings(cursor_path, "shift-enter", True, args.dry_run)
        if claude_kb.is_file() or claude_apply:
            apply_claude_keybindings(claude_kb, "shift-enter", True, args.dry_run,
                                     prev_kb.get("claude_keys_added"))
        if codex_toml.is_file() or codex_apply:
            apply_codex_toml(codex_toml, "shift-enter", True, args.dry_run,
                             prev_kb.get("codex_keys_added"))
        apply_wt_settings(wt_path, "shift-enter", True, args.dry_run)
        apply_tmux(tmux_conf, True, args.dry_run, prev_kb.get("tmux_added"))
        if not args.dry_run:
            strip_keybinds_from_manifest(home)
        return report_result("키바인딩 제거 완료 — 사용자 원래 항목은 보존했습니다.")

    chord = resolve_chord(explicit, manifest)
    print(f"🔧 줄바꿈 키바인딩 설치 ({chord})...")
    if args.dry_run:
        print("  🧪 DRY RUN — 실제 파일은 전혀 변경되지 않습니다.")
        print(f"  계획: VS Code {vscode_path} (keybindings.json)")
        print(f"  계획: Cursor {cursor_path} (keybindings.json)")
        print(f"  계획: Claude {claude_kb} (keybindings.json)")
        print(f"  계획: Codex {codex_toml} (config.toml)")
        if wt_path:
            print(f"  계획: Windows Terminal {wt_path} (settings.json)")
        if not is_windows():
            print(f"  계획: tmux {tmux_conf}")

    print_warnings()

    vscode_managed = apply_ide_keybindings(vscode_path, chord, False, args.dry_run)
    cursor_managed = apply_ide_keybindings(cursor_path, chord, False, args.dry_run)

    claude_keys = []
    if claude_apply:
        claude_keys = apply_claude_keybindings(claude_kb, chord, False, args.dry_run,
                                              prev_kb.get("claude_keys_added"))

    codex_keys = []
    if codex_apply:
        codex_keys = apply_codex_toml(codex_toml, chord, False, args.dry_run,
                                      prev_kb.get("codex_keys_added"))

    wt_managed = apply_wt_settings(wt_path, chord, False, args.dry_run)
    tmux_added = apply_tmux(tmux_conf, False, args.dry_run, prev_kb.get("tmux_added"))
    if not tmux_added and isinstance(prev_kb.get("tmux_added"), list) and not args.uninstall:
        # 이미 있는 줄은 다시 안 넣지만, 이전에 우리가 넣은 기록은 유지한다 (uninstall 근거).
        if not args.dry_run and "extended-keys" in (
            tmux_conf.read_text(encoding="utf-8") if tmux_conf.is_file() else ""
        ):
            tmux_added = list(prev_kb.get("tmux_added") or [])

    if args.dry_run:
        print("🧪 DRY RUN 완료 — keybindings.json / Codex config.toml 을 쓰지 않았습니다.")
        return 0

    merge_manifest_keybinds(home, {
        "newline_chord": chord,
        "vscode_managed": bool(vscode_managed) or bool(prev_kb.get("vscode_managed")),
        "cursor_managed": bool(cursor_managed) or bool(prev_kb.get("cursor_managed")),
        "wt_managed": (bool(wt_managed) or bool(prev_kb.get("wt_managed")))
        if chord == "ctrl-enter" else False,
        "tmux_added": tmux_added if tmux_added else list(prev_kb.get("tmux_added") or []),
        "claude_keys_added": claude_keys,
        "codex_keys_added": codex_keys,
    })
    return report_result("줄바꿈 키바인딩 설치 완료.")


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--newline", default=None)
    parser.add_argument("--home", default=None)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
