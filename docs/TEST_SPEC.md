# TEST_SPEC

> 범위: 2026-10-13 에 승인한 ai-setup 편입 범위만 다룬다. 목록의 추가·수정·삭제는 사용자만 닫는다.
> 기존 기능의 수용 케이스는 아직 이 문서에 없다. 아래 ID 는 기존 케이스와 겹치지 않게 `AI-` 접두를 쓴다.
> 모든 케이스는 격리된 임시 HOME 과 PATH 앞의 스텁 실행 파일(호출 인자를 기록)로 검증한다. 실제 사용자 홈과 실제 설치기는 쓰지 않는다.

## 수용 케이스

### doctor

AI-1~AI-6 은 jarvis DOCTOR-1~6 으로 옮김.

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-68 | WHEN `--doctor`(`-Doctor`)를 실행하면 THE SYSTEM SHALL 점검을 실행하지 않고 홈에 아무것도 쓰지 않으며, doctor 는 jarvis 가 맡는다고 안내한 뒤 종료 코드 1 로 끝난다 | `tests/test_stages.py::test_doctor_pointer_names_the_jarvis_doctor_module`, bats `setup.sh and install.sh --doctor point to jarvis and write nothing`, Pester `-Doctor and --doctor point to jarvis and write nothing`, Pester `-Doctor and --doctor point to jarvis before downloading` | GREEN (Pester 는 Linux pwsh; Windows PowerShell 5.1 미검증) |

### update-ai

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-7 | WHEN `update-ai --check` 를 실행하면 THE SYSTEM SHALL 현재·최신 버전만 보고하고 업데이트 명령을 호출하지 않는다 | `test_check_only_reads_versions_and_never_updates`, bats `update-ai.sh --check` | GREEN |
| AI-8 | WHEN 카탈로그의 도구가 설치되어 있지 않으면 THE SYSTEM SHALL 그 도구를 건너뛰고 설치 명령을 호출하지 않는다 | `test_missing_tools_are_skipped_without_installing` | GREEN |
| AI-9 | WHEN 대상의 세션이 실행 중이고 그 설치가 버전별 배치(native 버전 디렉터리, npm-release, brew)이면 THE SYSTEM SHALL `--allow-interrupt` 없이 업데이트한다 | `test_running_harness_with_a_versioned_install_is_updated_without_allow_interrupt`, `tests/test_npm_release.py::test_update_ai_updates_an_npm_release_install_while_its_session_runs` | GREEN (Linux; Windows 미검증) |
| AI-10 | WHEN 다른 update-ai 가 lock 을 잡고 있으면 THE SYSTEM SHALL 아무것도 업데이트하지 않고 종료하며, lock 의 PID 가 죽어 있으면 lock 을 회수하고 진행한다 | `test_live_lock_stops_the_run_and_dead_lock_is_reclaimed` | GREEN |
| AI-11 | WHEN `--only a,b` 를 주면 THE SYSTEM SHALL a, b 만 업데이트한다 | `test_only_updates_the_chosen_targets`, `test_unknown_only_target_is_rejected` | GREEN |
| AI-12 | WHEN 어느 한 항목이라도 업데이트에 실패하면 THE SYSTEM SHALL 나머지를 계속 진행하고 결과 표를 출력한 뒤 exit 1 로 끝낸다 | `test_one_failure_does_not_stop_the_rest_and_exits_1` | GREEN |
| AI-13 | WHEN npm 으로 설치된 하네스를 업데이트하면 THE SYSTEM SHALL 그 실행 파일을 설치한 npm(같은 node 접두 경로)을 사용한다 | `test_npm_harness_is_updated_with_the_npm_that_installed_it` | GREEN |
| AI-56 | WHEN 실행 중 세션이 쓰는 설치가 버전별 배치가 아니면(npm -g, winget portable) THE SYSTEM SHALL 그 대상을 바꾸지 않고 보류로 보고하며 옮기는 방법을 안내한다 | `test_running_session_of_an_in_place_npm_install_defers_the_update`, `test_session_detection` | GREEN (Linux; Windows 미검증) |
| AI-57 | WHEN npm-release 로 설치하거나 업데이트하면 THE SYSTEM SHALL 새 버전을 버전 디렉터리에 완성한 뒤에만 `current` 를 원자적으로 바꾸고, 이미 있는 셔임은 다시 쓰지 않는다 | `tests/test_npm_release.py::test_update_switches_current_only_after_the_new_version_is_complete_and_never_rewrites_the_shim` | GREEN (Linux; Windows 미검증) |
| AI-58 | WHEN npm-release 가 이전 버전을 정리하면 THE SYSTEM SHALL current, previous, 그리고 실행 중인 프로세스가 쓰는 버전을 남기고, 프로세스 목록을 읽을 수 없으면 아무것도 지우지 않는다 | `tests/test_npm_release.py::test_prune_keeps_current_previous_and_versions_a_running_session_uses` | GREEN (Linux; Windows 미검증) |
| AI-59 | WHEN npm-release 설치 시 같은 패키지의 npm -g 사본이 있으면 THE SYSTEM SHALL 그 사본을 쓰는 프로세스가 없을 때만 제거하고, 있으면 남긴 뒤 보고한다 | `tests/test_npm_release.py::test_old_global_copy_is_removed_only_when_no_process_uses_it` | GREEN (POSIX 만; Windows 는 셔임 위치가 달라 해당 테스트 건너뜀) |
| AI-60 | WHEN 셔임 경로에 ai-setup 셔임도 아니고 그 패키지의 npm 링크도 아닌 파일이 있으면 THE SYSTEM SHALL 덮어쓰지 않고 실패한다 | `tests/test_npm_release.py::test_a_file_ai_setup_did_not_write_at_the_shim_path_is_never_overwritten` | GREEN (Linux; Windows 미검증) |
| AI-61 | WHEN npm-release 대상을 uninstall 하면 THE SYSTEM SHALL 셔임과 사용 중이 아닌 버전만 지우고, 남긴 버전을 보고한다 | `tests/test_npm_release.py::test_uninstall_removes_the_shim_and_keeps_only_a_version_still_in_use` | GREEN (Linux; Windows 미검증) |
| AI-62 | WHEN brew 로 설치된 대상을 업데이트하면 THE SYSTEM SHALL `HOMEBREW_NO_INSTALL_CLEANUP=1` 을 주고 실행한다 | `test_brew_update_keeps_the_old_version_for_running_sessions` | GREEN (단위; macOS 실측 전) |

