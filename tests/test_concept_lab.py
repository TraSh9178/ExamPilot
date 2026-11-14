"""Tests for the pure mathematics in the Concept Lab."""

import pytest

from services.concept_lab import (
    cubic,
    cubic_derivative,
    limit_example,
    limit_table,
    secant_slope,
    tangent_line,
)


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (1.0, 3.0),
        (1.999, 3.999),
        (2.001, 4.001),
        (3.0, 5.0),
    ],
)
def test_limit_example_away_from_hole(x, expected):
    assert limit_example(x) == pytest.approx(expected)


def test_limit_example_is_undefined_at_two():
    with pytest.raises(ValueError, match="undefined"):
        limit_example(2.0)


def test_limit_table_values_approach_four_from_both_sides():
    distances = [1, 0.5, 0.1, 0.05, 0.01, 0.001]
    rows = limit_table(distances)

    assert len(rows) == len(distances)
    for distance, row in zip(distances, rows):
        assert row["distance"] == distance
        assert row["left_x"] == pytest.approx(2 - distance)
        assert row["right_x"] == pytest.approx(2 + distance)
        assert row["left_value"] == pytest.approx(4 - distance)
        assert row["right_value"] == pytest.approx(4 + distance)

    left_errors = [abs(row["left_value"] - 4) for row in rows]
    right_errors = [abs(row["right_value"] - 4) for row in rows]
    assert all(a > b for a, b in zip(left_errors, left_errors[1:]))
    assert all(a > b for a, b in zip(right_errors, right_errors[1:]))


def test_limit_table_rejects_zero_distance():
    with pytest.raises(ValueError, match="positive"):
        limit_table([0.0])


@pytest.mark.parametrize(
    ("x", "expected_cubic", "expected_derivative"),
    [
        (-2.0, 2.0, 7.0),
        (0.0, 0.0, -5.0),
        (1.0, -4.0, -2.0),
        (1.5, -4.125, 1.75),
        (2.0, -2.0, 7.0),
    ],
)
def test_cubic_and_exact_derivative(x, expected_cubic, expected_derivative):
    assert cubic(x) == pytest.approx(expected_cubic)
    assert cubic_derivative(x) == pytest.approx(expected_derivative)


@pytest.mark.parametrize("x0", [-2.0, 0.0, 1.5])
def test_secant_slope_approaches_derivative(x0):
    assert abs(secant_slope(x0, 1e-6) - cubic_derivative(x0)) < 1e-4


def test_secant_slope_is_undefined_when_h_is_zero():
    with pytest.raises(ValueError, match="nonzero"):
        secant_slope(1.0, 0.0)


@pytest.mark.parametrize("x0", [-2.0, 0.0, 1.0, 1.5, 2.0])
def test_tangent_line_passes_through_curve_with_exact_slope(x0):
    slope, intercept = tangent_line(x0)

    assert slope == pytest.approx(cubic_derivative(x0))
    assert slope * x0 + intercept == pytest.approx(cubic(x0))
