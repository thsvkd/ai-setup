#!/usr/bin/env python3
"""claude-code-setup 대화형 온보딩 — 무엇을 어떻게 설치할지 고르게 한다.

scripts/setup.sh (와 setup.ps1) 가 **인자 없이** 호출됐을 때만 실행된다. 플래그가
명시됐다면 사용자가 이미 뜻을 밝힌 것이므로 온보딩을 띄우지 않는다.

선택 결과는 stdout 이 아니라 --out 파일에 KEY=VALUE 로 쓴다. stdout 은 프롬프트 UI 가
쓰기 때문이다. 호출부는 이 파일을 읽어 기존 플래그로 옮긴다.

  SCOPE=all|hooks|agentsmd     설치 범위
  DEFAULT_MODE=auto|bypassPermissions
  NEWLINE_CHORD=shift-enter|ctrl-enter
                               줄바꿈 키 (SCOPE=all 일 때만 기록)
  HARNESSES=claude,codex,...   지침을 설치할 하네스 (SCOPE=all|agentsmd 일 때만 기록)
  OVERWRITE_AGENTSMD=0|1       기존 지침 파일을 덮어쓸지
  OMC=0|1                      oh-my-claudecode 플러그인 + 캐시 TTL HUD 도 설치할지
                               (SCOPE=all|hooks 일 때만 기록)
  OUTPUT_STYLE=0|1             fluent-korean 플러그인 설치 + outputStyle 지정 여부
                               (SCOPE=all|hooks 일 때만 기록)
  MODS=0|1                     Claude Code mod 설치 여부 (SCOPE=all|hooks 일 때만 기록)
  DRY_RUN=0|1                  실제 적용 전에 변경 계획만 볼지

종료 코드로 세 상황을 구분한다:

  0   사용자가 선택을 마쳤다 — --out 파일에 결과가 있다.
  2   대화형으로 물을 수 없는 환경이다 (TTY 없음 / CI / 벤더 import 실패).
      호출부는 지금까지처럼 기본값으로 그냥 진행해야 한다. 실패가 아니다.
  130 사용자가 Ctrl+C 로 취소했다. 호출부는 설치를 중단해야 한다.
      2 와 달리 "기본값으로 진행"으로 해석하면 안 된다 — 명시적 거부다.

## curl … | sh 에서 프롬프트가 동작하는 이유

`curl -fsSL install.sh | sh` 는 stdin 이 **스크립트 본문**이다. 프롬프트가 stdin 을 읽으면
스크립트 나머지를 삼키거나 EOF 를 만난다. 실측해보면 questionary 는 이 상황에서 에러도
없이 **첫 항목을 자동 확정**해버린다 — 사용자가 아무것도 고르지 않았는데 설치가 진행되는
가장 위험한 실패 모드다.

그래서 프롬프트를 띄우기 전에 제어 터미널(POSIX `/dev/tty`, Windows `CONIN$`/`CONOUT$`)을
직접 열어 fd 0/1 에 얹는다. 터미널을 못 열면 대화형을 아예 포기하고 2 로 빠진다.
"""

import os
import sys

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")

EXIT_OK = 0
EXIT_NON_INTERACTIVE = 2
EXIT_CANCELLED = 130

SCOPE_ALL = "all"
SCOPE_HOOKS = "hooks"
SCOPE_AGENTSMD = "agentsmd"

# Which harnesses the instruction files can be installed for, and what each one
# actually reads. Codex, Grok and OpenCode read the root AGENTS.md directly;
# Claude Code reads CLAUDE.md, which imports it. The worker owns that mapping --
# here we only collect the selection.
HARNESS_CHOICES = (
    ("claude", "Claude Code — AGENTS.md + CLAUDE.md (@AGENTS.md 로 불러옴)"),
    ("codex", "Codex — AGENTS.md 를 직접 읽음"),
    ("grok", "Grok — AGENTS.md 를 직접 읽음"),
    ("opencode", "OpenCode — AGENTS.md 를 직접 읽음"),
)


def parse_args(argv):
    out_path = ""
    project_dir = os.getcwd()
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_path = argv[i + 1]
            i += 2
        elif argv[i] == "--project-dir" and i + 1 < len(argv):
            project_dir = argv[i + 1]
            i += 2
        else:
            i += 1
    return out_path, project_dir


def is_ci() -> bool:
    """CI 는 TTY 를 붙여주는 경우가 있어(예: tmux, docker -t) TTY 검사만으로는 못 거른다."""
    for key in ("CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE"):
        value = os.environ.get(key, "")
        if value and value.lower() not in ("0", "false", ""):
            return True
    return False


