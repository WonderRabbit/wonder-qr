from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import TypeAlias

from wonder_qr.models import DecodeReport, ImageSize, ProductError, SCHEMA_VERSION, Symbol

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def serialize_reports(reports: tuple[DecodeReport, ...], output_format: str) -> bytes:
    if output_format == "jsonl":
        text = "\n".join(
            json.dumps(_report_data(report), ensure_ascii=False, separators=(",", ":"))
            for report in reports
        )
        return (text + "\n").encode()
    data = {"schema_version": SCHEMA_VERSION, "reports": [_report_data(item) for item in reports]}
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def serialize_diagnostic(
    command: str,
    requested_mode: str | None,
    actual_mode: str | None,
    fallback_reason: str | None,
    exit_code: int,
    reports: tuple[DecodeReport, ...],
    elapsed_ms: tuple[float, ...],
) -> bytes:
    data = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "requested_mode": requested_mode,
        "actual_mode": actual_mode,
        "fallback_reason": fallback_reason,
        "exit_code": exit_code,
        "reports": [_report_data(item) for item in reports],
        "metrics": {
            "reports": [
                {"source": report.source, "elapsed_ms": elapsed}
                for report, elapsed in zip(reports, elapsed_ms)
            ],
            "total_elapsed_ms": sum(elapsed_ms),
        },
    }
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def write_atomic(path: Path, data: bytes, force: bool) -> None:
    path.parent.mkdir(parents=False, exist_ok=True)
    if path.exists() and not force:
        raise ProductError(f"output already exists: {path}")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as file:
            temporary_path = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if force:
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
            temporary_path.unlink()
    except FileExistsError as error:
        raise ProductError(f"output already exists: {path}") from error
    except OSError as error:
        raise ProductError(f"cannot write output {path}: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _report_data(report: DecodeReport) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": report.source,
        "image": None
        if report.image is None
        else {
            "original": _size_data(report.original_image),
            "normalized": _size_data(report.image),
        },
        "status": report.status.value,
        "completeness": report.completeness.value,
        "symbols": [_symbol_data(symbol) for symbol in report.symbols],
        "errors": [
            {
                "code": issue.code,
                "message": issue.message,
                "attempt_id": issue.attempt_id,
                "symbol_index": issue.symbol_index,
            }
            for issue in report.errors
        ],
        "attempts": [
            {
                "id": attempt.id,
                "kind": attempt.kind,
                "disposition": attempt.disposition,
                "error_codes": list(attempt.error_codes),
            }
            for attempt in report.attempts
        ],
        "transforms": [
            {
                "attempt_id": transform.attempt_id,
                "normalized_to_candidate": list(transform.normalized_to_candidate),
            }
            for transform in report.transforms
        ],
    }


def _symbol_data(symbol: Symbol) -> dict[str, JsonValue]:
    return {
        "payload_base64": base64.b64encode(symbol.payload).decode("ascii"),
        "text": symbol.text,
        "format": symbol.format,
        "symbology_identifier": symbol.symbology_identifier,
        "content_type": symbol.content_type,
        "orientation": symbol.orientation,
        "polygon": [[point.x, point.y] for point in symbol.polygon],
        "source_polygon": [[point.x, point.y] for point in symbol.source_polygon],
        "provenance": {"attempt_ids": list(symbol.provenance.attempt_ids)},
    }


def _size_data(size: ImageSize | None) -> dict[str, JsonValue] | None:
    if size is None:
        return None
    return {"width": size.width, "height": size.height}
