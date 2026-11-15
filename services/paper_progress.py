"""A winding, dotted paper-plane route; decorative beside the question counter."""
import math

from services.ui_style import BRAND_PLANE


def progress_route(index, total, previous=None):
    def point(t):
        return 20 + 560*t, 48 + 22*math.sin(4*math.pi*t)

    stops = min(max(total, 1), 12)
    fraction = max(0, min(index / max(1, total-1), 1))
    before = fraction if previous is None else max(0, min(previous / max(1, total-1), 1))
    points = [point(i/120) for i in range(121)]
    path = 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x,y in points)
    # Motion follows physical distance along the same polyline as the dots.
    lengths = [0.0]
    for a,b in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.dist(a,b))
    def distance(t):
        position = t*120
        lower = min(int(position), 119)
        return (lengths[lower] + (position-lower)*(lengths[lower+1]-lengths[lower])) / lengths[-1]
    dots = ''.join(f'<circle class="route-stop" cx="{point(t)[0]:.2f}" cy="{point(t)[1]:.2f}" r="4"/>'
                   for t in ([i/(stops-1) for i in range(stops)] if stops>1 else [0]))
    plane = BRAND_PLANE.read_text(encoding='utf-8')
    # Inner SVG keeps the shared vector and uses a small fixed visual footprint.
    plane = plane.replace('<svg ', '<svg x="-17" y="-13" width="34" height="26" ', 1)
    x,y = point(fraction)
    return (f'<svg class="paper-progress-route" viewBox="0 0 600 96" aria-hidden="true">'
            f'<path class="route-line" d="{path}"/>{dots}'
            f'<g class="route-plane-static" transform="translate({x:.2f} {y:.2f})">{plane}</g>'
            f'<g class="route-plane-moving">{plane}<animateMotion dur="700ms" fill="freeze" '
            f'path="{path}" keyPoints="{distance(before):.6f};{distance(fraction):.6f}" '
            'keyTimes="0;1" calcMode="linear"/></g></svg>')
