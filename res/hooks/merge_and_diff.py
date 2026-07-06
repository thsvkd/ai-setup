#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_and_diff.py — 실제 settings.json 조각을 기존 settings.json에 외과적으로 병합

입력 조각(res/settings.json)은 진짜 Claude Code settings.json 형식이며(SSoT), 훅 command에
{{PY}} / {{HOOKS_DIR}} 자리표시자를 담는다. 이 스크립트가:
  1) 자리표시자를 치환하고 (Windows/POSIX 설치 스크립트 양쪽이 같은 이 로직을 씀),
  2) permissions(allow/deny/ask/defaultMode)와 hooks.* 만 기존 settings.json에 병합하며,
  3) 그 외 최상위 키(model, env, statusLine, 다른 훅 등)는 100% 그대로 보존한다.
예상치 못하게 바뀐 최상위 키가 감지되면 비정상 종료(exit 1)한다.

allow/deny/ask 는 합집합(중복 없이 뒤에 추가), defaultMode 는 덮어쓰기, hooks.* 는
(matcher, 훅 스크립트 파일명 집합) 시그니처로 중복 판정해 없는 것만 추가한다 → 재실행 멱등.

병합 시 기존 settings.json 이 있고 변경이 있으면 <path>.bak.<timestamp> 로 백업한다.
설치 시 manifest_path 를 주면 "우리가 실제로 추가한 allow/deny/ask 항목 + 이전 defaultMode" 를
설치 영수증(매니페스트)으로 기록한다. --uninstall 모드는 그 영수증을 읽어, 설치가 건드린
부분만 정밀하게 되돌린다 (훅 등록 해제 + 우리가 추가한 권한 항목만 제거 + defaultMode 원복).

usage: merge_and_diff.py <fragment.json> <settings_path> <dry_run:0|1> <py_invoke> <hooks_dir> [manifest_path] [hook_files_csv]
       merge_and_diff.py --uninstall <settings_path> <dry_run:0|1> <manifest_path>
