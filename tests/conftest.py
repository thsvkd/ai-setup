"""공용 pytest 픽스처: 훅을 서브프로세스로 실행하고 판정(permissionDecision)을 파싱한다.

Claude Code 훅은 JSON 이벤트를 stdin 으로 받아, stdout 에 hookSpecificOutput.permissionDecision
(allow|deny|ask)을 담은 JSON 을 출력하거나(판정), 아무것도 출력하지 않는다(통과). 이 계약을
블랙박스로 검증한다 — 보안 도구에서 가장 가치 있는 테스트.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "res" / "hooks"


def _run(hook_name: str, event: dict):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(HOOKS_DIR / hook_name)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    out = (proc.stdout or "").strip()
    payload = json.loads(out) if out else None
    decision = payload["hookSpecificOutput"]["permissionDecision"] if payload else None
    return decision, payload, proc


@pytest.fixture
def run_hook():
    """run_hook(hook_name, event) -> (decision|None, payload|None, CompletedProcess)"""
    return _run
