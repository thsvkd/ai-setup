#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, Bash 툴 대상, 유저 레벨, macOS/Linux)

정책:
  1) rm → 휴지통 이동으로 치환 (allow + updatedInput)
     치환에 쓸 도구는 trash-put (trash-cli) → trash (macOS 14.4+ 기본 내장) 순으로 찾는다.
     단, 루트 경로(/, ~, $HOME, 와일드카드 포함) 삭제 시도는 즉시 deny.
     휴지통 도구가 하나도 없으면 치환할 수 없으므로 fail-closed 로 deny.
     멀티라인 또는 체이닝(&&/;) 스크립트 안에 섞여 있으면 자동 치환 대신 deny.
  2) git: "서브커맨드"를 정확히 판정해 세분화한다(git_subcommand). 순진하게 "push in args" 로
     매칭하면 `git stash push`(작업을 저장하는 안전한 명령)까지 막히므로, 전역 옵션(-C/-c/…)을
     건너뛰고 실제 서브커맨드를 뽑아 아래 규칙을 적용한다. "되돌릴 수 없이 손상"만 deny 한다.
       deny  : push --force/-f/--force-with-lease, reset --hard, clean -f*(단, -n/--dry-run 은 제외),
               stash drop|clear, filter-branch/filter-repo, reflog expire|delete
       ask   : push(일반), branch -D, checkout/switch --force(강제 전환), gc --prune=now|all
       allow : checkout -- <path> / checkout . / restore(워킹트리) → git stash 로 보존 후 실행(자동치환)
       pass  : stash push/save/pop/apply/list/show, reset --soft/--mixed, clean -n, branch -d,
               checkout/switch <branch>(전환), restore --staged(인덱스만), 그 외 안전한 서브커맨드
  3) dd of=... / mkfs* / newfs_* / wipefs / fdisk / parted → deny
     diskutil 의 파괴적 서브커맨드(eraseDisk, eraseVolume, secureErase, partitionDisk,
     apfs deleteContainer 등) → deny
     /dev/sd*, /dev/disk* 등 블록 디바이스로의 리다이렉트, 포크밤 패턴 → deny
  4) curl|bash, wget -O- | sh 같은 "원격 스크립트를 바로 셸로 파이프 실행" 패턴 → deny
     (`curl url|bash` 처럼 파이프 앞뒤에 공백이 없어도 잡는다)
  5) shutdown / reboot / halt / poweroff → ask ; chmod 777 / shred → ask
  6) sudo 접두어는 벗겨서 실제 명령을 위 규칙으로 검사한다.
  7) bash/sh -c "inner" 패턴: 내부 명령을 추출해 동일 규칙으로 추가 검사한다.

이 훅은 macOS 기본 인터프리터(/usr/bin/python3, 3.9.x)에서도 반드시 실행되어야 한다.
훅이 예외로 죽으면 Claude Code 는 가드 없이 명령을 실행하므로, 3.10+ 전용 문법(PEP 604
`X | None` 애노테이션 등)을 쓰지 않는다. 애노테이션은 `from __future__ import annotations`
로 지연 평가시킨다.

Bash 툴은 여러 줄짜리 스크립트를 통째로 하나의 command 문자열로 보낸다. shlex.split을
전체 문자열에 한 번만 적용하면 (a) 파이프 뒤 검사가 전혀 무관한 다음 줄까지 새어 들어가
오탐이 나거나 (b) 위험한 명령이 첫 줄이 아니면 검사 자체가 안 되는 미탐이 생긴다. 그래서
command를 줄 단위로 나눠 각 줄을 독립적으로 검사한다. 또한 같은 줄 안의 &&/||/; 체이닝도
토큰 수준에서 분리해 각 서브커맨드를 독립적으로 검사한다.

