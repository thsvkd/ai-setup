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
| AI-63 | WHEN Orca deb 세션이 실행 중이고 `--allow-interrupt` 가 없으면 THE SYSTEM SHALL Orca 패키지를 설치하지 않고 보류로 보고한다 | `test_orca_deb_is_not_installed_under_a_running_session_without_allow_interrupt` | GREEN |

### 하네스·도구 설치

| ID | 케이스 | 테스트 | 상태 |
| -- | ------ | ------ | ---- |
| AI-14 | WHEN 선택한 하네스가 이미 설치되어 있으면 THE SYSTEM SHALL 설치 명령을 호출하지 않고 영수증에 기록하지 않는다 | | 미착수 |
| AI-15 | WHEN 선택한 하네스가 없으면 THE SYSTEM SHALL 현재 플랫폼의 카탈로그 설치 명령을 호출하고 성공하면 영수증에 기록한다 | | 미착수 |
| AI-16 | WHEN 하네스의 선행 조건(예: Node 버전)이 맞지 않으면 THE SYSTEM SHALL 설치하지 않고 필요한 조건을 안내한다 | | 미착수 |
| AI-17 | WHEN `--dry-run` 과 함께 설치 단계를 실행하면 THE SYSTEM SHALL 호출할 명령만 출력하고 아무것도 실행하지 않는다 | | 미착수 |
| AI-18 | WHEN `--tools orca` 를 macOS·Windows·Linux 에서 실행하면 THE SYSTEM SHALL 공식 `/Applications/Orca.app`, Windows 사용자 설치본, 공식 deb 경로를 선택한다 (2026-10-21 플랫폼별 설치 방식 적용) | `test_official_package_selection` | GREEN (플랫폼별 선택 검증) |
| AI-34 | WHEN `--install-harness`·`--tools` 를 `--uninstall` 과 함께 실행하면 THE SYSTEM SHALL 영수증에 기록된 항목만 기록된 설치 방식의 제거 명령으로 지우고, 원래 있던 항목과 설정·인증 디렉터리는 남긴다 | | 미착수 |
| AI-35 | WHEN sudo 가 필요한 설치 명령을 실행하기 전이면 THE SYSTEM SHALL 명령 전체를 출력하고, 표준 입력이 TTY 가 아니면 실행하지 않고 건너뛴 것으로 보고한다 | | 미착수 |
| AI-36 | WHEN 인자 없이 비대화형으로 실행하면 THE SYSTEM SHALL 새 단계를 하나도 실행하지 않는다 | | 미착수 |
| AI-37 | WHEN `--tools orca` 로 Orca 를 설치하면 THE SYSTEM SHALL 카탈로그에 묶인 orca 스킬도 설치해 영수증에 기록하고, `--skills` 만 실행할 때는 orca 스킬을 설치하지 않는다 | | 미착수 |
| AI-48 | WHEN `--tools orca` 를 실행하면 THE SYSTEM SHALL 원본 프로필의 서버에 런타임 링크로 별도 프로필의 데스크톱 클라이언트를 먼저 등록하고, 지속 서버 실행 중 현재 유효한 모바일 링크를 보관한다. 데스크톱 앱 실행과 Windows 바로가기 변경은 `--orca-desktop` 을 줄 때만 한다. Windows 는 재부팅 후 서버를 자동 시작한다. 페어링 전과 데스크톱 ID 저장 직후 복구 가능한 영수증을 기록하고, 임시 런타임이 활성인 동안 지속 서비스를 시작하지 않으며 재시도 시 링크 재발급 없이 이어간다. 같은 이름의 미확인 환경은 재사용하지 않는다. ai-setup 소유 활성 구성은 검증 후 재사용하고, 미구성 활성 서버는 재시작하지 않으며 실패 처리한다. 제거는 실행 중인 ai-setup 소유 서비스를 직접 멈춘 뒤 지우고, 그 서비스를 멈춘 뒤에도 남는 서버는 끊지 않고 제거를 거부하며, 프로필 데이터는 보존한다 | `tests/test_orca_server.py::test_issue_pairings_registers_desktop_before_stopping_runtime_offer`, `tests/test_orca_server.py::test_setup_records_pairing_state_and_environment_before_service_start`, `tests/test_orca_server.py::test_setup_keeps_recoverable_pairing_receipt_when_temporary_server_remains_active`, `tests/test_orca_server.py::test_setup_resumes_pairing_receipt_without_reissuing_desktop_offer`, `tests/test_orca_server.py::test_setup_recovers_environment_saved_before_pairing_receipt_id`, `tests/test_orca_server.py::test_issue_pairings_preflight_failure_does_not_start_offer`, `tests/test_orca_server.py::test_service_runner_persists_live_mobile_offer_for_connected_desktop`, `tests/test_orca_server.py::test_windows_service_starts_at_boot_without_stored_credentials`, `tests/test_orca_server.py::test_setup_server_client_does_not_report_an_active_profile_as_configured`, `tests/test_orca_server.py::test_setup_server_client_reuses_active_managed_setup`, `tests/test_orca_server.py::test_setup_server_client_resumes_an_interrupted_managed_setup`, `tests/test_orca_server.py::test_remove_user_service_deletes_only_its_files_and_keeps_extra_contents`, `tests/test_orca_server.py::test_remove_user_service_stops_its_own_running_service_first`, `tests/test_orca_server.py::test_remove_user_service_preserves_a_server_it_does_not_run`, `tests/test_orca_install.py::test_default_setup_pairs_the_desktop_without_opening_the_gui`, `tests/test_orca_install.py::test_existing_install_configures_server_and_records_before_open`, `tests/test_stages.py::test_orca_desktop_app_is_opt_in`, `tests/test_orca_server.py::test_remove_user_service_rejects_symlink_root`, `tests/test_orca_install.py::test_uninstall_preserves_pairing_receipt_when_new_desktop_environment_may_exist`, `tests/test_orca_install.py::test_server_setup_failure_keeps_recoverable_ownership_receipt`, `tests/test_orca_server.py::test_environment_add_refuses_to_reuse_an_unverified_saved_environment`, Windows 임시 S4U 예약 작업 설치·실행·재실행·중지 후 복구·제거 실측(2026-10-26) | RED (Windows 통합 통과; 실제 재부팅·POSIX 서비스 미검증) |
| AI-49 | WHEN Windows 에서 ai-setup 이 Orca 지속 서버를 실행하면 THE SYSTEM SHALL Orca 설치 폴더가 아니라 서비스 디렉터리 아래 ai-setup 소유 복사본에서 서버를 실행해 Orca 설치기(앱 내 업데이트 포함)의 설치 폴더 프로세스 검색에 잡히지 않게 하고, 제거 시 그 복사본도 지운다 (2026-10-27 승인) | `tests/test_orca_server.py::test_windows_service_runs_orca_from_its_own_app_copy_outside_the_install_dir`, `tests/test_orca_server.py::test_new_windows_bundle_runs_the_server_from_app_copies`, `tests/test_orca_server.py::test_remove_user_service_deletes_the_server_app_copies`, `tests/test_orca_server.py::test_remove_user_service_stops_a_runner_waiting_to_restart_its_crashed_server` | GREEN (단위 통과; thsvkd-kgolf 실측 2026-10-28: 서버가 복사본에서 실행, 설치기 판정식의 세션 0 일치 7→0) |
| AI-50 | WHEN Windows 서버 러너가 어떤 이유로든 종료되면(`schtasks /End` 포함) THE SYSTEM SHALL 러너가 띄운 서버 프로세스 트리도 함께 종료한다 | `tests/test_orca_windows.py::test_runner_process_tree_ends_when_the_runner_is_terminated`, `tests/test_orca_server.py::test_windows_service_runs_orca_from_its_own_app_copy_outside_the_install_dir` | GREEN (Windows Job 테스트 통과; thsvkd-kgolf 실제 작업 `/End` 뒤 세션 0 잔여 0·포트 해제, `/Run` 복구) |
| AI-51 | WHEN 서버 실행 중 Orca 설치본이 바뀌면 THE SYSTEM SHALL 살아 있는 터미널이 있거나 확인할 수 없는 동안 서버를 재시작하지 않고, 설치본이 안정되고 새 복사본이 완성된 뒤 터미널이 0개일 때만 그 복사본으로 재시작한다 | `tests/test_orca_server.py::test_windows_service_waits_for_no_live_terminals_before_moving_to_an_updated_install`, `tests/test_orca_server.py::test_windows_service_does_not_move_while_the_install_keeps_changing`, `tests/test_orca_server.py::test_windows_service_does_not_restart_for_a_build_it_could_not_copy` | GREEN (단위 통과; thsvkd-kgolf 실측: 1.4.242 설치 뒤 터미널 0개에서 새 복사본으로 전환) |
| AI-52 | WHEN ai-setup 이 서버 서비스를 멈추려 할 때(제거·재실행 적용) 살아 있는 터미널이 있거나 확인할 수 없으면 THE SYSTEM SHALL 멈추지 않고 거부하며, Job 이 없는 이전 러너의 서비스는 같은 사용자 동의 경로로 그 러너의 자손 트리만 정리한다 | `tests/test_orca_server.py::test_stopping_the_service_refuses_while_the_server_has_live_or_unknown_terminals`, `tests/test_orca_server.py::test_live_terminal_count_reads_the_server_profile_and_treats_failures_as_unknown`, `tests/test_orca_server.py::test_windows_stop_ends_a_legacy_runner_tree_through_the_elevated_helper_only`, `tests/test_orca_server.py::test_stop_asks_the_running_copy_when_the_installed_cli_is_gone`, `tests/test_orca_server.py::test_runner_records_itself_and_exits_instead_of_recreating_a_removed_service` | GREEN (단위 통과; 실측은 예전 러너 트리 정리만. 터미널이 있을 때의 거부는 실측 안 함) |
| AI-53 | WHEN 설치본을 복사할 수 없거나(디스크·권한) 설치가 진행 중이면 THE SYSTEM SHALL 마지막 완성 복사본으로 서버를 계속 실행하고, 완성 복사본이 없으면 경고와 함께 설치 폴더에서 실행한다 | `tests/test_orca_server.py::test_windows_service_keeps_its_last_good_copy_when_the_install_cannot_be_copied`, `tests/test_orca_server.py::test_windows_service_falls_back_to_the_install_when_no_copy_exists`, `tests/test_orca_server.py::test_windows_service_moves_off_the_install_directory_once_a_copy_succeeds`, `tests/test_orca_server.py::test_windows_service_does_not_restart_for_a_build_it_could_not_copy`, `tests/test_orca_server.py::test_windows_service_retries_a_failed_copy_only_after_the_backoff` | GREEN (단위 통과; 실측 안 함) |
| AI-54 | WHEN 구성된 서버가 있는 머신에서 `--tools orca` 를 다시 실행하면 THE SYSTEM SHALL 러너·헬퍼·설정을 갱신하되 예약 작업 정의·서버 프로필·페어링·데스크톱 환경은 보존하고, 실행 중인 서버는 터미널이 0개일 때만 다시 시작한다 | `tests/test_orca_server.py::test_rerun_refreshes_the_service_bundle_and_restarts_only_an_idle_server`, `tests/test_orca_server.py::test_rerun_leaves_an_up_to_date_running_server_alone`, `tests/test_orca_server.py::test_rerun_restarts_a_legacy_runner_whose_files_were_already_refreshed` | GREEN (단위 통과; thsvkd-kgolf 실측: 재실행이 예전 러너를 교체, 작업 정의·영수증·데스크톱 환경 보존) |
| AI-55 | WHEN Windows 에서 `update-ai orca` 를 실행하면 THE SYSTEM SHALL GUI 조작 없이 공식 매니페스트의 크기·SHA-512 를 통과한 설치 파일만 앱 내 업데이트와 같은 `/S --updated` 로 실행해 데스크톱 앱을 올리고, ai-setup 서버가 아직 설치 폴더에서 돌면 설치기를 띄우지 않고 거부하며, 서버는 터미널이 없을 때 새 판으로 옮긴 결과를 보고한다. ai-setup 서버 복사본과 Orca 터미널 호스트는 실행 중인 세션으로 보지 않는다 (2026-10-28 사용자 요청) | `tests/test_update_ai.py::test_orca_windows_update_runs_only_a_verified_installer_as_an_in_app_update`, `tests/test_update_ai.py::test_orca_windows_update_reports_a_server_that_waits_for_its_terminals`, `tests/test_update_ai.py::test_orca_windows_update_refuses_while_the_server_runs_from_the_install_directory`, `tests/test_update_ai.py::test_orca_server_copies_and_terminal_hosts_are_not_sessions_an_update_interrupts`, `tests/test_update_ai.py::test_windows_orca_install_is_updated_with_the_official_installer` | GREEN (단위 통과; thsvkd-kgolf 실측: `update-ai --allow-interrupt orca` 1.4.237→1.4.242, 서버 전환까지. GUI 의 앱 내 업데이트 버튼은 실측 안 함) |

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
- AI-48 의 실제 사용자 로그인 후 자동 시작과 `--orca-desktop` 의 GUI 워크스페이스 표시는 설치 통합 단계에서 검증한다.
- 영수증 드리프트 수정: doctor 의 보고(AI-4)까지만 범위다.

## 미검증

- `copilot mcp add` 문법은 문서로만 확인했다(설치된 장비 없음).
- `agy` 의 Windows 경로와 MCP 설정 파일 위치는 문서에 없다.
- `skills` CLI 의 Windows junction 생성과 SHA 고정 항목의 update 동작은 소스로만 확인했다.
