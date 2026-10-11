#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danger_guard.py — PreToolUse hook (Claude Code, 유저 레벨, POSIX/Windows 공용)

Bash 툴(POSIX 셸·Git Bash)과 PowerShell 툴 양쪽을 대상으로 한다. 둘 다 tool_input.command
에 실행할 명령 문자열을 담는다.

설계 원칙 — 이 훅의 가치는 '차단'이 아니라 '복구'다.
  실사용 로그 10,329건 전수 분석(2026-09):
    · deny/ask 53건 중 진짜 위험한 명령은 0건. 전부 테스트 픽스처거나 오탐이었다
      (평범한 셸 함수 정의를 포크밤으로, 히어독 본문을 curl|sh 로 오인 등).
    · 반대로 휴지통 치환 311건과 git 백업 22건은 실제로 작동했다.
  게다가 오탐의 상당수는 훅이 '명령 문자열을 재작성'하다 생겼다. 훅은 셸이 아니어서
  $VAR·글로브·따옴표 확장을 흉내 낼 수 없는데도 인자를 다시 따옴표로 감싸 넘겼다
  (`rm -rf "$FOO/bar"` → `trash-put '$FOO/bar'` → 확장이 막혀 실패).
  그래서 재작성을 버리고, 판정은 최소화하고, 복구만 남긴다.

정책:
  1) 삭제 → 휴지통. 인자를 건드리지 않는다.
     Bash      : SessionStart 에서 CLAUDE_ENV_FILE 에 'PATH 맨 앞에 shims/' 를 적는다. Claude
                 Code 가 이 파일을 매 Bash 명령 전에 source 하므로 명령 문자열을 바꿀 필요가
                 없다. 종전처럼 명령 앞에 줄을 붙이면 권한 규칙이 바뀐 명령에 대해 평가돼
                 `Bash(rm *)` 같은 사용자 허용 규칙이 맞지 않게 되고, allow 를 붙이면 권한
                 체계를 통째로 우회한다(둘 다 실측, CC 2.1.283). shims/rm 은 셸이 확장을
                 끝낸 뒤의 argv 를 받으므로 해석이 원본 rm 과 어긋날 수 없고, `find -exec rm`·
                 `xargs rm`·스크립트 내부 rm 도 PATH 로 해석되므로 같은 경로를 탄다.
     PowerShell: CLAUDE_ENV_FILE 은 Bash 전용이라, shims/RmShim.psm1 을 Import-Module 하는
                 한 줄을 updatedInput 으로 붙인다(판정 없이 — allow 를 붙이면 권한 우회). 명령 우선순위가
                 별칭 > 함수 > cmdlet 이라 같은 이름의 함수가 Remove-Item cmdlet 을 가리고,
                 rm/del/erase/ri/rd/rmdir 별칭이 전부 그 함수로 해석된다.
     한계: `sudo rm` 은 sudo 의 secure_path 가 PATH 를 버려 셰임을 타지 않는다
     (실사용 10,329건 중 2건). 셰임별 규칙은 각 셰임 파일의 주석 참고.
  2) git 미커밋 변경 보호. 명령 문자열을 건드리지 않는다.
     훅 프로세스가 직접 스크래치 인덱스로 스냅샷 커밋을 만들어 refs/claude-backups/<ts>
     에 남기고, 원본 명령은 한 글자도 바꾸지 않고 통과시킨다. `git stash create` 는 추적
     안 된 파일을 담지 못해서(검증됨) 임시 GIT_INDEX_FILE + `add -A` + `write-tree` 를 쓴다.
     대상은 '미커밋 변경을 되돌릴 수 없게 만드는 것'뿐이다 — reflog/ORIG_HEAD 가 이미
     되돌려 주는 rebase·branch -D·commit --amend·filter-branch·gc 와, gc 유예기간 안에서
     `git fsck --unreachable` 로 살릴 수 있는 stash drop/clear 는 다루지 않는다.
     오탐의 대가가 '쓸데없는 백업 ref 한 개'뿐이라 패턴을 느슨하게 잡아도 안전하다.
  3) deny 는 '명령 문자열의 꼴만으로 확실히 실행되면 안 되는 것' 둘뿐이다. 파싱하지 않는다.
       - 루트/홈 전체 삭제 (rm -rf 로 / · /* · ~ · $HOME ; Remove-Item 으로 드라이브 루트·홈)
       - 디스크 파괴 (mkfs*/fdisk/parted/wipefs, dd of=/dev/*, diskutil erase*, > /dev/sdX,
         format <드라이브>:, diskpart, Clear-Disk/Initialize-Disk/Remove-Partition)
     되돌릴 수단이 아예 없는 두 부류라 오탐 비용을 감수한다. 로그상 발동 0회.
  4) ask 는 push 가 원격 커밋을 되돌릴 수 없게 지울 때, 그리고 그것을 확인하지 못할 때다.
     push 가 바꿀 원격 ref 는 git 에게 같은 인자로 `push --dry-run --porcelain` 을 시켜 받는다.
     강제 갱신·삭제될 ref 의 원격 커밋이 전부 로컬에 있으면 refs/claude-backups/ 에 고정하고
     통과시키고(그 ref 를 다시 push 하면 원격이 돌아온다), 하나라도 로컬에 없으면 묻는다.
     권한 규칙에 push 확인이 없으므로 이 판정은 fail-closed 다 — 파싱하지 못한 명령, 모르는
     옵션·축약, -c/--git-dir/GIT_DIR, 알 수 없는 디렉터리, --mirror, 브랜치·태그가 아닌 ref,
     원격 조회 실패는 전부 묻는다. 브랜치 이름은 따지지 않는다. fast-forward push 는 기본
     브랜치여도 확인하지 않는다(로그상 23건 전부 정상 작업이었다).

  종전에 있었으나 실측 근거로 제거한 것: 포크밤 패턴, curl|sh 패턴, find/xargs 대량 삭제
  ask, 체이닝 삭제 ask, 글로브 미일치 deny, `.`/`..` deny, 대상 100개 초과 ask,
  chmod 777 ask, shred ask, shutdown/reboot ask, 훅 내부 오류 ask, 그리고 시크릿 파일
  접근 ask (secrets_guard — 파괴가 아니라 유출 위험이고, 그쪽은 auto mode 분류기가 맡는다).

이 훅은 macOS 기본 인터프리터(/usr/bin/python3, 3.9.x)에서도 실행되어야 한다. 3.10+ 전용
문법(PEP 604 `X | None` 애노테이션 등)을 쓰지 않고, 애노테이션은 `from __future__ import
annotations` 로 지연 평가시킨다.
"""
from __future__ import annotations

import sys
import json
import shlex
import re
import os
import datetime
import subprocess
import tempfile
import time

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HOOKS_DIR, "guard.log")
SHIM_DIR = os.path.join(HOOKS_DIR, "shims")
PS_SHIM = os.path.join(SHIM_DIR, "RmShim.psm1")

# --- deny: 명령 문자열을 그대로 본다. 토큰화도 확장도 하지 않는다. -----------------

# `rm … /`, `rm … /*`, `rm … ~`, `rm … $HOME` 류. 따옴표는 있어도 없어도 잡는다.
# `rm -rf ~/foo` 나 `rm -rf /tmp/x` 는 뒤에 경로가 더 붙어 끝 경계에 걸리지 않는다.
#
# rm 이 '명령 자리'에 있을 때만 본다. 그래야 `grep -rn "rm -rf /" docs/` 처럼 위험한 문자열을
# 데이터로 다루는 명령이 막히지 않는다 — 종전 가드의 오탐이 대부분 이 부류였다. 그 대가로
# `bash -c "rm -rf /"` 는 이 규칙을 비껴가지만, 그때는 셰임이 argv 수준에서 같은 거부를 한다.
_RM_POS = (r"(?:^|[\n;&|(]\s*"
           r"|\b(?:sudo|doas|env|command|exec|builtin|nohup|time|busybox|xargs|then|else|do)\s+"
           r"|\b(?:timeout|nice|ionice|stdbuf|setsid|taskset|chrt)\s+\S+\s+)")
ROOT_DELETE_RE = re.compile(
    _RM_POS + r"""(?:\S*/)?rm\b(?:\s+-{1,2}[^\s]+)*\s+"""
    r"""['"]?(?:/|~|\$HOME|\$\{HOME\})/?\*?['"]?"""
    r"""(?=\s|;|&|\||\)|$)"""
)

