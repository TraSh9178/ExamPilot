"""A winding, dotted paper-plane route; decorative beside the question counter."""
import hashlib
import math

from services.ui_style import BRAND_PLANE


def progress_route(index, total, previous=None):
    def point(t):
        return 20 + 560*t, 48 + 22*math.sin(4*math.pi*t)

    def angle(t):
        # Brand artwork points 25 degrees above its x axis. Align its nose
        # with the local tangent, reversing direction on a backwards jump.
        return math.degrees(math.atan2(88*math.pi*math.cos(4*math.pi*t), 560)) + 25 + (180 if fraction < before else 0)

    stops = min(max(total, 1), 12)
    fraction = max(0, min(index / max(1, total-1), 1))
    before = fraction if previous is None else max(0, min(previous / max(1, total-1), 1))
    points = [point(i/120) for i in range(121)]
    path = 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x,y in points)
    dots = ''.join(f'<circle class="route-stop" cx="{point(t)[0]:.2f}" cy="{point(t)[1]:.2f}" r="4"/>'
                   for t in ([i/(stops-1) for i in range(stops)] if stops>1 else [0]))
    plane = BRAND_PLANE.read_text(encoding='utf-8').replace(
        '<svg ', '<svg x="-17" y="-13" width="34" height="26" ', 1)
    # CSS transforms work inside Markdown's SVG renderer, which does not
    # reliably execute SMIL animateMotion. The transform attribute is the
    # exact current-node fallback even if animation styles are unavailable.
    name = 'route-flight-' + hashlib.sha256(f'{before}:{fraction}'.encode()).hexdigest()[:12]
    frames = []
    for frame in range(21):
        t = before + (fraction-before)*frame/20
        x,y = point(t)
        frames.append(f'{frame*5}%{{transform:translate({x:.2f}px,{y:.2f}px) rotate({angle(t):.2f}deg)}}')
    style = f'<style>@keyframes {name}{{{"".join(frames)}}}</style>'
    x,y = point(fraction)
    return (f'<svg class="paper-progress-route" viewBox="0 0 600 96" aria-hidden="true">{style}'
            f'<path class="route-line" d="{path}"/>{dots}'
            f'<g class="route-plane-static" transform="translate({x:.2f} {y:.2f}) rotate({angle(fraction):.2f})">{plane}</g>'
            f'<g class="route-plane-moving" transform="translate({x:.2f} {y:.2f}) rotate({angle(fraction):.2f})" '
            f'style="transform-origin:0 0;animation:{name} 700ms ease-in-out both">{plane}</g></svg>')
