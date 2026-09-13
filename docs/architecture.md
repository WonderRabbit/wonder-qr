# 구조

프로그램은 파일·네트워크 I/O와 판독·변환 규칙을 분리합니다. `argparse` CLI가 입력을 확인한 뒤 아래 모듈을 호출하고, 결과는 JSON 또는 파일로만 내보냅니다.

| 모듈 | 책임 |
| --- | --- |
| `cli` | 서브명령, 옵션, 종료 코드, stdout·stderr 경계 |
| `input` | 파일 크기·형식·단일 프레임 검사, EXIF 방향 적용, alpha 흰색 합성 |
| `decoder` | `zxing-cpp` 다중 판독, standard/robust 후보, 좌표 역변환과 중복 처리 |
| `geometry` | ROI·quad 검증, 변환 행렬, polygon 계산 |
| `models` | 불변 판독 report·symbol·printer profile·오류 모델 |
| `zpl` | raster/native/hybrid ZPL 생성과 배치·자원 한도 검사 |
| `renderer` | 명시적 Labelary HTTPS POST와 PNG 검증 |
| `output` | UTF-8 JSON 직렬화와 원자적 파일 쓰기 |

## 데이터 흐름

```text
image → input normalize → decoder → DecodeReport → output JSON
                                  └──────────────→ zpl → ZPL
ZPL → renderer (Labelary 요청을 명시한 경우만) → PNG
```

정규화 뒤 이미지 좌표와 원본 좌표를 함께 보존합니다. `DecodeReport`는 판독 상태, completeness, 심볼, 오류, 시도 이력, 좌표 변환을 담습니다. `payload_base64`는 원래 bytes를 보존하기 위한 필드이고 `text`는 표시용입니다.

## ZPL 모드의 경계

raster는 이미지 전체를 흰 배경에 맞추고 이진화해 `^GFA`로 만듭니다. native는 QR Model 2의 최대 14-byte printable ASCII, 유효 checksum EAN-13, printable ASCII Code 128과 GS1-128만 생성합니다. QR의 binary/ECI 표현, 그 밖의 형식, 비표준 control bytes는 보존 가능한 native 표현으로 간주하지 않습니다.

hybrid는 네 모서리의 축 정렬 사각형, 이미지 경계 안의 quiet zone, 주변 흰 배경, 다른 심볼과의 비겹침을 모두 확인할 때만 원래 심볼을 지웁니다. 확인할 수 없으면 native 겹쳐쓰기를 하지 않고 오류 또는 사용자가 명시한 전체 raster fallback을 사용합니다.

## 외부 경계와 한도

`decode`와 `to-zpl`은 네트워크를 쓰지 않습니다. `to-image`만 Labelary에 ZPL을 보내며, 응답 signature와 Pillow 검증을 통과한 PNG만 저장합니다.

이미지는 25 MiB와 40 MP, 라벨은 각 방향 8,192 dots·총 16,777,216 dots, raster 데이터는 2,097,152 bytes, 최종 ZPL은 8 MiB로 제한합니다. 이 한도는 현재 구현의 자원 보호이며 모든 프린터의 한도를 뜻하지 않습니다.
