"""danger_guard.py 의 git 스냅샷 백업 '실측' 테스트.

가짜 이벤트만 넣고 판정 문자열을 보는 것으로는 이 기능을 검증할 수 없다. 실제로 검증해야
하는 것은 "파괴적 git 명령을 실행한 뒤 잃어버린 내용을 정말 되찾을 수 있는가"다. 그래서
임시 저장소를 진짜로 만들고, 훅을 돌리고, 파괴 명령을 실제로 실행한 뒤, 백업 ref 에서
복구되는지를 본다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "res" / "hooks" / "danger_guard.py"
BACKUP_PREFIX = "refs/claude-backups/"


def git(repo, *args):
    # 로캘 인코딩(Windows 한국어는 cp949)으로 읽으면 UTF-8 내용이 디코딩에 실패해 stdout 이 None 이 된다.
    return subprocess.run(["git"] + list(args), cwd=str(repo),
                          capture_output=True, text=True, encoding="utf-8")


def run_hook(command, cwd):
    event = json.dumps({"tool_name": "Bash", "cwd": str(cwd),
                        "tool_input": {"command": command}})
    proc = subprocess.run([sys.executable, "-X", "utf8", str(HOOK)],
                          input=event, capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else None


def latest_backup(repo):
    r = git(repo, "for-each-ref", "--sort=-refname", "--count=1",
            "--format=%(refname)", BACKUP_PREFIX)
    return r.stdout.strip()


def backup_count(repo):
    r = git(repo, "for-each-ref", "--format=%(refname)", BACKUP_PREFIX)
    return len(r.stdout.split())


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    git(d, "init", "-q", ".")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "tracked.txt").write_text("committed\n", encoding="utf-8")
    (d / ".gitignore").write_text("*.env\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "init")
    return d


def restore_from_backup(repo, ref):
    """백업 ref 의 내용을 워킹트리로 되돌린다 — 사용자가 안내받는 복구 절차 그대로."""
    return git(repo, "checkout", ref, "--", ".")


# --- 파괴 → 복구 ------------------------------------------------------------------


def test_reset_hard_backs_up_tracked_modification(repo):
    (repo / "tracked.txt").write_text("WIP 편집\n", encoding="utf-8")
    run_hook("git reset --hard HEAD", repo)
    ref = latest_backup(repo)
    assert ref, "a backup ref must be created"

    git(repo, "reset", "--hard", "HEAD")
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "committed\n"

    restore_from_backup(repo, ref)
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "WIP 편집\n"


def test_clean_backs_up_untracked_files(repo):
    (repo / "untracked.txt").write_text("새 파일\n", encoding="utf-8")
    run_hook("git clean -fd", repo)
    ref = latest_backup(repo)
    assert ref

    git(repo, "clean", "-fdq")
    assert not (repo / "untracked.txt").exists()

    restore_from_backup(repo, ref)
    assert (repo / "untracked.txt").read_text(encoding="utf-8") == "새 파일\n"


def test_clean_x_backs_up_gitignored_files(repo):
    """`git clean -fdx` 는 .gitignore 대상(.env, 로컬 설정)까지 지운다.

    git 어디에도 남지 않는 파일이라 -x 일 때는 스냅샷에 무시된 파일까지 담아야 한다.
    """
    (repo / "local.env").write_text("SECRET=1\n", encoding="utf-8")
    run_hook("git clean -fdx", repo)
    ref = latest_backup(repo)
    assert ref

    git(repo, "clean", "-fdxq")
    assert not (repo / "local.env").exists()

    restore_from_backup(repo, ref)
    assert (repo / "local.env").read_text(encoding="utf-8") == "SECRET=1\n"


def test_clean_without_x_does_not_capture_ignored(repo):
    """-x 가 없으면 무시된 파일은 지워지지도, 담기지도 않는다 (불필요한 시크릿 사본 방지)."""
    (repo / "local.env").write_text("SECRET=1\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("x\n", encoding="utf-8")
    run_hook("git clean -fd", repo)
    ref = latest_backup(repo)
    listing = git(repo, "ls-tree", "-r", "--name-only", ref).stdout
    assert "untracked.txt" in listing
    assert "local.env" not in listing


def test_checkout_path_backs_up_worktree(repo):
    (repo / "tracked.txt").write_text("되돌려질 편집\n", encoding="utf-8")
    run_hook("git checkout -- tracked.txt", repo)
    ref = latest_backup(repo)
    assert ref

    git(repo, "checkout", "--", "tracked.txt")
    restore_from_backup(repo, ref)
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "되돌려질 편집\n"


def test_worktree_remove_backs_up_the_target_worktree(repo, tmp_path):
    """`git worktree remove` 의 대상은 cwd 가 아니라 인자다 — 거기서 백업해야 한다."""
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "-b", "side")
    (wt / "tracked.txt").write_text("워크트리 미커밋\n", encoding="utf-8")

    run_hook("git worktree remove --force %s" % wt, repo)
    ref = latest_backup(repo)
    assert ref, "a worktree snapshot must remain in the main repository"
    blob = git(repo, "show", "%s:tracked.txt" % ref).stdout
    assert blob == "워크트리 미커밋\n"


def test_leading_cd_targets_that_repo(repo, tmp_path):
    (repo / "tracked.txt").write_text("다른 디렉터리 편집\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    run_hook("cd %s && git reset --hard" % repo, elsewhere)
    assert backup_count(repo) == 1


def test_leading_cd_with_variable_is_skipped(repo, tmp_path):
    """대상 저장소를 특정할 수 없으면 엉뚱한 곳을 백업하느니 아무것도 하지 않는다."""
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    run_hook('cd "$TARGET" && git reset --hard', elsewhere)
    assert backup_count(repo) == 0


def _other_repo_with_changes(tmp_path):
    d = tmp_path / "session-cwd"
    d.mkdir()
    git(d, "init", "-q", ".")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "f.txt").write_text("committed\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "init")
    (d / "f.txt").write_text("세션 cwd 미커밋\n", encoding="utf-8")
    return d


def test_leading_cd_wins_even_if_line_has_variables_elsewhere(repo, tmp_path):
    """회귀: 경로 뒤 어딘가에 `$` 가 있으면 cd 를 무시하고 세션 cwd 를 백업했다."""
    (repo / "tracked.txt").write_text("다른 디렉터리 편집\n", encoding="utf-8")
    session = _other_repo_with_changes(tmp_path)
    run_hook('cd %s && git checkout -- . && echo "$HOME"' % repo, session)
    assert backup_count(repo) == 1
    assert backup_count(session) == 0


def test_leading_cd_with_variable_does_not_back_up_session_cwd(tmp_path):
    """cd 대상을 특정할 수 없을 때 세션 cwd 를 대신 백업하면 엉뚱한 저장소를 백업한다."""
    session = _other_repo_with_changes(tmp_path)
    run_hook('cd "$TARGET" && git reset --hard', session)
    assert backup_count(session) == 0


# --- 노이즈 비용 ------------------------------------------------------------------


def test_clean_worktree_makes_no_backup(repo):
    run_hook("git reset --hard HEAD", repo)
    assert backup_count(repo) == 0


def test_identical_tree_is_not_backed_up_twice(repo):
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    run_hook("git reset --hard", repo)
    run_hook("git reset --hard", repo)
    assert backup_count(repo) == 1


def test_safe_git_commands_make_no_backup(repo):
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    for cmd in ["git status --short", "git log --oneline -3", "git stash push -m x",
                "git rebase --continue", "git branch -D old", "git commit --amend"]:
        run_hook(cmd, repo)
    assert backup_count(repo) == 0


def test_restore_staged_still_backs_up(repo):
    """`git restore --staged` 자체는 손실이 없지만, 오탐 비용이 ref 하나뿐이라 굳이 가르지 않는다."""
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    run_hook("git restore --staged tracked.txt", repo)
    assert backup_count(repo) == 1


def test_non_git_directory_is_silent(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert run_hook("git reset --hard", d) is None


def test_command_is_never_rewritten(repo):
    """백업은 훅 프로세스가 직접 한다 — 명령 문자열에는 손대지 않는다."""
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    payload = run_hook("git reset --hard HEAD", repo)
    assert payload is not None
    out = payload["hookSpecificOutput"]
    assert "updatedInput" not in out
    assert "permissionDecision" not in out
    assert BACKUP_PREFIX in out["additionalContext"]


def test_old_backups_are_pruned(repo):
    (repo / "tracked.txt").write_text("x\n", encoding="utf-8")
    stale = BACKUP_PREFIX + "20200101T000000"
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", stale, head)
    run_hook("git reset --hard", repo)
    refs = git(repo, "for-each-ref", "--format=%(refname)", BACKUP_PREFIX).stdout
    assert stale not in refs


# --- push 확인 --------------------------------------------------------------------
#
# 계약: 원격 커밋을 덮어쓰거나 지우는 push 는, 사라질 커밋이 전부 로컬에 있으면 refs/claude-backups/
# 에 고정하고 통과한다. 하나라도 로컬에 없으면(다른 사람이 push 했고 아직 fetch 하지 않음) 묻는다.


def _with_origin(repo, tmp_path, default_branch):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/%s" % default_branch)
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD",
        "refs/remotes/origin/%s" % default_branch)
    return bare


def _remote_ahead(bare, tmp_path, *branches):
    """다른 클론이 branches 에 커밋을 push 한다 — 그 커밋은 이 저장소에 없다."""
    other = tmp_path / "other"
    if not other.exists():
        subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
        git(other, "config", "user.email", "o@o")
        git(other, "config", "user.name", "o")
        # 원격 HEAD 가 없는 브랜치를 가리키면 클론이 빈 채로 시작한다 — 기존 커밋 위에서 쌓는다.
        base = [r for r in git(other, "for-each-ref", "--format=%(refname)",
                               "refs/remotes/origin").stdout.split() if not r.endswith("/HEAD")]
        git(other, "checkout", "-q", base[0])
    for b in branches:
        (other / "theirs.txt").write_text(b + "\n", encoding="utf-8")
        git(other, "add", "-A")
        git(other, "commit", "-qm", "theirs " + b)
        git(other, "push", "-q", "origin", "HEAD:refs/heads/%s" % b)


def _decision(command, cwd):
    p = run_hook(command, cwd)
    return p["hookSpecificOutput"].get("permissionDecision") if p else None


def test_plain_push_to_remote_default_branch_passes(repo, tmp_path):
    """fast-forward push 는 원격 히스토리를 지우지 않는다(되돌리려면 revert).
    실사용 로그에서 이 확인은 23건 모두 평범한 작업 흐름을 멈춰 세우기만 했다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    assert _decision("git push origin main", repo) is None
    assert _decision("git push -u origin main", repo) is None
    assert _decision("git push", repo) is None


