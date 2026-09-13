from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import TYPE_CHECKING, Final, assert_never

from PIL import Image, ImageDraw

from .models import (
    Completeness,
    DecodeReport,
    DecodeStatus,
    NoResultError,
    PartialResultError,
    PrinterProfile,
    ProductError,
    Symbol,
    UsageError,
)

# noqa: SIZE_OK - the assigned public boundary owns the three ZPL modes and their encoders.
if TYPE_CHECKING:
    from .input import NormalizedImage

_MAX_DIMENSION: Final = 8192
_MAX_AREA: Final = 16_777_216
_MAX_GRAPHIC_BYTES: Final = 2_097_152
_MAX_ZPL_BYTES: Final = 8 * 1024 * 1024
_WHITE: Final = (255, 255, 255)


def image_to_zpl(
    image: NormalizedImage,
    profile: PrinterProfile,
    *,
    mode: str = "raster",
    report: DecodeReport | None = None,
    fallback: str = "error",
    layout_path: Path | None = None,
    hri: str = "preserve",
) -> tuple[bytes, str, str | None]:
    _validate_profile(profile)
    if fallback not in {"error", "raster"}:
        raise UsageError("fallback must be 'error' or 'raster'")
    if hri not in {"preserve", "regenerate"}:
        raise UsageError("hri must be 'preserve' or 'regenerate'")
    match mode:
        case "raster":
            has_incompatible_option = (
                report is not None
                or layout_path is not None
                or hri != "preserve"
                or fallback != "error"
            )
            if has_incompatible_option:
                raise UsageError(
                    "raster mode does not accept decode, layout, HRI, or fallback options"
                )
            return _raster(image.image, profile), "raster", None
        case "native" | "hybrid":
            if report is None:
                raise UsageError(f"{mode} mode requires a decode report")
            report_failure = _report_failure(report)
            if report_failure is not None:
                if fallback == "raster":
                    reason = str(report_failure)
                    return _raster(image.image, profile), "raster", reason
                raise report_failure
            if mode == "native" and (layout_path is not None or hri != "preserve"):
                raise UsageError("native mode does not accept layout or HRI options")
            if mode == "hybrid" and (layout_path is not None or hri == "regenerate"):
                return _fallback_or_raise(
                    image,
                    profile,
                    fallback,
                    "explicit hybrid layout and HRI regeneration are not supported safely",
                )
            try:
                native_fields = _native_fields(report, image.image.size, profile)
                if mode == "native":
                    return _finish(profile, native_fields), "native", None
                masked = _safe_hybrid_background(image.image, report.symbols)
                raster_field = _graphic_field(masked, profile)
                return _finish(profile, raster_field + native_fields), "hybrid", None
            except ProductError as error:
                return _fallback_or_raise(image, profile, fallback, str(error))
        case _:
            raise UsageError(f"unsupported ZPL mode: {mode}")


def _fallback_or_raise(
    image: NormalizedImage,
    profile: PrinterProfile,
    fallback: str,
    reason: str,
) -> tuple[bytes, str, str]:
    if fallback == "raster":
        return _raster(image.image, profile), "raster", reason
    raise ProductError(reason)


def _report_failure(
    report: DecodeReport,
) -> NoResultError | PartialResultError | ProductError | None:
    if not report.symbols:
        return NoResultError("no decodable symbols")
    match report.status:
        case DecodeStatus.OK:
            pass
        case DecodeStatus.PARTIAL:
            return PartialResultError("decode result is partial")
        case DecodeStatus.NO_RESULT:
            return NoResultError("no decodable symbols")
        case DecodeStatus.ERROR:
            return ProductError("decode failed")
        case unreachable:
            assert_never(unreachable)
    incomplete = report.completeness is Completeness.EXPECTED_COUNT_MISMATCH
    partial_codes = {"budget", "conflicting_result", "expected_count"}
    if incomplete or any(issue.code in partial_codes for issue in report.errors):
        return PartialResultError("decode result is incomplete or conflicting")
    return None


