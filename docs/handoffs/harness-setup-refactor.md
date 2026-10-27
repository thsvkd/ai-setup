# 핸드오프: `claude-code-setup` → 크로스 플랫폼·멀티 하네스 `harness-setup`

- 작성일: 2026-09-01 (Asia/Seoul)
- 로컬 저장소: `C:\Users\<user>\Workspace\claude-code-setup`
- 기준 브랜치/커밋: `main` / `1e36f17` (`origin/main`과 동일, ahead/behind `0/0`)
- 다음 작업 환경: 현재 Windows 장치의 로컬 Codex
- 이번 작업 범위: 조사와 인계 문서 작성만. 저장소 이름 변경, 설치 동작 변경, 훅 정책 변경은 아직 하지 않았다.

## 1. 한눈에 보는 결론

이 저장소는 이름보다 이미 범위가 넓다. Windows와 POSIX 설치기, Claude Code 안전 훅, 프로젝트 `AGENTS.md`, Claude/Codex/Grok용 줄바꿈 키 설정을 한 저장소에서 관리한다. 따라서 `harness-setup`으로의 이름 변경은 타당하다.

다만 구현 중심은 여전히 Claude Code다. 안전 훅·권한·모델 기본값·설치 영수증이 전부 `~/.claude`와 Claude 설정 스키마에 결합되어 있다. Codex는 줄바꿈 키만, Grok은 터미널 시퀀스만 지원하며, OpenCode 어댑터는 없다. 이름만 먼저 바꾸고 이 결합을 그대로 두면 “멀티 하네스”라는 이름과 실제 기능이 어긋난다.

권장 방향은 다음과 같다.

1. 기존 동작을 특성 테스트(characterization test, 현재 동작을 변경 전에 고정하는 테스트)로 잠근다.
2. 이름·환경변수·상태 파일의 이전 호환 계약을 먼저 정한다.
3. 공통 정책과 설치 상태를 하네스 중립 영역으로 옮긴다.
4. Claude, Codex, Grok, OpenCode를 각각 어댑터로 연결한다.
5. OS는 Windows 네이티브, WSL2, Linux, macOS를 별도 실행 환경으로 취급한다.

## 2. 현재 작업 트리 상태

`git status --short --branch` 기준:

```text
## main...origin/main
?? AGENTS.md
```

주의할 점:

- 루트 `AGENTS.md`는 미추적 사용자 파일이므로 삭제·덮어쓰기·자동 커밋하지 않는다.
- 이 파일은 현재 `res/AGENTS.md`와 SHA-256이 동일하다. 설치기를 이 저장소 루트에서 실행해 생성된 것으로 보인다.
- `.omc/`, `.pytest_cache/`, `__pycache__/`, `*.log`는 `.gitignore` 대상이다.
- `AGENTS.md` 첫 줄은 `docs/SPEC.md`를 참조하지만 해당 파일은 없다. 현재 템플릿 자체의 끊어진 참조다.
- 추적된 `.github/` 워크플로, 라이선스, 변경 기록, 기여 가이드는 없다.

이번 조사에서 변경한 파일은 이 인계 문서뿐이다.

## 3. 현재 저장소 구조와 역할

벤더링한 Python 의존성 내부를 생략하면 구조는 다음과 같다.

```text
claude-code-setup/
├── README.md                         # 358줄, 설치·정책·테스트 설명
├── install.ps1 / install.sh          # GitHub 아카이브를 받는 원격 부트스트랩
├── scripts/
│   ├── setup.ps1 / setup.sh          # 온보딩과 기능별 디스패처
│   ├── setup_hooks.*                  # Claude 전역 훅·권한 설치
│   ├── setup_agentsmd.*               # 현재 프로젝트에 AGENTS.md 설치
│   ├── setup_keybinds.*               # 줄바꿈 키 설정
│   ├── test.ps1 / test.sh             # pytest + Pester + bats 통합 러너
│   └── lib/                           # PowerShell/POSIX 공용 설치 보조 함수
├── res/
│   ├── AGENTS.md                      # 배포 템플릿(168줄)
│   ├── settings.json                  # Claude settings 조각
│   ├── onboard.py                     # questionary 기반 대화형 온보딩
│   ├── hooks/
│   │   ├── danger_guard.posix.py
│   │   ├── danger_guard.windows.py
│   │   ├── secrets_guard.py
│   │   ├── send_to_trash.py
│   │   └── merge_and_diff.py
│   ├── keybinds/apply.py              # IDE·터미널·Claude·Codex 설정 병합
│   └── vendor/                        # questionary/prompt_toolkit/wcwidth
├── tests/
│   ├── test_*.py                      # 정책·병합·온보딩·키바인드 테스트
│   ├── Setup.Tests.ps1                # Windows 설치 경로(Pester)
│   └── setup.bats                     # POSIX 설치 경로(bats)
└── docs/
    ├── CONTEXT.md                     # 줄바꿈 기능 용어
    ├── AUTHENTICATION.md              # GitHub 인증
    ├── 2026-07-31-delete-guard-architecture.md
    ├── handoffs/                      # 기존 R1/R3 인계 문서
    └── reviews/                       # 기존 정적 리뷰와 HTML 검수물
```