"""
import copy
import datetime
import json
import os
import re
import shutil
import sys

PY_RE = re.compile(r'[A-Za-z0-9_.\-]+\.py')

# 스칼라 최상위 설정 키(단일 값). allow/deny 처럼 '없을 때만 추가'하고, 기존 값이 있으면
# 사용자 선택을 그대로 보존한다. uninstall 은 '우리가 실제로 추가한' 키만 정밀 제거한다.
SCALAR_KEYS = ("model", "effortLevel", "language")


def backup_file(path):
    """덮어쓰기 전 타임스탬프 백업을 만든다. 생성한 백업 경로(없으면 None)를 반환."""
    if not os.path.exists(path):
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup = f"{path}.bak.{ts}"
    shutil.copy2(path, backup)
    return backup


def write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def substitute(obj, mapping):
    """조각 안 모든 문자열 값에서 자리표시자를 치환한다 (파싱된 객체 기준이라 JSON 이스케이프는 자동)."""
    if isinstance(obj, str):
        for key, value in mapping.items():
            obj = obj.replace(key, value)
        return obj
    if isinstance(obj, list):
        return [substitute(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: substitute(v, mapping) for k, v in obj.items()}
    return obj


def script_names(entry):
    names = []
    for h in entry.get("hooks", []):
        names.extend(PY_RE.findall(h.get("command", "")))
    return tuple(sorted(names))


def hook_sig(entry):
    return (entry.get("matcher"), script_names(entry))


def merge_list(perms, key, incoming, changes):
    """incoming 을 perms[key] 에 합집합으로 추가하고, 실제로 새로 추가된 항목 목록을 반환."""
    if not incoming:
        return []
    before = list(perms.get(key, []))
    merged = list(before)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    perms[key] = merged
    added = [x for x in merged if x not in before]
    if added:
        changes.append(f"permissions.{key}: +{added}")
    return added


def merge_scalars(existing: dict, fragment: dict, changes: list) -> dict:
    """model/effortLevel/language 를 '없을 때만' 추가한다(기존 값 보존). 실제로 추가한 {키: 값} 을 반환."""
    added = {}
    for key in SCALAR_KEYS:
        if key not in fragment or key in existing:
            continue  # 조각에 없거나, 사용자가 이미 값을 갖고 있으면 건드리지 않는다.
        existing[key] = fragment[key]
        added[key] = fragment[key]
        changes.append(f"{key}: (없음) -> {fragment[key]!r}")
    return added


def merge(existing: dict, fragment: dict):
    """(changes, receipt) 를 반환. receipt 는 uninstall 이 정밀 복원에 쓰는 '설치 영수증'."""
    changes = []
    receipt = {
        "added_allow": [],
        "added_deny": [],
        "added_ask": [],
        "added_scalars": {},
        "default_mode_before": None,
        "default_mode_after": None,
        "default_mode_changed": False,
    }

    receipt["added_scalars"] = merge_scalars(existing, fragment, changes)

    frag_perms = fragment.get("permissions", {})
    if frag_perms:
        perms = existing.setdefault("permissions", {})
        receipt["added_allow"] = merge_list(perms, "allow", frag_perms.get("allow", []), changes)
        receipt["added_deny"] = merge_list(perms, "deny", frag_perms.get("deny", []), changes)
        receipt["added_ask"] = merge_list(perms, "ask", frag_perms.get("ask", []), changes)
        if "defaultMode" in frag_perms:
            old_mode = perms.get("defaultMode")
            new_mode = frag_perms["defaultMode"]
            receipt["default_mode_before"] = old_mode
            receipt["default_mode_after"] = new_mode
            if old_mode != new_mode:
                changes.append(f"permissions.defaultMode: {old_mode!r} -> {new_mode!r}")
                perms["defaultMode"] = new_mode
                receipt["default_mode_changed"] = True
        if "mode" in perms:
            changes.append(f"permissions.mode (잘못된 legacy 키) 제거: {perms['mode']!r}")
            del perms["mode"]

    frag_hooks = fragment.get("hooks", {})
    if frag_hooks:
        hooks = existing.setdefault("hooks", {})
        for event, entries in frag_hooks.items():
            existing_list = hooks.setdefault(event, [])
            existing_sigs = {hook_sig(e) for e in existing_list}
            for entry in entries:
                sig = hook_sig(entry)
                if sig not in existing_sigs:
                    existing_list.append(entry)
                    existing_sigs.add(sig)
                    names = ", ".join(sig[1]) or "(?)"
                    changes.append(f"hooks.{event}: + matcher={entry.get('matcher')!r} ({names})")

    return changes, receipt


def revert_permissions(existing: dict, receipt: dict) -> list:
    """설치 영수증에 기록된, '우리가 추가한' allow/deny 항목만 제거하고 defaultMode 를 원복한다.
    사용자가 원래 갖고 있던 항목은 영수증에 없으므로 건드리지 않는다."""
    changes = []
    perms = existing.get("permissions")
    if not perms:
        return changes

    for key in ("allow", "deny", "ask"):
        added = receipt.get("added_" + key) or []
        if not added or key not in perms:
            continue
        removed = [x for x in perms[key] if x in added]
        if removed:
            perms[key] = [x for x in perms[key] if x not in added]
            changes.append(f"permissions.{key}: -{removed}")
        if not perms[key]:
            del perms[key]

    if receipt.get("default_mode_changed"):
        after = receipt.get("default_mode_after")
        before = receipt.get("default_mode_before")
        # 설치 이후 사용자가 defaultMode 를 또 바꿨다면 건드리지 않는다 (여전히 우리 값일 때만 원복).
        if perms.get("defaultMode") == after:
            if before is None:
                if "defaultMode" in perms:
                    del perms["defaultMode"]
                    changes.append("permissions.defaultMode 제거 (설치 전 값 없음)")
            else:
                perms["defaultMode"] = before
                changes.append(f"permissions.defaultMode: {after!r} -> {before!r}")

    if not perms:
        del existing["permissions"]
    return changes


def revert_scalars(existing: dict, receipt: dict) -> list:
    """설치가 '없어서 새로 추가한' model/effortLevel/language 만 제거한다.
    사용자가 원래 갖고 있던 값(영수증에 없음)이나 설치 후 사용자가 다시 바꾼 값은 건드리지 않는다."""
    changes = []
    added = receipt.get("added_scalars") or {}
    for key, value in added.items():
        # 설치 이후 사용자가 값을 또 바꿨다면 건드리지 않는다 (여전히 우리 값일 때만 제거).
        if key in existing and existing[key] == value:
            del existing[key]
            changes.append(f"{key} 제거 ({value!r})")
    return changes


def remove_hooks(existing: dict, targets: list) -> list:
    """PreToolUse 등 hooks.* 에서, 지정한 스크립트 파일명을 참조하는 항목을 제거한다."""
    changes = []
    hooks = existing.get("hooks", {})
    target_set = set(targets)
    for event in list(hooks.keys()):
        kept = []
        for entry in hooks[event]:
            hit = set(script_names(entry)) & target_set
            if hit:
                changes.append(f"hooks.{event}: - matcher={entry.get('matcher')!r} ({', '.join(sorted(hit))})")
            else:
                kept.append(entry)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if "hooks" in existing and not existing["hooks"]:
        del existing["hooks"]
    return changes


def top_level_diff(before: dict, after: dict):
    preserved, violated = [], []
    for k in before:
        if k in ("permissions", "hooks"):
            continue
        (preserved if after.get(k) == before.get(k) else violated).append(k)
    return preserved, violated


def main_uninstall(argv) -> int:
    if len(argv) != 3:
        print("usage: merge_and_diff.py --uninstall <settings_path> <dry_run> <manifest_path>", file=sys.stderr)
        return 1
    settings_path, dry_run_s, manifest_path = argv
    dry_run = dry_run_s == "1"

    if not os.path.exists(settings_path):
        print("(settings.json 이 없어 되돌릴 것이 없습니다.)")
        return 0

    # 설치 영수증(매니페스트). 없으면(구버전 설치) 훅 등록 해제만 하고 권한은 건드리지 못한다.
    receipt = {}
    hook_files = ["danger_guard.py", "secrets_guard.py"]
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                receipt = json.load(f)
            if receipt.get("hook_files"):
                hook_files = receipt["hook_files"]
        except (OSError, ValueError):
            pass

    with open(settings_path, "r", encoding="utf-8") as f:
        after = json.load(f)

    changes = remove_hooks(after, hook_files)
    changes += revert_permissions(after, receipt)
    changes += revert_scalars(after, receipt)

    print("── 되돌리기 계획 ──────────────────────")
    if changes:
        for c in changes:
            print(f"  • {c}")
    else:
        print("  (되돌릴 것 없음 — 이미 정리됨)")
    print("──────────────────────────────────────")

    if dry_run:
        print(f"🧪 DRY RUN — {settings_path} 에 실제로 쓰지 않았습니다.")
    elif changes:
        backup = backup_file(settings_path)
        if backup:
            print(f"  💾 백업: {backup}")
        # 설치가 settings.json 을 처음 만든 경우, 되돌린 뒤 빈 {} 만 남으면 그 파일도 제거한다.
        if not after and not receipt.get("settings_existed_before", True):
            os.remove(settings_path)
            print(f"✅ 설치 전 없던 settings.json 을 제거했습니다: {settings_path}")
        else:
            write_json(settings_path, after)
            print(f"✅ 설치가 건드린 부분을 되돌렸습니다: {settings_path}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--uninstall":
        return main_uninstall(argv[1:])

    if len(argv) < 5:
        print("usage: merge_and_diff.py <fragment.json> <settings_path> <dry_run> <py_invoke> <hooks_dir> [manifest_path] [hook_files_csv]",
              file=sys.stderr)
        return 1

    fragment_path, settings_path, dry_run_s, py_invoke, hooks_dir = argv[:5]
    manifest_path = argv[5] if len(argv) > 5 else ""
    hook_files_csv = argv[6] if len(argv) > 6 else ""
    dry_run = dry_run_s == "1"

    # 훅 command 경로 구분자를 정슬래시로 통일한다. Windows Python 도 정슬래시 경로를
    # 정상 처리하고, Claude Code 자체도 settings.json 에 정슬래시 Windows 경로를 쓴다
    # (예: statusLine 의 "C:/Users/.../omc-hud.mjs"). 혼합 슬래시를 피해 일관성을 얻는다.
    hooks_dir = hooks_dir.replace("\\", "/")

    with open(fragment_path, "r", encoding="utf-8") as f:
        fragment = json.load(f)
    fragment.pop("_comment", None)
    fragment = substitute(fragment, {"{{PY}}": py_invoke, "{{HOOKS_DIR}}": hooks_dir})

    settings_existed = os.path.exists(settings_path)
    if settings_existed:
        with open(settings_path, "r", encoding="utf-8") as f:
            before = json.load(f)
    else:
        before = {}

    after = copy.deepcopy(before)
    changes, receipt = merge(after, fragment)
    preserved, violated = top_level_diff(before, after)

    print("── 변경 계획 ──────────────────────────")
    if changes:
        for c in changes:
            print(f"  • {c}")
    else:
        print("  (변경 사항 없음 — 이미 최신 상태)")
    if before:
        print(f"── 보존된 기존 최상위 키: {preserved or '(없음)'}")
        if violated:
            print(f"  ⚠️ 예상과 다르게 변경된 키 발견: {violated}")
    print("──────────────────────────────────────")

    if dry_run:
        print(f"🧪 DRY RUN — {settings_path} 에 실제로 쓰지 않았습니다.")
        print("── 병합 결과 미리보기 (AFTER) ──")
        print(json.dumps(after, ensure_ascii=False, indent=2))
    else:
        if changes and settings_existed:
            backup = backup_file(settings_path)
            if backup:
                print(f"  💾 백업: {backup}")
        write_json(settings_path, after)
        print(f"✅ 병합 완료: {settings_path}")

        # 설치 영수증(매니페스트) 기록 — uninstall 이 '건드린 것만' 정밀 복원하는 근거.
        if manifest_path:
            manifest = {
                "version": 1,
                "hooks_dir": hooks_dir,
                "settings_path": settings_path,
                "settings_existed_before": settings_existed,
                "hook_files": [f for f in hook_files_csv.split(",") if f],
            }
            manifest.update(receipt)
            write_json(manifest_path, manifest)

    return 1 if violated else 0


if __name__ == "__main__":
    raise SystemExit(main())
