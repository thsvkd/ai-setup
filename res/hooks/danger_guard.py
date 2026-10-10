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
  4) ask 는 push 가 원격 커밋을 되돌릴 수 없게 지울 때뿐이다. force push(`+refspec`,
     --force-with-lease, HEAD/@, 글로브 refspec 포함), --mirror/--prune, 원격 ref 삭제는 push URL 에
     `git ls-remote` 해 사라질 원격 커밋을 조회한다. 전부 로컬에 있으면 refs/claude-backups/ 에
     고정하고 통과시키고(그 ref 를 다시 push 하면 원격이 돌아온다), 하나라도 로컬에 없거나 원격을
     조회하지 못할 때만 확인한다. 브랜치 이름은 따지지 않는다. fast-forward push 는 기본
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

# git 전역 옵션 중 값을 따로 받는 것들(`git -C "my repo" push`). 정규식으로는 따옴표로 묶인
# 값을 넘길 수 없어 구간을 shlex 로 나눠 본다.
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
                  "--super-prefix"}
PUSH_VALUE_OPTS = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
PUSH_ALL_FLAGS = {"--all", "--branches"}
PUSH_DELETE_FLAGS = {"--delete", "-d"}
# `-f` 는 `-uf` 처럼 다른 짧은 옵션과 묶여 올 수 있다.
PUSH_FORCE_RE = re.compile(r"^(?:--force|--force-with-lease(?:=.*)?|-[a-zA-Z]*f[a-zA-Z]*)$")


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
    return subprocess.run(["git"] + args, cwd=cwd, env=env, input=stdin,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=timeout)


# --- deny 판정 -------------------------------------------------------------------


def root_delete_reason(command):
    if ROOT_DELETE_RE.search(command):
        return "루트/홈 디렉터리 전체를 삭제하려는 시도는 차단합니다."
    for segment in SEGMENT_SPLIT_RE.split(command):
        if PS_DELETE_RE.search(segment) and PS_ROOT_TARGET_RE.search(segment):
            return "드라이브 루트/홈 디렉터리 전체를 삭제하려는 시도는 차단합니다."
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
                    "%s 의 .gitignore 대상이 %d개%s라 스냅샷에서 제외했습니다 — 담으면 훅이 "
                    "수십 초에서 수 분을 잡아먹습니다. 추적/미추적 파일은 그대로 백업했습니다."
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
                notes.append("%s 의 미커밋 변경을 %s 에 백업했습니다 "
                             "(git checkout %s -- . 로 복구)." % (repo, ref, ref))
        finally:
            if os.path.exists(idx):
                os.unlink(idx)
    return notes


# --- git push 확인 ---------------------------------------------------------------


def _find_pushes(command):
    """명령 속 `git … push` 전부. 반환: [(push 뒤 인자들, -C 디렉터리들)]."""
    found = []
    for segment in SEGMENT_SPLIT_RE.split(command):
        if "push" not in segment:
            continue
        try:
            toks = shlex.split(segment)
        except ValueError:
            continue
        for i, tok in enumerate(toks):
            if os.path.basename(tok) != "git":
                continue
            j, dirs = i + 1, []
            while j < len(toks) and toks[j].startswith("-"):
                if toks[j] in GIT_VALUE_OPTS and j + 1 < len(toks):
                    if toks[j] == "-C":
                        dirs.append(toks[j + 1])
                    j += 2
                else:
                    j += 1
            if j < len(toks) and toks[j] == "push":
                found.append((toks[j + 1:], dirs))
                break
    return found


def _push_remote(cwd):
    """원격 이름 없이 `git push` 했을 때 git 이 고르는 원격."""
    b = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()
    for key in ("branch.%s.pushRemote" % b, "remote.pushDefault", "branch.%s.remote" % b):
        r = _git(["config", "--get", key], cwd).stdout.strip()
        if r:
            return r
    return "origin"


# 원격 조회가 사람의 입력을 기다리며 훅을 멈춰 세우지 않게 한다. GCM 은 GIT_TERMINAL_PROMPT 를
# 무시하고 GUI 로그인 창을 띄운다(Windows). 부분 클론의 cat-file 은 누락 객체를 원격에서 받아 온다.
_NO_PROMPT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_NO_LAZY_FETCH": "1"}


