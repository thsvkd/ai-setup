#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, Bash 툴 대상, 유저 레벨, macOS/Linux)

정책:
  1) rm → 휴지통 이동으로 치환 (allow + updatedInput)
     치환에 쓸 도구는 trash-put (trash-cli) → trash (macOS 14.4+ 기본 내장) 순으로 찾는다.
     핵심 원칙: **치환된 명령이 원래 rm 보다 더 많이 지울 수 있으면 안 된다.** rm 은
     `rm -rf .` 을 거부하지만 trash-put 은 거부하지 않으므로, 그대로 치환하면 아무 일도
     없었을 명령이 현재 디렉터리를 통째로 휴지통에 넣는다. 그래서 아래를 모두 검사한다:
       - 루트 경로(/, ~, $HOME, 와일드카드, 실제 $HOME 값을 그대로 적은 절대경로) → deny
       - 말단이 `.`/`..` 인 경로(`.`, `./`, `..`, `sub/.`) → deny (rm 과 동일)
       - cwd 기준으로 풀면 루트/홈이 되는 상대경로 → deny
       - 와일드카드는 cwd 기준으로 직접 확장해 절대경로로 고정하고, 확장된 경로 각각에
         위 검사를 다시 적용한다. 매칭 0개/중괄호 확장이면 deny, 100개 초과면 ask.
       - `rm -f` 의 force 의미는 trash-put 의 -f 로 넘긴다(macOS trash 는 지원 미확인이라 제외).
     휴지통 도구가 하나도 없으면 치환할 수 없으므로 fail-closed 로 deny.
     멀티라인 또는 체이닝(&&/;) 스크립트 안에 섞여 있으면 자동 치환 대신 deny.
     sudo/command/env/exec/… 래퍼 접두어와 /bin/rm 같은 경로 표기는 벗겨서 동일하게 검사한다.
  2) git: "서브커맨드"를 정확히 판정해 세분화한다(git_subcommand). 순진하게 "push in args" 로
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
               checkout -- <path>/checkout ./restore(워킹트리) → 실행 전 refs/claude-backups/
               <timestamp>/<대상> 에 되돌릴 대상을 백업한 뒤 원본 명령을 그대로 이어서 실행한다
               (자동치환). git stash create 는 추적 안 된 파일을 담지 못하는 한계가 있어(검증됨)
               clean 은 별도 스크래치 인덱스로 추적 안 된 파일까지 스냅샷하며, -x/-X 로 무시된
               파일까지 지우는 경우엔 `git add -Af` 로 .gitignore 대상까지 담는다.
               백업 스니펫은 전부 `&&` 로 이어져 한 단계라도 실패하면 뒤의 원본 파괴적 명령이
               실행되지 않는다(fail-closed). 멀티라인/체이닝이거나 -C/--git-dir/--work-tree 로
               '다른 저장소'를 대상으로 삼아 백업 대상을 안전하게 특정할 수 없으면 ask 로 폴백한다.
       pass  : stash push/save/pop/apply/list/show, reset --soft/--mixed, clean -n, branch -d,
               checkout/switch <branch>(전환), restore --staged(인덱스만), rebase --continue/
               --abort/--skip, 그 외 안전한 서브커맨드
  3) dd of=... / mkfs* / newfs_* / wipefs / fdisk / parted → deny
     diskutil 의 파괴적 서브커맨드(eraseDisk, eraseVolume, secureErase, partitionDisk,
     apfs deleteContainer 등) → deny
     /dev/sd*, /dev/disk* 등 블록 디바이스로의 리다이렉트, 포크밤 패턴 → deny
  4) curl|bash, wget -O- | sh 같은 "원격 스크립트를 바로 셸로 파이프 실행" 패턴 → deny
     (`curl url|bash` 처럼 파이프 앞뒤에 공백이 없어도 잡는다)
  5) shutdown / reboot / halt / poweroff → ask ; chmod 777 / shred → ask
  6) 래퍼 접두어는 벗겨서 실제 명령을 위 규칙으로 검사한다. 두 종류가 있고 번갈아 벗긴다:
       - 바로 명령이 오는 것: sudo / doas / command / exec / builtin / env / nohup / time / busybox
       - 자기 인자를 먼저 받는 것: timeout / nice / ionice / stdbuf / setsid / taskset / chrt
         (`timeout 5 rm -rf .` 은 첫 인자 `5` 를 명령으로 보고 멈춰 rm 보호가 통째로
          무력화됐다 — 실측 확인. 옵션과 값, 숫자로 시작하는 위치 인자를 건너뛴다.)
  7) bash/sh -c "inner" 패턴: 내부 명령을 추출해 동일 규칙으로 추가 검사한다.
  8) 대상을 미리 볼 수 없는 대량 삭제 → ask (치환도 확장도 불가능하므로 판정을 넘긴다):
       - find … -delete / -exec|-execdir|-ok|-okdir <삭제명령>
       - xargs|parallel <삭제명령>  (파이프 하류에 있어도 잡는다)
     되돌리려면 `-exec trash-put -- {} +` / `xargs trash-put --` 형태를 쓰라고 안내한다.

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
import glob
import re
import os
import datetime
import subprocess

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HOOKS_DIR, "guard.log")