def attach_terminal():
    """제어 터미널을 fd 0/1 에 얹는다. 성공하면 True.

    이미 stdin·stdout 이 모두 터미널이면 아무것도 하지 않는다 (일반 실행 경로).
    """
    if sys.stdin.isatty() and sys.stdout.isatty():
        return True

    try:
        # Windows 는 입력/출력 콘솔 장치가 따로다. POSIX 는 /dev/tty 하나로 양방향.
        if os.name == "nt":
            in_fd = os.open("CONIN$", os.O_RDONLY)
            out_fd = os.open("CONOUT$", os.O_WRONLY)
        else:
            in_fd = os.open("/dev/tty", os.O_RDWR)
            out_fd = in_fd
    except OSError:
        return False

    try:
        if not sys.stdin.isatty():
            os.dup2(in_fd, 0)
        if not sys.stdout.isatty():
            os.dup2(out_fd, 1)
    except OSError:
        return False
    finally:
        for fd in {in_fd, out_fd}:
            if fd > 2:
                try:
                    os.close(fd)
                except OSError:
                    pass

    # dup2 는 fd 만 바꾼다. 파이썬 파일 객체는 옛 fd 를 감싼 채로 남아 있으므로 다시 만든다.
    try:
        sys.stdin = open(0, "r", closefd=False)
        sys.stdout = open(1, "w", closefd=False)
    except OSError:
        return False
    return os.isatty(0) and os.isatty(1)


def build_style(questionary):
    """clack 처럼 선택지가 한눈에 들어오도록 최소한만 손본다."""
    return questionary.Style(
        [
            ("qmark", "fg:#5f87d7 bold"),
            ("question", "bold"),
            ("pointer", "fg:#5f87d7 bold"),
            ("highlighted", "fg:#5f87d7 bold"),
            ("selected", "fg:#5f87d7"),
            ("answer", "fg:#5f87d7 bold"),
            ("instruction", "fg:#808080"),
        ]
    )


def ask_all(questionary, project_dir):
    """선택 결과 dict 를 반환. 사용자가 취소하면 None."""
    style = build_style(questionary)

    print("")
    print("  claude-code-setup — Claude Code 안전 설정")
    print("")

    scope = questionary.select(
        "무엇을 설치할까요?",
        choices=[
            questionary.Choice("전체 — 가드 훅/권한(전역) + AGENTS.md(현재 폴더) + 번들 스킬", value=SCOPE_ALL),
            questionary.Choice("가드 훅 + 권한만 (~/.claude, 모든 프로젝트에 적용)", value=SCOPE_HOOKS),
            questionary.Choice("AGENTS.md 만 (현재 폴더)", value=SCOPE_AGENTSMD),
        ],
        style=style,
        instruction="(↑↓ 이동, Enter 선택)",
    ).ask()
    if scope is None:
        return None

    answers = {
        "SCOPE": scope,
        "DEFAULT_MODE": "auto",
        "OVERWRITE_AGENTSMD": "0",
        "DRY_RUN": "0",
    }

    if scope in (SCOPE_ALL, SCOPE_HOOKS):
        mode = questionary.select(
            "권한 모드는 어떻게 할까요?",
            choices=[
                questionary.Choice(
                    "auto — 안전한 작업은 자동 허용, 위험한 것만 확인 (권장)", value="auto"
                ),
                questionary.Choice(
                    "bypassPermissions — 권한 확인을 모두 생략 (가드 훅은 그대로 동작)",
                    value="bypassPermissions",
                ),
            ],
            style=style,
            instruction="(↑↓ 이동, Enter 선택)",
        ).ask()
        if mode is None:
            return None
        answers["DEFAULT_MODE"] = mode

        if mode == "bypassPermissions":
            print("")
            print("  ⚠️  bypassPermissions 는 Claude Code 의 권한 확인을 전부 건너뜁니다.")
            print("     이 레포의 가드 훅(rm 휴지통 치환, git 백업 등)은 그대로 동작하지만,")
            print("     훅이 판단하지 않는 명령은 확인 없이 실행됩니다.")
            print("")

    # 줄바꿈 키는 전체 설치에만 포함된다. 훅/AGENTS.md 단독 범위에서는 묻지 않는다.
    if scope == SCOPE_ALL:
        chord = questionary.select(
            "줄바꿈 키는 어떤 조합으로 할까요?",
            choices=[
                questionary.Choice(
                    "Shift+Enter — 줄을 넣고 전송하지 않음 (기본)", value="shift-enter"
                ),
                questionary.Choice("Ctrl+Enter — 줄을 넣고 전송하지 않음", value="ctrl-enter"),
            ],
            style=style,
            instruction="(↑↓ 이동, Enter 선택)",
        ).ask()
        if chord is None:
            return None
        answers["NEWLINE_CHORD"] = chord

    if scope in (SCOPE_ALL, SCOPE_AGENTSMD):
        # Multi-select: one project is often driven by more than one agent, and
        # the artefacts are additive, so there is no reason to force a choice of
        # exactly one. Selecting none would install nothing, so it is rejected
        # rather than silently treated as "all".
        harnesses = questionary.checkbox(
            "어떤 하네스에 지침을 설치할까요?",
            choices=[
                questionary.Choice(label, value=name, checked=True)
                for name, label in HARNESS_CHOICES
            ],
            validate=lambda picked: bool(picked) or "최소 하나는 선택해야 합니다.",
            style=style,
            instruction="(↑↓ 이동, Space 선택/해제, Enter 확정)",
        ).ask()
        if harnesses is None:
            return None
        answers["HARNESSES"] = ",".join(harnesses)

        # 지침 파일은 프로젝트별로 손보는 파일이라 기본이 '건너뛰기'다. 이미 있을 때만 묻는다.
        # 하나라도 있으면 묻는다 — 덮어쓰기 결정은 파일별이 아니라 이 설치 전체에 적용된다.
        existing = [
            os.path.join(project_dir, name)
            for name in ("AGENTS.md", "CLAUDE.md")
            if os.path.isfile(os.path.join(project_dir, name))
        ]
        # CLAUDE.md 는 claude 를 고른 경우에만 설치 대상이므로, 그 경우에만 묻는 근거가 된다.
        if "claude" not in harnesses:
            existing = [p for p in existing if not p.endswith("CLAUDE.md")]
        if existing:
            overwrite = questionary.confirm(
                "%s 가 이미 있습니다. 덮어쓸까요?" % ", ".join(existing),
                default=False,
                style=style,
            ).ask()
            if overwrite is None:
                return None
            answers["OVERWRITE_AGENTSMD"] = "1" if overwrite else "0"

    # OMC 는 전역(~/.claude) 설치라 AGENTS.md 단독 범위에서는 묻지 않는다.
    if scope in (SCOPE_ALL, SCOPE_HOOKS):
        omc = questionary.confirm(
            "oh-my-claudecode(OMC) 플러그인도 설치할까요? (HUD 에 프롬프트 캐시 TTL 표시 포함)",
            default=False,
            style=style,
        ).ask()
        if omc is None:
            return None
        answers["OMC"] = "1" if omc else "0"

        fluent = questionary.confirm(
            "출력 스타일을 fluent-korean 으로 지정할까요? (플러그인 설치 포함)",
            default=False,
            style=style,
        ).ask()
        if fluent is None:
            return None
        answers["OUTPUT_STYLE"] = "1" if fluent else "0"

        mods = questionary.confirm(
            "Claude Code mod 도 설치할까요? (Bash 변경 표시에서 HUD 캐시 제외, 캐시 TTL 상태 줄 — v2.1.290 이상)",
            default=False,
            style=style,
        ).ask()
        if mods is None:
            return None
        answers["MODS"] = "1" if mods else "0"

    plan = questionary.select(
        "지금 바로 적용할까요?",
        choices=[
            questionary.Choice("적용한다", value="apply"),
            questionary.Choice("먼저 변경 계획만 본다 (--dry-run, 아무것도 바꾸지 않음)", value="dry"),
        ],
        style=style,
        instruction="(↑↓ 이동, Enter 선택)",
    ).ask()
    if plan is None:
        return None
    answers["DRY_RUN"] = "1" if plan == "dry" else "0"

    return answers


