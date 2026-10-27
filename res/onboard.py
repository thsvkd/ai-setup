#!/usr/bin/env python3
"""ai-setup 대화형 온보딩 — 무엇을 어떻게 설치할지 고르게 한다.

scripts/setup.sh (와 setup.ps1) 가 **인자 없이** 호출됐을 때만 실행된다. 플래그가
명시됐다면 사용자가 이미 뜻을 밝힌 것이므로 온보딩을 띄우지 않는다.

선택 결과는 stdout 이 아니라 --out 파일에 KEY=VALUE 로 쓴다. stdout 은 프롬프트 UI 가
쓰기 때문이다. 호출부는 이 파일을 읽어 기존 플래그로 옮긴다.

  SKIP=0|1                     1 이면 아무것도 설치하지 않는다 (허브의 Quit, 빈 선택의 Apply).
                               1 일 때는 다른 키를 쓰지 않는다.
  STAGES=base,harness,...      켠 단계, stages.STAGE_ORDER 순서. 비어 있으면 SKIP=1 로 쓴다
  HARNESSES=claude,codex,...   선택한 하네스
  DEFAULT_MODE=auto|bypassPermissions
                               hooks 단계가 켜졌을 때만 기록. 재실행에서 메뉴가 보여 줄 수 없는
                               기록값(acceptEdits·plan·없음)을 바꾸지 않았으면 기록하지 않는다
  NEWLINE_CHORD=shift-enter|ctrl-enter
                               줄바꿈 키 (newline 단계가 켜졌을 때만 기록, 위와 같은 재실행 규칙)
  JARVIS_ROLE=none|gateway|core
  HERDR=0|1
  OMC=0|1                      이미 OMC HUD 인 statusLine 의 캐시 래퍼
  OUTPUT_STYLE=0|1             fluent-korean 출력 스타일
  MODS=0|1                     Claude Code mod
                               (위 셋은 claude_special 단계와 Claude Code 가 모두 켜졌을 때만 1)
  OVERWRITE_AGENTSMD=0|1       기존 지침 파일을 덮어쓸지
  DRY_RUN=0|1                  실제 적용 전에 변경 계획만 볼지 (허브의 Preview)

종료 코드로 네 상황을 구분한다:

  0   사용자가 선택을 마쳤다 — --out 파일에 결과가 있다.
  1   프롬프트를 띄우다가 깨졌다 (렌더·입력 오류). 사용자는 무언가를 고르던 중이었으므로
      호출부는 설치를 중단해야 한다. 고르지도 않은 기본값으로 설치하면 안 된다.
  2   대화형으로 물을 수 없는 환경이다 (TTY 없음 / CI / Git Bash / 콘솔 준비 실패). 프롬프트를
      띄우기 전에 판정한다. 호출부는 아무것도 설치하지 않고 끝낸다. 실패가 아니다.
  130 사용자가 Ctrl+C 로 취소했다. 호출부는 설치를 중단해야 한다.
      2 와 달리 "기본값으로 진행"으로 해석하면 안 된다 — 명시적 거부다.

호출부는 2 이면 설치하지 않고 끝낸다. 파이썬이 traceback 으로 죽는 경우(1)도 중단이다.

## curl … | sh 에서 프롬프트가 동작하는 이유

`curl -fsSL install.sh | sh` 는 stdin 이 **스크립트 본문**이다. 프롬프트가 stdin 을 읽으면
스크립트 나머지를 삼키거나 EOF 를 만난다. 실측해보면 예전에 쓰던 questionary 는 이 상황에서
에러도 없이 **첫 항목을 자동 확정**해버렸다 — 사용자가 아무것도 고르지 않았는데 설치가 진행되는
가장 위험한 실패 모드다.

그래서 프롬프트를 띄우기 전에 제어 터미널(POSIX `/dev/tty`, Windows `CONIN$`/`CONOUT$`)을
직접 열어 fd 0/1 에 얹는다. 터미널을 못 열면 대화형을 아예 포기하고 2 로 빠진다.
"""

import json
import os
import sys