### 3.1 설치 흐름

1. `install.ps1` 또는 `install.sh`가 GitHub에서 저장소 아카이브를 임시 폴더로 받는다.
2. `scripts/setup.*`가 온보딩 결과 또는 CLI 플래그를 해석한다.
3. 기능별 워커가 다음을 수행한다.
   - hooks: `~/.claude/hooks`와 `~/.claude/settings.json` 수정
   - agentsmd: 현재 디렉터리에 `AGENTS.md` 복사(기존 파일은 기본 보존, `force`면 백업)
   - keybinds: VS Code, Cursor, Windows Terminal, tmux, Claude, Codex 설정을 외과적으로 병합
4. 설치 영수증은 `~/.claude/.claude-code-setup.json`에 저장한다.
5. 제거 시 영수증과 항목 시그니처를 이용해 설치가 관리한 값만 되돌리려 한다.

좋은 기반은 이미 있다. 실제 파일을 직접 덮어쓰기보다 병합하고, 기존 파일을 보존하며, dry-run·멱등 재실행·정밀 uninstall을 테스트한다.

### 3.2 현재 OS 지원

| 실행 환경 | 현재 상태 | 주요 한계 |
| --- | --- | --- |
| Windows 네이티브 | PowerShell 설치기와 Windows 훅이 존재 | App Execution Alias·PowerShell 버전·Windows 경로 변환 문제가 별도 존재 |
| macOS | POSIX 설치기와 macOS `trash` 폴백 존재 | macOS bash 3.2 호환을 코드에서 직접 부담 |
| Linux | POSIX 설치기와 `trash-cli` 경로 존재 | gnome-terminal 줄바꿈 한계, 배포판별 의존성 차이 |
| Git Bash | POSIX 설치기를 Windows에서 사용할 수 있게 고려 | Windows 네이티브와 WSL을 혼동하기 쉬움 |
| WSL | 일부 테스트와 설명에서 간접 고려 | 명시적인 WSL1/WSL2 탐지·경계·설치 정책이 없음 |

WSL은 “Windows의 다른 셸”이 아니다. 홈 디렉터리, PATH, 바이너리, 설정 파일, 샌드박스가 Linux 쪽에 있는 별도 실행 환경이다. Windows 호스트 설정과 WSL 설정을 한 실행에서 몰래 함께 고치지 않는 것이 안전하다.

### 3.3 현재 하네스 지원

| 하네스 | 프로젝트 지침 | 훅/권한 | 키바인드 | 현재 수준 |
| --- | --- | --- | --- | --- |
| Claude Code | `AGENTS.md`를 설치하지만 Claude가 직접 읽을 `CLAUDE.md`는 만들지 않음 | 완전 구현 | 구현 | 사실상 주 대상 |
| Codex | `AGENTS.md`를 직접 읽을 수 있음 | 미설치 | `~/.codex/config.toml` 구현 | 부분 지원 |
| Grok Build | 현재 Grok은 `AGENTS.md` 계열을 읽을 수 있음 | 미설치 | 터미널 시퀀스에만 의존 | 부분 지원 |
| OpenCode | `AGENTS.md`를 직접 읽을 수 있음 | 미설치 | 미구현 | 사실상 미지원 |

Claude Code 공식 문서는 Claude가 `AGENTS.md`가 아니라 `CLAUDE.md`를 읽으므로, Windows에서는 심볼릭 링크보다 `CLAUDE.md`에 `@AGENTS.md`를 넣는 방식을 권장한다. 현재 설치기는 이 연결 파일을 만들지 않으므로, “AGENTS.md 설치 = Claude 프로젝트 지침 설치”라고 볼 수 없다.

## 4. 현재 Claude 전용 가정

다음 항목은 멀티 하네스화 전에 분리하거나 명시적으로 Claude 프로필로 남겨야 한다.

1. 상태와 파일 위치
   - `~/.claude/settings.json`
   - `~/.claude/hooks/*`
   - `~/.claude/.claude-code-setup.json`
   - `.claude-code-setup.json`, `.tmp-claude-code-setup` 같은 이름
2. 설정 스키마
   - `permissions.defaultMode`
   - Claude 도구명 `Bash`, `PowerShell`, `Read`, `Write`, `Edit`, `MultiEdit`
   - `hookSpecificOutput.permissionDecision`
3. 오피니언 기본값
   - `model: opus`
   - `effortLevel: xhigh`
   - `language: korean`
   - `CLAUDE_CODE_SCROLL_SPEED=3`
4. 권한 정책
   - `Bash`, `PowerShell`, 읽기·쓰기·웹·에이전트 도구를 전역 allow
   - oh-my-claudecode 관련 MCP·Skill 이름을 직접 포함
