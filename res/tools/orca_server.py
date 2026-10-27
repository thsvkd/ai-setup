"""Windows and POSIX helpers for pairing an Orca desktop client to its local server."""
import json
import os
import plistlib
import queue
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import getpass
import uuid
from pathlib import Path
from xml.etree import ElementTree


def profile_paths(plat, home, appdata=None, xdg_config_home=None, local_app_data=None):
    home = Path(home)
    if plat == "win32":
        appdata = Path(appdata or os.environ.get("APPDATA") or home / "AppData/Roaming")
        return {"server": appdata / "orca", "client": appdata / "orca-desktop"}
    if plat == "darwin":
        root = home / "Library/Application Support"
    else:
        root = Path(xdg_config_home or os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return {"server": root / "orca", "client": root / "orca-desktop"}


def parse_ready_event(line, expected_scope):
    event = json.loads(line)
    if event.get("type") != "orca_server_ready":
        raise ValueError("Orca server did not emit a ready event")
    pairing = event.get("pairing")
    if not isinstance(pairing, dict) or not pairing.get("available") or not pairing.get("url"):
        raise ValueError("Orca server did not emit a pairing link")
    scope = pairing.get("scope") or "runtime"
    if scope != expected_scope:
        raise ValueError("Orca emitted the wrong pairing scope")
    return {"scope": scope, "url": pairing["url"], "runtime_id": event.get("runtimeId")}


def redact_server_line(line):
    try:
        event = json.loads(line)
    except (TypeError, ValueError):
        if (
            "orca://pair" in line.casefold()
            or "pairing qr" in line.casefold()
            or re.search(r"[?&](?:pair|code|token)=", line, re.IGNORECASE)
        ):
            return "[pairing output redacted]"
        return line
    if event.get("type") == "orca_server_ready":
        pairing = event.get("pairing")
        if isinstance(pairing, dict):
            event["pairing"] = {
                key: value for key, value in pairing.items()
                if key not in {"url", "qr", "webClientUrl"}
            }
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return line


def service_plan(plat, home):
    home = Path(home)
    if plat == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        return {
            "manager": "task-scheduler",
            "root": local / "ai-setup/orca-server",
            "runner": local / "ai-setup/orca-server/orca-server-runner.py",
            "service": local / "ai-setup/orca-server/orca-server-task.xml",
            "task": "ai-setup Orca Server",
        }
    if plat == "darwin":
        root = home / "Library/Application Support/ai-setup/orca-server"
        return {
            "manager": "launchd",
            "root": root,
            "runner": root / "orca-server-runner.py",
            "service": home / "Library/LaunchAgents/com.ai-setup.orca-server.plist",
        }
    root = home / ".local/share/ai-setup/orca-server"
    return {
        "manager": "systemd-user",
        "root": root,
        "runner": root / "orca-server-runner.py",
        "service": home / ".config/systemd/user/ai-setup-orca.service",
    }


def service_command(plan, pairing_address, port=6768, pairing_scope="runtime"):
    command = ["serve", "--port", str(port), "--pairing-address", pairing_address]
    if pairing_scope == "mobile":
        command.append("--mobile-pairing")
    elif pairing_scope != "runtime":
        raise ValueError("Unsupported Orca pairing scope")
    command.append("--json")
    return command


def service_document(plan, python, runner, config):
    manager = plan["manager"]
    # -B: 헬퍼 import 가 서비스 디렉터리에 __pycache__ 를 남기면 제거 뒤 디렉터리가 지워지지 않는다.
    args = ["-B", "-X", "utf8", str(runner), "--run", str(config)]
    if manager == "task-scheduler":
        ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
        tag = lambda name: "{" + ns + "}" + name
        root = ElementTree.Element(tag("Task"), {"version": "1.2"})
        triggers = ElementTree.SubElement(root, tag("Triggers"))
        boot = ElementTree.SubElement(triggers, tag("BootTrigger"))
        ElementTree.SubElement(boot, tag("Delay")).text = "PT30S"
        ElementTree.SubElement(boot, tag("Enabled")).text = "true"
        logon = ElementTree.SubElement(triggers, tag("LogonTrigger"))
        ElementTree.SubElement(logon, tag("Enabled")).text = "true"
        principals = ElementTree.SubElement(root, tag("Principals"))
        principal = ElementTree.SubElement(principals, tag("Principal"), {"id": "Author"})
        ElementTree.SubElement(principal, tag("LogonType")).text = "S4U"
        ElementTree.SubElement(principal, tag("RunLevel")).text = "LeastPrivilege"
        settings = ElementTree.SubElement(root, tag("Settings"))
        ElementTree.SubElement(settings, tag("MultipleInstancesPolicy")).text = "IgnoreNew"
        ElementTree.SubElement(settings, tag("StartWhenAvailable")).text = "true"
        ElementTree.SubElement(settings, tag("ExecutionTimeLimit")).text = "PT0S"
        ElementTree.SubElement(settings, tag("DisallowStartIfOnBatteries")).text = "false"
        ElementTree.SubElement(settings, tag("StopIfGoingOnBatteries")).text = "false"
        restart = ElementTree.SubElement(settings, tag("RestartOnFailure"))
        ElementTree.SubElement(restart, tag("Interval")).text = "PT1M"
        ElementTree.SubElement(restart, tag("Count")).text = "5"
        actions = ElementTree.SubElement(root, tag("Actions"), {"Context": "Author"})
        action = ElementTree.SubElement(actions, tag("Exec"))
        ElementTree.SubElement(action, tag("Command")).text = str(python)
        ElementTree.SubElement(action, tag("Arguments")).text = subprocess.list2cmdline(args)
        ElementTree.SubElement(action, tag("WorkingDirectory")).text = str(plan["root"])
        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)
    if manager == "launchd":
        return plistlib.dumps({
            "Label": "com.ai-setup.orca-server",
            "ProgramArguments": [str(python), *args],
            "RunAtLoad": True,
            "KeepAlive": True,
            "WorkingDirectory": str(plan["root"]),
            "StandardOutPath": str(Path(plan["root"]) / "server.log"),
            "StandardErrorPath": str(Path(plan["root"]) / "server.log"),
        }).decode("utf-8")
    if manager == "systemd-user":
        argv = [str(python), *args]
        quote = lambda value: '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
        return "\n".join([
            "[Unit]",
            "Description=ai-setup Orca remote server",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "ExecStart=" + " ".join(quote(value) for value in argv),
            "Restart=always",
            "RestartSec=30",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ])
    raise ValueError("Unsupported Orca service manager")


