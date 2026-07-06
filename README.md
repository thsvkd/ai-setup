# claude-code-setup

Claude Code를 **더 안전하게** 쓰기 위한 사용자 레벨(user-level) 설정 번들.
위험한 명령을 자동으로 막거나 휴지통 이동으로 치환하는 **가드 훅**, 합리적인 **권한(permissions)**,
그리고 프로젝트용 **AGENTS.md**를 Windows / macOS / Linux에 한 번에 설치한다.

- 🛡️ **가드 훅** — `rm`을 휴지통 이동으로 치환, `git push --force`·`git reset --hard`·디스크 포맷·`curl | bash` 등 되돌릴 수 없는 명령을 차단, 시크릿 파일 접근 시 확인 요청
- 🧩 **외과적 병합** — 권한/훅을 추가하고 `model`·`effortLevel`·`language`는 **없을 때만** 채운다. 사용자가 이미 고른 값과 그 외 키(env, statusLine 등)는 **100% 보존**
- 🔁 **멱등성 · dry-run** — 몇 번을 실행해도 안전하고, `--dry-run`으로 실제 적용 전에 바뀔 내용을 미리 확인
- 🖥️ **크로스 플랫폼** — Windows(PowerShell)와 POSIX(bash) 양쪽을 단일 소스로 관리

> ⚠️ **범위 주의**: 훅과 권한은 `~/.claude`(유저 레벨)에 설치되어 **이 사용자가 여는 모든 프로젝트**에 적용된다. 특정 프로젝트에만 적용되는 게 아니다.

---

## 빠른 시작

### 🔐 비공개 레포 인증 (이 저장소는 private)

이 저장소는 **비공개(private)** 이므로 원격 설치 명령에는 GitHub 인증이 필요하다.
인증 없이 실행하면 raw URL 과 아카이브 다운로드가 모두 **404 (Not Found)** 로 실패한다.

설치 스크립트는 환경변수 `GITHUB_TOKEN`(또는 `GH_TOKEN`)이 있으면 레포 아카이브를 자동으로
인증해서 받는다. 부트스트랩 파일 자체(`install.ps1`/`install.sh`)를 받을 때만 아래처럼 헤더로
토큰을 넘겨주면 된다.

**토큰 준비 — `gh` CLI 를 쓰고 있다면 이게 가장 안전하다 (평문 저장 없이 keyring 에서 그때그때 읽음):**

```powershell
# Windows PowerShell — 현재 세션
$env:GITHUB_TOKEN = gh auth token
```
```sh
# POSIX — 현재 세션
export GITHUB_TOKEN="$(gh auth token)"
```

`gh` 없이 PAT 을 직접 발급하려면 **classic 은 `repo` 스코프**, **fine-grained 는 대상 레포 Contents: Read** 권한이면 된다. 그 값을 위 변수에 넣는다.

**영구 저장 (새 세션마다 자동):**

```powershell
# Windows — 사용자 환경변수(레지스트리). 새 세션부터 적용
[Environment]::SetEnvironmentVariable('GITHUB_TOKEN', (gh auth token), 'User')
# 또는 프로필($PROFILE)에 아래 한 줄 — 매 세션 keyring 에서 읽어와 평문 파일에 토큰이 안 남아 더 안전
#   $env:GITHUB_TOKEN = gh auth token
```
```sh
# POSIX — ~/.bashrc 또는 ~/.zshrc 에 추가
export GITHUB_TOKEN="$(gh auth token)"
```

> ⚠️ 사용자 환경변수·셸 프로필에 PAT 문자열을 **직접** 박아두면 평문으로 저장된다. 가능하면 위처럼 `gh auth token` 으로 keyring 에서 읽어오는 방식을 권장한다. 아래 모든 명령은 `GITHUB_TOKEN` 이 설정돼 있다고 가정한다.

### 전역 가드/권한만 설치 (권장 시작점)

어느 위치에서 실행해도 됩니다. `~/.claude`에만 설치됩니다.

**macOS / Linux / Git Bash**
```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --hooks
```

**Windows PowerShell**
```powershell
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
& ([scriptblock]::Create((irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -Hooks
```

### 먼저 미리보기 (아무것도 바꾸지 않음)

```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --dry-run
```
```powershell
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
& ([scriptblock]::Create((irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -DryRun
```

### 전체 설치 (가드/권한 + 현재 폴더에 AGENTS.md)

`AGENTS.md`는 **현재 작업 디렉터리**에 설치되므로, 프로젝트 루트에서 실행하세요.

```sh
cd my-project
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh
```
```powershell
cd my-project
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1 | iex
```

> 인자를 주지 않으면 **가드/권한 + AGENTS.md**가 모두 설치됩니다. PowerShell에서 `irm | iex`는 인자를 넘기기 어려우므로, 플래그가 필요할 땐 위의 `scriptblock` 형태를 쓰세요.

---

## 무엇이 설치되나

