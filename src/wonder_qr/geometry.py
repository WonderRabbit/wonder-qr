from __future__ import annotations

from math import hypot

from wonder_qr.models import Point, UsageError

Matrix = tuple[float, ...]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def transform_point(point: Point, matrix: Matrix) -> Point:
    scale = matrix[6] * point.x + matrix[7] * point.y + matrix[8]
    if abs(scale) < 1e-12:
        raise UsageError("coordinate transform is singular")
    return Point(
        (matrix[0] * point.x + matrix[1] * point.y + matrix[2]) / scale,
        (matrix[3] * point.x + matrix[4] * point.y + matrix[5]) / scale,
    )


def transform_polygon(points: tuple[Point, ...], matrix: Matrix) -> tuple[Point, ...]:
    return tuple(transform_point(point, matrix) for point in points)


def multiply(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        sum(left[row * 3 + index] * right[index * 3 + column] for index in range(3))
        for row in range(3)
        for column in range(3)
    )


def inverse(matrix: Matrix) -> Matrix:
    determinant = (
        matrix[0] * (matrix[4] * matrix[8] - matrix[5] * matrix[7])
        - matrix[1] * (matrix[3] * matrix[8] - matrix[5] * matrix[6])
        + matrix[2] * (matrix[3] * matrix[7] - matrix[4] * matrix[6])
    )
    if abs(determinant) < 1e-12:
        raise UsageError("coordinate transform is singular")
    return tuple(
        value / determinant
        for value in (
            matrix[4] * matrix[8] - matrix[5] * matrix[7],
            matrix[2] * matrix[7] - matrix[1] * matrix[8],
            matrix[1] * matrix[5] - matrix[2] * matrix[4],
            matrix[5] * matrix[6] - matrix[3] * matrix[8],
            matrix[0] * matrix[8] - matrix[2] * matrix[6],
            matrix[2] * matrix[3] - matrix[0] * matrix[5],
            matrix[3] * matrix[7] - matrix[4] * matrix[6],
            matrix[1] * matrix[6] - matrix[0] * matrix[7],
            matrix[0] * matrix[4] - matrix[1] * matrix[3],
        )
    )


def parse_roi(value: str, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    values = _parse_numbers(value, 4, "ROI")
    x, y, width, height = (int(item) for item in values)
    if any(item != integer for item, integer in zip(values, (x, y, width, height))):
        raise UsageError("ROI values must be integers")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise UsageError("ROI must use non-negative origin and positive size")
    if x + width > image_width or y + height > image_height:
        raise UsageError("ROI lies outside the normalized image")
    return x, y, width, height


def parse_quad(value: str, image_width: int, image_height: int) -> tuple[Point, ...]:
    values = _parse_numbers(value, 8, "quad")
    points = tuple(Point(values[index], values[index + 1]) for index in range(0, 8, 2))
    if any(
        point.x < 0
        or point.y < 0
        or point.x >= image_width
        or point.y >= image_height
        for point in points
    ):
        raise UsageError("quad lies outside the normalized image")
    cross_products = tuple(_cross(points[index], points[(index + 1) % 4], points[(index + 2) % 4]) for index in range(4))
    if any(abs(value) < 1e-6 for value in cross_products):
        raise UsageError("quad is degenerate")
    positive = cross_products[0] > 0
    if any((value > 0) != positive for value in cross_products[1:]):
        raise UsageError("quad must be convex and ordered around its boundary")
    return points


def quad_output_size(points: tuple[Point, ...]) -> tuple[int, int]:
    width = max(_distance(points[0], points[1]), _distance(points[3], points[2]))
    height = max(_distance(points[0], points[3]), _distance(points[1], points[2]))
    return max(1, round(width)), max(1, round(height))


def rectangle_to_quad(points: tuple[Point, ...], width: int, height: int) -> Matrix:
    destinations = (
        Point(0.0, 0.0),
        Point(float(width), 0.0),
        Point(float(width), float(height)),
        Point(0.0, float(height)),
    )
    rows: list[list[float]] = []
    values: list[float] = []
    for source, target in zip(destinations, points):
        x, y = source.x, source.y
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -target.x * x, -target.x * y])
        values.append(target.x)
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -target.y * x, -target.y * y])
        values.append(target.y)
    solution = _solve(rows, values)
    return (*solution, 1.0)


def polygon_iou(left: tuple[Point, ...], right: tuple[Point, ...]) -> float:
    left_area = abs(_area(left))
    right_area = abs(_area(right))
    intersection = tuple(left)
    direction = 1.0 if _area(right) >= 0 else -1.0
    for index, edge_start in enumerate(right):
        intersection = _clip(
            intersection,
            edge_start,
            right[(index + 1) % len(right)],
            direction,
        )
        if not intersection:
            return 0.0
    intersection_area = abs(_area(intersection))
    union = left_area + right_area - intersection_area
    return 0.0 if union <= 0 else intersection_area / union


def _parse_numbers(value: str, count: int, name: str) -> tuple[float, ...]:
    try:
        values = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as error:
        raise UsageError(f"{name} must be comma-separated numbers") from error
    if len(values) != count:
        raise UsageError(f"{name} requires {count} values")
    return values


def _distance(left: Point, right: Point) -> float:
    return hypot(right.x - left.x, right.y - left.y)


def _cross(first: Point, second: Point, third: Point) -> float:
    return (second.x - first.x) * (third.y - second.y) - (second.y - first.y) * (third.x - second.x)


def _solve(matrix: list[list[float]], values: list[float]) -> tuple[float, ...]:
    size = len(values)
    augmented = [row[:] + [value] for row, value in zip(matrix, values)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise UsageError("quad transform is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * basis
                for current, basis in zip(augmented[row], augmented[column])
            ]
    return tuple(row[-1] for row in augmented)


def _area(points: tuple[Point, ...]) -> float:
    return sum(
        point.x * points[(index + 1) % len(points)].y
        - points[(index + 1) % len(points)].x * point.y
        for index, point in enumerate(points)
    ) / 2.0


def _clip(
    polygon: tuple[Point, ...], edge_start: Point, edge_end: Point, direction: float
) -> tuple[Point, ...]:
    result: list[Point] = []
    for index, current in enumerate(polygon):
        previous = polygon[index - 1]
        current_inside = direction * _cross(edge_start, edge_end, current) >= 0
        previous_inside = direction * _cross(edge_start, edge_end, previous) >= 0
        if current_inside != previous_inside:
            result.append(_intersection(previous, current, edge_start, edge_end))
        if current_inside:
            result.append(current)
    return tuple(result)


def _intersection(first: Point, second: Point, edge_start: Point, edge_end: Point) -> Point:
    dx, dy = second.x - first.x, second.y - first.y
    ex, ey = edge_end.x - edge_start.x, edge_end.y - edge_start.y
    denominator = dx * ey - dy * ex
    if abs(denominator) < 1e-12:
        return second
    scale = ((edge_start.x - first.x) * ey - (edge_start.y - first.y) * ex) / denominator
    return Point(first.x + scale * dx, first.y + scale * dy)