5. 이름과 배포 경로
   - `CLAUDE_SETUP_REPO`, `CLAUDE_SETUP_REF`, `CLAUDE_SETUP_*_KEYBINDINGS`
   - GitHub URL과 임시 디렉터리 이름에 `claude-code-setup` 하드코딩
6. 테스트 픽스처
   - 영수증과 설치 대상이 `~/.claude`에 있다고 전제
   - 테스트 아카이브 최상위 폴더가 `claude-code-setup-main`이라고 전제

`res/settings.json`은 “안전 훅”, “권한 모드”, “개인 모델/언어 취향”, “특정 플러그인 허용”을 한 조각에 섞는다. 멀티 하네스에서는 최소한 다음 프로필을 분리해야 한다.

- safety: 결정적 가드와 복구 장치
- permissions: 하네스별 승인/샌드박스 기본값
- preferences: 모델, 노력 수준, 언어, UI
- integrations: 특정 플러그인·MCP·스킬

## 5. 현재 안전 훅 평가

### 5.1 유지할 좋은 원칙

- 기존 사용자 파일을 덮지 않고 외과적으로 병합한다.
- 변경 전 백업과 설치 영수증을 남긴다.
- `rm` 계열은 가능하면 휴지통으로 치환한다.
- 파괴적 Git 명령은 실행을 무조건 막는 대신 `refs/claude-backups/`에 복구 지점을 만든 뒤 실행한다.
- 백업이 실패하면 원본 파괴 명령도 실행하지 않는다.
- 디스크 포맷, 블록 장치 덮어쓰기, 원격 스크립트의 즉시 셸 실행은 차단한다.
- dry-run, 멱등성, uninstall, 실제 Git 저장소 복구 동작을 테스트한다.

### 5.2 구조적 문제

- POSIX와 Windows 위험 명령 가드가 각각 약 1,461줄/1,595줄로 크게 중복된다.
- 정책 판정과 Claude 입력·출력 스키마가 같은 파일에 섞여 있다.
- 블랙리스트는 임의의 인터프리터·도구를 통한 삭제를 완전하게 막을 수 없다. 기존 삭제 방어 문서도 이 한계를 명시한다.
- 사용자 레벨 훅이 모든 Claude 프로젝트에 적용된다. 프로젝트 신뢰도나 작업 유형별 프로필이 없다.
- 일부 `ask`는 안전성보다 불편을 늘릴 수 있고, 하네스마다 `ask` 지원 의미가 다르다.
- 훅 파일 누락·Python 탐지 실패는 방어선 자체를 없앤다.

### 5.3 권장 안전 정책

우선순위는 다음 순서로 둔다.

1. **Containment(격리)**: OS/하네스 샌드박스로 작업 범위 밖 쓰기와 네트워크를 제한한다.
2. **Reversibility(가역성)**: 휴지통, Git ref, 백업 파일, 원자적 쓰기로 되돌릴 수 있게 만든다.
3. **Mechanical verification(기계적 검증)**: 대상 경로·현재 저장소·백업 성공·변경 diff를 코드로 확인한다.
4. **Deterministic guard(결정적 가드)**: 결과가 명확하고 영향이 크며 되돌리기 어려운 경우만 차단한다.
5. **Human approval(사람 승인)**: 코드로 안전성을 판정할 수 없고 영향이 큰 남은 경우에만 요청한다.

권장 분류:

| 행동 | 기본 처리 | 이유 |
| --- | --- | --- |
| 읽기, 단일 파일 검사, 특정 테스트 | 자동 허용 | 영향이 작고 되돌릴 필요 없음 |
| 작업공간 안 일반 편집 | 샌드박스 안 자동 허용 | diff로 검증·Git으로 복구 가능 |
| 일반 파일 삭제 | 휴지통으로 치환 | 승인보다 복구 가능성 제공 |
| 파괴적 로컬 Git 변경 | 자동 백업 후 실행 | 반복 승인 없이 복구 가능 |
| 보호 브랜치 push, 원격 브랜치 삭제 | 승인 | 외부 상태이고 로컬 백업만으로 복구 불가 |
| 디스크 포맷·블록 장치 덮어쓰기·시크릿 외부 전송 | 결정적 차단 | 영향이 매우 크고 저가역 |
| 패키지 설치·네트워크 다운로드 | 샌드박스/승인 정책에 위임 | 무조건 훅 차단보다 하네스 기본 경계가 적합 |
| 단순히 “수상해 보이는” 명령 | 기록 또는 하네스 기본 승인에 위임 | 광범위한 승인 피로 방지 |

시크릿 훅도 “민감 파일을 읽는 모든 시도”와 “민감 데이터를 외부로 보내는 시도”를 구분해야 한다. 전자는 정상 개발에서 자주 필요하지만, 후자는 영향이 크고 저가역이다.

### 5.4 하네스별 훅 차이

