from __future__ import annotations

from decimal import Decimal

import pytest
from PIL import Image

from wonder_qr.input import NormalizedImage
from wonder_qr.models import (
    Completeness,
    DecodeReport,
    DecodeStatus,
    ImageSize,
    NoResultError,
    PartialResultError,
    Point,
    PrinterProfile,
    ProductError,
    Provenance,
    Symbol,
    UsageError,
)
from wonder_qr.renderer import render_zpl
from wonder_qr.zpl import image_to_zpl


def _image(width: int, height: int) -> NormalizedImage:
    size = ImageSize(width, height)
    return NormalizedImage(
        source="fixture.png",
        image=Image.new("RGB", (width, height), "white"),
        original_size=size,
        normalized_size=size,
        normalized_to_source=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    )


def _report(symbol: Symbol, size: ImageSize) -> DecodeReport:
    return DecodeReport(
        source="fixture.png",
        image=size,
        original_image=size,
        status=DecodeStatus.OK,
        completeness=Completeness.UNKNOWN,
        symbols=(symbol,),
    )


def test_raster_packs_black_pixels_msb_first_with_row_padding() -> None:
    # Given
    image = _image(13, 3)
    black = image.image.load()
    assert black is not None
    for x in (0, 7, 8, 12):
        black[x, 0] = (0, 0, 0)
    profile = PrinterProfile(8, Decimal("1.625"), Decimal("0.375"))

    # When
    zpl, actual_mode, fallback_reason = image_to_zpl(image, profile)

    # Then
    assert b"^GFA,6,6,2,818800000000" in zpl
    assert actual_mode == "raster"
    assert fallback_reason is None


def test_native_ean13_validates_checksum_and_sends_twelve_digits() -> None:
    # Given
    image = _image(200, 100)
    symbol = Symbol(
        payload=b"4006381333931",
        text="4006381333931",
        format="EAN13",
        symbology_identifier="]E0",
        content_type="Text",
        orientation=0,
        polygon=(Point(20, 20), Point(180, 20), Point(180, 80), Point(20, 80)),
        source_polygon=(),
        provenance=Provenance((0,)),
    )

    # When
    zpl, actual_mode, _ = image_to_zpl(
        image,
        PrinterProfile(8, Decimal("25"), Decimal("12.5")),
        mode="native",
        report=_report(symbol, ImageSize(200, 100)),
    )

    # Then
    assert b"^BEN" in zpl
    assert b"^FD400638133393^FS" in zpl
    assert actual_mode == "native"


def test_native_rejects_command_bytes_in_qr_payload() -> None:
    # Given
    image = _image(100, 100)
    symbol = Symbol(
        payload=b"line\nfeed",
        text=None,
        format="QRCode",
        symbology_identifier="]Q1",
        content_type="Binary",
        orientation=0,
        polygon=(Point(10, 10), Point(90, 10), Point(90, 90), Point(10, 90)),
        source_polygon=(),
        provenance=Provenance((0,)),
    )

    # When / Then
    with pytest.raises(ProductError, match="QR.*ASCII"):
        image_to_zpl(
            image,
            PrinterProfile(8, Decimal("12.5"), Decimal("12.5")),
            mode="native",
            report=_report(symbol, ImageSize(100, 100)),
        )


def test_native_preserves_no_result_and_partial_exit_classes() -> None:
    # Given
    image = _image(100, 100)
    no_result = DecodeReport(
        source="fixture.png",
        image=ImageSize(100, 100),
        original_image=ImageSize(100, 100),
        status=DecodeStatus.NO_RESULT,
        completeness=Completeness.UNKNOWN,
    )
    partial = DecodeReport(
        source="fixture.png",
        image=ImageSize(100, 100),
        original_image=ImageSize(100, 100),
        status=DecodeStatus.PARTIAL,
        completeness=Completeness.EXPECTED_COUNT_MISMATCH,
        symbols=(
            Symbol(
                payload=b"safe",
                text="safe",
                format="QRCode",
                symbology_identifier="]Q1",
                content_type="Text",
                orientation=0,
                polygon=(Point(10, 10), Point(90, 10), Point(90, 90), Point(10, 90)),
                source_polygon=(),
                provenance=Provenance((0,)),
            ),
        ),
    )
    profile = PrinterProfile(8, Decimal("12.5"), Decimal("12.5"))

    # When / Then
    with pytest.raises(NoResultError):
        image_to_zpl(image, profile, mode="native", report=no_result)
    with pytest.raises(PartialResultError):
        image_to_zpl(image, profile, mode="native", report=partial)


def test_renderer_requires_explicit_network_permission() -> None:
    # Given
    profile = PrinterProfile(8, Decimal("100"), Decimal("50"))

    # When / Then
    with pytest.raises(UsageError, match="allow-network"):
        render_zpl(b"^XA^XZ", profile, label_index=0, allow_network=False)