ROOT_RE = re.compile(r'^(/(\*)?|~(/\*?)?|\$HOME(/\*?)?)$')

# `~`/`$HOME` 같은 축약 표기뿐 아니라, 실제 $HOME 환경변수 값을 그대로 적은 절대경로
# (예: rm -rf /home/pi)도 루트/홈 삭제로 잡아야 한다 — 그렇지 않으면 축약형만 막고 같은
# 대상을 가리키는 리터럴 경로는 새어나간다. HOME 이 비어있거나 "/" 인 비정상 환경에서는
# 이 보강판정을 건너뛴다(오탐으로 정상 삭제까지 막지 않기 위함).
_HOME_DIR = os.environ.get("HOME", "")


def _is_root_or_home_literal(path: str) -> bool:
    if ROOT_RE.match(path):
        return True
    if not _HOME_DIR or _HOME_DIR == "/":
        return False
    stripped = path.rstrip("/*") if path not in ("/", "") else path
    return os.path.normpath(stripped) == os.path.normpath(_HOME_DIR)


def _is_dot_target(path: str) -> bool:
    """GNU rm 이 거부하는 형태인가 — 경로의 말단 성분이 `.` 또는 `..` 인지.

    rm 은 `.`, `./`, `..`, `../`, `sub/.`, `sub/..` 를 모두 거부한다
    ("refusing to remove '.' or '..' directory", 실측 확인). 반면 trash-put 은
    거부하지 않으므로, 이 검사가 없으면 치환이 원래 명령보다 위험해진다 —
    `rm -rf .` 가 `trash-put .` 로 바뀌면서 현재 디렉터리가 통째로 휴지통에 들어간다.
    """
    stripped = path.rstrip("/") or path
    return os.path.basename(stripped) in (".", "..")


def _resolves_to_root_or_home(path: str, cwd: str) -> bool:
    """cwd 기준으로 해석했을 때 루트나 홈을 가리키는가.

    _is_root_or_home_literal 은 문자열만 보므로 `../../../home/pi` 처럼 해석해야
    홈이 되는 경로를 놓친다. 훅은 명령이 실행될 cwd 를 받으므로 해석 후 한 번 더 본다.
    """
    try:
        resolved = os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))
    except (OSError, ValueError):
        return False
    if resolved == os.sep:
        return True
    if not _HOME_DIR or _HOME_DIR == "/":
        return False
    return resolved == os.path.realpath(_HOME_DIR)


# 글로브는 셸이 확장하는데 shlex.quote 로 인용해 버리면 확장이 죽어 명령이 조용히
# 실패한다(`rm -rf *` → `trash-put '*'`). 인용을 빼면 반대로 무엇이 지워질지 모른 채
# 통과시키게 된다. 그래서 훅이 cwd 기준으로 직접 확장해 구체 경로로 바꾼 뒤, 확장된
# 경로 하나하나에 안전 검사를 적용한다. 중괄호 확장은 glob 이 다루지 못하므로 거부한다.
GLOB_META_RE = re.compile(r"[*?\[]")
BRACE_RE = re.compile(r"[{}]")
# 한 번에 휴지통으로 보낼 수 있는 대상 수 상한. 넘으면 자동치환 대신 확인을 요청한다 —
# 명령줄 길이 문제이기도 하고, 사고가 났을 때의 규모 문제이기도 하다.
MAX_TRASH_TARGETS = 100


def expand_delete_targets(args: list, cwd: str) -> tuple:
    """글로브를 cwd 기준으로 확장한다. 반환: (확장된 경로 리스트, 실패 사유 또는 None)."""
    expanded = []
    for a in args:
        if BRACE_RE.search(a):
            return [], f"중괄호 확장이 포함된 대상('{a}')은 훅이 해석할 수 없어 차단합니다."
        if not GLOB_META_RE.search(a):
            expanded.append(a)
            continue
        # 확장 결과는 절대경로로 고정한다. 훅이 판정한 cwd 와 실제 실행 cwd 가 어긋나도
        # 엉뚱한 디렉터리의 파일이 지워지지 않는다.
        pattern = a if os.path.isabs(a) else os.path.join(cwd, a)
        matches = sorted(glob.glob(pattern))
        if not matches:
            return [], f"'{a}' 와 일치하는 파일이 없습니다."
        expanded.extend(matches)
    return expanded, None


def _is_force_flag(arg: str) -> bool:
    """rm 의 -f(force). `-rf` 처럼 묶인 단축 플래그도 인식한다."""
    if arg in ("-f", "--force"):
        return True
    return arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]


# 실제 명령 앞에 붙어 가드를 빠져나가게 하는 래퍼들. sudo 만 벗기면 `command rm -rf x`,
# `env rm -rf x` 가 아무 판정 없이 통과한다(실측 확인). 반복해서 벗겨 실제 명령을 찾는다.
COMMAND_WRAPPERS = {"sudo", "doas", "command", "exec", "builtin", "env", "nohup", "time", "busybox"}
ENV_ASSIGN_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

