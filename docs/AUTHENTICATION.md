# GitHub 인증

이 저장소는 **비공개(private)** 이므로, 설치 스크립트를 원격으로 받으려면 GitHub 인증이 필요하다.

## 1. `gh` CLI 설치

macOS
```sh
brew install gh
```

Linux (Debian/Ubuntu)
```sh
sudo apt install gh
```

Windows
```powershell
winget install --id GitHub.cli
```

설치 후 한 번만 로그인한다.

```sh
gh auth login
```

## 2. 인증 방식

**`gh` CLI (권장):** `gh auth login`만 해두면 끝. `install.sh`/`install.ps1`은 `GITHUB_TOKEN`/`GH_TOKEN`이 없으면 `gh auth token`으로 자동 폴백한다.

**PAT 직접 사용:** GitHub → Settings → Developer settings → Personal access tokens에서 발급.

- classic PAT: `repo` 스코프
- fine-grained PAT: 대상 레포 Contents: Read 권한

```sh
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"   # 이 셸 세션 한정
```

> ⛔ **`GITHUB_TOKEN`을 rc 파일(`.zshrc` 등)에 영구 export 하지 말 것.**
> `gh`는 `GITHUB_TOKEN`이 설정돼 있으면 그 값을 우선 쓰고 `gh auth login`을 거부한다.
> 토큰이 만료되면 재로그인조차 못 하고 설치는 계속 `404`로 실패한다
> (비공개 레포는 인증 실패를 401이 아니라 404로 위장한다). 이미 export 해뒀다면
> rc에서 지우고 현재 셸에서 `unset GITHUB_TOKEN` 하자.

## 3. 토큰 확인

```sh
gh auth status                 # "Logged in" 이어야 한다
```

`The token in keyring is invalid`가 뜨면:

```sh
unset GITHUB_TOKEN GH_TOKEN    # 먼저 지워야 gh auth login 이 동작한다
gh auth login -h github.com
```

## 문제 해결 — `404`가 뜬다면

거의 항상 토큰 문제다. 비공개 레포는 인증 실패를 `401`이 아니라 `404`로 돌려주므로
"install.sh 파일이 없다"처럼 보이지만 파일은 멀쩡히 있다. `gh auth status`로 토큰 상태를
확인하고 위 순서(먼저 `unset`, 그다음 `gh auth login`)로 되살리면 된다.

`install.sh`는 다운로드에 실패하면 GitHub API를 한 번 찔러 `401`(토큰 만료) / `403`(권한 부족) /
`404`(레포 못 봄) / ref 오류를 구분해 알려준다. 그 메시지를 따르면 된다.

> `CLAUDE_SETUP_REF`에는 `feature/my-branch`처럼 슬래시가 든 브랜치명도 그대로 쓸 수 있다
> (raw URL·archive URL 양쪽에서 확인). 경계를 분명히 하고 싶다면 `refs/heads/feature/my-branch` 형태도 동작한다.
