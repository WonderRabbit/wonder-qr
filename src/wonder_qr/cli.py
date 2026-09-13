from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import monotonic

from wonder_qr import __version__
from wonder_qr.models import (
    AppError,
    Completeness,
    DecodeIssue,
    DecodeProfile,
    DecodeReport,
    DecodeStatus,
    InputError,
    PrinterProfile,
    ProductError,
    UsageError,
)
from wonder_qr.output import serialize_diagnostic, serialize_reports, write_atomic


def build_parser() -> argparse.ArgumentParser:
    parser = _parser(
        "wonder-qr",
        "Decode QR/barcodes and convert label images to and from ZPL.",
        "wonder-qr decode label.png\nwonder-qr to-zpl label.png --dpmm 8 --width-mm 100 --height-mm 50",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", title="subcommands")
    decode = _parser("decode", "Decode all supported symbols in one or more images.", "wonder-qr decode label.png --format json", commands)
    decode.add_argument("images", nargs="+")
    decode.add_argument("--format", choices=("json", "jsonl"), default="json")
    _decode_options(decode)
    _output_options(decode)

    to_zpl = _parser("to-zpl", "Convert an image to generic ZPL II. Raster mode preserves the full label.", "wonder-qr to-zpl label.png --mode raster --dpmm 8 --width-mm 100 --height-mm 50 --output label.zpl", commands)
    to_zpl.add_argument("image")
    to_zpl.add_argument("--mode", choices=("raster", "native", "hybrid"), default="raster")
    to_zpl.add_argument("--fallback", choices=("error", "raster"), default="error")
    to_zpl.add_argument("--layout", type=Path)
    to_zpl.add_argument("--hri", choices=("preserve", "regenerate"), default="preserve")
    _printer_options(to_zpl)
    _decode_options(to_zpl, include_selection=False)
    _output_options(to_zpl)

    to_image = _parser("to-image", "Render ZPL through Labelary. The complete ZPL is sent to an external service.", "wonder-qr to-image label.zpl --renderer labelary --allow-network --dpmm 8 --width-mm 100 --height-mm 50 --output label.png", commands)
    to_image.add_argument("zpl")
    to_image.add_argument("--renderer", choices=("labelary",), required=True)
    to_image.add_argument("--allow-network", action="store_true", required=True)
    to_image.add_argument("--label-index", type=int, default=0)
    _printer_options(to_image)
    to_image.add_argument("--output", type=Path, required=True)
    to_image.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
        if arguments.command is None:
            parser.error("a subcommand is required")
        if arguments.command == "decode":
            return _run_decode(arguments)
        if arguments.command == "to-zpl":
            return _run_to_zpl(arguments)
        return _run_to_image(arguments)
    except AppError as error:
        print(f"wonder-qr: {error}", file=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:
        print("wonder-qr: interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 1
    except Exception as error:  # noqa: BLE001, BROAD_EXCEPT_OK
        print(f"wonder-qr: internal error: {error}", file=sys.stderr)
        return 1


def _parser(
    name: str,
    description: str,
    examples: str,
    commands: argparse._SubParsersAction[argparse.ArgumentParser] | None = None,
) -> argparse.ArgumentParser:
    factory = argparse.ArgumentParser if commands is None else commands.add_parser
    parser = factory(
        name,
        description=description,
        epilog=f"Examples:\n  {examples.replace(chr(10), chr(10) + '  ')}\n\nExit codes: 0 success, 1 internal, 2 usage, 3 no result, 4 I/O/conversion, 5 partial.",
        add_help=False,
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-h", "--help", "-help", action="help", help="show this help message and exit")
    return parser


def _decode_options(parser: argparse.ArgumentParser, include_selection: bool = True) -> None:
    parser.add_argument("--profile", choices=("standard", "robust"), default="standard")
    parser.add_argument("--expected-count", type=int)
    if include_selection:
        selection = parser.add_mutually_exclusive_group()
        selection.add_argument("--roi")
        selection.add_argument("--quad")


def _output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--force", action="store_true")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--verbose", action="store_true")
    verbosity.add_argument("--quiet", action="store_true")


def _printer_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dpmm", type=int, choices=(6, 8, 12, 24))
    parser.add_argument("--width-mm")
    parser.add_argument("--height-mm")
    parser.add_argument("--printer-profile", type=Path)


def _run_decode(arguments: argparse.Namespace) -> int:
    if len(arguments.images) > 100:
        raise UsageError("decode accepts at most 100 inputs")
    if "-" in arguments.images and len(arguments.images) != 1:
        raise UsageError("stdin cannot be mixed with image paths")
    if (arguments.roi or arguments.quad) and len(arguments.images) != 1:
        raise UsageError("ROI and quad require exactly one input")
    _validate_expected(arguments.expected_count)
    _validate_targets(arguments.output, arguments.report, arguments.force)
    from wonder_qr.decoder import decode_image
    from wonder_qr.input import read_image

    reports: list[DecodeReport] = []
    elapsed: list[float] = []
    selection = ("roi", arguments.roi) if arguments.roi else (("quad", arguments.quad) if arguments.quad else None)
    for value in arguments.images:
        started = monotonic()
        try:
            loaded = read_image(None, sys.stdin.buffer) if value == "-" else read_image(Path(value))
            reports.append(decode_image(loaded, DecodeProfile(arguments.profile), arguments.expected_count, selection))
        except InputError as error:
            reports.append(_input_error(value, str(error), error.issue_code))
        elapsed.append((monotonic() - started) * 1000)
    result = tuple(reports)
    exit_code = _decode_exit(result)
    if arguments.report:
        write_atomic(arguments.report, serialize_diagnostic("decode", None, None, None, exit_code, result, tuple(elapsed)), arguments.force)
    payload = serialize_reports(result, arguments.format)
    _emit(payload, arguments.output, arguments.force)
    return exit_code


def _run_to_zpl(arguments: argparse.Namespace) -> int:
    _validate_expected(arguments.expected_count)
    _validate_targets(arguments.output, arguments.report, arguments.force)
    profile = _profile(arguments)
    if arguments.mode == "raster" and (arguments.layout or arguments.expected_count or arguments.fallback != "error" or arguments.hri != "preserve"):
        raise UsageError("raster mode does not accept layout, expected-count, fallback, or HRI options")
    if arguments.mode == "native" and (arguments.layout or arguments.hri != "preserve"):
        raise UsageError("native mode does not accept layout or HRI options")
    from wonder_qr.decoder import decode_image
    from wonder_qr.input import read_image
    from wonder_qr.zpl import image_to_zpl

    loaded = read_image(None, sys.stdin.buffer) if arguments.image == "-" else read_image(Path(arguments.image))
    started = monotonic()
    report = None
    if arguments.mode != "raster":
        report = decode_image(loaded, DecodeProfile(arguments.profile), arguments.expected_count)
    zpl, actual_mode, fallback_reason = image_to_zpl(
        loaded,
        profile,
        mode=arguments.mode,
        report=report,
        fallback=arguments.fallback,
        layout_path=arguments.layout,
        hri=arguments.hri,
    )
    elapsed = (monotonic() - started) * 1000
    reports = () if report is None else (report,)
    if arguments.report:
        write_atomic(arguments.report, serialize_diagnostic("to-zpl", arguments.mode, actual_mode, fallback_reason, 0, reports, (() if report is None else (elapsed,))), arguments.force)
    _emit(zpl, arguments.output, arguments.force)
    return 0


def _run_to_image(arguments: argparse.Namespace) -> int:
    profile = _profile(arguments)
    if arguments.label_index < 0:
        raise UsageError("label-index must be zero or greater")
    zpl = sys.stdin.buffer.read(8 * 1024 * 1024 + 1) if arguments.zpl == "-" else _read_bytes(Path(arguments.zpl))
    if len(zpl) > 8 * 1024 * 1024:
        raise ProductError("ZPL input exceeds 8 MiB limit")
    from wonder_qr.renderer import render_zpl

    png = render_zpl(zpl, profile, label_index=arguments.label_index, allow_network=arguments.allow_network, timeout_seconds=30.0)
    write_atomic(arguments.output, png, arguments.force)
    return 0


def _profile(arguments: argparse.Namespace) -> PrinterProfile:
    direct = (arguments.dpmm, arguments.width_mm, arguments.height_mm)
    if arguments.printer_profile is not None and any(value is not None for value in direct):
        raise UsageError("printer-profile cannot be combined with direct dimensions")
    if arguments.printer_profile is not None:
        try:
            data = json.loads(arguments.printer_profile.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                raise UsageError("printer profile schema_version must be 1")
            return _checked_profile(int(data["dpmm"]), str(data["width_mm"]), str(data["height_mm"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise UsageError(f"invalid printer profile: {error}") from error
    if any(value is None for value in direct):
        raise UsageError("provide dpmm, width-mm, and height-mm together")
    return _checked_profile(arguments.dpmm, arguments.width_mm, arguments.height_mm)


def _checked_profile(dpmm: int, width: str, height: str) -> PrinterProfile:
    try:
        profile = PrinterProfile(dpmm, Decimal(width), Decimal(height))
    except InvalidOperation as error:
        raise UsageError("width-mm and height-mm must be decimal numbers") from error
    if dpmm not in (6, 8, 12, 24) or profile.width_dots < 1 or profile.height_dots < 1:
        raise UsageError("printer dimensions must be positive and dpmm must be 6, 8, 12, or 24")
    if profile.width_dots > 8192 or profile.height_dots > 8192 or profile.width_dots * profile.height_dots > 16_777_216:
        raise ProductError("requested label exceeds resource limits")
    return profile


def _validate_expected(value: int | None) -> None:
    if value is not None and value < 1:
        raise UsageError("expected-count must be at least 1")


def _validate_targets(output: Path | None, report: Path | None, force: bool) -> None:
    if output is not None and report is not None and output.resolve() == report.resolve():
        raise UsageError("output and report must use different paths")
    for path in (output, report):
        if path is not None and path.exists() and not force:
            raise ProductError(f"output already exists: {path}")


def _emit(data: bytes, output: Path | None, force: bool) -> None:
    if output is not None:
        write_atomic(output, data, force)
    else:
        sys.stdout.buffer.write(data)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ProductError(f"cannot read input {path}: {error}") from error


def _input_error(source: str, message: str, code: str) -> DecodeReport:
    return DecodeReport(source, None, None, DecodeStatus.ERROR, Completeness.UNKNOWN, errors=(DecodeIssue(code, message),))


def _decode_exit(reports: tuple[DecodeReport, ...]) -> int:
    successes = sum(report.status is DecodeStatus.OK for report in reports)
    errors = sum(report.status is DecodeStatus.ERROR for report in reports)
    partials = sum(report.status is DecodeStatus.PARTIAL for report in reports)
    results = sum(bool(report.symbols) for report in reports)
    if successes and (errors or partials):
        return 5
    if partials:
        return 5
    if errors and not results:
        return 4
    if not results:
        return 3
    return 0
