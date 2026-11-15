"""Learning Radar spider chart: axis choice, SVG output and the stuck buttons."""

import math
import re

import pytest
from streamlit.testing.v1 import AppTest

from components import radar_chart
from components.radar_chart import RadarAxis, course_radar_axes, radar_chart_svg
from models.schemas import StudyPackage
from services import learning_radar
from services.postgres_store import PersistenceResult
from tests.auth_helpers import TEST_USER
from tests.test_knowledge_graph import (
    CALCULUS_ID,
    GENERIC_FAILURE,
    REASON_BUTTON_LABELS,
    RadarFake,
    ReasonRadarFake,
    _calculus_course,
    _topic,
)

CACHE_KEY = f"learning_radar_cache_{CALCULUS_ID}"


def _course(count, course_id="course-x"):
    return StudyPackage(
        course_id=course_id,
        course_name="Course",
        topics=[
            {"id": f"t{index}", "name": f"Topic {index}", "summary": "Summary."}
            for index in range(1, count + 1)
        ],
        relationships=[],
        questions=[],
    )


def _radar(*topics, has_sample=False, live=True):
    return learning_radar.CourseRadar(
        topics={topic.topic_id: topic for topic in topics},
        live=live,
        has_sample=has_sample,
    )


def _ids(axes):
    return [axis.topic_id for axis in axes]


# --- Axis choice -------------------------------------------------------------


def test_axes_keep_course_order_and_fill_to_five():
    axes = course_radar_axes(
        _course(8), _radar(_topic("t6", real=3), _topic("t2", real=7))
    )

    assert axes == [
        RadarAxis("t1", "Topic 1", 0, False),
        RadarAxis("t2", "Topic 2", 7, False),
        RadarAxis("t3", "Topic 3", 0, False),
        RadarAxis("t4", "Topic 4", 0, False),
        RadarAxis("t6", "Topic 6", 3, False),
    ]


def test_axes_take_the_most_flagged_topics_up_to_the_limit():
    radar = _radar(*(_topic(f"t{index}", real=index) for index in range(1, 9)))

    assert _ids(course_radar_axes(_course(10), radar)) == [
        "t3", "t4", "t5", "t6", "t7", "t8",
    ]
    assert _ids(course_radar_axes(_course(10), radar, limit=8)) == [
        f"t{index}" for index in range(1, 9)
    ]


def test_tied_counts_keep_course_order():
    radar = _radar(*(_topic(f"t{index}", real=2) for index in range(1, 6)))

    assert _ids(course_radar_axes(_course(5), radar, limit=3)) == ["t1", "t2", "t3"]


def test_focus_topic_is_added_and_highlighted():
    axes = course_radar_axes(
        _course(8), _radar(_topic("t2", real=7)), focus_topic_id="t8"
    )

    assert _ids(axes) == ["t1", "t2", "t3", "t4", "t8"]
    assert [axis.topic_id for axis in axes if axis.highlighted] == ["t8"]
    assert axes[-1].value == 0


def test_focus_topic_keeps_a_place_when_many_topics_are_flagged():
    radar = _radar(*(_topic(f"t{index}", real=index) for index in range(1, 9)))

    axes = course_radar_axes(_course(10), radar, focus_topic_id="t10", limit=6)

    assert _ids(axes) == ["t4", "t5", "t6", "t7", "t8", "t10"]
    assert [axis.highlighted for axis in axes] == [False] * 5 + [True]


def test_flagged_focus_topic_is_highlighted_in_place():
    axes = course_radar_axes(
        _course(6), _radar(_topic("t3", real=4)), focus_topic_id="t3"
    )

    assert _ids(axes) == ["t1", "t2", "t3", "t4", "t5"]
    assert [axis.topic_id for axis in axes if axis.highlighted] == ["t3"]


@pytest.mark.parametrize("focus", [None, "not-a-topic"])
def test_no_highlight_without_a_known_focus(focus):
    axes = course_radar_axes(_course(6), _radar(), focus_topic_id=focus)

    assert not any(axis.highlighted for axis in axes)
    assert _ids(axes) == ["t1", "t2", "t3", "t4", "t5"]