- Claude Code: `~/.claude/settings.json`의 `PreToolUse`에서 deny/ask/allow와 입력 치환을 사용할 수 있다.
- Codex: 현재 공식 훅은 Claude와 유사한 `PreToolUse` 입력 및 deny/입력 치환을 지원하지만, `permissionDecision: "ask"`는 아직 지원하지 않고 훅 실패 후 도구 호출을 계속한다. 승인 필요 정책은 Codex 샌드박스·approval policy·rules와 조합해야 한다.
- Grok Build: 프로젝트·사용자 훅과 Claude 호환 훅을 읽을 수 있지만 프로젝트 신뢰가 필요하다. 실제 지원 결정과 실패 모드는 버전별 계약 테스트로 고정해야 한다.
- OpenCode: JSON 훅 파일이 아니라 JavaScript/TypeScript 플러그인의 `tool.execute.before` 같은 이벤트가 주 확장점이다. 공통 정책 엔진을 호출하는 얇은 플러그인 어댑터가 필요하다.

따라서 `danger_guard.py` 한 파일을 네 하네스 설정에 그대로 복사하는 방식은 피한다. 공통 엔진은 `allow | deny | rewrite | review` 같은 중립 결과를 반환하고, 각 어댑터가 하네스에서 실제로 지원하는 형태로 변환해야 한다. 지원하지 않는 `review`를 조용히 `allow`로 바꾸면 안 된다.

## 6. 이름 변경의 이유와 영향

### 6.1 이름 변경 이유

`claude-code-setup`은 현재 목표를 지나치게 좁게 표현한다. 목표는 특정 모델 공급자가 아니라 여러 코딩 하네스가 같은 개발자 환경·지침·안전 원칙·키 설정을 공유하게 만드는 것이다. `harness-setup`은 Windows, WSL, Linux, macOS와 Claude Code, Codex, Grok Build, OpenCode를 포괄하는 중립적 이름이다.

### 6.2 GitHub 저장소 이름 변경

GitHub는 저장소 이름 변경 후 일반 웹 URL과 Git clone/fetch/push를 새 이름으로 리디렉션하지만, 로컬 remote URL 업데이트를 권장한다. GitHub Pages URL과 “이 저장소를 GitHub Action으로 호출하는 경로”는 예외가 있으므로 자동 리디렉션에 의존하면 안 된다.

이 저장소에는 현재 추적된 GitHub Actions 워크플로가 없지만, 아래 문자열은 반드시 갱신해야 한다.

- README와 설치 예제의 raw/archive/clone URL
- `install.ps1`/`install.sh`의 기본 저장소
- 다운로드 임시 폴더와 출력 문구
- 인증 문서와 테스트 아카이브 루트 이름
- 로컬 remote: `git remote set-url origin git@github.com:thsvkd/harness-setup.git`

### 6.3 사용자 설치 호환성

바로 삭제하거나 바꾸면 기존 설치·자동화가 깨지는 항목:

- `CLAUDE_SETUP_REPO`, `CLAUDE_SETUP_REF`
- `CLAUDE_SETUP_VSCODE_KEYBINDINGS`, `CLAUDE_SETUP_CURSOR_KEYBINDINGS`, `CLAUDE_SETUP_WT_SETTINGS`
- `~/.claude/.claude-code-setup.json`
- `.tmp-claude-code-setup` 임시 파일 시그니처
- 기존 README의 old raw URL을 사용한 복사 명령

권장 이전 계약:

1. 새 이름은 `HARNESS_SETUP_*`로 도입한다.
2. 한 번의 안정 릴리스 동안 새 변수 우선, 기존 `CLAUDE_SETUP_*` 폴백을 지원하고 경고한다.
3. 새 상태 파일은 하네스 중립 위치(예: `~/.harness-setup/state.json`)에 둔다.
4. 첫 실행에서 기존 `~/.claude/.claude-code-setup.json`을 읽어 새 상태로 가져오되, 성공 확인 전 기존 파일을 삭제하지 않는다.
5. uninstall은 구형·신형 영수증을 모두 이해해야 한다.
6. 이전 완료 뒤에도 구형 파일을 자동 삭제하지 말고 `.retired`로 보존하거나 명시적 정리 옵션을 둔다.

## 7. 목표 아키텍처

처음부터 모든 파일을 옮기지 말고, 아래 경계를 먼저 코드상 모듈로 만든 뒤 디렉터리를 정리한다.

