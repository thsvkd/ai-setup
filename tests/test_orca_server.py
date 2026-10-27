import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "res" / "tools" / "orca_server.py"
spec = importlib.util.spec_from_file_location("orca_server", WORKER)
assert spec and spec.loader
orca_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orca_server)


def test_profile_paths_keep_server_data_and_desktop_client_separate(tmp_path):
    appdata = tmp_path / "Roaming"
    plan = orca_server.profile_paths("win32", tmp_path, appdata=appdata)
    assert plan["server"] == appdata / "orca"
    assert plan["client"] == appdata / "orca-desktop"
    assert plan["server"] != plan["client"]


def test_ready_event_parser_returns_the_requested_scope_and_pairing_url():
    event = {
        "type": "orca_server_ready",
        "runtimeId": "runtime-1",
        "pairing": {"available": True, "scope": "mobile", "url": "orca://pair?code=secret"},
    }
    parsed = orca_server.parse_ready_event(json.dumps(event), expected_scope="mobile")
    assert parsed["scope"] == "mobile"
    assert parsed["url"] == "orca://pair?code=secret"
    assert parsed["runtime_id"] == "runtime-1"


def test_service_log_redacts_pairing_url_qr_and_web_client_url():
    event = {
        "type": "orca_server_ready",
        "runtimeId": "runtime-1",
        "pairing": {
            "available": True,
            "scope": "runtime",
            "url": "orca://pair?code=secret",
            "qr": "qr-secret",
            "webClientUrl": "https://example.invalid/?pair=secret",
        },
    }
    sanitized = orca_server.redact_server_line(json.dumps(event))
    assert "runtime-1" in sanitized
    assert "available" in sanitized
    assert "orca://pair" not in sanitized
    assert "qr-secret" not in sanitized
    assert "example.invalid" not in sanitized
    assert orca_server.redact_server_line("Web client: https://example.invalid/?pair=secret") == "[pairing output redacted]"


def test_service_plan_selects_supported_user_startup_managers(tmp_path):
    assert orca_server.service_plan("win32", tmp_path)["manager"] == "task-scheduler"
    assert orca_server.service_plan("darwin", tmp_path)["manager"] == "launchd"
    assert orca_server.service_plan("linux", tmp_path)["manager"] == "systemd-user"


def test_service_command_keeps_runtime_pairing_enabled_but_not_mobile_scope(tmp_path):
    plan = orca_server.service_plan("win32", tmp_path)
    command = orca_server.service_command(plan, "100.64.1.20")
    assert "--pairing-address" in command
    assert "100.64.1.20" in command
    assert "--mobile-pairing" not in command
    assert "--no-pairing" not in command
    assert orca_server.service_command(plan, "100.64.1.20", port=17679)[2] == "17679"


@pytest.mark.parametrize("plat,marker", [
    ("win32", "LogonTrigger"),
    ("darwin", "RunAtLoad"),
    ("linux", "Restart=always"),
])
def test_service_document_starts_the_runner_at_user_login(tmp_path, plat, marker):
    plan = orca_server.service_plan(plat, tmp_path)
    document = orca_server.service_document(
        plan, tmp_path / "python", tmp_path / "runner.py", tmp_path / "config.json"
    )
    assert marker in document
    assert "runner.py" in document


def test_windows_service_starts_at_boot_without_stored_credentials(tmp_path):
    plan = orca_server.service_plan("win32", tmp_path)
    document = orca_server.service_document(
        plan, tmp_path / "python.exe", tmp_path / "runner.py", tmp_path / "config.json"
    )
    assert "BootTrigger" in document
    assert "S4U" in document


def test_service_runner_uses_server_profile_and_redacts_pairing_output(tmp_path, monkeypatch, capsys):
    calls = []

    class Process:
        stdout = io.StringIO(
            '{"type":"orca_server_ready","pairing":{"available":true,"scope":"runtime",'
            '"url":"orca://pair?code=secret","qr":"secret-qr"}}\n'
        )

        def wait(self):
            return 0

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    monkeypatch.setattr(orca_server.subprocess, "Popen", fake_popen)
    result = orca_server.run_service({
        "cli": "orca.exe",
        "server_profile": str(tmp_path / "orca"),
        "pairing_address": "100.64.1.20",
        "port": 6768,
    })
    assert result == 0
    command, kwargs = calls[0]
    assert command == ["orca.exe", "serve", "--port", "6768", "--pairing-address", "100.64.1.20", "--json"]
    assert kwargs["env"]["ORCA_USER_DATA_PATH"] == str(tmp_path / "orca")
    output = capsys.readouterr().out
    assert "orca://pair" not in output
    assert "secret-qr" not in output


def test_service_runner_persists_live_mobile_offer_for_connected_desktop(tmp_path, monkeypatch, capsys):
    ready = {
        "type": "orca_server_ready",
        "pairing": {
            "available": True,
            "scope": "mobile",
            "url": "orca://pair?code=current-mobile",
        },
    }
    calls = []

    class Process:
        stdout = io.StringIO(json.dumps(ready) + "\n")

        def wait(self):
            return 0

    def fake_popen(command, **kwargs):
        assert "Mobile pairing link: waiting for server startup" in codes_path.read_text(encoding="utf-8")
        calls.append(command)
        return Process()

    if __import__("os").name == "nt":
        monkeypatch.syspath_prepend(str(WORKER.parent))
        import orca_windows
        monkeypatch.setattr(orca_windows, "protect_file", lambda path: None)
    monkeypatch.setattr(orca_server.subprocess, "Popen", fake_popen)
    codes_path = tmp_path / "pairing-codes.txt"
    result = orca_server.run_service({
        "cli": "orca.exe",
        "server_profile": str(tmp_path / "orca"),
        "pairing_address": "100.64.1.20",
        "port": 6768,
        "pairing_scope": "mobile",
        "pairing_codes_path": str(codes_path),
        "desktop_environment_id": "env-1",
    })

    assert result == 0
    assert "--mobile-pairing" in calls[0]
    content = codes_path.read_text(encoding="utf-8")
    assert "Desktop app environment: env-1" in content
    assert "Mobile pairing link: orca://pair?code=current-mobile" in content
    assert "orca://pair" not in capsys.readouterr().out


