# CONTEXT.md

이 파일은 모호한 어휘를 고정한다. 구현·테스트·리뷰는 여기 적힌 뜻만 쓴다.

## 줄바꿈 키 (newline chord)

프롬프트에 **줄을 넣고 전송하지 않는** 키 조합. 이번 기능에서 값은 `shift-enter` 또는 `ctrl-enter` 둘 중 하나다. 온보딩에서 고르고, 고르지 않으면 `shift-enter`다.

## 전송 (submit)

프롬프트를 에이전트에 보내는 동작. **Enter 단독**이 전송이다. 이번 기능은 Enter의 전송 동작을 바꾸지 않는다.

## 고르지 않은 키

줄바꿈 키로 고르지 않은 쪽 수정 Enter(예: 줄바꿈이 Shift+Enter면 Ctrl+Enter). 설치가 이 키를 바인딩하거나 언바인드하지 않는다. 각 에이전트 기본값 그대로 둔다.

## 터미널 번역

터미널 에뮬레이터가 줄바꿈 키를 눌렀을 때, 에이전트가 줄바꿈으로 읽는 **서로 다른 바이트 시퀀스**를 보내는 것. 에이전트마다 키맵 형식이 달라서, 공통 동작은 “고른 키가 줄바꿈을 만든다”이지 바이트 값이 아니다. 실제 시퀀스는 실측으로 고른다.

## 네이티브 구분 터미널

Shift+Enter를 Enter와 다른 시퀀스로 보내는 터미널. 문서 기준: Windows Terminal, iTerm2, Ghostty, Kitty, WezTerm, Warp, Apple Terminal. 이 터미널에 Shift+Enter용 sendInput/sendSequence를 **추가로** 넣으면 줄바꿈이 두 번 생길 수 있으므로, Shift+Enter 선택 시에는 넣지 않는다.

## 설정 필요 터미널

Shift+Enter와 Enter를 구분하지 못해 키바인딩이 필요한 터미널. 이번 범위: VS Code 통합 터미널, Cursor 통합 터미널.

## 불가 터미널

Shift+Enter를 구분할 수 없어 이번 기능으로도 로컬 세션에서는 맞출 수 없는 터미널. 대표: gnome-terminal. 설치는 실패하지 않고 경고만 한다. Linux 완료 기준은 로컬 gnome-terminal이 아니라 **SSH 실측 경로**다.

## 범용 테스트

테스트 코드는 **아무 개발 머신·CI에서** 격리 HOME/픽스처만으로 돌아야 한다. 특정 SSH 호스트, 이 사용자의 PATH에만 있는 에이전트 바이너리, 실제 Windows Terminal/Cursor 창은 테스트 코드의 전제가 아니다. OS 능력으로 건너뛰는 것은 허용한다(예: Windows에서 POSIX pty 테스트 skip). 호스트 이름으로 건너뛰거나 실패하는 것은 허용하지 않는다.

## SSH 실측 경로

키보드와 터미널 에뮬레이터는 로컬(Windows Terminal 또는 Cursor)에 있고, 에이전트 프로세스는 원격에서 도는 경로. **테스트 코드가 아니라 R3 실측**에만 쓴다.

## 관리 바인딩

이 설치가 넣은 키바인딩/tmux 줄. 시그니처(명령 + when + 시퀀스, 또는 우리가 붙인 주석 마커)로 식별한다. `--uninstall`은 관리 바인딩만 제거하고, 사용자가 원래 가진 항목은 남긴다.

## 대상 에이전트

Claude Code CLI, Codex CLI, Grok Build CLI. Gemini CLI와 Cursor/VS Code IDE 챗 입력창은 범위 밖이다.

## Grok 키맵

Grok Build TUI의 키바인딩은 현재 사용자가 리맵할 수 없다. Grok은 터미널이 보내는 시퀀스에만 의존한다.

## Grok multiline

`/multiline`(`/ml`) 또는 프롬프트 포커스에서 `Ctrl+M`을 켜면 Enter와 Shift+Enter의 의미가 **반대**가 된다 (Enter=줄바꿈, Shift+Enter=전송). `/vim-mode`와 달리 공식 문서는 이 토글을 `config.toml`에 저장한다고 하지 않는다. 이 모드가 켜진 Grok과 Claude/Codex를 한 키로 통일하는 것은 불가능하다(Grok이 Shift+Enter를 전송으로 읽기 때문). **완료 기준은 Grok 기본 프롬프트(multiline 꺼짐)다.** 설치기는 Grok multiline을 켜거나 끄지 않는다. 설치 리포트에 한 줄 경고만 남긴다.
