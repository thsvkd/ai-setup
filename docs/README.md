# 문서 지도

`AGENTS.md`의 문서 라우터가 가리키는 문서들의 현재 상태다. 라우터는 얇게 유지하고, 상세 규칙은 여기 등록된 문서가 소유한다.

## 상태 정의

- `authoritative` — 확정된 계약. 코드와 어긋나면 둘 중 하나가 버그다.
- `draft` — 작성 중. 참고는 하되 확정 계약처럼 쓰지 않는다.
- `planned` — 아직 파일이 없다. 라우터가 가리키지만 존재하지 않으므로 건너뛰고 `AGENTS.md`의 기본 계약을 따른다.
- `historical` — 당시의 결정 기록. 현재 동작의 근거가 아니라 배경 자료다.

## SSoT 계층

| 문서 | 답하는 질문 | 상태 |
| --- | --- | --- |
| `PRD.md` | 무엇을 왜 만드는가. 목표·비목표와 성공 지표 | `authoritative` (ai-setup 편입 범위만, 2026-10-13) |
| `SPEC.md` | 어떻게 구현하는가. 자주 바뀌지 않는 계약만 | `authoritative` (ai-setup 편입 범위만, 2026-10-13) |
| `TEST_SPEC.md` | 무엇이 완료인가. 수용 기준의 유일한 SSoT | `authoritative` (ai-setup 편입 범위만, 2026-10-13) |

세 가지 경계를 지킨다.

- **완료 판정은 `TEST_SPEC.md` 하나가 소유한다.** `PRD.md`의 성공 지표는 비즈니스 관점이고 완료 게이트가 아니다. 두 문서가 어긋나면 어느 쪽이 기준인지 판정할 수 없게 된다.
- **`SPEC.md`는 안정 계약만 담는다.** 레포 전체를 한 문서에 담으면 변경마다 전체를 리뷰해야 하고 가장 먼저 썩는다. 변경 단위 상세는 `handoffs/`에 쓴다.
- **`TEST_SPEC.md`의 케이스는 EARS 형식으로 쓴다.** `WHEN <조건> THE SYSTEM SHALL <기대 동작>`. 조건절이 그대로 테스트 이름이 되고, 모호성·누락·모순을 기계적으로 검사할 수 있다. 예: `Test-7: WHEN 기존 AGENTS.md 가 있고 -Force 가 없으면 THE SYSTEM SHALL 기존 파일을 변경하지 않는다`

## 작업 규칙

| 문서 | 다루는 것 | 상태 |
| --- | --- | --- |
| `TDD.md` | 테스트 작성 방식, RED/GREEN 정의, 적대적 리뷰 루프와 CRITICAL/HIGH/MEDIUM/LOW 심각도 등급 | `planned` |
| `GIT.md` | 커밋·브랜치·머지·백업 ref 규약 | `planned` |
| `CODE_STYLE.md` | 코드 스타일과 네이밍, PowerShell·bash·Python 스크립트 작성 규칙 | `planned` |
| `SECURITY.md` | 시크릿·권한·파괴적 동작 정책 | `planned` |
| `REPORTING.md` | 작업 보고·검수 보고서 양식, 증거 번들 구성 | `planned` |

실행 명령은 별도 문서 없이 `AGENTS.md`의 커맨드 표가 소유한다. 서브에이전트·모델 규칙도 `AGENTS.md`의 오케스트레이션 절이 전부다 — 두 주제 모두 라우터를 한 번 더 거칠 만큼 길지 않고, 실제 AI 네이티브 레포(openai/codex, sst/opencode)도 별도 문서를 두지 않는다.

## 배경과 기록

| 문서 | 다루는 것 | 상태 |
| --- | --- | --- |
| `CONTEXT.md` | 용어 정의 | `authoritative` |
| `AUTHENTICATION.md` | GitHub 인증 | `authoritative` |
| `2026-07-31-delete-guard-architecture.md` | 삭제 가드 설계와 그 한계 | `historical` |
| `handoffs/` | 이전 작업의 케이스 합의·핵심 결정·기각한 대안 | `historical` |
| `reviews/` | 정적 리뷰와 인간 검수 산출물 | `historical` |

`handoffs/`와 `reviews/`는 기록이다. 라우터가 가리키지 않으므로 필요할 때 직접 찾아본다.

## 초안 작성 시 참고

`planned` 문서를 채울 때 원자료가 있다. 직전 `res/AGENTS.md`(168줄)에는 R0~R4 워크플로, GREEN 의 정의, 적대적 리뷰 루프, 강제 항목, Git 컨벤션이 들어 있었다. 이 내용은 삭제된 것이 아니라 각 문서로 옮겨질 대상이며, 원문은 다음으로 볼 수 있다.

```bash
git show main:res/AGENTS.md
```

옮겨 갈 곳:

- R0~R4 워크플로, GREEN 의 정의, 적대적 리뷰 루프와 심각도 등급 -> `TDD.md`
- AI slop 제거 단계, E2E 실측 검증의 범위("테스트가 이미 검증한 동작은 수동으로 재확인하지 않는다") -> `TDD.md`
- 커밋 메시지·트레일러 규약, 커밋 단위 규칙(논리적 변경 단위·테스트와 구현을 함께·관련 변경만), `refs/claude-backups/` 사용법 -> `GIT.md`
- 강제 항목(훅·권한으로 강제하는 목록) -> `SECURITY.md`
- 신선 컨텍스트 리뷰어, 모델·에이전트 선택 -> `AGENTS.md` 오케스트레이션 절
- 하드코딩 금지, 기존 패턴 준수, 스크립트 작성 규칙 -> `CODE_STYLE.md`
- R4 인간 검수용 HTML 보고서, 증거 번들, "주니어에게 설명하듯" 보고 규칙 -> `REPORTING.md`
- 사용자 질의 시 항목에 번호 붙이기, 케이스가 10개를 넘으면 검수용 HTML 문서를 만든다 -> `REPORTING.md`

## 유지 규칙

- 문서를 추가하거나 상태를 바꾸면 이 표와 `AGENTS.md`의 라우터를 함께 갱신한다.
- 라우터에 없는 문서를 만들지 않는다. 만들었다면 라우터에 등록하거나 `historical`로 표시한다.
- 절차가 두 단계를 넘어가면 `AGENTS.md`가 아니라 여기 등록된 문서에 쓴다.
