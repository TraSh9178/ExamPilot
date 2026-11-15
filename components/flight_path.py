"""Responsive paper-plane route for the practice worksheet."""

from base64 import b64encode
from functools import lru_cache
from math import cos, pi, sin

from services.ui_style import BRAND_PLANE


@lru_cache(maxsize=1)
def _plane() -> str:
    return BRAND_PLANE.read_text(encoding="utf-8").replace(
        "<svg ", '<svg x="-19" y="-14" width="38" height="28" ', 1
    ).strip()


def _point(fraction: float) -> tuple[float, float]:
    x = 24 + 372 * fraction
    y = 29 + 11 * sin(4 * pi * fraction - 0.28) + 3 * sin(2 * pi * fraction)
    return x, y


def _slope(fraction: float) -> float:
    """Vertical change per unit of route fraction, for matching curve tangents."""
    return 44 * pi * cos(4 * pi * fraction - 0.28) + 6 * pi * cos(2 * pi * fraction)


def _coordinates(point: tuple[float, float]) -> str:
    return f"{point[0]:.2f} {point[1]:.2f}"


def _trail(stops: list[float]) -> str:
    path = f"M {_coordinates(_point(stops[0]))}"
    for start, end in zip(stops, stops[1:]):
        x0, y0 = _point(start)
        x1, y1 = _point(end)
        handle = (end - start) / 3
        path += (
            f" C {_coordinates((x0 + 372 * handle, y0 + _slope(start) * handle))}"
            f" {_coordinates((x1 - 372 * handle, y1 - _slope(end) * handle))}"
            f" {_coordinates((x1, y1))}"
        )
    return path


def practice_route(count: int, index: int, previous: int | None = None) -> str:
    """Produce an SVG image that can animate from either neighboring question."""
    stops = [step / (count - 1) for step in range(count)] if count > 1 else [0.5]
    # A short exercise still follows the same curves as a long one. Keep each
    # question on a spline vertex by including its fraction in the full route.
    bends = sorted(set(stops) | {step / 8 for step in range(9)})
    completed = [stop for stop in bends if stop <= stops[index]]
    x, y = _point(stops[index])
    dots = []
    for step, fraction in enumerate(stops):
        cx, cy = _point(fraction)
        radius = 5 if step == index else (2.7 if count <= 16 else 1.45)
        fill = "#FAF4EA" if step >= index else "#AD673C"
        stroke = "#9B582F" if step == index else "#8F8266"
        dots.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width=".9"/>'
        )
    paths = ""
    if count > 1:
        paths = (
            f'<path d="{_trail(bends)}" stroke="#A3987A" stroke-width="1.35" stroke-dasharray="3.5 4.7"/>'
            f'<path d="{_trail(completed)}" stroke="#AD673C" stroke-width="1.65" stroke-dasharray="3.5 4.7"/>'
        )

    plane = _plane()
    parked = f'<g class="parked" transform="translate({x:.2f} {y:.2f})">{plane}</g>'
    motion = ""
    if previous is not None and 0 <= previous < count and previous != index:
        start, end = stops[previous], stops[index]
        lower, upper = sorted((start, end))
        trip = [stop for stop in bends if lower <= stop <= upper]
        if start > end:
            trip.reverse()
        motion = (
            '<g class="flying">'
            f'<animateMotion dur=".66s" fill="freeze" rotate="auto" path="{_trail(trip)}"/>'
            f'<g transform="rotate(24)">{plane}</g></g>'
            '<style>.parked{display:none}'
            '@media (prefers-reduced-motion:reduce){.parked{display:inline}.flying{display:none}}</style>'
        )

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 58">'
        f'<g fill="none" stroke-linecap="round">{paths}</g>{"".join(dots)}{parked}{motion}</svg>'
    )
    source = b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="flight-route" alt="" src="data:image/svg+xml;base64,{source}">'
