from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from pathlib import Path
from typing import Final

SCHEMA_VERSION: Final = 1


class DecodeProfile(str, Enum):
    STANDARD = "standard"
    ROBUST = "robust"


class DecodeStatus(str, Enum):
    OK = "ok"
    NO_RESULT = "no_result"
    PARTIAL = "partial"
    ERROR = "error"


class Completeness(str, Enum):
    UNKNOWN = "unknown"
    EXPECTED_COUNT_MET = "expected_count_met"
    EXPECTED_COUNT_MISMATCH = "expected_count_mismatch"


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class ImageSize:
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Provenance:
    attempt_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Symbol:
    payload: bytes
    text: str | None
    format: str
    symbology_identifier: str | None
    content_type: str | None
    orientation: int | None
    polygon: tuple[Point, ...]
    source_polygon: tuple[Point, ...]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class DecodeIssue:
    code: str
    message: str
    attempt_id: int | None = None
    symbol_index: int | None = None


@dataclass(frozen=True, slots=True)
class DecodeAttempt:
    id: int
    kind: str
    disposition: str
    error_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Transform:
    attempt_id: int
    normalized_to_candidate: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class DecodeReport:
    source: str
    image: ImageSize | None
    original_image: ImageSize | None
    status: DecodeStatus
    completeness: Completeness
    symbols: tuple[Symbol, ...] = ()
    errors: tuple[DecodeIssue, ...] = ()
    attempts: tuple[DecodeAttempt, ...] = ()
    transforms: tuple[Transform, ...] = ()


@dataclass(frozen=True, slots=True)
class PrinterProfile:
    dpmm: int
    width_mm: Decimal
    height_mm: Decimal

    @property
    def width_dots(self) -> int:
        return int((self.width_mm * self.dpmm).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def height_dots(self) -> int:
        return int((self.height_mm * self.dpmm).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class AppError(Exception):
    message: str
    exit_code: int

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class UsageError(AppError):
    exit_code: int = 2


@dataclass(frozen=True, slots=True)
class NoResultError(AppError):
    exit_code: int = 3


@dataclass(frozen=True, slots=True)
class ProductError(AppError):
    exit_code: int = 4


@dataclass(frozen=True, slots=True)
class InputError(ProductError):
    issue_code: str = "input_io"


@dataclass(frozen=True, slots=True)
class PartialResultError(AppError):
    exit_code: int = 5


@dataclass(frozen=True, slots=True)
class OutputTarget:
    path: Path | None
    force: bool
