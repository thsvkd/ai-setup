#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OMC HUD 에 프롬프트 캐시 TTL 을 띄우도록 statusLine 을 외과적으로 고친다.

scripts/setup_omc.sh(.ps1) 가 OMC 플러그인을 설치한 뒤 호출한다.

  1. OMC HUD 래퍼(~/.claude/hud/omc-hud.mjs)가 없으면 플러그인 캐시의 정본 템플릿에서 복사한다.
  2. statusLine 이 없으면 OMC HUD 로 만든다. 다른 statusLine 이 있으면 건드리지 않고 멈춘다.
  3. omc-hud-ttl.mjs 를 복사하고 statusLine.command 앞에 끼운다 — session:NNm 이 cache:NNm 으로 바뀐다.
  4. refreshInterval 이 없으면 넣는다. 입력이 없어도 카운트다운이 흐르게 하기 위해서다.

영수증은 ~/.claude/.claude-code-setup.json 의 "omc_hud" 에 남기고, --uninstall 은 3·4 만 되돌린다.
OMC 플러그인과 그 HUD 자체는 사용자가 쓰는 도구이므로 제거하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "hooks"))
from merge_and_diff import backup_file, load_manifest, write_json  # noqa: E402

MANIFEST_NAME = ".claude-code-setup.json"
TTL_SCRIPT = "omc-hud-ttl.mjs"
REFRESH_SECONDS = 10
PLUGIN_CACHE = Path("plugins") / "cache" / "omc" / "oh-my-claudecode"
PREFIX_RE = re.compile(r'^node "[^"]*' + re.escape(TTL_SCRIPT) + r'" ')


def hud_dir_ref(claude_dir: Path) -> str:
    """statusLine 명령에 넣을 hud 디렉터리 표기. OMC hud 스킬과 같은 규칙을 따른다.

    POSIX 는 기기 사이에서 옮겨도 되도록 $HOME 기반, Windows 는 ~ 가 확장되지 않아 정슬래시 절대 경로.
    """
    if os.name == "nt":
        return (claude_dir / "hud").as_posix()
    return "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hud"


def latest_plugin_root(claude_dir: Path) -> Path | None:
    base = claude_dir / PLUGIN_CACHE
    if not base.is_dir():
        return None
    versions = [p for p in base.iterdir() if re.match(r"^\d+(\.\d+)*$", p.name)]
    if not versions:
        return None
    return max(versions, key=lambda p: tuple(int(x) for x in p.name.split(".")))