def test_service_runner_ignores_non_object_json_lines(tmp_path):
    assert not orca_server.save_mobile_pairing_offer(
        {
            "pairing_scope": "mobile",
            "pairing_codes_path": str(tmp_path / "pairing-codes.txt"),
        },
        "[]",
    )


def test_service_bundle_copies_runner_and_never_persists_pairing_codes(tmp_path, monkeypatch):
    local = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    plan = orca_server.service_plan("win32", tmp_path)
    config_path = orca_server.write_service_bundle(
        plan,
        tmp_path / "orca.exe",
        {"server": tmp_path / "Roaming" / "orca", "client": tmp_path / "Roaming" / "orca-desktop"},
        "100.64.1.20",
        tmp_path / "python.exe",
        Path(orca_server.__file__),
    )
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["server_profile"] == str(tmp_path / "Roaming" / "orca")
    assert data["pairing_scope"] == "mobile"
    assert data["pairing_codes_path"] == str(plan["root"] / "pairing-codes.txt")
    assert "orca://pair" not in json.dumps(data).lower()
    assert plan["runner"].is_file()
    assert plan["service"].is_file()


@pytest.mark.parametrize("plat,expected", [
    ("win32", "schtasks.exe"),
    ("darwin", "launchctl"),
    ("linux", "systemctl"),
])
def test_service_registration_uses_a_user_startup_manager(tmp_path, plat, expected):
    commands = orca_server.service_registration_commands(
        orca_server.service_plan(plat, tmp_path), username="user", uid=501
    )
    assert commands[0][0] == expected
    assert all("--force" not in " ".join(command) for command in commands)


def test_install_user_service_reuses_only_its_own_existing_windows_task(tmp_path, monkeypatch):
    plan = orca_server.service_plan("win32", tmp_path)
    calls = []

    plan["service"].parent.mkdir(parents=True, exist_ok=True)
    xml = orca_server.service_document(plan, "python.exe", plan["runner"], plan["root"] / "orca-server.json")
    plan["service"].write_text(xml, encoding="utf-8")
    xml = xml.replace("<ns0:LogonType>", "<ns0:UserId>S-1-5-21-1</ns0:UserId><ns0:LogonType>")
    monkeypatch.setattr(orca_server, "windows_user_sid", lambda: "S-1-5-21-1")

    class Result:
        returncode = 0
        stdout = xml
        stderr = ""

    monkeypatch.setattr(orca_server.subprocess, "run", lambda command, **kwargs: calls.append(command) or Result())
    orca_server.install_user_service(plan)
    assert calls[0][:4] == ["schtasks.exe", "/Query", "/TN", plan["task"]]
    assert calls[1] == ["schtasks.exe", "/Run", "/TN", plan["task"]]


def test_active_managed_windows_task_must_be_enabled(tmp_path, monkeypatch):
    plan = orca_server.service_plan("win32", tmp_path)

    class Result:
        returncode = 0
        stdout = (
            '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
            "<Settings><Enabled>false</Enabled></Settings>"
            "<Actions><Exec><Arguments>{}</Arguments></Exec></Actions></Task>"
        ).format(plan["runner"])

    monkeypatch.setattr(orca_server.subprocess, "run", lambda *args, **kwargs: Result())
    assert not orca_server.managed_user_service_is_registered(plan)


def test_discover_pairing_address_uses_tailscale_even_when_not_on_path(tmp_path, monkeypatch):
    tailscale = tmp_path / "Program Files" / "Tailscale" / "tailscale.exe"
    tailscale.parent.mkdir(parents=True)
    tailscale.write_text("stub")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setattr(orca_server.shutil, "which", lambda name: None)

    class Result:
        returncode = 0
        stdout = "100.101.102.103\n"

    monkeypatch.setattr(orca_server.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(orca_server.socket, "socket", lambda *a, **k: pytest.fail("LAN fallback selected"))
    assert orca_server.discover_pairing_address() == "100.101.102.103"


def test_setup_server_client_orders_pairing_service_and_client_start(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: False)
    monkeypatch.setattr(orca_server, "write_service_bundle", lambda *args: calls.append("bundle") or tmp_path / "config.json")
    def issue_pairings(*args, on_desktop_added=None, on_pairing_started=None):
        calls.append("pair")
        on_pairing_started([])
        on_desktop_added("env-1")
        return {"desktop_environment_id": "env-1"}
    monkeypatch.setattr(orca_server, "issue_pairings", issue_pairings)
    monkeypatch.setattr(orca_server, "save_pairing_codes", lambda *args: calls.append("codes") or tmp_path / "pairing-codes.txt")
    monkeypatch.setattr(orca_server, "install_user_service", lambda *args: calls.append("service"))
    monkeypatch.setattr(orca_server, "managed_user_service_is_registered", lambda *args: True)
    monkeypatch.setattr(orca_server, "wait_for_remote_environment", lambda *args: calls.append("ready"))
    monkeypatch.setattr(orca_server, "wait_for_mobile_pairing_code", lambda *args: calls.append("mobile-code"))
    result = orca_server.setup_server_client(
        "orca.exe", tmp_path, "100.64.1.20", tmp_path / "python.exe", Path(orca_server.__file__), plat="win32"
    )
    assert result["state"] == "configured"
    assert calls == ["pair", "bundle", "codes", "service", "ready", "mobile-code"]


def test_setup_server_client_records_ownership_before_service_readiness_failure(tmp_path, monkeypatch):
    calls = []
    records = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: False)
    def issue_pairings(*args, on_desktop_added=None, on_pairing_started=None):
        on_pairing_started([])
        on_desktop_added("env-1")
        return {"desktop_environment_id": "env-1"}
    monkeypatch.setattr(orca_server, "issue_pairings", issue_pairings)
    monkeypatch.setattr(orca_server, "write_service_bundle", lambda *args: calls.append("bundle"))
    monkeypatch.setattr(orca_server, "save_pairing_codes", lambda *args: calls.append("codes") or tmp_path / "pairing-codes.txt")
    monkeypatch.setattr(orca_server, "install_user_service", lambda *args: calls.append("service"))
    monkeypatch.setattr(orca_server, "managed_user_service_is_registered", lambda *args: True)
    monkeypatch.setattr(orca_server, "wait_for_remote_environment", lambda *args: calls.append("desktop"))
    monkeypatch.setattr(
        orca_server, "wait_for_mobile_pairing_code",
        lambda *args: (_ for _ in ()).throw(RuntimeError("mobile link not ready")),
    )

    def record(value):
        calls.append("record-" + value["state"])
        records.append(dict(value))

    with pytest.raises(RuntimeError, match="mobile link not ready"):
        orca_server.setup_server_client(
            "orca.exe", tmp_path, "100.64.1.20", tmp_path / "python.exe",
            Path(orca_server.__file__), plat="win32", on_record=record,
        )
    assert calls[:5] == ["record-pairing", "record-pairing", "record-pairing", "bundle", "codes"]
    assert calls[1] == "record-pairing"
    assert records[-1]["desktop_environment_id"] == "env-1"
    assert calls.index("record-configuring") < calls.index("service")


