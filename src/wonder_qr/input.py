from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Final

from wonder_qr.models import ImageSize, InputError, ProductError

if TYPE_CHECKING:
    from PIL import Image

MAX_INPUT_BYTES: Final = 25 * 1024 * 1024
MAX_IMAGE_PIXELS: Final = 40_000_000
SUPPORTED_FORMATS: Final = frozenset({"PNG", "JPEG", "BMP", "TIFF"})


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    source: str
    image: Image.Image
    original_size: ImageSize
    normalized_size: ImageSize
    normalized_to_source: tuple[float, ...]


def read_image(path: Path | None, stdin: BinaryIO | None = None) -> NormalizedImage:
    source = "stdin" if path is None else str(path)
    if path is None:
        if stdin is None:
            raise ProductError("stdin input is unavailable")
        data = stdin.read(MAX_INPUT_BYTES + 1)
    else:
        if path.is_dir():
                raise InputError(f"input is a directory: {path}")
        try:
            size = path.stat().st_size
            if size > MAX_INPUT_BYTES:
                raise InputError(f"input exceeds 25 MiB limit: {path}", issue_code="resource_limit")
            data = path.read_bytes()
        except OSError as error:
            raise InputError(f"cannot read input {path}: {error}") from error
    if len(data) > MAX_INPUT_BYTES:
        raise InputError(f"input exceeds 25 MiB limit: {source}", issue_code="resource_limit")
    return _normalize_image(data, source)


def _normalize_image(data: bytes, source: str) -> NormalizedImage:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ModuleNotFoundError as error:
        raise ProductError(
            "image support is unavailable; install wonder-qr with its Pillow dependency"
        ) from error
    try:
        with Image.open(BytesIO(data)) as opened:
            image_format = opened.format
            frame_count = getattr(opened, "n_frames", 1)
            if image_format not in SUPPORTED_FORMATS:
                raise InputError(
                    f"unsupported image format: {image_format or 'unknown'}",
                    issue_code="unsupported_image",
                )
            if frame_count != 1:
                raise InputError(
                    "multi-frame and animated images are unsupported",
                    issue_code="unsupported_image",
                )
            opened.load()
            original_size = ImageSize(*opened.size)
            orientation = int(opened.getexif().get(274, 1))
            transposed = ImageOps.exif_transpose(opened)
            rgba = transposed.convert("RGBA")
            normalized = Image.new("RGB", rgba.size, "white")
            normalized.paste(rgba, mask=rgba.getchannel("A"))
    except (UnidentifiedImageError, OSError) as error:
        raise InputError(
            f"unsupported or damaged image: {source}", issue_code="unsupported_image"
        ) from error
    if normalized.width * normalized.height > MAX_IMAGE_PIXELS:
        raise InputError(
            f"normalized image exceeds 40 MP limit: {source}", issue_code="resource_limit"
        )
    return NormalizedImage(
        source=source,
        image=normalized,
        original_size=original_size,
        normalized_size=ImageSize(*normalized.size),
        normalized_to_source=_exif_inverse(orientation, original_size),
    )


def _exif_inverse(orientation: int, size: ImageSize) -> tuple[float, ...]:
    width = float(size.width - 1)
    height = float(size.height - 1)
    matrices = {
        1: (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        2: (-1.0, 0.0, width, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        3: (-1.0, 0.0, width, 0.0, -1.0, height, 0.0, 0.0, 1.0),
        4: (1.0, 0.0, 0.0, 0.0, -1.0, height, 0.0, 0.0, 1.0),
        5: (0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        6: (0.0, 1.0, 0.0, -1.0, 0.0, height, 0.0, 0.0, 1.0),
        7: (0.0, -1.0, width, -1.0, 0.0, height, 0.0, 0.0, 1.0),
        8: (0.0, -1.0, width, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
    }
    return matrices.get(orientation, matrices[1])
