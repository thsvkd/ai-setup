#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OMC HUD 에 프롬프트 캐시 TTL 을 띄우도록 statusLine 을 외과적으로 고친다.

scripts/setup_omc.sh(.ps1) 가 OMC 플러그인을 설치한 뒤 호출한다.

  1. statusLine 이 OMC HUD 가 아닌 사용자 설정이면 아무것도 하지 않는다.
  2. OMC HUD 래퍼(~/.claude/hud/omc-hud.mjs)가 없으면 플러그인 캐시의 정본 템플릿에서 복사하고,
     statusLine 이 없으면 OMC HUD 로 만든다.
  3. omc-hud-ttl.mjs 를 복사하고 statusLine.command 앞에 끼운다 — session:NNm 이 cache:NNm 으로 바뀐다.
  4. refreshInterval 이 없으면 넣는다. 입력이 없어도 카운트다운이 흐르게 하기 위해서다.

영수증은 ~/.claude/.claude-code-setup.json 의 "omc_hud" 에 남기고, --uninstall 은 이 설치가
만든 것만 되돌린다. OMC 플러그인 자체와 원래 있던 OMC HUD 는 사용자가 쓰는 도구이므로 남긴다.
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
from merge_and_diff import backup_file, write_json  # noqa: E402

MANIFEST_NAME = ".claude-code-setup.json"
TTL_SCRIPT = "omc-hud-ttl.mjs"
REFRESH_SECONDS = 10
PLUGIN_CACHE = Path("plugins") / "cache" / "omc" / "oh-my-claudecode"
# 우리 접두는 따옴표로 감싼 TTL 스크립트 경로에서 끝난다. 그 앞의 node 실행기 표기는 설치
# 환경마다 다르므로(node / find-node.sh / 절대 경로) 스크립트 경로까지를 한 덩어리로 본다.
PREFIX_RE = re.compile(r'^.*?"[^"]*' + re.escape(TTL_SCRIPT) + r'" ')
HUD_FILES = ("omc-hud.mjs", "lib/config-dir.mjs")


def hud_dir_ref(claude_dir: Path) -> str:
    """statusLine 명령에 넣을 hud 디렉터리 표기.

    POSIX 는 기기 사이에서 옮겨도 되도록 $HOME 기반, Windows 는 ~ 가 확장되지 않아 정슬래시 절대 경로.
    파일은 항상 $HOME/.claude 아래에 쓰므로 CLAUDE_CONFIG_DIR 은 쓰지 않는다 — 가리키는 곳이 달라진다.
    """
    if os.name == "nt":
        return (claude_dir / "hud").as_posix()
    return "$HOME/.claude/hud"


def node_launcher(claude_dir: Path, ref: str) -> str:
    """래퍼를 띄울 node 실행기. PATH 에 node 가 없는 환경(nvm 만 쓰는 셸, Windows GUI)에서도
    OMC HUD 가 뜨던 곳이면 우리 래퍼도 떠야 한다. 그래서 OMC 가 이미 쓰는 탐색 수단을 빌린다."""
    if os.name != "nt" and (claude_dir / "hud" / "find-node.sh").is_file():
        return f'sh "{ref}/find-node.sh"'
    try:
        stored = json.loads((claude_dir / ".omc-config.json").read_text(encoding="utf-8")).get("nodeBinary")
    except (OSError, ValueError, AttributeError):
        stored = None
    if os.name == "nt" and isinstance(stored, str) and stored:
        return f'"{Path(stored).as_posix()}"'
    return "node"


def latest_plugin_root(claude_dir: Path) -> Path | None:
    base = claude_dir / PLUGIN_CACHE
    if not base.is_dir():
        return None
    versions = [p for p in base.iterdir() if re.match(r"^\d+(\.\d+)*$", p.name)]
    if not versions:
        return None
    return max(versions, key=lambda p: tuple(int(x) for x in p.name.split(".")))


