"""The Learning Radar page: chart, ranking and one-click flagging."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services.i18n import LANGUAGE_KEY
from tests.auth_helpers import TEST_USER, signed_in_app
from tests.test_knowledge_graph import (
    REASON_BUTTON_LABELS,
    RadarFake,
    ReasonRadarFake,
    _econ_course,
    _other_course,
    _topic,
)

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "pages" / "7_Learning_Radar.py"
ECON_ID = "econ101"
CALCULUS_ID = "calculus-i-demo"


def _calculus_full():
    return StudyPackage.model_validate_json(
        (ROOT / "data" / "calculus_i_demo.json").read_text(encoding="utf-8")
    )


def _page(course=None, *, signed_in=True):
    app = signed_in_app(PAGE_PATH) if signed_in else AppTest.from_file(str(PAGE_PATH))
    if course is not None:
        app.session_state["current_course"] = course
    return app.run()


def _markdown(app):
    return [item.value for item in app.markdown]


def _captions(app):
    return [item.value for item in app.caption]


def _svgs(app):
    return [value for value in _markdown(app) if "<svg" in value]


def _stuck_buttons(app, course_id, topic_id):
    prefix = f"learning_radar_stuck_{course_id}_{topic_id}_"
    return [
        button for button in app.button
        if button.key and button.key.startswith(prefix)
    ]


def test_page_without_a_course_points_to_the_dashboard(monkeypatch):
    import streamlit as st

    # Page links resolve only inside app.py's navigation, so record them here.
    links = []
    monkeypatch.setattr(st, "page_link", lambda page, **kwargs: links.append(page))
    radar = RadarFake(monkeypatch, [])

    app = _page()

    assert not app.exception
    assert app.title[0].value == "Learning Radar"
    assert [item.value for item in app.info] == ["Load a course from the dashboard first."]
    assert links == ["pages/0_Dashboard.py"]
    assert all(calls == [] for calls in radar.calls.values())


def test_page_for_another_course_says_radar_is_for_demo_courses(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("topic-1", real=9)], enabled=False)

    app = _page(_other_course())

    assert not app.exception
    assert [item.value for item in app.info] == [
        "Learning Radar is available for the built-in demo courses."
    ]
    assert radar.calls["radar_enabled"] == ["course-1"]
    assert all(
        calls == [] for name, calls in radar.calls.items() if name != "radar_enabled"
    )
    assert _svgs(app) == []
    assert "learning_radar_cache_course-1" not in app.session_state


def test_demo_course_shows_chart_ranking_and_topic_pills(monkeypatch):
    radar = RadarFake(
        monkeypatch,
        [
            _topic("elasticity", sample=7),
            _topic("supply_demand", sample=4),
            _topic("price_controls", sample=3),
        ],
        has_sample=True,
    )

    app = _page(_econ_course())

    assert not app.exception
    assert app.title[0].value == "Learning Radar"
    (svg,) = _svgs(app)
    assert (
        'aria-label="Supply and Demand: 4, Price Elasticity of Demand: 7, Price Controls: 3"'
        in svg
    )
    assert "radar-label-focus" not in svg
    assert "**Most flagged topics**" in _markdown(app)
    ranking = next(item.proto.body for item in app.get("html") if "radar-ranking-scroll" in item.proto.body)
    assert 'radar-ranking-scroll' in ranking
    assert ranking.count('class="radar-ranked-row"') == 3
    assert ranking.index('Price Elasticity') < ranking.index('Supply and Demand') < ranking.index('Price Controls')
    assert 'tabindex="0"' in ranking
    assert [limit for _, limit in radar.calls["top_hard_topics"]] == [3]
    pills = app.button_group(key=f"learning_radar_topic_{ECON_ID}")
    assert pills.options == ["Supply and Demand", "Price Elasticity of Demand", "Price Controls"]
    assert pills.value is None
    assert "Pick a topic above to mark it." in _captions(app)
    assert not any(button.key.startswith("learning_radar_stuck_") for button in app.button)
    assert not any("Live flags" in value for value in _captions(app))


def test_picking_a_topic_highlights_it_and_one_click_flags_it(monkeypatch):
    radar = ReasonRadarFake(monkeypatch, [_topic("elasticity", sample=7)])

    app = _page(_econ_course())
    app.button_group(key=f"learning_radar_topic_{ECON_ID}").set_value("elasticity").run()

    assert not app.exception
    (svg,) = _svgs(app)
    assert "<title>Price Elasticity of Demand</title>" in svg
    assert svg.count("radar-label-focus") == 1
    assert [button.label for button in _stuck_buttons(app, ECON_ID, "elasticity")] == (
        REASON_BUTTON_LABELS
    )
    assert "7 students are stuck here" in _markdown(app)

    app.button(key=f"learning_radar_stuck_{ECON_ID}_elasticity_wording").click().run()

    assert not app.exception
    assert radar.flag_reasons == ["wording"]
    assert radar.calls["set_flag"] == [(TEST_USER.user_id, ECON_ID, "elasticity")]
    assert "8 students are stuck here" in _markdown(app)
    assert "You marked this topic." in _markdown(app)
    assert app.button(
        key=f"learning_radar_stuck_{ECON_ID}_elasticity_clear"
    ).label == "Not stuck anymore"


def test_large_course_uses_a_dropdown_and_up_to_eight_axes(monkeypatch):
    course = _calculus_full()
    RadarFake(
        monkeypatch,
        [_topic(topic.id, real=3 + index) for index, topic in enumerate(course.topics[:10])],
    )

    app = _page(course)

    assert not app.exception
    assert app.get("button_group") == []
    picker = app.selectbox(key=f"learning_radar_topic_{CALCULUS_ID}")
    assert picker.value is None
    (svg,) = _svgs(app)
    assert svg.count('class="radar-spoke"') == 8

    picker.set_value("calc_chain_rule").run()

    assert not app.exception
    assert len(_stuck_buttons(app, CALCULUS_ID, "calc_chain_rule")) == 5


def test_open_in_knowledge_map_sets_the_map_focus(monkeypatch):
    import streamlit as st

    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    RadarFake(monkeypatch, [_topic("elasticity", sample=7)])

    app = _page(_econ_course())
    app.button_group(key=f"learning_radar_topic_{ECON_ID}").set_value("price_controls").run()
    button = app.button(key=f"learning_radar_map_{ECON_ID}_price_controls")
    assert button.label == "Open this topic in Knowledge Map"

    button.click().run()

    assert not app.exception
    assert app.session_state[f"graph_pending_focus_{ECON_ID}"] == "price_controls"
    assert destinations == ["pages/4_Knowledge_Graph.py"]


def test_page_shares_the_radar_cache(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("elasticity", sample=7)])

    app = _page(_econ_course())
    app.button_group(key=f"learning_radar_topic_{ECON_ID}").set_value("elasticity").run()

    assert not app.exception
    assert f"learning_radar_cache_{ECON_ID}" in app.session_state
    assert len(radar.calls["get_course_radar"]) == 1
    assert len(radar.calls["get_user_flags"]) == 1


@pytest.mark.parametrize("signed_in", [True, False])
def test_page_in_chinese(monkeypatch, signed_in):
    RadarFake(monkeypatch, [_topic("elasticity", sample=7)], has_sample=True)
    app = signed_in_app(PAGE_PATH) if signed_in else AppTest.from_file(str(PAGE_PATH))
    app.session_state[LANGUAGE_KEY] = True
    app.session_state["current_course"] = _econ_course()

    app.run()

    assert not app.exception
    assert app.title[0].value == "学习雷达"
    assert "各知识点卡住的学生人数" in _captions(app)
    assert app.session_state["current_course"].course_id == ECON_ID
