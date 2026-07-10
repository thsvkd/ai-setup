#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, 유저 레벨, Windows)

Bash 툴(Git Bash)과 PowerShell 툴(네이티브, Git for Windows 미설치 시 기본으로 쓰임)
양쪽 모두를 대상으로 한다. 둘 다 tool_input.command 에 실행할 명령 문자열을 담는다.

정책:
  1) rm / del / erase / Remove-Item / rd / rmdir  → send_to_trash.py 로 치환 (allow + updatedInput)
     단, 드라이브 루트(C 드라이브 전체, / 또는 ~) 삭제 시도는 치환하지 않고 즉시 deny.
     send2trash 가 설치되어 있지 않으면 치환할 수 없으므로 fail-closed 로 deny.
     멀티라인 또는 체이닝(&&/;) 스크립트 안에 섞여 있으면 자동 치환 대신 deny.
  2) git push / git push --force / git reset --hard / git clean -f* / git stash drop|clear → deny
     git branch -D / git checkout -- <path> / git restore → ask (되돌릴 수 없는 변경 손실 가능성)
  3) format / diskpart / mkfs / fdisk / Clear-Disk / Format-Volume / dd of=... → deny (디스크 레벨 파괴적)
     Clear-Content / reg delete / chmod 777 → ask
  4) curl|bash, irm ... | iex 같은 "원격 스크립트를 바로 실행 셸로 파이프" 패턴 → deny
  5) shutdown / Restart-Computer / Stop-Computer → ask
  6) bash/sh -c "inner" 패턴: 내부 명령을 추출해 동일 규칙으로 추가 검사한다.

Bash 툴은 여러 줄짜리 스크립트를 통째로 하나의 command 문자열로 보낸다. shlex.split을
전체 문자열에 한 번만 적용하면 (a) 파이프 뒤 검사가 전혀 무관한 다음 줄까지 새어 들어가
오탐이 나거나 (b) 위험한 명령이 첫 줄이 아니면 검사 자체가 안 되는 미탐이 생긴다. 그래서
command를 줄 단위로 나눠 각 줄을 독립적으로 검사한다. 또한 같은 줄 안의 &&/||/; 체이닝도
토큰 수준에서 분리해 각 서브커맨드를 독립적으로 검사한다.

