from __future__ import annotations

from dataclasses import dataclass, replace
from time import monotonic
from typing import TYPE_CHECKING, Protocol

from wonder_qr.geometry import (
    IDENTITY,
    Matrix,
    inverse,
    multiply,
    parse_quad,
    parse_roi,
    polygon_iou,
    quad_output_size,
    rectangle_to_quad,
    transform_polygon,
)
from wonder_qr.input import MAX_IMAGE_PIXELS, NormalizedImage
from wonder_qr.models import (
    Completeness,
    DecodeAttempt,
    DecodeIssue,
    DecodeProfile,
    DecodeReport,
    DecodeStatus,
    Point,
    ProductError,
    Provenance,
    Symbol,
    Transform,
)

if TYPE_CHECKING:
    from PIL import Image


class _ZXingPosition(Protocol):
    top_left: Point
    top_right: Point
    bottom_right: Point
    bottom_left: Point


class _ZXingResult(Protocol):
    valid: bool
    bytes: bytes
    text: str
    format: str
    symbology_identifier: str
    content_type: str
    orientation: int
    position: _ZXingPosition


@dataclass(frozen=True, slots=True)
class _Candidate:
    kind: str
    image: Image.Image
    candidate_to_normalized: Matrix
    skip_code: str | None = None


def decode_image(
    loaded: NormalizedImage,
    profile: DecodeProfile = DecodeProfile.STANDARD,
    expected_count: int | None = None,
    selection: tuple[str, str] | None = None,
) -> DecodeReport:
    try:
        import zxingcpp
    except ModuleNotFoundError as error:
        raise ProductError(
            "barcode decoding is unavailable; install wonder-qr with its zxing-cpp dependency"
        ) from error
    base = _select(loaded, selection)
    candidates = _candidates(base, profile)
    symbols: list[Symbol] = []
    issues: list[DecodeIssue] = []
    attempts: list[DecodeAttempt] = []
    transforms: list[Transform] = []
    started = monotonic()
    for attempt_id, candidate in enumerate(candidates):
        if monotonic() - started >= 5.0:
            attempts.append(DecodeAttempt(attempt_id, candidate.kind, "skipped", ("budget",)))
            issues.append(DecodeIssue("budget", "soft decode budget reached", attempt_id))
            continue
        if candidate.skip_code is not None:
            attempts.append(
                DecodeAttempt(attempt_id, candidate.kind, "skipped", (candidate.skip_code,))
            )
            continue
        if candidate.image.width * candidate.image.height > MAX_IMAGE_PIXELS:
            attempts.append(
                DecodeAttempt(attempt_id, candidate.kind, "skipped", ("resource_limit",))
            )
            continue
        kwargs = {"try_rotate": True, "try_downscale": True, "try_invert": True, "return_errors": True}
        if candidate.kind == "fixed":
            kwargs["binarizer"] = zxingcpp.Binarizer.FixedThreshold
        elif candidate.kind == "histogram":
            kwargs["binarizer"] = zxingcpp.Binarizer.GlobalHistogram
        try:
            decoded = zxingcpp.read_barcodes(candidate.image, **kwargs)
        except RuntimeError as error:
            attempts.append(DecodeAttempt(attempt_id, candidate.kind, "failed", ("format",)))
            issues.append(DecodeIssue("format", str(error), attempt_id))
            continue
        attempts.append(DecodeAttempt(attempt_id, candidate.kind, "completed"))
        transforms.append(Transform(attempt_id, inverse(candidate.candidate_to_normalized)))
        for result in decoded:
            if not result.valid:
                issues.append(DecodeIssue("checksum", "decoder rejected a candidate", attempt_id))
                continue
            symbol = _to_symbol(result, attempt_id, candidate.candidate_to_normalized, loaded)
            symbols = _merge(symbols, symbol)
        if expected_count is not None and len(symbols) >= expected_count:
            break
    symbols.sort(key=_sort_key)
    issues.extend(_conflicts(symbols))
    completeness = _completeness(expected_count, len(symbols))
    if completeness is Completeness.EXPECTED_COUNT_MISMATCH:
        issues.append(DecodeIssue("expected_count", "decoded count does not match expected count"))
    status = _status(symbols, issues)
    return DecodeReport(
        source=loaded.source,
        image=loaded.normalized_size,
        original_image=loaded.original_size,
        status=status,
        completeness=completeness,
        symbols=tuple(symbols),
        errors=tuple(issues),
        attempts=tuple(attempts),
        transforms=tuple(transforms),
    )


