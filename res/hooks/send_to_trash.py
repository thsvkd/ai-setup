# -*- coding: utf-8 -*-
"""
send_to_trash.py (Windows 전용)
지정된 경로들을 OS 휴지통으로 이동시킨다 (복구 가능한 삭제).
send2trash 가 없거나 오류가 나면 "아무것도 지우지 않고" 실패한다 (fail-closed).
"""
import os
import sys


def main() -> int:
    argv = sys.argv[1:]
    # `rm -f` / `del /f` 의 의미 보존: 없는 파일은 조용히 넘어간다. 가드가 이 플래그를
    # 항상 경로들 앞에 붙이므로 첫 인자만 본다.
    force = bool(argv) and argv[0] in ("-f", "--force")
    paths = argv[1:] if force else argv

    if not paths:
        print("send_to_trash: 대상 경로가 없어 아무 작업도 하지 않습니다.", file=sys.stderr)
        return 0

    try:
        from send2trash import send2trash
    except ImportError:
        print("BLOCKED: send2trash 모듈이 없어 아무 파일도 삭제하지 않았습니다.", file=sys.stderr)
        print("설치: pip install send2trash", file=sys.stderr)
        return 1

    had_failure = False
    for p in paths:
        if force and not os.path.exists(p):
            continue
        try:
            send2trash(p)
            print(f"🗑️  휴지통으로 이동: {p}")
        except Exception as exc:  # noqa: BLE001 - 사용자에게 그대로 보여줘야 함
            had_failure = True
            print(f"FAILED: {p} ({exc})", file=sys.stderr)

    return 1 if had_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
