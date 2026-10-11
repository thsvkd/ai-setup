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
    # 이 모듈의 bash 는 넘겨준 환경(PATH·HOME·D)을 받는다고 가정하고 rm 을 돌린다. Windows 에서
    # `bash` 가 WSL 로 잡히면 환경이 넘어가지 않아 엉뚱한 곳을 지운다. 그러면 아무것도 돌리지 않는다.
    probe = subprocess.run(["bash", "-c", 'printf %s "$RMSHIM_PROBE"'], capture_output=True,
                           env=dict(os.environ, RMSHIM_PROBE="ok"))
    if probe.stdout != b"ok":
        pytest.fail("bash does not receive the environment we pass (WSL bash?) - not running the rm tests: %r"
                    % shutil.which("bash"))
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
                          capture_output=True, text=True, encoding="utf-8")
    survivors = sorted(
        str(p.relative_to(d)) for p in d.rglob("*")
    )
    return proc.returncode, survivors


CASES = [
    ("plain file", "rm a.txt"),
    ("directory -r", "rm -r sub"),
    ("directory -rf", "rm -rf sub"),
    ("empty directory -d", "rm -d emptydir"),
    ("nonexistent file with -f", "rm -f nope.txt"),
    ("nonexistent file (no flags)", "rm nope.txt"),
    ("variable expansion", 'V="$D/sub"; rm -rf "$V"'),
    ("variable + slash", 'V="$D"; rm -rf "$V/sub"'),
    ("variable + glob", 'V="$D"; rm -f "$V"/*.txt'),
    ("unmatched glob with -f", "rm -f ./*.nomatch"),
    ("unmatched glob (no flags)", "rm ./*.nomatch"),
    ("matched glob", "rm ./*.txt"),
    ("dash file after --", "rm -- -weird"),
    ("name with spaces", 'rm "name with spaces.txt"'),
    ("name with newline", 'touch "$D/nl\nname"; rm "$D/nl\nname"'),
    ("symbolic link", "rm link"),
    ("multiple targets", "rm a.txt b.txt c.log"),
    ("only some exist with -f", "rm -f a.txt nope.txt b.txt"),
    ("only some exist (no flags)", "rm a.txt nope.txt b.txt"),
    ("find -exec +", 'find . -name "*.log" -exec rm -f {} +'),
    ("find -exec ;", 'find . -name "*.log" -exec rm -f {} \\;'),
    ("xargs -0", 'find . -name "*.log" -print0 | xargs -0 rm -f'),
    ("chaining", "cd sub && rm -f deep/x.log; echo done"),
    ("multiline", "cd sub\nrm -rf deep\necho done"),
    ("rm inside a heredoc (data)", "cat > note.md <<'EOT'\nrm -rf /\nEOT\nwc -l < note.md"),
    ("rm inside a script", "printf '#!/bin/sh\\nrm -f \"$1\"\\n' > s.sh; chmod +x s.sh; ./s.sh a.txt"),
    ("inside sh -c", 'sh -c "rm -f a.txt"'),
    ("timeout wrapper", "timeout 5 rm -f a.txt"),
    ("no arguments", "rm"),
    ("dot target", "rm -rf ."),
    ("parent dot target", "rm -rf sub/.."),
    ("CLAUDE_NO_TRASH escape hatch", "CLAUDE_NO_TRASH=1 rm -rf sub"),
]


@pytest.mark.parametrize("name,script", CASES, ids=[c[0] for c in CASES])
def test_matches_real_rm(name, script):
    real = observe(script, use_shim=False)
    shim = observe(script, use_shim=True)
    assert real == shim, "result differs from the real rm: %s" % name


REFUSED = ["rm -rf ~", 'rm -rf "$HOME"', "rm -rf /"]

# 셰임을 거쳐야 안전한 명령은 같은 셸 안에서 rm 이 셰임으로 잡히는지 먼저 확인한다. Windows 의
# PATH 에서 `bash` 가 WSL 로 잡히면 PATH·HOME 이 넘어가지 않아, 여기 있는 명령이 WSL 의 진짜
# rm 으로 실제 홈을 지웠다(2026-10-11). 확인에 실패하면 아무것도 지우지 않고 97 로 끝난다.
SHIM_GUARD = ('case "$(command -v rm)" in */shims/rm) ;; '
              '*) echo "rm is not the shim: $(command -v rm)" >&2; exit 97 ;; esac\n')


def run_via_shim(script, **kwargs):
    proc = subprocess.run(["bash", "-c", SHIM_GUARD + script],
                          capture_output=True, text=True, encoding="utf-8", **kwargs)
    assert proc.returncode != 97, "bash is not using the shim - %s" % proc.stderr
    return proc


def _guarded_home():
    """tmp 밖의 가짜 홈. 셰임은 tmp 아래의 HOME 은 보호하지 않으므로 BASE 아래에 둔다."""
    home = BASE / "guarded-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "keep").write_text("x", encoding="utf-8")
    return home