```text
harness-setup/
├── core/
│   ├── policy/                 # 하네스 중립 안전 판정과 복구 계획
│   ├── state/                  # 설치 영수증, 마이그레이션, uninstall
│   └── merge/                  # JSON/JSONC/TOML/텍스트 외과적 병합
├── adapters/
│   ├── harness/
│   │   ├── claude/
│   │   ├── codex/
│   │   ├── grok/
│   │   └── opencode/
│   └── platform/
│       ├── windows/
│       └── posix/              # 내부에서 macOS/Linux/WSL 능력 구분
├── profiles/
│   ├── safety/
│   ├── permissions/
│   ├── preferences/
│   └── integrations/
├── templates/
│   ├── AGENTS.md               # 공통·간결한 프로젝트 지침
│   └── CLAUDE.md               # @AGENTS.md + Claude 전용 최소 델타
├── scripts/                    # 얇은 PowerShell/bash 진입점
├── tests/
│   ├── unit/                   # 공통 정책·병합
│   ├── contracts/              # 하네스 이벤트/출력 계약
│   ├── integration/            # 격리 HOME 설치·재설치·제거
│   └── fixtures/
└── docs/
```

중요한 설계 규칙:

- `core`는 `~/.claude`, `~/.codex` 같은 경로를 모른다.
- 하네스 어댑터는 경로·스키마·도구명·훅 결과 형식만 책임진다.
- 플랫폼 어댑터는 경로, 셸, 휴지통, 원자적 쓰기, 실행 파일 탐지만 책임진다.
- 기능 선택은 `harness × capability × platform` 행렬로 표현한다.
- 설치 상태는 “파일을 만들었음”이 아니라 “정확히 어떤 항목을 추가·변경했음”을 기록한다.
- 기존 설정이 유효하지 않거나 파싱 불가능하면 덮어쓰지 않고 중단한다.
- WSL에서 Windows 설정을, Windows에서 WSL 설정을 암묵적으로 수정하지 않는다.

## 8. lean `AGENTS.md` 전략

현재 `res/AGENTS.md`는 168줄이고, 프로젝트마다 달라질 상세 R1→R4 절차·훅 강제 항목·Git 규칙을 모두 포함한다. 항상 컨텍스트에 들어가는 파일로는 무겁고, 존재하지 않는 `docs/SPEC.md`를 참조한다.

목표는 `AGENTS.md`를 다음 정보만 담는 얇은 라우터로 만드는 것이다.

1. 저장소 목적 한 문단
2. 가장 자주 쓰는 검증 명령
3. 변경 불변식 3~7개
4. 안전·Git의 절대 금지 항목
5. 작업 유형별 상세 문서/스킬 포인터

상세한 TDD, 리뷰 루프, 릴리스, 마이그레이션 절차는 Skills나 `docs/workflows/`로 옮겨 필요할 때만 읽는다. AGENTS.md에서 모든 참조 문서를 미리 읽으라고 지시하지 않는다.

하네스 연결 방식:

- Codex, Grok, OpenCode: 루트 `AGENTS.md`를 공통 소스로 사용
- Claude Code: 루트 `CLAUDE.md`에 `@AGENTS.md`를 넣고 Claude 전용 차이만 추가
- 하위 디렉터리: 실제로 다른 명령·규칙이 있을 때만 중첩 `AGENTS.md` 추가
- 개인 취향: 저장소 파일이 아니라 각 하네스 사용자 설정/개인 지침으로 분리

## 9. 권장 단계별 리팩터 계획

### Phase 0 — 기준선과 의사결정 고정

- 미추적 루트 `AGENTS.md`를 커밋할지 제거할지 사용자가 결정한다. 자동 처리 금지.
- 지원 OS·하네스 최소 버전과 “지원”의 의미를 합의한다.
- 현재 설치/재설치/uninstall 결과를 특성 테스트로 고정한다.
- README, 코드, 테스트에 흩어진 기존 이름과 Claude 전용 식별자 목록을 테스트 가능한 인벤토리로 만든다.

### Phase 1 — 동작 불변 이름 변경

- GitHub 저장소를 `harness-setup`으로 변경한다.
- 제목·URL·출력 문구·기본 repo를 새 이름으로 바꾼다.
- `HARNESS_SETUP_*`를 도입하고 `CLAUDE_SETUP_*`를 호환 별칭으로 유지한다.
- 구형 영수증 읽기와 새 상태 파일 마이그레이션 테스트를 먼저 작성한다.
- 이 단계에서는 훅 정책과 설치 기본값을 바꾸지 않는다.

### Phase 2 — 설치 기능과 개인 취향 분리

- `safety`, `instructions`, `keybinds`, `permissions`, `preferences`, `integrations`를 독립 capability로 만든다.
- 인자 없는 실행의 기본 선택을 다시 합의한다. 안전 훅 설치와 모델/언어 설정을 한 번에 묶지 않는다.
- 온보딩 출력이 최종 설치 행렬을 보여주고 확인받게 한다.

### Phase 3 — 공통 지침 정리

- lean `AGENTS.md`와 `CLAUDE.md` import wrapper를 추가한다.
- 기존 긴 워크플로는 Skills/문서로 이동하되 의미를 잃지 않는다.
- 기존 `setup_agentsmd.*`를 “instructions capability”로 일반화한다.

### Phase 4 — 안전 정책 코어 추출

