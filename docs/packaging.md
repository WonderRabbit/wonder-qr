# 패키징

패키지는 Python 3.12 전용입니다. `pyproject.toml`은 `requires-python = ">=3.12,<3.13"`, `uv_build` build backend, `wonder-qr = "wonder_qr.cli:main"` console script를 선언합니다.

런타임 의존성은 다음 두 개입니다.

- `Pillow==12.3.0`: 이미지 읽기·정규화·raster 변환·PNG 검증
- `zxing-cpp==3.1.1`: QR 및 바코드 판독

## 일반 설치

로컬 소스에서 다음을 실행하면 uv가 격리된 도구 환경에 설치합니다.

```sh
uv tool install --python 3.12 .
wonder-qr --help
```

이 명령은 사용 방법일 뿐 이번 작업에서 실행한 검증 명령은 아닙니다. 현재 저장소에는 `uv.lock`이 없으므로 `uv sync --locked`를 초기 설치 명령으로 사용하지 마세요. lock 파일이 만들어지고 커밋된 뒤에만 개발·CI에서 `uv sync --locked --python 3.12`를 사용합니다.

개발 중 상주 설치 없이 실행하려면, lock 파일이 준비된 뒤 다음을 사용할 수 있습니다.

```sh
uv run --locked wonder-qr --help
```

## 빌드와 배포

wheel과 source distribution은 다음 명령으로 만듭니다.

```sh
uv build
```

wheel 설치는 Git 없이 가능합니다. 원격 Git 설치는 실제 tag가 게시된 뒤에만 해당 tag를 지정해 사용합니다. 현재는 tag·게시·PyPI 배포를 수행하거나 약속하지 않습니다.

선택적으로 PyInstaller 단일 실행 파일을 만들 수 있지만, 빌드한 운영체제와 CPU에 맞는 산출물만 사용합니다. macOS에서 만든 실행 파일을 Windows나 Linux 용도로 사용하지 않습니다. 코드 서명·공증, Windows/macOS/Linux의 실제 설치 및 실행은 아직 확인되지 않았습니다.

프로젝트의 공개 라이선스는 지정되지 않았습니다.
