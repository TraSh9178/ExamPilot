"""A scope selection that is not confirmed yet survives a visit to a focus page.

Topic summaries and Course tools used to be expanders on Study Plan, so the
pills stayed on screen. They are pages of their own now, and Streamlit forgets
a widget's value once its page is left.
"""
from pathlib import Path

import pytest

from models.schemas import Question, StudyPackage
from tests.auth_helpers import signed_in_app

ROOT = Path(__file__).resolve().parents[1]
STUDY_PLAN = "pages/1_Study_Hub.py"
PILLS = "scope_selection_c1"
CONFIRMED = "confirmed_scope_c1"
FOCUS_BUTTONS = ["open_topic_summaries", "open_course_tools"]


def course(saved_scope=None):
    return StudyPackage(
        course_id="c1", course_name="Course",
        topics=[
            {"id": "t1", "name": "Limits", "summary": "L."},
            {"id": "t2", "name": "Series", "summary": "S."},
            {"id": "t3", "name": "Derivatives", "summary": "D."},
        ],
        relationships=[],
        questions=[
            Question(id=f"q{number}", topic_id="t1", question=f"Question {number}?", options=list("abcd"),
                     correct_index=1, explanation="E.")
            for number in range(1, 4)
        ],
        learning_state={"confirmed_scope": saved_scope} if saved_scope else {},
    )


def study_plan():
    """Study Plan in the registered app, with t1 confirmed in this session."""
    app = signed_in_app(ROOT / "app.py")
    app.default_timeout = 30
    app.run()
    app.session_state["current_course"] = course()
    app.session_state[CONFIRMED] = ["t1"]
    app.switch_page(STUDY_PLAN).run()
    assert not app.exception
    assert app.button_group(key=PILLS).value == ["t1"]
    return app


def visit(app, button):
    app.button(key=button).click().run()
    assert not app.exception
    assert app.title[0].value != "Study Plan"


@pytest.mark.parametrize("button", FOCUS_BUTTONS)
def test_unconfirmed_selection_is_back_after_the_visit(button):
    app = study_plan()
    app.button_group(key=PILLS).set_value(["t1", "t2", "t3"]).run()
    visit(app, button)
    app.switch_page(STUDY_PLAN).run()
    assert not app.exception
    pills = app.button_group(key=PILLS)
    assert pills.value == ["t1", "t2", "t3"]
    # The browser is told as well: the pills are drawn in the run that puts the selection back.
    assert pills.proto.set_value
    # Still unconfirmed, exactly as the student left it, and nothing is left behind.
    assert CONFIRMED not in app.session_state
    assert "scope_draft_c1" not in app.session_state


@pytest.mark.parametrize("button", FOCUS_BUTTONS)
def test_confirmed_selection_stays_confirmed_after_the_visit(button):
    app = study_plan()
    visit(app, button)
    app.switch_page(STUDY_PLAN).run()
    assert not app.exception
    assert app.button_group(key=PILLS).value == ["t1"]
    assert app.session_state[CONFIRMED] == ["t1"]


def test_selection_put_aside_is_dropped_when_the_saved_scope_changed_meanwhile():
    app = study_plan()
    app.button_group(key=PILLS).set_value(["t1", "t2", "t3"]).run()
    visit(app, "open_course_tools")
    # As after restoring a backup: the course now carries a different saved scope.
    app.session_state["current_course"] = course(saved_scope=["t2"])
    app.switch_page(STUDY_PLAN).run()
    assert not app.exception
    assert app.button_group(key=PILLS).value == ["t2"]
    assert app.session_state[CONFIRMED] == ["t2"]
    assert "scope_draft_c1" not in app.session_state


def test_topics_that_no_longer_exist_are_left_out():
    app = study_plan()
    app.button_group(key=PILLS).set_value(["t1", "t3"]).run()
    visit(app, "open_topic_summaries")
    smaller = course()
    smaller.topics = [topic for topic in smaller.topics if topic.id != "t3"]
    app.session_state["current_course"] = smaller
    app.switch_page(STUDY_PLAN).run()
    assert not app.exception
    assert app.button_group(key=PILLS).value == ["t1"]