FORCE_TO_DEFAULT = [
    "git push --force origin main",
    "git push -f origin main",
    "git push -uf origin main",
    "git push --force-with-lease origin main",
    "git push --force-with-lease=main:abc123 origin main",
    "git push origin +main",
    "git push origin +HEAD:refs/heads/main",
    "git push -f",
    "git push --force --all origin",
    # 리뷰에서 나온 누락: HEAD/@ 는 현재 브랜치, 값을 받는 git 전역 옵션, 글로브 refspec
    "git push -f origin HEAD",
    "git push origin +HEAD",
    "git push -f origin @",
    "git push --force-with-lease origin HEAD",
    "git -C . push -f origin main",
    "git -c core.x=y push -f origin main",
    "git push -f origin 'refs/heads/*:refs/heads/*'",
    "git push -f origin :",                 # 일치하는 브랜치 전부
    # 리뷰에서 나온 누락: 삭제와 섞인 force, 한 명령 속 여러 push
    "git push -f origin main :tmp",
    "git push origin +main :tmp",
    "git push origin HEAD:refs/heads/x && git push -f origin main",
    "git push origin x; git push -f origin main",
    "git push -f origin HEAD:heads/main",   # git 은 `refs/<이름>` 도 대상으로 푼다
]


@pytest.mark.parametrize("cmd", FORCE_TO_DEFAULT)
def test_force_push_to_remote_default_branch_asks_when_remote_commits_are_not_local(
        repo, tmp_path, cmd):
    """덮어쓸 원격 커밋이 로컬에 없으면 어디에도 보존되지 않는다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    assert _decision(cmd, repo) == "ask", cmd


@pytest.mark.parametrize("cmd", FORCE_TO_DEFAULT)
def test_force_push_to_remote_default_branch_passes_when_remote_commits_are_local(
        repo, tmp_path, cmd):
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    git(repo, "fetch", "-q", "origin")
    assert _decision(cmd, repo) is None, cmd


def test_force_push_pins_overwritten_remote_commit_and_restores_it(repo, tmp_path):
    """실측: force push 로 덮어쓴 원격 main 을 고정 ref 로 되돌릴 수 있어야 한다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    git(repo, "fetch", "-q", "origin")
    theirs = git(bare, "rev-parse", "main").stdout.strip()
    (repo / "mine.txt").write_text("mine\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "mine")

    p = run_hook("git push -f origin main", repo)
    assert p and "permissionDecision" not in p["hookSpecificOutput"]
    pins = git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
               BACKUP_PREFIX).stdout.split("\n")
    pin = next(line.split()[0] for line in pins if line.endswith(theirs))
    assert "-push/" in pin and pin.endswith("/heads/main")
    assert pin[:-len("heads/main")] in p["hookSpecificOutput"]["additionalContext"]

    git(repo, "push", "-q", "-f", "origin", "main")
    assert git(bare, "rev-parse", "main").stdout.strip() != theirs
    git(repo, "push", "-q", "--force", "origin", "%s:refs/heads/main" % pin)
    assert git(bare, "rev-parse", "main").stdout.strip() == theirs


