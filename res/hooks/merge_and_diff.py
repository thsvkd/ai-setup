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


def load_manifest(path):
    """설치 영수증을 읽는다. 없거나 깨졌으면 빈 dict."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fold_receipt(previous: dict, current: dict) -> dict:
    """이전 설치 영수증 위에 이번 병합 결과를 누적한다.

    설치는 멱등이라 두 번째 실행의 merge() 는 "추가한 것이 없다"는 빈 영수증을 낸다.
    그걸 그대로 기록하면 첫 설치가 무엇을 바꿨는지에 대한 기억이 사라져, 이후 --uninstall
    이 권한/defaultMode/스칼라 키를 되돌리지 못한다. 그래서 덮어쓰지 않고 합친다.
    """
    if not previous:
        return current

    folded = dict(current)
    for key in ("added_allow", "added_deny", "added_ask"):
        merged = list(previous.get(key) or [])
        for item in current.get(key) or []:
            if item not in merged:
                merged.append(item)
        folded[key] = merged

    scalars = dict(previous.get("added_scalars") or {})
    scalars.update(current.get("added_scalars") or {})
    folded["added_scalars"] = scalars

    env = dict(previous.get("added_env") or {})
    env.update(current.get("added_env") or {})
    folded["added_env"] = env

    # defaultMode 는 '설치 전 원래 값'이 유일하게 중요하다. 한 번이라도 우리가 바꿨다면
    # 그 최초 값을 계속 들고 간다.
    if previous.get("default_mode_changed"):
        folded["default_mode_before"] = previous.get("default_mode_before")
        folded["default_mode_after"] = current.get("default_mode_after") or previous.get("default_mode_after")
        folded["default_mode_changed"] = True

    return folded


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


def merge_env(existing: dict, fragment: dict, changes: list) -> dict:
    """env 하위의 '우리가 관리하는 키'(예: CLAUDE_CODE_SCROLL_SPEED)를 '없을 때만' 추가한다.
    scalar 와 동일한 철학을 env 한 단계 아래에 적용한다 — env 객체 자체와 사용자의 기존 env
    키/값은 절대 건드리지 않고, 조각에 있는 키 중 대상 env 에 없는 것만 채운다.
    실제로 추가한 {키: 값} 을 반환한다 (uninstall 정밀 복원의 근거)."""
    frag_env = fragment.get("env") or {}
    if not frag_env:
        return {}
    existing_env = existing.get("env")
    if not isinstance(existing_env, dict):
        existing_env = {}
    added = {}
    for key, value in frag_env.items():
        if key in existing_env:
            continue  # 사용자가 이미 값을 갖고 있으면 보존한다.
        existing_env[key] = value
        added[key] = value
        changes.append(f"env.{key}: (없음) -> {value!r}")
    if added:
        existing["env"] = existing_env
    return added


def merge(existing: dict, fragment: dict):
    """(changes, receipt) 를 반환. receipt 는 uninstall 이 정밀 복원에 쓰는 '설치 영수증'."""
    changes = []
    receipt = {
        "added_allow": [],
        "added_deny": [],
        "added_ask": [],
        "added_scalars": {},
        "added_env": {},
        "default_mode_before": None,
        "default_mode_after": None,
        "default_mode_changed": False,
    }

    receipt["added_scalars"] = merge_scalars(existing, fragment, changes)
    receipt["added_env"] = merge_env(existing, fragment, changes)

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


def revert_env(existing: dict, receipt: dict) -> list:
    """설치가 '없어서 새로 추가한' env 키만 제거한다. 사용자가 원래 갖고 있던 env 키/값이나
    설치 후 사용자가 다시 바꾼 값은 건드리지 않는다. env 가 비면 env 객체 자체를 제거한다."""
    changes = []
    added = receipt.get("added_env") or {}
    env = existing.get("env")
    if not added or not isinstance(env, dict):
        return changes
    for key, value in added.items():
        # 설치 이후 사용자가 값을 또 바꿨다면 건드리지 않는다 (여전히 우리 값일 때만 제거).
        if key in env and env[key] == value:
            del env[key]
            changes.append(f"env.{key} 제거 ({value!r})")
    if not env:
        del existing["env"]
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
        # permissions/hooks/env 는 우리가 의도적으로 병합(merge_env 는 env 하위 관리 키만 추가)하므로
        # '예상치 못한 변경' 위반 검사에서 제외한다. 사용자의 기존 env 키/값 보존은 merge_env 가 보장한다.
        if k in ("permissions", "hooks", "env"):
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
    receipt = load_manifest(manifest_path)
    hook_files = [f for f in receipt.get("hook_files") or [] if f and "/" not in f and "\\" not in f]
    if not hook_files:
        hook_files = ["danger_guard.py", "secrets_guard.py"]

    with open(settings_path, "r", encoding="utf-8") as f:
        after = json.load(f)

    changes = remove_hooks(after, hook_files)
    changes += revert_permissions(after, receipt)
    changes += revert_scalars(after, receipt)
    changes += revert_env(after, receipt)

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
        # 재실행(멱등)해도 첫 설치의 기억을 잃지 않도록 이전 영수증 위에 누적한다.
        if manifest_path:
            previous = load_manifest(manifest_path)
            manifest = {
                "version": 1,
                "hooks_dir": hooks_dir,
                "settings_path": settings_path,
                # settings.json 이 원래 있었는지는 '첫 설치' 시점의 사실이어야 한다.
                "settings_existed_before": previous.get("settings_existed_before", settings_existed)
                if previous else settings_existed,
                "hook_files": sorted(
                    set(previous.get("hook_files", []) if previous else [])
                    | {f for f in hook_files_csv.split(",") if f and "/" not in f and "\\" not in f}
                ),
            }
            manifest.update(fold_receipt(previous, receipt))
            write_json(manifest_path, manifest)

    return 1 if violated else 0


if __name__ == "__main__":
    raise SystemExit(main())