def load_settings(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("최상위가 객체가 아닙니다")
    return data


def save(path: Path, data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    backup_file(str(path))
    write_json(str(path), data)


def install(claude_dir: Path, dry_run: bool) -> int:
    settings_path = claude_dir / "settings.json"
    hud = claude_dir / "hud"
    ref = hud_dir_ref(claude_dir)
    try:
        settings = load_settings(settings_path)
    except ValueError as e:
        print(f"❌ {settings_path} 를 파싱할 수 없어 멈춥니다: {e}", file=sys.stderr)
        return 1

    changes = []
    receipt = dict(load_manifest(str(claude_dir / MANIFEST_NAME)).get("omc_hud") or {})

    if not (hud / "omc-hud.mjs").is_file():
        root = latest_plugin_root(claude_dir)
        template = root / "scripts" / "lib" / "hud-wrapper-template.txt" if root else None
        if template and template.is_file():
            changes.append(f"OMC HUD 래퍼 복사: {template} → {hud / 'omc-hud.mjs'}")
            if not dry_run:
                (hud / "lib").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(template, hud / "omc-hud.mjs")
                shutil.copyfile(root / "scripts" / "lib" / "config-dir.mjs", hud / "lib" / "config-dir.mjs")
        elif dry_run:
            changes.append("OMC HUD 래퍼 복사 (플러그인 설치 후 결정)")
        else:
            print("❌ OMC 플러그인 캐시에서 HUD 템플릿을 찾지 못했습니다. 플러그인 설치를 확인하세요.",
                  file=sys.stderr)
            return 1

    status = settings.get("statusLine")
    if not isinstance(status, dict) or not status.get("command"):
        if status:
            print("❌ statusLine 형식을 알 수 없어 멈춥니다. 직접 확인하세요.", file=sys.stderr)
            return 1
        status = {"type": "command", "command": f'node "{ref}/omc-hud.mjs"'}
        settings["statusLine"] = status
        changes.append("statusLine 추가: OMC HUD")
    elif "omc-hud" not in status["command"]:
        print(f"⚠️ statusLine 이 OMC HUD 가 아닙니다 ({status['command']}). 사용자 설정이라 건드리지 않습니다.")
        return 0

    changes.append(f"캐시 TTL 래퍼 복사: {hud / TTL_SCRIPT}")
    if not dry_run:
        hud.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / TTL_SCRIPT, hud / TTL_SCRIPT)

    if not PREFIX_RE.match(status["command"]):
        status["command"] = f'node "{ref}/{TTL_SCRIPT}" ' + status["command"]
        changes.append("statusLine.command 앞에 캐시 TTL 래퍼 연결 (session → cache)")
    if "refreshInterval" not in status:
        status["refreshInterval"] = REFRESH_SECONDS
        receipt["refresh_interval_added"] = True
        changes.append(f"statusLine.refreshInterval = {REFRESH_SECONDS}")

    for c in changes:
        print(f"  • {c}")
    if dry_run:
        print(f"🧪 DRY RUN — {settings_path} 에 실제로 쓰지 않았습니다.")
        return 0
    save(settings_path, settings, dry_run)
    manifest = load_manifest(str(claude_dir / MANIFEST_NAME))
    manifest["omc_hud"] = receipt
    write_json(str(claude_dir / MANIFEST_NAME), manifest)
    print(f"✅ OMC HUD 캐시 TTL 설정 완료: {settings_path}")
    return 0


def uninstall(claude_dir: Path, dry_run: bool) -> int:
    settings_path = claude_dir / "settings.json"
    manifest_path = claude_dir / MANIFEST_NAME
    try:
        settings = load_settings(settings_path)
    except ValueError as e:
        print(f"❌ {settings_path} 를 파싱할 수 없어 멈춥니다: {e}", file=sys.stderr)
        return 1
    manifest = load_manifest(str(manifest_path))
    receipt = manifest.get("omc_hud") or {}

    changes = []
    status = settings.get("statusLine")
    if isinstance(status, dict) and PREFIX_RE.match(status.get("command") or ""):
        status["command"] = PREFIX_RE.sub("", status["command"], count=1)
        changes.append("statusLine.command 에서 캐시 TTL 래퍼 제거")
    if isinstance(status, dict) and receipt.get("refresh_interval_added") and "refreshInterval" in status:
        del status["refreshInterval"]
        changes.append("statusLine.refreshInterval 제거")
    settings_changed = bool(changes)
    ttl = claude_dir / "hud" / TTL_SCRIPT
    if ttl.is_file():
        changes.append(f"{ttl} 삭제")

    for c in changes or ["(되돌릴 것 없음 — 이미 정리됨)"]:
        print(f"  • {c}")
    if dry_run:
        print(f"🧪 DRY RUN — {settings_path} 에 실제로 쓰지 않았습니다.")
        return 0
    if settings_changed:
        save(settings_path, settings, dry_run)
    if ttl.is_file():
        ttl.unlink()
    if "omc_hud" in manifest:
        del manifest["omc_hud"]
        write_json(str(manifest_path), manifest)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--home", default=None)
    args = parser.parse_args(argv)
    home = Path(args.home or os.environ.get("HOME") or os.environ.get("USERPROFILE") or ".")
    claude_dir = home / ".claude"
    if args.uninstall:
        return uninstall(claude_dir, args.dry_run)
    return install(claude_dir, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