def test_setup_server_client_does_not_report_an_active_profile_as_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: True)
    monkeypatch.setattr(orca_server, "write_service_bundle", lambda *args: pytest.fail("active profile modified"))
    with pytest.raises(RuntimeError, match="already active"):
        orca_server.setup_server_client(
            "orca.exe", tmp_path, "100.64.1.20", tmp_path / "python.exe", Path(orca_server.__file__), plat="win32"
        )


def test_setup_server_client_reuses_active_managed_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    plan = orca_server.service_plan("win32", tmp_path)
    runner = Path(plan["runner"])
    runner.parent.mkdir(parents=True)
    runner.write_text("managed runner")
    Path(plan["root"], ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    Path(plan["service"]).parent.mkdir(parents=True, exist_ok=True)
    Path(plan["service"]).write_text(str(runner))
    code_path = Path(plan["root"], "pairing-codes.txt")
    code_path.write_text(
        "Desktop app environment: env-1\n"
        "Mobile pairing link: orca://pair?code=current\n"
    )
    (Path(plan["root"]) / "orca-server.json").write_text(json.dumps({
        "pairing_scope": "mobile",
        "pairing_codes_path": str(code_path),
        "desktop_environment_id": "env-1",
    }))
    record = {
        "state": "configured",
        "server_profile": str(tmp_path / "Roaming" / "orca"),
        "client_profile": str(tmp_path / "Roaming" / "orca-desktop"),
        "desktop_environment_id": "env-1",
        "pairing_codes_path": str(code_path),
        "service_manager": plan["manager"],
        "service_root": str(plan["root"]),
        "service_path": str(plan["service"]),
        "service_task": plan["task"],
    }
    waited = []
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: True)
    monkeypatch.setattr(orca_server, "managed_user_service_is_registered", lambda plan: True)
    monkeypatch.setattr(orca_server, "wait_for_remote_environment", lambda *args: waited.append(args))
    monkeypatch.setattr(orca_server, "issue_pairings", lambda *args: pytest.fail("pairing was repeated"))
    monkeypatch.setattr(orca_server, "write_service_bundle", lambda *args: pytest.fail("service was rewritten"))
    monkeypatch.setattr(orca_server, "install_user_service", lambda *args: pytest.fail("service was reinstalled"))
    result = orca_server.setup_server_client(
        "orca.exe", tmp_path, "100.64.1.20", tmp_path / "python.exe",
        Path(orca_server.__file__), plat="win32", existing_record=record,
    )
    assert result == record
    assert waited and waited[0][1:] == (Path(record["client_profile"]), "env-1")


def test_setup_server_client_resumes_an_interrupted_managed_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    plan = orca_server.service_plan("win32", tmp_path)
    root = Path(plan["root"])
    root.mkdir(parents=True)
    runner = Path(plan["runner"])
    runner.write_text("managed runner")
    (root / ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    Path(plan["service"]).write_text(str(runner))
    codes_path = root / "pairing-codes.txt"
    codes_path.write_text("Mobile pairing link: waiting for server startup\n")
    (root / "orca-server.json").write_text(json.dumps({
        "pairing_scope": "mobile",
        "pairing_codes_path": str(codes_path),
        "desktop_environment_id": "env-1",
    }))
    record = {
        "state": "configuring",
        "server_profile": str(tmp_path / "Roaming" / "orca"),
        "client_profile": str(tmp_path / "Roaming" / "orca-desktop"),
        "desktop_environment_id": "env-1",
        "pairing_codes_path": str(codes_path),
        "service_manager": plan["manager"],
        "service_root": str(root),
        "service_path": str(plan["service"]),
        "service_task": plan["task"],
    }
    calls = []
    states = []
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: False)
    monkeypatch.setattr(orca_server, "managed_user_service_is_registered", lambda *args: True)
    monkeypatch.setattr(orca_server, "install_user_service", lambda *args: calls.append("start"))
    monkeypatch.setattr(orca_server, "wait_for_remote_environment", lambda *args: calls.append("desktop"))
    monkeypatch.setattr(orca_server, "wait_for_mobile_pairing_code", lambda *args: calls.append("mobile"))
    monkeypatch.setattr(orca_server, "issue_pairings", lambda *args: pytest.fail("desktop pairing was repeated"))

    result = orca_server.setup_server_client(
        "orca.exe", tmp_path, "100.64.1.20", tmp_path / "python.exe",
        Path(orca_server.__file__), plat="win32", existing_record=record,
        on_record=lambda item: states.append(item["state"]),
    )

    assert result["state"] == "configured"
    assert calls == ["start", "desktop", "mobile"]
    assert states == ["configuring", "configured"]


