#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, Bash 툴 대상, 유저 레벨, macOS/Linux)

정책:
  1) rm → trash-put 치환 (allow + updatedInput)
     단, 루트 경로(/, ~, $HOME, 와일드카드 포함) 삭제 시도는 즉시 deny.
     trash-put 이 없으면 치환할 수 없으므로 fail-closed 로 deny.
     멀티라인 스크립트 안에 섞여 있으면(아래 참고) 자동 치환 대신 deny.
  2) git push / git push --force / git reset --hard / git clean -f* → deny (수동 실행 요구)
     git checkout -- <path> / git restore → ask (되돌릴 수 없는 변경 손실 가능성)
  3) dd of=... / mkfs* / diskutil eraseDisk|eraseVolume / fdisk / parted → deny
  4) curl|bash, wget -O- | sh 같은 "원격 스크립트를 바로 셸로 파이프 실행" 패턴 → deny
  5) shutdown / reboot / halt / poweroff → ask

Bash 툴은 여러 줄짜리 스크립트를 통째로 하나의 command 문자열로 보낸다. shlex.split을
전체 문자열에 한 번만 적용하면 (a) 파이프 뒤 검사가 전혀 무관한 다음 줄까지 새어 들어가
오탐이 나거나 (b) 위험한 명령이 첫 줄이 아니면 검사 자체가 안 되는 미탐이 생긴다. 그래서
command를 줄 단위로 나눠 각 줄을 독립적으로 검사한다 (알려진 한계: 같은 줄 안에서
`&&`/`;` 로 이어붙인 다중 명령까지는 분리하지 않는다 — 완전한 셸 문법 파서가 필요해
이 휴리스틱 훅의 범위를 벗어난다).

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
DISK_COMMANDS = {"mkfs", "mkfs.ext4", "mkfs.xfs", "mkfs.vfat", "fdisk", "parted"}


def log(entry: dict) -> None:
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
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

    lines = [ln for ln in command.splitlines() if ln.strip()]
    is_multiline = len(lines) > 1

    for line in lines:
        try:
            parts = shlex.split(line)
        except ValueError:
            log({"line": line, "decision": "pass-unparsed"})
            continue

        if not parts:
            continue

        base = os.path.basename(parts[0])
        args = parts[1:]

        if base == "rm":
            clean_args = [p for p in args if not p.startswith("-")]

            if not clean_args:
                emit("deny", "삭제 대상 파일이 지정되지 않았습니다.")

            for a in clean_args:
                if ROOT_RE.match(a.strip()):
                    log({"command": command, "decision": "deny-root-delete"})
                    emit("deny", f"루트/홈 디렉터리 전체({a})를 삭제하려는 시도는 차단됩니다.")

            if is_multiline:
                emit("deny", "여러 줄 스크립트 안에 삭제 명령이 섞여 있어 안전하게 자동 치환할 수 없습니다. 삭제 명령은 단독으로 실행하세요.")

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
            if ("checkout" in args and "--" in args) or "restore" in args:
                emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")

        if base in DISK_COMMANDS:
            emit("deny", f"디스크 레벨 명령({base})은 되돌릴 수 없어 자동 실행을 차단합니다.")
        if base == "dd" and any(a.startswith("of=") for a in args):
            emit("deny", "dd of=... 는 대상 장치/파일을 덮어쓸 수 있어 차단합니다.")
        if base == "diskutil" and args and args[0] in ("eraseDisk", "eraseVolume", "reformat"):
            emit("deny", f"diskutil {args[0]} 은 되돌릴 수 없어 자동 실행을 차단합니다.")

        if "|" in parts:
            idx = parts.index("|")
            downstream = parts[idx + 1:]
            if downstream and os.path.basename(downstream[0]) in REMOTE_EXEC_TOKENS:
                emit("deny", "원격/외부 출력을 바로 셸에 파이프 실행하는 패턴입니다. 스크립트를 먼저 저장해 검토한 뒤 실행하세요.")

        if base in {"shutdown", "reboot", "halt", "poweroff"}:
            emit("ask", f"'{base}' 는 시스템을 종료/재시작합니다. 계속할까요?")

    sys.exit(0)


if __name__ == "__main__":
    main()