# PowerShell 은 매개변수 순서가 자유로워(`Remove-Item -Recurse -Force C:\`) 인접 규칙을
# 쓸 수 없다. 그래서 '삭제 동사'와 '루트 대상'이 같은 구간에 함께 있으면 거부한다.
# 구간 맨 앞(= 명령 자리)에 있을 때만 삭제 동사로 본다. `grep -rn "del ~"` 같은 데이터
# 취급 명령을 잡지 않기 위해서다.
PS_DELETE_RE = re.compile(
    r"""^\s*(?:&\s*)?['"]?(?:[\w:\\/.-]*[\\/])?"""
    r"""(?:Remove-Item|ri|rd|rmdir|del|erase|rm)\b""", re.IGNORECASE)
PS_ROOT_TARGET_RE = re.compile(
    r"""(?:^|[\s'"=,])(?:[A-Za-z]:[\\/]?\*?|\$HOME|\$env:USERPROFILE|%USERPROFILE%|~)"""
    r"""(?=[\s'"]|$)""", re.IGNORECASE)
# 구간 나누기용. 따옴표를 보지 않는 거친 분할이라 잘못 쪼개도 검사가 좁아질 뿐 넓어지지 않는다.
SEGMENT_SPLIT_RE = re.compile(r"[\n;|&]+")

# 디스크 자체를 파괴하는 명령. 산문 속 언급을 피하려고 '명령 자리'(줄 처음, 구분자 뒤,
# sudo 뒤)에서 시작할 때만 잡는다.
_CMD_POS = r"(?:^|[\n;&|(]\s*|\bsudo\s+|\bdoas\s+)"
DISK_DESTROY_RE = re.compile(
    _CMD_POS + r"""(?:mkfs(?:\.\w+)?|newfs(?:_\w+)?|fdisk|gdisk|sgdisk|parted|wipefs)\b"""
    r"""|""" + _CMD_POS + r"""dd\b[^\n]*?\bof=['"]?/dev/"""
    r"""|""" + _CMD_POS + r"""diskutil\b[^\n]*?\b(?:eraseDisk|eraseVolume|secureErase|"""
    r"""partitionDisk|reformat|zeroDisk|deleteContainer)\b"""
    r"""|>\s*/dev/(?:sd|nvme|hd|disk|mmcblk|vd)[a-z0-9]*\b"""
    # Windows. `format` 은 흔한 낱말이라 드라이브 문자를 함께 요구해 오탐을 없앤다.
    r"""|""" + _CMD_POS + r"""format(?:\.com)?\s+['"]?[A-Za-z]:"""
    r"""|""" + _CMD_POS + r"""diskpart\b"""
    r"""|""" + _CMD_POS + r"""(?:Clear-Disk|Initialize-Disk|Remove-Partition|Clear-Volume)\b""",
    re.IGNORECASE,
)

# --- 셰임 선행 ------------------------------------------------------------------

# --- git 스냅샷 -----------------------------------------------------------------

BACKUP_PREFIX = "refs/claude-backups/"
PRUNE_DAYS = 14

# `git clean -fdx` 는 .gitignore 대상까지 지우므로 스냅샷도 그것들을 담아야 한다. 그런데
# 무시된 파일은 node_modules/.venv/빌드 산출물이라 규모가 다르다 — 실측(라즈베리파이 5):
# 한 저장소가 52,722개 1,244MB 였고, 이 기기의 해싱 처리량은 100MB/2,000파일당 4.4초다.
# 그대로 담으면 훅이 1~2분을 잡아먹고 SD 카드에 1.2GB 를 쓴다. 목록 나열은 169ms 로 싸니,
# 먼저 규모를 재고 상한을 넘으면 무시된 파일은 포기한다(추적/미추적 스냅샷은 그대로 남는다).
MAX_IGNORED_FILES = 10000
MAX_IGNORED_BYTES = 100 * 1024 * 1024

