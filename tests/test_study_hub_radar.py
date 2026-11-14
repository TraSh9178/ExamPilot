"""Page tests for the Learning Radar "Most flagged topics" panel on Study Plan."""

import re
import time
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.runtime.state.common import user_key_from_element_id
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import StudyPackage
from services import learning_radar
from tests.auth_helpers import TEST_USER, signed_in_app


ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "pages" / "1_Study_Hub.py"
PRACTICE_PATH = ROOT / "pages" / "2_Practice_Center.py"
CALCULUS_ID = "calculus-i-demo"
CACHE_KEY = f"learning_radar_cache_{CALCULUS_ID}"
PANEL_KEY = "study_radar_panel"
PANEL_TITLE = "Most flagged topics · Top 3"
PRACTICE_PAGE = "pages/2_Practice_Center.py"
SAMPLE_CAPTION = "Includes sample data"
OFFLINE_CAPTION = "Live flags are unavailable right now."
EMPTY_CAPTION = "No topics have been flagged yet."


def _topic(topic_id, real=0, sample=0, display="total"):
    return learning_radar.TopicRadar(
        topic_id=topic_id,
        real_count=real,
        sample_count=sample,
        reasons={},
        display_count=real + sample if display == "total" else display,
    )


class RadarFake:
    """Scripted learning_radar functions; every call is recorded.

    Ranking uses the real top_hard_topics so the page is checked against the
    backend's ordering. The Study Plan page must never write flags.
    """

    def __init__(self, monkeypatch, topics=(), *, enabled=True, live=True, has_sample=False):
        self.topics = {topic.topic_id: topic for topic in topics}
        self.enabled = enabled
        self.live = live
        self.has_sample = has_sample
        self._rank = learning_radar.top_hard_topics
        self.calls = {
            name: []
            for name in (
                "radar_enabled",
                "get_course_radar",
                "get_user_flags",
                "top_hard_topics",
                "set_flag",
                "clear_flag",
            )
        }
        for name in self.calls:
            monkeypatch.setattr(learning_radar, name, getattr(self, name))

    def radar_enabled(self, course_id):
        self.calls["radar_enabled"].append(course_id)
        return self.enabled

    def get_course_radar(self, course_id):
        self.calls["get_course_radar"].append(course_id)
        return learning_radar.CourseRadar(
            topics=dict(self.topics), live=self.live, has_sample=self.has_sample
        )

    def get_user_flags(self, user_id, course_id):
        self.calls["get_user_flags"].append((user_id, course_id))
        return {}

    def top_hard_topics(self, radar, limit=3):
        self.calls["top_hard_topics"].append(limit)
        return self._rank(radar, limit)

    def set_flag(self, *args, **kwargs):
        self.calls["set_flag"].append(args)
        raise AssertionError("Study Plan must not write radar flags.")

    def clear_flag(self, *args, **kwargs):
        self.calls["clear_flag"].append(args)
        raise AssertionError("Study Plan must not write radar flags.")


def _calculus_course():
    return StudyPackage.model_validate_json(
        (ROOT / "data" / "calculus_i_demo.json").read_text(encoding="utf-8")
    )


def _course(course_id, names):
    return StudyPackage(
        course_id=course_id,
        course_name="Radar Course",
        topics=[
            {"id": topic_id, "name": name, "summary": f"{name} summary."}
            for topic_id, name in names.items()
        ],
        relationships=[],
        questions=[],
    )


def _study_page(course, *, signed_in=False, confirmed=None):
    app = signed_in_app(PAGE_PATH) if signed_in else AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = course
    if confirmed is not None:
        app.session_state[f"confirmed_scope_{course.course_id}"] = list(confirmed)
    return app.run()


def _block_key(node):
    proto = getattr(node, "proto", None)
    if isinstance(node, Block) and isinstance(proto, BlockProto) and proto.id:
        return user_key_from_element_id(proto.id)
    return None


def _panel(app):
    """The radar panel container, or None when it was not rendered."""
    return next((node for node in app.main if _block_key(node) == PANEL_KEY), None)


def _rows(panel):
    return [item.value for item in panel.markdown]


def _captions(panel):
    return [item.value for item in panel.caption]


def _practice_buttons(container):
    return [
        button for button in container.button
        if button.key and button.key.startswith("study_radar_practice_")
    ]


def _practice_key(course_id, topic_id):
    return f"study_radar_practice_{course_id}_{topic_id}"


def test_panel_lists_top_three_most_flagged_first_with_counts(monkeypatch):
    course = _course(
        "radar-course",
        {"t1": "Limits", "t2": "Derivatives", "t3": "Series", "t4": "Integrals"},
    )
    radar = RadarFake(
        monkeypatch,
        [
            _topic("t1", real=5),
            _topic("t2", real=3, sample=5),
            _topic("t3", real=1, display=None),
            _topic("t4", real=6),
        ],
    )

    app = _study_page(course)

    assert not app.exception
    panel = _panel(app)
    assert panel is not None
    assert [item.value for item in panel.subheader] == [PANEL_TITLE]
    assert _rows(panel) == [
        "**1. Derivatives** — 8 students are stuck here",
        "**2. Integrals** — 6 students are stuck here",
        "**3. Limits** — 5 students are stuck here",
    ]
    assert [(button.label, button.key) for button in _practice_buttons(panel)] == [
        ("Practice now", _practice_key("radar-course", "t2")),
        ("Practice now", _practice_key("radar-course", "t4")),
        ("Practice now", _practice_key("radar-course", "t1")),
    ]
    assert radar.calls["top_hard_topics"] == [3]
    assert radar.calls["get_course_radar"] == ["radar-course"]
    assert EMPTY_CAPTION not in _captions(panel)


