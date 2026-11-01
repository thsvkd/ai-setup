#!/bin/sh
# ai-setup 의 기능은 모두 jarvis 로 옮겼다(2026-11-01, jarvis docs/2026-10-30-ai-setup-absorption.md).
# 예전 진입점은 아무것도 바꾸지 않고 jarvis 를 안내한 뒤 종료 코드 1 로 끝난다.
echo "ai-setup has moved into jarvis (https://github.com/thsvkd/jarvis); this entry point changes nothing. Install and update from the AI setup screen on the jarvis core home, or from a jarvis checkout run: python3 -m jarvis module setup plan --json (updates: module harness plan --json, hooks: module hooks plan --json, Orca: module orca plan --json, doctor: module doctor status --json, AGENTS.md: python3 -m jarvis agentsmd)." >&2
exit 1