def write_answers(out_path, answers):
    # newline="\n" 을 고정한다. Windows python 은 기본 텍스트 모드에서 \n 을 \r\n 으로 바꾸는데,
    # 이 파일을 읽는 setup.sh 의 `read` 는 CR 을 값에 그대로 남긴다. 그러면 SCOPE·NEWLINE_CHORD 는
    # 물론 DRY_RUN=1 도 매칭에 실패해서, 미리보기를 고른 사용자에게 실제 쓰기가 일어난다.
    lines = ["%s=%s\n" % (k, v) for k, v in answers.items()]
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def main(argv) -> int:
    out_path, project_dir = parse_args(argv)
    if not out_path:
        print("usage: onboard.py --out <file> [--project-dir <dir>]", file=sys.stderr)
        return EXIT_NON_INTERACTIVE

    if is_ci():
        return EXIT_NON_INTERACTIVE
    if not attach_terminal():
        return EXIT_NON_INTERACTIVE

    # 벤더 경로를 앞에 넣어, 사용자 환경에 다른 버전이 있어도 우리 것이 쓰이게 한다.
    sys.path.insert(0, VENDOR)
    try:
        import questionary
    except Exception:
        # 벤더가 깨졌거나 파이썬이 너무 낮으면 온보딩만 포기한다. 설치는 계속돼야 한다.
        return EXIT_NON_INTERACTIVE

    try:
        answers = ask_all(questionary, project_dir)
    except KeyboardInterrupt:
        return EXIT_CANCELLED
    except Exception:
        # 터미널이 프롬프트를 못 그리는 경우(예: 이상한 TERM)에도 설치를 막지 않는다.
        return EXIT_NON_INTERACTIVE

    if answers is None:
        print("")
        print("  취소했습니다. 아무것도 설치하지 않았습니다.")
        return EXIT_CANCELLED

    write_answers(out_path, answers)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
