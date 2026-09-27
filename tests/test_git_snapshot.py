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
    return subprocess.run(["git"] + list(args), cwd=str(repo),
                          capture_output=True, text=True)


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
    assert ref, "백업 ref 가 생성돼야 한다"

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
    assert ref, "본 저장소에 워크트리 스냅샷이 남아야 한다"
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


def _with_origin(repo, tmp_path, default_branch):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/%s" % default_branch)
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD",
        "refs/remotes/origin/%s" % default_branch)
    return bare


def _decision(command, cwd):
    p = run_hook(command, cwd)
    return p["hookSpecificOutput"].get("permissionDecision") if p else None


def test_plain_push_to_remote_default_branch_passes(repo, tmp_path):
    """fast-forward push 는 원격 히스토리를 지우지 않는다(되돌리려면 revert).
    실사용 로그에서 이 확인은 23건 모두 평범한 작업 흐름을 멈춰 세우기만 했다."""
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push origin main", repo) is None
    assert _decision("git push -u origin main", repo) is None
    assert _decision("git push", repo) is None


@pytest.mark.parametrize("cmd", [
    "git push --force origin main",
    "git push -f origin main",
    "git push -uf origin main",
    "git push --force-with-lease origin main",
    "git push --force-with-lease=main:abc123 origin main",
    "git push origin +main",
    "git push origin +HEAD:refs/heads/main",
    "git push -f",
    "git push --force --all origin",
])
def test_force_push_to_remote_default_branch_asks(repo, tmp_path, cmd):
    """덮어쓴 원격 커밋은 로컬 백업이 닿지 않는다."""
    _with_origin(repo, tmp_path, "main")
    assert _decision(cmd, repo) == "ask", cmd


def test_push_to_side_branch_passes(repo, tmp_path):
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push origin feature/x", repo) is None


def test_push_force_to_side_branch_passes(repo, tmp_path):
    """곁다리 브랜치는 force 여도 확인하지 않는다."""
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push --force origin fix/y", repo) is None
    assert _decision("git push origin +fix/y", repo) is None


def test_push_all_without_force_passes(repo, tmp_path):
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push --all origin", repo) is None


def test_push_mirror_asks(repo, tmp_path):
    """--mirror 는 원격에만 있는 ref 를 지우고 나머지를 강제로 맞춘다."""
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push --mirror origin", repo) == "ask"


def test_push_respects_remote_default_branch_name(repo, tmp_path):
    """기본 브랜치가 main 이 아니어도 원격이 지정한 이름을 따른다."""
    _with_origin(repo, tmp_path, "trunk")
    assert _decision("git push --force origin trunk", repo) == "ask"
    assert _decision("git push --force origin main", repo) is None


def test_push_outside_git_repo_passes(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert _decision("git push origin main", d) is None


def test_stash_push_is_not_treated_as_push(repo, tmp_path):
    _with_origin(repo, tmp_path, "main")
    assert _decision("git stash push -m wip", repo) is None


def test_push_delete_remote_branch_asks(repo, tmp_path):
    """원격 브랜치 삭제는 로컬 백업이 닿지 않는다 — 곁다리 브랜치여도 확인한다."""
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push --delete origin feature/x", repo) == "ask"


def test_push_empty_src_refspec_asks(repo, tmp_path):
    """`git push origin :branch` 도 같은 삭제다."""
    _with_origin(repo, tmp_path, "main")
    assert _decision("git push origin :feature/x", repo) == "ask"


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

    assert any("제외했습니다" in n for n in notes), notes
    ref = latest_backup(repo)
    assert ref, "무시된 파일을 포기해도 스냅샷 자체는 남아야 한다"
    listing = git(repo, "ls-tree", "-r", "--name-only", ref).stdout
    assert "tracked.txt" in listing
    assert "junk/" not in listing


def test_clean_x_includes_ignored_when_small(repo):
    """상한 안이면 종전대로 .gitignore 대상까지 담는다."""
    (repo / "local.env").write_text("SECRET=1\n", encoding="utf-8")
    run_hook("git clean -fdx", repo)
    ref = latest_backup(repo)
    assert "local.env" in git(repo, "ls-tree", "-r", "--name-only", ref).stdout
