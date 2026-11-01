# TEST_SPEC

> 상태: 2026-11-01 ai-setup 의 기능을 모두 jarvis 로 옮겼다(jarvis `docs/2026-10-30-ai-setup-absorption.md`). 옮긴 수용 케이스는 jarvis `docs/TEST_SPEC.md` 가 소유한다. 목록의 추가·수정·삭제는 사용자만 닫는다.
> 모든 케이스는 격리된 임시 HOME 으로 검증한다. 실제 사용자 홈과 실제 설치기는 쓰지 않는다.

## 수용 케이스

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-70 | WHEN 예전 진입점(`install.sh`·`install.ps1`·`scripts/setup.sh`·`scripts/setup.ps1`·`scripts/update-ai.sh`·`scripts/Update-Ai.ps1`)을 어떤 인자로 실행하면 THE SYSTEM SHALL 홈에 아무것도 쓰지 않고 jarvis 의 setup 모듈(과 harness·hooks·orca·doctor 모듈, `jarvis agentsmd`)을 안내한 뒤 종료 코드 1 로 끝나며, `irm \| iex` 로 실행한 install.ps1 은 셸을 닫지 않는다 (예전 AI-66·68·69 를 포함한다) | bats `tests/setup.bats`, Pester `tests/Setup.Tests.ps1` | GREEN (Linux 의 bash·pwsh. Windows PowerShell 5.1 미검증) |

## 옮긴 케이스 (jarvis)

| 예전 ID | jarvis ID |
| --- | --- |
| AI-1~AI-6 | DOCTOR-1~7 |
| AI-7~AI-13, AI-56~AI-62, AI-65 | HARNESS-4~HARNESS-18 |
| AI-14~AI-17, AI-34, AI-35, AI-67, AI-19~AI-33, AI-38~AI-41, AI-43, AI-44 | SETUP-7~SETUP-35 |
| AI-36, AI-42 | SETUP-13(옮긴 setup.sh 는 인자 없이 실행하면 jarvis 를 안내하고 종료 코드 1) |
| AI-45~AI-47(온보딩) | 옮기지 않음. core 홈의 AI 셋업 화면이 대신한다 |
| AI-48~AI-55c, AI-64 | ORCA-1~13 |
| 훅 | HOOKS-1~4 |
| 문서에 없던 옛 케이스(`covers: Test-n`, 줄바꿈 키·AGENTS.md) | jarvis 로 옮긴 테스트(`tests/test_keybinds.py`, bats·Pester)의 docstring 에 그대로 남음 |

상태는 `미착수` / `RED` / `GREEN` 중 하나다. 러너가 없어 건너뛴 것은 `GREEN`이 아니다.
