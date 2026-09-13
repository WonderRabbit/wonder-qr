# wonder-qr

`wonder-qr`는 QR·바코드가 포함된 이미지에서 값을 읽고, 라벨 이미지를 ZPL로 변환하며, 선택적으로 ZPL을 PNG로 렌더하는 명령줄 도구입니다.

## 제공 기능

- `decode`: 이미지의 QR 및 1D/2D 바코드를 JSON 또는 JSONL로 읽습니다. payload bytes와 표시용 text, 형식, 위치 정보를 함께 보존합니다.
- `to-zpl`: 라벨 이미지를 ZPL로 변환합니다. `raster`는 전체 외형을, `native`는 지원하는 코드만, `hybrid`는 안전하게 검증된 경우 배경과 재생성 코드를 보존합니다.
- `to-image`: ZPL을 PNG로 렌더합니다. 이 명령은 `--renderer labelary --allow-network`를 모두 지정할 때만 Labelary에 ZPL 전체를 전송합니다.

## 빠른 시작

Python 3.12과 [uv](https://docs.astral.sh/uv/)가 필요합니다. 다음은 로컬 소스에서 도구를 설치하는 일반적인 사용 방법입니다.

```sh
uv tool install --python 3.12 .
wonder-qr --help
wonder-qr decode label.png --output decoded.json
wonder-qr to-zpl label.png --mode raster --dpmm 8 --width-mm 100 --height-mm 50 --output label.zpl
```

이 문서 작성 과정에서는 설치를 수행하지 않았습니다. 개발 환경의 lock 파일이 생성된 뒤에는 `uv sync --locked --python 3.12` 및 `uv run --locked wonder-qr --help`를 사용할 수 있습니다.

## 제한 사항

- 원본 ZPL, QR 비트 배열, 인코딩 분할을 복원하지 않습니다. 같은 payload라도 원본과 같은 코드 모양을 보장하지 않습니다.
- 판독 결과가 없다고 이미지에 코드가 없음을 증명하지 않습니다. 지원하지 않는 payload·형식·안전하지 않은 배치는 오류로 처리하거나 명시한 raster fallback을 사용합니다.
- native는 현재 QR Model 2의 짧은 printable ASCII, checksum이 유효한 EAN-13, printable ASCII Code 128·GS1-128만 재생성합니다. hybrid는 축에 맞고 흰 quiet zone이 확인된 심볼만 교체합니다.
- `decode`와 `to-zpl`은 네트워크를 사용하지 않습니다. `to-image`는 명시한 Labelary 네트워크 요청에 의존하며, 결과가 실제 프린터 출력과 완전히 같다고 보장하지 않습니다.
- 현재 검증 완료 여부와 운영체제별 결과는 [Python workflow](docs/python-workflow.md)에 기록합니다.

## 문서

- [CLI 사용법](docs/cli.md)
- [구조](docs/architecture.md)
- [패키징](docs/packaging.md)
- [Python workflow](docs/python-workflow.md)

프로젝트의 공개 라이선스는 아직 지정되지 않았습니다.