# 자기 인자를 먼저 받는 래퍼. `timeout 5 rm -rf .` 은 COMMAND_WRAPPERS 방식으로 못 벗긴다 —
# 첫 인자 `5` 를 명령으로 보고 멈추기 때문이다. 그 결과 rm 보호가 통째로 무력화된다(실측).
ARG_WRAPPERS = {"timeout", "nice", "ionice", "stdbuf", "setsid", "taskset", "chrt"}
# 위 래퍼들이 쓰는 '값을 받는' 옵션. 이 옵션을 만나면 다음 토큰까지 건너뛴다.
# 붙여 쓴 형태(`-oL`, `-n5`)는 토큰 자체가 `-` 로 시작하므로 그냥 옵션으로 건너뛰어진다.
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

# find -exec / xargs 뒤에 오면 대량 삭제인 명령들.
EXEC_DELETE_COMMANDS = {"rm", "unlink", "shred", "srm", "wipe"}
FIND_EXEC_OPTS = {"-exec", "-execdir", "-ok", "-okdir"}


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
            if tok in ARG_WRAPPER_VALUE_OPTS:
                i += 2
            else:
                i += 1
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
        return os.path.basename(tok)
    return None


def _find_delete_reason(args: list):
    """find 명령이 파일을 지우는지 판정하고, 지운다면 사유 문자열을 돌려준다."""
    for i, tok in enumerate(args):
        if tok == "-delete":
            return "find -delete"
        if tok in FIND_EXEC_OPTS and i + 1 < len(args):
            if os.path.basename(args[i + 1]) in EXEC_DELETE_COMMANDS:
                return f"find {tok} {args[i + 1]}"
    return None

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
    """git push 의 강제(force) 계열 플래그 존재 여부. 위치 무관, 짧은 플래그 결합(-fu)도,
    `+refspec` 형태(예: `git push origin +feature:main`)도 잡는다."""
    for t in rest:
        if t in ("--force", "--force-with-lease", "--force-if-includes"):
            return True
        if t.startswith("--force-with-lease") or t.startswith("--force-if-includes"):
            return True  # --force-with-lease=<ref> 형태
        if "f" in _short_flag_chars(t):     # -f, -fu, -uf …
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
# 파괴'하는 상황이 된다(`git -C /other reset --hard` 로 실측 확인). 그래서 백업 경로에서는
# 자동치환 대신 ask 로 폴백한다.
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
    """cwd 의 현재 브랜치 이름. detached HEAD/실패 시 None. (git 이 없거나 타임아웃되면 None —
    이 경우 호출부는 브랜치를 특정 못한 것으로 보고 안전 쪽인 ask 로 폴백한다.)"""
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
    """remote/refspec 을 생략한 `git push`(또는 remote 만 있고 refspec 생략)가 실제로 갱신할
    원격 브랜치 이름. 업스트림이 설정돼 있으면 그 이름(리모트 접두어 제거)을, 아니면 로컬 브랜치
    이름을 쓴다(push.default=simple/current 가정)."""
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
# refspec 없음(=현재 브랜치를 push)" 으로 읽는다(실측 — 'current branch has no upstream'
# 오류가 난다). --repo 를 여기서 빼면 origin 이 remote, feature/x 가 refspec 으로 잡혀
# '곁다리 브랜치 push' 로 통과시켜 버린다 — 실제로는 main 이 나갈 수 있는데도.
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
        # remote 생략, 혹은 remote 만 있고 refspec 생략 → 현재 브랜치를 그대로 push
        branch = _push_implicit_branch(cwd)
        return ([branch] if branch else []), False
    branches = []
    for rs in positional[1:]:
        rs = rs.lstrip("+")
        if ":" in rs:
            src, dst = rs.split(":", 1)
            target = dst or src   # dst 가 비어있으면(`origin :branch`) 원격 브랜치 삭제 — src 가 대상
            if target:
                branches.append(target)
        elif rs == "HEAD":
            b = _current_branch(cwd)
            if b:
                branches.append(b)
        else:
            branches.append(rs)
    return branches, False


def _backup_ts_snippet() -> str:
    """백업 ref 의 네임스페이스. 초 단위 타임스탬프만 쓰면 같은 초에 실행된 두 백업이 같은
    네임스페이스를 공유해, `feat`(파일)와 `feat/x`(디렉터리)처럼 D/F 충돌이 나는 ref 쌍이
    생긴다. 충돌 시 update-ref 가 실패하고 fail-closed 로 원본까지 막히므로(데이터는 안전하나
    사용자는 난해한 git 에러를 본다), 셸 PID 를 붙여 실행마다 네임스페이스를 분리한다.
    date 의 %N(나노초)은 BSD date(macOS)에 없어 쓰지 않는다."""
    return '_bk_ts=$(date +%Y%m%d_%H%M%S)_$$'