def _push_urls(remote, cwd):
    """push 가 실제로 쓰는 URL 전부(pushurl·pushInsteadOf 반영, pushurl 이 여럿이면 git 은 전부에 쓴다).
    원격 이름 대신 URL 을 직접 주면 그대로 쓴다."""
    return _git(["remote", "get-url", "--push", "--all", remote], cwd).stdout.split() or [remote]


def _remote_refs(url, cwd):
    """원격의 {ref: sha}. 조회하지 못하면 None — 그때는 가역성을 보장할 수 없다."""
    env = dict(os.environ, **_NO_PROMPT_ENV)
    # 호스트 키·암호 프롬프트로 ssh 가 멈추지 않게 한다. 사용자의 ssh 설정이 있으면 건드리지 않는다.
    if not (env.get("GIT_SSH_COMMAND") or env.get("GIT_SSH")
            or _git(["config", "core.sshCommand"], cwd).stdout.strip()):
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    r = _git(["ls-remote", url], cwd, env, timeout=20)
    if r.returncode != 0:
        return None
    refs = {}
    for line in r.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/") and not ref.endswith("^{}"):
            refs[ref] = sha
    return refs


def _check_push(args, dirs, cwd):
    """push 하나가 되돌릴 수 있는지 본다. 반환: (ask 사유, 안내 문구들)."""
    for d in dirs:                          # 판정은 push 가 실제로 도는 저장소에서 한다
        cwd = os.path.join(cwd, os.path.expanduser(d))
    if not os.path.isdir(cwd) or _git(["rev-parse", "--git-dir"], cwd).returncode != 0:
        return None, []

    force = any(PUSH_FORCE_RE.match(a) for a in args)
    positionals = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in PUSH_VALUE_OPTS:
            skip = True
            continue
        if a.startswith("-"):
            continue
        positionals.append(a)
    remote = positionals[0] if positionals else _push_remote(cwd)
    refspecs = positionals[1:]

    def local_refs(prefix):
        return _git(["for-each-ref", "--format=%(refname)", prefix], cwd).stdout.split()

    # 덮어쓰거나 지울 수 있는 원격 ref. wide 면 원격의 모든 ref 가 대상이다.
    wide = (any(a in ("--mirror", "--prune") for a in args)
            or _git(["config", "--bool", "remote.%s.mirror" % remote], cwd).stdout.strip() == "true")
    deleting = any(a in PUSH_DELETE_FLAGS for a in args)
    names = []
    if force and any(a in PUSH_ALL_FLAGS for a in args):
        names += local_refs("refs/heads/")
    if force and "--tags" in args:
        names += local_refs("refs/tags/")
    if force and not refspecs and not any(a in PUSH_ALL_FLAGS or a == "--tags" for a in args):
        names.append("HEAD")
    for spec in refspecs:
        if deleting or (spec.startswith(":") and len(spec) > 1):
            names.append(spec.lstrip(":"))  # `--delete origin x` 와 빈 src refspec `origin :x`
        elif force or spec.startswith("+"):   # `+` 는 그 refspec 만 force 한다
            dst = spec.split(":")[-1].lstrip("+")
            if "*" in dst or not dst:          # 글로브·`:`(일치 브랜치 전부)
                wide = True
            else:
                names.append(dst)
    if not wide and not names:
        return None, []                     # fast-forward·새 브랜치 push 는 원격 커밋을 지우지 않는다
    if any(n in ("HEAD", "@") for n in names):
        b = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()
        names = [b if n in ("HEAD", "@") else n for n in names]

    notes = []
    for url in _push_urls(remote, cwd):
        reason, note = _pin_remote(url, wide, names, cwd)
        if reason:
            return reason, []
        notes += note
    return None, notes


