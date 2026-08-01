# res/vendor — 온보딩 TUI 의존성 (벤더링)

`res/onboard.py` 가 쓰는 서드파티 패키지를 **레포에 직접 넣어** 둔다. 설치 과정에서
`pip install` 을 하지 않기 위해서다:

- 최신 배포판은 PEP 668(`externally-managed-environment`)로 시스템 Python 에 대한
  `pip install` 을 거부한다. 설치 스크립트가 사용자 환경을 바꾸는 것도 부적절하다.
- `curl … | sh` 한 방으로 끝나야 하는데, 네트워크가 막힌 환경에서 pip 이 추가로
  나가면 설치가 통째로 실패한다.

`res/onboard.py` 는 이 디렉터리를 `sys.path` 앞에 넣고 import 한다. 사용자 환경에
같은 패키지가 설치돼 있어도 여기 있는 버전이 쓰인다.

## 구성

| 패키지 | 버전 | 라이선스 | 용도 |
| ------ | ---- | -------- | ---- |
| `questionary` | 2.1.1 | MIT | select / confirm 프롬프트 |
| `prompt_toolkit` | 3.0.53 | BSD-3-Clause | questionary 의 렌더링·키 입력 백엔드 |
| `wcwidth` | 0.2.13 | MIT | 동아시아 문자 폭 계산 (한글 메뉴 정렬) |

라이선스 전문은 `LICENSES/` 에 있다.

`wcwidth` 는 최신(0.8.x)이 아니라 **0.2.13 으로 고정**한다. 0.8.x 는 grapheme 클러스터
override 테이블 때문에 혼자 1.8MB 를 차지하는데, `prompt_toolkit` 의 요구사항은
`wcwidth>=0.1.4` 라 굳이 받을 이유가 없다.

## `prompt_toolkit-*.dist-info/METADATA` 는 지우면 안 된다

`questionary` 는 프롬프트를 띄우기 전에 `is_prompt_toolkit_3()` 을 호출하고, 그 함수가
`from prompt_toolkit import __version__` 을 한다. 그런데 `prompt_toolkit` 은 이 값을
소스에 박아두지 않고 `importlib.metadata.version("prompt_toolkit")` 으로 **설치 메타데이터에서
읽는다**. 그래서 `*.dist-info` 를 통째로 지우면 import 는 통과하고 프롬프트를 띄우는 순간
`PackageNotFoundError` 로 죽는다.

`METADATA` 파일 하나만 남기면 되므로, 나머지 배포 부산물(`RECORD`, `WHEEL`, `INSTALLER`,
`top_level.txt`, `licenses/`)만 지운다. `questionary` 와 `wcwidth` 는 자기 버전을 소스에
갖고 있어 `dist-info` 가 통째로 없어도 된다.

## 갱신 방법

`__pycache__` 가 섞이지 않도록 `--no-compile` 로 받는다.

```sh
rm -rf res/vendor
pip install --target res/vendor --no-compile questionary "wcwidth==0.2.13"

# 라이선스 전문을 먼저 추려낸다 (dist-info 를 지우면 같이 사라진다)
mkdir -p res/vendor/LICENSES
cp res/vendor/questionary-*.dist-info/LICENSE             res/vendor/LICENSES/questionary-MIT.txt
cp res/vendor/wcwidth-*.dist-info/LICENSE                 res/vendor/LICENSES/wcwidth-MIT.txt
cp res/vendor/prompt_toolkit-*.dist-info/licenses/LICENSE res/vendor/LICENSES/prompt_toolkit-BSD-3-Clause.txt

# questionary·wcwidth 는 dist-info 통째로 제거, prompt_toolkit 은 METADATA 만 남긴다
rm -rf res/vendor/questionary-*.dist-info res/vendor/wcwidth-*.dist-info
cd res/vendor/prompt_toolkit-*.dist-info && rm -rf RECORD WHEEL INSTALLER top_level.txt licenses
```

갱신 후에는 `python -m pytest tests/test_onboard.py` 로 벤더 import 와 비대화형 폴백이
여전히 동작하는지 확인한다. 특히 위 `METADATA` 함정은 import 만으로는 드러나지 않고
**실제로 프롬프트를 띄울 때** 터지므로, 테스트를 반드시 돌린다.