def _backup_head_and_worktree(reason: str) -> str:
    """HEAD 커밋 위치 + 추적된 uncommitted 변경(git stash create)을 refs/claude-backups/ 에 백업.
    추적 안 된 파일은 담기지 않는다 — reset --hard/checkout --force/switch --force/checkout --
    <path>/restore 는 추적 안 된 파일을 지우지 않으므로 이걸로 충분하다(추적 안 된 파일까지
    지우는 git clean 은 _backup_full_snapshot 을 따로 쓴다).

    모든 단계를 `&&` 로만 잇는다. 예전엔 stash create 앞에 `;` 가 있었는데, `;` 는 앞선 실패의
    종료 상태를 덮어써서(rev-parse/update-ref 가 실패해도) 마지막 `[ -z "$_bk_stash" ]` 가 참이
    되어 전체가 성공으로 보고되고, 뒤에 `&&` 로 이어붙인 원본 파괴적 명령이 백업 없이 실행됐다
    (커밋이 없는 저장소·git 저장소가 아닌 디렉터리에서 실측 확인). '스태시할 변경이 없어 빈
    문자열'인 정상 경로만 `{ ... }` 로 감싸 성공 처리한다."""
    return (
        f'{_backup_ts_snippet()} && '
        '_bk_head=$(git rev-parse HEAD) && '
        'git update-ref "refs/claude-backups/${_bk_ts}/head" "$_bk_head" && '
        f'_bk_stash=$(git stash create {shlex.quote(reason)}) && '
        '{ [ -z "$_bk_stash" ] || git update-ref "refs/claude-backups/${_bk_ts}/worktree" "$_bk_stash"; }'
    )


def _backup_full_snapshot(reason: str, include_ignored: bool) -> str:
    """추적 + 추적 안 된 파일 전체를 스냅샷 커밋으로 백업한다. git clean 전용 — git stash create
    는 추적 안 된 파일을 담지 못하는 한계가 실측으로 확인되어(스크래치 저장소에서 untracked.txt
    가 스냅샷에서 누락됨을 확인), 별도 인덱스 파일(GIT_INDEX_FILE)로 실제 인덱스/워킹트리를
    전혀 건드리지 않고 전체 스냅샷을 만든다.

    include_ignored 는 `git clean -x/-X`(무시된 파일까지 삭제) 전용이다. 기본 `git add -A` 는
    .gitignore 대상을 담지 않아, -x 로 지워질 .env/node_modules/빌드 산출물이 백업에서 통째로
    빠진 채 영구 소실됐다(실측 확인). 이 경우에만 `-f` 를 붙여 무시된 파일까지 담는다 — 항상
    붙이면 -x 없는 평범한 clean 에서도 node_modules 전체를 커밋해 느려지기 때문이다."""
    add_cmd = 'git add -Af -- .' if include_ignored else 'git add -A -- .'
    # 스크래치 인덱스는 .git/ 안의 고정 경로에 만든다. mktemp 로 매번 새 이름을 쓰면 clean 을
    # 돌릴 때마다 /tmp 에 인덱스 파일이 하나씩 쌓이고, 지우려면 생성 명령에 rm 을 넣어야 한다
    # (가드가 rm 을 다루는 마당에 스스로 rm 을 생성하는 건 피하고 싶다). .git/ 안의 한 파일을
    # 계속 덮어쓰면 누적도 없고 삭제도 필요 없으며, git 이 원래 인덱스를 두는 자리이기도 하다.
    return (
        f'{_backup_ts_snippet()} && '
        '_bk_gitdir=$(git rev-parse --git-dir) && '
        '_bk_idx="$_bk_gitdir/claude-guard-index" && '
        f'GIT_INDEX_FILE="$_bk_idx" {add_cmd} && '
        '_bk_tree=$(GIT_INDEX_FILE="$_bk_idx" git write-tree) && '
        f'_bk_h=$(git commit-tree "$_bk_tree" -p HEAD -m {shlex.quote(reason)}) && '
        'git update-ref "refs/claude-backups/${_bk_ts}/snapshot" "$_bk_h"'
    )


def _backup_refs(ref_exprs: list) -> str:
    """주어진 각 ref 표현식(브랜치 이름 등)이 가리키는 커밋을, 삭제되기 전에 백업한다."""
    quoted = " ".join(shlex.quote(r) for r in ref_exprs)
    return (
        f'{_backup_ts_snippet()}; '
        f'for _bk_r in {quoted}; do '
        '_bk_h=$(git rev-parse "$_bk_r") && git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h" || exit 1; '
        'done'
    )


def _backup_stash_entries() -> str:
    """git stash clear 전에, 현재 존재하는 모든 스태시 항목의 커밋을 각각 백업한다."""
    return (
        f'{_backup_ts_snippet()}; '
        '_bk_i=0; '
        'for _bk_h in $(git stash list --format=%H); do '
        'git update-ref "refs/claude-backups/${_bk_ts}/stash${_bk_i}" "$_bk_h"; _bk_i=$((_bk_i+1)); '
        'done'
    )


def _backup_refs_if_exist(ref_exprs: list) -> str:
    """주어진 각 ref 표현식이 '이미 존재할 때만' 그 커밋을 백업한다. branch -M / tag -f 처럼
    대상이 아직 없는 것(덮어쓸 게 없어 안전한 경우)이 정상 경로인 명령에 쓴다 — 없으면
    조용히 건너뛰고, 있으면 덮어쓰이기 전 위치를 남긴다(실패해도 전체를 막지 않는다)."""
    quoted = " ".join(shlex.quote(r) for r in ref_exprs)
    return (
        f'{_backup_ts_snippet()}; '
        f'for _bk_r in {quoted}; do '
        '_bk_h=$(git rev-parse --verify -q "$_bk_r" 2>/dev/null) && '
        'git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h"; '
        'done; true'   # 대상이 아직 없어 백업을 건너뛴 것(정상 경로)이 && 로 뒤 원본 명령을 막지 않게 한다
    )


