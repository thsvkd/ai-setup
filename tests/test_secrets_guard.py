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


# .env.example 류(자리표시자만 담은 예시/템플릿)는 시크릿이 아니므로 확인 게이트에서 제외한다.
ENV_TEMPLATES = [
    "/proj/.env.example",
    "/proj/.env.sample",
    "/proj/.env.template",
    "/proj/.env.dist",
    "/proj/.env.local.example",     # 중간 세그먼트가 껴도 마지막 확장자로 판정
    "/proj/.env.dev.template",
    "C:\\Users\\u\\project\\.env.example",
    ".env.example",                 # 경로 없이 basename 만 와도 통과
]


@pytest.mark.parametrize("fp", ENV_TEMPLATES)
def test_env_template_files_pass(run_hook, fp):
    d, *_ = run_hook(HOOK, read(fp))
    assert d is None, f"expected pass for env template {fp}"


# 반대로 실제 시크릿을 담는 .env / .env.local / .env.production 은 계속 ask 여야 한다 (회귀 방지).
@pytest.mark.parametrize("fp", ["/proj/.env", "/proj/.env.local", "/proj/.env.production"])
def test_real_env_files_still_ask(run_hook, fp):
    d, *_ = run_hook(HOOK, read(fp))
    assert d == "ask", f"expected ask for real env file {fp}"


def test_write_to_env_example_passes(run_hook):
    # .env.example 을 '수정'하는 것도 블로킹되면 안 된다 (Write/Edit).
    d, *_ = run_hook(HOOK, {"tool_name": "Write", "tool_input": {"file_path": "/x/.env.example"}})
    assert d is None


def test_write_to_env_asks(run_hook):
    d, *_ = run_hook(HOOK, {"tool_name": "Write", "tool_input": {"file_path": "/x/.env"}})
    assert d == "ask"


def test_bash_tool_ignored(run_hook):
    d, *_ = run_hook(HOOK, {"tool_name": "Bash", "tool_input": {"command": "cat .env"}})
    assert d is None
