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


def hook_result(command: str) -> tuple:
    """(decision, substituted_command) 를 반환. 통과면 (None, None)."""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    out = (proc.stdout or "").strip()
    if not out:
        return None, None
    hso = json.loads(out)["hookSpecificOutput"]
    return hso["permissionDecision"], hso.get("updatedInput", {}).get("command")


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
    assert new_cmd == "git stash push -- tracked.txt && git checkout -- tracked.txt"
    run_in(repo, new_cmd)
    # checkout 목적(작업트리 HEAD 로 복원)은 달성되고,
    assert run_in(repo, "git diff --quiet").returncode == 0
    # 잃을 뻔한 변경은 stash 에 보존되어 pop 으로 복구된다 → 데이터 손실 0.
    assert run_in(repo, "git stash list").stdout.strip() != ""
    run_in(repo, "git stash pop -q")
    assert "PRECIOUS" in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_checkout_dot_substitution_preserves(repo):
    (repo / "tracked.txt").write_text("line1\nDOTCHANGE\n", encoding="utf-8")
    decision, new_cmd = hook_result("git checkout .")
    assert decision == "allow"
    assert new_cmd == "git stash push -- . && git checkout ."
    run_in(repo, new_cmd)
    assert run_in(repo, "git diff --quiet").returncode == 0
    run_in(repo, "git stash pop -q")
    assert "DOTCHANGE" in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_restore_staged_passes_and_only_unstages(repo):
    (repo / "tracked.txt").write_text("line1\nstaged\n", encoding="utf-8")
    run_in(repo, "git add tracked.txt")
    decision, _ = hook_result("git restore --staged tracked.txt")
    assert decision is None, "restore --staged 는 인덱스만 → 통과여야 한다"
    run_in(repo, "git restore --staged tracked.txt")
    assert run_in(repo, "git diff --cached --quiet").returncode == 0   # 언스테이지됨
    assert "staged" in (repo / "tracked.txt").read_text(encoding="utf-8")  # 워킹 변경 보존


def test_reset_hard_denied_and_would_destroy(repo):
    (repo / "tracked.txt").write_text("line1\nuncommitted\n", encoding="utf-8")
    decision, _ = hook_result("git reset --hard HEAD")
    assert decision == "deny"
    # 훅을 우회해 실제로 실행하면 변경이 파괴됨을 확인 → deny 정당성 입증.
    run_in(repo, "git reset --hard HEAD -q")
    assert "uncommitted" not in (repo / "tracked.txt").read_text(encoding="utf-8")


def test_clean_force_denied_dryrun_passes(repo):
    (repo / "junk.txt").write_text("x", encoding="utf-8")   # untracked
    assert hook_result("git clean -fd")[0] == "deny"
    assert hook_result("git clean -n")[0] is None
    run_in(repo, "git clean -n")                             # dry-run: 삭제 안 함
    assert (repo / "junk.txt").exists()


def test_checkout_force_to_branch_named_clean_asks_not_deny(repo):
    # 회귀: 'clean' 이라는 이름의 브랜치로 강제 전환을 clean 삭제로 오인하면 안 된다.
    run_in(repo, "git branch clean")
    decision, _ = hook_result("git checkout -f clean")
    assert decision == "ask"
    run_in(repo, "git checkout -f clean")
    assert run_in(repo, "git rev-parse --abbrev-ref HEAD").stdout.strip() == "clean"


def test_reset_soft_passes_and_preserves(repo):
    (repo / "tracked.txt").write_text("line1\nc2\n", encoding="utf-8")
    run_in(repo, "git commit -qam c2")
    assert hook_result("git reset --soft HEAD~1")[0] is None
    run_in(repo, "git reset --soft HEAD~1")
    assert "c2" in (repo / "tracked.txt").read_text(encoding="utf-8")   # 워킹트리 보존
