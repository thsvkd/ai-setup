#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
secrets_guard.py — PreToolUse hook (Claude Code, 유저 레벨, Windows/POSIX 공용)
.env, id_rsa, *.pem, credentials.json, .npmrc, ~/.aws/credentials 등 민감해 보이는
파일에 대한 Read / Write / Edit / MultiEdit 시도를 감지하면 "ask" 로 사용자 확인을 요구한다.
(완전 차단이 아니라 확인 요청인 이유: 정당하게 .env 를 편집해야 하는 경우가 많기 때문.
 더 엄격한 정책을 원하면 permissionDecision 을 "deny" 로 바꾸면 된다.)
"""
import sys
import json
import re

# 파일명(경로 끝 basename) 기준으로 민감 파일을 판정한다.
SENSITIVE_RE = re.compile(
    r'(^|[\\/])('
    r'\.env(\.[^\\/]*)?'
    r'|id_rsa(\.pub)?'
    r'|id_dsa(\.pub)?'
    r'|id_ecdsa(\.pub)?'
    r'|id_ed25519(\.pub)?'
    r'|[^\\/]*\.pem'
    r'|[^\\/]*\.pfx'
    r'|[^\\/]*\.p12'
    r'|[^\\/]*\.p8'
    r'|[^\\/]*\.ppk'
    r'|[^\\/]*\.jks'
    r'|[^\\/]*\.keystore'
    r'|credentials\.json'
    r'|secrets?\.ya?ml'
    r'|\.npmrc'
    r'|\.pypirc'
    r'|\.netrc'
    r'|\.git-credentials'
    r'|[^\\/]*_secret[^\\/]*'
    r'|[^\\/]*\.key'
    r')$',
    re.IGNORECASE,
)

# basename 만으로는 너무 흔해서 판정하기 어려운, 잘 알려진 자격증명 경로.
SENSITIVE_PATH_RE = re.compile(
    r'[\\/]\.(aws[\\/]credentials|kube[\\/]config|docker[\\/]config\.json)$',
    re.IGNORECASE,
)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name", "") not in ("Read", "Write", "Edit", "MultiEdit"):
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "") or ""
    if file_path and (SENSITIVE_RE.search(file_path) or SENSITIVE_PATH_RE.search(file_path)):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": f"'{file_path}' 는 자격증명/시크릿 파일로 보입니다. 접근을 계속할까요?",
            }
        }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
