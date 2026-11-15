"""Learning Radar spider chart and the one-click "I'm stuck here" buttons.

The chart is plain SVG markup built in Python: no JavaScript and no external
files, so any page can embed it. Colours are written as presentation
attributes (the paper palette) and the same elements carry classes that
``assets/paper_radar.css`` themes with the shared CSS variables.
"""

from __future__ import annotations

import html
import math
from collections.abc import MutableMapping, Sequence
from typing import Any, NamedTuple

import streamlit as st

from components.knowledge_graph import (
    RADAR_REASON_OPTIONS,
    forget_course_radar,
    load_course_radar,
    radar_count_text,
    radar_reason_label,
    render_saved_reason,
)
from models.schemas import StudyPackage
from services import learning_radar
from services.i18n import tr

# A radar chart needs at least three axes to enclose an area.
MIN_RADAR_TOPICS = 3
# Unflagged topics fill the chart up to this many axes so the shape reads well.
MIN_RADAR_AXES = 5
STUCK_FAILURE_MESSAGE = "Couldn't update Learning Radar. Try again in a moment."

# Paper palette; assets/paper_radar.css maps the same roles to CSS variables.
_INK_BODY = "#2A2F33"
_INK_MUTED = "#6B7280"
_RUST = "#B5622E"
_LINE = "#EEE7DF"
_BADGE = "#F0EADA"
_CARD = "#FFFCF7"
_FONT_FAMILY = "system-ui, sans-serif"

_FONT_SIZE = 12
_LINE_HEIGHT = 14
_BASELINE = 11  # first baseline below the top of a label block
_LABEL_GAP = 10  # space between the outer circle and a label
_MARGIN = 4  # space kept free at the edges of the drawing
_WRAP_WIDTH = 88  # labels estimated wider than this wrap onto two lines
_OVERFLOW_SLACK = 6  # a line may overrun its room by this much before "…"
_SIDE_THRESHOLD = 0.2  # |sin| below this: the label sits above or below
_MIN_RADIUS_SHARE = 0.22
_MAX_RADIUS_SHARE = 0.28
_PEAK_SHARE = 0.85  # the largest value reaches this share of the radius

# Rough Georgia advance widths at 12px, enough to wrap and place labels.
_NARROW = frozenset("fijlrtI.,:;'!|()[]-")
_WIDE = frozenset("mwMW")


class RadarAxis(NamedTuple):
    topic_id: str
    label: str
    value: int
    highlighted: bool


def _axis_value(topic_radar: learning_radar.TopicRadar | None) -> int:
    """The drawn count: a hidden count (privacy threshold) counts as 0."""
    if topic_radar is None:
        return 0
    count = topic_radar.display_count
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        return count
    return 0


def course_radar_axes(
    course: StudyPackage,
    radar: learning_radar.CourseRadar,
    *,
    focus_topic_id: str | None = None,
    limit: int = 6,
) -> list[RadarAxis]:
    """Choose the chart's axes and return them in course topic order.

    Priority: flagged topics with a visible count (highest first), then the
    focus topic, then other topics in course order until there are
    MIN_RADAR_AXES. At most ``limit`` axes are kept, and the focus topic
    always keeps a place so it can be highlighted. A limit below three is
    raised to three, the fewest axes a radar can show.
    """
    topics = list(course.topics)
    if len(topics) < MIN_RADAR_TOPICS:
        return []
    limit = max(limit, MIN_RADAR_TOPICS)
    values = {topic.id: _axis_value(radar.topics.get(topic.id)) for topic in topics}
    focus = focus_topic_id if focus_topic_id in values else None

    # sorted() is stable, so tied counts keep the course order.
    flagged = sorted(
        (topic_id for topic_id, value in values.items() if value > 0),
        key=lambda topic_id: -values[topic_id],
    )
    chosen = flagged[:limit]
    if focus is not None and focus not in chosen:
        chosen = [*chosen[: limit - 1], focus]
    fill_to = min(MIN_RADAR_AXES, limit)
    for topic in topics:
        if len(chosen) >= fill_to:
            break
        if topic.id not in chosen:
            chosen.append(topic.id)

    selected = set(chosen)
    return [
        RadarAxis(
            topic_id=topic.id,
            label=topic.name,
            value=values[topic.id],
            highlighted=topic.id == focus,
        )
        for topic in topics
        if topic.id in selected
    ]