GIT_WIPE_RE = re.compile(r"""\bgit\b[^\n]*?\b(?:
      reset\b[^\n]*?--hard
    | (?:checkout|switch)\b[^\n]*?(?:--force\b|\s-[a-zA-Z]*f\b)
    | checkout\b[^\n]*?(?:\s--\s|\s\.(?:\s|$))
    | restore\b
    | clean\b[^\n]*?\s-[a-zA-Z]*f
    | worktree\b[^\n]*?\bremove\b
)""", re.VERBOSE)

# -x/-X 는 .gitignore 대상(.env, 로컬 설정)까지 지운다 → 스냅샷에도 포함해야 한다.
CLEAN_IGNORED_RE = re.compile(r"\bclean\b[^\n]*?\s-[a-zA-Z]*[xX]")
# `git worktree remove <path>` 의 대상은 cwd 가 아니라 인자다.
WORKTREE_RE = re.compile(r"\bworktree\s+remove\s+(?:(?:--force|-f)\s+)*(\S+)")
# 명령이 `cd <경로>` 로 시작하면 백업도 거기서 돌아야 한다. 경로에 변수가 섞이면 특정 불가 →
# 포기한다. 변수 검사는 경로 토큰에만 한다 — 줄 전체를 보면 뒤따르는 `echo "$X"` 때문에 cd 를
# 놓치고 세션 cwd(엉뚱한 저장소)를 백업한다.
LEADING_CD_RE = re.compile(r"^\s*cd\s+['\"]?([^\s'\";&|]+)")

# --- git push -------------------------------------------------------------------

# 이 훅은 셸이 아니어서 명령 문자열에서 push 의 모든 꼴을 알아낼 수 없다. 그래서 알아본 꼴만
# 통과시키고, push 일 수 있는데 알아보지 못한 것은 묻는다(fail-closed). push 가 실제로 무엇을
# 바꾸는지는 직접 풀지 않고 git 에게 같은 인자로 `push --dry-run --porcelain` 을 시켜 받는다 —
# push.default·remote.*.push·pushInsteadOf·글로브·--prune 을 git 과 다르게 풀 여지를 없앤다.
PUSH_WORD_RE = re.compile(r"\bpush\b")
# 환경 변수로 저장소·설정을 바꾸면 훅이 보는 저장소와 push 가 쓰는 저장소가 달라진다.
GIT_ENV_RE = re.compile(r"\bGIT_(?:DIR|WORK_TREE|NAMESPACE|INDEX_FILE|OBJECT_DIRECTORY|COMMON_DIR"
                        r"|CONFIG\w*)\b")
# 이름이 위치에 영향을 주지 않는 git 전역 옵션. 그 밖의 전역 옵션(-c, --git-dir 등)이 붙은 push 는
# 묻는다 — `-c` 는 원격 URL·refspec 을 바꿀 수 있는데, 훅이 그것을 대신 실행해 볼 수는 없다
# (`-c core.sshCommand=...` 는 사용자가 승인하기 전에 임의 명령을 돌린다).
GIT_PLAIN_FLAGS = {"--no-pager", "-p", "-P", "--paginate", "--no-optional-locks", "--no-replace-objects",
                   "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs",
                   "--no-advice"}
# 내장 명령은 별칭으로 가릴 수 없다. 이 밖의 하위 명령은 별칭이 push 를 부르는지 본다.
GIT_BUILTINS = set("""add am apply archive bisect blame branch bundle cat-file check-ignore checkout
    cherry-pick clean clone commit config describe diff fetch for-each-ref format-patch fsck gc grep
    help init log ls-files ls-remote ls-tree merge merge-base mv notes pull rebase reflog remote
    reset restore rev-list rev-parse revert rm shortlog show show-ref sparse-checkout stash status
    submodule switch symbolic-ref tag update-index update-ref version worktree""".split())
# push 옵션 중 알아보는 것. 모르는 옵션·축약(`--del`, `--mirr`)은 git 이 받아 주더라도 묻는다.
PUSH_SHORT = {"f": "--force", "u": "--set-upstream", "q": "--quiet", "v": "--verbose",
              "n": "--dry-run", "d": "--delete", "4": "--ipv4", "6": "--ipv6"}
PUSH_FLAGS = {"--force", "--force-if-includes", "--no-force-if-includes", "--no-force-with-lease",
              "--set-upstream", "--quiet", "--verbose", "--progress", "--no-progress", "--dry-run",
              "--porcelain", "--delete", "--tags", "--follow-tags", "--no-follow-tags", "--all",
              "--branches", "--prune", "--atomic", "--no-atomic", "--verify", "--no-verify",
              "--signed", "--no-signed", "--thin", "--no-thin", "--ipv4", "--ipv6",
              "--no-recurse-submodules", "--force-with-lease"}
# dry-run 계획에 영향이 없거나 출력을 바꾸는 것 — 계획을 받을 때는 뺀다.
PUSH_PLAN_DROP = {"--set-upstream", "--quiet", "--verbose", "--progress", "--no-progress", "--porcelain",
                  "--verify", "--no-verify", "--signed", "--no-signed", "--thin", "--no-thin",
                  "--no-recurse-submodules"}
# 셸 안의 셸·eval 로 넘긴 문자열도 실행된다.
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd"}
EVALS = {"eval", "invoke-expression", "iex"}
RUN_FLAG_RE = re.compile(r"^(?:-[a-zA-Z]*c|-command|/c)$", re.IGNORECASE)
CD_WORDS = {"cd", "chdir", "set-location", "sl"}
DIR_STACK_WORDS = {"pushd", "popd", "push-location", "pop-location"}
LEAD_WORDS = {"if", "then", "do", "else", "elif", "while", "until", "!", "{", "time", "command", "builtin"}
PUNCT = ";&|()<>\n"
# 훅 하나에 쓸 수 있는 시간. Claude Code 가 훅을 시간 초과로 끊으면 판정 없이 명령이 실행된다.
PUSH_BUDGET = 40
# 원격에 닿기 전에 git 이 push 를 거부하는 로컬 오류.
PUSH_LOCAL_FATAL_RE = re.compile(r"^fatal: (?:The current branch \S+ has no upstream branch"
                                 r"|You are not currently on a branch|No configured push destination)", re.M)
HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(\\?)(?:'([^'\n]+)'|\"([^\"\n]+)\"|([A-Za-z0-9_.-]+))")


def log(entry):
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


def emit(decision, reason, updated_input=None, context=None):
    """판정을 내보내고 종료한다.

    decision 이 None 이면 permissionDecision 을 넣지 않는다 — 명령은 평소 권한 규칙대로
    흐르고 additionalContext 만 모델에게 전달된다. 백업 안내처럼 '알리되 승인을 대신하지는
    않아야 하는' 정보에 쓴다.
    """
    out = {"hookEventName": "PreToolUse"}
    if decision is not None:
        out["permissionDecision"] = decision
        out["permissionDecisionReason"] = reason
    # updatedInput 은 판정 없이도 적용된다. 여기에 allow 를 붙이면 권한 프롬프트와 auto mode
    # 분류기를 건너뛰므로, 셰임 선행 줄은 반드시 판정 없이 내보낸다(실측, CC 2.1.283).
    if updated_input is not None:
        out["updatedInput"] = updated_input
    if context:
        out["additionalContext"] = context
    print(json.dumps({"hookSpecificOutput": out}, ensure_ascii=False))
    sys.exit(0)


def _git(args, cwd, env=None, timeout=60, stdin=None):
    # 바이트로 주고받는다. Windows 의 텍스트 모드 파이프는 stdin 의 \n 을 \r\n 으로 바꿔서
    # update-ref --stdin 이 sha 뒤의 \r 때문에 거부했다. surrogateescape 로 ref 이름 바이트를 보존한다.
    p = subprocess.run(["git"] + args, cwd=cwd, env=env,
                       input=None if stdin is None else stdin.encode("utf-8", "surrogateescape"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    p.stdout = p.stdout.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
    p.stderr = p.stderr.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
    return p


# --- deny 판정 -------------------------------------------------------------------


def root_delete_reason(command):
    if ROOT_DELETE_RE.search(command):
        return "Blocked: attempt to delete the entire root/home directory."
    for segment in SEGMENT_SPLIT_RE.split(command):
        if PS_DELETE_RE.search(segment) and PS_ROOT_TARGET_RE.search(segment):
            return "Blocked: attempt to delete the entire drive root/home directory."
    return None


# --- git 스냅샷 백업 -------------------------------------------------------------


def _target_dirs(command, cwd):
    """백업을 돌릴 디렉터리들. 대개 cwd 하나지만 worktree remove 는 대상이 인자에 있다."""
    dirs = []
    base = cwd
    m = LEADING_CD_RE.match(command)
    if m:
        if "$" in m.group(1) or "`" in m.group(1):
            return []
        cand = os.path.expanduser(m.group(1))
        cand = cand if os.path.isabs(cand) else os.path.join(cwd, cand)
        if os.path.isdir(cand):
            base = cand
    dirs.append(base)
    for wt in WORKTREE_RE.findall(command):
        if "$" in wt or "`" in wt:
            continue
        wt = os.path.expanduser(wt.strip("'\""))
        wt = wt if os.path.isabs(wt) else os.path.join(base, wt)
        if os.path.isdir(wt) and wt not in dirs:
            dirs.append(wt)
    return dirs


def _prune(repo):
    """오래된 백업 ref 를 지운다 — 안 지우면 무한히 쌓인다."""
    cutoff = (datetime.datetime.now()
              - datetime.timedelta(days=PRUNE_DAYS)).strftime("%Y%m%dT%H%M%S")
    out = _git(["for-each-ref", "--format=%(refname)", BACKUP_PREFIX], repo).stdout
    for ref in out.split():
        if ref[len(BACKUP_PREFIX):] < cutoff:
            _git(["update-ref", "-d", ref], repo)


def _ignored_volume(repo):
    """무시된 파일까지 담을 때의 규모. 반환: (감당 가능한가, 파일 수, 바이트)."""
    out = _git(["ls-files", "-o", "-z"], repo).stdout
    names = [n for n in out.split("\0") if n]
    if len(names) > MAX_IGNORED_FILES:
        return False, len(names), None
    total = 0
    for n in names:
        try:
            total += os.path.getsize(os.path.join(repo, n))
        except OSError:
            pass
        if total > MAX_IGNORED_BYTES:
            return False, len(names), total
    return True, len(names), total


def git_snapshot(command, cwd):
    """되돌릴 대상을 refs/claude-backups/ 에 고정한다. 반환: 사람에게 보여줄 문구 목록."""
    if not GIT_WIPE_RE.search(command):
        return []

    wants_ignored = bool(CLEAN_IGNORED_RE.search(command))
    notes = []
    for d in _target_dirs(command, cwd):
        r = _git(["rev-parse", "--show-toplevel"], d)
        if r.returncode != 0:
            continue
        repo = r.stdout.strip()

        include_ignored = wants_ignored
        if include_ignored:
            ok, count, size = _ignored_volume(repo)
            if not ok:
                include_ignored = False
                notes.append(
                    "%s has %d .gitignore'd entries%s, so they were left out of the snapshot; including them would "
                    "make the hook take tens of seconds to several minutes. Tracked/untracked files were backed up as usual."
                    % (repo, count, ("" if size is None else " %.0fMB" % (size / 1024 / 1024))))

        fd, idx = tempfile.mkstemp(prefix="claude-backup-idx-")
        os.close(fd)
        os.unlink(idx)                     # git 이 새로 만들게 둔다
        env = dict(os.environ, GIT_INDEX_FILE=idx)
        try:
            head = _git(["rev-parse", "--verify", "HEAD"], repo).stdout.strip()
            if head:
                _git(["read-tree", "HEAD"], repo, env)
            add = ["add", "-A"] + (["-f"] if include_ignored else []) + ["--", "."]
            if _git(add, repo, env).returncode != 0:
                continue
            tree = _git(["write-tree"], repo, env).stdout.strip()
            if not tree:
                continue

            # 되돌릴 것이 없으면(HEAD 와 같은 트리) 백업하지 않는다.
            if head and _git(["rev-parse", "HEAD^{tree}"], repo).stdout.strip() == tree:
                continue
            # 직전 스냅샷과 트리가 같아도 새 ref 를 만들지 않는다.
            last = _git(["for-each-ref", "--sort=-refname", "--count=1",
                         "--format=%(objectname)", BACKUP_PREFIX], repo).stdout.strip()
            if last and _git(["rev-parse", last + "^{tree}"], repo).stdout.strip() == tree:
                continue

            msg = "claude-backup: " + command.splitlines()[0][:120]
            args = ["commit-tree", tree] + (["-p", head] if head else []) + ["-m", msg]
            commit = _git(args, repo, env).stdout.strip()
            if not commit:
                continue
            ref = BACKUP_PREFIX + datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
            if _git(["update-ref", ref, commit], repo).returncode == 0:
                _prune(repo)
                notes.append("Backed up uncommitted changes in %s to %s "
                             "(restore with git checkout %s -- .)." % (repo, ref, ref))
        finally:
            if os.path.exists(idx):
                os.unlink(idx)
    return notes


# --- git push 확인 ---------------------------------------------------------------


class _Unclear(Exception):
    """가역성을 확인하지 못한 push. 메시지가 ask 사유가 된다."""


def _shell_text(command, powershell=False):
    """판정용으로 다듬은 명령 텍스트.

    주석과 따옴표 친 히어독 본문(커밋 메시지 등 데이터)을 걷어내고 줄 잇기를 합친다. 작은따옴표
    안의 `$`·백틱은 실행되지 않으니 지운다. 따옴표 없는 백틱 명령 치환은 줄바꿈으로 바꿔 안의
    명령이 따로 보이게 한다. `2>&1` 의 fd 번호는 지운다(남기면 refspec 처럼 보인다).
    셸을 재현하려는 것이 아니다. 잘못 다듬으면 파싱이 실패하거나 push 가 드러나 묻게 될 뿐이다.
    """
    s, n, out, i = command, len(command), [], 0
    esc = "`" if powershell else "\\"
    quote, word_start, heredocs = None, True, []
    while i < n:
        c = s[i]
        if quote == "'":
            out.append("_" if c in "$`" else c)
            quote = None if c == "'" else quote
            i += 1
            continue
        if quote == '"':
            if c == esc and i + 1 < n:
                out.append(s[i:i + 2])
                i += 2
                continue
            quote = None if c == '"' else quote
            out.append(c)
            i += 1
            continue
        if c == esc and i + 1 < n:
            if s[i + 1] == "\n" or s.startswith("\r\n", i + 1):
                out.append(" ")
                i += 2 if s[i + 1] == "\n" else 3
                continue
            out.append(s[i:i + 2])
            i += 2
            word_start = False
            continue
        if c in "'\"":
            quote = c
        elif word_start and c == "#":
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        elif word_start and c.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            if j < n and s[j] in "<>":
                i = j
                continue
        elif c == "`" and not powershell:
            out.append("\n")
            i += 1
            word_start = True
            continue
        elif c == "<" and not powershell and not s.startswith("<<<", i):
            m = HEREDOC_RE.match(s, i)
            if m:
                heredocs.append((m.group(1) == "-", m.group(3) or m.group(4) or m.group(5),
                                 bool(m.group(2) or m.group(3) or m.group(4))))
                out.append(" ")
                i = m.end()
                continue
        elif c == "\n" and heredocs:
            out.append("\n")
            i += 1
            for strip, delim, quoted in heredocs:
                j = i
                while True:
                    e = s.find("\n", j)
                    line = (s[j:] if e < 0 else s[j:e]).rstrip("\r")
                    if (line.lstrip("\t") if strip else line) == delim:
                        body = s[i:j]
                        # 따옴표 없는 히어독은 본문의 명령 치환을 실행한다.
                        if not quoted and ("$(" in body or "`" in body):
                            out.append(body.replace("`", "\n"))
                        out.append("\n")
                        i = n if e < 0 else e + 1
                        break
                    if e < 0:
                        # 끝 구분자가 없다. 본문을 지우지 않고 명령으로 본다.
                        break
                    j = e + 1
            heredocs = []
            word_start = True
            continue
        out.append(c)
        word_start = c in " \t\r\n;&|()<>"
        i += 1
    return "".join(out)


def _tokens(text, powershell):
    lx = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    lx.commenters = ""
    if powershell:
        lx.escape = ""                      # `C:\repo` 를 그대로 둔다
    return list(lx)


def _cmd_name(word):
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _resolve_dir(base, target):
    if base is None or not target or "$" in target or "`" in target:
        return None
    path = os.path.expanduser(target)
    path = path if os.path.isabs(path) else os.path.join(base, path)
    return path if os.path.isdir(path) else None


def _git_call(words, k, cwd, pushes):
    """words[k] 가 git 일 때 그 호출을 본다. push 면 (인자, 디렉터리)를 pushes 에 넣는다."""
    j, dirs, risky, aliases = k + 1, [], None, {}
    while j < len(words) and words[j].startswith("-"):
        opt, _, val = words[j].partition("=")
        if words[j] in GIT_PLAIN_FLAGS:
            j += 1
            continue
        if opt in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
                   "--super-prefix", "--exec-path") and not val:
            val = words[j + 1] if j + 1 < len(words) else ""
            j += 1
        if opt == "-C":
            dirs.append(val)
        else:
            risky = risky or opt
            if opt == "-c" and val.startswith("alias."):
                name, _, body = val[len("alias."):].partition("=")
                aliases[name] = body
        j += 1
    sub = words[j] if j < len(words) else ""
    if sub == "push":
        if risky:
            raise _Unclear("`git %s` can change which repository or remote the push uses" % risky)
        d = cwd
        for x in dirs:
            d = _resolve_dir(d, x)
        if d is None:
            raise _Unclear("the directory this push runs in cannot be determined from the command")
        pushes.append((words[j + 1:], d))
    elif ("$" in sub or "`" in sub) and PUSH_WORD_RE.search(_command):
        raise _Unclear("the git subcommand is expanded by the shell")
    elif sub and sub not in GIT_BUILTINS:
        body = aliases.get(sub)
        if body is None:
            body = _git(["config", "--get", "alias." + sub], cwd or os.getcwd()).stdout
        if PUSH_WORD_RE.search(body):
            raise _Unclear("git alias `%s` runs push" % sub)


def _simple_command(words, cwd, powershell, pushes, depth):
    """한 단순 명령을 본다. 반환: 이 명령 뒤의 작업 디렉터리(None 이면 알 수 없음)."""
    for k, w in enumerate(words):
        # 셸 안의 셸·eval·명령 치환으로 넘긴 문자열은 그 자리에서 실행된다.
        if depth < 3 and PUSH_WORD_RE.search(w) and (
                "$(" in w or "`" in w and not powershell
                or k and RUN_FLAG_RE.match(words[k - 1]) and any(_cmd_name(x) in SHELLS for x in words[:k - 1])
                or k and _cmd_name(words[0]) in EVALS):
            _walk(w, cwd, powershell, pushes, depth + 1)
    for k, w in enumerate(words):
        name = _cmd_name(w)
        if name in ("git", "git-push"):
            if name == "git-push":
                words = words[:k] + ["git", "push"] + words[k + 1:]
            if any(_cmd_name(x) in ("xargs", "parallel") for x in words[:k]):
                if "push" in words[k + 1:]:
                    raise _Unclear("the push arguments come from xargs")
            _git_call(words, k, cwd, pushes)
    lead = 0
    while lead < len(words) and words[lead] in LEAD_WORDS:
        lead += 1
    names = [_cmd_name(w) for w in words]
    if any(n in DIR_STACK_WORDS for n in names) or any(n in CD_WORDS for n in names[lead + 1:]):
        return None
    if lead < len(words) and names[lead] in CD_WORDS:
        args = words[lead + 1:]
        if "-" in args:
            return None
        args = [a for a in args if not a.startswith("-")]
        return _resolve_dir(cwd, args[0] if args else "~")
    return cwd


def _walk(text, cwd, powershell, pushes, depth=0):
    """명령 텍스트를 단순 명령 단위로 차례로 보며 push 를 모은다. 파싱하지 못하면 ValueError."""
    toks = _tokens(text, powershell)
    stack, words, i = [], [], 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if not set(t) <= set(PUNCT):
            words.append(t)
            continue
        # 리다이렉트와 그 대상은 명령의 일부가 아니다. `>(…)`·`<(…)` 는 프로세스 치환이라 안의 명령이 실행된다.
        if ("<" in t or ">" in t) and "(" not in t:
            i += 1
            if not any(ch in t for ch in "();|\n"):
                continue
        if words:
            cwd = _simple_command(words, cwd, powershell, pushes, depth)
            words = []
        for ch in t:
            if ch == "(":
                stack.append(cwd)
            elif ch == ")" and stack:
                cwd = stack.pop()
    if words:
        _simple_command(words, cwd, powershell, pushes, depth)


def _push_plan_args(args):
    """push 인자를 dry-run 에 넘길 꼴로 바꾼다. 반환: 인자 목록, 사용자 자신이 dry-run 이면 None."""
    out, i, options_done = [], 0, False
    while i < len(args):
        a = args[i]
        i += 1
        if "$" in a or "`" in a:
            raise _Unclear("the argument %r is expanded by the shell" % a)
        if options_done or not a.startswith("-") or a == "-":
            out.append(a)
            continue
        if a == "--":
            options_done = True
            out.append(a)
            continue
        if a == "-o" or a.startswith("--push-option") or a.startswith("--repo") or a.startswith("--recurse-submodules"):
            name, eq, val = a.partition("=")
            if name not in ("-o", "--push-option", "--repo", "--recurse-submodules"):
                raise _Unclear("unknown push option %r" % a)
            if not eq:
                if i >= len(args):
                    raise _Unclear("option %r has no value" % a)
                val = args[i]
                i += 1
            if name == "--repo":
                out.append("--repo=" + val)
            elif name == "--recurse-submodules" and val not in ("no", "check"):
                raise _Unclear("--recurse-submodules=%s also pushes submodules" % val)
            continue
        if a == "--mirror":
            raise _Unclear("--mirror pushes every local ref, including the hook's own backups under %s"
                           % BACKUP_PREFIX)
        if a.startswith("--"):
            names = [a]
        else:                               # `-uf` 처럼 묶인 짧은 옵션
            if any(ch not in PUSH_SHORT for ch in a[1:]):
                raise _Unclear("unknown push option %r" % a)
            names = [PUSH_SHORT[ch] for ch in a[1:]]
        for name in names:
            base = name.partition("=")[0] if name.startswith(("--force-with-lease=", "--signed=")) else name
            if base not in PUSH_FLAGS:
                raise _Unclear("unknown push option %r" % name)
            if base == "--dry-run":
                return None
            if base not in PUSH_PLAN_DROP:
                out.append(name)
    return out


# 원격 조회가 사람의 입력을 기다리며 훅을 멈춰 세우지 않게 한다. GCM 은 GIT_TERMINAL_PROMPT 를
# 무시하고 GUI 로그인 창을 띄운다(Windows). 부분 클론의 cat-file 은 누락 객체를 원격에서 받아 온다.
_NO_PROMPT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_NO_LAZY_FETCH": "1"}


def _net_env(cwd):
    env = dict(os.environ, **_NO_PROMPT_ENV)
    # 호스트 키·암호 프롬프트로 ssh 가 멈추지 않게 한다. 사용자의 ssh 설정이 있으면 건드리지 않는다.
    if not (env.get("GIT_SSH_COMMAND") or env.get("GIT_SSH")
            or _git(["config", "core.sshCommand"], cwd).stdout.strip()):
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    return env


def _left(deadline):
    left = deadline - time.monotonic()
    if left < 1:
        raise subprocess.TimeoutExpired("git", PUSH_BUDGET)
    return min(left, 20)


def _push_plan(args, cwd, deadline):
    """git 이 이 push 로 바꿀 원격 ref. 반환: {url: [(flag, src, dst)]}.

    flag 는 porcelain 의 것이다: `+` 강제 갱신, `-` 삭제, `*` 새 ref, ` ` fast-forward, `!` 거부.
    """
    p = _git(["push", "--dry-run", "--porcelain", "--no-verify", "--recurse-submodules=no"] + args,
             cwd, _net_env(cwd), timeout=_left(deadline))
    if "fatal:" in p.stderr:
        # 원격에 닿기 전에 실패하는 로컬 설정 오류는 실제 push 도 똑같이 실패한다 — 아무것도 바뀌지 않는다.
        if PUSH_LOCAL_FATAL_RE.search(p.stderr):
            return {}
        last = [line for line in p.stderr.splitlines() if line.startswith("fatal:")][-1]
        raise _Unclear("git could not plan this push (%s)" % last)
    plan, url = {}, None
    for line in p.stdout.splitlines():
        if line.startswith("To "):
            url = line[3:]
            plan.setdefault(url, [])
        elif url and len(line) > 2 and line[1] == "\t":
            src, _, dst = line.split("\t")[1].partition(":")
            plan[url].append((line[0], src, dst))
    return plan


def _remote_refs(url, cwd, deadline):
    """원격의 {ref: sha}. 조회하지 못하면 None — 그때는 가역성을 보장할 수 없다."""
    r = _git(["ls-remote", url], cwd, _net_env(cwd), timeout=_left(deadline))
    if r.returncode != 0:
        return None
    refs = {}
    for line in r.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/") and not ref.endswith("^{}"):
            refs[ref] = sha
    return refs


def _check_push(args, cwd, deadline):
    """push 하나가 되돌릴 수 있는지 본다. 되돌릴 수 없거나 확인하지 못하면 _Unclear. 반환: 안내 문구들."""
    args = _push_plan_args(args)
    if args is None:
        return []
    notes = []
    for url, entries in _push_plan(args, cwd, deadline).items():
        for _flag, src, dst in entries:
            # 백업 ref 를 내보내면 스냅샷에 담긴 .gitignore 대상(.env 등)까지 원격에 올라간다.
            if src.startswith(BACKUP_PREFIX) or not dst.startswith(("refs/heads/", "refs/tags/")):
                raise _Unclear("it writes %s on %s, which is not a branch or tag" % (dst or src, url))
        doomed = [dst for flag, _src, dst in entries if flag in "+-"]
        if doomed:
            notes += _pin_remote(url, doomed, cwd, deadline)
    return notes


def _pin_remote(url, refs, cwd, deadline):
    """url 의 refs 에서 사라질 원격 커밋이 전부 로컬에 있으면 고정한다. 반환: 안내 문구들."""
    remote_refs = _remote_refs(url, cwd, deadline)
    if remote_refs is None:
        raise _Unclear("could not query remote %s, so it cannot be verified that the remote commits this "
                       "push would overwrite or delete are still present locally" % url)
    at_risk = {ref: remote_refs[ref] for ref in refs if ref in remote_refs}
    if not at_risk:
        return []

    check = _git(["cat-file", "--batch-check"], cwd, dict(os.environ, **_NO_PROMPT_ENV),
                 stdin="".join(sha + "\n" for sha in at_risk.values()))
    absent = {line.split()[0] for line in check.stdout.splitlines() if line.endswith(" missing")}
    missing = sorted(ref for ref, sha in at_risk.items() if sha in absent)
    if check.returncode != 0 or missing:
        raise _Unclear("remote %s has commits at %s that are not present locally. This push would overwrite "
                       "or delete them irreversibly (running git fetch first preserves them locally)"
                       % (url, ", ".join(missing or sorted(at_risk))))

    # 같은 이름의 로컬 ref 가 이미 같은 커밋을 쥐고 있으면 고정하지 않는다.
    held = set(_git(["for-each-ref", "--format=%(refname) %(objectname)"], cwd).stdout.splitlines())
    pins = {ref: sha for ref, sha in at_risk.items() if "%s %s" % (ref, sha) not in held}
    if not pins:
        return []
    # 한 명령 속 여러 push·여러 URL 이 같은 초에 고정해도 겹치지 않게 번호를 붙이고, `create` 로
    # 덮어쓰기를 막는다(겹치면 실패 → ask). `/` 는 유지한다 — feat/x 와 feat-x 를 구분해야 한다.
    global _pin_seq
    _pin_seq += 1
    base = "%s%s-push/%d/" % (BACKUP_PREFIX, datetime.datetime.now().strftime("%Y%m%dT%H%M%S"),
                              _pin_seq)
    tx = "".join("create %s%s %s\n" % (base, ref[len("refs/"):], sha) for ref, sha in pins.items())
    if _git(["update-ref", "--stdin"], cwd, stdin=tx).returncode != 0:
        raise _Unclear("could not pin locally the commits on remote %s that this push would overwrite" % url)
    _prune(cwd)
    shown = sorted(pins)
    listed = ", ".join(shown[:5]) + (" and %d more" % (len(shown) - 5) if len(shown) > 5 else "")
    return ["Before the push, pinned remote %s refs %s under %s for %d days (to undo: git push --force "
            "%s %s<ref>:refs/<ref>, e.g. %s%s:%s)."
            % (url, listed, base, PRUNE_DAYS, url, base, base, shown[0][len("refs/"):], shown[0])]


_pin_seq = 0
_command = ""                               # 지금 보는 명령 원문 (셸이 확장하는 하위 명령 판정용)


def push_check(command, cwd, powershell=False):
    """원격 커밋을 덮어쓰거나 지우는 push 가 되돌릴 수 있는지 본다. 반환: (ask 사유, 안내 문구들).

    git 의 dry-run 계획에서 강제 갱신(`+`)·삭제(`-`)될 원격 ref 를 받아, 사라질 커밋이 전부 로컬에
    있으면 refs/claude-backups/<ts>-push/ 에 고정하고 통과시킨다 — 그 ref 를 다시 push 하면 원격이
    원래대로 돌아온다. 하나라도 로컬에 없거나, 원격을 조회하지 못하거나, push 를 알아보지 못하면
    묻는다. fast-forward·새 ref push 는 원격 히스토리를 지우지 않으므로 그대로 통과한다.
    """
    # push 라는 낱말이 없어도 git 별칭이 push 를 부를 수 있다.
    if not PUSH_WORD_RE.search(command) and "git" not in command.lower():
        return None, []
    global _command
    _command = command
    deadline = time.monotonic() + PUSH_BUDGET
    try:
        pushes = []
        try:
            _walk(_shell_text(command, powershell), cwd, powershell, pushes)
        except ValueError:
            if not PUSH_WORD_RE.search(command):
                return None, []
            raise _Unclear("the command could not be parsed")
        if pushes and GIT_ENV_RE.search(command):
            raise _Unclear("the command sets a GIT_* variable that changes the repository the push uses")
        notes = []
        for args, d in pushes:
            notes += _check_push(args, d, deadline)
        return None, notes
    except _Unclear as exc:
        return "Could not confirm that this push is reversible: %s. Continue?" % exc, []
    except subprocess.TimeoutExpired:
        return ("Checking the remote took too long, so it cannot be verified that this push is reversible. "
                "Continue?"), []


# --- 셰임 선행 줄 ----------------------------------------------------------------


def write_shim_path(env_file):
    """SessionStart: 이후 모든 Bash 명령의 PATH 맨 앞에 shims/ 를 둔다.

    stdout 에는 아무것도 쓰지 않는다 — SessionStart 의 stdout 은 모델 컨텍스트에 들어간다.
    """
    if not env_file or not os.path.isdir(SHIM_DIR):
        return
    d = SHIM_DIR
    if os.name == "nt":
        # Git Bash 의 PATH 는 ':' 구분이라 `C:\...` 를 그대로 넣으면 쪼개진다 → /c/... 로.
        drive, rest = os.path.splitdrive(d)
        d = "/" + drive.rstrip(":").lower() + rest.replace("\\", "/")
    q = shlex.quote(d)
    # startup/resume/clear/compact 마다 다시 불려 줄이 쌓여도 PATH 가 길어지지 않게 한다.
    # newline 고정: Windows 텍스트 모드는 \r\n 을 쓰고, bash 는 그 줄을 문법 오류로 버린다.
    with open(env_file, "a", encoding="utf-8", newline="\n") as f:
        f.write('case ":$PATH:" in *:%s:*) ;; *) PATH=%s:$PATH; export PATH ;; esac\n' % (q, q))


def shim_prefix(tool_name, command):
    """PowerShell 명령 앞에 붙일 한 줄. 붙일 이유가 없으면 None.

    원본 명령은 한 글자도 바꾸지 않는다 — 인자 해석은 전적으로 PowerShell 몫이다.
    """
    if tool_name == "PowerShell":
        if not PS_DELETE_RE.search(command) or not os.path.isfile(PS_SHIM):
            return None
        p = PS_SHIM.replace("'", "''")
        return ("if (-not (Get-Module RmShim)) { Import-Module '%s' -DisableNameChecking "
                "-Global -ErrorAction SilentlyContinue }\n" % p)

    return None


# --- 진입점 ----------------------------------------------------------------------


def read_event_json():
    """stdin 에서 훅 이벤트 JSON 을 읽는다. 선행 BOM(U+FEFF)은 벗겨낸다.

    BOM 이 남아 있으면 json.loads 가 실패하고, 이 훅은 파싱 실패를 '판정할 수 없는 입력'으로
    보고 조용히 exit 0 한다 — 가드가 통째로 무력화되는데 아무 신호도 남지 않는다. Windows
    PowerShell 5.1 의 Process.StandardInput 이 실제로 이 상황을 만든다(AutoFlush StreamWriter
    가 스트림 접근 시점에 인코딩 preamble 을 먼저 흘려보내는데, .NET Framework 에는
    StandardInputEncoding 이 없어 호출부에서 끌 수 없다). RFC 8259 도 파서가 BOM 을 무시하는
    것을 허용하므로, 받는 쪽에서 벗기는 것이 옳다."""
    return sys.stdin.read().lstrip("\ufeff")


def main():
    try:
        raw = read_event_json()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("hook_event_name") == "SessionStart":
        write_shim_path(os.environ.get("CLAUDE_ENV_FILE"))
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    reason = root_delete_reason(command)
    if reason:
        log({"tool": tool_name, "command": command, "decision": "deny-root-delete"})
        emit("deny", reason)

    if DISK_DESTROY_RE.search(command):
        log({"tool": tool_name, "command": command, "decision": "deny-disk-destroy"})
        emit("deny", "Blocked: disk-level destructive commands are irreversible.")

    cwd = data.get("cwd") or os.getcwd()

    try:
        reason, notes = push_check(command, cwd, tool_name == "PowerShell")
    except Exception as exc:  # noqa: BLE001 — 가역성을 확인하지 못한 push 를 그냥 내보내지 않는다
        log({"decision": "guard-error", "error": repr(exc)})
        reason, notes = ("A hook error occurred while checking whether the push is reversible (%r). Continue?" % exc
                         if PUSH_WORD_RE.search(command) else None), []
    if reason:
        log({"tool": tool_name, "command": command, "decision": "ask-push-irreversible"})
        emit("ask", reason)

    notes += git_snapshot(command, cwd)

    prefix = shim_prefix(tool_name, command)
    if prefix:
        log({"tool": tool_name, "command": command, "decision": "prepend-shim"})
        emit(None, "", updated_input=dict(data.get("tool_input", {}), command=prefix + command),
             context="\n".join(notes) if notes else None)

    if notes:
        log({"tool": tool_name, "command": command, "decision": "git-snapshot", "notes": notes})
        emit(None, "", context="\n".join(notes))

    sys.exit(0)


if __name__ == "__main__":
    # 훅이 예외로 죽으면 Claude Code 는 판정 없이 명령을 그대로 실행한다(fail-open).
    # 종전에는 이때 ask 로 승격했지만, 실측상 훅 내부 오류로 인한 ask 는 전부 마찰이기만
    # 했다. 이제 남은 판정은 되돌릴 수 없는 두 부류뿐이고 나머지는 복구 보조라, 오류는
    # 로그에 남기고 조용히 통과시킨다.
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        log({"decision": "guard-error", "error": repr(exc)})
        sys.exit(0)