def load_json_object(path: Path) -> dict:
    """없으면 {}. 있는데 읽을 수 없으면 ValueError — 호출부는 쓰지 않고 멈춘다."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("최상위가 객체가 아닙니다")
    return data


def install(claude_dir: Path, dry_run: bool) -> int:
    settings_path = claude_dir / "settings.json"
    manifest_path = claude_dir / MANIFEST_NAME
    hud = claude_dir / "hud"
    ref = hud_dir_ref(claude_dir)
    try:
        settings = load_json_object(settings_path)
        manifest = load_json_object(manifest_path)
    except ValueError as e:
        print(f"❌ 설정 파일을 파싱할 수 없어 멈춥니다: {e}", file=sys.stderr)
        return 1

    status = settings.get("statusLine")
    if status is not None and not (isinstance(status, dict) and status.get("command")):
        print("❌ statusLine 형식을 알 수 없어 멈춥니다. 직접 확인하세요.", file=sys.stderr)
        return 1
    if status is not None and "omc-hud" not in status["command"]:
        print(f"⚠️ statusLine 이 OMC HUD 가 아닙니다 ({status['command']}). 사용자 설정이라 건드리지 않습니다.")
        return 0

    before = json.dumps(settings, sort_keys=True)
    receipt = dict(manifest.get("omc_hud") or {})
    changes = []

    if not (hud / "omc-hud.mjs").is_file():
        root = latest_plugin_root(claude_dir)
        sources = [root / "scripts" / "lib" / "hud-wrapper-template.txt",
                   root / "scripts" / "lib" / "config-dir.mjs"] if root else []
        if sources and all(p.is_file() for p in sources):
            changes.append(f"OMC HUD 래퍼 복사: {sources[0]} → {hud / 'omc-hud.mjs'}")
            if not dry_run:
                (hud / "lib").mkdir(parents=True, exist_ok=True)
                for src, name in zip(sources, HUD_FILES):
                    shutil.copyfile(src, hud / name)
                receipt["hud_copied"] = True
        elif dry_run:
            changes.append("OMC HUD 래퍼 복사 (플러그인 설치 후 결정)")
        else:
            print("❌ OMC 플러그인 캐시에서 HUD 템플릿을 찾지 못했습니다. 플러그인 설치를 확인하세요.",
                  file=sys.stderr)
            return 1

    if status is None:
        status = {"type": "command", "command": f'node "{ref}/omc-hud.mjs"'}
        settings["statusLine"] = status
        receipt["statusline_added"] = status["command"]
        receipt.setdefault("settings_created", not settings_path.is_file())
        changes.append("statusLine 추가: OMC HUD")

    changes.append(f"캐시 TTL 래퍼 복사: {hud / TTL_SCRIPT}")
    if not PREFIX_RE.match(status["command"]):
        status["command"] = f'{node_launcher(claude_dir, ref)} "{ref}/{TTL_SCRIPT}" ' + status["command"]
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

    hud.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / TTL_SCRIPT, hud / TTL_SCRIPT)
    # 내용이 같으면 다시 쓰지 않는다 — 재실행마다 .bak 이 쌓이지 않게.
    if json.dumps(settings, sort_keys=True) != before:
        backup_file(str(settings_path))
        write_json(str(settings_path), settings)
    manifest["omc_hud"] = receipt
    write_json(str(manifest_path), manifest)
    print(f"✅ OMC HUD 캐시 TTL 설정 완료: {settings_path}")
    return 0


def uninstall(claude_dir: Path, dry_run: bool) -> int:
    settings_path = claude_dir / "settings.json"
    manifest_path = claude_dir / MANIFEST_NAME
    hud = claude_dir / "hud"
    try:
        settings = load_json_object(settings_path)
        manifest = load_json_object(manifest_path)
    except ValueError as e:
        print(f"❌ 설정 파일을 파싱할 수 없어 멈춥니다: {e}", file=sys.stderr)
        return 1
    receipt = manifest.get("omc_hud") or {}

    changes = []
    status = settings.get("statusLine")
    if isinstance(status, dict):
        if PREFIX_RE.match(status.get("command") or ""):
            status["command"] = PREFIX_RE.sub("", status["command"], count=1)
            changes.append("statusLine.command 에서 캐시 TTL 래퍼 제거")
        # 사용자가 나중에 바꾼 값은 사용자 것이다. 우리가 넣은 값 그대로일 때만 지운다.
        if receipt.get("refresh_interval_added") and status.get("refreshInterval") == REFRESH_SECONDS:
            del status["refreshInterval"]
            changes.append("statusLine.refreshInterval 제거")
        if receipt.get("statusline_added") and status == {"type": "command",
                                                          "command": receipt["statusline_added"]}:
            del settings["statusLine"]
            changes.append("설치가 추가한 statusLine 제거")
    settings_changed = bool(changes)

    files = [hud / TTL_SCRIPT] + ([hud / name for name in HUD_FILES] if receipt.get("hud_copied") else [])
    files = [p for p in files if p.is_file()]
    changes += [f"{p} 삭제" for p in files]

    for c in changes or ["(되돌릴 것 없음 — 이미 정리됨)"]:
        print(f"  • {c}")
    if dry_run:
        print(f"🧪 DRY RUN — {settings_path} 에 실제로 쓰지 않았습니다.")
        return 0

    if settings_changed:
        backup_file(str(settings_path))
        if not settings and receipt.get("settings_created"):
            settings_path.unlink()
        else:
            write_json(str(settings_path), settings)
    for p in files:
        p.unlink()
    for d in (hud / "lib", hud):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    if "omc_hud" in manifest:
        del manifest["omc_hud"]
        if manifest:
            write_json(str(manifest_path), manifest)
        else:
            manifest_path.unlink()
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