def _select(loaded: NormalizedImage, selection: tuple[str, str] | None) -> _Candidate:
    if selection is None:
        return _Candidate("base", loaded.image, IDENTITY)
    name, value = selection
    if name == "roi":
        x, y, width, height = parse_roi(
            value, loaded.normalized_size.width, loaded.normalized_size.height
        )
        return _Candidate(
            "base",
            loaded.image.crop((x, y, x + width, y + height)),
            (1.0, 0.0, float(x), 0.0, 1.0, float(y), 0.0, 0.0, 1.0),
        )
    points = parse_quad(value, loaded.normalized_size.width, loaded.normalized_size.height)
    width, height = quad_output_size(points)
    matrix = rectangle_to_quad(points, width, height)
    from PIL import Image

    image = loaded.image.transform(
        (width, height), Image.Transform.PERSPECTIVE, matrix[:8], Image.Resampling.BICUBIC
    )
    return _Candidate("base", image, matrix)


def _candidates(base: _Candidate, profile: DecodeProfile) -> tuple[_Candidate, ...]:
    if profile is DecodeProfile.STANDARD:
        return (base,)
    from PIL import ImageOps

    gray = ImageOps.grayscale(base.image)
    scale = (0.5, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 1.0)
    if gray.width * gray.height * 4 <= MAX_IMAGE_PIXELS:
        doubled = gray.resize((gray.width * 2, gray.height * 2))
        upscale = _Candidate(
            "upscale2", doubled, multiply(base.candidate_to_normalized, scale)
        )
    else:
        upscale = _Candidate("upscale2", gray, base.candidate_to_normalized, "resource_limit")
    crops = _end_crops(gray, base.candidate_to_normalized)
    return (
        base,
        _Candidate("fixed", gray, base.candidate_to_normalized),
        _Candidate("histogram", gray, base.candidate_to_normalized),
        upscale,
        *crops,
    )


def _end_crops(image: Image.Image, base_matrix: Matrix) -> tuple[_Candidate, _Candidate]:
    if image.width >= image.height:
        crop_width = max(1, round(image.width * 0.6))
        boxes = ((0, 0, crop_width, image.height), (image.width - crop_width, 0, image.width, image.height))
    else:
        crop_height = max(1, round(image.height * 0.6))
        boxes = ((0, 0, image.width, crop_height), (0, image.height - crop_height, image.width, image.height))
    candidates = []
    for kind, box in zip(("crop_start", "crop_end"), boxes):
        translation = (1.0, 0.0, float(box[0]), 0.0, 1.0, float(box[1]), 0.0, 0.0, 1.0)
        candidates.append(
            _Candidate(kind, image.crop(box), multiply(base_matrix, translation))
        )
    return candidates[0], candidates[1]


def _to_symbol(
    result: _ZXingResult,
    attempt_id: int,
    candidate_to_normalized: Matrix,
    loaded: NormalizedImage,
) -> Symbol:
    position = result.position
    candidate_polygon = tuple(
        Point(float(point.x), float(point.y))
        for point in (
            position.top_left,
            position.top_right,
            position.bottom_right,
            position.bottom_left,
        )
    )
    polygon = transform_polygon(candidate_polygon, candidate_to_normalized)
    source_polygon = transform_polygon(polygon, loaded.normalized_to_source)
    return Symbol(
        payload=bytes(result.bytes),
        text=result.text or None,
        format=str(result.format),
        symbology_identifier=result.symbology_identifier or None,
        content_type=str(result.content_type) or None,
        orientation=int(result.orientation),
        polygon=polygon,
        source_polygon=source_polygon,
        provenance=Provenance((attempt_id,)),
    )


def _merge(symbols: list[Symbol], candidate: Symbol) -> list[Symbol]:
    for index, current in enumerate(symbols):
        if (
            current.format == candidate.format
            and current.payload == candidate.payload
            and polygon_iou(current.polygon, candidate.polygon) >= 0.7
        ):
            attempt_ids = tuple(
                sorted(set(current.provenance.attempt_ids + candidate.provenance.attempt_ids))
            )
            symbols[index] = replace(current, provenance=Provenance(attempt_ids))
            return symbols
    symbols.append(candidate)
    return symbols


def _conflicts(symbols: list[Symbol]) -> list[DecodeIssue]:
    issues = []
    for index, left in enumerate(symbols):
        for right in symbols[index + 1 :]:
            if (left.format != right.format or left.payload != right.payload) and polygon_iou(
                left.polygon, right.polygon
            ) >= 0.7:
                issues.append(DecodeIssue("conflicting_result", "decoders disagree at one location"))
    return issues


def _completeness(expected_count: int | None, actual_count: int) -> Completeness:
    if expected_count is None:
        return Completeness.UNKNOWN
    if expected_count == actual_count:
        return Completeness.EXPECTED_COUNT_MET
    return Completeness.EXPECTED_COUNT_MISMATCH


def _status(symbols: list[Symbol], issues: list[DecodeIssue]) -> DecodeStatus:
    if not symbols:
        return DecodeStatus.NO_RESULT
    if issues:
        return DecodeStatus.PARTIAL
    return DecodeStatus.OK


def _sort_key(symbol: Symbol) -> tuple[float, float, str, bytes]:
    return (
        min(point.y for point in symbol.polygon),
        min(point.x for point in symbol.polygon),
        symbol.format,
        symbol.payload,
    )