| 위치 | 내용 |
| --- | --- |
| `~/.claude/hooks/danger_guard.py` | 위험 명령 가드 (Bash·PowerShell 툴) |
| `~/.claude/hooks/secrets_guard.py` | 시크릿 파일 접근 가드 (Read·Write·Edit) |
| `~/.claude/hooks/send_to_trash.py` | (Windows) 휴지통 이동 헬퍼 |
| `~/.claude/settings.json` | 권한 + PreToolUse 훅 등록 + `model`/`effortLevel`/`language` 기본값(없을 때만) (**기존 키는 보존**) |
| `./AGENTS.md` | (`--agentsmd` 시) 현재 폴더에 프로젝트 워크플로 규칙 — 이미 있으면 건너뜀 |

### settings.json에 병합되는 것

- `permissions.defaultMode: "auto"`
- `permissions.allow` — `Bash`, `PowerShell`, `Read(*)`, `Edit(*)`, `Write(*)`, `Agent(*)`, `WebFetch(*)` 등 핵심 툴
- `permissions.deny` — `git push`, `git reset --hard` (Bash·PowerShell 모두)
- `hooks.PreToolUse` — `danger_guard` / `secrets_guard` 등록
- `model: "opus"`, `effortLevel: "xhigh"`, `language: "korean"` — **없을 때만** 추가한다(사용자가 이미 값을 갖고 있으면 그대로 보존). `allow`/`deny` 와 같은 union 철학이라, `--uninstall`은 우리가 실제로 추가한 키만 되돌린다.

그 외 최상위 키(`env`, `statusLine`, 다른 훅 등)와 사용자가 이미 고른 `model`/`effortLevel`/`language`는 **건드리지 않는다**. 단일 소스는 [`res/settings.json`](res/settings.json)이며, 설치 시 python 실행 명령과 훅 경로만 치환된다.

---

## 가드 정책

### danger_guard — 위험 명령

