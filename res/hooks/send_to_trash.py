# -*- coding: utf-8 -*-
"""
send_to_trash.py (Windows 전용)
지정된 경로들을 OS 휴지통으로 이동시킨다 (복구 가능한 삭제).
send2trash 가 없거나 오류가 나면 "아무것도 지우지 않고" 실패한다 (fail-closed).
"""
import sys


def main() -> int:
    paths = sys.argv[1:]
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
        try:
            send2trash(p)
            print(f"🗑️  휴지통으로 이동: {p}")
        except Exception as exc:  # noqa: BLE001 - 사용자에게 그대로 보여줘야 함
            had_failure = True
            print(f"FAILED: {p} ({exc})", file=sys.stderr)

    return 1 if had_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