def _systemd_service(tmp_path):
    root = tmp_path / "service"
    root.mkdir()
    runner = root / "orca-server-runner.py"
    runner.write_text("runner")
    service = tmp_path / "ai-setup-orca.service"
    service.write_text("ExecStart=python3 " + str(runner))
    (root / ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    return runner, service, {
        "service_root": str(root), "service_path": str(service),
        "service_manager": "systemd-user", "server_profile": str(tmp_path / "orca"),
    }


def test_remove_user_service_stops_its_own_running_service_first(tmp_path, monkeypatch):
    """ai-setup 이 띄운 서버는 제거가 직접 멈춘다. 사용자가 먼저 멈출 필요가 없다."""
    runner, service, record = _systemd_service(tmp_path)
    calls, running = [], {"value": True}

    def run(command, **kwargs):
        calls.append(command[:3])
        if command[:3] == ["systemctl", "--user", "stop"]:
            running["value"] = False
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: running["value"])
    monkeypatch.setattr(orca_server.subprocess, "run", run)
    orca_server.remove_user_service(record)
    assert calls[0] == ["systemctl", "--user", "stop"]
    assert not runner.exists() and not service.exists()


def test_remove_user_service_preserves_a_server_it_does_not_run(tmp_path, monkeypatch):
    """자기 서비스를 멈춰도 서버가 남아 있으면 ai-setup 이 띄운 것이 아니다. 끊지 않고 보존한다."""
    runner, service, record = _systemd_service(tmp_path)
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: True)
    monkeypatch.setattr(orca_server, "STOP_WAIT_SECONDS", 0)
    monkeypatch.setattr(orca_server.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "", ""))
    with pytest.raises(RuntimeError, match="not run by ai-setup"):
        orca_server.remove_user_service(record)
    assert runner.exists() and service.exists()


def test_remove_user_service_reports_a_failed_stop_instead_of_blaming_another_server(tmp_path, monkeypatch):
    runner, service, record = _systemd_service(tmp_path)
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: True)
    monkeypatch.setattr(orca_server.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "Failed to connect to bus"))
    with pytest.raises(RuntimeError, match="Could not stop the ai-setup Orca service"):
        orca_server.remove_user_service(record)
    assert runner.exists() and service.exists()


def test_windows_stop_falls_back_to_the_elevated_task_helper(tmp_path, monkeypatch):
    """승격해 등록한 예약 작업은 일반 권한 schtasks /End 로 멈추지 못할 수 있다."""
    running, operations = {"value": True}, []

    def change(plan, operation):
        operations.append((plan["task"], operation))
        running["value"] = False
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: running["value"])
    monkeypatch.setattr(orca_server, "change_windows_task", change)
    monkeypatch.setattr(orca_server.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "Access is denied"))
    root = tmp_path / "service"
    record = {"service_manager": "task-scheduler", "service_task": "ai-setup Orca Server",
              "server_profile": str(tmp_path / "orca"), "service_root": str(root)}
    orca_server.stop_managed_service(record, root / "orca-server-task.xml")
    assert operations == [("ai-setup Orca Server", "end")]


def test_remove_user_service_deletes_only_its_files_and_keeps_extra_contents(tmp_path, monkeypatch):
    monkeypatch.setattr(orca_server, "change_windows_task", lambda *args: type("Result", (), {"returncode": 0})())
    monkeypatch.setattr(orca_server, "windows_task_matches", lambda *args: True)
    root = tmp_path / "service"
    root.mkdir()
    runner = root / "orca-server-runner.py"
    service = root / "orca-server-task.xml"
    runner.write_text("runner")
    service.write_text(str(runner))
    (root / ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    (root / "orca-server.json").write_text("{}")
    (root / "pairing-codes.txt").write_text("no current link")
    extra = root / "user-notes.txt"
    extra.write_text("keep")
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: False)
    monkeypatch.setattr(
        orca_server.subprocess, "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": str(runner)})(),
    )
    record = {
        "service_root": str(root), "service_path": str(service),
        "service_manager": "task-scheduler", "service_task": "ai-setup Orca Server",
        "server_profile": str(tmp_path / "orca"),
    }

    orca_server.remove_user_service(record)

    assert extra.read_text() == "keep"
    assert root.exists()
    assert not runner.exists()
    assert not service.exists()


def test_remove_user_service_also_removes_what_the_service_left_so_reinstall_is_not_refused(tmp_path, monkeypatch):
    """launchd 로그, 중단된 페어링 파일 쓰기, 헬퍼 import 의 바이트코드가 남으면
    디렉터리가 지워지지 않고 다음 설치가 '소유하지 않은 디렉터리'로 거부한다."""
    monkeypatch.setattr(orca_server, "change_windows_task", lambda *args: type("Result", (), {"returncode": 0})())
    monkeypatch.setattr(orca_server, "windows_task_matches", lambda *args: True)
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda profile: False)
    root = tmp_path / "service"
    root.mkdir()
    runner = root / "orca-server-runner.py"
    service = root / "orca-server-task.xml"
    runner.write_text("runner")
    service.write_text(str(runner))
    (root / ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    (root / "server.log").write_text("log")
    (root / "pairing-codes.txt.tmp").write_text("partial")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "orca_windows.cpython-313.pyc").write_bytes(b"\0")
    monkeypatch.setattr(
        orca_server.subprocess, "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": str(runner)})(),
    )
    orca_server.remove_user_service({
        "service_root": str(root), "service_path": str(service),
        "service_manager": "task-scheduler", "service_task": "ai-setup Orca Server",
        "server_profile": str(tmp_path / "orca"),
    })
    assert not root.exists()


def test_service_runs_python_without_writing_bytecode(tmp_path):
    plan = orca_server.service_plan("linux", tmp_path / "home")
    document = orca_server.service_document(plan, "/usr/bin/python3", plan["runner"], plan["root"] / "orca-server.json")
    assert '"-B"' in document