| 명령 | 조치 |
| --- | --- |
| `rm`, `del`, `Remove-Item`, `rd`, `rmdir` | 🗑️ 휴지통 이동으로 **치환** (send2trash / trash-put) |
| ↳ 드라이브·홈 루트 삭제 (`C:\`, `/`, `~`) | ⛔ **차단** |
| ↳ 휴지통 도구 미설치 / 여러 줄 스크립트에 섞임 | ⛔ **차단** (fail-closed) |
| `git push`, `git push --force` | ⛔ **차단** (수동 실행 요구) |
| `git reset --hard`, `git clean -f*`, `git stash drop`/`clear` | ⛔ **차단** |
| `git branch -D`, `git checkout -- <경로>`, `git restore` | ❓ **확인** |
| `format` / `diskpart` / `mkfs` / `fdisk` / `parted` / `wipefs` / `Clear-Disk` / `Format-Volume` / `diskutil eraseDisk` / `dd of=` | ⛔ **차단** |
| `/dev/sd*` 등 블록 디바이스로의 리다이렉트, 포크밤 `:(){ :\|:& };:` | ⛔ **차단** |
| `curl … \| bash`, `irm … \| iex` (원격 출력을 셸로 파이프) | ⛔ **차단** |
| `shutdown` / `reboot` / `Restart-Computer`, `chmod 777`, `shred`, `Clear-Content`, `reg delete` | ❓ **확인** |
| 그 외 | ✅ 통과 (판단 안 함) |

`sudo <명령>`은 접두어를 벗겨 실제 명령을 위 규칙으로 검사한다. 모든 판정은 `~/.claude/hooks/guard.log`에 감사 기록으로 남는다.

### secrets_guard — 시크릿 파일

`.env`, `id_rsa`/`id_dsa`/`id_ecdsa`/`id_ed25519`, `*.pem`/`*.pfx`/`*.p12`/`*.p8`/`*.ppk`/`*.jks`/`*.keystore`,
`credentials.json`, `secrets.y(a)ml`, `.npmrc`/`.pypirc`/`.netrc`/`.git-credentials`, `~/.aws/credentials`, `*_secret*`, `*.key` 등을
**Read / Write / Edit / MultiEdit**로 접근하면 ❓ 확인을 요청한다. (완전 차단이 아니라, 정당한 편집을 위해 확인 게이트)

---

## 사용법 (플래그)

`setup`은 디스패처이고, 인자에 따라 하위 작업을 골라 실행한다. **인자가 없으면 전부 실행**한다.

| 플래그 (POSIX / PowerShell) | 동작 |
| --- | --- |
| `--hooks` / `-Hooks` | 가드 훅 + 권한만 설치 (전역, `~/.claude`) |
| `--agentsmd` / `-AgentsMd` | 현재 폴더에 `AGENTS.md`만 설치 |
| `--uninstall` / `-Uninstall` | **설치가 건드린 것만 정밀 복원** — 훅 제거 + 우리가 추가한 allow/deny·defaultMode·`model`/`effortLevel`/`language` 원복 (사용자가 원래 갖고 있던 설정은 보존, 백업 후) |
| `--dry-run` / `-DryRun` | 아무것도 바꾸지 않고 변경 계획만 출력 |
| `--help` / `-Help` | 도움말 |
| (없음) | 위 설치를 모두 수행 |

> 설치는 **멱등**하다 — 여러 번 실행해도 훅이 중복 등록되지 않는다. `settings.json`을 바꿀 땐 항상 `settings.json.bak.<타임스탬프>`로 백업하고, 설치 내역은 `~/.claude/.claude-code-setup.json` 매니페스트에 기록되어 `--uninstall`이 참조한다.

### 레포를 clone 해서 직접 실행

```sh
git clone https://github.com/thsvkd/claude-code-setup.git
cd claude-code-setup
bash scripts/setup.sh --dry-run      # 미리보기
bash scripts/setup.sh --hooks        # 전역 가드/권한
```
```powershell
git clone https://github.com/thsvkd/claude-code-setup.git
cd claude-code-setup
.\scripts\setup.ps1 -DryRun
.\scripts\setup.ps1 -Hooks
```

---

## 보안 고려사항

### `CLAUDE_SETUP_REPO` / `CLAUDE_SETUP_REF` 환경변수

`CLAUDE_SETUP_REPO` 환경변수를 설정하면 지정한 레포의 스크립트를 다운로드해 **그대로 실행**한다.
이 변수를 신뢰할 수 없는 입력(CI 파이프라인 환경변수, 공유 환경 등)에서 제어할 수 있으면
**임의 코드 실행(RCE)** 으로 이어질 수 있다.

> ⚠️ **주의**: `CLAUDE_SETUP_REPO` 와 `CLAUDE_SETUP_REF` 는 **신뢰된 환경에서만** 설정하라.
> 공유 CI 환경에서는 이 변수를 외부에서 덮어쓸 수 없도록 접근을 제한해야 한다.

---

## 요구사항

- **Python 3** (필수 — 훅과 병합 엔진이 사용)
- **POSIX**: `bash`, `trash-cli`(자동 설치 시도 — 없으면 `rm` 계열이 **차단**됨)
- **Windows**: `send2trash`(pip로 자동 설치 시도 — 없으면 `rm`/`del` 계열이 **차단**됨)

> `auto` 모드는 계정/버전 자격 요건(플랜·모델·Claude Code 버전)을 충족해야 실제로 켜진다. 설치 후 세션에서 `Shift+Tab`으로 모드를 순환시켜 확인할 수 있다.

---

## 저장소 구조

```
res/
  AGENTS.md                 # 배포될 프로젝트 워크플로 규칙
  settings.json             # 실제 settings.json 조각 (SSoT, {{PY}}·{{HOOKS_DIR}} 자리표시자)
  hooks/
    danger_guard.windows.py # Windows용 (Bash + PowerShell)
    danger_guard.posix.py   # macOS/Linux용 (Bash)
    secrets_guard.py        # 공용
    send_to_trash.py        # Windows 휴지통 헬퍼
    merge_and_diff.py       # 자리표시자 치환 + 외과적 병합 엔진
scripts/
  setup.{ps1,sh}            # CLI 디스패처 (엔트리포인트)
  setup_hooks.{ps1,sh}      # 가드 훅 + 권한 설치 / uninstall 워커
  setup_agentsmd.{ps1,sh}   # AGENTS.md 설치 워커
  lib/                      # 공용 오케스트레이션 함수
install.{ps1,sh}            # 원격 설치 부트스트랩 (curl | sh / irm | iex)
tests/                      # pytest(훅·병합) + bats(bash) + Pester(PowerShell)
```

---

## 개발 · 테스트

가드 훅과 병합 엔진은 블랙박스로 테스트한다 (JSON을 stdin으로 넣고 판정을 검증).

```sh
python -m pytest tests/                 # 훅 정책 + 병합 엔진 (Python)
bats tests/setup.bats                    # 셋업 스크립트 (bash, bats-core 필요)
```
```powershell
Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed   # 셋업 스크립트 (PowerShell)
```

---

## 되돌리기

`setup.sh --uninstall` / `setup.ps1 -Uninstall`은 **설치가 건드린 부분만 정밀하게 되돌린다**.
설치 시 기록해둔 영수증(`~/.claude/.claude-code-setup.json`)을 근거로, 우리가 추가한 훅·allow/deny 항목과
우리가 새로 넣은 `model`/`effortLevel`/`language`만 제거하고 `defaultMode`를 이전 값으로 원복하며(설치 이후 사용자가 또 바꿨다면 건드리지 않음), 훅 파일·guard.log·매니페스트를
지운다. 설치가 `settings.json`을 처음 만든 경우 되돌린 뒤 비면 그 파일도 제거한다. 사용자가 원래 갖고 있던 설정과
그 외 모든 키는 그대로 보존되고, 변경 전 `.bak`을 남긴다. 원격에서 바로 실행하려면:

```sh
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --uninstall
```
```powershell
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
& ([scriptblock]::Create((irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -Uninstall
```

수동으로 지우려면 `~/.claude/settings.json`의 `hooks.PreToolUse`에서 `danger_guard`/`secrets_guard` 항목과
`~/.claude/hooks/`의 해당 `.py` 파일을 삭제하면 된다. (이 설정 외 다른 키는 설치 시 건드리지 않았으므로 그대로다.)
