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
    "/x/keyboard.py",
    "/x/tokenizer.py",
]


@pytest.mark.parametrize("fp", BENIGN)
def test_benign_files_pass(run_hook, fp):
    d, *_ = run_hook(HOOK, read(fp))
    assert d is None, f"expected pass for {fp}"


# 완화: 이름만으로는 시크릿 여부를 알 수 없는 패턴(`*_secret*`, `*.key`)을 뺐다. 워크스페이스
# 전수 검사에서 이 두 패턴의 히트가 전부 라이브러리·테스트 소스코드였다 — 확인 프롬프트만
# 늘리고 막아주는 건 없었다. 시크릿이 밖으로 새는 방향은 auto mode 분류기가 담당한다.
NAME_ONLY_AMBIGUOUS = [
    "/x/crypto_secretbox.py",       # PyNaCl 바인딩
    "/x/nested_secrets.py",         # pydantic-settings 소스
    "/x/test_secrets_guard.py",     # 이 레포 자신의 테스트 파일
    "/x/api.key",                   # 개인키일 수도, 자막·설정·데이터일 수도 있다
    "/x/subtitles.key",
]


@pytest.mark.parametrize("fp", NAME_ONLY_AMBIGUOUS)
def test_name_only_ambiguous_files_pass(run_hook, fp):
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
