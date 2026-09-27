"""res/hooks/shims/rm 이 원본 rm 과 '관측 가능한 결과'가 같은지 대조한다.

이 셰임의 존재 이유는 훅이 명령 문자열을 재작성하지 않게 하는 것이다. 그래서 검증도
"치환된 문자열이 어떻게 생겼나"가 아니라 "같은 명령을 원본 rm 으로 돌렸을 때와 결과가
같은가"로 한다. 각 케이스를 동일한 픽스처 두 벌에서 실행하고 (a) 살아남은 파일 목록과
(b) 종료 코드를 비교한다.

픽스처는 /tmp 밖에 만든다. 셰임은 /tmp 아래를 의도적으로 '실제 삭제'로 넘기므로(tmpfs 는
휴지통도 같은 램이라 옮겨봐야 회수되지 않는다) 거기서 재면 셰임 경로를 전혀 검증하지 못한다.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHIM_DIR = REPO / "res" / "hooks" / "shims"
BASE = REPO / ".tmp-rmshim"


@pytest.fixture(scope="module", autouse=True)
def base_dir():
    shutil.rmtree(str(BASE), ignore_errors=True)
    BASE.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(str(BASE), ignore_errors=True)


def make_fixture(d):
    shutil.rmtree(str(d), ignore_errors=True)
    (d / "sub" / "deep").mkdir(parents=True)
    for name in ("a.txt", "b.txt", "c.log", "name with spaces.txt", "-weird"):
        (d / name).write_text("x", encoding="utf-8")
    (d / "sub" / "deep" / "x.log").write_text("x", encoding="utf-8")
    (d / "emptydir").mkdir()
    os.symlink("a.txt", str(d / "link"))


def observe(script, use_shim):
    """스크립트를 돌리고 (종료 코드, 남은 파일 목록)을 돌려준다."""
    d = BASE / ("shim" if use_shim else "real")
    make_fixture(d)
    env = dict(os.environ)
    env.pop("CLAUDE_NO_TRASH", None)
    env["D"] = str(d)
    if use_shim:
        env["PATH"] = str(SHIM_DIR) + os.pathsep + env["PATH"]
    proc = subprocess.run(["bash", "-c", script], cwd=str(d), env=env,
                          capture_output=True, text=True)
    survivors = sorted(
        str(p.relative_to(d)) for p in d.rglob("*")
    )
    return proc.returncode, survivors


CASES = [
    ("일반 파일", "rm a.txt"),
    ("디렉터리 -r", "rm -r sub"),
    ("디렉터리 -rf", "rm -rf sub"),
    ("빈 디렉터리 -d", "rm -d emptydir"),
    ("-f 없는 파일", "rm -f nope.txt"),
    ("없는 파일(플래그 없음)", "rm nope.txt"),
    ("변수 확장", 'V="$D/sub"; rm -rf "$V"'),
    ("변수+슬래시", 'V="$D"; rm -rf "$V/sub"'),
    ("변수+글로브", 'V="$D"; rm -f "$V"/*.txt'),
    ("글로브 미일치 -f", "rm -f ./*.nomatch"),
    ("글로브 미일치(플래그 없음)", "rm ./*.nomatch"),
    ("글로브 일치", "rm ./*.txt"),
    ("-- 뒤 대시 파일", "rm -- -weird"),
    ("공백 포함 이름", 'rm "name with spaces.txt"'),
    ("줄바꿈 포함 이름", 'touch "$D/nl\nname"; rm "$D/nl\nname"'),
    ("심볼릭 링크", "rm link"),
    ("여러 대상", "rm a.txt b.txt c.log"),
    ("일부만 존재 -f", "rm -f a.txt nope.txt b.txt"),
    ("일부만 존재(플래그 없음)", "rm a.txt nope.txt b.txt"),
    ("find -exec +", 'find . -name "*.log" -exec rm -f {} +'),
    ("find -exec ;", 'find . -name "*.log" -exec rm -f {} \\;'),
    ("xargs -0", 'find . -name "*.log" -print0 | xargs -0 rm -f'),
    ("체이닝", "cd sub && rm -f deep/x.log; echo done"),
    ("멀티라인", "cd sub\nrm -rf deep\necho done"),
    ("히어독 안의 rm(데이터)", "cat > note.md <<'EOT'\nrm -rf /\nEOT\nwc -l < note.md"),
    ("스크립트 내부 rm", "printf '#!/bin/sh\\nrm -f \"$1\"\\n' > s.sh; chmod +x s.sh; ./s.sh a.txt"),
    ("sh -c 내부", 'sh -c "rm -f a.txt"'),
    ("래퍼 timeout", "timeout 5 rm -f a.txt"),
    ("인자 없음", "rm"),
    ("점 대상", "rm -rf ."),
    ("상위 점 대상", "rm -rf sub/.."),
    ("CLAUDE_NO_TRASH 탈출구", "CLAUDE_NO_TRASH=1 rm -rf sub"),
]


@pytest.mark.parametrize("name,script", CASES, ids=[c[0] for c in CASES])
def test_matches_real_rm(name, script):
    real = observe(script, use_shim=False)
    shim = observe(script, use_shim=True)
    assert real == shim, "원본 rm 과 결과가 다르다: %s" % name


REFUSED = ["rm -rf ~", 'rm -rf "$HOME"', "rm -rf /"]


@pytest.mark.parametrize("script", REFUSED)
def test_root_and_home_are_refused(script):
    env = dict(os.environ)
    env["PATH"] = str(SHIM_DIR) + os.pathsep + env["PATH"]
    proc = subprocess.run(["bash", "-c", script], cwd=str(BASE), env=env,
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert "거부" in proc.stderr
    assert Path(os.path.expanduser("~")).is_dir()


def test_tmp_targets_are_really_deleted(tmp_path):
    """/tmp 는 tmpfs 라 휴지통 자리도 같은 램이다 — 옮기면 램이 회수되지 않는다."""
    target = tmp_path / "big"
    target.mkdir()
    (target / "f").write_text("x", encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = str(SHIM_DIR) + os.pathsep + env["PATH"]
    subprocess.run(["bash", "-c", "rm -rf %s" % target], env=env, capture_output=True)
    assert not target.exists()


@pytest.mark.skipif(shutil.which("trash-put") is None, reason="trash-put 미설치")
def test_deleted_content_is_recoverable():
    d = BASE / "rec"
    make_fixture(d)
    env = dict(os.environ)
    env["PATH"] = str(SHIM_DIR) + os.pathsep + env["PATH"]
    subprocess.run(["bash", "-c", "rm -rf sub"], cwd=str(d), env=env, capture_output=True)
    assert not (d / "sub").exists()
    listing = subprocess.run(["trash-list"], capture_output=True, text=True).stdout
    assert str(d / "sub") in listing


def test_macos_builtin_trash_is_used_when_trash_put_is_absent(tmp_path):
    """macOS 14.4+ 는 /usr/bin/trash 를 기본 제공한다. 설치기(setup_hooks.sh)는 이것을
    휴지통 도구로 인정하므로, 셰임도 이것을 써야 한다 — 아니면 '휴지통 있음'으로 설치해 놓고
    실제로는 삭제한다. trash-put 이 없는 PATH 에 가짜 uname(Darwin)·trash 를 둬서 흉내 낸다.
    """
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uname").write_text("#!/bin/sh\necho Darwin\n", encoding="utf-8")
    # 대시로 시작하는 인자를 받으면 옵션으로 오인했다는 뜻이다 — 실패로 기록한다.
    (fake / "trash").write_text(
        '#!/bin/sh\nfor a; do case "$a" in -*) echo "OPT:$a" >> "$LOG"; exit 2 ;; esac\n'
        'echo "$a" >> "$LOG"; mv -- "$a" "$BIN_DIR/"; done\n', encoding="utf-8")
    for f in fake.iterdir():
        f.chmod(0o755)
    d = BASE / "mac"
    make_fixture(d)
    bin_dir = tmp_path / "trashbin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    env = dict(os.environ, LOG=str(log), BIN_DIR=str(bin_dir))
    env.pop("CLAUDE_NO_TRASH", None)
    env["PATH"] = os.pathsep.join([str(SHIM_DIR), str(fake), "/usr/bin", "/bin"])
    proc = subprocess.run(["bash", "-c", "rm -rf sub a.txt -- -weird"], cwd=str(d), env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "휴지통 없이" not in proc.stderr
    assert "OPT:" not in log.read_text(encoding="utf-8")
    assert sorted(p.name for p in bin_dir.iterdir()) == ["-weird", "a.txt", "sub"]


def test_sandboxed_home_can_be_cleaned_up(tmp_path):
    """테스트·스크립트가 HOME 을 임시 디렉터리로 바꿔 두고 `rm -rf "$HOME"` 으로 정리하는 것은
    홈 삭제가 아니다. 실제 홈은 $HOME 이 아니라 사용자 DB 에서 구해야 한다 — bats 의 샌드박스
    teardown 이 이 오인으로 막혔다. 가짜 trash-put 이라 아무것도 지우지 않는다."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "trash-put").write_text('#!/bin/sh\necho "TRASHED $*"\n', encoding="utf-8")
    (fake / "trash-put").chmod(0o755)
    sandbox = BASE / "sandbox-home"
    sandbox.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HOME=str(sandbox))
    env.pop("CLAUDE_NO_TRASH", None)
    env["PATH"] = os.pathsep.join([str(SHIM_DIR), str(fake), "/usr/bin", "/bin"])
    proc = subprocess.run(["bash", "-c", 'rm -rf "$HOME"'], env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "거부" not in proc.stderr
    assert "TRASHED -- %s" % sandbox in proc.stdout
