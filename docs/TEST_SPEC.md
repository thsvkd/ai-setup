# TEST_SPEC

> 범위: 2026-10-13 에 승인한 ai-setup 편입 범위만 다룬다. 목록의 추가·수정·삭제는 사용자만 닫는다.
> 기존 기능의 수용 케이스는 아직 이 문서에 없다. 아래 ID 는 기존 케이스와 겹치지 않게 `AI-` 접두를 쓴다.
> 모든 케이스는 격리된 임시 HOME 과 PATH 앞의 스텁 실행 파일(호출 인자를 기록)로 검증한다. 실제 사용자 홈과 실제 설치기는 쓰지 않는다.

## 수용 케이스

### doctor

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-1 | WHEN `--doctor` 를 실행하면 THE SYSTEM SHALL 홈 아래 어떤 파일도 만들거나 바꾸지 않는다 | `test_doctor_writes_nothing_under_home`, bats·Pester `--doctor` | GREEN |
| AI-2 | WHEN 카탈로그의 하네스가 PATH 에 있으면 THE SYSTEM SHALL 그 이름과 버전을 보고하고, 없으면 그 플랫폼의 설치 명령을 안내한다 | `test_reports_installed_harness_version_and_install_hint_for_missing` | GREEN |
| AI-3 | WHEN 같은 하네스 실행 파일이 PATH 에 두 개 이상 있으면 THE SYSTEM SHALL 중복 설치로 보고하고 어느 쪽이 우선인지 표시한다 | `test_duplicate_harness_on_path_is_reported_with_the_winner`, `test_same_directory_twice_on_path_is_not_a_duplicate` | GREEN |
| AI-4 | WHEN 영수증이 은퇴로 표시한 훅이 어느 하네스 설정에 아직 연결되어 있으면 THE SYSTEM SHALL 드리프트로 보고한다 | `test_retired_hook_still_wired_in_another_harness_is_drift`, `test_current_hook_is_not_drift`, `test_hook_the_receipt_lists_as_retired_is_drift` | GREEN |
| AI-5 | WHEN 하네스 설정 파일에 토큰·키처럼 보이는 평문 값이 있으면 THE SYSTEM SHALL 파일 위치와 키 이름만 보고하고 값은 출력하지 않는다 | `test_plaintext_secret_reports_location_and_key_but_never_the_value`, `test_keys_that_only_mention_a_secret_word_are_not_reported`, `test_bearer_values_are_reported_whatever_the_key_is_called`, `test_common_secret_shapes_are_reported_without_values`, `test_header_mapped_to_an_environment_variable_name_is_not_reported` | GREEN |
| AI-6 | WHEN `~/.agents/skills` 에 lock 파일에 없는 스킬 디렉터리가 있으면 THE SYSTEM SHALL 그 이름을 보고하고 지우지 않는다 | `test_skill_outside_lock_is_reported_and_kept`, bats·Pester `--doctor` | GREEN |

### update-ai

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-7 | WHEN `update-ai --check` 를 실행하면 THE SYSTEM SHALL 현재·최신 버전만 보고하고 업데이트 명령을 호출하지 않는다 | `test_check_only_reads_versions_and_never_updates`, bats `update-ai.sh --check` | GREEN |
| AI-8 | WHEN 카탈로그의 도구가 설치되어 있지 않으면 THE SYSTEM SHALL 그 도구를 건너뛰고 설치 명령을 호출하지 않는다 | `test_missing_tools_are_skipped_without_installing` | GREEN |
| AI-9 | WHEN 대상 하네스의 프로세스가 실행 중이고 `--allow-interrupt` 가 없으면 THE SYSTEM SHALL 그 하네스를 업데이트하지 않고 실패로 보고한다 | `test_running_harness_is_not_updated_without_allow_interrupt` | GREEN |
| AI-10 | WHEN 다른 update-ai 가 lock 을 잡고 있으면 THE SYSTEM SHALL 아무것도 업데이트하지 않고 종료하며, lock 의 PID 가 죽어 있으면 lock 을 회수하고 진행한다 | `test_live_lock_stops_the_run_and_dead_lock_is_reclaimed` | GREEN |
| AI-11 | WHEN `--only a,b` 를 주면 THE SYSTEM SHALL a, b 만 업데이트한다 | `test_only_updates_the_chosen_targets`, `test_unknown_only_target_is_rejected` | GREEN |
| AI-12 | WHEN 어느 한 항목이라도 업데이트에 실패하면 THE SYSTEM SHALL 나머지를 계속 진행하고 결과 표를 출력한 뒤 exit 1 로 끝낸다 | `test_one_failure_does_not_stop_the_rest_and_exits_1` | GREEN |
| AI-13 | WHEN npm 으로 설치된 하네스를 업데이트하면 THE SYSTEM SHALL 그 실행 파일을 설치한 npm(같은 node 접두 경로)을 사용한다 | `test_npm_harness_is_updated_with_the_npm_that_installed_it` | GREEN |

