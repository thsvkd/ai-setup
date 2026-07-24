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
  2) git: 서브커맨드를 정확히 판정해 세분화한다(git_subcommand). 순진하게 "push in args" 로
     매칭하면 `git stash push`(작업을 저장하는 안전한 명령)까지 막히므로, 전역 옵션(-C/-c/…)을
     건너뛰고 실제 서브커맨드를 뽑아 아래 규칙을 적용한다.
       push  : 대상 원격 브랜치 이름에 '/' 가 있으면(feature/*, fix/* 등 곁다리 브랜치) 통과.
               '/' 가 없으면(main/master/develop 등 보호 브랜치로 간주) 브랜치 이름을 명시하며
               ask. --all/--mirror 처럼 특정 브랜치로 좁힐 수 없으면 ask. force 여부는 통과/ask
               판정에 영향 없음(브랜치 이름만 기준) — ask 사유 문구에만 force 여부를 표시한다.
       backup 후 allow : reset --hard, clean -f*(단 -n/--dry-run 제외), stash drop|clear,
               branch -D, branch -M(대상 이름이 이미 있었으면), tag -d, tag -f(대상이 이미
               있었으면), rebase(새로 시작하는 경우), commit --amend, filter-branch/filter-repo,
               reflog expire|delete, gc --prune=now|all, checkout/switch --force|-B|-C(강제 전환),
               checkout -- <path>/checkout ./restore(워킹트리) → 실행 전 refs/claude-backups/
               <timestamp>/<대상> 에 되돌릴 대상을 백업한 뒤 원본 명령을 그대로 이어서 실행한다
               (자동치환). git stash create 는 추적 안 된 파일을 담지 못하는 한계가 있어(검증됨)
               clean 은 별도 스크래치 인덱스로 추적 안 된 파일까지 스냅샷한다. 멀티라인/체이닝된
               경우 백업 대상을 안전하게 특정할 수 없어 ask 로 폴백한다.
       pass  : stash push/pop/apply/list, reset --soft/--mixed, clean -n, branch -d,
               checkout/switch <branch>, restore --staged, rebase --continue/--abort/--skip,
               commit(amend 아님), 그 외 안전한 서브커맨드
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
import subprocess

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

# `~`/`$HOME`/`%USERPROFILE%` 같은 축약 표기뿐 아니라, 실제 홈 디렉터리 값을 그대로 적은
# 절대경로(예: rm -rf C:\Users\pi)도 루트/홈 삭제로 잡아야 한다 — 그렇지 않으면 축약형만 막고
# 같은 대상을 가리키는 리터럴 경로는 새어나간다. 값을 못 찾으면 이 보강판정을 건너뛴다.
_HOME_DIR = os.environ.get("USERPROFILE") or os.environ.get("HOME", "")


def _is_root_or_home_literal(path: str) -> bool:
    if ROOT_RE.match(path):
        return True
    if not _HOME_DIR or _HOME_DIR in ("/", "\\"):
        return False
    stripped = path.rstrip("/\\*") if path not in ("/", "\\", "") else path
    return os.path.normcase(os.path.normpath(stripped)) == os.path.normcase(os.path.normpath(_HOME_DIR))

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


# git 전역 옵션 중 '다음 토큰'을 값으로 소비하는 것들 (예: git -C <path> <sub>, git -c k=v <sub>).
GIT_GLOBAL_VALUE_OPTS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--config-env", "--exec-path",
}


def git_subcommand(args: list):
    """git 전역 옵션(-C/-c/--no-pager 등)을 건너뛰고 (실제 서브커맨드, 그 뒤 인자들) 을 반환한다.
    이래야 `git stash push`(안전)의 서브커맨드가 'stash'로, `git push` 만 'push'로 잡힌다.
    옵션 판정은 대소문자 구분(-C ≠ -c). 서브커맨드를 못 찾으면 (None, [])."""
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if not a.startswith("-"):
            return a, args[i + 1:]
        if "=" in a:
            i += 1
            continue
        if a in GIT_GLOBAL_VALUE_OPTS:
            i += 2
            continue
        i += 1
    return None, []


def _git_own_args(args: list) -> list:
    """git 명령 '자체'의 인자만 남긴다 — 파이프/리다이렉트 뒤(다른 명령이나 파일)를 잘라낸다.
    split_commands 는 | 와 리다이렉트를 나누지 않으므로, 그대로 두면 남의 토큰이 rest 에 새어들어
    플래그 판정을 오염시킨다. (스모글링 최종 판정은 _emit_backup_prepend 가 cmd_parts 로 다시 잡는다.)"""
    out = []
    for t in args:
        if t in ("|", "|&", "&", ">", ">>", "<", "<<") or t[:1] in (">", "<") or t[:2] in ("2>", "&>", "1>"):
            break
        out.append(t)
    return out


def _short_flag_chars(token: str) -> set:
    """'-fd' → {'f','d'}. git 플래그는 대소문자를 구분하므로(-S staged ≠ -s source) 소문자화하지 않는다."""
    if token.startswith("-") and not token.startswith("--") and len(token) > 1:
        return set(token[1:])
    return set()


def _push_is_force(rest: list) -> bool:
    """git push 의 강제(force) 계열 플래그 존재 여부. `+refspec` 형태도 잡는다."""
    for t in rest:
        if t in ("--force", "--force-with-lease", "--force-if-includes"):
            return True
        if t.startswith("--force-with-lease") or t.startswith("--force-if-includes"):
            return True
        if "f" in _short_flag_chars(t):
            return True
        if not t.startswith("-") and t.startswith("+"):
            return True
    return False


PUSH_BROAD_FLAGS = {"--all", "--mirror"}
REBASE_SAFE_ACTIONS = {"--continue", "--abort", "--skip", "--quit", "--edit-todo", "--show-current-patch"}
BACKUP_REF_PREFIX = "refs/claude-backups/"
BACKUP_HINT = f"{BACKUP_REF_PREFIX} 는 git for-each-ref {BACKUP_REF_PREFIX} 로 조회 가능합니다."
CHAINED_BACKUP_ASK = "여러 줄 또는 체이닝된 명령이라 되돌릴 대상을 안전하게 특정해 백업할 수 없습니다. 계속할까요?"


def _current_branch(cwd: str):
    """cwd 의 현재 브랜치 이름. detached HEAD/실패 시 None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or None, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def _push_implicit_branch(cwd: str):
    """remote/refspec 을 생략한 `git push`가 실제로 갱신할 원격 브랜치 이름. 업스트림이 설정돼
    있으면 그 이름(리모트 접두어 제거)을, 아니면 로컬 브랜치 이름을 쓴다."""
    try:
        up = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "@{u}"],
            cwd=cwd or None, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        up = None
    if up is not None and up.returncode == 0 and up.stdout.strip():
        tracking = up.stdout.strip()
        return tracking.split("/", 1)[1] if "/" in tracking else tracking
    return _current_branch(cwd)


def _push_target_branches(rest: list, cwd: str):
    """git push 인자에서 실제로 갱신/삭제될 원격 브랜치 이름들을 뽑는다.
    반환: (branches, broad) — broad 면 --all/--mirror 등으로 특정 브랜치로 좁힐 수 없다."""
    if any(f in rest for f in PUSH_BROAD_FLAGS):
        return [], True
    positional = [a for a in rest if not a.startswith("-")]
    if len(positional) <= 1:
        branch = _push_implicit_branch(cwd)
        return ([branch] if branch else []), False
    branches = []
    for rs in positional[1:]:
        rs = rs.lstrip("+")
        if ":" in rs:
            src, dst = rs.split(":", 1)
            target = dst or src
            if target:
                branches.append(target)
        elif rs == "HEAD":
            b = _current_branch(cwd)
            if b:
                branches.append(b)
        else:
            branches.append(rs)
    return branches, False


def _clean_is_destructive(rest: list) -> bool:
    """git clean 이 실제로 삭제하는지. -n/--dry-run(미리보기)이 있으면 삭제하지 않는다."""
    dry = any(t == "--dry-run" or "n" in _short_flag_chars(t) for t in rest)
    if dry:
        return False
    return any(t == "--force" or "f" in _short_flag_chars(t) for t in rest)


def _restore_touches_worktree(rest: list) -> bool:
    """git restore 가 워킹트리를 건드리는지. --staged 만 주면 인덱스만 바뀌어 손실이 없다."""
    staged = any(t in ("--staged",) or "S" in _short_flag_chars(t) for t in rest)
    worktree = any(t in ("--worktree",) or "W" in _short_flag_chars(t) for t in rest)
    return worktree or not staged


def _has_force_flag(rest: list) -> bool:
    """rest 에 강제 플래그가 있는지. -f/--force/--discard-changes 외에, `checkout -B`(강제 생성+
    전환)와 `switch -C`(강제 생성+전환)도 기존 브랜치 위치를 되돌릴 수 없이 재설정하고 uncommitted
    변경을 버릴 수 있어 같은 취급을 한다."""
    for t in rest:
        if t in ("-f", "--force", "--discard-changes", "-B", "-C", "--force-create"):
            return True
        chars = _short_flag_chars(t)
        if "f" in chars or "B" in chars or "C" in chars:
            return True
    return False


def _first_non_option(rest: list):
    for t in rest:
        if not t.startswith("-"):
            return t
    return None


def _checkout_paths(rest: list) -> list:
    """git checkout 의 되돌림 대상 pathspec. '--' 뒤 토큰, 또는 '--' 없이 '.' 만 온 경우 '.'."""
    if "--" in rest:
        idx = rest.index("--")
        return [a for a in rest[idx + 1:] if a]
    return [a for a in rest if a == "."]


def _restore_paths(rest: list) -> list:
    """git restore 의 pathspec. '-s <ref>' 같은 값-소비 옵션의 값과 모든 옵션을 제외한 나머지."""
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


def _join(is_bash: bool) -> str:
    """백업 스니펫과 원본 명령을 잇는 구분자. bash 는 `&&`(백업 실패 시 원본 미실행, fail-closed).
    PowerShell 5.1 은 `&&`가 없어 `;` 를 쓰되, 백업 스니펫 쪽에서 실패 시 자체적으로
    `exit 1` 해 스크립트 전체를 끊는 방식으로 같은 fail-closed 효과를 낸다."""
    return " && " if is_bash else "; "


def _backup_head_and_worktree(reason: str, is_bash: bool) -> str:
    """HEAD 커밋 위치 + 추적된 uncommitted 변경(stash)을 refs/claude-backups/ 에 백업.
    추적 안 된 파일은 담기지 않는다 — reset --hard/checkout --force/switch --force/checkout --
    <path>/restore 는 추적 안 된 파일을 지우지 않으므로 이걸로 충분하다(git clean 은
    _backup_full_snapshot 을 따로 쓴다)."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            '_bk_head=$(git rev-parse HEAD) && git update-ref "refs/claude-backups/${_bk_ts}/head" "$_bk_head" && '
            '_bk_stash=$(git stash create ' + shlex.quote(reason) + '); '
            '[ -z "$_bk_stash" ] || git update-ref "refs/claude-backups/${_bk_ts}/worktree" "$_bk_stash"'
        )
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        '$bkHead = git rev-parse HEAD; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        'git update-ref "refs/claude-backups/$bkTs/head" $bkHead; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkStash = git stash create ' + quote_ps(reason) + '; '
        'if ($bkStash) { git update-ref "refs/claude-backups/$bkTs/worktree" $bkStash }'
    )


def _backup_full_snapshot(reason: str, is_bash: bool) -> str:
    """추적 + 추적 안 된 파일(gitignore 대상 제외) 전체를 스냅샷 커밋으로 백업한다. git clean
    전용 — git stash create 는 추적 안 된 파일을 담지 못하는 한계가 실측으로 확인되어, 별도
    인덱스로 실제 인덱스/워킹트리를 전혀 건드리지 않고 전체 스냅샷을 만든다."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            '_bk_idx=$(mktemp -u) && '
            'GIT_INDEX_FILE="$_bk_idx" git add -A -- . && '
            '_bk_tree=$(GIT_INDEX_FILE="$_bk_idx" git write-tree) && '
            '_bk_h=$(git commit-tree "$_bk_tree" -p HEAD -m ' + shlex.quote(reason) + ') && '
            'git update-ref "refs/claude-backups/${_bk_ts}/snapshot" "$_bk_h"'
        )
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        '$bkIdx = Join-Path $env:TEMP ("claude-bk-" + [guid]::NewGuid().ToString("N")); '
        '$env:GIT_INDEX_FILE = $bkIdx; '
        'git add -A -- .; '
        'if ($LASTEXITCODE -ne 0) { Remove-Item Env:\\GIT_INDEX_FILE -ErrorAction SilentlyContinue; exit 1 }; '
        '$bkTree = git write-tree; '
        'Remove-Item Env:\\GIT_INDEX_FILE -ErrorAction SilentlyContinue; '
        'if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkH = git commit-tree $bkTree -p HEAD -m ' + quote_ps(reason) + '; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        'git update-ref "refs/claude-backups/$bkTs/snapshot" $bkH'
    )


def _backup_refs(ref_exprs: list, is_bash: bool) -> str:
    """주어진 각 ref 표현식(브랜치/태그 이름 등)이 가리키는 커밋을, 삭제/재작성되기 전에
    백업한다. 대상을 못 찾으면(예상과 다름) fail-closed 로 원본 명령도 막는다."""
    if is_bash:
        quoted = " ".join(shlex.quote(r) for r in ref_exprs)
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            'for _bk_r in ' + quoted + '; do '
            '_bk_h=$(git rev-parse "$_bk_r") && git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h" || exit 1; '
            'done'
        )
    quoted_ps = ",".join(quote_ps(r) for r in ref_exprs)
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        'foreach ($bkR in @(' + quoted_ps + ')) { '
        '$bkH = git rev-parse $bkR; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        'git update-ref "refs/claude-backups/$bkTs/$bkR" $bkH; if ($LASTEXITCODE -ne 0) { exit 1 } '
        '}'
    )


def _backup_refs_if_exist(ref_exprs: list, is_bash: bool) -> str:
    """주어진 각 ref 표현식이 '이미 존재할 때만' 그 커밋을 백업한다. branch -M / tag -f 처럼
    대상이 아직 없는 것(덮어쓸 게 없어 안전한 경우)이 정상 경로인 명령에 쓴다 — 없으면 조용히
    건너뛰고, 있으면 덮어쓰이기 전 위치를 남긴다(실패해도 전체를 막지 않는다)."""
    if is_bash:
        quoted = " ".join(shlex.quote(r) for r in ref_exprs)
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            'for _bk_r in ' + quoted + '; do '
            '_bk_h=$(git rev-parse --verify -q "$_bk_r" 2>/dev/null) && '
            'git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h"; '
            'done; true'
        )
    quoted_ps = ",".join(quote_ps(r) for r in ref_exprs)
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        'foreach ($bkR in @(' + quoted_ps + ')) { '
        '$bkH = git rev-parse --verify -q $bkR 2>$null; '
        'if ($LASTEXITCODE -eq 0 -and $bkH) { git update-ref "refs/claude-backups/$bkTs/$bkR" $bkH } '
        '}'
    )


def _backup_all_branch_tips(is_bash: bool) -> str:
    """filter-branch/filter-repo 처럼 저장소 전체 히스토리를 재작성하기 전에, 현재 존재하는
    모든 로컬 브랜치의 커밋 위치를 전부 백업한다."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            "for _bk_r in $(git for-each-ref refs/heads --format='%(refname:short)'); do "
            '_bk_h=$(git rev-parse "$_bk_r") && git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h" || exit 1; '
            'done'
        )
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        '$bkList = git for-each-ref refs/heads --format="%(refname:short)"; '
        'foreach ($bkR in $bkList) { '
        '$bkH = git rev-parse $bkR; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        'git update-ref "refs/claude-backups/$bkTs/$bkR" $bkH; if ($LASTEXITCODE -ne 0) { exit 1 } '
        '}'
    )


def _backup_stash_entries(is_bash: bool) -> str:
    """git stash clear 전에, 현재 존재하는 모든 스태시 항목의 커밋을 각각 백업한다."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            '_bk_i=0; '
            'for _bk_h in $(git stash list --format=%H); do '
            'git update-ref "refs/claude-backups/${_bk_ts}/stash${_bk_i}" "$_bk_h"; _bk_i=$((_bk_i+1)); '
            'done'
        )
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        '$bkI = 0; '
        '$bkList = git stash list --format=%H; '
        'foreach ($bkH in $bkList) { '
        'git update-ref "refs/claude-backups/$bkTs/stash$bkI" $bkH; $bkI++ '
        '}'
    )


def _backup_reflog_reachable(is_bash: bool) -> str:
    """git reflog expire/delete 전에, 현재 reflog 로만 도달 가능한 커밋들을 전부 고정한다."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            '_bk_i=0; '
            "for _bk_h in $(git reflog show --all --format=%H 2>/dev/null | sort -u); do "
            'git update-ref "refs/claude-backups/${_bk_ts}/reflog${_bk_i}" "$_bk_h" 2>/dev/null; _bk_i=$((_bk_i+1)); '
            'done'
        )
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        '$bkI = 0; '
        '$bkList = git reflog show --all --format=%H 2>$null | Sort-Object -Unique; '
        'foreach ($bkH in $bkList) { '
        'git update-ref "refs/claude-backups/$bkTs/reflog$bkI" $bkH 2>$null; $bkI++ '
        '}'
    )


def _backup_dangling_commits(is_bash: bool) -> str:
    """git gc --prune=now/all 전에, reflog 로도 안 잡히는 커밋들을 전부 고정한다."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S); '
            '_bk_i=0; '
            "for _bk_h in $(git fsck --no-reflog --unreachable 2>/dev/null | awk '$1==\"unreachable\" && $2==\"commit\"{print $3}'); do "
            'git update-ref "refs/claude-backups/${_bk_ts}/dangling${_bk_i}" "$_bk_h" 2>/dev/null; _bk_i=$((_bk_i+1)); '
            'done'
        )
    return (
        '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; '
        '$bkI = 0; '
        '$bkList = git fsck --no-reflog --unreachable 2>$null | '
        "Where-Object { $_ -match '^unreachable commit (\\S+)' } | ForEach-Object { $matches[1] }; "
        'foreach ($bkH in $bkList) { '
        'git update-ref "refs/claude-backups/$bkTs/dangling$bkI" $bkH 2>$null; $bkI++ '
        '}'
    )


def _emit_with_backup(backup_snippet: str, line: str, reason: str, command: str, is_bash: bool) -> None:
    new_command = backup_snippet + _join(is_bash) + line.strip()
    log({"command": command, "decision": "prepend-backup", "new_command": new_command})
    emit("allow", reason, updated_input={"command": new_command})


def _emit_with_backup_or_ask(backup_snippet, line, allow_reason, is_multiline, is_chained, command, is_bash) -> None:
    if is_multiline or is_chained:
        emit("ask", CHAINED_BACKUP_ASK)
    _emit_with_backup(backup_snippet, line, allow_reason, command, is_bash)


def _emit_backup_prepend(paths, cmd_parts, line, is_multiline, is_chained, command, quote, is_bash) -> None:
    """되돌리기 전 uncommitted 변경을 refs/claude-backups/ 에 백업한 뒤 원본을 그대로 실행하도록
    자동 치환한다. 원본 명령을 안전하게 특정할 수 없으면(멀티라인/체이닝/파이프/리다이렉트/경로
    추출 실패) ask 로 폴백."""
    has_pipe_or_redirect = "|" in cmd_parts or any(t in (">", ">>") for t in cmd_parts)
    if is_multiline or is_chained or not paths or has_pipe_or_redirect:
        emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")
    backup = _backup_head_and_worktree(f"claude-auto-backup: before {line.strip()}", is_bash)
    _emit_with_backup(
        backup, line,
        f"되돌리기 전 uncommitted 변경사항을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
        command, is_bash,
    )
    emit("allow", "되돌리기 전 uncommitted 변경사항을 git stash로 보존했습니다 (git stash pop으로 복구 가능).",
         updated_input={"command": new_command})


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
                    if _is_root_or_home_literal(a.strip()):
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
                # 서브커맨드를 정확히 판정한다 (순진한 "push in args" 는 `git stash push` 를 오탐).
                sub, rest = git_subcommand(_git_own_args(args))
                subl = sub.lower() if sub else ""
                quote = quote_bash if is_bash else quote_ps

                if subl == "push":
                    cwd = data.get("cwd") or os.getcwd()
                    branches, broad = _push_target_branches(rest, cwd)
                    if broad:
                        emit("ask", "git push --all/--mirror 는 여러 브랜치(보호 브랜치 포함 가능)를 한 번에 원격에 반영합니다. 계속할까요?")
                    if not branches:
                        emit("ask", "푸시 대상 브랜치를 확인할 수 없습니다. 계속할까요?")
                    protected = [b for b in branches if "/" not in b]
                    if protected:
                        kind = "force push" if _push_is_force(rest) else "push"
                        emit("ask", f"'{', '.join(protected)}' 브랜치로 {kind} 하려고 합니다. 계속할까요?")
                    # feature/*, fix/* 처럼 '/'가 있는 곁다리 브랜치만 대상이면 통과(force 여부 무관).

                if subl == "reset" and "--hard" in rest:
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git reset --hard", is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"되돌리기 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --hard <hash> 또는 git stash apply <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "clean" and _clean_is_destructive(rest):
                    backup = _backup_full_snapshot("claude-auto-backup: pre git clean", is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"삭제될 추적/미추적 파일 전체를 스냅샷으로 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git checkout <hash> -- . 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "stash":
                    stash_action = _first_non_option(rest)
                    if stash_action == "drop":
                        idx = rest.index("drop")
                        ref = next((t for t in rest[idx + 1:] if not t.startswith("-")), "stash@{0}")
                        if is_bash:
                            backup = f'_bk_ts=$(date +%Y%m%d_%H%M%S); _bk_h=$(git rev-parse {shlex.quote(ref)}) && git update-ref "refs/claude-backups/${{_bk_ts}}/stash" "$_bk_h"'
                        else:
                            backup = '$bkTs = Get-Date -Format "yyyyMMdd_HHmmss"; $bkH = git rev-parse ' + quote_ps(ref) + '; if ($LASTEXITCODE -ne 0) { exit 1 }; git update-ref "refs/claude-backups/$bkTs/stash" $bkH'
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 스태시를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            is_multiline, is_chained, command, is_bash,
                        )
                    if stash_action == "clear":
                        backup = _backup_stash_entries(is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 모든 스태시를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            is_multiline, is_chained, command, is_bash,
                        )

                if subl == "branch" and ("-D" in rest or ("--delete" in rest and _has_force_flag(rest))):
                    names = [t for t in rest if not t.startswith("-")]
                    if not names:
                        emit("ask", "삭제할 브랜치 이름을 확인할 수 없습니다. 계속할까요?")
                    backup = _backup_refs(names, is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"삭제될 브랜치({', '.join(names)})의 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "branch" and ("-M" in rest or ("--move" in rest and _has_force_flag(rest))):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs_if_exist([names[-1]], is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"'{names[-1]}' 이름이 이미 있었다면 덮어쓰이기 전 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                            is_multiline, is_chained, command, is_bash,
                        )

                if subl == "tag" and ("-d" in rest or "--delete" in rest):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs(names, is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 태그({', '.join(names)})의 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git tag <name> <hash> 로 복구).",
                            is_multiline, is_chained, command, is_bash,
                        )

                if subl == "tag" and ("-f" in rest or "--force" in rest):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs_if_exist([names[0]], is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"'{names[0]}' 태그가 이미 있었다면 덮어쓰이기 전 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git tag <name> <hash> 로 복구).",
                            is_multiline, is_chained, command, is_bash,
                        )

                if subl == "rebase" and not any(a in rest for a in REBASE_SAFE_ACTIONS):
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git rebase", is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"rebase 시작 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --hard <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "commit" and "--amend" in rest:
                    backup = _backup_refs(["HEAD"], is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"amend 전 이전 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --soft <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl in ("filter-branch", "filter-repo"):
                    backup = _backup_all_branch_tips(is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"저장소 히스토리 재작성 전 모든 로컬 브랜치 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "reflog" and _first_non_option(rest) in ("expire", "delete"):
                    backup = _backup_reflog_reachable(is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"reflog 로만 도달 가능하던 커밋들을 refs/claude-backups/ 에 고정했습니다 ({BACKUP_HINT} git stash apply <hash> 또는 git branch <name> <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "gc" and any(t in ("--prune=now", "--prune=all") for t in rest):
                    backup = _backup_dangling_commits(is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"즉시 삭제될 도달 불가능한 커밋들을 refs/claude-backups/ 에 고정했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "switch" and _has_force_flag(rest):
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git switch --force", is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"전환 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                        is_multiline, is_chained, command, is_bash,
                    )

                if subl == "checkout":
                    if _has_force_flag(rest):
                        backup = _backup_head_and_worktree("claude-auto-backup: pre git checkout --force", is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"전환 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            is_multiline, is_chained, command, is_bash,
                        )
                    if "--" in rest or "." in rest:
                        _emit_backup_prepend(_checkout_paths(rest), cmd_parts, line, is_multiline, is_chained, command, quote, is_bash)

                if subl == "restore" and _restore_touches_worktree(rest):
                    _emit_backup_prepend(_restore_paths(rest), cmd_parts, line, is_multiline, is_chained, command, quote, is_bash)

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