EXIT_OK = 0
EXIT_FAILED = 1
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
    ("claude", "Claude Code", "AGENTS.md + CLAUDE.md, imported via @AGENTS.md"),
    ("codex", "Codex", "reads AGENTS.md directly"),
    ("grok", "Grok", "reads AGENTS.md directly"),
    ("agy", "Antigravity", "listed, off unless chosen"),
    ("opencode", "OpenCode", "reads AGENTS.md directly"),
    ("gemini", "Gemini", "listed, off unless chosen"),
    ("copilot", "Copilot", "listed, off unless chosen"),
)

# 기본으로 켜 두는 하네스. 나머지는 목록에만 있다.
DEFAULT_HARNESSES = ("claude", "codex")

# 단계 실행 순서. stages.STAGE_ORDER 와 같아야 한다 — STAGES 답을 이 순서로 쓴다.
STAGE_ORDER = (
    "base", "harness", "plugins", "skills", "codegraph", "mcp",
    "newline", "claude_special", "tools", "hooks", "agentsmd",
)

# 허브의 카테고리. 내부 단계는 11개지만 codegraph 와 mcp 는 한 화면에서 고른다.
CATEGORIES = (
    ("base", "Base", "git, Python, Node if a later item needs it"),
    ("harness", "Harnesses", "which harnesses, and whether to install missing ones"),
    ("plugins", "Plugins", "Claude Code plugins for the selected harnesses"),
    ("skills", "Skills", "bundled skills for the selected harnesses"),
    ("codegraph", "CodeGraph", "package, then MCP on the selected harnesses"),
    ("newline", "Newline key", "the key that inserts a newline"),
    ("claude_special", "Claude extras", "output style, mods, OMC HUD wrap"),
    ("tools", "Tools", "Orca, Tailscale, Jarvis, herdr"),
    ("hooks", "Guard hooks", "with the permission mode"),
    ("agentsmd", "AGENTS.md", "in the current directory"),
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

    # Git Bash(mintty) 는 Windows 프로그램에 콘솔 대신 파이프를 준다. 여기서 CONOUT$ 를 열면
    # 보이지 않는 숨은 콘솔에 프롬프트를 그리고 키를 기다려, 설치가 멈춘 것처럼 보인다.
    if os.name == "nt" and os.environ.get("MSYSTEM") and not sys.stdout.isatty():
        print("  Interactive onboarding is unavailable in Git Bash; nothing was installed. "
              "Run from PowerShell, or use --no-onboard with a scope flag.", file=sys.stderr)
        return False

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


def _stopped(value):
    return value is None


def default_state():
    """아무것도 묻기 전의 선택. 산책과 허브가 같은 기본값에서 시작한다."""
    return {
        "stages": {stage for stage in STAGE_ORDER},
        "harnesses": list(DEFAULT_HARNESSES),
        "chord": "shift-enter",
        "output_style": True,
        "mods": True,
        "omc": True,
        "jarvis_role": "none",
        "herdr": False,
        "mode": "auto",
        "overwrite": False,
    }


def _include(tui, state, stage, prompt):
    value = tui.confirm(prompt, default=stage in state["stages"])
    if _stopped(value):
        return False
    if value:
        state["stages"].add(stage)
    else:
        state["stages"].discard(stage)
    return True


def _edit_base(tui, state, project_dir):
    return _include(tui, state, "base",
                    "Include base prerequisites (git, Python, Node if a later item needs it)?")


def _edit_harness(tui, state, project_dir):
    harnesses = tui.multiselect(
        "Which harnesses should be selected?",
        HARNESS_CHOICES,
        initial_values=state["harnesses"],
    )
    if _stopped(harnesses):
        return False
    if harnesses != state["harnesses"]:
        # 덮어쓰기 질문이 가리키던 파일 목록이 바뀌었으므로 안전한 기본값으로 되돌린다.
        state["overwrite"] = False
    state["harnesses"] = harnesses
    return _include(tui, state, "harness", "Install the selected harnesses that are missing?")


def _edit_plugins(tui, state, project_dir):
    return _include(tui, state, "plugins", "Include plugin install?")


def _edit_skills(tui, state, project_dir):
    return _include(tui, state, "skills", "Include skill install?")


def _edit_codegraph(tui, state, project_dir):
    return (_include(tui, state, "codegraph", "Include the CodeGraph package?")
            and _include(tui, state, "mcp", "Include CodeGraph MCP registration?"))


def _edit_newline(tui, state, project_dir):
    if not _include(tui, state, "newline", "Include newline key setup?"):
        return False
    if "newline" not in state["stages"]:
        return True
    options = [
        ("shift-enter", "Shift+Enter", "inserts a newline without sending · default"),
        ("ctrl-enter", "Ctrl+Enter", "inserts a newline without sending"),
    ]
    chord = tui.select("Which key combination for a newline?", options,
                       initial=[o[0] for o in options].index(state["chord"]))
    if _stopped(chord):
        return False
    state["chord"] = chord
    return True


def _edit_claude_special(tui, state, project_dir):
    if not _include(tui, state, "claude_special", "Include Claude-only special setup?"):
        return False
    if "claude_special" not in state["stages"] or "claude" not in state["harnesses"]:
        return True
    for key, prompt in (
        ("output_style", "Set the output style to fluent-korean?"),
        ("mods", "Install Claude Code mods (bash-diff-filter, cache-ttl-status, "
                 "korean-reply-rewrite, v2.1.290 or later)?"),
        ("omc", "Wrap the OMC HUD cache when statusLine is already the OMC HUD?"),
    ):
        value = tui.confirm(prompt, default=state[key])
        if _stopped(value):
            return False
        state[key] = value
    return True


def _edit_tools(tui, state, project_dir):
    if not _include(tui, state, "tools", "Include tool install (Orca, Tailscale, Jarvis)?"):
        return False
    if "tools" not in state["stages"]:
        return True
    options = [
        ("none", "Do not install", "leave Jarvis alone"),
        ("gateway", "Gateway", "deploy/gateway.toml"),
        ("core", "Core", "deploy/s2.toml"),
    ]
    role = tui.select("Jarvis role?", options,
                      initial=[o[0] for o in options].index(state["jarvis_role"]))
    if _stopped(role):
        return False
    state["jarvis_role"] = role
    herdr = tui.confirm("Install herdr?", default=state["herdr"])
    if _stopped(herdr):
        return False
    state["herdr"] = herdr
    return True


def _edit_hooks(tui, state, project_dir):
    if not _include(tui, state, "hooks", "Include guard hooks?"):
        return False
    if "hooks" not in state["stages"]:
        return True
    options = [
        ("auto", "auto", "safe actions auto-approved, only risky ones ask · recommended"),
        ("bypassPermissions", "bypassPermissions",
         "skip all permission prompts, guard hooks still run"),
    ]
    mode = tui.select("Which permission mode?", options,
                      initial=[o[0] for o in options].index(state["mode"]))
    if _stopped(mode):
        return False
    state["mode"] = mode
    if mode == "bypassPermissions":
        tui.warn([
            "bypassPermissions skips all of Claude Code's permission prompts.",
            "This repo's guard hooks (rm to trash, git backup, etc.) still run,",
            "but commands the hooks do not judge run without confirmation.",
        ])
    return True


def _edit_agentsmd(tui, state, project_dir):
    if not _include(tui, state, "agentsmd", "Include AGENTS.md in the current directory?"):
        return False
    if "agentsmd" not in state["stages"]:
        return True
    names = ("AGENTS.md", "CLAUDE.md") if "claude" in state["harnesses"] else ("AGENTS.md",)
    existing = [os.path.join(project_dir, name) for name in names
                if os.path.isfile(os.path.join(project_dir, name))]
    if existing:
        overwrite = tui.confirm("%s already exists. Overwrite?" % ", ".join(existing),
                                default=state["overwrite"])
        if _stopped(overwrite):
            return False
        state["overwrite"] = overwrite
    return True


EDITORS = {
    "base": _edit_base,
    "harness": _edit_harness,
    "plugins": _edit_plugins,
    "skills": _edit_skills,
    "codegraph": _edit_codegraph,
    "newline": _edit_newline,
    "claude_special": _edit_claude_special,
    "tools": _edit_tools,
    "hooks": _edit_hooks,
    "agentsmd": _edit_agentsmd,
}


def _summary(state, category):
    """허브 한 줄에 붙는 현재 선택. 꺼진 카테고리는 off 다."""
    on = state["stages"]
    names = dict((value, label) for value, label, _ in HARNESS_CHOICES)
    if category == "harness":
        picked = ", ".join(names[h] for h in state["harnesses"]) or "none"
        return picked + ("" if "harness" in on else " · no install")
    if category == "codegraph":
        parts = [label for stage, label in (("codegraph", "package"), ("mcp", "MCP")) if stage in on]
        return ", ".join(parts) or "off"
    if category not in on:
        return "off"
    if category == "newline":
        return "Shift+Enter" if state["chord"] == "shift-enter" else "Ctrl+Enter"
    if category == "claude_special":
        if "claude" not in state["harnesses"]:
            return "on · needs Claude Code"
        parts = [label for key, label in (("output_style", "fluent-korean"), ("mods", "mods"),
                                          ("omc", "HUD wrap")) if state[key]]
        return ", ".join(parts) or "on · nothing chosen"
    if category == "tools":
        return "Jarvis: %s%s" % (state["jarvis_role"], " · herdr" if state["herdr"] else "")
    if category == "hooks":
        return state["mode"]
    return "on"


def hub_options(state):
    """허브 select 의 항목. 카테고리 다음에 Apply, Preview, Quit 순서다. 테스트가 직접 부른다."""
    options = [(category, "%s · %s" % (label, _summary(state, category)), hint)
               for category, label, hint in CATEGORIES]
    options += [
        ("apply", "Apply", "install the selection above"),
        ("dry", "Preview the plan", "--dry-run, changes nothing"),
        ("quit", "Quit", "install nothing"),
    ]
    return options


def _answers(state, plan):
    # 빈 STAGES 를 쓰면 setup.sh·setup.ps1 은 범위 플래그가 없다고 보고 예전 전체 설치로 간다.
    # 아무 단계도 켜지 않은 Apply 는 Quit 과 같다.
    if not state["stages"]:
        return {"SKIP": "1"}
    answers = {
        "SKIP": "0",
        "STAGES": ",".join(stage for stage in STAGE_ORDER if stage in state["stages"]),
        "HARNESSES": ",".join(state["harnesses"]),
        "JARVIS_ROLE": state["jarvis_role"] if "tools" in state["stages"] else "none",
        "HERDR": "1" if state["herdr"] and "tools" in state["stages"] else "0",
        "DRY_RUN": "1" if plan == "dry" else "0",
    }
    special = "claude_special" in state["stages"] and "claude" in state["harnesses"]
    for key in ("omc", "output_style", "mods"):
        answers[key.upper()] = "1" if special and state[key] else "0"
    answers["OVERWRITE_AGENTSMD"] = "1" if state["overwrite"] and "agentsmd" in state["stages"] else "0"
    # 메뉴가 보여 줄 수 없는 기록값(acceptEdits·plan·없음) 자리에서는 시작값이 기본값이다. 그 기본값을 그대로 넘기면
    # setup 이 명시한 값으로 전달해 기록값을 되돌리므로, 바꾸지 않았으면 넘기지 않는다. 메뉴가 보여 준 기록값은 넘긴다.
    # 훅이 이미 깔렸으면 같은 값이라 계획이 없고, 아직 안 깔렸으면 그 값으로 깔아야 한다.
    unchanged = state.get("unchanged", {})
    if "hooks" in state["stages"] and unchanged.get("mode") != state["mode"]:
        answers["DEFAULT_MODE"] = state["mode"]
    if "newline" in state["stages"] and unchanged.get("chord") != state["chord"]:
        answers["NEWLINE_CHORD"] = state["chord"]
    return answers


def _hub(tui, state, project_dir, cursor):
    """카테고리 메뉴. Apply·Preview 는 답을, Quit 은 SKIP 을, 취소는 None 을 반환한다."""
    while True:
        options = hub_options(state)
        choice = tui.select("Choose a category to change, then Apply.", options, initial=cursor)
        if _stopped(choice):
            return None
        if choice == "quit":
            return {"SKIP": "1"}
        if choice in ("apply", "dry"):
            tui.outro("Showing the change plan." if choice == "dry" else "Starting installation.")
            return _answers(state, choice)
        if not EDITORS[choice](tui, state, project_dir):
            return None
        cursor = [o[0] for o in options].index(choice)


def _claude_dir():
    home = os.environ.get("USERPROFILE") if os.name == "nt" else os.environ.get("HOME")
    return os.path.join(home or os.path.expanduser("~"), ".claude")


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def recorded_choices():
    """이전 설치가 남긴 권한 모드·줄바꿈 키. 메뉴가 이 값에서 시작해야 그대로 둔 Apply 가 사용자의 값을 되돌리지 않는다."""
    keybinds = _read_json(os.path.join(_claude_dir(), ".claude-code-setup.json")).get("keybinds")
    permissions = _read_json(os.path.join(_claude_dir(), "settings.json")).get("permissions")
    chord = keybinds.get("newline_chord") if isinstance(keybinds, dict) else None
    mode = permissions.get("defaultMode") if isinstance(permissions, dict) else None
    choices = {}
    if chord in ("shift-enter", "ctrl-enter"):
        choices["chord"] = chord
    if mode in ("auto", "bypassPermissions"):    # _edit_hooks 가 고를 수 있는 값만
        choices["mode"] = mode
    return choices


def has_receipt():
    """이 setup 이 이미 한 번 설치한 머신인가. 그렇다면 산책 없이 허브부터 연다.

    경로 규칙은 stages._receipt_path 와 같다. stages 를 import 하지 않는 것은 onboard.py 가
    tui.py 만 옆에 둔 채로도 돌아야 하기 때문이다.
    """
    return os.path.isfile(os.path.join(_claude_dir(), ".claude-code-setup.json"))


def ask_all(tui, project_dir, first_run=True):
    """선택 결과 dict 를 반환. 사용자가 취소하면 None.

    첫 실행이면 산책과 Skip 을 묻는다. 산책은 카테고리 편집기를 순서대로 연 뒤 허브로
    가고, Skip 은 허브로 바로 간다. 영수증이 있는 머신은 허브부터 연다. 설치는 허브의
    Apply 에서만 일어나고, Quit 은 아무것도 설치하지 않는다.
    """
    tui.intro("ai-setup — Claude Code safety setup")
    state = default_state()
    recorded = recorded_choices()
    state.update(recorded)
    if not first_run:
        state["unchanged"] = {key: state[key] for key in ("mode", "chord") if key not in recorded}
        return _hub(tui, state, project_dir, 0)

    start = tui.select(
        "Set up this machine?",
        [
            ("walk", "Walk the stages", "accept or skip each stage"),
            ("skip", "Skip", "go to the category menu"),
        ],
    )
    if _stopped(start):
        return None
    if start == "skip":
        return _hub(tui, state, project_dir, 0)
    for category, _, _ in CATEGORIES:
        if not EDITORS[category](tui, state, project_dir):
            return None
    return _hub(tui, state, project_dir, [o[0] for o in hub_options(state)].index("apply"))


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

    try:
        # stdin 이 닫힌 채 실행되면 sys.stdin 이 None 이라 여기서 예외가 난다. 역시 물을 수 없음이다.
        if not attach_terminal():
            return EXIT_NON_INTERACTIVE
        # 스크립트 폴더가 sys.path 에 없는 실행(PYTHONSAFEPATH 등)에서도 옆의 tui.py 를 찾는다.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tui
        # 아무것도 그리기 전의 콘솔 준비다. 여기서 실패하면(보이지 않는 콘솔, VT 미지원) 사용자는
        # 아무것도 보지 못했으므로 '물을 수 없음'이다.
        tui.prepare_console()
    except Exception as exc:
        print("  Interactive onboarding is unavailable; nothing was installed (%s)." % exc, file=sys.stderr)
        return EXIT_NON_INTERACTIVE

    try:
        answers = ask_all(tui, project_dir, first_run=not has_receipt())
    except KeyboardInterrupt:
        return EXIT_CANCELLED
    except Exception as exc:
        # 프롬프트가 깨졌다(예: VT 를 못 켜는 콘솔). 사용자는 고르던 중이었으므로 고르지도 않은
        # 기본값으로 설치하지 않고 전체를 멈춘다.
        try:
            print("\n  Interactive onboarding was interrupted; nothing was installed (%s).\n"
                  "  Re-run with --no-onboard and a scope flag." % exc)
        except Exception:
            pass    # 터미널이 끊겨 안내조차 못 찍는 경우에도 종료 코드는 지킨다.
        return EXIT_FAILED

    if answers is None:
        tui.cancel("Cancelled. Nothing was installed.")
        return EXIT_CANCELLED

    write_answers(out_path, answers)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
