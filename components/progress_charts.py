"""Progress page charts as plain HTML and SVG built in Python.

No JavaScript, no chart library and no external files. Every builder returns
one markup string whose outer element has role="img" and an aria-label that
states the chart's content in words; course text is always escaped.
``assets/paper_progress.css`` styles the classes with the paper tokens, and
the SVG also carries its colours as attributes so it still reads without it.

The builders take a ``tr`` function for interface words (identity by
default), so they never touch Streamlit. The ``render_*`` wrappers pass the
app's translator and draw the markup.
"""

from __future__ import annotations

import html
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, NamedTuple

from services.learning_dna import DIMENSIONS, MIN_EVIDENCE, DimensionEvidence
from services.mastery_engine import get_mastery_status

Translate = Callable[[str], str]

STATUS_LABELS = {
    "unattempted": "Unattempted",
    "insufficient_evidence": "Insufficient evidence",
    "weak": "Weak",
    "developing": "Developing",
    "mastered": "Mastered",
}
# Bar looks: solid, tinted with an outline, striped, and an empty dashed track.
# They differ in fill pattern as well as hue, and a text chip names the status.
STATUS_STYLES = {
    "unattempted": "empty",
    "insufficient_evidence": "empty",
    "weak": "weak",
    "developing": "developing",
    "mastered": "mastered",
}
DNA_STYLES = {
    "Consistent answers": "mastered",
    "Mixed answers": "developing",
    "Needs review": "weak",
}
STYLES = ("mastered", "developing", "weak", "empty", "plain")
NOT_ENOUGH = "Not enough answers yet"

# Session chart drawing, in SVG user units.
_WIDTH = 400
_HEIGHT = 190
_LEFT, _RIGHT, _TOP, _BOTTOM = 42, 14, 26, 30
_INSET = 16  # the first and last points sit this far inside the frame
_MAX_POINT_LABELS = 10  # more sessions than this: values are listed below the chart
_FONT = "Georgia, 'Times New Roman', serif"
# Paper palette; assets/paper_progress.css maps the same roles to CSS variables.
_INK_MUTED = "#6B7280"
_BLUE_FILL = "#557A99"
_RUST_TEXT = "#9A5426"
_CARD = "#FFFCF7"


class BarRow(NamedTuple):
    """One labelled bar: ``fill`` is 0–100, or None for an empty track."""

    label: str
    fill: float | None
    style: str
    chip: str | None
    value: str
    detail: str = ""


class SessionPoint(NamedTuple):
    number: int  # 1 is the oldest session
    accuracy: float


def _same(text: str) -> str:
    return text


def _escape(text: Any) -> str:
    return html.escape(str(text), quote=True)


def percent_text(value: float) -> str:
    return f"{value:.0f}%"


def questions_text(count: int, tr: Translate = _same) -> str:
    return tr(f"{count} different question" if count == 1 else f"{count} different questions")


def answers_text(count: int, tr: Translate = _same) -> str:
    return tr(f"{count} answer" if count == 1 else f"{count} answers")


def duration_text(seconds: float, tr: Translate = _same) -> str:
    whole = int(round(seconds))
    if whole < 60:
        return tr(f"{whole} s")
    minutes, rest = divmod(whole, 60)
    return tr(f"{minutes} min {rest} s")


# ---- Rows from the existing calculations -------------------------------------


def mastery_rows(topics: Iterable[Any], stats_by_topic: Mapping[str, Any], tr: Translate = _same) -> list[BarRow]:
    """One bar per topic, in course order, from calculate_topic_stats for one mode.

    Bar length is the latest-answer accuracy; unattempted and
    insufficient-evidence topics get an empty track with their count.
    """
    rows = []
    for topic in topics:
        stats = stats_by_topic.get(topic.id)
        status = "unattempted" if stats is None else get_mastery_status(stats)
        attempted = 0 if stats is None else stats.attempted
        different = (
            attempted if stats is None or stats.unique_attempted is None else stats.unique_attempted
        )
        style = STATUS_STYLES[status]
        chip = tr(STATUS_LABELS[status])
        if style == "empty":
            if attempted:
                rows.append(BarRow(topic.name, None, style, chip, questions_text(different, tr),
                                   answers_text(attempted, tr)))
            else:
                rows.append(BarRow(topic.name, None, style, chip, answers_text(0, tr)))
            continue
        accuracy = stats.evidence_accuracy if stats.unique_attempted is not None else stats.accuracy
        rows.append(BarRow(
            topic.name, accuracy, style, chip, percent_text(accuracy),
            f"{questions_text(different, tr)} · {answers_text(attempted, tr)}",
        ))
    return rows


