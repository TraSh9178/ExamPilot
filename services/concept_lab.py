"""Pure math helpers for the Calculus I Concept Lab.

These functions do not depend on Streamlit, so they can be tested separately
from the interactive page.
"""


def limit_example(x: float) -> float:
    """Evaluate (x**2 - 4) / (x - 2) for x != 2.

    Factoring gives x + 2 away from the removable discontinuity.
    """
    if x == 2:
        raise ValueError("The function is undefined at x = 2.")
    return x + 2


def limit_table(distances: list[float]) -> list[dict]:
    """Calculate function values on both sides of x = 2."""
    rows = []
    for distance in distances:
        if distance <= 0:
            raise ValueError("Distances must be positive.")
        left_x = 2 - distance
        right_x = 2 + distance
        rows.append(
            {
                "distance": distance,
                "left_x": left_x,
                "left_value": limit_example(left_x),
                "right_x": right_x,
                "right_value": limit_example(right_x),
            }
        )
    return rows


def cubic(x: float) -> float:
    """Return f(x) = x**3 - 5*x."""
    return x**3 - 5 * x


def cubic_derivative(x: float) -> float:
    """Return the exact derivative f'(x) = 3*x**2 - 5."""
    return 3 * x**2 - 5


def secant_slope(x0: float, h: float) -> float:
    """Return the slope of the secant through x0 and x0 + h."""
    if h == 0:
        raise ValueError("The secant requires nonzero h.")
    return (cubic(x0 + h) - cubic(x0)) / h


def tangent_line(x0: float) -> tuple[float, float]:
    """Return (slope, intercept) of the tangent line at x0."""
    slope = cubic_derivative(x0)
    intercept = cubic(x0) - slope * x0
    return slope, intercept