def test_limit_caps_the_fill():
    assert _ids(course_radar_axes(_course(8), _radar(), limit=4)) == [
        "t1", "t2", "t3", "t4",
    ]


@pytest.mark.parametrize(("count", "expected"), [(1, 0), (2, 0), (3, 3), (4, 4)])
def test_small_courses(count, expected):
    axes = course_radar_axes(_course(count), _radar(_topic("t1", real=5)))

    assert len(axes) == expected


def test_hidden_count_is_drawn_as_zero_and_not_ranked():
    radar = _radar(
        *(_topic(f"t{index}", real=4) for index in range(1, 7)),
        _topic("t8", real=2, display=None),
    )

    axes = course_radar_axes(_course(8), radar, limit=7)

    assert _ids(axes) == ["t1", "t2", "t3", "t4", "t5", "t6"]
    hidden = course_radar_axes(_course(8), radar, focus_topic_id="t8", limit=7)
    assert hidden[-1] == RadarAxis("t8", "Topic 8", 0, True)


# --- SVG --------------------------------------------------------------------


def _axes(*values, highlight=None, labels=None):
    labels = labels or [f"Topic {index}" for index in range(1, len(values) + 1)]
    return [
        RadarAxis(f"t{index}", label, value, index == highlight)
        for index, (label, value) in enumerate(zip(labels, values), start=1)
    ]


def _count(svg, element_class):
    return len(re.findall(rf'<\w+ class="{element_class}[ "]', svg))


def _polygon_points(svg):
    (points,) = re.findall(r'<polygon class="radar-shape" points="([^"]+)"', svg)
    return [tuple(map(float, pair.split(","))) for pair in points.split()]


def test_svg_is_one_accessible_element_without_scripts_or_external_files():
    svg = radar_chart_svg(_axes(3, 0, 5))

    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    assert svg.count("<svg") == 1
    assert 'role="img"' in svg
    assert 'aria-label="Topic 1: 3, Topic 2: 0, Topic 3: 5"' in svg
    assert "<script" not in svg and "href" not in svg and "url(" not in svg
    assert svg.count("http") == 1  # only the SVG namespace


@pytest.mark.parametrize("count", [3, 5, 8])
def test_svg_draws_grid_spokes_vertices_and_labels_per_axis(count):
    svg = radar_chart_svg(_axes(*range(1, count + 1)))

    assert _count(svg, "radar-grid") == 3
    assert _count(svg, "radar-spoke") == count
    assert _count(svg, "radar-point") == count
    assert len(_polygon_points(svg)) == count
    assert svg.count("<text ") == count
    assert 'stroke-width="1.5"' in svg and 'fill-opacity="0.18"' in svg


def test_svg_highlights_one_axis_with_a_larger_dot_ring_and_bold_label():
    svg = radar_chart_svg(_axes(4, 2, 6, 1, 3, highlight=3))

    assert _count(svg, "radar-point") == 5
    assert _count(svg, "radar-point radar-point-focus") == 1
    assert _count(svg, "radar-ring") == 1
    assert re.findall(
        r'<text class="radar-label radar-label-focus"[^>]*font-weight="700"><title>([^<]*)</title>',
        svg,
    ) == ["Topic 3"]
    assert svg.count('font-weight="700"') == 1


def test_svg_scales_the_largest_value_to_85_percent_of_the_radius():
    svg = radar_chart_svg(_axes(2, 8, 4, 0, 6))

    outer = max(float(r) for r in re.findall(r'class="radar-grid"[^>]* r="([^"]+)"', svg))
    cx, cy = map(
        float, re.search(r'class="radar-grid" cx="([^"]+)" cy="([^"]+)"', svg).groups()
    )
    distances = [math.dist((cx, cy), point) for point in _polygon_points(svg)]
    assert distances[1] == pytest.approx(0.85 * outer, abs=0.15)
    assert distances[3] == pytest.approx(0, abs=0.15)
    assert distances[0] == pytest.approx(0.85 * outer * 2 / 8, abs=0.15)