def _backup_all_branch_tips() -> str:
    """filter-branch/filter-repo 처럼 저장소 전체 히스토리를 재작성하기 전에, 현재 존재하는
    모든 로컬 브랜치의 커밋 위치를 전부 백업한다."""
    return (
        f'{_backup_ts_snippet()}; '
        "for _bk_r in $(git for-each-ref refs/heads --format='%(refname:short)'); do "
        '_bk_h=$(git rev-parse "$_bk_r") && git update-ref "refs/claude-backups/${_bk_ts}/$_bk_r" "$_bk_h" || exit 1; '
        'done'
    )


def _backup_reflog_reachable() -> str:
    """git reflog expire/delete 전에, 현재 reflog 로만 도달 가능한(다른 ref 에서는 안 보이는)
    커밋들을 전부 refs/claude-backups/ 에 고정한다 — reflog 가 지워져도 그 커밋들은 GC 대상이
    되지 않는다(reflog 본연의 안전망 역할을 백업 ref 가 대신 떠맡는다)."""
    return (
        f'{_backup_ts_snippet()}; '
        '_bk_i=0; '
        "for _bk_h in $(git reflog show --all --format=%H 2>/dev/null | sort -u); do "
        'git update-ref "refs/claude-backups/${_bk_ts}/reflog${_bk_i}" "$_bk_h" 2>/dev/null; _bk_i=$((_bk_i+1)); '
        'done'
    )


def _backup_dangling_commits() -> str:
    """git gc --prune=now/all 전에, reflog 로도 안 잡히는(진짜 도달 불가능한) 커밋들을 전부
    refs/claude-backups/ 에 고정해 즉시 GC 로 영구 삭제되지 않게 한다."""
    return (
        f'{_backup_ts_snippet()}; '
        '_bk_i=0; '
        "for _bk_h in $(git fsck --no-reflog --unreachable 2>/dev/null | awk '$1==\"unreachable\" && $2==\"commit\"{print $3}'); do "
        'git update-ref "refs/claude-backups/${_bk_ts}/dangling${_bk_i}" "$_bk_h" 2>/dev/null; _bk_i=$((_bk_i+1)); '
        'done'
    )


def _fail_closed(backup_snippet: str) -> str:
    """백업 스니펫을 `{ ... } || { 메시지; exit 1; }` 로 감싼다. 스니펫 안의 어떤 단계가 실패하든
    셸이 즉시 끊겨, 뒤에 `&&` 로 이어붙인 원본 파괴적 명령이 절대 실행되지 않는다. 각 스니펫이
    자체적으로 `&&` 체인을 유지하는 것에 더한 2중 방어이자, 실패 시 사용자에게 왜 명령이 안
    돌았는지 알려주는 유일한 통로다(그냥 종료 상태만 0이 아니면 원인이 보이지 않는다)."""
    return (
        "{ " + backup_snippet + "; } || "
        '{ echo "claude-guard: 백업에 실패해 원본 명령을 실행하지 않았습니다." >&2; exit 1; }'
    )


def _emit_with_backup(backup_snippet: str, line: str, reason: str, command: str) -> None:
    new_command = _fail_closed(backup_snippet) + " && " + line.strip()
    log({"command": command, "decision": "prepend-backup", "new_command": new_command})
    emit("allow", reason, updated_input={"command": new_command})


def _emit_with_backup_or_ask(backup_snippet, line, allow_reason, no_safe_backup, command) -> None:
    """no_safe_backup 이면(멀티라인·체이닝·다른 저장소 대상) 백업 대상을 특정할 수 없어 ask."""
    if no_safe_backup:
        emit("ask", CHAINED_BACKUP_ASK)
    _emit_with_backup(backup_snippet, line, allow_reason, command)


def _clean_is_destructive(rest: list) -> bool:
    """git clean 이 실제로 파일을 삭제하는지. -n/--dry-run(미리보기)이 있으면 삭제하지 않는다."""
    dry = any(t == "--dry-run" or "n" in _short_flag_chars(t) for t in rest)
    if dry:
        return False
    return any(t == "--force" or "f" in _short_flag_chars(t) for t in rest)


def _clean_removes_ignored(rest: list) -> bool:
    """git clean 이 .gitignore 대상까지 지우는지(-x: 무시된 파일도 함께, -X: 무시된 파일만).
    이 경우 기본 `git add -A` 스냅샷으로는 .env/node_modules/빌드 산출물이 백업에서 빠진다."""
    return any("x" in _short_flag_chars(t) or "X" in _short_flag_chars(t) for t in rest)


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
    """rest 에 강제 플래그가 있는지 (checkout/switch/branch 판정용).
    -f/--force/--discard-changes 외에, `checkout -B`(강제 생성+전환)와 `switch -C`(강제 생성+전환)도
    기존 브랜치 위치를 되돌릴 수 없이 재설정하고 uncommitted 변경을 버릴 수 있어 같은 취급을 한다."""
    for t in rest:
        if t in ("-f", "--force", "--discard-changes", "-B", "-C", "--force-create"):
            return True
        chars = _short_flag_chars(t)
        if "f" in chars or "B" in chars or "C" in chars:
            return True
    return False