- 기존 훅 테스트를 그대로 둔 상태에서 순수 정책 함수와 하네스 출력 어댑터를 분리한다.
- 공통 명령 분류, 플랫폼별 경로/휴지통, 하네스별 이벤트 변환을 각각 테스트한다.
- `ask` 미지원 하네스에 대한 명시적 폴백 계약을 정한다.
- 시크릿 “파일 접근”과 “외부 전송” 정책을 분리한다.

### Phase 5 — 하네스 어댑터 순차 도입

1. Claude: 현재 동작과 완전 동등하게 어댑터화
2. Codex: AGENTS, hooks, rules, sandbox/approval profile
3. Grok: AGENTS, hooks/config, trust 확인, 키바인드 제약
4. OpenCode: AGENTS, config, 정책 엔진 호출 플러그인

한 번에 네 하네스를 구현하지 않는다. 각 어댑터마다 설치→재실행→dry-run→uninstall→실제 CLI inspect 순서를 완료한 뒤 다음으로 간다.

### Phase 6 — 플랫폼 행렬과 CI

- Windows, Ubuntu, macOS에서 격리 HOME 통합 테스트를 실행한다.
- WSL2는 Windows 네이티브와 별도 시나리오로 검증한다.
- Python/PowerShell/bash 러너가 없으면 통과로 위장하지 않고, 무엇이 검증되지 않았는지 명시한다.
- 실제 사용자 홈과 에디터 설정을 CI/자동 테스트에서 절대 사용하지 않는다.

### Phase 7 — 문서·릴리스·구형 설치 정리

- README를 설치 행렬과 capability 중심으로 다시 쓴다.
- 마이그레이션/롤백/제거 문서를 추가한다.
- 버전 태그와 변경 기록을 도입하고 raw `main` 실행보다 고정 태그 설치를 권장한다.
- 라이선스와 기여 정책을 결정한다.

## 10. 현재 Windows Codex에서 바로 할 첫 작업

아래는 다음 세션의 권장 순서다. 각 작업은 독립 커밋 후보이며, 사용자 합의 없이 구현 단계로 넘어가지 않는다.

1. **환경 기준선 복구**
   - 현재 `scripts/test.ps1 -PythonOnly`가 Microsoft Store App Execution Alias인 `python.exe`에서 `ResourceUnavailable`로 중단된다.
   - Codex 번들 Python 3.12.13은 실행되지만 `pytest`가 없다.
   - Python 후보 탐지가 실행 불가능한 alias를 만나도 다음 후보로 계속되는지에 대한 회귀 테스트를 먼저 정의한다.
2. **지원 행렬 합의**
   - Windows 네이티브/WSL2/Linux/macOS와 네 하네스의 최소 버전, 설치 범위, 기본 선택을 `docs/CONTEXT.md`에 고정한다.
3. **이름 이전 계약 테스트 작성**
   - old/new repo URL, env 변수 우선순위, 구형 영수증 마이그레이션, uninstall 호환의 테스트 케이스를 인간과 합의한다.
4. **Phase 1만 구현**
   - 동작을 바꾸지 않고 이름과 호환 shim만 도입한다.
5. **lean 지침 설계 합의**
   - 현재 `res/AGENTS.md`에서 반드시 항상 남을 규칙과 Skill/문서로 옮길 규칙을 분류한다.
6. **Claude 어댑터 특성화**
   - 현재 `res/settings.json`, `merge_and_diff.py`, 두 danger guard의 입출력 골든 픽스처를 만든다.
7. **Codex 프로토타입**
   - 별도 임시 HOME에서 Claude 훅 JSON의 deny/rewrite가 Codex에서 실제로 동작하는지 확인한다.
   - `ask`는 지원되지 않으므로 rules/approval policy 경로를 별도 검증한다.

## 11. 성공 기준 초안

아래는 R1 인간 검수 전 초안이다. 구현 전에 번호와 범위를 사용자와 확정해야 한다.

- **HS-1** 새 설치 문서·출력·기본 URL은 `harness-setup`을 사용한다.
- **HS-2** 기존 `CLAUDE_SETUP_*` 자동화는 호환 기간 동안 같은 결과를 내며 deprecation 경고만 추가된다.
- **HS-3** 기존 영수증이 있는 사용자는 설치 항목을 잃지 않고 새 상태로 마이그레이션할 수 있다.
- **HS-4** 설치, dry-run, 재실행, 옵션 변경, uninstall이 사용자 원래 설정을 보존한다.
- **HS-5** Windows 네이티브, WSL2, Linux, macOS가 별도 환경으로 감지되고 암묵적으로 서로의 홈을 수정하지 않는다.
- **HS-6** Claude, Codex, Grok, OpenCode가 공통 `AGENTS.md` 지침을 실제로 읽는다. Claude는 `CLAUDE.md` import를 통해 읽는다.
- **HS-7** 각 하네스의 설정·훅 어댑터가 지원하지 않는 정책을 조용히 허용으로 내리지 않는다.
- **HS-8** 안전 정책은 고영향·저가역 행동만 결정적으로 차단하고, 가능한 행동은 격리·백업·기계 검증으로 자동 처리한다.
- **HS-9** 모든 자동 테스트는 격리 HOME/설정 픽스처를 사용하며 실제 사용자 설정을 읽거나 쓰지 않는다.
- **HS-10** 설치된 각 하네스에서 inspect/doctor 명령으로 지침·훅·권한 출처를 확인할 수 있다.
- **HS-11** 기존 Claude 기능과 줄바꿈 기능의 회귀 테스트가 계속 통과한다.
- **HS-12** README의 지원 행렬이 실제 테스트 행렬과 일치한다.