def test_all_zero_values_draw_only_grid_and_labels():
    svg = radar_chart_svg(_axes(0, 0, 0, 0, 0, highlight=2))

    assert "radar-shape" not in svg
    assert "radar-point" not in svg
    assert "radar-ring" not in svg
    assert _count(svg, "radar-grid") == 3
    assert _count(svg, "radar-spoke") == 5
    assert svg.count("<text ") == 5


def test_svg_escapes_labels():
    label = '<script>alert("x")</script> & Co'
    svg = radar_chart_svg(_axes(1, 2, 3, labels=[label, "B", "C"]))

    assert "<script" not in svg
    assert "&lt;script&gt;" in svg
    assert 'aria-label="&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; Co: 1, B: 2, C: 3"' in svg


def test_long_labels_wrap_onto_two_lines_and_keep_the_full_name_as_title():
    svg = radar_chart_svg(
        _axes(1, 2, 3, labels=["Limits", "Applications of Derivatives", "Derivatives"])
    )

    texts = re.findall(r"<text [^>]*>(.*?)</text>", svg)
    lines = [re.findall(r"<tspan [^>]*>([^<]*)</tspan>", text) for text in texts]
    assert lines == [["Limits"], ["Applications", "of Derivatives"], ["Derivatives"]]
    assert "<title>Applications of Derivatives</title>" in svg


def test_very_long_label_is_shortened_on_two_lines():
    name = "Fundamental Theorem of Calculus and Its Many Applications"
    svg = radar_chart_svg(_axes(1, 2, 3, 4, 5, labels=["A", name, "B", "C", "D"]))

    (text,) = [text for text in re.findall(r"<text [^>]*>(.*?)</text>", svg) if name in text]
    spans = re.findall(r"<tspan [^>]*>([^<]*)</tspan>", text)
    assert len(spans) == 2
    assert spans[-1].endswith("…")


def test_empty_axes_give_an_empty_svg():
    svg = radar_chart_svg([])

    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    assert "<circle" not in svg and "<text" not in svg


# --- render_course_radar_chart -------------------------------------------------


def _chart_script(course, radar, focus):
    from components.radar_chart import render_course_radar_chart

    render_course_radar_chart(course, radar, focus_topic_id=focus, key="test_chart")


def _chart_app(course, radar, focus=None):
    return AppTest.from_function(_chart_script, args=(course, radar, focus)).run()


def _markdown(app):
    return [item.value for item in app.markdown]


def _captions(app):
    return [item.value for item in app.caption]


@pytest.mark.parametrize("has_sample", [True, False])
def test_chart_renders_svg_and_captions(has_sample):
    app = _chart_app(
        _calculus_course(),
        _radar(_topic("calc_derivatives", sample=8), has_sample=has_sample, live=False),
        focus="calc_limits",
    )

    assert not app.exception
    (svg,) = [value for value in _markdown(app) if "<svg" in value]
    assert 'class="paper-radar"' in svg
    assert "<title>Limits</title>" in svg and "radar-label-focus" in svg
    captions = _captions(app)
    assert captions[0] == "Students stuck per topic"
    assert captions.count("Includes sample data") == (1 if has_sample else 0)
    assert "No topics have been flagged yet." not in captions
    # No database or offline notice, even when live flags could not be read.
    assert not any("Live flags" in value or "database" in value for value in captions)


def test_chart_without_flags_shows_the_empty_grid_and_a_note():
    app = _chart_app(_calculus_course(), _radar())

    assert not app.exception
    (svg,) = [value for value in _markdown(app) if "<svg" in value]
    assert "radar-shape" not in svg
    assert _captions(app) == ["Students stuck per topic", "No topics have been flagged yet."]


def test_chart_draws_nothing_for_a_course_with_too_few_topics():
    app = _chart_app(_course(2), _radar(_topic("t1", real=5)))

    assert not app.exception
    assert _markdown(app) == []
    assert _captions(app) == []


# --- render_stuck_buttons ------------------------------------------------------


def _stuck_script(user_id):
    import streamlit as st

    from components.radar_chart import render_stuck_buttons

    render_stuck_buttons(
        st.session_state, "calculus-i-demo", "calc_derivatives", user_id, key="stuck"
    )


