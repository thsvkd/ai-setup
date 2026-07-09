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

> 이 저장소는 **비공개(private)** 이므로 GitHub 인증이 필요하다. 아래 순서대로 따라하면 된다.

### Step 1 — `gh` CLI 설치

`gh` CLI가 있으면 토큰을 keyring에서 안전하게 읽어올 수 있다. 이미 설치돼 있으면 Step 2로 건너뛰자.

**macOS**
```sh
brew install gh
```

**Linux (Debian/Ubuntu)**
```sh
sudo apt install gh
# 또는 공식 패키지 저장소: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

**Windows**
```powershell
winget install --id GitHub.cli
# 또는 Scoop: scoop install gh
```

설치 후 한 번만 로그인:
```sh
gh auth login
```

### Step 2 — 인증

**`gh` CLI 사용 (권장):** Step 1에서 `gh auth login`을 했다면 **더 할 일이 없다.**
`install.sh`는 `GITHUB_TOKEN`/`GH_TOKEN`이 없으면 `gh auth token`으로 알아서 폴백한다.

**`gh` 없이 PAT 직접 사용:**

GitHub → Settings → Developer settings → Personal access tokens에서 토큰 발급.
- classic PAT: `repo` 스코프
- fine-grained PAT: 대상 레포 Contents: Read 권한

```sh
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"   # 발급한 PAT 값으로 교체 — 이 셸 세션 한정
```

> ⛔ **`GITHUB_TOKEN`을 rc 파일(`.zshrc` 등)에 영구 export 하지 말 것.**
> `gh`는 `GITHUB_TOKEN`이 설정돼 있으면 그 값을 우선 쓰고 **`gh auth login`을 거부한다.**
> 그 상태에서 토큰이 만료되면 재로그인조차 못 하고, 설치는 계속 `404`로 실패한다
> (비공개 레포는 인증 실패를 401이 아니라 404로 위장하기 때문에 원인도 안 보인다).
> 이미 그렇게 해뒀다면 rc에서 그 줄을 지우고, 현재 셸에서 `unset GITHUB_TOKEN` 하자.

**토큰이 살아있는지 확인 (설치 전 1초):**

```sh
gh auth status                 # "Logged in" 이어야 한다
```
```powershell
gh auth status
```

`The token in keyring is invalid`가 뜨면 아래로 되살린다.

```sh
unset GITHUB_TOKEN GH_TOKEN    # 이걸 먼저 해야 gh auth login 이 동작한다
gh auth login -h github.com
```

### Step 3 — 설치

아래 명령의 `${GITHUB_TOKEN:-$(gh auth token)}`는 "환경변수가 있으면 그걸,
없으면 `gh`에서 읽어라"라는 뜻이라 위 두 방식 모두에서 그대로 동작한다.

> 📥 **`curl … | sh` 로 파이프하지 않고 파일로 받아 실행한다.** 파이프라인의 종료 코드는 마지막
> 명령(`sh`)의 것이다. 그래서 토큰이 죽어 `curl`이 404로 실패해도, 빈 stdin을 받은 `sh`는
> **0(성공)으로 끝난다** — 아무것도 설치되지 않았는데 성공처럼 보인다. `install.sh`가 내부에서
> `curl | tar` 대신 파일로 받는 것도 같은 이유이고, 이 저장소가 설치하는 `danger_guard`는 아예
> `curl … | sh` 패턴을 차단한다. 받아둔 파일은 실행 전에 `less "$f"`로 훑어볼 수 있다.

#### a) 전역 가드/권한만 설치 (권장 시작점)

어느 위치에서 실행해도 된다. `~/.claude`에만 설치된다.

**macOS / Linux / Git Bash**
```sh
f="$(mktemp)"
curl --proto '=https' --tlsv1.2 -fsSL \
  -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  -o "$f" https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh \
  && sh "$f" --hooks
