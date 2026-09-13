from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from wonder_qr.cli import build_parser, main


class CliBoundaryTests(unittest.TestCase):
    def test_all_help_spellings_exit_successfully(self) -> None:
        for spelling in ("-h", "--help", "-help"):
            with self.subTest(spelling=spelling), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    build_parser().parse_args([spelling])
                self.assertEqual(raised.exception.code, 0)

    def test_missing_image_returns_io_exit(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"

            with contextlib.redirect_stderr(stderr):
                result = main(
                    ["decode", "definitely-missing.png", "--output", str(output)]
                )

            self.assertEqual(result, 4)
            report = json.loads(output.read_text(encoding="utf-8"))["reports"][0]
            self.assertEqual(report["errors"][0]["code"], "input_io")


if __name__ == "__main__":
    unittest.main()