def run_service(config):
    env = os.environ.copy()
    env["ORCA_USER_DATA_PATH"] = str(config["server_profile"])
    command = [
        str(config["cli"]),
        *service_command(
            config,
            config["pairing_address"],
            port=config.get("port", 6768),
            pairing_scope=config.get("pairing_scope", "runtime"),
        ),
    ]
    if config.get("pairing_scope") == "mobile" and config.get("pairing_codes_path"):
        write_pairing_codes(
            config["pairing_codes_path"],
            config.get("desktop_environment_id", "unknown"),
            None,
        )
    process = subprocess.Popen(
        command,
        cwd=str(Path.home()),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=os.name != "nt",
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0,
    )
    try:
        for line in process.stdout:
            save_mobile_pairing_offer(config, line)
            print(redact_server_line(line.rstrip("\r\n")), flush=True)
        return process.wait()
    except KeyboardInterrupt:
        stop_server_process(process)
        return 0


def write_pairing_codes(path, desktop_environment_id, mobile_url):
    path = Path(path)
    link = mobile_url or "waiting for server startup"
    content = (
        "Desktop app environment: {}\n"
        "Mobile pairing link: {}\n"
    ).format(desktop_environment_id, link)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    if os.name == "nt":
        from orca_windows import protect_file
        protect_file(temporary)
    temporary.replace(path)
    try:
        if os.name != "nt":
            path.chmod(0o600)
    except OSError:
        if os.name != "nt":
            raise


def save_mobile_pairing_offer(config, line):
    path = config.get("pairing_codes_path")
    if not path or config.get("pairing_scope") != "mobile":
        return False
    try:
        event = json.loads(line)
    except (TypeError, ValueError):
        return False
    if not isinstance(event, dict):
        return False
    pairing = event.get("pairing")
    if (
        event.get("type") != "orca_server_ready"
        or not isinstance(pairing, dict)
        or pairing.get("available") is not True
        or pairing.get("scope") != "mobile"
        or not isinstance(pairing.get("url"), str)
        or not pairing["url"].startswith("orca://pair?")
    ):
        return False
    write_pairing_codes(path, config.get("desktop_environment_id", "unknown"), pairing["url"])
    return True


def service_registration_commands(plan, username=None, uid=None):
    manager = plan["manager"]
    service = str(plan["service"])
    if manager == "task-scheduler":
        return [
            ["schtasks.exe", "/Create", "/TN", plan["task"], "/XML", service,
             "/RU", username or getpass.getuser(), "/NP"],
            ["schtasks.exe", "/Run", "/TN", plan["task"]],
        ]
    if manager == "launchd":
        if uid is None:
            uid = os.getuid()
        return [["launchctl", "bootstrap", "gui/{}".format(uid), service]]
    if manager == "systemd-user":
        unit = Path(service).name
        return [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", unit],
        ]
    raise ValueError("Unsupported Orca service manager")