def _emit_backup_prepend(paths, cmd_parts, line, no_safe_backup, command) -> None:
    """되돌리기 전 uncommitted 변경을 refs/claude-backups/ 에 백업한 뒤 원본을 그대로 실행하도록
    자동 치환한다. 원본 명령을 안전하게 특정할 수 없으면(멀티라인/체이닝/다른 저장소/파이프/
    리다이렉트/경로 추출 실패) ask 로 폴백. `git stash create` 는 워킹트리를 건드리지 않는 플러밍
    명령이라(검증됨), 이전의 `git stash push`(워킹트리를 즉시 되돌림)와 달리 원본 checkout/restore
    명령이 그 뒤에 자기 몫의 일(다른 ref 에서 가져오기 등)을 그대로 수행할 수 있다. 백업 스니펫은
    _fail_closed 로 감싼 뒤 `&&` 로 이어붙여, 백업이 실패하면 뒤의 파괴적 원본이 실행되지 않는다."""
    has_pipe_or_redirect = "|" in cmd_parts or any(t in (">", ">>") for t in cmd_parts)
    if no_safe_backup or not paths or has_pipe_or_redirect:
        emit("ask", "커밋되지 않은 로컬 변경사항을 버릴 수 있는 명령입니다. 계속할까요?")
    backup = _backup_head_and_worktree(f"claude-auto-backup: before {line.strip()}")
    _emit_with_backup(
        backup, line,
        f"되돌리기 전 uncommitted 변경사항을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
        command,
    )


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

        # 파이프 하류의 명령도 개별 검사한다. `find . -type f | xargs rm -rf` 는 앞 명령만
        # 보면 삭제로 보이지 않는다(실측 확인). 원본(파이프 토큰 포함)도 목록에 남겨 둬야
        # 아래의 파이프→셸 검사가 그대로 동작한다. 따옴표 안의 `|` 는 shlex 가 한 토큰으로
        # 묶으므로 여기 걸리지 않는다 — `grep "a|rm" f` 가 삭제로 오탐되지 않는다.
        for segment in list(sub_commands):
            if "|" not in segment:
                continue
            # 삭제가 파이프에 얽혀 있으면 치환 대상을 안전하게 특정할 수 없다.
            # 체이닝과 동일하게 취급해 자동 치환 대신 deny 로 보낸다.
            is_chained = True
            piece: list = []
            for token in segment:
                if token == "|":
                    if piece:
                        sub_commands.append(piece)
                    piece = []
                else:
                    piece.append(token)
            if piece:
                sub_commands.append(piece)

        for cmd_parts in sub_commands:
            if not cmd_parts:
                continue

            # `FOO=1 rm -rf /` 처럼 명령 바로 앞에 붙는 환경변수 할당은 명령이 아니다. 벗겨내지
            # 않으면 base 가 'FOO=1' 이 되어 rm/git 규칙이 통째로 우회된다 — 실제로
            # `FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch …` 가 무판정으로 통과했다(실측 확인).
            # env 래퍼(`env FOO=1 rm …`)와 달리 여기엔 벗겨낼 명령 이름이 없으므로 별도 처리한다.
            head = 0
            while head < len(cmd_parts) - 1 and ENV_ASSIGN_RE.match(cmd_parts[head]):
                head += 1
            base = os.path.basename(cmd_parts[head])
            args = cmd_parts[head + 1:]
            lower_args = [a.lower() for a in args]

            # 래퍼 접두어(sudo/command/env/exec/…)는 벗겨서 실제 명령을 검사한다.
            # `sudo rm -rf /` 뿐 아니라 `command rm -rf x`, `env rm -rf x` 같은 우회도 막는다.
            # 중첩(`sudo env rm …`)을 위해 반복하되, 비정상 입력에 대비해 횟수를 제한한다.
            # 두 종류의 래퍼를 번갈아 벗긴다. 한 종류씩 순서대로 처리하면
            # `timeout 5 sudo rm -rf .` 처럼 섞인 형태를 놓친다(실측 확인).
            for _ in range(8):
                if base in COMMAND_WRAPPERS and args:
                    # `env VAR=1 rm …` 의 환경변수 할당은 명령이 아니므로 건너뛴다.
                    idx = 0
                    if base == "env":
                        while idx < len(args) and ENV_ASSIGN_RE.match(args[idx]):
                            idx += 1
                    # 플래그가 오면(`command -v rm`, `env -i`) 실제 명령을 특정할 수 없으므로 멈춘다.
                    if idx >= len(args) or args[idx].startswith("-"):
                        break
                    base = os.path.basename(args[idx])
                    args = args[idx + 1:]
                    lower_args = [a.lower() for a in args]
                    continue

                # 자기 인자를 먼저 받는 래퍼(timeout 5 rm …, nice -n 5 rm …).
                # 옵션·위치 인자를 건너뛰는 규칙이 달라 별도 헬퍼로 처리한다.
                if base in ARG_WRAPPERS:
                    peeled = _peel_arg_wrapper(args)
                    if not peeled:
                        break
                    base = os.path.basename(peeled[0])
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
                    emit("ask", f"`{base} {target}` 은 표준입력으로 받은 목록을 지웁니다. "
                                "훅이 대상을 확인할 수 없어 휴지통 치환도 못 합니다. "
                                f"되돌리려면 `{base} trash-put --` 형태를 쓰세요. 계속할까요?")

            if base == "find":
                reason = _find_delete_reason(args)
                if reason:
                    log({"command": command, "decision": "ask-find-delete"})
                    emit("ask", f"`{reason}` 는 조건에 맞는 파일을 전부 지웁니다. 훅이 대상을 "
                                "미리 확인할 수 없습니다. 되돌리려면 "
                                "`-exec trash-put -- {} +` 형태를 쓰세요. 계속할까요?")

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

                # rm 이 거부하는 형태(`.`/`..`)는 훅도 거부한다. 치환이 원래 명령보다
                # 위험해지면 안 된다. 확장 전에 검사해야 사용자가 적은 그대로를 보여줄 수 있다.
                for a in clean_args:
                    if _is_dot_target(a.strip()):
                        log({"command": command, "decision": "deny-dot-delete"})
                        emit("deny", f"'{a}' 는 rm 이 거부하는 형태입니다(`.` 또는 `..`). "
                                     "지울 대상을 명시적으로 지정하세요.")

                for a in clean_args:
                    if _is_root_or_home_literal(a.strip()):
                        log({"command": command, "decision": "deny-root-delete"})
                        emit("deny", f"루트/홈 디렉터리 전체({a})를 삭제하려는 시도는 차단됩니다.")

                cwd = data.get("cwd") or os.getcwd()
                targets, glob_reason = expand_delete_targets(clean_args, cwd)
                if glob_reason:
                    log({"command": command, "decision": "deny-unexpandable-target"})
                    emit("deny", glob_reason)

                # 확장 결과에도 같은 안전 검사를 적용한다 — 글로브가 홈이나 루트를
                # 가리키는 경로로 펼쳐질 수 있다.
                for a in targets:
                    if _is_root_or_home_literal(a.strip()) or _resolves_to_root_or_home(a.strip(), cwd):
                        log({"command": command, "decision": "deny-root-delete"})
                        emit("deny", f"루트/홈 디렉터리 전체({a})를 삭제하려는 시도는 차단됩니다.")

                if len(targets) > MAX_TRASH_TARGETS:
                    emit("ask", f"삭제 대상이 {len(targets)}개입니다. 한 번에 이만큼 휴지통으로 옮길까요?")

                if is_multiline or is_chained:
                    emit("deny", "여러 줄 또는 체이닝된 명령 안에 삭제 명령이 섞여 있어 안전하게 자동 치환할 수 없습니다. 삭제 명령은 단독으로 실행하세요.")

                trash_cmd = resolve_trash_command()
                if not trash_cmd:
                    emit("deny", "휴지통 이동 도구(trash-put / macOS trash)가 없어 삭제를 차단합니다. (pip install trash-cli)")

                # `rm -f` 는 없는 파일을 조용히 넘긴다. 이 의미를 버리면 `rm -f 없는파일` 이
                # 실패해 호출자를 혼란스럽게 하므로 trash-put 의 -f 로 넘긴다.
                # macOS 내장 trash 는 -f 지원을 확인하지 못했으므로 붙이지 않는다 —
                # 모르는 플래그를 넘겨 삭제 도구가 오작동하는 쪽이 더 위험하다.
                force_flag = (" -f" if trash_cmd == "trash-put"
                              and any(_is_force_flag(a) for a in args) else "")
                new_command = trash_cmd + force_flag + " " + " ".join(shlex.quote(a) for a in targets)
                log({"command": command, "decision": "redirect-to-trash", "new_command": new_command})
                emit("allow", f"rm → {trash_cmd} 치환 (휴지통으로 안전하게 이동)",
                     updated_input={"command": new_command})

            if base == "git":
                # 서브커맨드를 정확히 판정한다. 이래야 `git stash push`(안전, 저장)가
                # 순진한 "push in args" 매칭으로 오탐되지 않는다. _git_own_args 로 파이프/
                # 리다이렉트 뒤(스모글링된 다른 명령의 토큰, 예: `checkout -- f | rm -rf ~`의
                # `-rf`)를 먼저 잘라내야 한다 — 안 그러면 남의 `-rf` 가 `-f`(force)로 오인된다.
                own_args = _git_own_args(args)
                sub, rest = git_subcommand(own_args)
                subl = sub.lower() if sub else ""
                # 백업 자동치환을 포기하고 ask 로 폴백해야 하는 조건들. -C/--git-dir/--work-tree 는
                # 명령의 대상 저장소를 cwd 밖으로 옮기는데 백업 스니펫은 cwd 에서 돌기 때문에,
                # 그대로 두면 엉뚱한 저장소를 백업하고 진짜 대상은 무방비로 파괴된다.
                no_safe_backup = is_multiline or is_chained or _git_repo_redirected(own_args)

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
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git reset --hard")
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"되돌리기 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --hard <hash> 또는 git stash apply <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "clean" and _clean_is_destructive(rest):
                    with_ignored = _clean_removes_ignored(rest)
                    backup = _backup_full_snapshot("claude-auto-backup: pre git clean", with_ignored)
                    scope = "추적/미추적 파일 전체(.gitignore 대상 포함)" if with_ignored else "삭제될 추적/미추적 파일"
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"{scope}를 스냅샷으로 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git checkout <hash> -- . 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "stash":
                    stash_action = _first_non_option(rest)
                    if stash_action == "drop":
                        idx = rest.index("drop")
                        ref = next((t for t in rest[idx + 1:] if not t.startswith("-")), "stash@{0}")
                        backup = f'{_backup_ts_snippet()}; _bk_h=$(git rev-parse {shlex.quote(ref)}) && git update-ref "refs/claude-backups/${{_bk_ts}}/stash" "$_bk_h"'
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 스태시를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            no_safe_backup, command,
                        )
                    if stash_action == "clear":
                        backup = _backup_stash_entries()
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 모든 스태시를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            no_safe_backup, command,
                        )

                if subl == "branch" and ("-D" in rest or ("--delete" in rest and _has_force_flag(rest))):
                    names = [t for t in rest if not t.startswith("-")]
                    if not names:
                        emit("ask", "삭제할 브랜치 이름을 확인할 수 없습니다. 계속할까요?")
                    backup = _backup_refs(names)
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"삭제될 브랜치({', '.join(names)})의 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "branch" and ("-M" in rest or ("--move" in rest and _has_force_flag(rest))):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs_if_exist([names[-1]])   # 새 이름이 마지막 위치 인자
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"'{names[-1]}' 이름이 이미 있었다면 덮어쓰이기 전 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                            no_safe_backup, command,
                        )

                if subl == "tag" and ("-d" in rest or "--delete" in rest):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs(names)
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"삭제될 태그({', '.join(names)})의 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git tag <name> <hash> 로 복구).",
                            no_safe_backup, command,
                        )

                if subl == "tag" and ("-f" in rest or "--force" in rest):
                    names = [t for t in rest if not t.startswith("-")]
                    if names:
                        backup = _backup_refs_if_exist([names[0]])   # 태그 이름이 첫 위치 인자
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"'{names[0]}' 태그가 이미 있었다면 덮어쓰이기 전 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git tag <name> <hash> 로 복구).",
                            no_safe_backup, command,
                        )

                if subl == "rebase" and not any(a in rest for a in REBASE_SAFE_ACTIONS):
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git rebase")
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"rebase 시작 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --hard <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "commit" and "--amend" in rest:
                    backup = _backup_refs(["HEAD"])
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"amend 전 이전 커밋 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git reset --soft <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl in ("filter-branch", "filter-repo"):
                    backup = _backup_all_branch_tips()
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"저장소 히스토리 재작성 전 모든 로컬 브랜치 위치를 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "reflog" and _first_non_option(rest) in ("expire", "delete"):
                    backup = _backup_reflog_reachable()
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"reflog 로만 도달 가능하던 커밋들을 refs/claude-backups/ 에 고정했습니다 ({BACKUP_HINT} git stash apply <hash> 또는 git branch <name> <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "gc" and any(t in ("--prune=now", "--prune=all") for t in rest):
                    backup = _backup_dangling_commits()
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"즉시 삭제될 도달 불가능한 커밋들을 refs/claude-backups/ 에 고정했습니다 ({BACKUP_HINT} git branch <name> <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "switch" and _has_force_flag(rest):
                    backup = _backup_head_and_worktree("claude-auto-backup: pre git switch --force")
                    _emit_with_backup_or_ask(
                        backup, line,
                        f"전환 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                        no_safe_backup, command,
                    )

                if subl == "checkout":
                    if _has_force_flag(rest):
                        backup = _backup_head_and_worktree("claude-auto-backup: pre git checkout --force")
                        _emit_with_backup_or_ask(
                            backup, line,
                            f"전환 전 HEAD 위치와 uncommitted 변경을 refs/claude-backups/ 에 백업했습니다 ({BACKUP_HINT} git stash apply <hash> 로 복구).",
                            no_safe_backup, command,
                        )
                    # 경로 되돌리기(`-- <path>` 또는 `git checkout .`)만 백업 후 실행한다.
                    # 그냥 브랜치 전환(`git checkout <branch>`)은 충돌 시 git 이 거부하므로 통과.
                    if "--" in rest or "." in rest:
                        _emit_backup_prepend(_checkout_paths(rest), cmd_parts, line, no_safe_backup, command)

                if subl == "restore" and _restore_touches_worktree(rest):
                    # `git restore --staged`(인덱스만)는 손실이 없어 통과. 워킹트리를 되돌리는 경우만 백업.
                    _emit_backup_prepend(_restore_paths(rest), cmd_parts, line, no_safe_backup, command)

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
