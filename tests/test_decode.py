from __future__ import annotations

import base64
import json
import unittest

from wonder_qr.geometry import polygon_iou, transform_point
from wonder_qr.models import (
    Completeness,
    DecodeReport,
    DecodeStatus,
    ImageSize,
    Point,
    Provenance,
    Symbol,
)
from wonder_qr.output import serialize_reports


class DecodeBoundaryTests(unittest.TestCase):
    def test_payload_bytes_and_coordinates_are_lossless_in_json(self) -> None:
        payload = b"\xff\x1dABC"
        polygon = (Point(1.25, 2.5), Point(5.0, 2.5), Point(5.0, 7.0), Point(1.25, 7.0))
        symbol = Symbol(
            payload,
            None,
            "Code128",
            "]C1",
            "Binary",
            0,
            polygon,
            polygon,
            Provenance((0, 2)),
        )
        report = DecodeReport(
            "label.png",
            ImageSize(10, 20),
            ImageSize(10, 20),
            DecodeStatus.OK,
            Completeness.UNKNOWN,
            (symbol,),
        )

        result = json.loads(serialize_reports((report,), "json"))

        encoded = result["reports"][0]["symbols"][0]
        self.assertEqual(base64.b64decode(encoded["payload_base64"]), payload)
        self.assertEqual(encoded["polygon"][0], [1.25, 2.5])

    def test_polygon_iou_distinguishes_same_and_separate_locations(self) -> None:
        first = (Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10))
        same = (Point(1, 1), Point(9, 1), Point(9, 9), Point(1, 9))
        separate = (Point(20, 20), Point(30, 20), Point(30, 30), Point(20, 30))

        self.assertGreater(polygon_iou(first, same), 0.6)
        self.assertEqual(polygon_iou(first, separate), 0.0)

    def test_projective_coordinate_mapping_preserves_fractional_values(self) -> None:
        matrix = (2.0, 0.0, 3.0, 0.0, 4.0, 5.0, 0.0, 0.0, 1.0)

        result = transform_point(Point(1.25, 2.5), matrix)

        self.assertEqual(result, Point(5.5, 15.0))


if __name__ == "__main__":
    unittest.main()