모든 판단은 hookSpecificOutput.permissionDecision(allow|deny|ask) 방식으로 반환하고,
~/.claude/hooks/guard.log 에 감사 로그를 남긴다. 이 훅은 유저 레벨에 설치되므로
이 사용자가 여는 모든 프로젝트에 적용된다.
"""
from __future__ import annotations

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
DISK_COMMANDS = {"fdisk", "parted", "wipefs", "gdisk", "sgdisk", "mke2fs"}
# 접두어로 판정하는 파일시스템 생성 도구: Linux 의 mkfs.* 와 macOS 의 newfs_* 계열.
DISK_COMMAND_PREFIXES = ("mkfs", "newfs_")
# diskutil 의 파괴적 서브커맨드. `diskutil apfs deleteContainer` 처럼 두 번째 인자에
# 오는 형태가 있어 앞의 두 인자를 모두 살펴본다.
DISKUTIL_DESTRUCTIVE = {
    "erasedisk", "erasevolume", "eraseoptical", "reformat", "secureerase",
    "zerodisk", "randomdisk", "partitiondisk", "splitpartition",
    "deletecontainer", "deletevolume",
}

# 휴지통 이동 도구 우선순위. macOS 14.4+ 는 /usr/bin/trash 를 기본 제공하므로 별도 설치가
# 필요 없다 (Homebrew 의 trash-cli 는 keg-only 라 trash-put 이 PATH 에 잡히지 않는다).
TRASH_COMMANDS = ("trash-put", "trash") if sys.platform == "darwin" else ("trash-put",)

# shlex 로 파싱되지 않는(또는 파싱 전에 잡아야 하는) 원시 문자열 패턴.
FORK_BOMB_RE = re.compile(r'\(\s*\)\s*\{[^}]*\|[^}]*&')  # :(){ :|:& };:
DEVICE_REDIRECT_RE = re.compile(r'>\s*/dev/(sd|nvme|hd|disk|mmcblk|vd)[a-z0-9]*', re.IGNORECASE)
# `curl url|bash` 처럼 파이프 앞뒤에 공백이 없으면 shlex 가 `url|bash` 를 한 토큰으로 묶어
# 토큰 기반 검사를 그대로 빠져나간다. 원시 문자열에서 한 번 더 잡는다. (?<!\|)\|(?!\|) 는
# OR 연산자 `||` 를 제외하기 위한 것.
PIPE_TO_SHELL_RE = re.compile(
    r'(?<!\|)\|(?!\|)\s*(?:sudo\s+)?(?:\S*/)?(?:' + "|".join(REMOTE_EXEC_TOKENS) + r')\b'
)
# 따옴표 안의 문자열은 실행되는 명령이 아니므로 위 파이프 검사에서 제외한다
# (예: grep "x|bash" file 이 오탐으로 차단되지 않도록).
QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')


def resolve_trash_command() -> str | None:
    for candidate in TRASH_COMMANDS:
        if shutil.which(candidate):
            return candidate
    return None


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


# git 전역 옵션 중 '다음 토큰'을 값으로 소비하는 것들 (예: git -C <path> <sub>, git -c k=v <sub>).
# 서브커맨드를 정확히 찾으려면 이 옵션들의 값 토큰을 건너뛰어야 한다. 대소문자 구분(-C ≠ -c).
GIT_GLOBAL_VALUE_OPTS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--config-env", "--exec-path",
}


def git_subcommand(args: list):
    """git 전역 옵션(-C/-c/--no-pager 등)을 건너뛰고 (실제 서브커맨드, 그 뒤 인자들) 을 반환한다.
    이래야 `git stash push` 의 서브커맨드가 'stash'(안전)로, `git push` 만 'push'로 잡힌다.
    서브커맨드를 못 찾으면 (None, []). 옵션 판정은 대소문자 구분(-C 는 값 소비, -c 도 값 소비)."""
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if not a.startswith("-"):
            return a, args[i + 1:]
        if "=" in a:                       # --git-dir=… 처럼 값이 '=' 로 붙은 형태
            i += 1
            continue
        if a in GIT_GLOBAL_VALUE_OPTS:      # 값이 다음 토큰에 오는 형태 (git -C <path>)
            i += 2
            continue
        i += 1                             # 값 없는 전역 플래그(-p, --no-pager, --bare, …)
    return None, []


def _git_own_args(args: list) -> list:
    """git 명령 '자체'의 인자만 남긴다 — 파이프/리다이렉트 뒤(다른 명령이나 파일)를 잘라낸다.
    split_commands 는 &&/||/; 만 나누고 | 와 리다이렉트는 나누지 않으므로, 그대로 두면
    `git checkout -- f | rm -rf ~` 의 `-rf` 같은 남의 토큰이 rest 에 새어들어 플래그 판정을
    오염시킨다. (스모글링 자체의 최종 판정은 _emit_stash_prepend 가 cmd_parts 로 다시 잡는다.)"""
    out = []
    for t in args:
        if t in ("|", "|&", "&", ">", ">>", "<", "<<") or t[:1] in (">", "<") or t[:2] in ("2>", "&>", "1>"):
            break
        out.append(t)
    return out


def _short_flag_chars(token: str) -> set:
    """'-fd' → {'f','d'} (단일 대시 짧은 플래그의 문자들). '--force'/비플래그 → 빈 집합.
    git 플래그는 대소문자를 구분하므로(-S staged ≠ -s source) 소문자화하지 않는다."""
    if token.startswith("-") and not token.startswith("--") and len(token) > 1:
        return set(token[1:])
    return set()


def _push_is_force(rest: list) -> bool:
    """git push 의 강제(force) 계열 플래그 존재 여부. 위치 무관, 짧은 플래그 결합(-fu)도 잡는다."""
    for t in rest:
        if t in ("--force", "--force-with-lease", "--force-if-includes"):
            return True
        if t.startswith("--force-with-lease") or t.startswith("--force-if-includes"):
            return True  # --force-with-lease=<ref> 형태
        if "f" in _short_flag_chars(t):     # -f, -fu, -uf …
            return True
    return False


def _clean_is_destructive(rest: list) -> bool:
    """git clean 이 실제로 파일을 삭제하는지. -n/--dry-run(미리보기)이 있으면 삭제하지 않는다."""
    dry = any(t == "--dry-run" or "n" in _short_flag_chars(t) for t in rest)
    if dry:
        return False
    return any(t == "--force" or "f" in _short_flag_chars(t) for t in rest)


def _restore_touches_worktree(rest: list) -> bool:
    """git restore 가 워킹트리를 건드리는지. `--staged` 만 주면 인덱스만 바뀌어 손실이 없다.
    기본(옵션 없음)은 워킹트리를 되돌린다. `-S`(staged) 와 `-s`(source)는 다른 옵션이므로 대소문자 구분."""
    staged = any(t in ("--staged",) or "S" in _short_flag_chars(t) for t in rest)
    worktree = any(t in ("--worktree",) or "W" in _short_flag_chars(t) for t in rest)
    return worktree or not staged


def _first_non_option(rest: list):
    """rest 에서 첫 번째 비옵션 토큰(예: stash/reflog 의 하위 동작). 없으면 None."""
    for t in rest:
        if not t.startswith("-"):
            return t
    return None


def _checkout_paths(rest: list) -> list:
    """git checkout 의 되돌림 대상 pathspec. '--' 뒤 토큰, 또는 '--' 없이 '.' 만 온 경우 '.'."""
    if "--" in rest:
        idx = rest.index("--")
        return [a for a in rest[idx + 1:] if a]
    return [a for a in rest if a == "."]     # git checkout . (현재 디렉터리 전체 폐기)


def _restore_paths(rest: list) -> list:
    """git restore 의 pathspec. '-s <ref>' 처럼 값이 분리된 옵션의 값과 모든 옵션을 제외한 나머지."""
    value_opts = {"-s", "--source", "--conflict", "--pathspec-from-file"}
    paths = []
    skip_next = False
    for a in rest:
        if skip_next:
            skip_next = False
            continue
        if a in value_opts:
            skip_next = True
            continue
        if a.startswith("-"):
            continue
        paths.append(a)
    return paths


def _has_force_flag(rest: list) -> bool:
    """rest 에 -f / --force / --discard-changes 강제 플래그가 있는지 (checkout/switch/branch 판정용)."""
    for t in rest:
        if t in ("-f", "--force", "--discard-changes"):
            return True
        if "f" in _short_flag_chars(t):
            return True
    return False


def _emit_stash_prepend(paths, cmd_parts, line, is_multiline, is_chained, command) -> None:
    """되돌리기 전 uncommitted 변경을 git stash 로 보존한 뒤 원본을 실행하도록 자동 치환한다.
    원본 명령을 안전하게 특정할 수 없으면(멀티라인/체이닝/파이프/리다이렉트/경로 추출 실패) ask 로 폴백.
    `&&` 로 이어붙여 stash 실패 시 뒤의 파괴적 원본이 실행되지 않게 한다(fail-open 방지)."""
    has_pipe_or_redirect = "|" in cmd_parts or any(t in (">", ">>") for t in cmd_parts)
    if is_multiline or is_chained or not paths or has_pipe_or_redirect:
        emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")
    stash_cmd = "git stash push -- " + " ".join(shlex.quote(p) for p in paths)
    new_command = stash_cmd + " && " + line.strip()
    log({"command": command, "decision": "prepend-stash-preserve", "new_command": new_command})
    emit("allow", "되돌리기 전 uncommitted 변경사항을 git stash로 보존했습니다 (git stash pop으로 복구 가능).",
         updated_input={"command": new_command})


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
        if PIPE_TO_SHELL_RE.search(QUOTED_RE.sub(" ", stripped)):
            log({"command": command, "decision": "deny-pipe-to-shell"})
            emit("deny", "원격/외부 출력을 바로 셸에 파이프 실행하는 패턴입니다. 스크립트를 먼저 저장해 검토한 뒤 실행하세요.")

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
            lower_args = [a.lower() for a in args]

            # sudo 접두어는 벗겨서 실제 명령을 검사한다 (sudo rm -rf / 가 우회되지 않도록).
            if base == "sudo" and args and not args[0].startswith("-"):
                base = os.path.basename(args[0])
                args = args[1:]
                lower_args = [a.lower() for a in args]

            # bash/sh -c "inner" 패턴: 내부 명령을 처리 큐에 추가해 동일 규칙으로 검사한다
            # (예: sudo bash -c "rm -rf /" 우회 차단).
            if base in REMOTE_EXEC_TOKENS and "-c" in lower_args:
                c_idx = lower_args.index("-c")
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

                trash_cmd = resolve_trash_command()
                if not trash_cmd:
                    emit("deny", "휴지통 이동 도구(trash-put / macOS trash)가 없어 삭제를 차단합니다. (pip install trash-cli)")

                new_command = trash_cmd + " " + " ".join(shlex.quote(a) for a in clean_args)
                log({"command": command, "decision": "redirect-to-trash", "new_command": new_command})
                emit("allow", f"rm → {trash_cmd} 치환 (휴지통으로 안전하게 이동)",
                     updated_input={"command": new_command})

            if base == "git":
                # 서브커맨드를 정확히 판정한다. 이래야 `git stash push`(안전, 저장)가
                # 순진한 "push in args" 매칭으로 오탐되지 않는다.
                sub, rest = git_subcommand(args)
                subl = sub.lower() if sub else ""

                if subl == "push":
                    if _push_is_force(rest):
                        emit("deny", "git push --force 류는 원격 히스토리를 파괴할 수 있어 수동 실행이 필요합니다.")
                    emit("ask", "git push 는 원격에 반영됩니다 (로컬 변경은 손상되지 않음). 진행할까요?")

                if subl == "reset" and "--hard" in rest:
                    emit("deny", "git reset --hard는 커밋되지 않은 변경사항을 되돌릴 수 없이 삭제합니다. (--soft/--mixed/stash 권장)")

                if subl == "clean" and _clean_is_destructive(rest):
                    emit("deny", "git clean -f 류는 추적되지 않는 파일을 되돌릴 수 없이 삭제합니다. (-n/--dry-run 으로 먼저 확인하세요.)")

                if subl == "stash" and _first_non_option(rest) in ("drop", "clear"):
                    emit("deny", "git stash drop/clear 는 스태시를 되돌릴 수 없이 삭제합니다. (push/save/pop/apply/list 는 안전.)")

                if subl == "branch" and ("-D" in rest or ("--delete" in rest and _has_force_flag(rest))):
                    emit("ask", "git branch -D 는 병합되지 않은 브랜치를 강제 삭제합니다 (reflog 로만 복구 가능). 계속할까요?")

                if subl in ("filter-branch", "filter-repo"):
                    emit("deny", f"git {subl} 는 저장소 히스토리를 대량으로 재작성합니다. 신중히 수동으로 실행하세요.")

                if subl == "reflog" and _first_non_option(rest) in ("expire", "delete"):
                    emit("deny", "git reflog expire/delete 는 커밋 복구 안전망(reflog)을 파괴합니다.")

                if subl == "gc" and any(t in ("--prune=now", "--prune=all") for t in rest):
                    emit("ask", "git gc --prune=now/all 은 도달 불가능한 객체를 영구 삭제합니다 (reflog 만료분 복구 불가). 계속할까요?")

                if subl == "switch" and _has_force_flag(rest):
                    emit("ask", "git switch --force/--discard-changes 는 커밋되지 않은 로컬 변경을 버릴 수 있습니다. 계속할까요?")

                if subl == "checkout":
                    if _has_force_flag(rest):
                        emit("ask", "git checkout --force 는 전환 시 커밋되지 않은 로컬 변경을 버릴 수 있습니다. 계속할까요?")
                    # 경로 되돌리기(`-- <path>` 또는 `git checkout .`)만 stash 로 보존 후 실행한다.
                    # 그냥 브랜치 전환(`git checkout <branch>`)은 충돌 시 git 이 거부하므로 통과.
                    if "--" in rest or "." in rest:
                        _emit_stash_prepend(_checkout_paths(rest), cmd_parts, line, is_multiline, is_chained, command)

                if subl == "restore" and _restore_touches_worktree(rest):
                    # `git restore --staged`(인덱스만)는 손실이 없어 통과. 워킹트리를 되돌리는 경우만 보존.
                    _emit_stash_prepend(_restore_paths(rest), cmd_parts, line, is_multiline, is_chained, command)

            if base in DISK_COMMANDS or base.startswith(DISK_COMMAND_PREFIXES):
                emit("deny", f"디스크 레벨 명령({base})은 되돌릴 수 없어 자동 실행을 차단합니다.")
            if base == "dd" and any(a.startswith("of=") for a in args):
                emit("deny", "dd of=... 는 대상 장치/파일을 덮어쓸 수 있어 차단합니다.")
            if base == "diskutil":
                hit = next((a for a in lower_args[:2] if a in DISKUTIL_DESTRUCTIVE), None)
                if hit:
                    emit("deny", f"diskutil {hit} 은 되돌릴 수 없어 자동 실행을 차단합니다.")
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