def _stuck_app(user_id=TEST_USER.user_id):
    return AppTest.from_function(_stuck_script, args=(user_id,)).run()


@pytest.fixture
def forgotten(monkeypatch):
    calls = []
    real = radar_chart.forget_course_radar

    def record(session_state, course_id):
        calls.append(course_id)
        real(session_state, course_id)

    monkeypatch.setattr(radar_chart, "forget_course_radar", record)
    return calls


def _button_keys(app):
    return [button.key for button in app.button]


def test_unflagged_topic_offers_one_button_per_reason_and_just_stuck(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _stuck_app()

    assert not app.exception
    assert "4 students are stuck here" in _markdown(app)
    assert "I'm stuck here because…" in _captions(app)
    assert [button.label for button in app.button] == REASON_BUTTON_LABELS
    assert _button_keys(app) == [
        "stuck_concept", "stuck_calculation", "stuck_wording", "stuck_start",
        "stuck_no_reason",
    ]


@pytest.mark.parametrize(
    ("suffix", "reason"),
    [
        ("concept", "concept"),
        ("calculation", "calculation"),
        ("wording", "wording"),
        ("start", "start"),
        ("no_reason", None),
    ],
)
def test_each_button_flags_with_its_reason_and_clears_the_cache(
    monkeypatch, forgotten, suffix, reason
):
    radar = ReasonRadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])
    app = _stuck_app()

    app.button(key=f"stuck_{suffix}").click().run()

    assert not app.exception
    assert radar.flag_reasons == [reason]
    assert radar.calls["set_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert forgotten == [CALCULUS_ID]
    assert len(radar.calls["get_course_radar"]) == 2
    assert "5 students are stuck here" in _markdown(app)
    assert "You marked this topic." in _markdown(app)
    assert _button_keys(app) == ["stuck_clear"]
    assert app.warning == []


def test_not_stuck_anymore_clears_the_flag(monkeypatch, forgotten):
    radar = RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        user_flags={"calc_derivatives": "concept"},
    )
    app = _stuck_app()

    assert "You marked this topic." in _markdown(app)
    assert "Your reason: Concept unclear" in _captions(app)
    button = app.button(key="stuck_clear")
    assert button.label == "Not stuck anymore"

    button.click().run()

    assert not app.exception
    assert radar.calls["clear_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert radar.calls["set_flag"] == []
    assert forgotten == [CALCULUS_ID]
    assert "3 students are stuck here" in _markdown(app)
    # AppTest keeps the first run's trailing element after st.rerun(); a
    # plain run shows the tree a browser would show.
    app.run()
    assert [button.label for button in app.button] == REASON_BUTTON_LABELS
    assert "You marked this topic." not in _markdown(app)


@pytest.mark.parametrize("flagged", [False, True])
def test_failed_write_shows_the_generic_warning(monkeypatch, forgotten, flagged):
    raw = "connection to server at db.internal failed: password authentication failed"
    radar = RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        user_flags={"calc_derivatives": None} if flagged else None,
        write_result=PersistenceResult(success=False, message=raw),
    )
    app = _stuck_app()

    app.button(key="stuck_clear" if flagged else "stuck_wording").click().run()

    assert not app.exception
    assert [item.value for item in app.warning] == [GENERIC_FAILURE]
    shown = _markdown(app) + _captions(app) + [item.value for item in app.warning]
    assert not any(raw in value or "db.internal" in value for value in shown)
    assert forgotten == []
    assert len(radar.calls["get_course_radar"]) == 1
    assert "4 students are stuck here" in _markdown(app)


def test_without_a_user_only_the_count_is_shown(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _stuck_app(user_id=None)

    assert not app.exception
    assert _markdown(app) == ["4 students are stuck here"]
    assert len(app.button) == 0
    assert radar.calls["get_user_flags"] == []


def test_stuck_buttons_reuse_the_shared_radar_cache(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _stuck_app()
    app.run()

    assert not app.exception
    assert CACHE_KEY in app.session_state
    assert len(radar.calls["get_course_radar"]) == 1
    assert len(radar.calls["get_user_flags"]) == 1
