# Python 개발 workflow

이 기록은 리서치의 결정과 현재 구현 상태를 구분합니다. 설치·제품 실행·테스트를 하지 않은 항목을 통과로 표시하지 않습니다.

| 단계 | 수행 내용 | 상태 |
| --- | --- | --- |
| research-01 | Python 3.12, uv, `zxing-cpp`, Pillow, generic ZPL II, Labelary 선택과 제약 조사 | 완료 |
| task-01 | `pyproject.toml`, Python 3.12 제약, console script와 데이터 모델 구현 | 소스 확인 완료 |
| task-02 | 이미지 정규화와 `zxing-cpp` 판독·구조화 JSON 구현 | 소스 확인 완료, 런타임 미검증 |
| task-03 | raster/native/hybrid 이미지→ZPL 구현 | 소스 확인 완료, 이미지·프린터 검증 미완료 |
| task-04 | 명시적 Labelary ZPL→PNG 구현 | 소스 확인 완료, 네트워크·PNG 검증 미완료 |
| task-05 | `decode`, `to-zpl`, `to-image` CLI와 도움말·종료 코드 구현 | 소스 확인 완료, 현재 환경의 help 실행 실패 |
| task-06 | uv build·tool install 및 설치된 명령 실행 | 미검증 |
| task-07 | README와 사용자 문서 작성 | 완료 |

## 관측한 환경과 미검증 범위

현재 기본 Python은 3.9.6이며 요구 버전인 Python 3.12가 아닙니다. Pillow, `zxing-cpp`, pytest, ruff, basedpyright도 설치되어 있지 않습니다. `cd src && python3 -m wonder_qr --help`는 Python 3.9.6이 필요한 `dataclass(slots=True)`를 지원하지 않아 parser 시작 전에 exit 1로 실패했습니다. `uv lock --offline --no-python-downloads`는 설치된 Python 3.12가 없어 exit 2로 실패했고, lock 파일을 만들지 않았습니다.

신규 runtime·의존성·테스트 도구를 설치하지 않는 작업 조건을 지켜 판독, ZPL 생성, Labelary 요청, pytest, lint, typecheck, wheel build, `uv tool install`은 실행하지 않았습니다. help 실패는 Python 3.12에서의 CLI 동작을 확인한 결과가 아닙니다.

따라서 다음은 아직 달성했다고 말할 수 없습니다.

- 실제 QR·바코드 판독과 payload/좌표 보존
- raster/native/hybrid ZPL의 renderer 또는 프린터 결과
- Labelary HTTPS 요청과 응답 PNG 검증
- Python 3.12 wheel·tool 설치와 설치된 `wonder-qr` 실행
- Windows, macOS, Linux, 실제 프린터 동작

## 다음 직접 확인

Python 3.12 환경에서 필요한 runtime 의존성이 준비된 경우에만 아래 최소 경로를 실행하고, 결과와 산출물 위치를 이 표에 추가합니다.

```sh
uv tool install --python 3.12 .
wonder-qr --help
```

그 다음 정답을 아는 이미지 한 장으로 `decode`와 각 `to-zpl` 모드를 확인합니다. `to-image`는 ZPL 전송을 승인한 자료에서만 `--renderer labelary --allow-network`를 붙여 한 번 확인합니다. 없는 runtime이나 외부 서비스는 대체 구현·가짜 PNG·테스트 우회로 대신하지 않고 미검증으로 남깁니다.

## 저장소 상태

원격 저장소는 `git@github.com:WonderRabbit/wonder-qr.git`입니다. 최초 구현은 `main`의 `487a504d4aea1f5e658dc90d99977fff25080621` 커밋으로 전달했습니다. Python runtime·`uv.lock`·문서 변경의 전달 이력은 Git 로그에서 확인할 수 있습니다.

## 2026-09-14 런타임과 단일 synthetic smoke 관측

이후 명시된 설치 승인에 따라 프로젝트 runtime을 실제로 준비하고, 고객 자료 없이 `test1234` 단일 QR 경로를 실행했다. 이전 표의 런타임 미검증 상태는 이 관측으로 대체한다.

- pyenv의 `3.12.14` 설치는 빌드 마지막 `ensurepip`에서 segmentation fault(11), `make` error 139로 실패했다. pyenv에 Python 3.12는 등록되지 않았으며 이 실패는 우회하거나 숨기지 않았다.
- `UV_PYTHON_DOWNLOADS=manual uv python install 3.12`는 uv 관리형 CPython 3.12.14를 `/Users/sophi/.local/share/uv/python/cpython-3.12.14-macos-aarch64-none/bin/python3.12`에 설치했다.
- 해당 절대 interpreter로 `uv sync`를 실행해 프로젝트 `.venv`와 `uv.lock`을 만들었다. `.venv/bin/python --version`은 Python 3.12.14였다.
- `wonder-qr --help`를 한 번 실행해 CLI 표면을 확인했다. `uv tool install`은 실행·검증하지 않았다.

직접 관측한 synthetic 경로는 다음과 같다.

1. ZXing writer API로 `test1234` QR PNG(232×232, 690 bytes)를 만들었다.
2. `decode`는 status `ok`, QR Code 1개, text `test1234`를 반환했다.
3. `to-zpl --mode raster`는 40,047-byte `^GFA` ZPL을, `--mode native`는 76-byte `^BQN` ZPL을 만들었다.
4. native ZPL을 `to-image --renderer labelary --allow-network --dpmm 8 --width-mm 50 --height-mm 50`로 한 번 전송했다. Labelary PNG(399×399, 2,516 bytes)를 받은 뒤 `decode`가 다시 정확히 `test1234`를 반환했다.

산출물과 실제 명령·exit code·payload assertion은 `.omo/evidence/test1234/`에 있다. 특히 `runtime-setup.txt`, `qa-transcript.txt`, `native-labelary-roundtrip-transcript.txt`가 환경 설정, QR→ZPL, Labelary roundtrip의 관측 기록이다. 이 결과는 synthetic 입력 하나와 Labelary 응답 하나의 확인이며, 실제 프린터·Windows/Linux·`uv tool install`·대규모 입력 corpus의 검증은 포함하지 않는다.