def test_single_flag_uses_singular_wording(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_derivatives", sample=1)])

    app = _study_page(_calculus_course())

    assert not app.exception
    assert _rows(_panel(app)) == ["**1. Derivatives** — 1 student is stuck here"]


def test_hidden_count_shows_no_number(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_limits", real=2, display=None)])

    app = _study_page(_calculus_course())

    assert not app.exception
    rows = _rows(_panel(app))
    assert rows == ["**1. Limits** — Some students flagged this"]
    count_text = rows[0].split(" — ", 1)[1]
    assert not re.search(r"\d", count_text)


def test_topics_outside_the_course_are_skipped(monkeypatch):
    RadarFake(
        monkeypatch,
        [
            _topic("calc_integrals", real=20),
            _topic("calc_derivatives", real=8),
            _topic("calc_limits", real=5),
        ],
    )

    app = _study_page(_calculus_course())

    assert not app.exception
    panel = _panel(app)
    assert _rows(panel) == [
        "**1. Derivatives** — 8 students are stuck here",
        "**2. Limits** — 5 students are stuck here",
    ]
    assert not any("calc_integrals" in button.key for button in panel.button)


@pytest.mark.parametrize("has_sample", [True, False])
@pytest.mark.parametrize("live", [True, False])
def test_panel_captions_for_sample_and_offline_data(monkeypatch, live, has_sample):
    RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        live=live,
        has_sample=has_sample,
    )

    app = _study_page(_calculus_course())

    assert not app.exception
    captions = _captions(_panel(app))
    assert captions.count(SAMPLE_CAPTION) == (1 if has_sample else 0)
    assert captions.count(OFFLINE_CAPTION) == (0 if live else 1)
    assert EMPTY_CAPTION not in captions


def test_panel_says_when_nothing_is_flagged(monkeypatch):
    RadarFake(monkeypatch, [])

    app = _study_page(_calculus_course())

    assert not app.exception
    panel = _panel(app)
    assert [item.value for item in panel.subheader] == [PANEL_TITLE]
    assert EMPTY_CAPTION in _captions(panel)
    assert _rows(panel) == []
    assert _practice_buttons(panel) == []


def test_panel_never_mentions_a_time_window(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)], has_sample=True, live=False)

    app = _study_page(_calculus_course())

    assert not app.exception
    panel = _panel(app)
    texts = (
        [item.value for item in panel.subheader] + _rows(panel) + _captions(panel)
    )
    assert not any(
        word in text.lower()
        for text in texts
        for word in ("week", "today", "month", "recent")
    )


def test_non_demo_course_shows_no_panel_and_fetches_nothing(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("topic-1", real=9)], enabled=False)
    course = _course("course-1", {"topic-1": "Limits", "topic-2": "Series"})

    app = _study_page(course, signed_in=True, confirmed=["topic-1"])

    assert not app.exception
    assert radar.calls["radar_enabled"] == ["course-1"]
    assert all(
        calls == [] for name, calls in radar.calls.items() if name != "radar_enabled"
    )
    assert _panel(app) is None
    assert PANEL_TITLE not in [item.value for item in app.subheader]
    assert _practice_buttons(app) == []
    assert not any(
        item.value in {SAMPLE_CAPTION, OFFLINE_CAPTION, EMPTY_CAPTION}
        for item in app.caption
    )
    assert "learning_radar_cache_course-1" not in app.session_state


def test_panel_sits_between_start_practice_and_question_review(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])
    course = _calculus_course()

    app = _study_page(course, confirmed=[topic.id for topic in course.topics])

    assert not app.exception
    top_level = list(app.main.children.values())

    def index_of(predicate):
        return next(index for index, node in enumerate(top_level) if predicate(node))

    scope = index_of(lambda node: _block_key(node) == "study_scope_panel")
    start = index_of(
        lambda node: node.type == "button" and node.label == "Start practice"
    )
    panel = index_of(lambda node: _block_key(node) == PANEL_KEY)
    review = index_of(
        lambda node: node.type == "expander"
        and node.label == "Review and edit questions"
    )
    assert scope < start < panel < review