def windows_user_sid():
    from orca_windows import current_user_sid
    return current_user_sid()


def windows_task_matches(plan, xml):
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    try:
        expected = ElementTree.fromstring(Path(plan["service"]).read_text(encoding="utf-8"))
        actual = ElementTree.fromstring(xml)
        actions = actual.findall("t:Actions/*", ns)
        reference = expected.find("t:Actions/t:Exec", ns)
        if len(actions) != 1 or reference is None or actions[0].tag != reference.tag:
            return False
        for field in ("Command", "Arguments", "WorkingDirectory"):
            if actions[0].findtext("t:" + field, namespaces=ns) != reference.findtext("t:" + field, namespaces=ns):
                return False
        principal = actual.find("t:Principals/t:Principal", ns)
        return (principal is not None
                and principal.findtext("t:UserId", namespaces=ns) == windows_user_sid()
                and principal.findtext("t:RunLevel", default="LeastPrivilege", namespaces=ns) == "LeastPrivilege"
                and principal.findtext("t:LogonType", namespaces=ns) == "S4U")
    except (OSError, ElementTree.ParseError):
        return False


def change_windows_task(plan, operation):
    from orca_windows import change_task
    return change_task(plan, operation)


def install_user_service(plan, username=None, uid=None):
    commands = service_registration_commands(plan, username=username, uid=uid)
    if plan["manager"] == "task-scheduler":
        query = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", plan["task"], "/XML"],
            check=False,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
        if query.returncode == 0:
            if not windows_task_matches(plan, query.stdout):
                raise RuntimeError("A different task already uses the ai-setup Orca service name; preserving it")
            commands = [["schtasks.exe", "/Run", "/TN", plan["task"]]]
    elif plan["manager"] == "launchd":
        label = "com.ai-setup.orca-server"
        target = "gui/{}".format(uid if uid is not None else os.getuid()) + "/" + label
        query = subprocess.run(
            ["launchctl", "print", target],
            check=False,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
        if query.returncode == 0:
            commands = []
    for command in commands:
        if plan["manager"] == "task-scheduler" and "/Create" in command:
            result = change_windows_task(plan, "create")
        else:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True,
                encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="", timeout=60,
            )
        if result.returncode:
            raise RuntimeError(
                "Could not register the ai-setup Orca user service; existing service state was preserved: "
                + (getattr(result, "stderr", "") or "Windows administrator consent or service registration failed").strip()
            )


STOP_WAIT_SECONDS = 30


def stop_managed_service(record, service):
    """ai-setup 이 등록한 서비스만 멈춘다. 다른 런타임은 건드리지 않는다."""
    manager = record["service_manager"]
    if manager == "task-scheduler":
        command = ["schtasks.exe", "/End", "/TN", record["service_task"]]
    elif manager == "launchd":
        command = ["launchctl", "bootout", "gui/{}".format(os.getuid()), str(service)]
    elif manager == "systemd-user":
        command = ["systemctl", "--user", "stop", service.name]
    else:
        raise RuntimeError("Unsupported Orca service manager; preserving its files")
    result = subprocess.run(
        command, check=False, capture_output=True,
        text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="", timeout=60,
    )
    if result.returncode and manager == "task-scheduler":
        # 승격해 등록한 작업은 일반 권한으로 멈추지 못할 수 있다. 등록·삭제와 같은 동의 경로로 다시 시도한다.
        result = change_windows_task({
            "task": record["service_task"], "service": service,
            "runner": Path(record["service_root"]) / "orca-server-runner.py",
        }, "end")
    if result.returncode:
        raise RuntimeError(
            "Could not stop the ai-setup Orca service; preserving it: " + (result.stderr or "").strip()
        )
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while runtime_is_active(record["server_profile"]):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "An Orca server not run by ai-setup is active on this profile; stop it and retry the uninstall"
            )
        time.sleep(1)


