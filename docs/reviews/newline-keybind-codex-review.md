# Codex 리뷰 — 줄바꿈 키바인딩 (R5)

`omc ask codex` 로 `feat/newline-keybind` 를 검토한 결과다. 아홉 건 전부 이 저장소에서 직접
재현한 뒤 고쳤다. 원본 아티팩트는 `.omc/artifacts/ask/` 에 있다(추적하지 않는다).

앞선 정적 검토(`newline-keybind-static-review.md`)와 같은 패턴이 반복됐다 — **아홉 건 모두
어떤 픽스처도 시드하지 않는 분기**에 있었고, 그동안 세 러너가 전부 초록이었다. 그중 셋은
앞선 검토에서 고쳤다고 적은 항목이 절반만 고쳐진 것이었다.

## 확정 결함과 수정

| # | 심각도 | 결함 | 수정 | 회귀 테스트 |
| --- | --- | --- | --- | --- |
| 1 | HIGH | uninstall 이 사용자 소유 Claude/Codex 키를 지우고, 설치가 덮어쓴 값을 복원하지 않음 | 영수증에 있는 키만 제거. 설치가 덮어쓴 값은 `claude_overwrote` 에 남겨 복원. 이미 있던 키는 영수증에 적지 않음 | `test_uninstall_restores_claude_value_overwritten_by_install`, `test_uninstall_does_not_remove_codex_chords_absent_from_manifest` |
| 2 | HIGH | 점 표기 TOML 을 유효하지 않게 만듦 | 편집기를 경로 인식 방식으로 재작성 — 섹션 헤더와 점 표기 키를 같은 경로로 해석한다 | `test_dotted_codex_toml_stays_valid` (4개 형태) |
| 3 | HIGH | shift-enter 설치가 사용자의 ctrl+enter WT 항목을 삭제 | 시퀀스에 더해 **소유권**(지금 쓰는 키이거나 영수증에 있는 이전 키)까지 봐야 제거 | `test_wt_user_entries_for_unchosen_key_are_kept` |
| 4 | HIGH | 원자적 쓰기가 심볼릭 링크를 끊고 권한을 완화 | 링크는 실체를 찾아 쓰고, 교체 전 `shutil.copymode` 로 권한 이전 | `test_keeps_symlink_intact_and_preserves_permissions` |
| 5 | MEDIUM | 부분 복구가 영수증을 줄여 uninstall 이 우리 줄을 남김 | `union_receipt` 로 영수증을 합집합 누적 | `test_manifest_remembers_both_lines_after_partial_repair` |
| 6 | MEDIUM | 주석의 `extended-keys` 가 tmux 설정을 통째로 막음 | 주석을 뗀 뒤 실제 명령만 검사 | `test_tmux_comments_do_not_count_as_config` |
| 7 | MEDIUM | tmux 설치 경로가 백업·원자적 쓰기를 안 씀 | 설치 경로도 `write_text_atomic` 사용 | `test_tmux_also_leaves_a_backup` |
| 8 | MEDIUM | WT Preview/Canary/비패키지 설치를 못 찾음 | `default_wt_paths()` 가 후보 넷을 반환하고 존재하는 것을 고름. `local` 인자를 받아 플랫폼과 무관하게 검증 가능 | `test_wt_default_paths_also_find_non_stable` |
| 9 | MEDIUM | `--hooks --uninstall` 이 키바인딩까지 제거 (결정 4 위반) | 제거도 설치와 같은 범위 규칙을 따른다 | `test_hooks_uninstall_leaves_keybindings_untouched` |

## 앞선 검토에서 절반만 고쳤던 것

- **#4 는 앞선 검토가 만든 회귀다.** 백업·원자적 쓰기를 요구사항으로 승격하면서 `tmp.write_text()`
  + `os.replace()` 를 넣었는데, 그것이 심볼릭 링크를 일반 파일로 바꾸고 새 파일의 기본 권한을
  씌운다. dotfile 관리자로 링크된 설정이 끊기고 `0600` 설정이 `0644` 가 된다. 그때 붙인 회귀
  테스트는 백업 내용과 임시 파일만 봤지 파일 메타데이터를 보지 않았다.
- **#3** 은 페이로드 검사만 넣고 소유권·선택키 검사를 넣지 않았다. 게다가 그때 "강화" 한 단언이
  오히려 파괴적 동작을 고정하고 있었다.
- **#7** 은 tmux 의 uninstall 분기만 원자적 쓰기로 바꾸고 설치 분기를 놓쳤다.

## 설계 판단 하나

WT 에서 `shift-enter` 를 골랐는데 사용자가 Shift+Enter 에 직접 SSoT 시퀀스를 걸어 둔 경우,
어휘 5("C=shift-enter 면 shift+enter sendInput 없음")와 핵심 결정 5("고르지 않은 키를
언바인드하지 않는다")가 부딪힌다. WT 는 이 키를 네이티브로 구분하므로 그대로 두면 줄이 두 번
생긴다. **지우지 않고 경고만 한다** — 어휘 5 는 우리 설치 결과에 대한 사후조건이지 사용자
항목을 지우라는 지시가 아니고, 남의 설정을 말없이 지우는 쪽이 더 나쁘다.

## 검증

| 러너 | 결과 |
| --- | --- |
| pytest (Windows) | 610 passed · 1 failed |
| pytest (WSL Ubuntu 24.04) | **661 passed · 0 failed** |
| Pester | 25 / 25 |

Windows 의 1건은 `test_벤더링된_questionary가_실제로_프롬프트를_만들_수_있다` 로, 진짜 Windows
콘솔 스크린 버퍼가 필요해 이 도구 환경에서는 돌 수 없다(`NoConsoleScreenBufferError`).
이 기능과 무관하며 실제 터미널에서 확인이 필요하다.