def _validate_profile(profile: PrinterProfile) -> None:
    if profile.dpmm not in {6, 8, 12, 24}:
        raise UsageError("dpmm must be one of 6, 8, 12, or 24")
    width, height = profile.width_dots, profile.height_dots
    if not 1 <= width <= _MAX_DIMENSION or not 1 <= height <= _MAX_DIMENSION:
        raise ProductError("label dimensions must be between 1 and 8192 dots")
    if width * height > _MAX_AREA:
        raise ProductError("label area exceeds 16,777,216 dots")
    if ((width + 7) // 8) * height > _MAX_GRAPHIC_BYTES:
        raise ProductError("raster data exceeds 2,097,152 bytes")


def _raster(source: Image.Image, profile: PrinterProfile) -> bytes:
    return _finish(profile, _graphic_field(source, profile))


def _graphic_field(source: Image.Image, profile: PrinterProfile) -> bytes:
    width, height = profile.width_dots, profile.height_dots
    scale = min(width / source.width, height / source.height)
    target = (max(1, _half_up(source.width * scale)), max(1, _half_up(source.height * scale)))
    converted = Image.new("RGB", (width, height), _WHITE)
    resized = source.convert("RGB").resize(target, Image.Resampling.LANCZOS)
    converted.paste(resized, ((width - target[0]) // 2, (height - target[1]) // 2))
    monochrome = converted.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="1")
    row_bytes = (width + 7) // 8
    packed = bytearray(row_bytes * height)
    pixels = monochrome.load()
    if pixels is None:
        raise ProductError("could not access normalized image pixels")
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0:
                packed[y * row_bytes + x // 8] |= 1 << (7 - x % 8)
    data = bytes(packed).hex().upper().encode("ascii")
    byte_count = str(len(packed)).encode()
    return (
        b"^FO0,0^GFA,"
        + byte_count
        + b","
        + byte_count
        + b","
        + str(row_bytes).encode()
        + b","
        + data
        + b"^FS"
    )


def _finish(profile: PrinterProfile, fields: bytes) -> bytes:
    zpl = (
        b"^XA^PW"
        + str(profile.width_dots).encode()
        + b"^LL"
        + str(profile.height_dots).encode()
        + fields
        + b"^XZ"
    )
    if len(zpl) > _MAX_ZPL_BYTES:
        raise ProductError("ZPL output exceeds 8 MiB")
    return zpl


def _native_fields(
    report: DecodeReport,
    image_size: tuple[int, int],
    profile: PrinterProfile,
) -> bytes:
    return b"".join(_native_field(symbol, image_size, profile) for symbol in report.symbols)


def _native_field(symbol: Symbol, image_size: tuple[int, int], profile: PrinterProfile) -> bytes:
    left, top, right, bottom = _symbol_box(symbol, image_size)
    scale = min(profile.width_dots / image_size[0], profile.height_dots / image_size[1])
    x_offset = (profile.width_dots - image_size[0] * scale) / 2
    y_offset = (profile.height_dots - image_size[1] * scale) / 2
    x, y = _half_up(x_offset + left * scale), _half_up(y_offset + top * scale)
    width = max(1, _half_up((right - left) * scale))
    height = max(1, _half_up((bottom - top) * scale))
    orientation = _orientation(symbol.orientation)
    match _normalized_format(symbol.format):
        case "qr" | "qrcode":
            if len(symbol.payload) > 14 or any(byte < 32 or byte > 126 for byte in symbol.payload):
                raise ProductError("native QR supports ASCII payloads up to 14 bytes")
            magnification = min(width, height) // 29
            if magnification < 1:
                raise ProductError("QR region is too small for Model 2 with a 4-module quiet zone")
            origin = f"^FO{x + 4 * magnification},{y + 4 * magnification}".encode()
            return (
                origin
                + f"^BQ{orientation},2,{magnification},M,7^FH\\^FDMA,".encode()
                + _field_hex(symbol.payload)
                + b"^FS"
            )
        case "ean13":
            body = _ean13_body(symbol.payload)
            module = width // 117
            if module < 1:
                raise ProductError("EAN-13 region is too small for required quiet zones")
            return (
                f"^FO{x + 11 * module},{y}^BY{module}"
                f"^BE{orientation},{height},N,N^FD"
            ).encode() + body + b"^FS"
        case "code128" | "gs1128" as barcode_format:
            gs1 = barcode_format == "gs1128" or symbol.symbology_identifier == "]C1"
            data, codewords = _code128_data(symbol.payload, gs1)
            module = width // (11 * (codewords + 2) + 13 + 20)
            if module < 1:
                raise ProductError("Code 128 region is too small for required quiet zones")
            origin = (
                f"^FO{x + 10 * module},{y}^BY{module}"
                f"^BC{orientation},{height},N,N,N,N^FH\\^FD>:"
            ).encode()
            if gs1:
                origin += b">8"
            return origin + data + b"^FS"
        case unsupported:
            raise ProductError(f"unsupported native symbology: {unsupported}")


def _field_hex(payload: bytes) -> bytes:
    return b"".join(f"\\{byte:02X}".encode() for byte in payload)


def _code128_data(payload: bytes, gs1: bool) -> tuple[bytes, int]:
    encoded = bytearray()
    codewords = 1 if gs1 else 0
    for byte in payload:
        if gs1 and byte == 29:
            encoded.extend(b">8")
        elif 32 <= byte <= 126:
            match byte:
                case 62:
                    encoded.extend(b">0")
                case 94 | 126:
                    encoded.extend(f"\\{byte:02X}".encode())
                case _:
                    encoded.append(byte)
        else:
            raise ProductError("native Code 128 supports printable ASCII and GS1 separators only")
        codewords += 1
    return bytes(encoded), codewords


def _ean13_body(payload: bytes) -> bytes:
    if len(payload) != 13 or not payload.isdigit():
        raise ProductError("EAN-13 payload must contain exactly 13 digits")
    digits = [byte - 48 for byte in payload]
    check = (10 - (sum(digits[0:12:2]) + 3 * sum(digits[1:12:2])) % 10) % 10
    if check != digits[12]:
        raise ProductError("EAN-13 checksum is invalid")
    return payload[:12]


def _symbol_box(symbol: Symbol, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    if len(symbol.polygon) != 4:
        raise ProductError("native placement requires a four-corner polygon")
    xs = [point.x for point in symbol.polygon]
    ys = [point.y for point in symbol.polygon]
    left, top = _half_up(min(xs)), _half_up(min(ys))
    right, bottom = _half_up(max(xs)), _half_up(max(ys))
    outside = (
        left < 0
        or top < 0
        or right > image_size[0]
        or bottom > image_size[1]
        or left >= right
        or top >= bottom
    )
    if outside:
        raise ProductError("symbol polygon is outside the image")
    tolerance = 1.0
    for point in symbol.polygon:
        x_error = min(abs(point.x - left), abs(point.x - right))
        y_error = min(abs(point.y - top), abs(point.y - bottom))
        if x_error > tolerance or y_error > tolerance:
            raise ProductError("native placement requires an axis-aligned rectangular symbol")
    return left, top, right, bottom


def _safe_hybrid_background(source: Image.Image, symbols: tuple[Symbol, ...]) -> Image.Image:
    rgb = source.convert("RGB")
    boxes = [_symbol_box(symbol, rgb.size) for symbol in symbols]
    pixels = rgb.load()
    if pixels is None:
        raise ProductError("could not access hybrid image pixels")
    for index, (left, top, right, bottom) in enumerate(boxes):
        margin = max(1, min(right - left, bottom - top) // 20)
        outer = (
            max(0, left - margin),
            max(0, top - margin),
            min(rgb.width, right + margin),
            min(rgb.height, bottom + margin),
        )
        if outer[0] == left or outer[1] == top or outer[2] == right or outer[3] == bottom:
            raise ProductError("hybrid symbol lacks an in-bounds quiet-zone mask")
        for other_index, other in enumerate(boxes):
            if index != other_index and _boxes_overlap(outer, other):
                raise ProductError("hybrid quiet zone overlaps another symbol")
        for y in range(outer[1], outer[3]):
            for x in range(outer[0], outer[2]):
                if left <= x < right and top <= y < bottom:
                    continue
                red, green, blue = pixels[x, y]
                if red < 250 or green < 250 or blue < 250:
                    raise ProductError("hybrid quiet zone contains non-white content")
    masked = rgb.copy()
    draw = ImageDraw.Draw(masked)
    for left, top, right, bottom in boxes:
        draw.rectangle((left, top, right - 1, bottom - 1), fill=_WHITE)
    return masked


def _boxes_overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
    horizontal = first[0] < second[2] and first[2] > second[0]
    vertical = first[1] < second[3] and first[3] > second[1]
    return horizontal and vertical


def _orientation(value: int | None) -> str:
    match value:
        case None | 0:
            return "N"
        case 90:
            return "R"
        case 180:
            return "I"
        case 270:
            return "B"
        case _:
            raise ProductError(
                "native placement supports only 0, 90, 180, or 270 degree orientation"
            )


def _normalized_format(value: str) -> str:
    return value.lower().replace("-", "").replace("_", "").replace(" ", "")


def _half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