### 하네스·도구 설치

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-14 | WHEN 선택한 하네스가 이미 설치되어 있으면 THE SYSTEM SHALL 설치 명령을 호출하지 않고 영수증에 기록하지 않는다 | | 미착수 |
| AI-15 | WHEN 선택한 하네스가 없으면 THE SYSTEM SHALL 현재 플랫폼의 카탈로그 설치 명령을 호출하고 성공하면 영수증에 기록한다 | | 미착수 |
| AI-16 | WHEN 하네스의 선행 조건(예: Node 버전)이 맞지 않으면 THE SYSTEM SHALL 설치하지 않고 필요한 조건을 안내한다 | | 미착수 |
| AI-17 | WHEN `--dry-run` 과 함께 설치 단계를 실행하면 THE SYSTEM SHALL 호출할 명령만 출력하고 아무것도 실행하지 않는다 | | 미착수 |
| AI-18 | WHEN `--tools orca` 를 macOS·Windows·Linux 에서 실행하면 THE SYSTEM SHALL 각각 brew cask(tap stablyai/orca), winget `StablyAI.Orca`, GitHub 릴리스 패키지 경로를 선택한다 | | 미착수 |
| AI-34 | WHEN `--install-harness`·`--tools` 를 `--uninstall` 과 함께 실행하면 THE SYSTEM SHALL 영수증에 기록된 항목만 기록된 설치 방식의 제거 명령으로 지우고, 원래 있던 항목과 설정·인증 디렉터리는 남긴다 | | 미착수 |
| AI-35 | WHEN sudo 가 필요한 설치 명령을 실행하기 전이면 THE SYSTEM SHALL 명령 전체를 출력하고, 표준 입력이 TTY 가 아니면 실행하지 않고 건너뛴 것으로 보고한다 | | 미착수 |
| AI-36 | WHEN 인자 없이 비대화형으로 실행하면 THE SYSTEM SHALL 새 단계를 하나도 실행하지 않는다 | | 미착수 |
| AI-37 | WHEN `--tools orca` 로 Orca 를 설치하면 THE SYSTEM SHALL 카탈로그에 묶인 orca 스킬도 설치해 영수증에 기록하고, `--skills` 만 실행할 때는 orca 스킬을 설치하지 않는다 | | 미착수 |

### 플러그인

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-19 | WHEN 선택한 플러그인이 이미 설치되어 있으면 THE SYSTEM SHALL 다시 설치하지 않고 영수증에 기록하지 않는다 | | 미착수 |
| AI-20 | WHEN 플러그인의 마켓플레이스가 등록되어 있지 않으면 THE SYSTEM SHALL 마켓플레이스를 추가한 뒤 user scope 로 설치하고 둘 다 영수증에 기록한다 | | 미착수 |
| AI-21 | WHEN `--plugins --uninstall` 을 실행하면 THE SYSTEM SHALL 영수증에 기록된 플러그인·마켓플레이스만 제거하고 원래 있던 것은 남긴다 | | 미착수 |
| AI-22 | WHEN 기존 `--omc` 또는 `--output-style` 로 실행하면 THE SYSTEM SHALL 이전과 같은 플러그인과 설정 변경을 만든다 | | 미착수 |