모든 판단은 hookSpecificOutput.permissionDecision(allow|deny|ask) 방식으로 반환하고,
guard.log 에 감사 로그를 남긴다. 이 훅은 유저 레벨에 설치되므로 이 사용자가 여는
모든 프로젝트에 적용된다.
"""
from __future__ import annotations

import sys
import json
import shlex
import re
import os
import datetime

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HOOKS_DIR, "guard.log")
SEND_TO_TRASH = os.path.join(HOOKS_DIR, "send_to_trash.py")


def send2trash_available() -> bool:
    """send_to_trash.py 파일 존재만으로는 부족하다 — 그 파일이 실제로 삭제를 수행하려면
    send2trash 패키지가 임포트돼야 한다. 패키지가 없으면 send_to_trash.py 는 실행 시점에
    BLOCKED 로 종료해 파일은 안전하지만, 그 사이 Claude Code 에게는 'allow'로 보고돼
    POSIX 쪽(fail-closed)과 정책이 어긋난다. 여기서 미리 확인해 deny 로 통일한다."""
    try:
        import send2trash  # noqa: F401
        return True
    except ImportError:
        return False

DELETE_COMMANDS = {"rm", "del", "erase", "remove-item", "ri", "rd", "rmdir"}
WINDOWS_FLAG_STYLE = {"del", "erase", "rd", "rmdir"}  # 이 명령들은 /flag 사용 (rm/Remove-Item 은 -flag)

# 드라이브/홈 루트 삭제. 와일드카드 변형과 홈을 가리키는 환경변수 표기까지 포함해야 한다 —
# `C:\` 를 막으면서 `C:\*` 를 흘려보내면 막은 의미가 없다. Bash 툴(Git Bash)도 이 훅을 쓰므로
# POSIX 표기(`/`, `/*`, `~/*`, `$HOME`)도 함께 본다.
ROOT_RE = re.compile(
    r'^('
    r'[a-zA-Z]:[\\/]*(\*(\.\*)?)?'          # C:   C:\   C:/   C:\*   C:\*.*
    r'|[\\/]+\*?'                            # /    \     /*    \*
    r'|~[\\/]*\*?'                           # ~    ~\    ~/    ~\*   ~/*
    r'|\$HOME([\\/]\*?)?'                    # $HOME  $HOME/  $HOME/*
    r'|\$env:USERPROFILE([\\/]\*?)?'
    r'|\$env:HOMEPATH([\\/]\*?)?'
    r'|%USERPROFILE%([\\/]\*?)?'
    r'|%HOMEPATH%([\\/]\*?)?'
    r')$',
    re.IGNORECASE,
)

REMOTE_EXEC_TOKENS = {"bash", "sh", "zsh", "iex", "invoke-expression", "powershell", "pwsh"}

# `irm http://x|iex` 처럼 파이프 앞뒤에 공백이 없으면 shlex 가 `http://x|iex` 를 한 토큰으로
# 묶어 토큰 기반 검사를 그대로 빠져나간다. 원시 문자열에서 한 번 더 잡는다.
# (?<!\|)\|(?!\|) 는 PowerShell/셸의 OR 연산자 `||` 를 제외하기 위한 것.
PIPE_TO_SHELL_RE = re.compile(
    r'(?<!\|)\|(?!\|)\s*(?:sudo\s+)?(?:[^\s|]*[\\/])?'
    r'(?:' + "|".join(sorted(REMOTE_EXEC_TOKENS, key=len, reverse=True)) + r')(?:\.exe)?\b',
    re.IGNORECASE,
)
# 따옴표 안의 문자열은 실행되는 명령이 아니므로 위 파이프 검사에서 제외한다
# (예: Select-String -Pattern "x|iex" 가 오탐으로 차단되지 않도록).
QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')


def log(entry: dict) -> None:
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        first_write = not os.path.exists(LOG_PATH)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            if first_write:
                try:
                    os.chmod(LOG_PATH, 0o600)
                    username = os.getenv("USERNAME") or os.getenv("USER", "")
                    if username:
                        import subprocess
                        subprocess.run(
                            ["icacls", LOG_PATH, "/inheritance:r", "/grant:r", f"{username}:F"],
                            capture_output=True,
                        )
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


def quote_bash(arg: str) -> str:
    return shlex.quote(arg)


def quote_ps(arg: str) -> str:
    return "'" + arg.replace("'", "''") + "'"


def strip_ps_quotes(token: str) -> str:
    # shlex.split(posix=False) (PowerShell 경로에서 사용, 백슬래시 경로를 보존하기 위해
    # posix=True 대신 이걸 씀) 는 따옴표 문자를 토큰에서 벗겨내지 않고 그대로 남긴다.
    # 이걸 벗겨두지 않으면 (a) send_to_trash.py 로 넘어가는 경로에 리터럴 따옴표가
    # 섞여 들어가 실패하고, (b) 드라이브 루트 삭제 탐지(ROOT_RE)가 따옴표 붙은
    # 토큰에는 매칭되지 않아 우회될 수 있다.
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        return token[1:-1]
    return token


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


def _checkout_restore_paths(args: list, lower_args: list) -> list:
    """git checkout/restore 명령에서 되돌림 대상 pathspec 토큰을 뽑아낸다.
    키워드 판별은 lower_args(소문자), 실제 경로 토큰은 args(원본 대소문자)로 다룬다.
    - checkout: "--" 뒤의 모든 토큰이 경로다.
    - restore: "restore" 서브커맨드와 "-" 로 시작하는 옵션, 그리고 값이 분리된
      옵션(-s <ref> 등)의 값 토큰까지 제외한 나머지 토큰이 경로다.
    """
    if "checkout" in lower_args and "--" in args:
        idx = args.index("--")
        return [a for a in args[idx + 1:] if a]
    if "restore" in lower_args:
        # -s/--source, --conflict, --pathspec-from-file 은 다음 토큰을 값으로 소비한다
        # (--source=<ref> 처럼 '='로 붙는 형태는 '-'로 시작하므로 이미 걸러진다).
        value_opts = {"-s", "--source", "--conflict", "--pathspec-from-file"}
        paths = []
        skip_next = False
        for a, la in zip(args, lower_args):
            if skip_next:
                skip_next = False
                continue
            if la == "restore":
                continue
            if la in value_opts:
                skip_next = True
                continue
            if a.startswith("-"):
                continue
            paths.append(a)
        return paths
    return []


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    is_bash = tool_name == "Bash"
    original_lines = [ln for ln in command.splitlines() if ln.strip()]
    is_multiline = len(original_lines) > 1
    # 처리 큐: 원본 라인 + bash/sh -c 로 발견된 내부 명령이 추가된다.
    lines = list(original_lines)

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        # shlex 파싱 전에 원시 문자열로 잡아야 하는 패턴 (공백 없는 파이프).
        if PIPE_TO_SHELL_RE.search(QUOTED_RE.sub(" ", line)):
            log({"tool": tool_name, "command": command, "decision": "deny-pipe-to-shell"})
            emit("deny", "원격/외부 출력을 바로 셸에 파이프 실행하는 패턴입니다. 스크립트를 먼저 저장해 검토한 뒤 실행하세요.")

        try:
            parts = shlex.split(line, posix=is_bash)
        except ValueError:
            log({"tool": tool_name, "line": line, "decision": "pass-unparsed"})
            continue

        if not parts:
            continue

        if not is_bash:
            parts = [strip_ps_quotes(p) for p in parts]

        sub_commands = split_commands(parts)
        is_chained = len(sub_commands) > 1

        for cmd_parts in sub_commands:
            if not cmd_parts:
                continue

            base = os.path.basename(cmd_parts[0]).lower()
            args = cmd_parts[1:]
            lower_args = [a.lower() for a in args]

            # bash/sh -c "inner" 패턴: 내부 명령을 처리 큐에 추가해 동일 규칙으로 검사한다
            # (예: sudo bash -c "rm -rf /" 우회 차단).
            if base in {"bash", "sh", "zsh"} and "-c" in lower_args:
                c_idx = lower_args.index("-c")
                if c_idx + 1 < len(args):
                    lines.append(args[c_idx + 1])

            if base in DELETE_COMMANDS:
                if base in WINDOWS_FLAG_STYLE:
                    clean_args = [a for a in args if not a.startswith("/")]
                else:
                    clean_args = [a for a in args if not a.startswith("-")]

                if not clean_args:
                    emit("deny", "삭제 대상 경로가 지정되지 않았습니다.")

                for a in clean_args:
                    if ROOT_RE.match(a.strip()):
                        log({"tool": tool_name, "command": command, "decision": "deny-root-delete"})
                        emit("deny", f"드라이브/파일시스템 루트({a})를 삭제하려는 시도는 차단됩니다.")

                if is_multiline or is_chained:
                    emit("deny", "여러 줄 또는 체이닝된 명령 안에 삭제 명령이 섞여 있어 안전하게 자동 치환할 수 없습니다. 삭제 명령은 단독으로 실행하세요.")

                if not os.path.exists(SEND_TO_TRASH):
                    emit("deny", "안전 삭제 스크립트(send_to_trash.py)가 없어 삭제를 차단합니다.")

                if not send2trash_available():
                    emit("deny", "휴지통 이동 도구(send2trash)가 설치되어 있지 않아 삭제를 차단합니다. (pip install send2trash)")

                quote = quote_bash if is_bash else quote_ps
                py_exe = sys.executable
                new_command = f'{py_exe} -X utf8 {quote(SEND_TO_TRASH)} ' + " ".join(quote(a) for a in clean_args)

                log({"tool": tool_name, "command": command, "decision": "redirect-to-trash", "new_command": new_command})
                emit("allow", "삭제 명령을 휴지통 이동으로 안전하게 치환했습니다 (send2trash).",
                     updated_input={"command": new_command})

            if base == "git":
                if "push" in lower_args and any(f in lower_args for f in ("--force", "-f", "--force-with-lease")):
                    emit("deny", "git push --force 류는 원격 히스토리를 파괴할 수 있어 수동 실행이 필요합니다.")
                if "push" in lower_args:
                    emit("deny", "git push는 수동으로 실행하세요.")
                if "reset" in lower_args and "--hard" in lower_args:
                    emit("deny", "git reset --hard는 커밋되지 않은 변경사항을 되돌릴 수 없이 삭제합니다. (stash/soft 권장)")
                if "clean" in lower_args and any(f in lower_args for f in ("-f", "-fd", "-fx", "-fdx", "-xdf", "--force")):
                    emit("deny", "git clean -f 류는 추적되지 않는 파일을 되돌릴 수 없이 삭제합니다.")
                if "stash" in lower_args and any(a in lower_args for a in ("drop", "clear")):
                    emit("deny", "git stash drop/clear 는 스태시를 되돌릴 수 없이 삭제합니다.")
                if "branch" in lower_args and "-D" in args:
                    emit("ask", "git branch -D 는 병합되지 않은 브랜치를 강제 삭제합니다 (reflog 로만 복구 가능). 계속할까요?")
                if ("checkout" in lower_args and "--" in args) or "restore" in lower_args:
                    paths = _checkout_restore_paths(args, lower_args)
                    # split_commands 는 |/리다이렉트를 나누지 않으므로 이런 토큰이 섞이면
                    # is_chained 가 False 라도 뒤에 파괴적 명령이 스모글링될 수 있다. 이 경우
                    # 자동치환 없이 ask 로 폴백한다.
                    has_pipe_or_redirect = "|" in cmd_parts or any(t in (">", ">>") for t in cmd_parts)
                    # 멀티라인/체이닝(&&/;)이 섞여 있으면 원본 명령을 안전하게 특정할 수 없어
                    # stash-prepend 자동치환을 할 수 없다. 경로 추출에 실패(빈 리스트)한 경우도
                    # 안전하게 ask 로 폴백한다. (rm 자동치환의 multiline/chained 가드와 동일 원칙.)
                    if is_multiline or is_chained or not paths or has_pipe_or_redirect:
                        emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")
                    # 원본 명령은 건드리지 않고 앞에 git stash push 만 붙인다. 이렇게 해야
                    # `git checkout <다른-ref> -- <path>` 처럼 다른 ref 에서 가져오는 의미도
                    # 안 깨지고, 되돌리기 전 uncommitted 변경은 stash 에 보존돼 pop 으로 복구된다.
                    # `&&` 로 이어붙여 stash 가 실패하면 뒤의 파괴적 원본 명령이 실행되지 않게 한다
                    # (fail-open 방지). "보존할 게 없음"은 exit 0 이라 정상 진행된다.
                    quote = quote_bash if is_bash else quote_ps
                    stash_cmd = "git stash push -- " + " ".join(quote(p) for p in paths)
                    new_command = stash_cmd + " && " + line.strip()
                    log({"tool": tool_name, "command": command, "decision": "prepend-stash-preserve", "new_command": new_command})
                    emit("allow", "되돌리기 전 uncommitted 변경사항을 git stash로 보존했습니다 (git stash pop으로 복구 가능).",
                         updated_input={"command": new_command})

            if base in {"format", "diskpart", "mkfs", "fdisk", "clear-disk", "format-volume"}:
                emit("deny", f"디스크 레벨 명령({base})은 되돌릴 수 없어 자동 실행을 차단합니다.")
            if base == "dd" and any(a.startswith("of=") for a in args):
                emit("deny", "dd of=... 는 대상 장치/파일을 덮어쓸 수 있어 차단합니다.")
            if base == "chmod" and any(a in ("777", "0777", "a+rwx", "a=rwx") for a in args):
                emit("ask", "chmod 777 류는 모든 사용자에게 전체 권한을 부여합니다 (보안 위험). 계속할까요?")
            if base == "clear-content":
                emit("ask", "Clear-Content 는 파일 내용을 비웁니다 (데이터 손실 가능). 계속할까요?")
            if base == "reg" and lower_args and lower_args[0] == "delete":
                emit("ask", "reg delete 는 레지스트리 키/값을 삭제합니다. 계속할까요?")

            # 파이프 체크: &&/; 분리 후 서브커맨드 단위로 검사한다.
            if "|" in cmd_parts:
                idx = cmd_parts.index("|")
                downstream = [p.lower() for p in cmd_parts[idx + 1:]]
                if any(tok in downstream for tok in REMOTE_EXEC_TOKENS):
                    emit("deny", "원격/외부 출력을 바로 셸에 파이프 실행하는 패턴입니다. 스크립트를 먼저 저장해 검토한 뒤 실행하세요.")

            if base in {"shutdown", "restart-computer", "stop-computer"}:
                emit("ask", f"'{base}' 는 시스템을 종료/재시작합니다. 계속할까요?")

    sys.exit(0)


if __name__ == "__main__":
    main()