rm -f "$f"
```

**Windows PowerShell**
```powershell
# install.ps1 은 $env:GITHUB_TOKEN 을 읽는다 — 이 세션에만 채워둔다 (영구 저장 금지)
if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = gh auth token }
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
& ([scriptblock]::Create((irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -Hooks
```

#### b) 먼저 미리보기 (아무것도 바꾸지 않음)

설치 전에 어떤 변경이 일어날지 확인하고 싶다면:

**macOS / Linux / Git Bash**
```sh
f="$(mktemp)"
curl --proto '=https' --tlsv1.2 -fsSL \
  -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  -o "$f" https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh \
  && sh "$f" --dry-run
rm -f "$f"
```
**Windows PowerShell**
```powershell
# install.ps1 은 $env:GITHUB_TOKEN 을 읽는다 — 이 세션에만 채워둔다 (영구 저장 금지)
if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = gh auth token }
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
& ([scriptblock]::Create((irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -DryRun
```

#### c) 전체 설치 (가드/권한 + 현재 폴더에 AGENTS.md)

`AGENTS.md`는 **현재 작업 디렉터리**에 설치되므로 프로젝트 루트에서 실행하자.

**macOS / Linux / Git Bash**
```sh
cd my-project
f="$(mktemp)"
curl --proto '=https' --tlsv1.2 -fsSL \
  -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  -o "$f" https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh \
  && sh "$f"
rm -f "$f"
```
**Windows PowerShell**
```powershell
cd my-project
# install.ps1 은 $env:GITHUB_TOKEN 을 읽는다 — 이 세션에만 채워둔다 (영구 저장 금지)
if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = gh auth token }
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1 | iex
```

> 인자를 주지 않으면 **가드/권한 + AGENTS.md**가 모두 설치된다. PowerShell에서 `irm | iex`는 인자를 넘기기 어려우므로, 플래그가 필요할 땐 위의 `scriptblock` 형태를 쓰자.

### 문제 해결 — `404`가 뜬다면

거의 항상 **토큰 문제**다. 비공개 레포는 인증 실패를 `401`이 아니라 `404`로 돌려준다
("이 레포는 존재조차 하지 않는다"고 시치미를 떼는 게 GitHub의 정책이다). 그래서
`install.sh 파일이 없다`처럼 보이지만, 파일은 멀쩡히 있다.

```sh
gh auth status    # "The token in keyring is invalid" → 토큰이 죽었다
```

되살리는 **순서**가 중요하다. `GITHUB_TOKEN`이 설정돼 있으면 `gh`가 그 값을 우선 쓰면서
로그인 자체를 거부하므로, 반드시 먼저 `unset` 해야 한다.

```sh
unset GITHUB_TOKEN GH_TOKEN
gh auth login -h github.com
```

**오류가 어디서 나오는지 구분하자.** 다운로드는 두 단계이고, 각 단계를 다른 쪽이 보고한다.

1. **`install.sh` 자체를 받는 단계** — `curl`이 직접 보고한다. 토큰이 죽었으면 이렇게 뜬다:
   ```
   curl: (56) The requested URL returned error: 404
   ```
   `curl`은 56으로 종료하고, 위 설치 명령은 `&&` 때문에 `sh`를 실행하지 않는다. 여기서
   멈췄다면 `install.sh`는 **아직 실행조차 되지 않았으므로** 아래 2번의 친절한 진단은 볼 수 없다.

2. **`install.sh`가 실행된 뒤 레포 아카이브를 받는 단계** — 이때 실패하면 스크립트가 GitHub API를
   한 번 찔러 `401`(토큰 만료) / `403`(권한 부족) / `404`(레포 못 봄) / ref 오류를 구분해 알려준다.
   주로 `CLAUDE_SETUP_REPO`·`CLAUDE_SETUP_REF`를 잘못 줬을 때, 또는 clone 해둔 `install.sh`를
   직접 실행할 때 만난다.

어느 쪽이든 먼저 확인할 것은 `gh auth status` 하나로 같다.

> `CLAUDE_SETUP_REF`에는 `feature/my-branch`처럼 슬래시가 든 브랜치명을 **그대로 써도 된다**
> (raw URL과 archive URL 양쪽에서 확인했다). ref와 경로의 경계를 분명히 하고 싶다면
> `refs/heads/feature/my-branch` 형태도 동작한다.

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
| `rm`, `del`, `Remove-Item`, `rd`, `rmdir` | 🗑️ 휴지통 이동으로 **치환** (macOS `trash` / `trash-put` / send2trash) |
| ↳ 드라이브·홈 루트 삭제 (`C:\`, `/`, `~`) | ⛔ **차단** |
| ↳ 휴지통 도구 미설치 / 여러 줄 스크립트에 섞임 | ⛔ **차단** (fail-closed) |
| `git push`, `git push --force` | ⛔ **차단** (수동 실행 요구) |
| `git reset --hard`, `git clean -f*`, `git stash drop`/`clear` | ⛔ **차단** |
| `git branch -D`, `git checkout -- <경로>`, `git restore` | ❓ **확인** |
| `format` / `diskpart` / `mkfs*` / `newfs_*` / `fdisk` / `parted` / `wipefs` / `Clear-Disk` / `Format-Volume` / `dd of=` | ⛔ **차단** |
| `diskutil` 파괴적 서브커맨드 (`eraseDisk`, `eraseVolume`, `secureErase`, `partitionDisk`, `apfs deleteContainer` 등) | ⛔ **차단** |
| `/dev/sd*`·`/dev/disk*` 등 블록 디바이스로의 리다이렉트, 포크밤 `:(){ :\|:& };:` | ⛔ **차단** |
| `curl … \| bash`, `irm … \| iex` (원격 출력을 셸로 파이프 — `curl url\|bash` 처럼 공백이 없어도) | ⛔ **차단** |
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

- **Python 3.9+** (필수 — 훅과 병합 엔진이 사용).
  훅은 `settings.json`에 `python3`라는 이름으로 등록되므로, Claude Code가 PATH에서 처음 찾는
  python3에서 반드시 돌아야 한다 — macOS 기본 `/usr/bin/python3`(3.9.x)를 포함해서.
- **macOS**: 추가 설치 불필요. 14.4+는 `/usr/bin/trash`를 기본 제공하고 훅이 이걸 쓴다.
  (Homebrew의 `trash-cli`는 keg-only라 `brew install` 해도 `trash-put`이 PATH에 링크되지 않는다.)
- **Linux**: `bash`, `trash-cli`(pip로 자동 설치 시도 — 없으면 `rm` 계열이 **차단**됨)
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
python -m pytest tests/                 # 훅 정책 + 병합 엔진 + 셋업 스크립트 (Python)
bats tests/setup.bats                    # 셋업 스크립트 (선택 — bats-core 필요)
```
```powershell
Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed   # 셋업 스크립트 (PowerShell)
```

`pytest`만으로도 셋업 스크립트의 **실제 설치 경로**(`--dry-run`이 아닌 쪽)까지 커버한다
([`tests/test_setup_scripts.py`](tests/test_setup_scripts.py)) — `bats`는 없어도 된다.
훅 테스트는 **호스트에 휴지통 도구가 깔려 있는지에 좌우되지 않는다**: `send2trash`의 유무는
`sys.modules` 주입으로, `trash-put`/`trash`의 유무는 `PATH` 통제로 시뮬레이션하므로 어느
OS에서든 같은 결과가 나온다. 그래서 Windows 가드도 macOS에서 그대로 검증된다 — 플랫폼별
`skipif`는 훅이 실제로 `sys.platform`으로 분기하는 지점에만 쓴다(예: macOS 기본 `/usr/bin/trash`).
그리고 [`tests/test_hook_compat.py`](tests/test_hook_compat.py)는 훅이 시스템의 구버전
python3(macOS의 3.9.x)에서도 죽지 않는지 확인한다. 훅이 예외로 죽으면 Claude Code는
가드 없이 명령을 실행하므로(fail-open), 최신 인터프리터로만 테스트하면 위험하다.

---

## 되돌리기

`setup.sh --uninstall` / `setup.ps1 -Uninstall`은 **설치가 건드린 부분만 정밀하게 되돌린다**.
설치 시 기록해둔 영수증(`~/.claude/.claude-code-setup.json`)을 근거로, 우리가 추가한 훅·allow/deny 항목과
우리가 새로 넣은 `model`/`effortLevel`/`language`만 제거하고 `defaultMode`를 이전 값으로 원복하며(설치 이후 사용자가 또 바꿨다면 건드리지 않음), 훅 파일·guard.log·매니페스트를
지운다. 설치가 `settings.json`을 처음 만든 경우 되돌린 뒤 비면 그 파일도 제거한다. 사용자가 원래 갖고 있던 설정과
그 외 모든 키는 그대로 보존되고, 변경 전 `.bak`을 남긴다. 원격에서 바로 실행하려면:

```sh
f="$(mktemp)"
curl --proto '=https' --tlsv1.2 -fsSL \
  -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  -o "$f" https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh \
  && sh "$f" --uninstall
rm -f "$f"
```
```powershell
# install.ps1 은 $env:GITHUB_TOKEN 을 읽는다 — 이 세션에만 채워둔다 (영구 저장 금지)
if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = gh auth token }
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
& ([scriptblock]::Create((irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -Uninstall
```

수동으로 지우려면 `~/.claude/settings.json`의 `hooks.PreToolUse`에서 `danger_guard`/`secrets_guard` 항목과
`~/.claude/hooks/`의 해당 `.py` 파일을 삭제하면 된다. (이 설정 외 다른 키는 설치 시 건드리지 않았으므로 그대로다.)