def test_remove_user_service_rejects_symlink_root(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    (target / ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    root = tmp_path / "service"
    root.symlink_to(target, target_is_directory=True)
    record = {
        "service_root": str(root), "service_path": str(root / "task.xml"),
        "service_manager": "task-scheduler", "service_task": "ai-setup Orca Server",
        "server_profile": str(tmp_path / "orca"),
    }

    with pytest.raises(RuntimeError, match="symbolic link"):
        orca_server.remove_user_service(record)
    assert (target / ".ai-setup-managed").exists()


def test_validate_service_record_rejects_changed_cleanup_paths(tmp_path):
    plan = orca_server.service_plan("win32", tmp_path)
    record = {
        "service_manager": plan["manager"],
        "service_root": str(plan["root"]),
        "service_path": str(plan["service"]),
        "service_task": plan["task"],
        "server_profile": str(tmp_path / "Roaming" / "orca"),
    }
    orca_server.validate_service_record(record, plan, tmp_path / "Roaming" / "orca")
    record["service_root"] = str(tmp_path / "unrelated")
    with pytest.raises(RuntimeError, match="paths changed"):
        orca_server.validate_service_record(record, plan, tmp_path / "Roaming" / "orca")


def test_environment_add_targets_the_separate_desktop_client_profile(tmp_path, monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        result = Result()
        if command[1:3] == ["environment", "list"]:
            result.stdout = '{"ok":true,"result":{"environments":[]}}'
        else:
            result.stdout = '{"ok":true,"result":{"environment":{"id":"env-1"}}}'
        return result

    monkeypatch.setattr(orca_server.subprocess, "run", fake_run)
    environment_id = orca_server.add_remote_environment(
        "orca.exe", tmp_path / "client", "Local server", "orca://pair?code=secret"
    )
    assert environment_id == "env-1"
    command, kwargs = calls[1]
    assert command[:3] == ["orca.exe", "environment", "add"]
    assert "orca://pair?code=secret" in command
    assert kwargs["env"]["ORCA_USER_DATA_PATH"] == str(tmp_path / "client")
    assert kwargs["capture_output"] is True


def test_environment_add_refuses_to_reuse_an_unverified_saved_environment(tmp_path, monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        result = Result()
        result.stdout = '{"ok":true,"result":{"environments":[{"id":"env-existing","name":"Windows server"}]}}'
        return result

    monkeypatch.setattr(orca_server.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="already exists"):
        orca_server.add_remote_environment(
            "orca.exe", tmp_path / "client", "Windows server", "orca://pair?code=secret"
        )
    assert len(calls) == 1
    assert calls[0][1:3] == ["environment", "list"]


def test_open_desktop_client_selects_the_paired_server_environment(tmp_path, monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = '{"ok":true}'
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr(orca_server.subprocess, "run", fake_run)
    orca_server.open_desktop_client("orca.exe", tmp_path / "orca-desktop", "env-1")
    command, kwargs = calls[0]
    assert command == ["orca.exe", "open", "--environment", "env-1"]
    assert kwargs["env"]["ORCA_USER_DATA_PATH"] == str(tmp_path / "orca-desktop")


def test_connect_desktop_client_saves_pairing_then_opens_that_environment(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        orca_server, "add_remote_environment",
        lambda cli, profile, name, url: calls.append(("add", cli, profile, name, url)) or "env-1",
    )
    monkeypatch.setattr(
        orca_server, "open_desktop_client",
        lambda cli, profile, environment_id: calls.append(("open", cli, profile, environment_id)),
    )
    result = orca_server.connect_desktop_client(
        "orca.exe", tmp_path / "orca-desktop", "Windows server", "orca://pair?code=secret"
    )
    assert result == "env-1"
    assert calls == [
        ("add", "orca.exe", tmp_path / "orca-desktop", "Windows server", "orca://pair?code=secret"),
        ("open", "orca.exe", tmp_path / "orca-desktop", "env-1"),
    ]


def test_issue_pairings_registers_desktop_before_stopping_runtime_offer(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(orca_server, "ensure_environment_name_available", lambda *args: calls.append("preflight"))

    def issue(cli, server_profile, address, scope):
        process = scope + "-process"
        calls.append(("issue", server_profile, scope))
        return process, {"scope": scope, "url": "orca://pair?code=" + scope, "runtime_id": "runtime-1"}

    def stop(process):
        calls.append(("stop", process))

    def add(cli, profile, name, url):
        calls.append(("add", profile, name, url))
        return "env-1"

    monkeypatch.setattr(orca_server, "issue_pairing_offer", issue)
    monkeypatch.setattr(orca_server, "stop_server_process", stop)
    monkeypatch.setattr(orca_server, "add_remote_environment", add)
    result = orca_server.issue_pairings(
        "orca.exe", tmp_path / "orca", tmp_path / "orca-desktop", "100.64.1.20", "Windows server"
    )
    assert result["desktop_environment_id"] == "env-1"
    assert calls == [
        "preflight",
        ("issue", tmp_path / "orca", "runtime"),
        ("add", tmp_path / "orca-desktop", "Windows server", "orca://pair?code=runtime"),
        ("stop", "runtime-process"),
    ]


def test_issue_pairings_records_desktop_before_runtime_cleanup_failure(tmp_path, monkeypatch):
    calls = []
    records = []
    monkeypatch.setattr(orca_server, "ensure_environment_name_available", lambda *args: calls.append("preflight"))
    monkeypatch.setattr(
        orca_server, "issue_pairing_offer",
        lambda *args: calls.append("issue") or ("runtime-process", {"url": "orca://pair?code=runtime"}),
    )
    monkeypatch.setattr(
        orca_server, "add_remote_environment",
        lambda *args: calls.append("add") or "env-1",
    )

    def fail_to_stop(process):
        calls.append("stop")
        raise RuntimeError("process did not stop")

    monkeypatch.setattr(orca_server, "stop_server_process", fail_to_stop)
    result = orca_server.issue_pairings(
        "orca.exe", tmp_path / "orca", tmp_path / "orca-desktop", "100.64.1.20",
        "Windows server", on_desktop_added=lambda env_id: records.append(env_id),
    )
    assert result["desktop_environment_id"] == "env-1"
    assert records == ["env-1"]
    assert calls == ["preflight", "issue", "add", "stop"]


def prepare_server_setup(monkeypatch, tmp_path, runtime_active=lambda profile: False):
    events = []
    monkeypatch.setattr(orca_server, "runtime_is_active", runtime_active)
    monkeypatch.setattr(orca_server, "write_service_bundle", lambda *args: events.append("bundle"))
    monkeypatch.setattr(orca_server, "save_pairing_codes", lambda *args: tmp_path / "pairing-codes.txt")
    monkeypatch.setattr(orca_server, "install_user_service", lambda plan: events.append("install"))
    monkeypatch.setattr(orca_server, "managed_user_service_is_registered", lambda plan: True)
    monkeypatch.setattr(orca_server, "wait_for_remote_environment", lambda *args: events.append("desktop-ready"))
    monkeypatch.setattr(orca_server, "wait_for_mobile_pairing_code", lambda *args: events.append("mobile-ready"))
    return events


def test_setup_records_pairing_state_and_environment_before_service_start(tmp_path, monkeypatch):
    events = prepare_server_setup(monkeypatch, tmp_path)

    def issue(*args, on_desktop_added=None, on_pairing_started=None):
        events.append("offer")
        on_pairing_started([])
        on_desktop_added("env-1")
        return {"desktop_environment_id": "env-1"}

    monkeypatch.setattr(orca_server, "issue_pairings", issue)
    records = []
    result = orca_server.setup_server_client(
        "orca.exe", tmp_path, "100.64.1.20", "python", "runner.py", plat="win32",
        on_record=lambda record: records.append(dict(record)),
    )

    assert result["state"] == "configured"
    assert [record["state"] for record in records] == ["pairing", "pairing", "pairing", "configuring", "configured"]
    assert records[0].get("desktop_environment_id") is None
    assert records[2]["desktop_environment_id"] == "env-1"
    assert events.index("bundle") < events.index("install")


def test_setup_keeps_recoverable_pairing_receipt_when_temporary_server_remains_active(tmp_path, monkeypatch):
    active = {"value": False}
    events = prepare_server_setup(monkeypatch, tmp_path, lambda profile: active["value"])

    def issue(*args, on_desktop_added=None, on_pairing_started=None):
        on_pairing_started([])
        on_desktop_added("env-1")
        active["value"] = True
        return {"desktop_environment_id": "env-1"}

    monkeypatch.setattr(orca_server, "issue_pairings", issue)
    records = []
    with pytest.raises(RuntimeError, match="Temporary Orca pairing server is still active"):
        orca_server.setup_server_client(
            "orca.exe", tmp_path, "100.64.1.20", "python", "runner.py", plat="win32",
            on_record=lambda record: records.append(dict(record)),
        )

    assert [record["state"] for record in records] == ["pairing", "pairing", "pairing"]
    assert records[-1]["desktop_environment_id"] == "env-1"
    assert events == []


def test_setup_resumes_pairing_receipt_without_reissuing_desktop_offer(tmp_path, monkeypatch):
    events = prepare_server_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(orca_server, "issue_pairings", lambda *args, **kwargs: pytest.fail("desktop offer reissued"))
    existing = {"state": "pairing", "desktop_environment_id": "env-1"}

    result = orca_server.setup_server_client(
        "orca.exe", tmp_path, "100.64.1.20", "python", "runner.py", plat="win32",
        existing_record=existing,
    )

    assert result["state"] == "configured"
    assert result["desktop_environment_id"] == "env-1"
    assert events == ["bundle", "install", "desktop-ready", "mobile-ready"]


def test_setup_recovers_environment_saved_before_pairing_receipt_id(tmp_path, monkeypatch):
    events = prepare_server_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(orca_server, "issue_pairings", lambda *args, **kwargs: pytest.fail("desktop offer reissued"))
    monkeypatch.setattr(orca_server, "find_new_environment_id", lambda *args: "env-recovered")
    records = []
    existing = {
        "state": "pairing",
        "desktop_environment_name": "host Orca server",
        "client_environment_ids_before_pairing": ["env-old"],
    }

    result = orca_server.setup_server_client(
        "orca.exe", tmp_path, "100.64.1.20", "python", "runner.py", plat="win32",
        existing_record=existing, on_record=lambda record: records.append(dict(record)),
    )

    assert result["desktop_environment_id"] == "env-recovered"
    assert result["state"] == "configured"
    assert records[0]["desktop_environment_id"] == "env-recovered"
    assert events == ["bundle", "install", "desktop-ready", "mobile-ready"]


def test_issue_pairings_preflight_failure_does_not_start_offer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        orca_server, "ensure_environment_name_available",
        lambda *args: (_ for _ in ()).throw(RuntimeError("environment name already exists")),
    )
    monkeypatch.setattr(
        orca_server, "issue_pairing_offer",
        lambda *args: pytest.fail("pairing offer started before name preflight"),
    )
    with pytest.raises(RuntimeError, match="environment name already exists"):
        orca_server.issue_pairings(
            "orca.exe", tmp_path / "orca", tmp_path / "orca-desktop", "100.64.1.20", "Windows server"
        )


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows process handle lifetime')
def test_runtime_probe_ignores_an_exited_windows_process_with_an_open_handle(tmp_path, monkeypatch):
    import subprocess
    import sys

    monkeypatch.setattr(orca_server, 'port_is_listening', lambda: False)
    process = subprocess.Popen([sys.executable, '-c', 'pass'])
    try:
        process.wait(timeout=10)
        (tmp_path / 'orca-runtime.json').write_text(json.dumps({'pid': process.pid}))
        assert orca_server.runtime_is_active(tmp_path) is False
    finally:
        process._handle.Close()


def test_windows_service_registration_does_not_prompt_for_or_store_a_password(tmp_path):
    plan = orca_server.service_plan('win32', tmp_path)
    commands = orca_server.service_registration_commands(plan, username='user')
    assert commands[0] == [
        'schtasks.exe', '/Create', '/TN', 'ai-setup Orca Server', '/XML', str(plan['service']),
        '/RU', 'user', '/NP',
    ]


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows service output encoding')
def test_windows_service_command_can_write_unicode_with_utf8_mode_disabled(tmp_path):
    import os
    import subprocess
    import sys
    from xml.etree import ElementTree

    runner = tmp_path / 'runner.py'
    runner.write_text("print('\\u2014')\n", encoding='utf-8')
    plan = orca_server.service_plan('win32', tmp_path)
    xml = ElementTree.fromstring(orca_server.service_document(plan, sys.executable, runner, tmp_path / 'config.json'))
    ns = {'task': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    executable = xml.findtext('task:Actions/task:Exec/task:Command', namespaces=ns)
    arguments = xml.findtext('task:Actions/task:Exec/task:Arguments', namespaces=ns)
    env = os.environ.copy()
    env['PYTHONUTF8'] = '0'
    env.pop('PYTHONIOENCODING', None)
    result = subprocess.run('"' + executable + '" ' + arguments, env=env, capture_output=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '\u2014'


@pytest.mark.parametrize('existing_client', [False, True])
def test_client_keeps_original_remote_servers_when_profiles_are_split(tmp_path, existing_client):
    server = tmp_path / 'orca'
    client = tmp_path / 'orca-desktop'
    server.mkdir()
    original = {'version': 1, 'environments': [{'id': 'remote-1', 'name': 'old host', 'credential': 'test-only'}]}
    source = server / 'orca-environments.json'
    source.write_text(json.dumps(original))
    if existing_client:
        client.mkdir()
        (client / 'orca-environments.json').write_text(json.dumps({
            'version': 1, 'environments': [{'id': 'local-1', 'name': 'this host'}],
        }))
    assert orca_server.preserve_client_environments(server, client) == 1
    saved = json.loads((client / 'orca-environments.json').read_text())
    assert saved['environments'][-1] == original['environments'][0]
    assert len(saved['environments']) == (2 if existing_client else 1)
    assert json.loads(source.read_text()) == original
    assert orca_server.preserve_client_environments(server, client) == 0


def test_client_environment_migration_does_not_modify_a_running_client(tmp_path):
    server = tmp_path / 'orca'
    client = tmp_path / 'orca-desktop'
    server.mkdir()
    client.mkdir()
    (server / 'orca-environments.json').write_text(json.dumps({'version': 1, 'environments': [{'id': 'remote-1'}]}))
    target = client / 'orca-environments.json'
    target.write_text(json.dumps({'version': 1, 'environments': []}))
    (client / 'orca-runtime.json').write_text('{}')
    before = target.read_bytes()
    with pytest.raises(RuntimeError, match='Close the Orca desktop client'):
        orca_server.preserve_client_environments(server, client)
    assert target.read_bytes() == before


def test_windows_persistent_service_has_no_time_or_battery_stop(tmp_path):
    from xml.etree import ElementTree

    document = ElementTree.fromstring(orca_server.service_document(
        orca_server.service_plan('win32', tmp_path), 'python.exe', 'runner.py', 'config.json',
    ))
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    settings = document.find('t:Settings', ns)
    assert settings.findtext('t:ExecutionTimeLimit', namespaces=ns) == 'PT0S'
    assert settings.findtext('t:DisallowStartIfOnBatteries', namespaces=ns) == 'false'
    assert settings.findtext('t:StopIfGoingOnBatteries', namespaces=ns) == 'false'


def test_windows_remove_queries_task_actions_before_removing(tmp_path, monkeypatch):
    monkeypatch.setattr(orca_server, "change_windows_task", lambda *args: type("Result", (), {"returncode": 0})())
    monkeypatch.setattr(orca_server, "windows_task_matches", lambda *args: True)
    root = tmp_path / 'service'
    root.mkdir()
    runner = root / 'orca-server-runner.py'
    service = root / 'orca-server-task.xml'
    runner.write_text('runner')
    service.write_text(str(runner))
    (root / '.ai-setup-managed').write_text('ai-setup orca server v1\n')
    monkeypatch.setattr(orca_server, 'runtime_is_active', lambda profile: False)
    calls = []

    def native(command, **kwargs):
        calls.append(command)
        output = str(runner) if '/XML' in command else 'TaskName Next Run Time Status'
        return type('Result', (), {'returncode': 0, 'stdout': output})()

    monkeypatch.setattr(orca_server.subprocess, 'run', native)
    orca_server.remove_user_service({
        'service_root': str(root), 'service_path': str(service),
        'service_manager': 'task-scheduler', 'service_task': 'test-task',
        'server_profile': str(tmp_path / 'orca'),
    })
    assert calls[0] == ['schtasks.exe', '/Query', '/TN', 'test-task', '/XML']
    assert not runner.exists()


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows shortcut lifecycle')
def test_desktop_shortcuts_record_ownership_and_preserve_later_user_edits(tmp_path, monkeypatch):
    import subprocess

    cli = tmp_path / 'installation/resources/bin/orca.exe'
    cli.parent.mkdir(parents=True)
    cli.touch()
    executable = cli.parents[2] / 'Orca.exe'
    executable.touch()
    appdata = tmp_path / 'Roaming'
    monkeypatch.setenv('APPDATA', str(appdata))
    paths = [
        appdata / 'Microsoft/Windows/Start Menu/Programs/Orca.lnk',
        appdata / 'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar/Orca.lnk',
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)

    def shortcuts(arguments=None):
        script = r'''
$data=[Console]::In.ReadToEnd()|ConvertFrom-Json
$shell=New-Object -ComObject WScript.Shell
$values=@()
foreach($path in $data.paths){
  $link=$shell.CreateShortcut($path)
  if($null -ne $data.arguments){$link.TargetPath=$data.target;$link.Arguments=$data.arguments;$link.Save()}
  $values+= $link.Arguments
}
$values|ConvertTo-Json -Compress
'''
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            input=json.dumps({'paths': [str(path) for path in paths], 'target': str(executable), 'arguments': arguments}),
            capture_output=True, text=True, encoding='utf-8', check=True)
        return json.loads(result.stdout)

    shortcuts('--enable-logging')
    client = tmp_path / 'orca-desktop'
    orca_server.configure_desktop_shortcuts(cli, client)
    ownership = client / 'ai-setup-desktop-shortcuts.json'
    assert ownership.is_file()
    first = ownership.read_bytes()
    assert all('--user-data-dir=' in value for value in shortcuts())
    orca_server.configure_desktop_shortcuts(cli, client)
    assert ownership.read_bytes() == first
    shortcuts('--user-custom-flag')
    orca_server.configure_desktop_shortcuts(cli, client, restore=True)
    assert shortcuts() == ['--user-custom-flag', '--user-custom-flag']
    assert not ownership.exists()

    shortcuts('--enable-logging')
    orca_server.configure_desktop_shortcuts(cli, client)
    orca_server.configure_desktop_shortcuts(cli, client, restore=True)
    assert shortcuts() == ['--enable-logging', '--enable-logging']
    assert not ownership.exists()


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows native command encoding')
def test_service_registration_reads_native_output_without_utf8_thread_errors(tmp_path, monkeypatch):
    import subprocess
    import sys

    command = [sys.executable, '-c', "import sys;sys.stdout.buffer.write('completed'.encode('ascii')+bytes.fromhex('bfcfb7e1'))"]
    monkeypatch.setattr(orca_server, 'service_registration_commands', lambda *args, **kwargs: [command])
    native_run = subprocess.run
    results = []

    def observe(*args, **kwargs):
        result = native_run(*args, **kwargs)
        results.append(result)
        return result

    monkeypatch.setattr(orca_server.subprocess, 'run', observe)
    orca_server.install_user_service({'manager': 'systemd-user'})
    assert results[0].stdout == 'completed\uc644\ub8cc'


def test_windows_registration_elevates_only_task_creation(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    plan = orca_server.service_plan('win32', tmp_path)
    calls = []
    changes = []

    def native(command, **kwargs):
        calls.append(command)
        assert '/Create' not in command, 'Task creation must use scoped administrator consent'
        return subprocess.CompletedProcess(command, 1 if '/Query' in command else 0, '', '')

    def task_change(plan, operation):
        changes.append(operation)
        return subprocess.CompletedProcess([], 0, '', '')

    monkeypatch.setattr(orca_server.subprocess, 'run', native)
    monkeypatch.setattr(orca_server, 'change_windows_task', task_change, raising=False)
    orca_server.install_user_service(plan)
    assert changes == ['create']
    assert calls[-1] == ['schtasks.exe', '/Run', '/TN', plan['task']]


def test_cancelled_windows_creation_does_not_start_the_task(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    plan = orca_server.service_plan('win32', tmp_path)
    calls = []
    monkeypatch.setattr(orca_server.subprocess, 'run', lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 1, '', ''))
    monkeypatch.setattr(orca_server, 'change_windows_task', lambda *args: subprocess.CompletedProcess([], 1223, '', 'Administrator consent was cancelled'), raising=False)
    with pytest.raises(RuntimeError, match='register'):
        orca_server.install_user_service(plan)
    assert not any('/Run' in command for command in calls)


@pytest.mark.parametrize("field,value", [("Command", "cmd.exe"), ("Arguments", "/c echo runner.py"), ("RunLevel", "HighestAvailable"), ("UserId", "S-1-5-18")])
def test_windows_task_ownership_checks_action_and_principal(tmp_path, monkeypatch, field, value):
    from xml.etree import ElementTree
    plan = orca_server.service_plan("win32", tmp_path)
    plan["service"].parent.mkdir(parents=True, exist_ok=True)
    xml = orca_server.service_document(plan, "python.exe", plan["runner"], plan["root"] / "orca-server.json")
    plan["service"].write_text(xml, encoding="utf-8")
    xml = xml.replace("<ns0:LogonType>", "<ns0:UserId>S-1-5-21-1</ns0:UserId><ns0:LogonType>")
    monkeypatch.setattr(orca_server, "windows_user_sid", lambda: "S-1-5-21-1")
    assert orca_server.windows_task_matches(plan, xml)
    document = ElementTree.fromstring(xml)
    document.find(".//{http://schemas.microsoft.com/windows/2004/02/mit/task}" + field).text = value
    assert not orca_server.windows_task_matches(plan, ElementTree.tostring(document, encoding="unicode"))


def test_windows_failed_query_preserves_files_until_privileged_delete_succeeds(tmp_path, monkeypatch):
    import subprocess
    root = tmp_path / "service"
    root.mkdir()
    runner = root / "orca-server-runner.py"
    service = root / "orca-server-task.xml"
    runner.write_text("runner")
    service.write_text(str(runner))
    (root / ".ai-setup-managed").write_text("ai-setup orca server v1\n")
    monkeypatch.setattr(orca_server, "runtime_is_active", lambda *args: False)
    monkeypatch.setattr(orca_server.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 1, "", "Access denied"))
    monkeypatch.setattr(orca_server, "change_windows_task", lambda *args: subprocess.CompletedProcess([], 5, "", "Access denied"))
    with pytest.raises(RuntimeError, match="preserving"):
        orca_server.remove_user_service({"service_root": str(root), "service_path": str(service), "service_manager": "task-scheduler", "service_task": "fixture", "server_profile": str(tmp_path / "profile")})
    assert runner.exists() and service.exists()