def _char_width(char: str) -> float:
    if char == " ":
        return 3.0
    if char in _NARROW:
        return 3.8
    if char in _WIDE:
        return 9.5
    if ord(char) > 0x2E7F:  # CJK and other full-width text
        return 12.0
    if char.isupper():
        return 7.6
    if char.isdigit():
        return 6.6
    return 6.0


def _text_width(text: str, bold: bool = False) -> float:
    width = sum(_char_width(char) for char in text)
    return width * 1.1 if bold else width


def _wrap_label(label: str, bold: bool) -> list[str]:
    """One line when short, otherwise the most balanced split into two."""
    words = label.split()
    if not words:
        return [""]
    whole = " ".join(words)
    if len(words) == 1 or _text_width(whole, bold) <= _WRAP_WIDTH:
        return [whole]
    best: list[str] = [whole]
    best_width = math.inf
    for split in range(1, len(words)):
        lines = [" ".join(words[:split]), " ".join(words[split:])]
        widest = max(_text_width(line, bold) for line in lines)
        if widest < best_width:
            best, best_width = lines, widest
    return best


def _fits(line: str, room: float, bold: bool) -> bool:
    return _text_width(line, bold) <= room + _OVERFLOW_SLACK


def _fit_line(line: str, room: float, bold: bool) -> str:
    """Shorten a line with "…" when it would overrun its room."""
    if _fits(line, room, bold):
        return line
    for end in range(len(line) - 1, 0, -1):
        candidate = line[:end].rstrip() + "…"
        if _text_width(candidate, bold) <= room:
            return candidate
    return "…"


def _fit_label(lines: list[str], room: float, bold: bool) -> list[str]:
    """Keep the natural lines when they fit, else refill two lines and cut."""
    words = " ".join(lines).split()
    if not words or all(_fits(line, room, bold) for line in lines):
        return lines
    first = words[0]
    rest = 1
    while rest < len(words) and _fits(f"{first} {words[rest]}", room, bold):
        first = f"{first} {words[rest]}"
        rest += 1
    refilled = [first]
    if rest < len(words):
        refilled.append(" ".join(words[rest:]))
    return [_fit_line(line, room, bold) for line in refilled]


