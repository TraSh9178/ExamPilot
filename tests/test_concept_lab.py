"""Tests for the Concept Lab mathematics and interactive page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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

PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "6_Concept_Lab.py"


def test_limits_page_loads_without_a_selected_course():
    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = None
    app.run()

    assert not app.exception
    assert "Concept Lab" in [title.value for title in app.title]
    # Step 1 comes first; the explanation waits for step 3 and "Show answer".
    assert not any("Both sides approach 4" in item.value for item in app.markdown)
    assert not app.expander


def load_course(filename="calculus_i_demo.json"):
    from models.schemas import StudyPackage

    return StudyPackage.model_validate_json(
        (PAGE_PATH.parents[1] / "data" / filename).read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("filename", ["calculus_i_demo.json", "sample_course.json"])
def test_page_loads_with_selected_course(filename):
    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = load_course(filename)
    app.run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Limits", "Derivatives", "Corners & differentiability"]


def test_limits_slider_updates_both_sides_and_keeps_hole():
    import json

    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["lab_limits_step"] = 2  # the explore step
    app.run()
    for distance in [1, 0.001]:
        app.select_slider(key="concept_lab_limit_distance").set_value(distance).run()
        assert not app.exception
        assert float(app.metric[0].value) == pytest.approx(4 - distance)
        assert float(app.metric[1].value) == pytest.approx(4 + distance)
    spec = json.loads(app.get("vega_lite_chart")[0].proto.spec)
    assert spec["layer"][-1]["mark"]["filled"] is False
    assert len(app.dataframe[0].value) == 6


@pytest.mark.parametrize("x0,exact", [(-3, 22), (0, -5), (1, -2), (2, 7), (3, 22)])
def test_derivative_sliders_update_exact_and_secant_values(x0, exact):
    import json

    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["lab_derivatives_step"] = 2  # the explore step
    app.run()
    app.slider(key="concept_lab_x0").set_value(float(x0)).run()
    errors = []
    for h in [1, 0.001]:
        app.select_slider(key="concept_lab_h").set_value(h).run()
        assert not app.exception
        assert float(app.metric[2].value) == pytest.approx(secant_slope(x0, h), abs=1e-6)
        assert float(app.metric[3].value) == exact
        errors.append(abs(float(app.metric[2].value) - exact))
    assert errors[1] < errors[0]
    spec = json.loads(app.get("vega_lite_chart")[1].proto.spec)
    assert spec["layer"][0]["encoding"]["color"]["scale"]["domain"] == [
        "Curve f(x)", "Secant", "Tangent",
    ]


# The lab tab whose step 3 holds each topic's "Practice this topic" button.
EXPLAIN_STEP = {"calc_limits": "lab_limits_step", "calc_derivatives": "lab_derivatives_step"}


@pytest.mark.parametrize("topic", ["calc_limits", "calc_derivatives"])
@pytest.mark.parametrize("filename", [None, "sample_course.json", "calculus_i_demo.json"])
def test_practice_button_explains_missing_course_or_scope(monkeypatch, topic, filename):
    import streamlit as st

    links = []
    monkeypatch.setattr(st, "page_link", lambda page, **kwargs: links.append(page))
    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = load_course(filename) if filename else None
    app.session_state[EXPLAIN_STEP[topic]] = 3  # the practice button sits in step 3
    app.run().button(key=f"concept_lab_practice_{topic}").click().run()
    assert not app.exception
    expected = (
        "Confirm this topic in Study Plan first."
        if filename == "calculus_i_demo.json"
        else "Open the Calculus I Demo course on the Dashboard to practise this topic."
    )
    assert expected in [item.value for item in app.info]
    assert bool(links) == (filename == "calculus_i_demo.json")
    assert "practice_mode_calculus-i-demo" not in app.session_state


@pytest.mark.parametrize("topic", ["calc_limits", "calc_derivatives"])
def test_practice_button_sets_contract_and_practice_page_uses_it(monkeypatch, topic):
    import streamlit as st

    destinations = []
    # Standalone AppTest has no registered navigation for the pending-review link.
    # The registered-app test below exercises actual navigation without this stub.
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    course = load_course()
    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = course
    app.session_state["confirmed_scope_calculus-i-demo"] = [t.id for t in course.topics]
    history = {"saved-session": {"result": "preserved"}}
    app.session_state["practice_history_calculus-i-demo"] = history
    app.session_state[EXPLAIN_STEP[topic]] = 3  # the practice button sits in step 3
    app.run().button(key=f"concept_lab_practice_{topic}").click().run()
    assert not app.exception
    assert destinations == ["pages/2_Practice_Center.py"]
    practice = AppTest.from_file(str(PAGE_PATH.with_name("2_Practice_Center.py")))
    for key in ["current_course", "confirmed_scope_calculus-i-demo",
                "practice_mode_calculus-i-demo", "practice_topic_calculus-i-demo"]:
        practice.session_state[key] = app.session_state[key]
    practice.run()
    assert not practice.exception
    assert practice.radio(key="practice_mode_calculus-i-demo").value == "Topic Practice"
    assert practice.selectbox(key="practice_topic_calculus-i-demo").value == topic
    assert app.session_state["practice_history_calculus-i-demo"] == history


@pytest.mark.parametrize("topic", ["calc_limits", "calc_derivatives"])
def test_registered_app_navigates_from_lab_to_selected_practice(topic):
    from tests.auth_helpers import signed_in_app

    app = signed_in_app(PAGE_PATH.parents[1] / "app.py").run()
    assert not app.exception
    app.session_state["current_course"] = load_course()
    app.session_state["confirmed_scope_calculus-i-demo"] = [
        "calc_limits", "calc_derivatives",
    ]
    app.session_state[EXPLAIN_STEP[topic]] = 3  # the practice button sits in step 3
    app.switch_page("pages/6_Concept_Lab.py").run()
    assert not app.exception
    assert app.title[0].value == "Concept Lab"
    app.button(key=f"concept_lab_practice_{topic}").click().run()
    assert not app.exception
    assert app.title[0].value == "Practice"
    assert app.radio(key="practice_mode_calculus-i-demo").value == "Topic Practice"
    assert app.selectbox(key="practice_topic_calculus-i-demo").value == topic
