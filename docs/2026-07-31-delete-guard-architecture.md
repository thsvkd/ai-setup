# 삭제 방어 아키텍처 조사

- 조사일: 2026-07-31
- 계기: `rm -rf .` 로 저장소가 통째로 휴지통에 들어간 사건 (`danger_guard` 의 rm→trash-put 치환이 원인)
- 환경: Claude Code 2.1.220, Linux (Raspberry Pi OS, aarch64)
- **결론: 지금의 블랙리스트 방식을 유지한다.** 아래 대안들은 근거 기록이며 현재 구현하지 않는다.

## 1. 블랙리스트의 한계 — 실측

훅에 삭제 경로 35가지를 넣고 돌린 결과 **4개만 잡는다.** 통과한 것:

| 부류 | 예 |
| --- | --- |
| find / xargs | `find . -delete`, `find . -exec rm {} \;`, `xargs rm -rf` |
| 인터프리터 | `python3 -c "shutil.rmtree('.')"`, `node -e "fs.rmSync(...)"`, `perl`, `ruby` |
| 덮어쓰기 | `> f`, `cp /dev/null f`, `sed -i 's/.*//' f`, `truncate -s 0 f` |
| 인자 먹는 래퍼 | `timeout 5 rm -rf .`, `nice -n 5 rm -rf .` |
| 이름 바꾼 rm | `cp /bin/rm /tmp/zz && /tmp/zz -rf .` |
| 도구 경유 | `docker system prune -af`, `kubectl delete ns prod`, `rsync --delete` |

목록이 부족한 게 아니라 **원리적으로 못 채운다.** 블랙리스트는 "이 명령이 무엇을 하려는가"를
명령 문자열에서 읽어야 하는데, 셸은 임의의 프로그램을 실행할 수 있다. `python3 -c` 를 막으면
파일에 써서 실행하고, 그걸 막으면 인코딩한다. 항목을 늘려도 쫓아가는 쪽이 항상 늦는다.

이 한계를 인정하고 **훅의 역할을 "완전 차단"이 아니라 "흔한 실수에 대한 확인"으로 본다.**

## 2. 대안 1 — Claude Code 내장 샌드박스 (도입 보류)