## 12. 검증 명령

### 12.1 변경 전/후 공통

```powershell
git status --short --branch
git diff --check
git diff --stat
git grep -n -I "claude-code-setup\|CLAUDE_SETUP_"
```

마지막 검색은 구형 호환 shim과 마이그레이션 문서에만 남아야 한다.

### 12.2 Windows

```powershell
$env:HARNESS_TEST_PYTHON = "C:\path\to\python.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test.ps1 -Strict

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -Hooks -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -AgentsMd -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -Keybinds -DryRun
```

환경변수 이름 변경 전 현재 러너는 `CLAUDE_TEST_PYTHON`을 사용한다. 위 `HARNESS_TEST_PYTHON`은 Phase 1 이후 목표 이름이며, 호환 기간에는 둘 다 테스트한다.

### 12.3 macOS/Linux/WSL2

```sh
HARNESS_TEST_PYTHON=/path/to/python bash scripts/test.sh --strict

bash scripts/setup.sh --dry-run
bash scripts/setup.sh --hooks --dry-run
bash scripts/setup.sh --agentsmd --dry-run
bash scripts/setup.sh --keybinds --dry-run
```

### 12.4 하네스 실측

- Claude Code: `/memory`, `/hooks`, `/permissions`, `/doctor`
- Codex: `/hooks`에서 소스·신뢰 상태 확인, AGENTS 지침 체인 확인
- Grok Build: `grok inspect`, `/hooks-list`, 프로젝트 trust 상태 확인
- OpenCode: 프로젝트 `AGENTS.md` 로드와 정책 플러그인의 before-tool 이벤트를 격리 프로젝트에서 확인

실측은 파일 존재만 보지 않는다. “위험 명령이 실제로 차단/치환되는가”, “재실행해도 중복이 없는가”, “제거 후 사용자 원본만 남는가”를 확인한다.

## 13. 이번 세션 검증 결과

- 저장소는 `main`이며 `origin/main`과 동일하다.
- 루트 미추적 파일은 `AGENTS.md` 하나다.
- 로컬 Markdown 상대 링크는 유효하지만 `AGENTS.md`의 `docs/SPEC.md` 참조는 끊어져 있다.
- Python 테스트 실행을 시도했으나 테스트 수집 전에 러너가 중단됐다.
  - PATH의 `python.exe`: Microsoft Store App Execution Alias, 현재 환경에서 접근 불가
  - Codex 번들 Python: 3.12.13 실행 가능, `pytest` 미설치
  - 결과: 코드 실패로 판정할 수 없음. 이번 세션에서 pytest/Pester/bats 통과를 주장하지 않는다.
- 저장소 파일과 사용자 설정을 변경하는 설치/E2E 검증은 실행하지 않았다.

## 14. 열린 위험과 결정 질문

1. 저장소 공개 범위: `docs/AUTHENTICATION.md`는 비공개 저장소라고 하지만 현재 상태와 일치하는지 확인이 필요하다.
2. “지원” 정의: 지침만 읽으면 지원인지, 설치·훅·권한·키바인드·uninstall까지 모두 있어야 지원인지?
3. 최소 하네스 버전: Codex와 Grok의 훅 기능은 빠르게 변하고 있으므로 버전을 고정할지 최신만 지원할지?
4. WSL 정책: Windows에서 한 번 실행해 WSL까지 설치할지, 각 환경 안에서 별도 실행만 허용할지? 권장은 후자다.
5. 기본 설치 범위: 인자 없는 실행이 여전히 모든 capability를 설치해야 하는가?
6. 전역 훅 범위: 모든 프로젝트에 적용할지, 신뢰된 프로젝트만 적용할지, 둘 다 프로필로 제공할지?
7. 모델·언어 취향: 개인 기본값을 공개 저장소의 공통 safety 프로필에 포함할지?
8. 상태 위치: `~/.harness-setup/`을 쓸지 XDG/LOCALAPPDATA 규칙을 따를지?
9. 구형 파일 정리: 자동 삭제 대신 `.retired` 보존 기간과 명시적 purge 옵션을 둘지?
10. `ask` 의미: 하네스별 네이티브 승인으로 통일할지, 미지원 하네스에서는 deny+재시도 안내로 처리할지?
11. 시크릿 정책: 파일 접근 전체를 묻는 현재 정책을 유지할지, 외부 전송 중심으로 좁힐지?
12. 블랙리스트 한계: 작업공간 내부 파괴를 스냅샷으로 보강할지, 각 하네스 샌드박스만 사용할지?
13. 배포 안정성: raw `main` 실행을 계속 허용할지, 서명/체크섬이 있는 태그 릴리스로 전환할지?
14. 공개 배포 요건: 라이선스, SECURITY, CHANGELOG, CI를 어느 Phase에서 추가할지?