def remove_user_service(record):
    root = Path(record["service_root"])
    service = Path(record["service_path"])
    if root.is_symlink() or root.parent.is_symlink() or service.parent.is_symlink():
        raise RuntimeError("Orca service path was replaced with a symbolic link; preserving its files")
    marker = root / ".ai-setup-managed"
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != "ai-setup orca server v1":
        raise RuntimeError("Orca service ownership marker is missing; preserving its files")
    runner = root / "orca-server-runner.py"
    owned_files = (
        runner,
        root / "orca-server.json",
        root / "pairing-codes.txt",
        root / "orca_windows.py",
        # 서비스가 만든 것: launchd 로그, 중단된 페어링 파일 쓰기
        root / "server.log",
        root / "pairing-codes.txt.tmp",
        marker,
        service,
    )
    if any(path.is_symlink() for path in owned_files):
        raise RuntimeError("An ai-setup Orca service file was replaced with a symbolic link; preserving its files")
    if not service.is_file() or str(runner).casefold() not in service.read_text(encoding="utf-8").casefold():
        raise RuntimeError("Orca service definition changed; preserving it")
    # 소유를 확인한 서비스가 돌고 있으면 먼저 멈춘다. 멈춘 뒤에도 남는 서버는 남의 것이라 보존한다.
    if runtime_is_active(record["server_profile"]):
        stop_managed_service(record, service)
    manager = record["service_manager"]
    if manager == "task-scheduler":
        query = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", record["service_task"], "/XML"],
            check=False,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
        if query.returncode == 0 and not windows_task_matches({"service": service}, query.stdout):
            raise RuntimeError("The scheduled task changed; preserving it")
        result = change_windows_task({
            "task": record["service_task"], "service": service,
            "runner": runner, "root": root,
        }, "delete")
        if result.returncode:
            raise RuntimeError("Could not remove the Orca scheduled task; preserving its files: " + result.stderr)
    elif manager == "launchd":
        subprocess.run(
            ["launchctl", "bootout", "gui/{}".format(os.getuid()), str(service)],
            check=False,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
    elif manager == "systemd-user":
        unit = service.name
        result = subprocess.run(
            ["systemctl", "--user", "disable", "--now", unit],
            check=False,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
        if result.returncode:
            raise RuntimeError("Could not stop the ai-setup Orca user service; preserving its files")
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=True,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
    else:
        raise RuntimeError("Unsupported Orca service manager; preserving its files")
    if record.get("cli") and record.get("client_profile"):
        configure_desktop_shortcuts(record["cli"], record["client_profile"], restore=True)
    for path in owned_files:
        if path.exists():
            path.unlink()
    # -B 이전 설치는 헬퍼의 바이트코드를 남겼다. 그 파일만 지운다.
    cache = root / "__pycache__"
    if cache.is_dir() and not cache.is_symlink():
        for compiled in cache.glob("orca_windows.*.pyc"):
            compiled.unlink()
        try:
            cache.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def validate_service_record(record, plan, server_profile):
    expected = {
        "service_manager": plan["manager"],
        "service_root": str(plan["root"]),
        "service_path": str(plan["service"]),
        "server_profile": str(server_profile),
    }
    if plan.get("task"):
        expected["service_task"] = plan["task"]
    if any(record.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Orca service receipt paths changed; preserving its files")


def runtime_is_active(server_profile):
    metadata = Path(server_profile) / "orca-runtime.json"
    try:
        runtime = json.loads(metadata.read_text(encoding="utf-8"))
        pid = int(runtime["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return port_is_listening()
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87 or port_is_listening()
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259 or port_is_listening()  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return port_is_listening()


def port_is_listening(port=6768):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        sock.close()


def discover_pairing_address():
    candidates = [shutil.which("tailscale")]
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if root:
                candidates.append(str(Path(root) / "Tailscale" / "tailscale.exe"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(str(Path(local) / "Programs" / "Tailscale" / "tailscale.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    else:
        candidates.extend(["/usr/bin/tailscale", "/usr/sbin/tailscale"])
    for tailscale in dict.fromkeys(path for path in candidates if path):
        if not Path(tailscale).is_file():
            continue
        result = subprocess.run(
            [tailscale, "ip", "-4"], check=False, capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            address = line.strip()
            if address and not address.startswith("127."):
                return address
    # orca serve 는 바인드 주소를 고를 수 없어 모든 인터페이스에서 수신한다. 기본 경로 IP 로
    # 폴백하면 공인 IP 의 VPS 에서 페어링 토큰 하나로 원격 터미널이 열리므로 Tailscale 에서만 설정한다.
    raise RuntimeError(
        "No Tailscale IPv4 address found. The Orca server listens on every network interface, "
        "so it is only set up over Tailscale: run `tailscale up`, then re-run the installer with --tools orca."
    )


def save_pairing_codes(plan, pairings):
    path = Path(plan["root"]) / "pairing-codes.txt"
    write_pairing_codes(path, pairings["desktop_environment_id"], None)
    return path


def wait_for_remote_environment(cli, client_profile, environment_id, timeout=90):
    deadline = time.monotonic() + timeout
    env = os.environ.copy()
    env["ORCA_USER_DATA_PATH"] = str(client_profile)
    while time.monotonic() < deadline:
        result = subprocess.run(
            [str(cli), "status", "--environment", str(environment_id), "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError):
            payload = {}
        runtime = payload.get("result", {}).get("runtime", {})
        if result.returncode == 0 and payload.get("ok") and runtime.get("reachable") is True:
            return
        time.sleep(2)
    raise RuntimeError("The Orca desktop client could not reach its server")


def wait_for_mobile_pairing_code(path, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            content = ""
        if "Mobile pairing link: orca://pair?" in content:
            return
        time.sleep(2)
    raise RuntimeError("The Orca server did not publish a usable mobile pairing link")


def managed_user_service_is_registered(plan):
    if plan["manager"] == "task-scheduler":
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", plan["task"], "/XML"],
            check=False,
            capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="",
            timeout=30,
        )
        if result.returncode or not windows_task_matches(plan, result.stdout):
            return False
        ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
        try:
            task = ElementTree.fromstring(result.stdout)
        except ElementTree.ParseError:
            return False
        enabled = task.find(".//{{{}}}Settings/{{{}}}Enabled".format(ns, ns))
        return enabled is None or enabled.text is None or enabled.text.casefold() == "true"
    if plan["manager"] == "launchd":
        target = "gui/{}/com.ai-setup.orca-server".format(os.getuid())
        return subprocess.run(
            ["launchctl", "print", target], check=False, capture_output=True,
            text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="", timeout=30,
        ).returncode == 0
    if plan["manager"] == "systemd-user":
        return subprocess.run(
            ["systemctl", "--user", "is-enabled", Path(plan["service"]).name],
            check=False, capture_output=True, text=True, encoding="oem" if os.name == "nt" else "utf-8", errors="replace", input="", timeout=30,
        ).returncode == 0
    return False


def validate_existing_service_bundle(record, plan):
    root = Path(record["service_root"])
    runner = Path(plan["runner"])
    service = Path(record["service_path"])
    marker = root / ".ai-setup-managed"
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != "ai-setup orca server v1":
        raise RuntimeError("Orca service ownership marker is missing; preserving the active server")
    if not service.is_file() or str(runner).casefold() not in service.read_text(encoding="utf-8").casefold():
        raise RuntimeError("Orca service definition changed; preserving the active server")
    try:
        config = json.loads((root / "orca-server.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError("Orca service configuration is missing; preserving the active server")
    if (
        config.get("pairing_scope") != "mobile"
        or config.get("pairing_codes_path") != record.get("pairing_codes_path")
        or config.get("desktop_environment_id") != record.get("desktop_environment_id")
    ):
        raise RuntimeError("Orca service configuration changed; preserving the active server")
    if not Path(record["pairing_codes_path"]).is_file() or not record.get("desktop_environment_id"):
        raise RuntimeError("Orca client setup receipt is incomplete; preserving the active server")


def preserve_client_environments(server_profile, client_profile):
    source = Path(server_profile) / "orca-environments.json"
    target = Path(client_profile) / "orca-environments.json"
    if not source.is_file():
        return 0
    original = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(original, dict):
        raise RuntimeError("Invalid Orca environment file; preserving both profiles")
    saved = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else {
        "version": original.get("version"), "environments": [],
    }
    for data in (original, saved):
        if not isinstance(data, dict) or not isinstance(data.get("environments"), list):
            raise RuntimeError("Invalid Orca environment file; preserving both profiles")
        if any(not isinstance(item, dict) or not item.get("id") for item in data["environments"]):
            raise RuntimeError("Invalid Orca environment entry; preserving both profiles")
    if original.get("version") != saved.get("version"):
        raise RuntimeError("Orca environment file versions differ; preserving both profiles")
    known_ids = {item["id"] for item in saved["environments"]}
    missing = [item for item in original["environments"] if item["id"] not in known_ids]
    if not missing:
        return 0
    if (Path(client_profile) / "orca-runtime.json").exists():
        raise RuntimeError("Close the Orca desktop client before restoring its saved servers")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_name(target.name + ".before-ai-setup-" + uuid.uuid4().hex[:8])
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(target.read_bytes())
    saved["environments"].extend(missing)
    pending = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    pending.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.chmod(0o600)
    os.replace(pending, target)
    return len(missing)

def setup_server_client(
    cli, home, pairing_address, python, source_path, plat=None, existing_record=None,
    on_record=None,
):
    plat = plat or os.sys.platform
    profiles = profile_paths(plat, home)
    plan = service_plan(plat, home)
    runtime_active = runtime_is_active(profiles["server"])
    if isinstance(existing_record, dict) and existing_record.get("state") in ("configured", "configuring"):
        validate_service_record(existing_record, plan, profiles["server"])
        validate_existing_service_bundle(existing_record, plan)
        preserve_client_environments(profiles["server"], profiles["client"])
        if runtime_active and not managed_user_service_is_registered(plan):
            raise RuntimeError("The recorded Orca server service is not registered; preserving the active server")
        record = dict(existing_record)
        record["state"] = "configuring"
        if on_record:
            on_record(record)
        if not runtime_active:
            install_user_service(plan)
        if not managed_user_service_is_registered(plan):
            raise RuntimeError("The recorded Orca server service is not enabled; preserving its files")
        wait_for_remote_environment(
            cli, profiles["client"], record["desktop_environment_id"]
        )
        wait_for_mobile_pairing_code(record["pairing_codes_path"])
        record["state"] = "configured"
        if on_record:
            on_record(record)
        return record
    pairing_resume = (
        isinstance(existing_record, dict)
        and existing_record.get("state") == "pairing"
    )
    if runtime_active:
        raise RuntimeError(
            "Orca server is already active on its original profile; stop it before configuring pairing and retrying"
        )
    preserve_client_environments(profiles["server"], profiles["client"])
    record = {
        "state": "pairing",
        "cli": str(cli),
        "server_profile": str(profiles["server"]),
        "client_profile": str(profiles["client"]),
        "shortcut_receipt_path": str(profiles["client"] / "ai-setup-desktop-shortcuts.json"),
        "service_manager": plan["manager"],
        "service_root": str(plan["root"]),
        "service_path": str(plan["service"]),
        "service_task": plan.get("task"),
        "desktop_environment_name": "{} Orca server ({})".format(
            socket.gethostname(), uuid.uuid4().hex[:8]
        ),
    }
    if pairing_resume:
        record.update(existing_record)
    if pairing_resume and record.get("desktop_environment_id"):
        pairings = {"desktop_environment_id": record["desktop_environment_id"]}
    else:
        if pairing_resume and "client_environment_ids_before_pairing" in record:
            recovered_id = find_new_environment_id(
                cli, profiles["client"], record.get("desktop_environment_name", ""),
                record["client_environment_ids_before_pairing"],
            )
            if recovered_id:
                record["desktop_environment_id"] = recovered_id
                if on_record:
                    on_record(record)
                pairings = {"desktop_environment_id": recovered_id}
            else:
                pairings = None
        else:
            pairings = None
        if pairings is None:
            if on_record and (not pairing_resume or "client_environment_ids_before_pairing" not in record):
                on_record(record)

        def save_desktop_environment(environment_id):
            record["desktop_environment_id"] = environment_id
            if on_record:
                on_record(record)

        def save_pairing_baseline(environments):
            record["client_environment_ids_before_pairing"] = [
                item["id"] for item in environments if isinstance(item, dict) and item.get("id")
            ]
            if on_record:
                on_record(record)

        if pairings is None:
            pairings = issue_pairings(
                cli, profiles["server"], profiles["client"], pairing_address,
                record["desktop_environment_name"], on_desktop_added=save_desktop_environment,
                on_pairing_started=save_pairing_baseline,
            )
    if runtime_is_active(profiles["server"]):
        raise RuntimeError(
            "Temporary Orca pairing server is still active; stop it before starting the persistent server"
        )
    write_service_bundle(
        plan, cli, profiles, pairing_address, python, source_path, pairings
    )
    code_path = save_pairing_codes(plan, pairings)
    record["desktop_environment_id"] = pairings["desktop_environment_id"]
    record["pairing_codes_path"] = str(code_path)
    record["state"] = "configuring"
    if on_record:
        on_record(record)
    install_user_service(plan)
    if not managed_user_service_is_registered(plan):
        raise RuntimeError("The Orca server service was not registered and enabled")
    wait_for_remote_environment(cli, profiles["client"], pairings["desktop_environment_id"])
    wait_for_mobile_pairing_code(code_path)
    record["state"] = "configured"
    if on_record:
        on_record(record)
    return record


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Run the ai-setup Orca server service")
    parser.add_argument("--run", metavar="CONFIG")
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run CONFIG is required")
    try:
        config = json.loads(Path(args.run).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("service config must be an object")
        return run_service(config)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print("Orca server service failed: " + str(error), flush=True)
        return 1


def write_service_bundle(plan, cli, profiles, pairing_address, python, source_path, pairings=None):
    root = Path(plan["root"])
    runner = Path(plan["runner"])
    service = Path(plan.get("service") or root / "ai-setup-orca.service")
    config_path = root / "orca-server.json"
    marker = root / ".ai-setup-managed"
    managed_paths = (root, runner, service, config_path, marker)
    if any(path.is_symlink() for path in managed_paths) or (service.exists() and not marker.exists()):
        raise RuntimeError("Existing Orca service files are not owned by ai-setup; preserving them")
    if root.exists() and not marker.exists() and any(root.iterdir()):
        raise RuntimeError("Existing Orca service directory is not owned by ai-setup; preserving it")
    root.mkdir(parents=True, exist_ok=True)
    service.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "cli": str(cli),
        "server_profile": str(profiles["server"]),
        "pairing_address": pairing_address,
        "port": 6768,
        "pairing_scope": "mobile",
        "pairing_codes_path": str(root / "pairing-codes.txt"),
        "desktop_environment_id": (pairings or {}).get("desktop_environment_id", "unknown"),
    }
    if plan["manager"] == "task-scheduler":
        helper = Path(__file__).with_name("orca_windows.py")
        target = root / helper.name
        if target.is_symlink():
            raise RuntimeError("The Windows helper path changed; preserving it")
        shutil.copyfile(helper, target)
    shutil.copyfile(str(source_path), str(runner))
    runner.chmod(0o700)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    config_path.chmod(0o600)
    service.write_text(
        service_document(plan, python, runner, config_path), encoding="utf-8"
    )
    service.chmod(0o600)
    marker.write_text("ai-setup orca server v1\n", encoding="utf-8")
    marker.chmod(0o600)
    return config_path


def add_remote_environment(cli, client_profile, name, pairing_url):
    env = os.environ.copy()
    env["ORCA_USER_DATA_PATH"] = str(client_profile)
    ensure_environment_name_available(cli, client_profile, name)
    result = subprocess.run(
        [str(cli), "environment", "add", "--name", name, "--pairing-code", pairing_url, "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("Orca could not save the server pairing in the desktop client profile")
    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Orca returned invalid environment registration output") from error
    if not payload.get("ok"):
        raise RuntimeError("Orca could not save the server pairing in the desktop client profile")
    saved = payload.get("result", {})
    environment = saved.get("environment") if isinstance(saved, dict) else None
    environment_id = (
        saved.get("id") or saved.get("environmentId")
        or (environment.get("id") if isinstance(environment, dict) else None)
    )
    if not environment_id:
        raise RuntimeError("Orca did not return the saved server environment ID")
    return environment_id


def list_remote_environments(cli, client_profile):
    env = os.environ.copy()
    env["ORCA_USER_DATA_PATH"] = str(client_profile)
    listed = subprocess.run(
        [str(cli), "environment", "list", "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    if listed.returncode:
        raise RuntimeError("Orca could not inspect saved desktop environments")
    try:
        current = json.loads(listed.stdout)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Orca returned invalid desktop environment data") from error
    if not current.get("ok"):
        raise RuntimeError("Orca could not inspect saved desktop environments")
    environments = current.get("result", {}).get("environments", [])
    if not isinstance(environments, list):
        raise RuntimeError("Orca returned invalid desktop environment data")
    return environments


def ensure_environment_name_available(cli, client_profile, name):
    environments = list_remote_environments(cli, client_profile)
    for saved in environments:
        if isinstance(saved, dict) and saved.get("name") == name:
            raise RuntimeError(
                "An Orca environment named '{}' already exists; preserving it".format(name)
            )
    return environments


def find_new_environment_id(cli, client_profile, name, previous_ids):
    if not name or not isinstance(previous_ids, list):
        return None
    previous = {str(value) for value in previous_ids}
    candidates = [
        item for item in list_remote_environments(cli, client_profile)
        if isinstance(item, dict) and item.get("name") == name
        and item.get("id") and str(item["id"]) not in previous
    ]
    if len(candidates) > 1:
        raise RuntimeError("Multiple new Orca environments match the interrupted pairing; preserving the receipt")
    return str(candidates[0]["id"]) if candidates else None


def configure_desktop_shortcuts(cli, client_profile, restore=False):
    if os.name != "nt" or len(Path(cli).parents) < 3:
        return
    executable = Path(cli).parents[2] / "Orca.exe"
    if not executable.is_file():
        return
    profile = Path(client_profile)
    receipt = profile / "ai-setup-desktop-shortcuts.json"
    if any(path.is_symlink() for path in (profile, receipt, profile / "shortcut-backups")):
        raise RuntimeError("Orca shortcut ownership paths are linked; preserving them")
    script = r'''
$ErrorActionPreference = 'Stop'
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$paths = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Orca.lnk'),
    (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Orca.lnk')
)
$backup = Join-Path $data.profile 'shortcut-backups'
$entries = @()
if (Test-Path -LiteralPath $data.receipt) {
    $owned = Get-Content -LiteralPath $data.receipt -Raw | ConvertFrom-Json
    if ($owned.version -ne 1 -or $owned.executable -ine $data.executable) {
        throw 'Invalid Orca shortcut ownership receipt; preserving shortcuts.'
    }
    $entries = @($owned.shortcuts)
}
if ($data.restore) {
    foreach ($entry in $entries) {
        if ($entry.path -notin $paths -or $entry.target -ine $data.executable -or
            [IO.Path]::GetDirectoryName($entry.backup) -ine $backup) {
            throw 'Orca shortcut receipt paths changed; preserving shortcuts.'
        }
        if (-not (Test-Path -LiteralPath $entry.path)) { continue }
        $shortcut = $shell.CreateShortcut($entry.path)
        if ($shortcut.TargetPath -ieq $entry.target -and $shortcut.Arguments -eq $entry.managedArguments) {
            $shortcut.Arguments = $entry.originalArguments
            $shortcut.Save()
            if (Test-Path -LiteralPath $entry.backup) { Remove-Item -LiteralPath $entry.backup }
        }
    }
    if (Test-Path -LiteralPath $data.receipt) { Remove-Item -LiteralPath $data.receipt }
    exit 0
}
$argument = '--user-data-dir="' + $data.profile + '"'
foreach ($path in $paths) {
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $shortcut = $shell.CreateShortcut($path)
    if ($shortcut.TargetPath -ine $data.executable) { continue }
    if ($shortcut.Arguments.Contains($argument)) { continue }
    if ($shortcut.Arguments -match '--user-data-dir') {
        throw 'An Orca shortcut uses another profile; preserving it.'
    }
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    $backupPath = Join-Path $backup ([Guid]::NewGuid().ToString() + '.lnk')
    Copy-Item -LiteralPath $path -Destination $backupPath
    $managed = ($shortcut.Arguments + ' ' + $argument).Trim()
    $entries = @($entries | Where-Object { $_.path -ine $path })
    $entries += [pscustomobject]@{
        path = $path; target = $shortcut.TargetPath; backup = $backupPath
        originalArguments = $shortcut.Arguments; managedArguments = $managed
    }
    $owned = @{ version = 1; executable = $data.executable; shortcuts = @($entries) }
    $owned | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ($data.receipt + '.tmp') -Encoding UTF8
    Move-Item -LiteralPath ($data.receipt + '.tmp') -Destination $data.receipt -Force
    $shortcut.Arguments = $managed
    $shortcut.Save()
}
'''
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        input=json.dumps({"executable": str(executable), "profile": str(profile),
                         "receipt": str(receipt), "restore": restore}),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Could not configure the Orca desktop shortcuts; existing profiles were preserved")


def open_desktop_client(cli, client_profile, environment_id):
    configure_desktop_shortcuts(cli, client_profile)
    env = os.environ.copy()
    env["ORCA_USER_DATA_PATH"] = str(client_profile)
    result = subprocess.run(
        [str(cli), "open", "--environment", str(environment_id)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError("Orca could not open the desktop client for the paired server")


def connect_desktop_client(cli, client_profile, environment_name, pairing_url):
    environment_id = add_remote_environment(
        cli, client_profile, environment_name, pairing_url
    )
    open_desktop_client(cli, client_profile, environment_id)
    return environment_id


def issue_pairing_offer(cli, server_profile, address, scope, timeout=45, port=6768):
    command = service_command(
        {"manager": "manual"}, address, port=port, pairing_scope=scope
    )
    env = os.environ.copy()
    env["ORCA_USER_DATA_PATH"] = str(server_profile)
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        [str(cli), *command],
        cwd=str(Path.home()),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    lines = queue.Queue()

    def read_output():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Orca did not start in time to issue a pairing link")
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty as error:
                raise RuntimeError("Orca did not start in time to issue a pairing link") from error
            if line is None:
                raise RuntimeError("Orca server did not start; an existing runtime may own this profile")
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if event.get("type") == "orca_server_ready":
                return process, parse_ready_event(line, expected_scope=scope)
    except BaseException:
        stop_server_process(process)
        raise


def stop_server_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(process.pid), "/T"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=15)


def issue_pairings(
    cli, server_profile, client_profile, address, environment_name,
    on_desktop_added=None, on_pairing_started=None,
):
    environments = ensure_environment_name_available(cli, client_profile, environment_name)
    if on_pairing_started:
        on_pairing_started(environments)
    runtime_process, runtime = issue_pairing_offer(cli, server_profile, address, "runtime")
    try:
        environment_id = add_remote_environment(
            cli, client_profile, environment_name, runtime["url"]
        )
        if on_desktop_added:
            on_desktop_added(environment_id)
    finally:
        try:
            stop_server_process(runtime_process)
        except Exception:
            pass
    return {"desktop_environment_id": environment_id}


if __name__ == "__main__":
    raise SystemExit(main())