### 하네스·도구 설치

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-14 | WHEN 선택한 하네스가 이미 설치되어 있으면 THE SYSTEM SHALL 설치 명령을 호출하지 않고 영수증에 기록하지 않는다 | | 미착수 |
| AI-15 | WHEN 선택한 하네스가 없으면 THE SYSTEM SHALL 현재 플랫폼의 카탈로그 설치 명령을 호출하고 성공하면 영수증에 기록한다 | | 미착수 |
| AI-16 | WHEN 하네스의 선행 조건(예: Node 버전)이 맞지 않으면 THE SYSTEM SHALL 설치하지 않고 필요한 조건을 안내한다 | | 미착수 |
| AI-17 | WHEN `--dry-run` 과 함께 설치 단계를 실행하면 THE SYSTEM SHALL 호출할 명령만 출력하고 아무것도 실행하지 않는다 | | 미착수 |
| AI-34 | WHEN `--install-harness` 를 `--uninstall` 과 함께 실행하면 THE SYSTEM SHALL 영수증에 기록된 항목만 기록된 설치 방식의 제거 명령으로 지우고, 원래 있던 항목과 설정·인증 디렉터리는 남긴다 | | 미착수 |
| AI-35 | WHEN sudo 가 필요한 설치 명령을 실행하기 전이면 THE SYSTEM SHALL 명령 전체를 출력하고, 표준 입력이 TTY 가 아니면 실행하지 않고 건너뛴 것으로 보고한다 | | 미착수 |
| AI-36 | WHEN 인자 없이 비대화형으로 실행하면 THE SYSTEM SHALL 새 단계를 하나도 실행하지 않는다 | | 미착수 |
| AI-65 | WHEN `update-ai` 가 확인한 설치본이 최신 릴리스와 같거나 더 새로우면 THE SYSTEM SHALL `--check` 와 갱신 뒤 검사 모두에서 최신으로 판정한다 | `tests/test_update_ai.py::test_an_install_newer_than_the_latest_release_counts_as_up_to_date` | GREEN (단위) |
| AI-66 | WHEN `--tools orca`(`-Tools orca`), `--orca-desktop` 또는 `update-ai orca` 를 실행하면 THE SYSTEM SHALL Orca 패키지·서버·스킬·영수증 기록을 바꾸지 않고 Orca 는 jarvis 가 관리한다고 안내한 뒤 종료 코드 1 로 끝난다 (ORCA-12) | `tests/test_stages.py::test_orca_desktop_points_to_jarvis_and_changes_nothing`, `tests/test_update_ai.py::test_update_ai_orca_points_to_jarvis_and_updates_nothing`, `tests/test_update_ai.py::test_plain_update_ai_does_not_list_orca`, bats `setup.sh and install.sh Orca options point to jarvis and change nothing`, Pester `-Tools orca, --tools orca and --orca-desktop point to jarvis and change nothing`, Pester `-Tools orca and --orca-desktop point to jarvis before downloading` | GREEN |
| AI-67 | WHEN tools 단계나 `--stages all --uninstall` 을 실행하면 THE SYSTEM SHALL Orca 를 설치·제거하지 않고 영수증의 `tool_installs.orca`·`tool_installs.orca_server` 를 그대로 둔다(jarvis 의 Orca 모듈이 같은 키를 읽고 제거한다) | `tests/test_stages.py::test_tools_and_full_uninstall_leave_orca_and_its_receipt_records_to_jarvis`, bats `setup.sh --uninstall keeps the Orca receipt records for jarvis`, Pester `-Hooks -Uninstall keeps the Orca receipt records for jarvis` | GREEN |

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
| AI-28 | WHEN mcp 단계를 계획하면 THE SYSTEM SHALL 선택된 하네스마다 SPEC 의 CodeGraph user scope 등록 명령(`codegraph serve --mcp`)을 액션으로 내고, 패키지 액션보다 뒤에 둔다. 실제 등록 호출과 영수증 기록은 아직 이 케이스의 실행 경로가 아니다 | `test_mcp_registration_uses_codegraph_serve_for_each_selected_harness` | 미착수 |
| AI-29 | WHEN 같은 이름의 MCP 서버가 이미 등록되어 있으면 THE SYSTEM SHALL 덮어쓰지 않고 영수증에 기록하지 않는다 | | 미착수 |
| AI-30 | WHEN OpenCode 설정에 MCP 를 등록하면 THE SYSTEM SHALL `mcp.<name>` 키만 추가하고 나머지 키·플러그인 항목을 보존하며, 파싱할 수 없으면 쓰기 전에 멈춘다 | | 미착수 |
| AI-31 | WHEN `--mcp --uninstall` 을 실행하면 THE SYSTEM SHALL 영수증에 기록된 하네스·서버 쌍만 제거한다 | | 미착수 |

