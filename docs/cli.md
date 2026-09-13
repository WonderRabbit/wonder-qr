# CLI 사용법

`wonder-qr`는 이미지 판독, 이미지→ZPL, ZPL→PNG를 제공합니다. 모든 명령은 `-h`, `--help`, `-help`로 도움말을 표시하고 종료 코드 0으로 끝납니다. `--version`은 버전을 표시합니다.

```text
wonder-qr {decode,to-zpl,to-image} ...
```

명령이 없거나 옵션이 잘못되면 usage 오류(2)입니다. stdout에는 결과 데이터만 쓰며, 오류와 진단은 stderr에 씁니다. 파일 출력을 원하면 `--output`을 사용하세요. 기존 출력 파일은 `--force` 없이는 바꾸지 않습니다.

## `decode`

```sh
wonder-qr decode label.png --format json --output decoded.json
wonder-qr decode first.png second.png --format jsonl --output decoded.jsonl
```

PNG, JPEG, BMP, 단일 프레임 TIFF를 읽습니다. 입력은 최대 100개이며, 각 파일은 25 MiB, 정규화 이미지는 40 MP까지입니다. `-`는 stdin의 이미지 하나를 뜻하며 다른 파일 인자와 함께 쓸 수 없습니다.

`--profile standard|robust`는 판독 후보 수를 고릅니다. `robust`는 제한된 threshold·확대·끝부분 crop 후보를 추가합니다. 단일 입력에는 `--roi x,y,width,height` 또는 `--quad x1,y1,x2,y2,x3,y3,x4,y4` 중 하나를 지정할 수 있습니다. `--expected-count N`은 판독 개수 기대값을 기록합니다.

기본 출력은 JSON 한 문서이고, `--format jsonl`은 입력 이미지마다 한 줄입니다. 심볼마다 `payload_base64`, 표시용 `text`, `format`, 위치 polygon, 원본 좌표, 판독 시도 이력을 기록합니다. raw payload bytes를 텍스트 stdout으로 직접 쓰지 않습니다. `--report FILE`은 실행 시간과 실제 결과를 포함한 진단 JSON을 별도로 씁니다.

## `to-zpl`

프린터 크기는 `--dpmm {6,8,12,24} --width-mm W --height-mm H`로 모두 지정하거나, 같은 세 값을 가진 `--printer-profile FILE` 하나를 지정합니다.

```sh
wonder-qr to-zpl label.png --mode raster --dpmm 8 --width-mm 100 --height-mm 50 --output label.zpl
wonder-qr to-zpl label.png --mode native --dpmm 8 --width-mm 100 --height-mm 50 --fallback raster --output label.zpl
```

| 모드 | 동작 |
| --- | --- |
| `raster` (기본) | 이미지를 비율 유지로 라벨에 맞춰 `^GFA`로 출력합니다. 판독하지 않으므로 코드 판독 실패와 무관합니다. |
| `native` | 판독한 지원 심볼만 다시 생성합니다. 배경, 로고, 일반 텍스트는 포함하지 않습니다. |
| `hybrid` | 원본 배경 raster에서 안전성이 확인된 심볼 영역을 지우고 native 심볼을 추가합니다. |

native와 hybrid는 지원하지 않는 payload·형식·배치에서 기본적으로 실패합니다. `--fallback raster`를 명시하면 전체 라벨 raster로 전환합니다. raster 모드에서는 `--layout`, `--expected-count`, `--fallback raster`, `--hri`를 쓸 수 없고, native 모드에서는 `--layout`과 `--hri`를 쓸 수 없습니다. hybrid의 명시 `--layout` 및 `--hri regenerate`는 아직 안전하게 적용되지 않아 실패하거나 명시한 raster fallback으로 전환합니다.

`--report FILE`은 요청 모드, 실제 모드, fallback 사유와 판독 진단을 기록합니다. `--output`을 생략하면 ZPL bytes가 stdout으로 나가므로 보통 파일 출력을 권장합니다.

## `to-image`

```sh
wonder-qr to-image label.zpl --renderer labelary --allow-network \
  --dpmm 8 --width-mm 100 --height-mm 50 --output label.png
```

`--renderer labelary`와 `--allow-network`는 모두 필수입니다. 둘 중 하나가 없으면 usage 오류(2)이며 요청을 보내지 않습니다. 지정하면 ZPL 전체를 HTTPS POST로 Labelary에 전송하고, PNG 응답만 저장합니다. `--label-index`는 0부터 시작하며 기본값은 0입니다.

이 명령은 30초 socket timeout을 사용하고 재시도·대체 renderer·자동 fallback을 하지 않습니다. 네트워크 오류, HTTP 오류, 범위 밖 label index, 유효하지 않은 PNG는 변환 오류(4)입니다. Labelary의 렌더 결과는 실제 프린터 출력과 같다고 보장되지 않습니다.

## 종료 코드

| 코드 | 의미 |
| --- | --- |
| 0 | 성공 |
| 1 | 내부 오류 또는 broken pipe |
| 2 | 사용법 오류 |
| 3 | 판독 결과 없음 |
| 4 | 입력·출력·변환 오류 |
| 5 | 일부 판독 결과 또는 입력 오류가 섞인 결과 |
| 130 | 인터럽트 |

현재 실행 환경에서 이 도움말과 명령의 런타임 실행은 확인하지 않았습니다. 확인 상태는 [Python workflow](python-workflow.md)에 있습니다.
