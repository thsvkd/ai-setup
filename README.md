# claude-code-setup

Claude Code를 **더 안전하게** 쓰기 위한 사용자 레벨(user-level) 설정 번들.
위험한 명령을 자동으로 막거나 휴지통 이동으로 치환하는 **가드 훅**, 합리적인 **권한(permissions)**,
그리고 프로젝트용 **AGENTS.md**를 Windows / macOS / Linux에 한 번에 설치한다.

- 🛡️ **가드 훅** — `rm`을 휴지통 이동으로 치환, 디스크 포맷·`curl | bash` 등 되돌릴 수 없는 명령을 차단, `git push`는 브랜치 이름으로 판단(곁다리 브랜치는 통과, 보호 브랜치는 확인), `git reset --hard`/`clean`/`stash drop` 등 되돌릴 수 없는 git 명령은 `refs/claude-backups/`에 백업한 뒤 그대로 실행, 시크릿 파일 접근 시 확인 요청
- 🧩 **외과적 병합** — 권한/훅을 추가하고 `model`·`effortLevel`·`language`는 **없을 때만** 채운다. 사용자가 이미 고른 값과 그 외 키(env, statusLine 등)는 100% 보존
- 🔁 **멱등성 · dry-run** — 몇 번을 실행해도 안전하고, `--dry-run`으로 실제 적용 전에 바뀔 내용을 미리 확인
- 🖥️ **크로스 플랫폼** — Windows(PowerShell)와 POSIX(bash) 양쪽을 단일 소스로 관리

> ⚠️ **범위 주의**: 훅과 권한은 `~/.claude`(유저 레벨)에 설치되어 **이 사용자가 여는 모든 프로젝트**에 적용된다.

---

## 설치

> 비공개(private) 레포라서 GitHub 인증이 필요하다. `gh` CLI 설치와 토큰 발급은 [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) 참고.

인자 없이 실행하면 가드 훅/권한(전역)과 `AGENTS.md`(현재 폴더)가 모두 설치된다. `AGENTS.md`는 현재 작업 디렉터리에 생기므로 프로젝트 루트에서 실행하자.

**macOS / Linux / Git Bash**
```sh
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh
```

**Windows PowerShell**
```powershell
if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = gh auth token }
$h = @{ Authorization = "Bearer $env:GITHUB_TOKEN" }
irm -Headers $h https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1 | iex
```

---

## 사용법

`setup`은 디스패처이고, 플래그로 하위 작업을 고른다. 인자가 없으면 전부 실행한다. PowerShell에서 `irm | iex`는 인자를 넘기기 어려우므로, 플래그가 필요하면 아래처럼 `scriptblock` 형태로 감싸서 쓴다.

| 플래그 (POSIX / PowerShell)  | 동작                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------- |
| (없음)                       | 가드 훅/권한 + `AGENTS.md` 모두 설치                                                              |
| `--hooks` / `-Hooks`         | 가드 훅 + 권한만 설치 (전역, `~/.claude`)                                                         |
| `--agentsmd` / `-AgentsMd`   | 현재 폴더에 `AGENTS.md`만 설치                                                                    |
| `--dry-run` / `-DryRun`      | 아무것도 바꾸지 않고 변경 계획만 출력                                                             |
| `--uninstall` / `-Uninstall` | 설치가 추가한 것만 정밀 복원 (아래 참고)                                                          |
| `--help` / `-Help`           | 도움말                                                                                             |

예시 (macOS/Linux/Git Bash — Windows는 위 `scriptblock` 패턴에 `-Hooks`/`-DryRun`/`-Uninstall` 등을 붙이면 된다):

```sh
# 전역 가드/권한만, 미리보기
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --hooks --dry-run

# 제거
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN:-$(gh auth token)}" \
  https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.sh | sh -s -- --uninstall
```

`--uninstall`은 설치 시 기록한 매니페스트(`~/.claude/.claude-code-setup.json`)를 근거로 우리가 추가한 훅·allow/deny 항목·`model`/`effortLevel`/`language`만 제거하고, `defaultMode`를 이전 값으로 원복한다. 사용자가 원래 갖고 있던 설정과 그 외 키는 그대로 보존되며 변경 전 `settings.json.bak.<타임스탬프>`를 남긴다. `settings.json`을 설치가 새로 만든 경우, 되돌린 뒤 비면 파일도 제거한다.

