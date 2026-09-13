from __future__ import annotations

import socket
from decimal import Decimal
from io import BytesIO
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError

from .models import PrinterProfile, ProductError, UsageError

_LABELARY_BASE: Final = "https://api.labelary.com/v1/printers"
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"


def render_zpl(
    zpl: bytes,
    profile: PrinterProfile,
    *,
    label_index: int,
    allow_network: bool,
    timeout_seconds: float = 30.0,
) -> bytes:
    if not allow_network:
        raise UsageError("Labelary requires explicit --allow-network permission")
    if profile.dpmm not in {6, 8, 12, 24}:
        raise UsageError("dpmm must be one of 6, 8, 12, or 24")
    if label_index < 0:
        raise UsageError("label index must be zero or greater")
    if timeout_seconds <= 0:
        raise UsageError("renderer timeout must be greater than zero")
    if not zpl:
        raise ProductError("ZPL input is empty")
    if profile.width_mm <= 0 or profile.height_mm <= 0:
        raise UsageError("label width and height must be greater than zero")
    width = _decimal_text(profile.width_mm / Decimal("25.4"))
    height = _decimal_text(profile.height_mm / Decimal("25.4"))
    url = f"{_LABELARY_BASE}/{profile.dpmm}dpmm/labels/{width}x{height}/{label_index}"
    request = Request(
        url,
        data=zpl,
        headers={
            "Accept": "image/png",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "wonder-qr/0.1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            png = response.read()
    except HTTPError as error:
        raise ProductError(f"Labelary returned HTTP {error.code}") from None
    except (URLError, TimeoutError, socket.timeout) as error:
        reason = error.reason if isinstance(error, URLError) else error
        raise ProductError(f"Labelary request failed: {reason}") from None
    if not png.startswith(_PNG_SIGNATURE):
        raise ProductError("Labelary response is not a PNG image")
    try:
        with Image.open(BytesIO(png)) as rendered:
            if rendered.format != "PNG":
                raise ProductError("Labelary response is not a PNG image")
            rendered.verify()
    except (UnidentifiedImageError, OSError):
        raise ProductError("Labelary returned an invalid PNG image") from None
    return png


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")).normalize(), "f")