### 공통

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-32 | WHEN 새 단계를 설치한 뒤 같은 명령을 다시 실행하면 THE SYSTEM SHALL 추가 변경 없이 끝난다 (멱등) | | 미착수 |
| AI-33 | WHEN 새 단계가 하네스 설정을 쓸 때 다른 도구가 넣은 훅·플러그인 항목이 있으면 THE SYSTEM SHALL 그 항목을 그대로 보존한다 | | 미착수 |
| AI-41 | WHEN 전체 단계 선택을 계획하면 THE SYSTEM SHALL CodeGraph npm 패키지 액션을 MCP 등록보다 앞에 두고 graft 또는 Trail 설치 명령을 내지 않는다 | `test_full_selection_orders_codegraph_package_before_mcp` | GREEN |
| AI-42 | WHEN 인자 없이 TTY 또는 CI 가 아니면 THE SYSTEM SHALL 아무것도 설치하지 않는다 | `test_ci_skips_onboarding_and_installs_all_with_shift_enter` | GREEN |
| AI-43 | WHEN 같은 단계 선택을 첫 계획이 만든 상태에 다시 계획하면 THE SYSTEM SHALL 추가 쓰기 액션을 내지 않는다 | `test_second_plan_against_post_state_does_not_write` | GREEN |
| AI-44 | WHEN Jarvis 역할을 고르지 않으면 THE SYSTEM SHALL Jarvis 설치를 계획하지 않고, Tailscale 제거는 logout 을 포함하지 않으며, 기록하지 않은 Jarvis 유닛은 지우지 않는다 | `test_jarvis_herdr_and_setcap_follow_explicit_choice`, `test_uninstall_removes_only_recorded_units_and_packages` | GREEN |
| AI-45 | WHEN 첫 실행에서 Skip 을 고르면 THE SYSTEM SHALL 아무것도 설치하지 않고 카테고리 허브를 열며, 허브에서 바꾼 선택은 Apply 를 고를 때만 답으로 기록한다 | `test_skip_opens_hub_and_apply_records_the_edited_selection` | GREEN |
| AI-46 | WHEN 영수증이 있는 머신에서 인자 없이 TTY 로 실행하면 THE SYSTEM SHALL 산책 질문 없이 허브부터 연다 | `test_receipt_opens_hub_without_the_walk` | GREEN |
| AI-47 | WHEN 허브에서 Quit 을 고르거나 모든 단계를 끈 채 Apply 하면 THE SYSTEM SHALL 아무것도 설치하지 않는다 | `test_skip_then_quit_selects_nothing`, `test_apply_with_every_stage_off_selects_nothing` | GREEN |

상태는 `미착수` / `RED` / `GREEN` 중 하나다. 러너가 없어 건너뛴 것은 `GREEN`이 아니다.

## 범위 밖

- 실제 네트워크 설치·업데이트의 성공 여부: 자동 테스트는 스텁으로 호출 명령만 검증한다. 실제 동작은 장비 3대에서 수동 실측으로 확인한다.
- 영수증 드리프트 수정: doctor 의 보고(jarvis DOCTOR-4)까지만 범위다.

## 미검증

- `copilot mcp add` 문법은 문서로만 확인했다(설치된 장비 없음).
- `agy` 의 Windows 경로와 MCP 설정 파일 위치는 문서에 없다.
- `skills` CLI 의 Windows junction 생성과 SHA 고정 항목의 update 동작은 소스로만 확인했다.