def dna_rows(by_dimension: Mapping[str, DimensionEvidence | None], tr: Translate = _same) -> list[BarRow]:
    """Computation and conceptual understanding for one topic, from evidence_profile."""
    rows = []
    for dimension, label in DIMENSIONS.items():
        item = by_dimension.get(dimension)
        count = 0 if item is None else item.count
        if item is not None and count >= MIN_EVIDENCE:
            rows.append(BarRow(tr(label), item.accuracy, DNA_STYLES[item.status], tr(item.status),
                               percent_text(item.accuracy), questions_text(count, tr)))
        else:
            rows.append(BarRow(tr(label), None, "empty", None, tr(NOT_ENOUGH), questions_text(count, tr)))
    return rows


def time_rows(total_seconds: Mapping[str, float], names: Mapping[str, str], fallback: str,
              tr: Translate = _same) -> list[BarRow]:
    """Tracked time per topic, longest first; the longest fills the track."""
    ordered = sorted(total_seconds.items(), key=lambda pair: -pair[1])
    peak = max((seconds for _, seconds in ordered), default=0)
    return [
        BarRow(names.get(topic_id, fallback), 100 * seconds / peak if peak > 0 else 0.0, "plain", None,
               duration_text(seconds, tr))
        for topic_id, seconds in ordered
    ]


def session_points(records: Iterable[Mapping[str, Any]]) -> list[SessionPoint]:
    """Accuracy of each graded session, oldest first; records come in that order."""
    points = []
    for record in records:
        attempts = record["attempts"]
        if attempts:
            accuracy = 100 * sum(attempt.is_correct for attempt in attempts) / len(attempts)
            points.append(SessionPoint(len(points) + 1, accuracy))
    return points


# ---- Markup -------------------------------------------------------------------


def _row_words(row: BarRow) -> str:
    return ", ".join(part for part in (row.label, row.chip, row.value, row.detail) if part)


def _row_markup(row: BarRow) -> str:
    style = row.style if row.style in STYLES else "plain"
    chip = f'<span class="progress-chip is-{style}">{_escape(row.chip)}</span>' if row.chip else ""
    detail = f' <span class="progress-bar-detail">· {_escape(row.detail)}</span>' if row.detail else ""
    if row.fill is None:
        track = '<div class="progress-track is-empty"></div>'
    else:
        width = min(100.0, max(0.0, float(row.fill)))
        track = (
            f'<div class="progress-track"><span class="progress-fill is-{style}" '
            f'style="width:{width:.1f}%"></span></div>'
        )
    return (
        f'<div class="progress-bar-row is-{style}"><div class="progress-bar-head">'
        f'<span class="progress-bar-label">{_escape(row.label)}</span>{chip}'
        f'<span class="progress-bar-value"><strong>{_escape(row.value)}</strong>{detail}</span>'
        f"</div>{track}</div>"
    )


def bar_chart_html(title: str, rows: Sequence[BarRow], *, kind: str, heading: str | None = None,
                   empty_text: str = "", tr: Translate = _same) -> str:
    """Horizontal bars, one row each: label, status chip, value and detail, then the track.

    ``title`` names the chart for screen readers; ``heading`` (course text,
    such as a topic name) is also drawn above the rows.
    """
    words = [_row_words(row) for row in rows] or ([tr(empty_text)] if empty_text else [])
    label = f"{heading}: " if heading else ""
    aria = f"{title}: {label}" + "; ".join(words)
    parts = [f'<div class="progress-chart progress-bars progress-{_escape(kind)}" role="img" '
             f'aria-label="{_escape(aria)}">']
    if heading:
        parts.append(f'<p class="progress-chart-heading">{_escape(heading)}</p>')
    if rows:
        parts.extend(_row_markup(row) for row in rows)
    elif empty_text:
        parts.append(f'<p class="progress-chart-empty">{_escape(tr(empty_text))}</p>')
    parts.append("</div>")
    return "".join(parts)


