#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, Bash 툴 대상, 유저 레벨, macOS/Linux)

정책:
  1) rm → trash-put 치환 (allow + updatedInput)
     단, 루트 경로(/, ~, $HOME, 와일드카드 포함) 삭제 시도는 즉시 deny.
     trash-put 이 없으면 치환할 수 없으므로 fail-closed 로 deny.
     멀티라인 또는 체이닝(&&/;) 스크립트 안에 섞여 있으면 자동 치환 대신 deny.
  2) git push / git push --force / git reset --hard / git clean -f* / git stash drop|clear → deny
     git branch -D / git checkout -- <path> / git restore → ask (되돌릴 수 없는 변경 손실 가능성)
  3) dd of=... / mkfs* / wipefs / diskutil eraseDisk|eraseVolume / fdisk / parted → deny
     /dev/sd* 등 블록 디바이스로의 리다이렉트, 포크밤 패턴 → deny
  4) curl|bash, wget -O- | sh 같은 "원격 스크립트를 바로 셸로 파이프 실행" 패턴 → deny
  5) shutdown / reboot / halt / poweroff → ask ; chmod 777 / shred → ask
  6) sudo 접두어는 벗겨서 실제 명령을 위 규칙으로 검사한다.
  7) bash/sh -c "inner" 패턴: 내부 명령을 추출해 동일 규칙으로 추가 검사한다.

Bash 툴은 여러 줄짜리 스크립트를 통째로 하나의 command 문자열로 보낸다. shlex.split을
전체 문자열에 한 번만 적용하면 (a) 파이프 뒤 검사가 전혀 무관한 다음 줄까지 새어 들어가
오탐이 나거나 (b) 위험한 명령이 첫 줄이 아니면 검사 자체가 안 되는 미탐이 생긴다. 그래서
command를 줄 단위로 나눠 각 줄을 독립적으로 검사한다. 또한 같은 줄 안의 &&/||/; 체이닝도
토큰 수준에서 분리해 각 서브커맨드를 독립적으로 검사한다.