## 15. 기각하거나 보류할 접근

- 네 하네스 설정을 한 번에 구현: 실패 원인을 분리하기 어렵고 uninstall 위험이 커서 보류.
- 현재 `danger_guard.py`를 모든 하네스에 그대로 복사: 입출력·승인 의미가 달라 기각.
- `AGENTS.md`와 `CLAUDE.md`에 같은 긴 내용을 복제: 드리프트가 생기므로 기각.
- Windows에서 심볼릭 링크로 `CLAUDE.md` 생성: 관리자 권한/Developer Mode 의존 때문에 기본 경로로 기각.
- 저장소 rename과 훅 정책 변경을 같은 커밋에서 수행: 회귀 원인과 롤백 경계가 섞이므로 기각.
- 기존 `CLAUDE_SETUP_*`와 영수증을 즉시 삭제: 기존 설치/uninstall을 깨뜨리므로 기각.
- 위험해 보이는 모든 명령에 승인 요청: 승인 피로가 생겨 실제 고위험 경고의 신호가 약해지므로 기각.
- 훅 블랙리스트를 완전한 보안 경계로 취급: 기존 조사에서도 원리적 우회 가능성이 확인되어 기각.

## 16. 관련 코드 포인터

- 설치 진입점: `install.ps1`, `install.sh`
- 온보딩/디스패치: `scripts/setup.ps1`, `scripts/setup.sh`, `res/onboard.py`
- Claude 설정 설치: `scripts/setup_hooks.ps1`, `scripts/setup_hooks.sh`, `res/settings.json`
- 상태·병합: `res/hooks/merge_and_diff.py`, `scripts/lib/SetupCommon.ps1`, `scripts/lib/setup_common.sh`
- 위험 정책: `res/hooks/danger_guard.windows.py`, `res/hooks/danger_guard.posix.py`
- 시크릿 정책: `res/hooks/secrets_guard.py`
- 지침 템플릿: `res/AGENTS.md`
- 키 설정: `res/keybinds/apply.py`
- 삭제 정책의 한계: `docs/2026-07-31-delete-guard-architecture.md`
- 기존 기능 합의/실측: `docs/handoffs/newline-keybind.md`, `docs/handoffs/newline-keybind-R3.md`
- 테스트: `tests/test_setup_scripts.py`, `tests/test_merge_and_diff.py`, `tests/test_keybinds.py`, `tests/test_danger_guard_*.py`, `tests/Setup.Tests.ps1`, `tests/setup.bats`

## 17. 근거 링크

- [GitHub 저장소 이름 변경 동작과 예외](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)
- [Claude Code: AGENTS.md를 CLAUDE.md에서 가져오는 공식 방식](https://code.claude.com/docs/en/memory#agents-md)
- [Claude Code 훅 가이드](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code 설정 디버깅](https://code.claude.com/docs/en/debug-your-config)
- [OpenAI Docs: Codex의 AGENTS.md 탐색](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [OpenAI Docs: Codex 훅과 현재 PreToolUse 제약](https://learn.chatgpt.com/docs/hooks)
- [OpenAI Docs: Codex 샌드박스·승인·Windows/WSL 경계](https://learn.chatgpt.com/docs/agent-approvals-security)
- [OpenAI Docs: Codex command rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [xAI 공식 Grok Build 개요](https://docs.x.ai/build/overview)
- [xAI Grok Build 공개 저장소와 사용자 가이드](https://github.com/xai-org/grok-build)
- [OpenCode 공식 AGENTS.md 규칙](https://opencode.ai/docs/rules)
- [OpenCode 공식 플러그인 훅](https://opencode.ai/docs/plugins/)

## 18. Suggested skills

다음 로컬 Codex 세션에서 권장하는 Skills:

- `grill-me`: 지원 행렬, 기본 설치 범위, 이전 호환, `ask` 폴백의 결정 트리를 사용자와 확정
- `tdd`: 확정된 HS-N을 RED→GREEN 테스트로 구현
- `diagnose`: Windows Python/App Execution Alias와 크로스 셸 실행 문제를 재현 기반으로 해결
- `openai-docs`: Codex hooks/rules/sandbox의 현재 공식 계약을 구현 시점에 재확인
- `deep-research`: Claude/Grok/OpenCode의 버전별 훅·신뢰·권한 차이를 공식 문서와 소스로 교차 검증