def _pin_remote(url, wide, names, cwd):
    """url 에서 사라질 원격 커밋이 전부 로컬에 있으면 고정한다. 반환: (ask 사유, 안내 문구들)."""
    remote_refs = _remote_refs(url, cwd)
    if remote_refs is None:
        return ("원격(%s)을 조회하지 못해, 이 push 가 덮어쓰거나 지울 원격 커밋이 로컬에 남아 "
                "있는지 확인할 수 없습니다. 계속할까요?" % url), []
    # git 이 짧은 대상 이름을 푸는 규칙(ref_rev_parse_rules)을 그대로 따른다.
    at_risk = {ref: sha for ref, sha in remote_refs.items()
               if wide or any(ref in (n, "refs/" + n, "refs/tags/" + n, "refs/heads/" + n,
                                      "refs/remotes/" + n) for n in names)}
    if not at_risk:
        return None, []

    check = _git(["cat-file", "--batch-check"], cwd, dict(os.environ, **_NO_PROMPT_ENV),
                 stdin="".join(sha + "\n" for sha in at_risk.values()))
    absent = {line.split()[0] for line in check.stdout.splitlines() if line.endswith(" missing")}
    missing = sorted(ref for ref, sha in at_risk.items() if sha in absent)
    if check.returncode != 0 or missing:
        return ("원격 %s 의 %s 에 로컬에 없는 커밋이 있습니다. 이 push 는 그 커밋을 덮어쓰거나 지워 "
                "되돌릴 수 없게 만듭니다(먼저 git fetch 하면 로컬에 보존됩니다). 계속할까요?"
                % (url, ", ".join(missing or sorted(at_risk)))), []

    # 같은 이름의 로컬 ref 가 이미 같은 커밋을 쥐고 있으면 고정하지 않는다.
    held = set(_git(["for-each-ref", "--format=%(refname) %(objectname)"], cwd).stdout.splitlines())
    pins = {ref: sha for ref, sha in at_risk.items() if "%s %s" % (ref, sha) not in held}
    if not pins:
        return None, []
    # 한 명령 속 여러 push·여러 URL 이 같은 초에 고정해도 겹치지 않게 번호를 붙이고, `create` 로
    # 덮어쓰기를 막는다(겹치면 실패 → ask). `/` 는 유지한다 — feat/x 와 feat-x 를 구분해야 한다.
    global _pin_seq
    _pin_seq += 1
    base = "%s%s-push/%d/" % (BACKUP_PREFIX, datetime.datetime.now().strftime("%Y%m%dT%H%M%S"),
                              _pin_seq)
    tx = "".join("create %s%s %s\n" % (base, ref[len("refs/"):], sha) for ref, sha in pins.items())
    if _git(["update-ref", "--stdin"], cwd, stdin=tx).returncode != 0:
        return ("원격 %s 의 덮어쓸 커밋을 로컬에 고정하지 못했습니다. 계속할까요?" % url), []
    _prune(cwd)
    shown = sorted(pins)
    listed = ", ".join(shown[:5]) + (" 외 %d개" % (len(shown) - 5) if len(shown) > 5 else "")
    return None, ["push 전 원격 %s 의 %s 를 %s 아래에 고정했습니다 (되돌리기: git push --force "
                  "%s %s<ref>:refs/<ref>, 예: %s%s:%s)."
                  % (url, listed, base, url, base, base, shown[0][len("refs/"):], shown[0])]


_pin_seq = 0


def push_check(command, cwd):
    """원격 커밋을 덮어쓰거나 지우는 push 가 되돌릴 수 있는지 본다. 반환: (ask 사유, 안내 문구들).

    대상은 force push(`+refspec` 포함), 원격 ref 삭제, --mirror/--prune 이다. 사라질 원격 커밋이
    전부 로컬에 있으면 refs/claude-backups/<ts>-push/ 에 고정하고 통과시킨다 — 그 ref 를 다시
    push 하면 원격이 원래대로 돌아온다. 하나라도 로컬에 없거나 원격을 조회하지 못하면 묻는다.
    fast-forward push 는 원격 히스토리를 지우지 않으므로 보지 않는다.
    """
    dirs = _target_dirs(command, cwd)       # 선행 `cd <경로>` 를 따른다
    base = dirs[0] if dirs else cwd
    notes = []
    for args, cdirs in _find_pushes(command):
        try:
            reason, n = _check_push(args, cdirs, base)
        except subprocess.TimeoutExpired:
            reason, n = "원격 조회가 시간을 넘겨 이 push 가 되돌릴 수 있는지 확인하지 못했습니다. 계속할까요?", []
        if reason:
            return reason, []
        notes += n
    return None, notes


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
        emit("deny", "디스크 레벨 파괴 명령은 되돌릴 수 없어 차단합니다.")

    cwd = data.get("cwd") or os.getcwd()

    reason, notes = push_check(command, cwd)
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