CC 2.1.220에 OS 수준 샌드박스가 내장돼 있다. Linux는 [bubblewrap](https://github.com/containers/bubblewrap)
사용(이 머신에 설치됨, `socat` 은 없음). 기본 정책은 "작업 디렉터리 + 세션 임시 폴더만 쓰기 가능".

문서상 기본 정책을 `bwrap` 으로 재현해 실측:

```
작업 디렉터리 밖
  rm -rf ~/precious                → Read-only file system
  python3 -c shutil.rmtree(...)    → OSError: Read-only
  echo '' > ~/precious/f.txt       → Read-only file system
  echo x > ~/.claude/settings.json → Read-only  (정책 자체 보호)

작업 디렉터리 안
  rm -rf ./sub                     → 전부 삭제됨
  python3 shutil.rmtree('.git')    → .git 사라짐
```

> 실험 정확도: Claude Code의 실제 샌드박스를 켜서 잰 게 아니라 문서의 기본 정책을 `bwrap` 으로
> 재현한 것이다. 경계의 성질은 같지만 세부 동작은 다를 수 있다.

**강점** — 명령을 해석하지 않고 OS가 막으므로 위 35가지 우회가 전부 무력화된다.

**치명적 한계** — 작업 디렉터리 *안* 은 아무 보호가 없다. `.git` 도 안에 있어 같이 사라진다.
즉 이번 `rm -rf .` 사건은 **샌드박스를 켰어도 똑같이 났다.**

**보류 이유** — 에이전트 자유도가 준다. 특히 이 저장소는 `~/.claude/**` 를 상시 수정하는데
기본 정책이 정면으로 막는다.

**재검토 시 진입점** — `sandbox.filesystem.allowWrite` 에 `~/.claude`, `~/.npm`, `~/.cache`,
`~/.local` 을 넣으면 실작업 자유도는 거의 유지하면서 `~/Documents` 나 타 저장소만 보호할 수 있다.

### 함정 — 샌드박스를 그냥 켜면 지금 훅이 깨진다 (실측)

```
샌드박스 안:  trash-put -f f.txt  →  멈춤(hang), 파일 그대로 남음
샌드박스 밖:  trash-put -f f.txt  →  exit=0, 정상 이동
```

휴지통(`~/.local/share/Trash`)이 작업 디렉터리 밖이라 쓰기가 막힌다. `rm` 을 `trash-put` 으로
바꿔놓고 그게 실패하면 **삭제도 안 되고 백업도 안 되는** 어정쩡한 상태가 된다.

해결:

```json
{ "sandbox": { "filesystem": { "allowWrite": ["~/.local/share/Trash"] } } }
```

이걸 넣으면 `exit=0` 으로 정상 동작함을 확인했다.

### 참고 — 내장 기능과의 중복

CC 2.1.218부터 `rm`/`rmdir` 이 `/`, 홈, 기타 시스템 경로를 겨냥하면 **기본으로 확인을 띄운다.**
현재 훅의 루트/홈 차단은 이제 내장 기능과 중복이다.

## 3. 대안 2 — 섀도 스냅샷 (설계만, 미구현)

작업 디렉터리 **밖** 에 별도 bare git 저장소를 두고, 훅이 매 Bash 명령 직전에 현재 상태를
통째로 커밋한다. **무엇이 지우는지 판정하지 않는다 — 판정을 포기하는 게 요점.**
차단이 없으므로 에이전트 자유도는 전혀 줄지 않는다.

```
~/.claude/snapshots/<프로젝트>.git    ← GIT_DIR (작업 디렉터리 밖)
프로젝트/                              ← GIT_WORK_TREE
훅: git add -A → write-tree → commit-tree → update-ref
```

### 비용 (실측)

| 저장소 | 첫 스냅샷 | 이후 | 디스크 |
| --- | --- | --- | --- |
| claude-code-setup (128파일 / 4.2M) | 36ms | 9~10ms | 116KB |
| asset-portfolio (53,417파일 / 1.4G) | 84ms | 7ms | 1MB |

git이 내용이 같은 파일을 한 번만 저장하므로 디스크가 거의 늘지 않는다.

### 복구 검증

`python3 -c shutil.rmtree` 로 `.git` 포함 전부 날린 뒤:

```
남은 것: ''                    ← 전부 소멸
git checkout -f <snap> -- .
복구:   ./src/app.py  ./config.yml  ./.gitignore
내용:   중요한 소스
```

### `.gitignore` 를 반드시 존중해야 한다

무시 파일까지 포함하면 **92초 / 687MB** 로 폭발한다(node_modules 때문). 이건 못 쓴다.
`git add -A --force` 는 `core.excludesFile` 까지 무시하므로 제외 목록으로 우회할 수도 없다.

### 남는 한계

1. 작업 디렉터리 **밖** 은 여전히 블랙리스트뿐. 이걸 덮는 건 샌드박스밖에 없다.
2. `.gitignore` 대상(`.env`, 빌드 산출물, 로컬 DB)은 복구 불가 — 비용상 다른 선택지가 없다.
3. 프로젝트의 `.git` 히스토리는 별도 처리 필요. 스냅샷 시점에 `git fetch` 로 커밋 객체를
   같이 끌어오면 해결되고 증분이라 비용은 거의 없다.
4. 에이전트가 스냅샷 저장소를 지울 수 있다(OS 강제가 아니므로). 방어 대상이 "악의"가 아니라
   "실수"라면 실질적 문제는 아니다.
5. 명령 *안* 에서 만들고 지운 파일은 못 잡는다. 스냅샷은 명령 직전 상태다.
6. 병렬 Bash 호출 시 `index.lock` 경합 처리가 필요하다.

### 에이전트가 복구 가능성을 인지하게 하는 부분

구현한다면 함께 필요하다. 없으면 에이전트가 복구 대신 기억으로 파일을 재작성한다.

- 훅이 위험해 보이는 명령을 허용할 때 스냅샷 ID와 복구 명령을 함께 알린다 (지금 `refs/claude-backups/` 백업과 동일 방식)
- AGENTS.md 2줄 — "삭제 실수는 되돌릴 수 있다. `<명령>` 으로 스냅샷 목록 확인"
- 복구 스크립트 1개 — 절차가 복잡하면 안 쓰게 된다

## 4. 참고 자료

- [Configure the sandboxed Bash tool — Claude Code Docs](https://code.claude.com/docs/en/sandboxing)
- [Configure permissions — Claude Code Docs](https://code.claude.com/docs/en/permissions)