def _fake_trash_path(tmp_path):
    """아무것도 지우지 않는 trash-put 을 앞세운 PATH. 거부 테스트가 실제 홈을 대상으로 하므로,
    셰임이 퇴행해도 실제로는 아무것도 옮겨지지 않게 한다."""
    fake = tmp_path / "fakebin"
    fake.mkdir(exist_ok=True)
    (fake / "trash-put").write_text('#!/bin/sh\necho "TRASHED $*"\n', encoding="utf-8")
    (fake / "trash-put").chmod(0o755)
    return os.pathsep.join([str(SHIM_DIR), str(fake), "/usr/bin", "/bin"])


@pytest.mark.parametrize("script", REFUSED)
def test_root_and_home_are_refused(script, tmp_path):
    # 실제 홈을 대상으로 삼지 않는다. 셰임이 퇴행하면 /bin/rm 이 그대로 지우기 때문이다.
    home = _guarded_home()
    env = dict(os.environ, HOME=str(home))
    env.pop("CLAUDE_NO_TRASH", None)
    env["PATH"] = _fake_trash_path(tmp_path)
    proc = run_via_shim(script, cwd=str(BASE), env=env)
    assert proc.returncode != 0
    assert "refusing" in proc.stderr
    assert (home / "keep").is_file()


def test_tmp_targets_are_really_deleted(tmp_path):
    """/tmp 는 tmpfs 라 휴지통 자리도 같은 램이다 — 옮기면 램이 회수되지 않는다."""
    target = tmp_path / "big"
    target.mkdir()
    (target / "f").write_text("x", encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = str(SHIM_DIR) + os.pathsep + env["PATH"]
    run_via_shim("rm -rf %s" % target, env=env)
    assert not target.exists()


@pytest.mark.skipif(shutil.which("trash-put") is None, reason="trash-put not installed")
def test_deleted_content_is_recoverable():
    d = BASE / "rec"
    make_fixture(d)
    env = dict(os.environ)
    env["PATH"] = str(SHIM_DIR) + os.pathsep + env["PATH"]
    subprocess.run(["bash", "-c", "rm -rf sub"], cwd=str(d), env=env, capture_output=True)
    assert not (d / "sub").exists()
    listing = subprocess.run(["trash-list"], capture_output=True, text=True, encoding="utf-8").stdout
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
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "without the trash" not in proc.stderr
    assert "OPT:" not in log.read_text(encoding="utf-8")
    assert sorted(p.name for p in bin_dir.iterdir()) == ["-weird", "a.txt", "sub"]


def test_sandboxed_home_under_tmp_can_be_cleaned_up(tmp_path):
    """테스트·스크립트가 HOME 을 임시 디렉터리로 바꿔 두고 `rm -rf "$HOME"` 으로 정리하는 것은
    홈 삭제가 아니다 — bats 의 샌드박스 teardown 이 이 오인으로 막혔다."""
    sandbox = tmp_path / "sandbox-home"
    sandbox.mkdir()
    env = dict(os.environ, HOME=str(sandbox), PATH=_fake_trash_path(tmp_path))
    env.pop("CLAUDE_NO_TRASH", None)
    proc = run_via_shim('rm -rf "$HOME"', env=env)
    assert proc.returncode == 0, proc.stderr
    assert "refusing" not in proc.stderr


def test_overridden_home_outside_tmp_is_still_refused(tmp_path):
    """컨테이너(-e HOME=…)·`sudo -E` 처럼 passwd 홈과 $HOME 이 다르면 $HOME 도 진짜 홈이다."""
    app_home = BASE / "app-home"
    app_home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HOME=str(app_home), PATH=_fake_trash_path(tmp_path))
    env.pop("CLAUDE_NO_TRASH", None)
    proc = run_via_shim('rm -rf "$HOME"', env=env)
    assert proc.returncode != 0
    assert "refusing" in proc.stderr
    assert app_home.is_dir()


def test_username_is_not_evaluated_as_shell(tmp_path):
    """실제 홈 조회에 `~이름` 을 eval 한다. 이름에 셸 문법이 섞여도 실행되면 안 된다."""
    mark = tmp_path / "PWNED"
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "id").write_text('#!/bin/sh\necho "x;touch %s"\n' % mark, encoding="utf-8")
    (fake / "id").chmod(0o755)
    (fake / "trash-put").write_text('#!/bin/sh\nexit 0\n', encoding="utf-8")
    (fake / "trash-put").chmod(0o755)
    d = BASE / "evalcheck"
    d.mkdir(parents=True, exist_ok=True)
    (d / "f").write_text("x", encoding="utf-8")
    env = dict(os.environ, PATH=os.pathsep.join([str(SHIM_DIR), str(fake), "/usr/bin", "/bin"]))
    env.pop("CLAUDE_NO_TRASH", None)
    subprocess.run(["bash", "-c", "rm f"], cwd=str(d), env=env, capture_output=True)
    assert not mark.exists()
