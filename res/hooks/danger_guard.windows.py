#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, 유저 레벨, Windows)

Bash 툴(Git Bash)과 PowerShell 툴(네이티브, Git for Windows 미설치 시 기본으로 쓰임)
양쪽 모두를 대상으로 한다. 둘 다 tool_input.command 에 실행할 명령 문자열을 담는다.

정책:
  1) rm / del / erase / Remove-Item / rd / rmdir  → send_to_trash.py 로 치환 (allow + updatedInput)
     핵심 원칙: **치환된 명령이 원래 명령보다 더 많이 지울 수 있으면 안 된다.** rm 은
     `rm -rf .` 을 거부하지만 휴지통 이동 도구는 거부하지 않으므로, 그대로 치환하면 아무 일도
     없었을 명령이 현재 디렉터리를 통째로 휴지통에 넣는다. 그래서 아래를 모두 검사한다:
       - 드라이브 루트(C 드라이브 전체, / 또는 ~) → deny
       - 말단이 `.`/`..` 인 경로(`.`, `./`, `..`, `sub/.`) → deny (rm 과 동일)
       - cwd 기준으로 풀면 루트/홈이 되는 상대경로 → deny
       - 와일드카드는 cwd 기준으로 직접 확장해 절대경로로 고정하고, 확장된 경로 각각에
         위 검사를 다시 적용한다. 매칭 0개/중괄호 확장이면 deny, 100개 초과면 ask.
       - `rm -f` / `del /f` 의 force 의미는 send_to_trash.py 의 -f 로 넘긴다.
     send2trash 가 설치되어 있지 않으면 치환할 수 없으므로 fail-closed 로 deny.
     멀티라인 또는 체이닝(&&/;) 스크립트 안에 섞여 있으면 자동 치환 대신 deny.
     sudo/command/env/exec/… 래퍼 접두어와 /bin/rm, rm.exe 같은 표기는 벗겨서 동일하게 검사한다.
  2) git: 서브커맨드를 정확히 판정해 세분화한다(git_subcommand). 순진하게 "push in args" 로
     매칭하면 `git stash push`(작업을 저장하는 안전한 명령)까지 막히므로, 전역 옵션(-C/-c/…)을
     건너뛰고 실제 서브커맨드를 뽑아 아래 규칙을 적용한다.
       push  : 대상 원격 브랜치 이름에 '/' 가 있으면(feature/*, fix/* 등 곁다리 브랜치) 통과.
               '/' 가 없으면(main/master/develop 등 보호 브랜치로 간주) 브랜치 이름을 명시하며
               ask. --all/--mirror 처럼 특정 브랜치로 좁힐 수 없으면 ask. force 여부는 통과/ask
               판정에 영향 없음(브랜치 이름만 기준) — ask 사유 문구에만 force 여부를 표시한다.
               단 원격 브랜치 '삭제'(--delete/-d, 빈 src refspec `origin :branch`)는 브랜치
               이름과 무관하게 ask — 원격 히스토리는 로컬 백업으로 되돌릴 수 없다.
       backup 후 allow : reset --hard, clean -f*(단 -n/--dry-run 제외), stash drop|clear,
               branch -D, branch -M(대상 이름이 이미 있었으면), tag -d, tag -f(대상이 이미
               있었으면), rebase(새로 시작하는 경우), commit --amend, filter-branch/filter-repo,
               reflog expire|delete, gc --prune=now|all, checkout/switch --force|-B|-C(강제 전환),
               worktree remove --force(지워질 워크트리 안의 추적/미추적 파일을 -C 로 스냅샷),
               checkout -- <path>/checkout ./restore(워킹트리) → 실행 전 refs/claude-backups/
               <timestamp>/<대상> 에 되돌릴 대상을 백업한 뒤 원본 명령을 그대로 이어서 실행한다
               (자동치환). git stash create 는 추적 안 된 파일을 담지 못하는 한계가 있어(검증됨)
               clean 은 별도 스크래치 인덱스로 추적 안 된 파일까지 스냅샷하며, -x/-X 로 무시된
               파일까지 지우는 경우엔 `git add -Af` 로 .gitignore 대상까지 담는다.
               백업 스니펫은 bash 에선 전부 `&&` 로, PowerShell 에선 단계마다 $LASTEXITCODE 를
               확인해 실패 시 `exit 1` 로 끊어, 한 단계라도 실패하면 뒤의 원본 파괴적 명령이
               실행되지 않는다(fail-closed). 자동치환에는 두 가지 형태가 있다:
                 - 한 줄짜리 명령: `백업 <구분자> 원본` 으로 통째로 갈아끼운다.
                 - 멀티라인 블록: 파괴적 명령이 한 줄 통째로 있으면 그 줄 '바로 앞'에 백업 줄만
                   끼워 넣고 나머지 줄은 원문 그대로 둔다. 블록 전체를 갈아끼우면 나머지 줄이
                   소리 없이 사라지고, 블록 맨 앞에 백업을 붙이면 앞선 cd 가 반영되기 전 cwd 를
                   백업해 엉뚱한 저장소를 잡는다 — 줄 삽입은 둘 다 피한다. 삽입 판정은 모든
                   줄·파이프 하류까지 검사한 뒤 확정하므로 뒤쪽의 deny/ask 가 항상 우선한다.
               줄 안에서 체이닝된 경우(`cd X && git reset --hard`)는 원문 문자열을 그 앞
               연산자에서 잘라 백업을 사이에 끼운다 — 백업이 cd 뒤에서 돌아야 '실제로 명령이
               돌 저장소'를 잡는다. 자를 위치는 '잘린 두 조각을 다시 파싱하면 원래 토큰 열이
               복원되는가' 로 검증해, 따옴표나 $( ) 안의 연산자에서 잘리면 ask 로 폴백한다.
               `a || git reset --hard` 는 `(a||백업) && git reset` 으로 결합 방향이 바뀌어
               실행되지 않아야 할 명령이 실행되므로 || 앞에서는 자르지 않는다.
               히어독·줄에 걸친 따옴표라 줄 단위로 쪼갤 수 없거나, -C/--git-dir/--work-tree 로
               '다른 저장소'를 대상으로 삼아 백업 대상을 안전하게 특정할 수 없을 때도 ask 다.
       pass  : stash push/pop/apply/list, reset --soft/--mixed, clean -n, branch -d,
               checkout/switch <branch>, restore --staged, rebase --continue/--abort/--skip,
               commit(amend 아님), 그 외 안전한 서브커맨드
  3) format / diskpart / mkfs / fdisk / Clear-Disk / Format-Volume / dd of=... → deny (디스크 레벨 파괴적)
     Clear-Content / reg delete / chmod 777 → ask
  4) curl|bash, irm ... | iex 같은 "원격 스크립트를 바로 실행 셸로 파이프" 패턴 → deny
  5) shutdown / Restart-Computer / Stop-Computer → ask
  6) bash/sh -c "inner" 패턴: 내부 명령을 추출해 동일 규칙으로 추가 검사한다.
  7) 래퍼 접두어는 벗겨서 실제 명령을 위 규칙으로 검사한다. 두 종류가 있고 번갈아 벗긴다:
       - 바로 명령이 오는 것: sudo / doas / command / exec / builtin / env / nohup / time / busybox
       - 자기 인자를 먼저 받는 것: timeout / nice / ionice / stdbuf / setsid / taskset / chrt
         (`timeout 5 rm -rf .` 은 첫 인자 `5` 를 명령으로 보고 멈춰 rm 보호가 통째로
          무력화됐다 — 실측 확인. WSL/Git Bash 에서 그대로 쓰이므로 여기에도 필요하다.)
  8) 대상을 미리 볼 수 없는 대량 삭제 → ask (치환도 확장도 불가능하므로 판정을 넘긴다):
       - find … -delete / -exec|-execdir|-ok|-okdir <삭제명령>
       - xargs|parallel <삭제명령>  (파이프 하류에 있어도 잡는다)

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
import glob
import re
import os
import datetime
import subprocess

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HOOKS_DIR, "guard.log")
SEND_TO_TRASH = os.path.join(HOOKS_DIR, "send_to_trash.py")


def read_event_json() -> str:
    """stdin 에서 훅 이벤트 JSON 을 읽는다. 선행 BOM(U+FEFF)은 벗겨낸다.

    BOM 이 남아 있으면 json.loads 가 실패하고, 이 훅은 파싱 실패를 '판정할 수 없는 입력'으로
    보고 조용히 exit 0 한다 — 가드가 통째로 무력화되는데 아무 신호도 남지 않는다. 실제로
    Windows PowerShell 5.1 의 Process.StandardInput 이 이 상황을 만든다: AutoFlush StreamWriter
    라 스트림에 접근하는 순간 인코딩 preamble 을 먼저 흘려보내는데, .NET Framework 에는
    StandardInputEncoding 이 없어 호출부에서 끌 수가 없다. RFC 8259 도 파서가 BOM 을 무시하는
    것을 허용하므로, 받는 쪽에서 벗기는 것이 옳다."""
    return sys.stdin.read().lstrip("\ufeff")


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


# Git Bash(MSYS)는 드라이브를 `/c/Users/pi` 로 표기한다. 이 훅의 Bash 툴이 곧 Git Bash 이므로
# 이게 그쪽의 '평범한' 절대경로 표기다. 정규화하지 않으면 같은 홈 디렉터리인데도 `~`, `$HOME`,
# `"C:\Users\pi"` 는 막히고 `/c/Users/pi` 만 통과한다 — 실제로 그런 구멍이 있었다.
# 이 훅은 Windows 전용이라 안전한 변환이다 (진짜 POSIX 에서는 /c/... 가 평범한 디렉터리다).
_MSYS_DRIVE_RE = re.compile(r'^/([A-Za-z])(?=/|$)')


def _from_msys_path(path: str) -> str:
    """`/c/Users/pi` → `C:\\Users\\pi`. MSYS 드라이브 표기가 아니면 원본 그대로."""
    m = _MSYS_DRIVE_RE.match(path)
    if not m:
        return path
    return m.group(1).upper() + ":\\" + path[m.end():].lstrip("/").replace("/", "\\")


def _is_root_or_home_literal(path: str) -> bool:
    for candidate in (path, _from_msys_path(path)):
        if ROOT_RE.match(candidate):
            return True
        if not _HOME_DIR or _HOME_DIR in ("/", "\\"):
            continue
        stripped = candidate.rstrip("/\\*") if candidate not in ("/", "\\", "") else candidate
        if os.path.normcase(os.path.normpath(stripped)) == os.path.normcase(os.path.normpath(_HOME_DIR)):
            return True
    return False


def _is_dot_target(path: str) -> bool:
    """rm 이 거부하는 형태인가 — 경로의 말단 성분이 `.` 또는 `..` 인지.

    GNU rm 은 `.`, `./`, `..`, `sub/.` 를 모두 거부하지만(실측 확인) 휴지통 이동
    도구는 거부하지 않는다. 이 검사가 없으면 치환이 원래 명령보다 위험해진다 —
    `rm -rf .` 가 휴지통 치환을 타면서 현재 디렉터리가 통째로 사라진다.
    """
    stripped = path.rstrip("/\\") or path
    return os.path.basename(stripped.replace("\\", "/")) in (".", "..")


def _resolves_to_root_or_home(path: str, cwd: str) -> bool:
    """cwd 기준으로 해석했을 때 드라이브 루트나 홈을 가리키는가.

    _is_root_or_home_literal 은 문자열만 보므로 `..\\..\\..\\Users\\pi` 처럼
    해석해야 홈이 되는 경로를 놓친다.
    """
    try:
        resolved = os.path.realpath(os.path.join(cwd, os.path.expanduser(_from_msys_path(path))))
    except (OSError, ValueError):
        return False
    tail = os.path.splitdrive(resolved)[1]
    if tail in ("", "/", "\\", os.sep):
        return True
    if not _HOME_DIR or _HOME_DIR in ("/", "\\"):
        return False
    return os.path.normcase(resolved) == os.path.normcase(os.path.realpath(_HOME_DIR))


# 와일드카드는 셸이 확장하는데 훅이 인용해 버리면 확장이 죽어 명령이 조용히 실패한다.
# 인용을 빼면 반대로 무엇이 지워질지 모른 채 통과시키게 된다. 그래서 훅이 cwd 기준으로
# 직접 확장해 구체 경로로 바꾼 뒤, 확장된 경로 각각에 안전 검사를 적용한다.
GLOB_META_RE = re.compile(r"[*?\[]")
BRACE_RE = re.compile(r"[{}]")
MAX_TRASH_TARGETS = 100


def expand_delete_targets(args: list, cwd: str) -> tuple:
    """와일드카드를 cwd 기준으로 확장한다. 반환: (확장된 경로 리스트, 실패 사유 또는 None)."""
    expanded = []
    for a in args:
        if BRACE_RE.search(a):
            return [], f"중괄호 확장이 포함된 대상('{a}')은 훅이 해석할 수 없어 차단합니다."
        if not GLOB_META_RE.search(a):
            expanded.append(a)
            continue
        # 확장 결과는 절대경로로 고정한다 — 훅이 본 cwd 와 실제 실행 cwd 가 어긋나도
        # 엉뚱한 디렉터리의 파일이 지워지지 않는다.
        pattern = a if os.path.isabs(a) else os.path.join(cwd, a)
        matches = sorted(glob.glob(pattern))
        if not matches:
            return [], f"'{a}' 와 일치하는 파일이 없습니다."
        expanded.extend(matches)
    return expanded, None


def _is_force_flag(arg: str) -> bool:
    """force 플래그인가. rm 계열의 `-f`/`-rf` 와 del/rd 계열의 `/f` 를 모두 본다."""
    lowered = arg.lower()
    if lowered in ("-f", "--force", "/f"):
        return True
    return lowered.startswith("-") and not lowered.startswith("--") and "f" in lowered[1:]


# 실제 명령 앞에 붙어 가드를 빠져나가게 하는 래퍼들. 이걸 벗기지 않으면
# `command rm -rf x`, `env rm -rf x` 가 아무 판정 없이 통과한다(실측 확인).
COMMAND_WRAPPERS = {"sudo", "doas", "command", "exec", "builtin", "env", "nohup", "time", "busybox"}
ENV_ASSIGN_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

# 자기 인자를 먼저 받는 래퍼. `timeout 5 rm -rf .` 은 COMMAND_WRAPPERS 방식으로 못 벗긴다 —
# 첫 인자 `5` 를 명령으로 보고 멈추기 때문이다. 그 결과 rm 보호가 통째로 무력화된다(실측).
# WSL/Git Bash 에서 이 래퍼들이 그대로 쓰이므로 Windows 훅에도 동일하게 필요하다.
ARG_WRAPPERS = {"timeout", "nice", "ionice", "stdbuf", "setsid", "taskset", "chrt"}
ARG_WRAPPER_VALUE_OPTS = {
    "-s", "--signal", "-k", "--kill-after",              # timeout
    "-n", "--adjustment",                                # nice
    "-c", "--class", "--classdata", "--cpu-list",        # ionice, taskset
    "-p", "--pid",                                       # ionice, chrt
    "-i", "-o", "-e", "--input", "--output", "--error",  # stdbuf
}
# 래퍼가 명령 앞에 두는 위치 인자(timeout 의 5s, taskset 의 0x3, chrt 의 우선순위 99).
# 전부 숫자로 시작한다 — 명령 이름은 숫자로 시작하지 않으므로 이걸로 구분한다.
WRAPPER_NUMERIC_ARG_RE = re.compile(r'^(0x[0-9a-fA-F]+|[0-9][0-9.,:+-]*[a-zA-Z]*)$')

# 대상을 표준입력으로 받아 실행하는 래퍼. 훅이 대상을 볼 수 없어 치환도 확장도 불가능하다.
STDIN_WRAPPERS = {"xargs", "parallel"}
XARGS_VALUE_OPTS = {
    "-a", "--arg-file", "-d", "--delimiter", "-E", "-I", "-i", "--replace",
    "-L", "-l", "--max-lines", "-n", "--max-args", "-P", "--max-procs",
    "-s", "--max-chars",
}

# find -exec / xargs 뒤에 오면 대량 삭제인 명령들. 위 DELETE_COMMANDS(PowerShell
# 삭제 커맨드릿 포함)와는 쓰임이 달라 이름을 분리한다 — 같은 이름을 쓰면 덮어써서
# remove-item 판정이 조용히 사라진다(실제로 겪음).
EXEC_DELETE_COMMANDS = {"rm", "unlink", "shred", "srm", "wipe", "del", "erase"}
FIND_EXEC_OPTS = {"-exec", "-execdir", "-ok", "-okdir"}


def _command_base(token: str) -> str:
    """실행 파일 토큰에서 명령 이름을 뽑는다 — 경로와 `.exe` 확장자를 벗긴다.

    `/bin/rm`, `C:\\tools\\rm.exe` 처럼 적어 가드를 빠져나가지 못하게 한다.
    Windows 경로 구분자는 os.path 가 POSIX 에서 인식하지 못하므로 먼저 통일한다.
    """
    name = os.path.basename(token.replace("\\", "/")).lower()
    return name[:-4] if name.endswith(".exe") else name


def _peel_arg_wrapper(args: list) -> list:
    """ARG_WRAPPERS 의 자기 인자를 건너뛰고 실제 명령부터 시작하는 토큰 목록을 돌려준다.

    옵션(-로 시작) → 값을 받는 옵션이면 그 값까지 → 숫자로 시작하는 위치 인자 순으로
    건너뛴다. 명령을 특정하지 못하면 빈 목록을 돌려준다(판정 포기).

    Args:
        args: 래퍼 이름을 제외한 나머지 토큰.

    Returns:
        실제 명령으로 시작하는 토큰 목록. 특정 실패 시 빈 목록.
    """
    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("-"):
            i += 2 if tok in ARG_WRAPPER_VALUE_OPTS else 1
            continue
        if WRAPPER_NUMERIC_ARG_RE.match(tok):
            i += 1
            continue
        return args[i:]
    return []


def _stdin_wrapper_target(args: list):
    """xargs/parallel 이 실행할 명령 이름을 돌려준다. 특정하지 못하면 None."""
    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("-"):
            i += 2 if tok in XARGS_VALUE_OPTS else 1
            continue
        return _command_base(tok)
    return None


def _find_delete_reason(args: list):
    """find 명령이 파일을 지우는지 판정하고, 지운다면 사유 문자열을 돌려준다."""
    for i, tok in enumerate(args):
        if tok == "-delete":
            return "find -delete"
        if tok in FIND_EXEC_OPTS and i + 1 < len(args):
            if _command_base(args[i + 1]) in EXEC_DELETE_COMMANDS:
                return "find {} {}".format(tok, args[i + 1])
    return None


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


# 최상위 명령 구분자. 2글자를 먼저 봐야 `||` 가 `|` 두 개로 쪼개지지 않는다.
COMMAND_SEPARATORS = ("&&", "||", ";", "|")


def separate_operators(line: str, ps_style: bool = False) -> str:
    """따옴표 밖의 &&/||/;/| 앞뒤에 공백을 넣어, shlex 가 이들을 독립 토큰으로 뽑게 한다.

    split_commands() 는 토큰이 구분자와 정확히 일치할 때만 나누는데, shlex 는 구분자가 앞
    토큰에 붙어 있으면 떼어내지 않는다 — `-Confirm:$false;` 와 `build;ls` 가 각각 한 토큰이
    된다. 그러면 is_chained 가 False 로 나와 '체이닝 안의 삭제는 자동 치환하지 않는다'는
    방어선이 발동하지 않고, `-` 로 시작하지 않는 토큰이 전부 휴지통 대상 목록으로 들어간다.
    실제로 guard.log 에 뒤 명령의 `-C <repo>` 인자 때문에 레포 루트가 삭제 대상에 포함된
    기록이 남아 있다. send_to_trash.py 는 인자 하나가 실패해도 다음 인자를 계속 처리한다.

    토큰을 사후에 쪼개는 방법은 쓸 수 없다 — shlex 를 거치고 나면 `rm "a;b.txt"` 의 `a;b.txt`
    와 `rm a;b.txt` 의 `a;b.txt` 를 구별할 수 없어, 따옴표로 감싼 파일명을 잘라버린다. 그래서
    원문을 문자 단위로 훑어 따옴표·서브셸 밖의 구분자만 떼어낸다.


    알려진 한계: 짝이 맞지 않는 여는 괄호 뒤의 구분자는 서브셸 안으로 보여 떼어내지 않는다
    (`echo (;rm -rf /`). 수정 전에도 놓치던 경우라 회귀는 아니고, 그런 줄은 bash/PowerShell
    양쪽에서 문법 오류라 애초에 실행되지 않는다.
    반환값은 토크나이즈 전용이다. 원문 줄은 그대로 둬야 _split_line_at_operator 처럼 원문을
    잘라 쓰는 쪽이 어긋나지 않는다 (공백을 끼우면 offset 이 밀린다).
    """
    out = []
    i = 0
    n = len(line)
    quote = ""
    depth = 0
    while i < n:
        ch = line[i]
        if quote:
            if ps_style and quote == '"' and ch == "`":       # PowerShell: "..." 안 백틱 이스케이프
                out.append(line[i:i + 2])
                i += 2
                continue
            if not ps_style and quote == '"' and ch == "\\":  # POSIX: "..." 안 백슬래시 이스케이프
                out.append(line[i:i + 2])
                i += 2
                continue
            if ch == quote:
                # PowerShell 은 따옴표를 두 번 써서 이스케이프한다 ('' 와 "").
                if ps_style and i + 1 < n and line[i + 1] == quote:
                    out.append(line[i:i + 2])
                    i += 2
                    continue
                quote = ""
            out.append(ch)
            i += 1
            continue

        if ch == ("`" if ps_style else "\\"):                 # 따옴표 밖 이스케이프 (`find … \;`)
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            sep = next((s for s in COMMAND_SEPARATORS if line.startswith(s, i)), None)
            if sep:
                out.append(" " + sep + " ")
                i += len(sep)
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def split_commands(parts: list) -> list:
    """shlex 토큰 목록을 &&, ||, ; 기준으로 서브커맨드 리스트로 분리한다.

    구분자가 독립 토큰으로 들어와야 동작한다 — separate_operators() 가 그 조건을 보장한다."""
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
CHAINED_BACKUP_ASK = "여러 줄·체이닝된 명령이거나 다른 저장소(-C/--git-dir)를 대상으로 해서, 되돌릴 대상을 안전하게 특정해 백업할 수 없습니다. 계속할까요?"

# 명령의 대상 저장소를 현재 디렉터리 밖으로 바꾸는 git 전역 옵션. 백업 스니펫은 이 옵션을
# 물려받지 않고 cwd 에서 실행되므로, 이게 붙으면 '엉뚱한 저장소를 백업하고 진짜 대상은 무방비로
# 파괴'하는 상황이 된다. 그래서 백업 경로에서는 자동치환 대신 ask 로 폴백한다.
GIT_REPO_REDIRECT_OPTS = {"-C", "--git-dir", "--work-tree", "--namespace"}
GIT_REPO_REDIRECT_PREFIXES = ("--git-dir=", "--work-tree=", "--namespace=")


def _git_repo_redirected(own_args: list) -> bool:
    """git 명령이 cwd 가 아닌 다른 저장소/워크트리를 대상으로 삼는지."""
    for a in own_args:
        if a in GIT_REPO_REDIRECT_OPTS or a.startswith(GIT_REPO_REDIRECT_PREFIXES):
            return True
    return False


def _push_is_delete(rest: list) -> bool:
    """원격 브랜치를 '삭제'하는 push 인지. `--delete`/`-d` 플래그 또는 src 가 빈 refspec
    (`git push origin :branch`). 원격 히스토리는 refs/claude-backups/ 로 되돌릴 수 없으므로,
    브랜치 이름에 '/' 가 있어도(곁다리 브랜치여도) 통과시키지 않는다."""
    for t in rest:
        if t == "--delete" or "d" in _short_flag_chars(t):
            return True
        if not t.startswith("-") and t.startswith(":") and len(t) > 1:
            return True
    return False


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


# git push 옵션 중 '다음 토큰'을 값으로 소비하는 것들. 이걸 걸러내지 않으면 그 값이 위치
# 인자로 잡혀 remote 자리로 밀려 들어간다 — `git push -o ci.skip origin feature/x` 가
# "'origin' 브랜치로 push 하려 합니다" 로 오탐되던 원인.
#
# --repo 는 남겨둘 것: `git push --repo origin feature/x` 를 git 은 "repository=feature/x,
# refspec 없음(=현재 브랜치를 push)" 으로 읽는다(실측). --repo 를 여기서 빼면 origin 이
# remote, feature/x 가 refspec 으로 잡혀 '곁다리 브랜치 push' 로 통과시켜 버린다.
PUSH_VALUE_OPTS = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}


def _push_positionals(rest: list) -> list:
    """git push 인자에서 위치 인자(remote, refspec)만 뽑는다."""
    out = []
    skip_next = False
    for t in rest:
        if skip_next:
            skip_next = False
            continue
        if t in PUSH_VALUE_OPTS:
            skip_next = True
            continue
        if t.startswith("-"):
            continue
        out.append(t)
    return out


def _push_target_branches(rest: list, cwd: str):
    """git push 인자에서 실제로 갱신/삭제될 원격 브랜치 이름들을 뽑는다.
    반환: (branches, broad) — broad 면 --all/--mirror 등으로 특정 브랜치로 좁힐 수 없다."""
    if any(f in rest for f in PUSH_BROAD_FLAGS):
        return [], True
    positional = _push_positionals(rest)
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


def _clean_removes_ignored(rest: list) -> bool:
    """git clean 이 .gitignore 대상까지 지우는지(-x: 무시된 파일도 함께, -X: 무시된 파일만).
    이 경우 기본 `git add -A` 스냅샷으로는 .env/node_modules/빌드 산출물이 백업에서 빠진다."""
    return any("x" in _short_flag_chars(t) or "X" in _short_flag_chars(t) for t in rest)


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
        # 모든 단계를 `&&` 로만 잇는다. 예전엔 stash create 앞에 `;` 가 있었는데, `;` 는 앞선
        # 실패의 종료 상태를 덮어써서 마지막 `[ -z "$_bk_stash" ]` 가 참이 되어 전체가 성공으로
        # 보고되고, 뒤에 이어붙인 원본 파괴적 명령이 백업 없이 실행됐다(POSIX 판에서 실측 확인).
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$ && '
            '_bk_head=$(git rev-parse HEAD) && '
            'git update-ref "refs/claude-backups/${_bk_ts}/head" "$_bk_head" && '
            '_bk_stash=$(git stash create ' + shlex.quote(reason) + ') && '
            '{ [ -z "$_bk_stash" ] || git update-ref "refs/claude-backups/${_bk_ts}/worktree" "$_bk_stash"; }'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
        '$bkHead = git rev-parse HEAD; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        'git update-ref "refs/claude-backups/$bkTs/head" $bkHead; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkStash = git stash create ' + quote_ps(reason) + '; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        # 마지막 update-ref 의 실패도 반드시 잡아야 한다 — 여기서 놓치면 스태시 커밋이 ref 로
        # 고정되지 않은 채(=GC 대상) 원본 파괴적 명령이 이어서 실행된다.
        'if ($bkStash) { git update-ref "refs/claude-backups/$bkTs/worktree" $bkStash; if ($LASTEXITCODE -ne 0) { exit 1 } }'
    )


def _backup_full_snapshot(reason: str, is_bash: bool, include_ignored: bool) -> str:
    """추적 + 추적 안 된 파일 전체를 스냅샷 커밋으로 백업한다. git clean 전용 — git stash create
    는 추적 안 된 파일을 담지 못하는 한계가 실측으로 확인되어, 별도 인덱스로 실제 인덱스/워킹트리를
    전혀 건드리지 않고 전체 스냅샷을 만든다.

    include_ignored 는 `git clean -x/-X`(무시된 파일까지 삭제) 전용이다. 기본 `git add -A` 는
    .gitignore 대상을 담지 않아, -x 로 지워질 .env/node_modules/빌드 산출물이 백업에서 통째로
    빠진 채 영구 소실됐다(실측 확인). 이 경우에만 `-f` 를 붙인다 — 항상 붙이면 -x 없는 평범한
    clean 에서도 node_modules 전체를 커밋해 느려지기 때문이다."""
    add_cmd = 'git add -Af -- .' if include_ignored else 'git add -A -- .'
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$ && '
            '_bk_gitdir=$(git rev-parse --git-dir) && '
            '_bk_idx="$_bk_gitdir/claude-guard-index" && '
            'GIT_INDEX_FILE="$_bk_idx" ' + add_cmd + ' && '
            '_bk_tree=$(GIT_INDEX_FILE="$_bk_idx" git write-tree) && '
            '_bk_h=$(git commit-tree "$_bk_tree" -p HEAD -m ' + shlex.quote(reason) + ') && '
            'git update-ref "refs/claude-backups/${_bk_ts}/snapshot" "$_bk_h"'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
        '$bkGitDir = git rev-parse --git-dir; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkIdx = Join-Path $bkGitDir "claude-guard-index"; '
        '$env:GIT_INDEX_FILE = $bkIdx; '
        + add_cmd + '; '
        'if ($LASTEXITCODE -ne 0) { Remove-Item Env:\\GIT_INDEX_FILE -ErrorAction SilentlyContinue; exit 1 }; '
        '$bkTree = git write-tree; '
        'Remove-Item Env:\\GIT_INDEX_FILE -ErrorAction SilentlyContinue; '
        'if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkH = git commit-tree $bkTree -p HEAD -m ' + quote_ps(reason) + '; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        # 마지막 update-ref 의 실패도 반드시 잡아야 한다 — 여기서 놓치면 스냅샷 커밋이 ref 로
        # 고정되지 않은 채(=GC 대상) 뒤이어 git clean 이 실행된다. bash 경로는 _fail_closed 가
        # 같은 역할을 하므로, 이 검사가 빠지면 PowerShell 만 fail-open 인 비대칭이 생긴다.
        'git update-ref "refs/claude-backups/$bkTs/snapshot" $bkH; if ($LASTEXITCODE -ne 0) { exit 1 }'
    )


def _dq_embed(token: str, is_bash: bool):
    """경로 토큰을 백업 스니펫에 큰따옴표로 감싸 넣는다. 불가능하면 None(→ ask).

    리터럴로 따옴표 처리하면 안 된다 — `git worktree remove --force "$SCRATCH/clean"` 의
    변수가 확장되지 않아 존재하지 않는 경로를 백업하려다 실패하고, fail-closed 때문에 원본
    명령까지 못 돌게 된다. 큰따옴표는 변수 확장과 공백을 동시에 살린다. 위험 문자는 셸마다
    다르다 — PowerShell 의 큰따옴표 안에서 역슬래시는 평범한 문자라(이스케이프 문자는 백틱),
    `C:\\repo\\wt` 같은 정상적인 Windows 경로까지 막지 않으려면 bash 와 다르게 판정해야 한다."""
    unsafe = ('"', '`', '\\', '$(') if is_bash else ('"', '`', '$(')
    if not token or any(bad in token for bad in unsafe):
        return None
    return '"' + token + '"'


def _backup_worktree_snapshot(path_expr: str, reason: str, is_bash: bool) -> str:
    """`git worktree remove --force` 로 지워질 워크트리의 추적/미추적 파일을 스냅샷 커밋으로
    백업한다. git 은 더티한 워크트리를 그냥은 지우지 않고 --force 를 요구하므로(실측 확인),
    --force 가 붙었다는 것 자체가 '버릴 미커밋 변경이 실제로 있다'는 신호다.

    백업 대상이 cwd 가 아니라 '지워질 워크트리' 라서 모든 git 호출에 -C 를 붙인다. 그냥
    cwd 에서 스냅샷하면 본 저장소를 백업하고 정작 사라질 워크트리는 무방비가 된다.
    refs/claude-backups/ 는 워크트리별 ref 가 아니라 저장소 전체가 공유하는 ref 라,
    워크트리가 사라진 뒤에도 본 저장소에서 그대로 조회·복구할 수 있다(실측 확인)."""
    if is_bash:
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$ && '
            '_bk_wt=' + path_expr + ' && '
            '_bk_gitdir=$(git -C "$_bk_wt" rev-parse --absolute-git-dir) && '
            '_bk_idx="$_bk_gitdir/claude-guard-index" && '
            'GIT_INDEX_FILE="$_bk_idx" git -C "$_bk_wt" add -A -- . && '
            '_bk_tree=$(GIT_INDEX_FILE="$_bk_idx" git -C "$_bk_wt" write-tree) && '
            '_bk_h=$(git -C "$_bk_wt" commit-tree "$_bk_tree" -p HEAD -m ' + shlex.quote(reason) + ') && '
            'git -C "$_bk_wt" update-ref "refs/claude-backups/${_bk_ts}/worktree-snapshot" "$_bk_h"'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
        '$bkWt = ' + path_expr + '; '
        '$bkGitDir = git -C $bkWt rev-parse --absolute-git-dir; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkIdx = Join-Path $bkGitDir "claude-guard-index"; '
        '$env:GIT_INDEX_FILE = $bkIdx; '
        'git -C $bkWt add -A -- .; '
        'if ($LASTEXITCODE -ne 0) { Remove-Item Env:\\GIT_INDEX_FILE -ErrorAction SilentlyContinue; exit 1 }; '
        '$bkTree = git -C $bkWt write-tree; '
        'Remove-Item Env:\\GIT_INDEX_FILE -ErrorAction SilentlyContinue; '
        'if ($LASTEXITCODE -ne 0) { exit 1 }; '
        '$bkH = git -C $bkWt commit-tree $bkTree -p HEAD -m ' + quote_ps(reason) + '; if ($LASTEXITCODE -ne 0) { exit 1 }; '
        'git -C $bkWt update-ref "refs/claude-backups/$bkTs/worktree-snapshot" $bkH; if ($LASTEXITCODE -ne 0) { exit 1 }'
    )


def _worktree_remove_force_path(rest: list):
    """`git worktree remove --force <path>` 의 <path>. remove 가 아니거나 --force 가 없으면
    None — --force 없는 remove 는 워크트리가 더티하면 git 이 알아서 거부하므로 손실이 없다."""
    if _first_non_option(rest) != "remove":
        return None
    if not any(t == "--force" or "f" in _short_flag_chars(t) for t in rest):
        return None
    positionals = [t for t in rest if not t.startswith("-")]
    return positionals[1] if len(positionals) > 1 else None


def _backup_refs(ref_exprs: list, is_bash: bool) -> str:
    """주어진 각 ref 표현식(브랜치/태그 이름 등)이 가리키는 커밋을, 삭제/재작성되기 전에
    백업한다. 대상을 못 찾으면(예상과 다름) fail-closed 로 원본 명령도 막는다."""
    if is_bash:
        quoted = " ".join(shlex.quote(r) for r in ref_exprs)
        return (
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$; '
            'for _bk_r in ' + quoted + '; do '
            '_bk_h=$(git rev-parse "$_bk_r") && git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h" || exit 1; '
            'done'
        )
    quoted_ps = ",".join(quote_ps(r) for r in ref_exprs)
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
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
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$; '
            'for _bk_r in ' + quoted + '; do '
            '_bk_h=$(git rev-parse --verify -q "$_bk_r" 2>/dev/null) && '
            'git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h"; '
            'done; true'
        )
    quoted_ps = ",".join(quote_ps(r) for r in ref_exprs)
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
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
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$; '
            "for _bk_r in $(git for-each-ref refs/heads --format='%(refname:short)'); do "
            '_bk_h=$(git rev-parse "$_bk_r") && git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h" || exit 1; '
            'done'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
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
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$; '
            '_bk_i=0; '
            'for _bk_h in $(git stash list --format=%H); do '
            'git update-ref "refs/claude-backups/${_bk_ts}/stash${_bk_i}" "$_bk_h"; _bk_i=$((_bk_i+1)); '
            'done'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
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
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$; '
            '_bk_i=0; '
            "for _bk_h in $(git reflog show --all --format=%H 2>/dev/null | sort -u); do "
            'git update-ref "refs/claude-backups/${_bk_ts}/reflog${_bk_i}" "$_bk_h" 2>/dev/null; _bk_i=$((_bk_i+1)); '
            'done'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
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
            '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$; '
            '_bk_i=0; '
            "for _bk_h in $(git fsck --no-reflog --unreachable 2>/dev/null | awk '$1==\"unreachable\" && $2==\"commit\"{print $3}'); do "
            'git update-ref "refs/claude-backups/${_bk_ts}/dangling${_bk_i}" "$_bk_h" 2>/dev/null; _bk_i=$((_bk_i+1)); '
            'done'
        )
    return (
        '$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
        '$bkI = 0; '
        '$bkList = git fsck --no-reflog --unreachable 2>$null | '
        "Where-Object { $_ -match '^unreachable commit (\\S+)' } | ForEach-Object { $matches[1] }; "
        'foreach ($bkH in $bkList) { '
        'git update-ref "refs/claude-backups/$bkTs/dangling$bkI" $bkH 2>$null; $bkI++ '
        '}'
    )


def _fail_closed(backup_snippet: str, is_bash: bool) -> str:
    """bash 경로에서 백업 스니펫을 `{ ... } || { 메시지; exit 1; }` 로 감싼다. 스니펫 안의 어떤
    단계가 실패하든 셸이 즉시 끊겨, 뒤에 `&&` 로 이어붙인 원본 파괴적 명령이 실행되지 않는다.
    PowerShell 경로는 스니펫 자체가 단계마다 $LASTEXITCODE 를 보고 `exit 1` 하므로 감싸지 않는다."""
    if not is_bash:
        return backup_snippet
    return (
        "{ " + backup_snippet + "; } || "
        '{ echo "claude-guard: 백업에 실패해 원본 명령을 실행하지 않았습니다." >&2; exit 1; }'
    )


# 멀티라인 블록에서 '파괴적 명령이 있는 줄 바로 앞'에 끼워 넣을 백업 스니펫 예약 목록
# ({원본 줄 인덱스: 스니펫}). 명령 전체를 `백업 <구분자> 그 줄` 로 갈아끼우면 나머지 줄이
# 소리 없이 사라지므로, 멀티라인에서는 다른 줄을 원문 그대로 두고 백업 줄만 삽입한다.
# 이 방식은 앞선 cd/Set-Location 이 그대로 살아 있어 백업이 '실제로 명령이 돌 저장소'를 잡는다.
_PENDING_BACKUPS: dict = {}
_PENDING_REASONS: list = []
# 지금 검사 중인 서브커맨드의 삽입 계획 (원본 줄 인덱스, 백업 앞에 둘 원문, 백업 뒤에 둘 원문).
# 파괴적 명령이 줄 맨 앞이면 앞부분은 빈 문자열이고, `cd X && git reset --hard` 처럼 뒤에 오면
# 원문을 그 `&&` 에서 잘라 앞뒤로 나눈다.
_INSERT_PLAN = None


def _emit_with_backup(backup_snippet: str, line: str, reason: str, command: str, is_bash: bool) -> None:
    """_INSERT_PLAN 이 있으면 즉시 emit 하지 않고 삽입을 '예약'한 뒤 검사를 계속한다. 여기서
    바로 allow 를 내면 같은 블록 뒤쪽 줄과 파이프 하류 토큰(`… | rm -rf ~`)이 아예 검사되지
    않은 채 통과한다 — 예약해 두면 뒤에서 발견된 deny/ask 가 그대로 우선한다."""
    if _INSERT_PLAN is not None:
        raw_idx, head_text, tail_text = _INSERT_PLAN
        # 한 줄에는 백업이 하나면 충분하다. checkout 처럼 한 서브커맨드가 두 규칙에 걸릴 때
        # 먼저 걸린 쪽을 쓰는 기존 우선순위와 같다.
        if raw_idx not in _PENDING_BACKUPS:
            gated = _fail_closed(backup_snippet, is_bash)
            # 앞부분이 있으면 그 끝의 연산자에 이어 붙으므로 백업 뒤에도 구분자를 단다.
            _PENDING_BACKUPS[raw_idx] = ([head_text, gated + _join(is_bash).rstrip(), tail_text]
                                         if head_text else [gated, tail_text])
            _PENDING_REASONS.append(reason)
        return
    new_command = _fail_closed(backup_snippet, is_bash) + _join(is_bash) + line.strip()
    log({"command": command, "decision": "prepend-backup", "new_command": new_command})
    emit("allow", reason, updated_input={"command": new_command})


def _emit_with_backup_or_ask(backup_snippet, line, allow_reason, no_safe_backup, command, is_bash) -> None:
    """no_safe_backup 이면(백업 줄을 끼워 넣을 수도, 명령 전체를 갈아끼울 수도 없으면) ask."""
    if no_safe_backup:
        emit("ask", CHAINED_BACKUP_ASK)
    _emit_with_backup(backup_snippet, line, allow_reason, command, is_bash)


def _emit_backup_prepend(paths, cmd_parts, line, no_safe_backup, command, is_bash) -> None:
    """되돌리기 전 uncommitted 변경을 refs/claude-backups/ 에 백업한 뒤 원본을 그대로 실행하도록
    자동 치환한다. 원본 명령을 안전하게 특정할 수 없으면(멀티라인/체이닝/다른 저장소/파이프/
    리다이렉트/경로 추출 실패) ask 로 폴백."""
    has_pipe_or_redirect = "|" in cmd_parts or any(t in (">", ">>") for t in cmd_parts)
    # 파이프/리다이렉트는 '명령 전체를 갈아끼우는' 경로에서만 위험하다 — 원본을 재구성하면서
    # 남의 토큰(`… | rm -rf ~` 의 rm)을 끌어들인다. 백업 줄만 앞에 끼워 넣는 경로는 원본 줄을
    # 손대지 않고, 그 rm 도 서브커맨드로 계속 검사돼 deny 가 예약된 백업보다 우선하므로 무관하다.
    if not paths or (_INSERT_PLAN is None and (no_safe_backup or has_pipe_or_redirect)):
        emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")
    backup = _backup_head_and_worktree(f"claude-auto-backup: before {line.strip()}", is_bash)
    _emit_with_backup(
        backup, line,
        f"되돌리기 전 uncommitted 변경사항을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
        command, is_bash,
    )


def _split_line_at_operator(line: str, parts: list, op_index: int, is_bash: bool):
    """원문 line 을 parts[op_index] 의 연산자 위치에서 (연산자까지의 앞부분, 그 뒤) 로 자른다.
    자를 수 없으면 None(→ ask).

    토큰에서 줄을 재조립하면 따옴표·확장이 깨지므로 원문 문자열을 그대로 자른다. 자를 위치는
    '잘린 두 조각을 다시 파싱하면 원래 토큰 열이 그대로 복원되는가' 로 검증하고, 그런 후보가
    정확히 하나일 때만 쓴다 — 따옴표 안의 연산자에서 엉뚱하게 잘리면 검증이 실패해 조용히
    통과하지 않는다. 검증에는 PowerShell 따옴표를 벗기기 전의 토큰을 쓴다(벗긴 뒤와 비교하면
    항상 어긋난다)."""
    op = parts[op_index]
    # `a || git reset --hard` 를 `(a || 백업) && git reset --hard` 로 바꾸면 결합 방향 때문에
    # a 가 성공했을 때 원래는 실행되지 않았어야 할 파괴적 명령이 실행된다. && 와 ; 만 안전하다.
    if op not in ("&&", ";"):
        return None
    hits = []
    start = 0
    while True:
        i = line.find(op, start)
        if i < 0:
            break
        start = i + 1
        try:
            head_tokens = shlex.split(line[:i], posix=is_bash)
            tail_tokens = shlex.split(line[i + len(op):], posix=is_bash)
        except ValueError:
            continue
        if len(head_tokens) == op_index and head_tokens + [op] + tail_tokens == parts:
            hits.append((line[:i + len(op)], line[i + len(op):]))
    return hits[0] if len(hits) == 1 else None


def _all_lines_parseable(lines: list, is_bash: bool) -> bool:
    """모든 줄이 각각 독립적으로 파싱되는지. 하나라도 실패하면 그 블록은 따옴표나 역슬래시가
    줄에 걸쳐 있다는 뜻이라(`python3 -c "` … `"`), 줄 사이에 뭔가를 끼워 넣으면 문자열 리터럴
    한복판을 잘라 원문을 망가뜨린다."""
    for ln in lines:
        try:
            shlex.split(ln, posix=is_bash)
        except ValueError:
            return False
    return True


def main() -> None:
    global _INSERT_PLAN
    try:
        raw = read_event_json()
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
    raw_lines = command.splitlines()
    original_lines = [ln for ln in raw_lines if ln.strip()]
    # 검사 대상 줄 → 원본(빈 줄 포함) 줄 번호. 백업 줄을 원위치에 끼워 넣을 때 쓴다.
    original_raw_index = [idx for idx, ln in enumerate(raw_lines) if ln.strip()]
    is_multiline = len(original_lines) > 1
    # 이 블록에 백업 줄을 끼워 넣어도 원문이 보존되는가. 히어독(`<<`)이나 줄에 걸친 따옴표가
    # 있으면 삽입 지점이 문자열 내부일 수 있어 원문을 망가뜨리므로, 그 경우는 종전대로 ask 로 넘긴다.
    can_insert_lines = "<<" not in command and _all_lines_parseable(original_lines, is_bash)
    # 처리 큐: 원본 라인 + bash/sh -c 로 발견된 내부 명령이 추가된다.
    lines = list(original_lines)

    i = 0
    while i < len(lines):
        line = lines[i]
        # bash -c 로 추출된 내부 명령은 원본에 대응하는 줄이 없어 삽입 대상이 아니다.
        line_raw_index = original_raw_index[i] if i < len(original_raw_index) else None
        i += 1
        # shlex 파싱 전에 원시 문자열로 잡아야 하는 패턴 (공백 없는 파이프).
        if PIPE_TO_SHELL_RE.search(QUOTED_RE.sub(" ", line)):
            log({"tool": tool_name, "command": command, "decision": "deny-pipe-to-shell"})
            emit("deny", "원격/외부 출력을 바로 셸에 파이프 실행하는 패턴입니다. 스크립트를 먼저 저장해 검토한 뒤 실행하세요.")

        try:
            parts = shlex.split(separate_operators(line, ps_style=not is_bash), posix=is_bash)
        except ValueError:
            log({"tool": tool_name, "line": line, "decision": "pass-unparsed"})
            continue

        if not parts:
            continue

        # 연산자 위치 검증은 따옴표를 벗기기 전 토큰과 대조해야 한다(벗긴 뒤와는 어긋난다).
        raw_parts = list(parts)
        if not is_bash:
            parts = [strip_ps_quotes(p) for p in parts]

        sub_commands = split_commands(parts)
        is_chained = len(sub_commands) > 1
        # 파이프 승격(아래) 이전의 '진짜 &&/||/; 체이닝' 여부. 백업 줄 삽입 판정에는 이걸 쓴다 —
        # 파이프는 원본 줄을 손대지 않는 삽입 방식에선 무해하지만, 체이닝은 파괴적 명령이 줄
        # 전체가 아니라서 그 앞에 백업 줄을 놓아도 실행 순서를 보장할 수 없다.
        chained_by_operator = is_chained

        # 파이프 하류의 명령도 개별 검사한다. `find . -type f | xargs rm -rf` 는 앞 명령만
        # 보면 삭제로 보이지 않는다(실측 확인). 원본(파이프 토큰 포함)도 목록에 남겨 둬야
        # 아래의 파이프→셸 검사가 그대로 동작한다. 따옴표 안의 `|` 는 한 토큰으로 묶이므로
        # 여기 걸리지 않는다 — `grep "a|rm" f` 가 삭제로 오탐되지 않는다.
        # 각 서브커맨드가 이 줄의 몇 번째 체이닝 항목인지. 0 이면 줄 맨 앞이라 그 줄 앞에 백업을
        # 놓으면 되고, 그 뒤면 원문을 앞 연산자에서 잘라 백업을 사이에 끼워야 한다
        # (`cd X && git reset --hard` 의 백업은 반드시 cd 이후에 돌아야 한다).
        operator_segments = list(sub_commands)
        segment_index = {id(seg): j for j, seg in enumerate(operator_segments)}

        for segment in list(sub_commands):
            if "|" not in segment:
                continue
            # 삭제가 파이프에 얽혀 있으면 치환 대상을 안전하게 특정할 수 없다.
            # 체이닝과 동일하게 취급해 자동 치환 대신 deny 로 보낸다.
            is_chained = True
            piece: list = []
            first_piece = True
            for token in segment:
                if token == "|":
                    if piece:
                        sub_commands.append(piece)
                        # 파이프 상류의 첫 조각은 원래 서브커맨드와 같은 자리에서 시작한다
                        # (`git restore . | tee log`) — 같은 체이닝 인덱스를 물려준다.
                        if first_piece and id(segment) in segment_index:
                            segment_index[id(piece)] = segment_index[id(segment)]
                        first_piece = False
                    piece = []
                else:
                    piece.append(token)
            if piece:
                sub_commands.append(piece)

        for cmd_parts in sub_commands:
            if not cmd_parts:
                continue

            # bash 경로에서 `FOO=1 rm -rf /` 처럼 명령 바로 앞에 붙는 환경변수 할당은 명령이
            # 아니다. 벗겨내지 않으면 base 가 'FOO=1' 이 되어 rm/git 규칙이 통째로 우회된다 —
            # 실제로 `FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch …` 가 무판정으로
            # 통과했다(실측 확인). PowerShell 에는 이 구문이 없으므로 bash 에서만 적용한다.
            head = 0
            if is_bash:
                while head < len(cmd_parts) - 1 and ENV_ASSIGN_RE.match(cmd_parts[head]):
                    head += 1
            base = _command_base(cmd_parts[head])
            args = cmd_parts[head + 1:]
            lower_args = [a.lower() for a in args]

            # 래퍼 접두어(sudo/command/env/exec/…)는 벗겨서 실제 명령을 검사한다.
            # 벗기지 않으면 `command rm -rf x` 가 아무 판정 없이 통과한다.
            # 두 종류의 래퍼를 번갈아 벗긴다 — 한 종류씩 순서대로 처리하면
            # `timeout 5 sudo rm -rf .` 처럼 섞인 형태를 놓친다(실측 확인).
            # 중첩(`sudo env rm …`)을 위해 반복하되, 비정상 입력에 대비해 횟수를 제한한다.
            for _ in range(8):
                if base in COMMAND_WRAPPERS and args:
                    idx = 0
                    if base == "env":
                        while idx < len(args) and ENV_ASSIGN_RE.match(args[idx]):
                            idx += 1
                    # 플래그가 오면 실제 명령을 특정할 수 없으므로 멈춘다. PowerShell 모드에서는
                    # `/f` 도 플래그지만 bash 모드에서 `/bin/rm` 은 경로이므로 구분한다.
                    flag_prefixes = ("-",) if is_bash else ("-", "/")
                    if idx >= len(args) or args[idx].startswith(flag_prefixes):
                        break
                    base = _command_base(args[idx])
                    args = args[idx + 1:]
                    lower_args = [a.lower() for a in args]
                    continue

                # 자기 인자를 먼저 받는 래퍼(timeout 5 rm …, nice -n 5 rm …).
                if base in ARG_WRAPPERS:
                    peeled = _peel_arg_wrapper(args)
                    if not peeled:
                        break
                    base = _command_base(peeled[0])
                    args = peeled[1:]
                    lower_args = [a.lower() for a in args]
                    continue

                break

            # xargs/parallel 은 대상을 표준입력으로 받아 훅이 볼 수 없다. 확장도 치환도
            # 불가능하므로 판정을 사용자에게 넘긴다.
            if base in STDIN_WRAPPERS:
                target = _stdin_wrapper_target(args)
                if target in EXEC_DELETE_COMMANDS:
                    log({"command": command, "decision": "ask-stdin-delete"})
                    emit("ask", "`{} {}` 은 표준입력으로 받은 목록을 지웁니다. 훅이 대상을 "
                                "확인할 수 없어 휴지통 치환도 못 합니다. 되돌리려면 "
                                "`{} trash-put --` 형태를 쓰세요. 계속할까요?".format(base, target, base))

            if base == "find":
                reason = _find_delete_reason(args)
                if reason:
                    log({"command": command, "decision": "ask-find-delete"})
                    emit("ask", "`{}` 는 조건에 맞는 파일을 전부 지웁니다. 훅이 대상을 미리 "
                                "확인할 수 없습니다. 되돌리려면 `-exec trash-put -- {{}} +` "
                                "형태를 쓰세요. 계속할까요?".format(reason))

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

                # rm 이 거부하는 형태(`.`/`..`)는 훅도 거부한다 — 치환이 원래 명령보다
                # 위험해지면 안 된다. 확장 전에 검사해야 사용자가 적은 그대로를 보여줄 수 있다.
                for a in clean_args:
                    if _is_dot_target(a.strip()):
                        log({"tool": tool_name, "command": command, "decision": "deny-dot-delete"})
                        emit("deny", f"'{a}' 는 rm 이 거부하는 형태입니다(`.` 또는 `..`). "
                                     "지울 대상을 명시적으로 지정하세요.")

                for a in clean_args:
                    if _is_root_or_home_literal(a.strip()):
                        log({"tool": tool_name, "command": command, "decision": "deny-root-delete"})
                        emit("deny", f"드라이브/파일시스템 루트({a})를 삭제하려는 시도는 차단됩니다.")

                cwd = data.get("cwd") or os.getcwd()
                targets, glob_reason = expand_delete_targets(clean_args, cwd)
                if glob_reason:
                    log({"tool": tool_name, "command": command, "decision": "deny-unexpandable-target"})
                    emit("deny", glob_reason)

                # 확장 결과에도 같은 검사를 적용한다 — 와일드카드가 홈이나 루트를 가리키는
                # 경로로 펼쳐질 수 있다.
                for a in targets:
                    if _is_root_or_home_literal(a.strip()) or _resolves_to_root_or_home(a.strip(), cwd):
                        log({"tool": tool_name, "command": command, "decision": "deny-root-delete"})
                        emit("deny", f"드라이브/파일시스템 루트({a})를 삭제하려는 시도는 차단됩니다.")

                if len(targets) > MAX_TRASH_TARGETS:
                    emit("ask", f"삭제 대상이 {len(targets)}개입니다. 한 번에 이만큼 휴지통으로 옮길까요?")

                if is_multiline or is_chained:
                    emit("deny", "여러 줄 또는 체이닝된 명령 안에 삭제 명령이 섞여 있어 안전하게 자동 치환할 수 없습니다. 삭제 명령은 단독으로 실행하세요.")

                if not os.path.exists(SEND_TO_TRASH):
                    emit("deny", "안전 삭제 스크립트(send_to_trash.py)가 없어 삭제를 차단합니다.")

                if not send2trash_available():
                    emit("deny", "휴지통 이동 도구(send2trash)가 설치되어 있지 않아 삭제를 차단합니다. (pip install send2trash)")

                quote = quote_bash if is_bash else quote_ps
                py_exe = sys.executable
                # `rm -f` / `del /f` 는 없는 파일을 조용히 넘긴다. 이 의미를 버리면
                # 없는 파일을 지우려는 명령이 실패해 호출자를 혼란스럽게 하므로 그대로 넘긴다.
                force_flag = "-f " if any(_is_force_flag(a) for a in args) else ""
                new_command = (f'{py_exe} -X utf8 {quote(SEND_TO_TRASH)} {force_flag}'
                               + " ".join(quote(a) for a in targets))

                log({"tool": tool_name, "command": command, "decision": "redirect-to-trash", "new_command": new_command})
                emit("allow", "삭제 명령을 휴지통 이동으로 안전하게 치환했습니다 (send2trash).",
                     updated_input={"command": new_command})

            if base == "git":
                # 서브커맨드를 정확히 판정한다 (순진한 "push in args" 는 `git stash push` 를 오탐).
                own_args = _git_own_args(args)
                sub, rest = git_subcommand(own_args)
                subl = sub.lower() if sub else ""
                # 백업 자동치환을 포기하고 ask 로 폴백해야 하는 조건들. -C/--git-dir/--work-tree 는
                # 명령의 대상 저장소를 cwd 밖으로 옮기는데 백업 스니펫은 cwd 에서 돌기 때문에,
                # 그대로 두면 엉뚱한 저장소를 백업하고 진짜 대상은 무방비로 파괴된다.
                redirected = _git_repo_redirected(own_args)
                # 체이닝도 멀티라인도 아닌 한 줄짜리는 종전대로 `백업 <구분자> 원본` 으로
                # 갈아끼운다. 그 외에는 이 파괴적 명령이 '줄의 맨 앞'일 때만 그 줄 앞에 백업 줄을
                # 끼워 넣어 나머지 줄·체이닝을 원문 그대로 살린다. -C/--git-dir 는 여전히 제외한다 —
                # 백업 스니펫은 그 옵션을 물려받지 않아 엉뚱한 저장소를 백업한다.
                needs_line_insert = is_multiline or chained_by_operator
                seg_idx = segment_index.get(id(cmd_parts))
                _INSERT_PLAN = None
                if (needs_line_insert and can_insert_lines
                        and line_raw_index is not None and seg_idx is not None
                        and not redirected):
                    if seg_idx == 0:
                        _INSERT_PLAN = (line_raw_index, "", line)
                    else:
                        # parts = seg0 + [연산자] + seg1 + [연산자] + … 이므로, seg_idx 번째
                        # 서브커맨드 앞 연산자의 토큰 위치는 앞 서브커맨드들의 길이 합 + (개수-1).
                        op_index = sum(len(operator_segments[j]) for j in range(seg_idx)) + seg_idx - 1
                        split = _split_line_at_operator(line, raw_parts, op_index, is_bash)
                        if split:
                            _INSERT_PLAN = (line_raw_index, split[0], split[1])
                no_safe_backup = _INSERT_PLAN is None and (is_multiline or is_chained or redirected)

                if subl == "push":
                    cwd = data.get("cwd") or os.getcwd()
                    branches, broad = _push_target_branches(rest, cwd)
                    if broad:
                        emit("ask", "git push --all/--mirror 는 여러 브랜치(보호 브랜치 포함 가능)를 한 번에 원격에 반영합니다. 계속할까요?")
                    if not branches:
                        emit("ask", "푸시 대상 브랜치를 확인할 수 없습니다. 계속할까요?")
                    if _push_is_delete(rest):
                        # 원격 브랜치 삭제는 refs/claude-backups/ 로 되돌릴 수 없다 — 로컬 백업이
                        # 닿지 않는 유일한 영역이라, 곁다리 브랜치여도 확인을 받는다.
                        emit("ask", f"원격 브랜치({', '.join(branches)})를 삭제하려고 합니다. 원격 히스토리는 로컬 백업으로 되돌릴 수 없습니다. 계속할까요?")
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
                        no_safe_backup, command, is_bash,
                    )

                if subl == "clean" and _clean_is_destructive(rest):
                    with_ignored = _clean_removes_ignored(rest)
                    backup = _backup_full_snapshot("claude-auto-backup: pre git clean", is_bash, with_ignored)
                    scope = "추적/미추적 파일 전체(.gitignore 대상 포함)" if with_ignored else "삭제될 추적/미추적 파일"
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"{scope}를 스냅샷으로 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git checkout <hash> -- . 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "worktree":
                    wt_path = _worktree_remove_force_path(rest)
                    if wt_path:
                        embedded = _dq_embed(wt_path, is_bash)
                        if embedded is None:
                            emit("ask", "삭제할 워크트리 경로를 백업 명령에 안전하게 넣을 수 없습니다. 워크트리 안의 미커밋 변경은 되돌릴 수 없습니다. 계속할까요?")
                        backup = _backup_worktree_snapshot(
                            embedded, f"claude-auto-backup: pre git worktree remove --force {wt_path}", is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"사라질 워크트리의 추적/미추적 파일을 스냅샷으로 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git checkout <hash> -- . 로 복구).",
                            no_safe_backup, command, is_bash,
                        )

                if subl == "stash":
                    stash_action = _first_non_option(rest)
                    if stash_action == "drop":
                        idx = rest.index("drop")
                        ref = next((t for t in rest[idx + 1:] if not t.startswith("-")), "stash@{0}")
                        if is_bash:
                            backup = f'_bk_ts=$(date +%Y%m%d_%H%M%S); _bk_h=$(git rev-parse {shlex.quote(ref)}) && git update-ref "refs/claude-backups/${{_bk_ts}}/stash" "$_bk_h"'
                        else:
                            # 마지막 update-ref 실패도 잡아야 뒤의 stash drop 이 막힌다 (bash 는 _fail_closed 담당).
                            backup = ('$bkTs = (Get-Date -Format "yyyyMMdd_HHmmss") + "_$PID"; '
                                      '$bkH = git rev-parse ' + quote_ps(ref) + '; if ($LASTEXITCODE -ne 0) { exit 1 }; '
                                      'git update-ref "refs/claude-backups/$bkTs/stash" $bkH; if ($LASTEXITCODE -ne 0) { exit 1 }')
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 스태시를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            no_safe_backup, command, is_bash,
                        )
                    if stash_action == "clear":
                        backup = _backup_stash_entries(is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 모든 스태시를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            no_safe_backup, command, is_bash,
                        )

                if subl == "branch" and ("-D" in rest or ("--delete" in rest and _has_force_flag(rest))):
                    names = [t for t in rest if not t.startswith("-")]
                    if not names:
                        emit("ask", "삭제할 브랜치 이름을 확인할 수 없습니다. 계속할까요?")
                    backup = _backup_refs(names, is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"삭제될 브랜치({', '.join(names)})의 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "branch" and ("-M" in rest or ("--move" in rest and _has_force_flag(rest))):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs_if_exist([names[-1]], is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"'{names[-1]}' 이름이 이미 있었다면 덮어쓰이기 전 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                            no_safe_backup, command, is_bash,
                        )

                if subl == "tag" and ("-d" in rest or "--delete" in rest):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs(names, is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 태그({', '.join(names)})의 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git tag <name> <hash> 로 복구).",
                            no_safe_backup, command, is_bash,
                        )

                if subl == "tag" and ("-f" in rest or "--force" in rest):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs_if_exist([names[0]], is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"'{names[0]}' 태그가 이미 있었다면 덮어쓰이기 전 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git tag <name> <hash> 로 복구).",
                            no_safe_backup, command, is_bash,
                        )

                if subl == "rebase" and not any(a in rest for a in REBASE_SAFE_ACTIONS):
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git rebase", is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"rebase 시작 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --hard <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "commit" and "--amend" in rest:
                    backup = _backup_refs(["HEAD"], is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"amend 전 이전 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --soft <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl in ("filter-branch", "filter-repo"):
                    backup = _backup_all_branch_tips(is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"저장소 히스토리 재작성 전 모든 로컬 브랜치 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "reflog" and _first_non_option(rest) in ("expire", "delete"):
                    backup = _backup_reflog_reachable(is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"reflog 로만 도달 가능하던 커밋들을 refs/claude-backups/ 에 고정했습니다 ({BACKUP_HINT} git stash apply <hash> 또는 git branch <name> <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "gc" and any(t in ("--prune=now", "--prune=all") for t in rest):
                    backup = _backup_dangling_commits(is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"즉시 삭제될 도달 불가능한 커밋들을 refs/claude-backups/ 에 고정했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "switch" and _has_force_flag(rest):
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git switch --force", is_bash)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"전환 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                        no_safe_backup, command, is_bash,
                    )

                if subl == "checkout":
                    if _has_force_flag(rest):
                        backup = _backup_head_and_worktree("claude-auto-backup: pre git checkout --force", is_bash)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"전환 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            no_safe_backup, command, is_bash,
                        )
                    if "--" in rest or "." in rest:
                        _emit_backup_prepend(_checkout_paths(rest), cmd_parts, line, no_safe_backup, command, is_bash)

                if subl == "restore" and _restore_touches_worktree(rest):
                    _emit_backup_prepend(_restore_paths(rest), cmd_parts, line, no_safe_backup, command, is_bash)

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

    # 모든 줄·서브커맨드를 다 본 뒤에야 예약된 백업을 확정한다. 여기까지 왔다는 건 블록 어디에도
    # deny/ask 사유가 없다는 뜻이다. 백업 줄은 해당 줄 '바로 앞'에 들어가므로 앞선 cd 가 이미
    # 적용된 상태에서 돌고, 나머지 줄은 한 글자도 바뀌지 않는다.
    if _PENDING_BACKUPS:
        out_lines = []
        for idx, ln in enumerate(raw_lines):
            # 예약된 줄은 '백업이 끼워진 형태'로 통째 대체된다(원문 조각을 그대로 포함한다).
            out_lines.extend(_PENDING_BACKUPS[idx] if idx in _PENDING_BACKUPS else [ln])
        new_command = "\n".join(out_lines)
        log({"command": command, "decision": "insert-backup-line", "new_command": new_command})
        emit("allow", " / ".join(dict.fromkeys(_PENDING_REASONS)),
             updated_input={"command": new_command})

    sys.exit(0)


if __name__ == "__main__":
    # settings.json 의 permissions.deny 에서 git 규칙을 뺀 뒤로는 이 훅이 유일한 방어선이다.
    # 훅이 예외로 죽으면 Claude Code 는 판정 없이 명령을 그대로 실행하므로(fail-open), 예상 못 한
    # 내부 오류는 조용히 흘려보내지 않고 ask 로 승격해 사용자에게 판단을 넘긴다. emit() 이 내는
    # SystemExit 은 정상 종료 경로이므로 다시 잡지 않는다.
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        log({"decision": "ask-guard-error", "error": repr(exc)})
        emit("ask", f"가드 훅 내부 오류로 이 명령의 안전성을 판정하지 못했습니다 ({type(exc).__name__}). 계속할까요?")