def _number(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def session_chart_html(points: Sequence[SessionPoint], *, title: str, empty_text: str,
                       tr: Translate = _same) -> str:
    """Accuracy per graded session as a line with dots on a 0–100% scale.

    Each dot carries its value (listed under the chart when there are many
    sessions) and the latest value is written out. With no sessions only the
    frame and one line of text are drawn.
    """
    points = list(points)
    plot_width = _WIDTH - _LEFT - _RIGHT
    plot_height = _HEIGHT - _TOP - _BOTTOM

    def y_of(value: float) -> float:
        return _TOP + plot_height * (1 - min(100.0, max(0.0, value)) / 100)

    if points:
        words = "; ".join(tr(f"Session {p.number}: {percent_text(p.accuracy)}") for p in points)
        latest = tr(f"Latest session: {percent_text(points[-1].accuracy)}")
        aria = f"{title}: {words}. {latest}"
    else:
        latest = ""
        aria = f"{title}: {tr(empty_text)}"

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="progress-sessions-svg" '
        f'viewBox="0 0 {_WIDTH} {_HEIGHT}" width="{_WIDTH}" height="{_HEIGHT}" '
        'style="max-width:100%;height:auto" aria-hidden="true" focusable="false">'
    ]
    for value in (0, 50, 100):
        y = _number(y_of(value))
        css = "ps-axis" if value == 0 else "ps-grid"
        opacity = "0.55" if value == 0 else "0.25"
        svg.append(
            f'<line class="{css}" x1="{_LEFT}" y1="{y}" x2="{_WIDTH - _RIGHT}" y2="{y}" '
            f'stroke="{_INK_MUTED}" stroke-opacity="{opacity}" stroke-width="1"/>'
        )
        svg.append(
            f'<text class="ps-tick" x="{_LEFT - 8}" y="{_number(y_of(value) + 4)}" text-anchor="end" '
            f'font-family="{_FONT}" font-size="11" fill="{_INK_MUTED}">{value}%</text>'
        )

    if not points:
        svg.append(
            f'<text class="ps-empty" x="{_number(_LEFT + plot_width / 2)}" '
            f'y="{_number(_TOP + plot_height / 2)}" text-anchor="middle" font-family="{_FONT}" '
            f'font-size="12" fill="{_INK_MUTED}">{_escape(tr(empty_text))}</text>'
        )
    else:
        inner = plot_width - 2 * _INSET
        count = len(points)
        xs = [
            _LEFT + _INSET + (inner * index / (count - 1) if count > 1 else inner / 2)
            for index in range(count)
        ]
        ys = [y_of(point.accuracy) for point in points]
        if count > 1:
            path = " ".join(f"{_number(x)},{_number(y)}" for x, y in zip(xs, ys))
            svg.append(
                f'<polyline class="ps-line" points="{path}" fill="none" stroke="{_BLUE_FILL}" '
                'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        step = 1 if count <= _MAX_POINT_LABELS else math.ceil(count / _MAX_POINT_LABELS)
        for index, (x, y, point) in enumerate(zip(xs, ys, points)):
            last = index == count - 1
            if last:
                svg.append(
                    f'<circle class="ps-dot ps-dot-latest" cx="{_number(x)}" cy="{_number(y)}" r="6" '
                    f'fill="{_RUST_TEXT}" stroke="{_CARD}" stroke-width="1.5"/>'
                )
            else:
                svg.append(
                    f'<circle class="ps-dot" cx="{_number(x)}" cy="{_number(y)}" r="4" '
                    f'fill="{_BLUE_FILL}" stroke="{_CARD}" stroke-width="1.5"/>'
                )
            if count <= _MAX_POINT_LABELS or last:
                weight = ' font-weight="700"' if last else ""
                css = "ps-value ps-value-latest" if last else "ps-value"
                svg.append(
                    f'<text class="{css}" x="{_number(x)}" y="{_number(y - 10)}" text-anchor="middle" '
                    f'font-family="{_FONT}" font-size="11" fill="{_RUST_TEXT if last else _INK_MUTED}"'
                    f"{weight}>{percent_text(point.accuracy)}</text>"
                )
            if index % step == 0 or last:
                svg.append(
                    f'<text class="ps-tick" x="{_number(x)}" y="{_HEIGHT - _BOTTOM + 18}" '
                    f'text-anchor="middle" font-family="{_FONT}" font-size="11" '
                    f'fill="{_INK_MUTED}">{point.number}</text>'
                )
    svg.append("</svg>")

    parts = [f'<div class="progress-chart progress-sessions" role="img" aria-label="{_escape(aria)}">',
             "".join(svg)]
    if points:
        parts.append(f'<p class="progress-chart-note">{_escape(latest)}</p>')
    if len(points) > _MAX_POINT_LABELS:
        parts.append(
            '<ol class="progress-session-values">'
            + "".join(f"<li>{point.number} · {percent_text(point.accuracy)}</li>" for point in points)
            + "</ol>"
        )
    parts.append("</div>")
    return "".join(parts)


def example_banner_html(tr: Translate = _same) -> str:
    return (
        '<div class="progress-example-banner" role="note">'
        f'<strong>{_escape(tr("Example report"))}</strong> · '
        f'{_escape(tr("These numbers are sample data. Finish a practice session to see your own."))}'
        "</div>"
    )


# ---- Streamlit wrappers -------------------------------------------------------


def _draw(markup: str) -> None:
    import streamlit as st

    st.markdown(markup, unsafe_allow_html=True)


def _translator() -> Translate:
    from services.i18n import tr

    return tr


def render_bar_chart(title: str, rows: Sequence[BarRow], *, kind: str, heading: str | None = None,
                     empty_text: str = "") -> None:
    _draw(bar_chart_html(title, rows, kind=kind, heading=heading, empty_text=empty_text, tr=_translator()))


def render_session_chart(points: Sequence[SessionPoint], *, title: str, empty_text: str) -> None:
    _draw(session_chart_html(points, title=title, empty_text=empty_text, tr=_translator()))


def render_example_banner() -> None:
    _draw(example_banner_html(_translator()))