def test_push_to_side_branch_passes(repo, tmp_path):
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push origin feature/x", repo) is None


def test_push_force_to_side_branch_asks_only_when_remote_commits_are_not_local(repo, tmp_path):
    """가역성은 브랜치 이름과 무관하다 — 곁다리 브랜치도 남의 커밋을 덮어쓰면 묻는다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "fix/y")
    assert _decision("git push --force origin fix/y", repo) == "ask"
    assert _decision("git push origin +fix/y", repo) == "ask"
    git(repo, "fetch", "-q", "origin")
    assert _decision("git push --force origin fix/y", repo) is None


def test_push_all_without_force_passes(repo, tmp_path):
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push --all origin", repo) is None


@pytest.mark.parametrize("cmd", [
    "git push --mirror origin",
    # --prune 은 로컬에 없는 원격 브랜치를 지운다 — 원격 브랜치 삭제와 같다.
    "git push --prune origin 'refs/heads/*:refs/heads/*'",
])
def test_push_mirror_and_prune_ask_only_when_remote_commits_are_not_local(repo, tmp_path, cmd):
    """--mirror/--prune 은 원격에만 있는 ref 를 지운다 — 어느 브랜치든 대상이다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "feature/x")
    assert _decision(cmd, repo) == "ask"
    git(repo, "fetch", "-q", "origin")
    assert _decision(cmd, repo) is None