### 외부 스킬

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-23 | WHEN `--skills` 를 실행하면 THE SYSTEM SHALL `sources.json` 의 선택된 스킬마다 `skills add` 를 고정 ref 와 비대화형 플래그로 호출한다 | | 미착수 |
| AI-24 | WHEN `~/.agents/.skill-lock.json` 을 파싱할 수 없거나 version 이 3 미만이면 THE SYSTEM SHALL 외부 스킬 단계를 쓰기 전에 중단한다 | | 미착수 |
| AI-25 | WHEN `npx` 가 없으면 THE SYSTEM SHALL 외부 스킬만 건너뛰고 번들 스킬 설치는 그대로 진행한다 | | 미착수 |
| AI-26 | WHEN `--skills --uninstall` 을 실행하면 THE SYSTEM SHALL 영수증에 기록된 외부 스킬만 `skills remove` 로 제거하고 번들 스킬은 기존 규칙대로 되돌린다 | | 미착수 |
| AI-38 | WHEN `--prune-skills` 를 대화형으로 실행하면 THE SYSTEM SHALL lock 에 없는 실제 디렉터리만 후보로 보여 주고, 승인한 항목만 휴지통으로 옮기며 그 항목을 가리키던 하네스 링크를 지운다 | | 미착수 |
| AI-39 | WHEN `--prune-skills` 의 후보를 고를 때 THE SYSTEM SHALL lock 에 있는 스킬과 심볼릭 링크·junction 인 스킬을 후보에서 제외한다 | | 미착수 |
| AI-40 | WHEN `--prune-skills` 를 비대화형으로 실행하면 THE SYSTEM SHALL 아무것도 옮기지 않고 exit 1 로 끝낸다 | | 미착수 |
| AI-27 | WHEN 플러그인 목록이 어떤 스킬을 `provides_skills` 로 제공하면 THE SYSTEM SHALL 그 스킬을 `skills` CLI 로 중복 설치하지 않는다 | | 미착수 |

### MCP

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-28 | WHEN `--mcp` 를 실행하면 THE SYSTEM SHALL 설치된 하네스마다 SPEC 의 user scope 등록 명령을 호출하고 하네스별로 영수증에 기록한다 | | 미착수 |
| AI-29 | WHEN 같은 이름의 MCP 서버가 이미 등록되어 있으면 THE SYSTEM SHALL 덮어쓰지 않고 영수증에 기록하지 않는다 | | 미착수 |
| AI-30 | WHEN OpenCode 설정에 MCP 를 등록하면 THE SYSTEM SHALL `mcp.<name>` 키만 추가하고 나머지 키·플러그인 항목을 보존하며, 파싱할 수 없으면 쓰기 전에 멈춘다 | | 미착수 |
| AI-31 | WHEN `--mcp --uninstall` 을 실행하면 THE SYSTEM SHALL 영수증에 기록된 하네스·서버 쌍만 제거한다 | | 미착수 |

### 공통

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-32 | WHEN 새 단계를 설치한 뒤 같은 명령을 다시 실행하면 THE SYSTEM SHALL 추가 변경 없이 끝난다 (멱등) | | 미착수 |
| AI-33 | WHEN 새 단계가 하네스 설정을 쓸 때 다른 도구가 넣은 훅·플러그인 항목이 있으면 THE SYSTEM SHALL 그 항목을 그대로 보존한다 | | 미착수 |

상태는 `미착수` / `RED` / `GREEN` 중 하나다. 러너가 없어 건너뛴 것은 `GREEN`이 아니다.

## 범위 밖

- 실제 네트워크 설치·업데이트의 성공 여부: 자동 테스트는 스텁으로 호출 명령만 검증한다. 실제 동작은 장비 3대에서 수동 실측으로 확인한다.
- Orca 헤드리스 서버(R9, 선택): 범위가 확정되면 케이스를 추가한다.
- 영수증 드리프트 수정: doctor 의 보고(AI-4)까지만 범위다.

## 미검증

- `copilot mcp add` 문법은 문서로만 확인했다(설치된 장비 없음).
- `agy` 의 Windows 경로와 MCP 설정 파일 위치는 문서에 없다.
- `skills` CLI 의 Windows junction 생성과 SHA 고정 항목의 update 동작은 소스로만 확인했다.