레포를 clone해서 로컬로 실행할 수도 있다:

```sh
git clone https://github.com/thsvkd/claude-code-setup.git && cd claude-code-setup
bash scripts/setup.sh --dry-run   # 또는 .\scripts\setup.ps1 -DryRun
```

---

## 무엇이 설치되나

| 위치                                | 내용                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------ |
| `~/.claude/hooks/danger_guard.py`  | 위험 명령 가드 (Bash·PowerShell 툴)                                                  |
| `~/.claude/hooks/secrets_guard.py` | 시크릿 파일 접근 가드 (Read·Write·Edit)                                              |
| `~/.claude/hooks/send_to_trash.py` | (Windows) 휴지통 이동 헬퍼                                                           |
| `~/.claude/settings.json`          | 권한 + PreToolUse 훅 등록 + `model`/`effortLevel`/`language`·`env.CLAUDE_CODE_SCROLL_SPEED` 기본값(없을 때만) |
| `./AGENTS.md`                      | (`--agentsmd` 시) 현재 폴더에 프로젝트 워크플로 규칙 — 이미 있으면 건너뜀            |

`settings.json`에는 `permissions.defaultMode: "auto"`, 핵심 툴 `allow`(`Bash`, `PowerShell`, `Read(*)`, `Edit(*)`, `Write(*)`, `Agent(*)`, `WebFetch(*)` 등), `ask`(위험 스킬만 — git 관련 규칙은 없음), `hooks.PreToolUse` 등록, 그리고 없을 때만 채우는 `model: "opus"` / `effortLevel: "xhigh"` / `language: "korean"` 과 `env.CLAUDE_CODE_SCROLL_SPEED: "3"`(마우스 휠 스크롤 속도, `/scroll-speed` 대응)이 병합된다. git 관련 deny/ask를 `permissions`에 두지 않는 이유는, Claude Code에서 permission의 deny/ask 규칙은 PreToolUse 훅의 판정(allow)보다 항상 우선하기 때문이다 — 여기에 `Bash(git push *)` 같은 규칙을 두면 `danger_guard.py`가 브랜치 이름을 보고 내리는 세밀한 판단(곁다리 브랜치 통과 등)이 전부 무력화된다. 그래서 git 정책은 전적으로 훅이 담당한다. 사용자가 이미 고른 값과 그 외 최상위 키(`statusLine` 등), 그리고 사용자의 기존 `env` 키/값은 건드리지 않는다(우리가 관리하는 `env` 키만 없을 때 추가). 단일 소스는 [`res/settings.json`](res/settings.json)이며, 설치 시 python 실행 명령과 훅 경로만 치환된다.

---

## 가드 정책

### danger_guard — 위험 명령