def test_force_push_with_quoted_dash_c_path_asks(repo, tmp_path):
    """`git -C "경로 공백"` 처럼 값이 따옴표로 묶여도 push 를 찾고, 판정은 -C 저장소에서 한다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    (tmp_path / "my repo").symlink_to(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert _decision('git -C "%s" push -f origin main' % (tmp_path / "my repo"), elsewhere) == "ask"
    assert _decision('git -c a=b -C "%s" push -f origin main' % (tmp_path / "my repo"), elsewhere) == "ask"
    assert _decision('git -C "%s" push origin main' % (tmp_path / "my repo"), elsewhere) is None
    # 선행 `cd` 도 따른다 (LEADING_CD_RE 는 공백 든 경로를 못 읽어 공백 없는 경로로 본다)
    assert _decision('cd %s && git push -f origin main' % repo, elsewhere) == "ask"


def test_force_push_not_touching_default_branch_passes(repo, tmp_path):
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    assert _decision("git push --tags -f origin", repo) is None
    assert _decision("git push -f origin refs/heads/release/main", repo) is None


def test_force_push_checks_the_push_url_not_the_fetch_url(repo, tmp_path):
    """fetch 는 미러에서, push 는 원본으로 하면 원본의 커밋을 봐야 한다."""
    bare = _with_origin(repo, tmp_path, "main")
    mirror = tmp_path / "mirror.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(bare), str(mirror)], check=True)
    git(repo, "remote", "set-url", "origin", str(mirror))
    git(repo, "remote", "set-url", "--push", "origin", str(bare))
    _remote_ahead(bare, tmp_path, "main")
    assert _decision("git push -f origin main", repo) == "ask"
    # pushurl 이 여럿이면 git 은 전부에 쓴다 — 첫 번째(미러, 로컬과 같음)만 보면 안 된다.
    git(repo, "config", "--unset-all", "remote.origin.pushurl")
    git(repo, "config", "--add", "remote.origin.pushurl", str(mirror))
    git(repo, "config", "--add", "remote.origin.pushurl", str(bare))
    assert _decision("git push -f origin main", repo) == "ask"


@pytest.mark.parametrize("cmd", ["git push --force --repo up", "git push --force --repo=up"])
def test_force_push_with_repo_option_checks_that_remote(repo, tmp_path, cmd):
    """`--repo <원격>` 은 원격 위치 인자와 같다 — 기본 원격(origin)을 보면 안 된다."""
    _with_origin(repo, tmp_path, "main")
    up = tmp_path / "up.git"
    subprocess.run(["git", "init", "-q", "--bare", str(up)], check=True)
    git(repo, "remote", "add", "up", str(up))
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    git(repo, "push", "-q", "up", "HEAD:refs/heads/%s" % branch)
    _remote_ahead(up, tmp_path, branch)
    assert _decision(cmd, repo) == "ask", cmd


def test_deleting_remote_ref_outside_heads_and_tags_asks(repo, tmp_path):
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    other = tmp_path / "other"
    git(other, "notes", "add", "-m", "theirs", "HEAD")
    git(other, "push", "-q", "origin", "refs/notes/commits")
    assert _decision("git push origin :refs/notes/commits", repo) == "ask"


def test_mirror_pins_do_not_collide_on_slash_and_dash_names(repo, tmp_path):
    """feat/x 와 feat-x 의 고정 ref 가 같은 이름이 되면 하나를 잃는다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "feat/x", "feat-x")
    git(repo, "fetch", "-q", "origin")
    assert _decision("git push --mirror origin", repo) is None
    pinned = set(git(repo, "for-each-ref", "--format=%(objectname)", BACKUP_PREFIX).stdout.split())
    for b in ("feat/x", "feat-x"):
        assert git(bare, "rev-parse", b).stdout.strip() in pinned, b