모든 판단은 hookSpecificOutput.permissionDecision(allow|deny|ask) 방식으로 반환하고,
~/.claude/hooks/guard.log 에 감사 로그를 남긴다. 이 훅은 유저 레벨에 설치되므로
이 사용자가 여는 모든 프로젝트에 적용된다.
"""
import sys
import json
import shutil
import shlex
import re
import os
import datetime

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HOOKS_DIR, "guard.log")

ROOT_RE = re.compile(r'^(/(\*)?|~(/\*?)?|\$HOME(/\*?)?)$')

REMOTE_EXEC_TOKENS = {"bash", "sh", "zsh", "dash"}
DISK_COMMANDS = {"mkfs", "mkfs.ext4", "mkfs.xfs", "mkfs.vfat", "fdisk", "parted", "wipefs"}

# shlex 로 파싱되지 않는(또는 파싱 전에 잡아야 하는) 원시 문자열 패턴.
FORK_BOMB_RE = re.compile(r'\(\s*\)\s*\{[^}]*\|[^}]*&')  # :(){ :|:& };:
DEVICE_REDIRECT_RE = re.compile(r'>\s*/dev/(sd|nvme|hd|disk|mmcblk|vd)[a-z0-9]*', re.IGNORECASE)


def log(entry: dict) -> None:
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        first_write = not os.path.exists(LOG_PATH)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            if first_write:
                try:
                    os.chmod(LOG_PATH, 0o600)
                except OSError:
                    pass
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def emit(decision: str, reason: str, updated_input: dict | None = None) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    if updated_input is not None:
        payload["hookSpecificOutput"]["permissionDecision"] = "allow"
        payload["hookSpecificOutput"]["updatedInput"] = updated_input
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def split_commands(parts: list) -> list:
    """shlex 토큰 목록을 &&, ||, ; 기준으로 서브커맨드 리스트로 분리한다."""
    commands: list = []
    current: list = []
    for token in parts:
        if token in ("&&", "||", ";"):
            if current:
                commands.append(current)
            current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    return commands if commands else [parts]


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    original_lines = [ln for ln in command.splitlines() if ln.strip()]
    is_multiline = len(original_lines) > 1
    # 처리 큐: 원본 라인 + bash/sh -c 로 발견된 내부 명령이 추가된다.
    lines = list(original_lines)

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        stripped = line.strip()
        # shlex 파싱 전에 원시 문자열로 잡아야 하는 패턴들.
        if FORK_BOMB_RE.search(stripped):
            log({"command": command, "decision": "deny-fork-bomb"})
            emit("deny", "포크밤(fork bomb)으로 보이는 패턴이 감지되어 차단합니다.")
        if DEVICE_REDIRECT_RE.search(stripped):
            log({"command": command, "decision": "deny-device-redirect"})
            emit("deny", "블록 디바이스(/dev/sd* 등)로의 출력 리다이렉트는 디스크를 파괴할 수 있어 차단합니다.")

        try:
            parts = shlex.split(line)
        except ValueError:
            log({"line": line, "decision": "pass-unparsed"})
            continue

        if not parts:
            continue

        sub_commands = split_commands(parts)
        is_chained = len(sub_commands) > 1

        for cmd_parts in sub_commands:
            if not cmd_parts:
                continue

            base = os.path.basename(cmd_parts[0])
            args = cmd_parts[1:]

            # sudo 접두어는 벗겨서 실제 명령을 검사한다 (sudo rm -rf / 가 우회되지 않도록).
            if base == "sudo" and args and not args[0].startswith("-"):
                base = os.path.basename(args[0])
                args = args[1:]

            # bash/sh -c "inner" 패턴: 내부 명령을 처리 큐에 추가해 동일 규칙으로 검사한다
            # (예: sudo bash -c "rm -rf /" 우회 차단).
            if base in REMOTE_EXEC_TOKENS and "-c" in args:
                c_idx = args.index("-c")
                if c_idx + 1 < len(args):
                    lines.append(args[c_idx + 1])

            if base == "rm":
                clean_args = [p for p in args if not p.startswith("-")]

                if not clean_args:
                    emit("deny", "삭제 대상 파일이 지정되지 않았습니다.")

                for a in clean_args:
                    if ROOT_RE.match(a.strip()):
                        log({"command": command, "decision": "deny-root-delete"})
                        emit("deny", f"루트/홈 디렉터리 전체({a})를 삭제하려는 시도는 차단됩니다.")

                if is_multiline or is_chained:
                    emit("deny", "여러 줄 또는 체이닝된 명령 안에 삭제 명령이 섞여 있어 안전하게 자동 치환할 수 없습니다. 삭제 명령은 단독으로 실행하세요.")

                if not shutil.which("trash-put"):
                    emit("deny", "trash-put 이 설치되어 있지 않아 삭제를 차단합니다. (pip install trash-cli)")

                new_command = "trash-put " + " ".join(shlex.quote(a) for a in clean_args)
                log({"command": command, "decision": "redirect-to-trash", "new_command": new_command})
                emit("allow", "rm → trash-put 치환 (휴지통으로 안전하게 이동)",
                     updated_input={"command": new_command})

            if base == "git":
                if "push" in args and any(f in args for f in ("--force", "-f", "--force-with-lease")):
                    emit("deny", "git push --force 류는 원격 히스토리를 파괴할 수 있어 수동 실행이 필요합니다.")
                if "push" in args:
                    emit("deny", "git push는 수동으로 실행하세요.")
                if "reset" in args and "--hard" in args:
                    emit("deny", "git reset --hard는 커밋되지 않은 변경사항을 되돌릴 수 없이 삭제합니다. (stash/soft 권장)")
                if "clean" in args and any(f in args for f in ("-f", "-fd", "-fx", "-fdx", "-xdf", "--force")):
                    emit("deny", "git clean -f 류는 추적되지 않는 파일을 되돌릴 수 없이 삭제합니다.")
                if "stash" in args and any(a in args for a in ("drop", "clear")):
                    emit("deny", "git stash drop/clear 는 스태시를 되돌릴 수 없이 삭제합니다.")
                if "branch" in args and "-D" in args:
                    emit("ask", "git branch -D 는 병합되지 않은 브랜치를 강제 삭제합니다 (reflog 로만 복구 가능). 계속할까요?")
                if ("checkout" in args and "--" in args) or "restore" in args:
                    emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")

            if base in DISK_COMMANDS:
                emit("deny", f"디스크 레벨 명령({base})은 되돌릴 수 없어 자동 실행을 차단합니다.")
            if base == "dd" and any(a.startswith("of=") for a in args):
                emit("deny", "dd of=... 는 대상 장치/파일을 덮어쓸 수 있어 차단합니다.")
            if base == "diskutil" and args and args[0] in ("eraseDisk", "eraseVolume", "reformat"):
                emit("deny", f"diskutil {args[0]} 은 되돌릴 수 없어 자동 실행을 차단합니다.")
            if base == "chmod" and any(a in ("777", "0777", "a+rwx", "a=rwx") for a in args):
                emit("ask", "chmod 777 류는 모든 사용자에게 전체 권한을 부여합니다 (보안 위험). 계속할까요?")
            if base == "shred":
                emit("ask", "shred 는 파일을 복구 불가능하게 덮어씁니다. 계속할까요?")

            # 파이프 체크: &&/; 분리 후 서브커맨드 단위로 검사한다.
            if "|" in cmd_parts:
                idx = cmd_parts.index("|")
                downstream = cmd_parts[idx + 1:]
                if downstream and os.path.basename(downstream[0]) in REMOTE_EXEC_TOKENS:
                    emit("deny", "원격/외부 출력을 바로 셸에 파이프 실행하는 패턴입니다. 스크립트를 먼저 저장해 검토한 뒤 실행하세요.")

            if base in {"shutdown", "reboot", "halt", "poweroff"}:
                emit("ask", f"'{base}' 는 시스템을 종료/재시작합니다. 계속할까요?")

    sys.exit(0)


if __name__ == "__main__":
    main()