| 명령                                                                                                                    | 조치                                                                  |
| ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `rm`, `del`, `Remove-Item`, `rd`, `rmdir`                                                                               | 🗑️ 휴지통 이동으로 **치환** (macOS `trash` / `trash-put` / send2trash) |
| ↳ 드라이브·홈 루트 삭제 (`C:\`, `/`, `~`, 그리고 `$HOME` 값을 그대로 적은 절대경로)                                     | ⛔ **차단**                                                            |
| ↳ 휴지통 도구 미설치 / 여러 줄 스크립트에 섞임                                                                          | ⛔ **차단** (fail-closed)                                              |
| **git** — 전역 옵션(`-C`/`-c` 등)을 건너뛰고 **실제 서브커맨드**를 판정해 세분화 (`git stash push` 같은 안전 명령 오탐 방지) | ↓ 아래 세분화 |
| `git push` — 대상 브랜치 이름에 `/`가 있으면(`feature/*`, `fix/*` 등 곁다리 브랜치) 통과. `/`가 없으면(`main`/`master`/`develop` 등) 브랜치 이름을 명시하며 확인. `--all`/`--mirror` 처럼 특정 브랜치로 못 좁히면 확인 (force 여부는 통과/확인 판정에 영향 없음) | ✅ 통과 또는 ❓ **확인** |
| `reset --hard`, `clean -f*`(`-n`/`--dry-run` 제외), `stash drop`/`clear`, `branch -D`/`-M`(대상 있었으면), `tag -d`/`-f`(대상 있었으면), `rebase`(새로 시작), `commit --amend`, `filter-branch`/`filter-repo`, `reflog expire`/`delete`, `gc --prune=now`/`all`, `checkout`/`switch --force`(강제 전환) | 🗂️ **`refs/claude-backups/<timestamp>/<대상>`에 백업 후 그대로 실행** (자동치환) |
| `git checkout -- <경로>` / `checkout .` / `restore`(워킹트리)                                                            | 🗂️ 위와 동일하게 백업 후 실행 (**자동치환**)          |
| `git stash push`/`pop`/`apply`/`list`, `reset --soft`/`--mixed`, `clean -n`, `branch -d`, `checkout`/`switch <브랜치>`, `restore --staged`, `rebase --continue`/`--abort`/`--skip` | ✅ 통과 (안전) |
| `format` / `diskpart` / `mkfs*` / `newfs_*` / `fdisk` / `parted` / `wipefs` / `Clear-Disk` / `Format-Volume` / `dd of=` | ⛔ **차단**                                                            |
| `diskutil` 파괴적 서브커맨드 (`eraseDisk`, `eraseVolume`, `secureErase`, `partitionDisk`, `apfs deleteContainer` 등)    | ⛔ **차단**                                                            |
| `/dev/sd*`·`/dev/disk*` 등 블록 디바이스로의 리다이렉트, 포크밤 `:(){ :\|:& };:`                                        | ⛔ **차단**                                                            |
| `curl … \| bash`, `irm … \| iex` (원격 출력을 셸로 파이프 — 공백이 없어도)                                              | ⛔ **차단**                                                            |
| `shutdown` / `reboot` / `Restart-Computer`, `chmod 777`, `shred`, `Clear-Content`, `reg delete`                         | ❓ **확인**                                                            |
| 그 외                                                                                                                   | ✅ 통과 (판단 안 함)                                                   |

`sudo <명령>`은 접두어를 벗겨 실제 명령을 위 규칙으로 검사한다. 모든 판정은 `~/.claude/hooks/guard.log`에 감사 기록으로 남는다.

### 왜 git 명령을 막지 않고 백업 후 실행하는가

되돌릴 수 없는 git 명령이라도 실행 자체를 막으면 에이전트가 정상적인 작업(재작업, 정리, 리베이스 등)을 진행하지 못하고 매번 사용자 승인을 기다리게 된다. 대신 실행 **직전**에 되돌릴 대상(현재 HEAD, uncommitted 변경, 삭제될 브랜치/태그/스태시, 도달 불가능해질 커밋 등)을 `refs/claude-backups/<timestamp>/<대상>` 아래에 커밋 객체로 고정해두고 원본 명령은 그대로 실행한다.

- **조회**: `git for-each-ref refs/claude-backups/`
- **복구**: 백업 종류에 따라 `git stash apply <hash>`(uncommitted 변경/스냅샷), `git branch <name> <hash>`(브랜치/태그), `git reset --hard <hash>`(HEAD 위치) 중 알맞은 걸 사용

`git clean`처럼 추적 안 된 파일까지 지우는 명령은 `git stash create`가 추적 안 된 파일을 담지 못하는 한계가 있어(실측 확인), 별도 스크래치 인덱스로 추적/미추적 파일 전체를 스냅샷 커밋으로 백업한다. 멀티라인이나 `&&`/`;`로 체이닝된 명령 안에 섞여 있으면 백업 대상을 안전하게 특정할 수 없어 확인을 요청한다.

`git push`만 이 백업 메커니즘 대신 브랜치 이름 기반 정책을 쓴다 — 원격 히스토리는 로컬 백업으로 보호할 수 있는 대상이 아니고, 어떤 브랜치로 반영되는지가 사용자가 알아야 할 핵심 정보이기 때문이다.

### secrets_guard — 시크릿 파일

`.env`, `id_rsa`/`id_dsa`/`id_ecdsa`/`id_ed25519`, `*.pem`/`*.pfx`/`*.p12`/`*.p8`/`*.ppk`/`*.jks`/`*.keystore`,
`credentials.json`, `secrets.y(a)ml`, `.npmrc`/`.pypirc`/`.netrc`/`.git-credentials`, `~/.aws/credentials`, `*_secret*`, `*.key` 등을
**Read / Write / Edit / MultiEdit**로 접근하면 ❓ 확인을 요청한다 (완전 차단이 아닌 확인 게이트).

단, `.env.example`/`.env.sample`/`.env.template`/`.env.dist` 처럼 자리표시자(placeholder)만 담고 커밋을 전제로 하는
**예시/템플릿 파일은 시크릿이 아니므로 확인 없이 통과**시킨다 (`.env.local.example` 같은 변형도 마지막 확장자로 판정). 실제
시크릿을 담는 `.env`/`.env.local`/`.env.production` 은 그대로 확인 게이트가 걸린다.

---

## 보안 고려사항

`CLAUDE_SETUP_REPO` 환경변수를 설정하면 지정한 레포의 스크립트를 다운로드해 그대로 실행한다. 신뢰할 수 없는 입력(CI 환경변수, 공유 환경 등)이 이 변수를 제어할 수 있으면 임의 코드 실행(RCE)으로 이어질 수 있다. `CLAUDE_SETUP_REPO`/`CLAUDE_SETUP_REF`는 신뢰된 환경에서만 설정하고, 공유 CI에서는 외부에서 덮어쓸 수 없도록 접근을 제한하자.

---

## 요구사항

- **Python 3.9+** (필수) — 훅은 `settings.json`에 `python3`로 등록되므로, Claude Code가 PATH에서 처음 찾는 python3에서 반드시 돌아야 한다 (macOS 기본 `/usr/bin/python3` 포함).
- **macOS**: 추가 설치 불필요. 14.4+는 `/usr/bin/trash`를 기본 제공. (Homebrew `trash-cli`는 keg-only라 `brew install` 해도 PATH에 안 잡힌다.)
- **Linux**: `bash`, `trash-cli`(pip로 자동 설치 시도 — 없으면 `rm` 계열이 차단됨)
- **Windows**: `send2trash`(pip로 자동 설치 시도 — 없으면 `rm`/`del` 계열이 차단됨)

> `auto` 모드는 계정/버전 자격 요건을 충족해야 켜진다. 설치 후 세션에서 `Shift+Tab`으로 모드를 순환시켜 확인할 수 있다.

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
docs/                       # 인증 등 부가 문서
tests/                      # pytest(훅·병합) + bats(bash) + Pester(PowerShell)
```

---

## 개발 · 테스트

가드 훅과 병합 엔진은 블랙박스로 테스트한다 (JSON을 stdin으로 넣고 판정을 검증). git 정책은
판정뿐 아니라 **실제 git 저장소에서 실측**한다 — 자동치환(stash-prepend)이 진짜로 작업을
보존·복구하는지, 안전 판정한 명령이 정말 안전한지까지 확인한다 ([`tests/test_git_guard_realworld.py`](tests/test_git_guard_realworld.py)).

```sh
python -m pytest tests/                 # 훅 정책 + git 실측 + 병합 엔진 + 셋업 스크립트 (Python)
bats tests/setup.bats                    # 셋업 스크립트 (선택 — bats-core 필요)
```
```powershell
Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed   # 셋업 스크립트 (PowerShell)
```

`pytest`만으로도 셋업 스크립트의 실제 설치 경로(`--dry-run`이 아닌 쪽)까지 커버한다
([`tests/test_setup_scripts.py`](tests/test_setup_scripts.py)). [`tests/test_hook_compat.py`](tests/test_hook_compat.py)는
훅이 구버전 python3(macOS 3.9.x)에서도 죽지 않는지 확인한다 — 훅이 예외로 죽으면 Claude Code는
가드 없이 명령을 실행하므로(fail-open), 최신 인터프리터로만 테스트하면 위험하다.
