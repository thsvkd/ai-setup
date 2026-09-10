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
    # `rm -f` / `del /f` 의 의미 보존: 없는 파일은 조용히 넘어간다. 호출자가 이 플래그를
    # 항상 경로들 앞에 붙이므로 첫 인자만 본다.
    force = bool(argv) and argv[0] in ("-f", "--force")
    paths = argv[1:] if force else argv
    # `--` 뒤는 전부 경로다. `-` 로 시작하는 파일 이름을 옵션으로 오인하지 않게 한다.
    if paths and paths[0] == "--":
        paths = paths[1:]

    if not paths:
        print("send_to_trash: 대상 경로가 없어 아무 작업도 하지 않습니다.", file=sys.stderr)
        return 0

    try:
        from send2trash import send2trash
    except ImportError:
        # 127 은 '휴지통으로 옮길 수단이 없다'는 뜻으로 호출자(rm 셰임)와 약속된 코드다.
        # 셰임은 이 코드를 보고 경고 후 원본 rm 으로 넘긴다 — 아무것도 못 지우게 만드는
        # 쪽이 더 해롭기 때문이다.
        print("send_to_trash: send2trash 모듈이 없어 휴지통으로 옮길 수 없습니다.", file=sys.stderr)
        print("설치: pip install send2trash", file=sys.stderr)
        return 127

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
