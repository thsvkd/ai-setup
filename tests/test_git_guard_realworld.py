"""danger_guard.posix.py 의 git 정책 '실측' 테스트.

기존 test_danger_guard_posix.py 는 훅의 '판정(allow/ask/deny)'만 블랙박스로 검증한다.
이 파일은 한 걸음 더 나아가, 실제 git 저장소를 만들어 다음을 실측한다:
  - 안전 판정된 명령(git stash push 등)이 실제로 정상 동작하는지,
  - 자동치환(stash-prepend)이 '진짜로' 작업을 보존하고 복구 가능한지
    (대조군: 순수 git checkout -- 은 변경을 영구 삭제한다),
  - restore --staged 가 인덱스만 건드리고 워킹트리 변경은 보존하는지.

git 이 없거나 Windows 면 skip 한다 (posix 훅 대상).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "res" / "hooks" / "danger_guard.posix.py"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None,
    reason="실제 git 을 쓰는 posix 실측 (git 필요)",
)


def hook_result(command: str, cwd: str = "") -> tuple:
    """(decision, substituted_command) 를 반환. 통과면 (None, None). cwd 를 주면 push 의
    브랜치 판정(현재 브랜치 조회)이 그 저장소를 기준으로 동작한다."""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True, text=True, encoding="utf-8",
    )
    out = (proc.stdout or "").strip()
    if not out:
        return None, None
    hso = json.loads(out)["hookSpecificOutput"]
    return hso["permissionDecision"], hso.get("updatedInput", {}).get("command")


def backup_refs(repo):
    """(refname, hash) 쌍 목록. _backup_head_and_worktree 는 .../head(HEAD 커밋)와
    .../worktree(스태시 커밋) 둘 다 만들 수 있어, 복구 테스트는 이름으로 정확히 골라야 한다
    (아무거나 하나 집으면 head 커밋을 stash apply 하려다 'not a stash-like commit' 로 실패한다)."""
    r = run_in(repo, "git for-each-ref refs/claude-backups/ --format='%(refname) %(objectname)'")
    pairs = []
    for line in r.stdout.splitlines():
        if line.strip():
            ref, _, h = line.strip().partition(" ")
            pairs.append((ref, h))
    return pairs


def worktree_backup_hash(pairs):
    for ref, h in pairs:
        if ref.endswith("/worktree") or ref.endswith("/snapshot"):
            return h
    return None


@pytest.fixture
def repo(tmp_path):
    """tracked.txt 를 1개 커밋한 실제 git 저장소."""
    r = tmp_path / "repo"
    r.mkdir()
    def git(*a):
        return subprocess.run(["git", *a], cwd=r, capture_output=True, text=True, check=True)
    git("init", "-q")
    git("config", "user.email", "t@t.co")
    git("config", "user.name", "t")
    git("config", "commit.gpgsign", "false")
    (r / "tracked.txt").write_text("line1\n", encoding="utf-8")
    git("add", "tracked.txt")
    git("commit", "-qm", "init")
    return r


def run_in(repo, command):
    """훅이 내놓은(또는 원본) 명령을 실제 저장소에서 실행한다."""
    return subprocess.run(command, cwd=repo, shell=True, capture_output=True, text=True)


def test_stash_push_passes_and_actually_works(repo):
    (repo / "tracked.txt").write_text("line1\nWIP\n", encoding="utf-8")
    decision, _ = hook_result("git stash push -m wip")
    assert decision is None, "git stash push 는 안전 → 통과여야 한다"
    run_in(repo, "git stash push -m wip -q")
    # 작업트리가 깨끗해지고(스태시됨) 스태시 목록에 남아야 한다.
    assert run_in(repo, "git diff --quiet").returncode == 0
    assert "wip" in run_in(repo, "git stash list").stdout
    run_in(repo, "git stash pop -q")
    assert "WIP" in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_plain_checkout_destroys_work_but_substitution_preserves(repo):
    # 대조군: 순수 git checkout -- 은 커밋 안 된 변경을 영구 삭제한다.
    (repo / "tracked.txt").write_text("line1\nPRECIOUS\n", encoding="utf-8")
    run_in(repo, "git checkout -- tracked.txt")
    assert "PRECIOUS" not in (repo / "tracked.txt").read_text(encoding="utf-8"), \
        "대조군: 순수 checkout 은 변경을 잃어야 한다(이 사실이 자동치환의 존재 이유)"

    # 훅 치환본: 같은 변경을 다시 만들고, 훅이 내놓은 명령을 실행하면 보존돼야 한다.
    (repo / "tracked.txt").write_text("line1\nPRECIOUS\n", encoding="utf-8")
    decision, new_cmd = hook_result("git checkout -- tracked.txt")
    assert decision == "allow"
    assert "refs/claude-backups/" in new_cmd
    assert new_cmd.endswith(" && git checkout -- tracked.txt")
    before = set(backup_refs(repo))
    run_in(repo, new_cmd)
    # checkout 목적(작업트리 HEAD 로 복원)은 달성되고,
    assert run_in(repo, "git diff --quiet").returncode == 0
    # 잃을 뻔한 변경은 refs/claude-backups/ 에 stash 커밋으로 보존된다 → 데이터 손실 0.
    after = set(backup_refs(repo)) - before
    h = worktree_backup_hash(after)
    assert h, "새 worktree 백업 ref 가 생겨야 한다"
    restore = run_in(repo, f"git stash apply {h}")
    assert restore.returncode == 0, restore.stderr
    assert "PRECIOUS" in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_checkout_dot_substitution_preserves(repo):
    (repo / "tracked.txt").write_text("line1\nDOTCHANGE\n", encoding="utf-8")
    decision, new_cmd = hook_result("git checkout .")
    assert decision == "allow"
    assert "refs/claude-backups/" in new_cmd
    assert new_cmd.endswith(" && git checkout .")
    before = set(backup_refs(repo))
    run_in(repo, new_cmd)
    assert run_in(repo, "git diff --quiet").returncode == 0
    after = set(backup_refs(repo)) - before
    h = worktree_backup_hash(after)
    assert h
    run_in(repo, f"git stash apply {h}")
    assert "DOTCHANGE" in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_restore_staged_passes_and_only_unstages(repo):
    (repo / "tracked.txt").write_text("line1\nstaged\n", encoding="utf-8")
    run_in(repo, "git add tracked.txt")
    decision, _ = hook_result("git restore --staged tracked.txt")
    assert decision is None, "restore --staged 는 인덱스만 → 통과여야 한다"
    run_in(repo, "git restore --staged tracked.txt")
    assert run_in(repo, "git diff --cached --quiet").returncode == 0   # 언스테이지됨
    assert "staged" in (repo / "tracked.txt").read_text(encoding="utf-8")  # 워킹 변경 보존


def test_reset_hard_backs_up_then_actually_destroys_and_is_recoverable(repo):
    # 정책 변경: deny 가 아니라 refs/claude-backups/ 에 백업한 뒤 원본을 그대로 실행한다.
    (repo / "tracked.txt").write_text("line1\nuncommitted\n", encoding="utf-8")
    decision, new_cmd = hook_result("git reset --hard HEAD")
    assert decision == "allow"
    assert "refs/claude-backups/" in new_cmd
    assert new_cmd.endswith(" && git reset --hard HEAD")

    before = set(backup_refs(repo))
    run_in(repo, new_cmd)
    # reset --hard 자체는 실제로 파괴적이어야 한다(백업이 그 사실 자체를 바꾸진 않음).
    assert "uncommitted" not in (repo / "tracked.txt").read_text(encoding="utf-8")
    # 하지만 이제는 백업 ref 로 복구가 가능해야 한다 (head 는 순수 커밋, worktree 가 stash 커밋).
    after = set(backup_refs(repo)) - before
    h = worktree_backup_hash(after)
    assert h, "새 worktree 백업 ref 가 생겨야 한다"
    restore = run_in(repo, f"git stash apply {h}")
    assert restore.returncode == 0, restore.stderr
    assert "uncommitted" in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_clean_force_backs_up_then_allows_dryrun_still_passes(repo):
    (repo / "junk.txt").write_text("x", encoding="utf-8")   # untracked
    decision, new_cmd = hook_result("git clean -fd")
    assert decision == "allow"
    assert "refs/claude-backups/" in new_cmd
    assert new_cmd.endswith(" && git clean -fd")

    before = set(backup_refs(repo))
    run_in(repo, new_cmd)
    assert not (repo / "junk.txt").exists(), "clean 자체는 실제로 파일을 지워야 한다"
    after = set(backup_refs(repo)) - before
    h = worktree_backup_hash(after)
    assert h, "untracked 파일까지 포함한 스냅샷 백업 ref 가 생겨야 한다"
    assert "junk.txt" in run_in(repo, f"git ls-tree -r {h} --name-only").stdout

    assert hook_result("git clean -n")[0] is None
    run_in(repo, "git clean -n")                             # dry-run: 삭제 안 함


def test_checkout_force_to_branch_named_clean_backs_up_not_deny(repo):
    # 회귀: 'clean' 이라는 이름의 브랜치로 강제 전환을 clean 삭제로 오인하면 안 된다.
    run_in(repo, "git branch clean")
    decision, new_cmd = hook_result("git checkout -f clean")
    assert decision == "allow"
    assert "refs/claude-backups/" in new_cmd
    run_in(repo, new_cmd)
    assert run_in(repo, "git rev-parse --abbrev-ref HEAD").stdout.strip() == "clean"


def test_reset_soft_passes_and_preserves(repo):
    (repo / "tracked.txt").write_text("line1\nc2\n", encoding="utf-8")
    run_in(repo, "git commit -qam c2")
    assert hook_result("git reset --soft HEAD~1")[0] is None
    run_in(repo, "git reset --soft HEAD~1")
    assert "c2" in (repo / "tracked.txt").read_text(encoding="utf-8")   # 워킹트리 보존


def test_backup_failure_blocks_destructive_original(repo):
    """리뷰 지적 #1 회귀: 백업이 실패하면 원본 파괴적 명령이 '절대' 실행되면 안 된다.

    예전 스니펫은 stash create 앞이 `;` 라 앞 단계 실패의 종료 상태가 덮여 전체가 성공으로
    보고됐고, 뒤에 `&&` 로 붙은 reset --hard 가 백업 없이 실행됐다. 여기서는 refs/claude-backups
    '자체'를 ref 로 만들어 하위 ref 생성이 D/F 충돌로 실패하게 만들어(=백업 실패) 재현한다.
    """
    run_in(repo, "git update-ref refs/claude-backups HEAD")   # 하위 ref 생성 불가 상태로 만든다
    (repo / "tracked.txt").write_text("line1\nPRECIOUS\n", encoding="utf-8")

    decision, new_cmd = hook_result("git reset --hard HEAD")
    assert decision == "allow"
    result = run_in(repo, new_cmd)

    assert result.returncode != 0, "백업 실패 시 명령 전체가 실패해야 한다"
    assert "백업에 실패" in result.stderr, result.stderr
    assert "PRECIOUS" in (repo / "tracked.txt").read_text(encoding="utf-8"), \
        "백업이 실패했는데 reset --hard 가 실행되어 작업이 사라졌다 (fail-open 회귀)"


def test_clean_x_backs_up_gitignored_files(repo):
    """리뷰 지적 #3 회귀: `git clean -fdx` 는 .gitignore 대상까지 지운다. 기본 `git add -A`
    스냅샷은 그것들을 담지 못해 .env/node_modules 가 백업 없이 영구 소실됐다."""
    (repo / ".gitignore").write_text(".env\nbuild/\n", encoding="utf-8")
    run_in(repo, "git add .gitignore && git commit -qm ignore")
    (repo / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "out.js").write_text("compiled\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("junk\n", encoding="utf-8")

    decision, new_cmd = hook_result("git clean -fdx")
    assert decision == "allow"
    before = set(backup_refs(repo))
    run_in(repo, new_cmd)

    # clean 자체는 실제로 지운다 (백업이 그 사실을 바꾸진 않는다).
    assert not (repo / ".env").exists()
    assert not (repo / "build").exists()

    snapshot = worktree_backup_hash(set(backup_refs(repo)) - before)
    assert snapshot, "스냅샷 백업 ref 가 생겨야 한다"
    files = run_in(repo, f"git ls-tree -r {snapshot} --name-only").stdout.split()
    assert ".env" in files, "무시된 파일도 백업에 담겨야 한다"
    assert "build/out.js" in files
    assert "untracked.txt" in files
    # 실제로 내용까지 복구 가능해야 한다.
    assert "SECRET=1" in run_in(repo, f"git cat-file -p {snapshot}:.env").stdout


def test_clean_without_x_keeps_default_snapshot(repo):
    """반대 방향 회귀: -x 가 없으면 무시된 파일은 clean 도 안 지우므로, 굳이 담아
    node_modules 전체를 커밋하는 느린 경로로 가면 안 된다."""
    decision, new_cmd = hook_result("git clean -fd")
    assert decision == "allow"
    assert "git add -A -- ." in new_cmd and "git add -Af" not in new_cmd