def test_pins_from_two_pushes_in_one_command_do_not_overwrite_each_other(repo, tmp_path):
    """같은 초에 두 원격의 main 을 고정해도 둘 다 남아야 한다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "main")
    b2 = tmp_path / "b2.git"
    subprocess.run(["git", "init", "-q", "--bare", str(b2)], check=True)
    git(repo, "remote", "add", "b2", str(b2))
    git(repo, "push", "-q", "b2", "HEAD:refs/heads/main")
    git(repo, "fetch", "-q", "--all")
    (repo / "mine.txt").write_text("mine\n", encoding="utf-8")   # 두 원격의 main 이 모두 로컬 main 과 달라진다
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "mine")
    assert _decision("git push -f origin HEAD:main && git push -f b2 HEAD:main", repo) is None
    pinned = set(git(repo, "for-each-ref", "--format=%(objectname)", BACKUP_PREFIX).stdout.split())
    for remote in (bare, b2):
        assert git(remote, "rev-parse", "main").stdout.strip() in pinned, remote


def test_push_outside_git_repo_passes(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert _decision("git push origin main", d) is None


def test_stash_push_is_not_treated_as_push(repo, tmp_path):
    _with_origin(repo, tmp_path, "main")
    assert _decision("git stash push -m wip", repo) is None


@pytest.mark.parametrize("cmd", [
    "git push --delete origin feature/x",
    "git push origin :feature/x",           # 빈 src refspec 도 같은 삭제다
])
def test_push_delete_remote_branch_asks_only_when_its_commits_are_not_local(repo, tmp_path, cmd):
    """원격 브랜치 삭제는 곁다리 브랜치여도 본다 — 그 커밋이 로컬에 없으면 영영 사라진다."""
    bare = _with_origin(repo, tmp_path, "main")
    _remote_ahead(bare, tmp_path, "feature/x")
    assert _decision(cmd, repo) == "ask"
    git(repo, "fetch", "-q", "origin")
    assert _decision(cmd, repo) is None


def test_destructive_push_asks_when_remote_is_unreachable(repo, tmp_path):
    """원격을 조회하지 못하면 가역성을 보장할 수 없다."""
    git(repo, "remote", "add", "origin", str(tmp_path / "missing.git"))
    assert _decision("git push -f origin master", repo) == "ask"
    assert _decision("git push --delete origin feature/x", repo) == "ask"


def test_clean_x_skips_ignored_when_too_large(repo, monkeypatch):
    """.gitignore 대상이 상한을 넘으면 담지 않는다 — 담으면 훅이 수십 초를 잡아먹는다.

    상한을 넘겨도 추적/미추적 스냅샷은 그대로 남아야 한다.
    """
    import sys
    sys.path.insert(0, str(HOOK.parent))
    import danger_guard

    (repo / ".gitignore").write_text("junk/\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("WIP\n", encoding="utf-8")
    junk = repo / "junk"
    junk.mkdir()
    for i in range(5):
        (junk / ("f%d.bin" % i)).write_text("x" * 100, encoding="utf-8")

    monkeypatch.setattr(danger_guard, "MAX_IGNORED_FILES", 1)
    notes = danger_guard.git_snapshot("git clean -fdx", str(repo))

    assert any("left out of the snapshot" in n for n in notes), notes
    ref = latest_backup(repo)
    assert ref, "the snapshot itself must remain even when ignored files are given up"
    listing = git(repo, "ls-tree", "-r", "--name-only", ref).stdout
    assert "tracked.txt" in listing
    assert "junk/" not in listing


def test_clean_x_includes_ignored_when_small(repo):
    """상한 안이면 종전대로 .gitignore 대상까지 담는다."""
    (repo / "local.env").write_text("SECRET=1\n", encoding="utf-8")
    run_hook("git clean -fdx", repo)
    ref = latest_backup(repo)
    assert "local.env" in git(repo, "ls-tree", "-r", "--name-only", ref).stdout


def test_push_check_error_asks_instead_of_passing(repo, monkeypatch, capsys):
    """가역성을 확인하지 못한 push 를 그냥 내보내지 않는다 — 훅의 다른 오류는 통과(fail-open)다."""
    import io
    monkeypatch.syspath_prepend(str(HOOK.parent))
    import danger_guard

    def boom(command, cwd):
        raise RuntimeError("boom")
    monkeypatch.setattr(danger_guard, "push_check", boom)
    monkeypatch.setattr(danger_guard, "log", lambda entry: None)
    for cmd, expected in (("git push -f origin main", "ask"), ("ls", None)):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
            {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}})))
        with pytest.raises(SystemExit):
            danger_guard.main()
        out = capsys.readouterr().out.strip()
        got = json.loads(out)["hookSpecificOutput"].get("permissionDecision") if out else None
        assert got == expected, cmd