def _number(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def radar_chart_svg(axes: Sequence[RadarAxis], *, size: int = 320) -> str:
    """Return one ``<svg>`` element drawing the axes as a spider chart.

    ``size`` is the drawing width in pixels; the height follows from the
    labels. Axes start at the top and run clockwise. When every value is 0
    only the grid and the labels are drawn.
    """
    axes = list(axes)
    width = float(size)
    aria_label = html.escape(
        ", ".join(f"{axis.label}: {axis.value}" for axis in axes), quote=True
    )
    if not axes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" class="paper-radar-chart" '
            f'viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'role="img" aria-label="{aria_label}"></svg>'
        )

    count = len(axes)
    directions = [
        (math.sin(2 * math.pi * index / count), -math.cos(2 * math.pi * index / count))
        for index in range(count)
    ]
    natural_lines = [_wrap_label(axis.label, axis.highlighted) for axis in axes]

    # Shrink the circle (within limits) so the side labels fit across the
    # drawing width; labels that still do not fit are shortened below.
    radius = width * _MAX_RADIUS_SHARE
    for (dx, _), lines, axis in zip(directions, natural_lines, axes):
        if abs(dx) < _SIDE_THRESHOLD:
            continue
        needed = max(_text_width(line, axis.highlighted) for line in lines)
        radius = min(radius, (width / 2 - _MARGIN - needed) / abs(dx) - _LABEL_GAP)
    radius = max(radius, width * _MIN_RADIUS_SHARE)
    label_radius = radius + _LABEL_GAP

    # Lay out each label relative to the centre (y grows downwards).
    labels = []
    for (dx, dy), lines, axis in zip(directions, natural_lines, axes):
        x = width / 2 + dx * label_radius
        if abs(dx) < _SIDE_THRESHOLD:
            anchor, room = "middle", 2 * (min(x, width - x) - _MARGIN)
        elif dx > 0:
            anchor, room = "start", width - _MARGIN - x
        else:
            anchor, room = "end", x - _MARGIN
        lines = _fit_label(lines, room, axis.highlighted)
        block = len(lines) * _LINE_HEIGHT
        # Above the chart a label ends at its point, below it starts there.
        top = dy * label_radius + dy * block / 2 - block / 2
        labels.append((x, top, anchor, lines, axis))

    top_edge = min(-radius, *(top for _, top, _, _, _ in labels))
    bottom_edge = max(
        radius, *(top + len(lines) * _LINE_HEIGHT for _, top, _, lines, _ in labels)
    )
    height = math.ceil(bottom_edge - top_edge + 2 * _MARGIN)
    cx = width / 2
    cy = _MARGIN - top_edge

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" class="paper-radar-chart" '
        f'viewBox="0 0 {size} {height}" width="{size}" height="{height}" '
        f'role="img" aria-label="{aria_label}" '
        'style="max-width:100%;height:auto;overflow:visible">'
    ]

    # Grid: two soft discs and three thin rings, then one spoke per axis.
    for share in (1, 2 / 3):
        parts.append(
            f'<circle class="radar-disc" cx="{_number(cx)}" cy="{_number(cy)}" '
            f'r="{_number(radius * share)}" fill="{_BADGE}" fill-opacity="0.35"/>'
        )
    for share in (1 / 3, 2 / 3, 1):
        parts.append(
            f'<circle class="radar-grid" cx="{_number(cx)}" cy="{_number(cy)}" '
            f'r="{_number(radius * share)}" fill="none" stroke="{_LINE}" stroke-width="1"/>'
        )
    for dx, dy in directions:
        end_x, end_y = cx + dx * radius, cy + dy * radius
        parts.append(
            f'<line class="radar-spoke" x1="{_number(cx)}" y1="{_number(cy)}" '
            f'x2="{_number(end_x)}" y2="{_number(end_y)}" stroke="{_LINE}" stroke-width="1"/>'
        )
        parts.append(
            f'<circle class="radar-tick" cx="{_number(end_x)}" cy="{_number(end_y)}" '
            f'r="2" fill="{_INK_MUTED}" fill-opacity="0.45"/>'
        )

    peak = max(axis.value for axis in axes)
    if peak > 0:
        vertices = [
            (
                cx + dx * radius * _PEAK_SHARE * axis.value / peak,
                cy + dy * radius * _PEAK_SHARE * axis.value / peak,
            )
            for (dx, dy), axis in zip(directions, axes)
        ]
        points = " ".join(f"{_number(x)},{_number(y)}" for x, y in vertices)
        parts.append(
            f'<polygon class="radar-shape" points="{points}" fill="{_RUST}" '
            f'fill-opacity="0.18" stroke="{_RUST}" stroke-width="1.5" '
            'stroke-linejoin="round"/>'
        )
        focus_marks = []
        for (x, y), axis in zip(vertices, axes):
            if axis.highlighted:
                # Drawn last so the larger dot and its ring sit on top.
                focus_marks.append(
                    f'<circle class="radar-ring" cx="{_number(x)}" cy="{_number(y)}" '
                    f'r="8.5" fill="{_RUST}" fill-opacity="0.16" stroke="{_RUST}" '
                    'stroke-opacity="0.55" stroke-width="1"/>'
                )
                focus_marks.append(
                    f'<circle class="radar-point radar-point-focus" cx="{_number(x)}" '
                    f'cy="{_number(y)}" r="5.5" fill="{_RUST}" stroke="{_CARD}" '
                    'stroke-width="1.5"/>'
                )
            else:
                parts.append(
                    f'<circle class="radar-point" cx="{_number(x)}" cy="{_number(y)}" '
                    f'r="3" fill="{_RUST}"/>'
                )
        parts.extend(focus_marks)

    for x, top, anchor, lines, axis in labels:
        weight = ' font-weight="700"' if axis.highlighted else ""
        css_class = "radar-label radar-label-focus" if axis.highlighted else "radar-label"
        spans = "".join(
            f'<tspan x="{_number(x)}" y="{_number(cy + top + _BASELINE + row * _LINE_HEIGHT)}">'
            f"{html.escape(line, quote=False)}</tspan>"
            for row, line in enumerate(lines)
        )
        parts.append(
            f'<text class="{css_class}" text-anchor="{anchor}" '
            f'font-family="{_FONT_FAMILY}" font-size="{_FONT_SIZE}" fill="{_INK_BODY}"{weight}>'
            f"<title>{html.escape(axis.label, quote=False)}</title>{spans}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def _render_svg(axes: Sequence[RadarAxis], size: int = 320) -> None:
    # The wrapping <div> keeps the markup one raw HTML block for Markdown.
    st.markdown(
        f'<div class="paper-radar">\n{radar_chart_svg(axes, size=size)}\n</div>',
        unsafe_allow_html=True,
    )


def render_radar_figure(
    course: StudyPackage,
    radar: learning_radar.CourseRadar,
    *,
    focus_topic_id: str | None = None,
    limit: int = 6,
    key: str,
) -> None:
    """Draw the chart and its axis caption only, for panels that print their
    own "No topics have been flagged yet." and sample-data notes."""
    axes = course_radar_axes(
        course, radar, focus_topic_id=focus_topic_id, limit=limit
    )
    with st.container(key=key):
        if axes:
            _render_svg(axes)
            st.caption(tr("Students stuck per topic"))


def render_course_radar_chart(
    course: StudyPackage,
    radar: learning_radar.CourseRadar,
    *,
    focus_topic_id: str | None = None,
    limit: int = 6,
    size: int = 320,
    key: str,
) -> None:
    """Draw the course's Learning Radar chart with its captions."""
    axes = course_radar_axes(
        course, radar, focus_topic_id=focus_topic_id, limit=limit
    )
    with st.container(key=key):
        if not axes:
            return
        _render_svg(axes, size)
        st.caption(tr("Students stuck per topic"))
        if not any(axis.value > 0 for axis in axes):
            st.caption(tr("No topics have been flagged yet."))
        if radar.has_sample:
            st.caption(tr("Includes sample data"))


def _finish_write(
    session_state: MutableMapping[str, Any],
    course_id: str,
    result: Any,
) -> None:
    """Refresh the counts after a saved change; otherwise show a short notice.

    The stored failure reason may describe the database, so it is not shown.
    """
    if result.success:
        # Show the new count right away instead of waiting for the cache.
        forget_course_radar(session_state, course_id)
        st.rerun()
    st.warning(tr(STUCK_FAILURE_MESSAGE))


def render_stuck_buttons(
    session_state: MutableMapping[str, Any],
    course_id: str,
    topic_id: str,
    user_id: str | None,
    *,
    key: str,
) -> None:
    """Show the topic's count and one-click buttons to flag or unflag it.

    Without a signed-in user only the count is shown.
    """
    radar, user_flags = load_course_radar(session_state, course_id, user_id)
    st.markdown(tr(radar_count_text(radar.topics.get(topic_id))))
    if user_id is None:
        return

    if topic_id in user_flags:
        st.markdown(tr("You marked this topic."))
        render_saved_reason(user_flags[topic_id])
        if st.button(tr("Not stuck anymore"), key=f"{key}_clear"):
            _finish_write(
                session_state,
                course_id,
                learning_radar.clear_flag(user_id, course_id, topic_id),
            )
        return

    st.caption(tr("I'm stuck here because…"))
    chosen: tuple[str | None] | None = None
    with st.container(horizontal=True, gap="small", key=f"{key}_stuck_reasons"):
        for reason in RADAR_REASON_OPTIONS:
            if st.button(
                tr(radar_reason_label(reason)),
                key=f"{key}_{reason if reason is not None else 'no_reason'}",
            ):
                chosen = (reason,)
    if chosen is not None:
        _finish_write(
            session_state,
            course_id,
            learning_radar.set_flag(user_id, course_id, topic_id, chosen[0]),
        )