def test_practice_now_on_confirmed_topic_preselects_topic_practice(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    # Standalone AppTest has no registered navigation for the Practice page's
    # review link; the registered-app test below navigates without this stub.
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=8), _topic("calc_limits", real=5)],
    )
    course = _calculus_course()
    app = _study_page(course, confirmed=[topic.id for topic in course.topics])
    assert "practice_mode_calculus-i-demo" not in app.session_state
    assert "practice_topic_calculus-i-demo" not in app.session_state

    app.button(key=_practice_key(CALCULUS_ID, "calc_derivatives")).click().run()

    assert not app.exception
    assert destinations == [PRACTICE_PAGE]
    assert app.session_state["practice_mode_calculus-i-demo"] == "Topic Practice"
    assert app.session_state["practice_topic_calculus-i-demo"] == "calc_derivatives"
    assert [item.value for item in _panel(app).info] == []

    # The Practice page picks up the preselection without any change to it.
    practice = AppTest.from_file(str(PRACTICE_PATH))
    for key in [
        "current_course",
        "confirmed_scope_calculus-i-demo",
        "practice_mode_calculus-i-demo",
        "practice_topic_calculus-i-demo",
    ]:
        practice.session_state[key] = app.session_state[key]
    practice.run()
    assert not practice.exception
    assert practice.radio(key="practice_mode_calculus-i-demo").value == "Topic Practice"
    assert practice.selectbox(key="practice_topic_calculus-i-demo").value == "calc_derivatives"


@pytest.mark.parametrize("confirmed", [None, ["calc_limits"]])
def test_practice_now_on_unconfirmed_topic_asks_to_confirm_scope(monkeypatch, confirmed):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=8), _topic("calc_limits", real=5)],
    )

    app = _study_page(_calculus_course(), confirmed=confirmed)
    app.button(key=_practice_key(CALCULUS_ID, "calc_derivatives")).click().run()

    assert not app.exception
    assert destinations == []
    assert "practice_mode_calculus-i-demo" not in app.session_state
    assert "practice_topic_calculus-i-demo" not in app.session_state
    assert [item.value for item in _panel(app).info] == [
        "Confirm Derivatives in your exam scope above, then select Practice now again."
    ]
    assert app.session_state["scope_selection_calculus-i-demo"] == (confirmed or [])


def test_registered_app_navigates_from_study_plan_to_selected_practice(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_derivatives", real=8)])

    app = signed_in_app(ROOT / "app.py").run()
    assert not app.exception
    app.session_state["current_course"] = _calculus_course()
    app.session_state["confirmed_scope_calculus-i-demo"] = [
        "calc_limits", "calc_derivatives",
    ]
    app.switch_page("pages/1_Study_Hub.py").run()
    assert not app.exception
    assert app.title[0].value == "Study Plan"

    app.button(key=_practice_key(CALCULUS_ID, "calc_derivatives")).click().run()

    assert not app.exception
    assert app.title[0].value == "Practice"
    assert app.radio(key="practice_mode_calculus-i-demo").value == "Topic Practice"
    assert app.selectbox(key="practice_topic_calculus-i-demo").value == "calc_derivatives"


def test_two_reruns_within_fifteen_seconds_fetch_the_radar_once(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _study_page(_calculus_course(), signed_in=True)
    app.run()
    app.run()

    assert not app.exception
    assert radar.calls["get_course_radar"] == [CALCULUS_ID]
    assert radar.calls["get_user_flags"] == [(TEST_USER.user_id, CALCULUS_ID)]
    assert app.session_state[CACHE_KEY]["user_id"] == TEST_USER.user_id

    snapshot = dict(app.session_state[CACHE_KEY])
    snapshot["fetched_at"] -= 16
    app.session_state[CACHE_KEY] = snapshot
    app.run()

    assert not app.exception
    assert radar.calls["get_course_radar"] == [CALCULUS_ID, CALCULUS_ID]


def test_panel_reuses_the_radar_cached_by_the_knowledge_map(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_limits", real=3)])
    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = _calculus_course()
    app.session_state[CACHE_KEY] = {
        "fetched_at": time.monotonic(),
        "user_id": None,
        "radar": learning_radar.CourseRadar(
            topics={"calc_derivatives": _topic("calc_derivatives", real=7)},
            live=True,
            has_sample=False,
        ),
        "user_flags": {},
    }

    app.run()

    assert not app.exception
    assert radar.calls["get_course_radar"] == []
    assert _rows(_panel(app)) == ["**1. Derivatives** — 7 students are stuck here"]


def test_panel_renders_without_a_signed_in_user(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _study_page(_calculus_course())

    assert not app.exception
    assert _rows(_panel(app)) == ["**1. Derivatives** — 4 students are stuck here"]
    assert radar.calls["get_user_flags"] == []
    assert app.session_state[CACHE_KEY]["user_id"] is None


def test_page_renders_with_real_backend_when_database_is_unavailable():
    # Tests never configure a database, so the backend reports sample data only.
    app = _study_page(_calculus_course())

    assert not app.exception
    panel = _panel(app)
    assert _rows(panel) == [
        "**1. Derivatives** — 8 students are stuck here",
        "**2. Applications of Derivatives** — 6 students are stuck here",
        "**3. Limits** — 5 students are stuck here",
    ]
    assert SAMPLE_CAPTION in _captions(panel)
    assert OFFLINE_CAPTION in _captions(panel)
