"""secrets_guard.py 정책 테스트."""
import pytest

HOOK = "secrets_guard.py"


def read(fp):
    return {"tool_name": "Read", "tool_input": {"file_path": fp}}


SENSITIVE = [
    "/home/u/.env",
    "/proj/.env.local",
    "/home/u/.ssh/id_rsa",
    "/home/u/.ssh/id_ed25519",
    "/home/u/.ssh/id_ecdsa",
    "/x/server.pem",
    "/x/cert.pfx",
    "/x/creds.p12",
    "/x/AuthKey.p8",
    "/x/key.ppk",
    "/x/app.jks",
    "/x/release.keystore",
    "/x/credentials.json",
    "/x/secrets.yaml",
    "/x/secret.yml",
    "/proj/.npmrc",
    "/home/u/.pypirc",
    "/home/u/.netrc",
    "/home/u/.git-credentials",
    "/x/api.key",
    "/x/db_secret_prod.txt",
    "/home/u/.aws/credentials",
    "C:\\Users\\u\\.aws\\credentials",
    "C:\\Users\\u\\project\\.env",
]


@pytest.mark.parametrize("fp", SENSITIVE)
def test_sensitive_files_ask(run_hook, fp):
    d, *_ = run_hook(HOOK, read(fp))
    assert d == "ask", f"expected ask for {fp}"


BENIGN = [
    "/x/main.py",
    "/x/README.md",
    "/x/config.yaml",
    "/x/data.json",
    "/x/index.ts",
    "/x/keyboard.py",       # 'key' 를 포함하지만 .key 확장자가 아님
    "/x/tokenizer.py",
]


@pytest.mark.parametrize("fp", BENIGN)
def test_benign_files_pass(run_hook, fp):
    d, *_ = run_hook(HOOK, read(fp))
    assert d is None, f"expected pass for {fp}"


def test_write_to_env_asks(run_hook):
    d, *_ = run_hook(HOOK, {"tool_name": "Write", "tool_input": {"file_path": "/x/.env"}})
    assert d == "ask"


def test_bash_tool_ignored(run_hook):
    d, *_ = run_hook(HOOK, {"tool_name": "Bash", "tool_input": {"command": "cat .env"}})
    assert d is None
