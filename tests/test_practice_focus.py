"""Practice focus: one screen at a time, one question per page, a side panel that folds away."""
import re
import time
from copy import deepcopy
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import ExamSession, Question, StudyPackage
from services.exam_engine import create_exam, grade_exam
from services.i18n import LANGUAGE_KEY
from tests.auth_helpers import signed_in_app
from tests.test_learning_flow_ux import calculus
from tests.test_paper_practice import FakeRadarChart, badges, page_markdown
from tests.test_practice_clock import clock_html, find_block
from tests.test_practice_insights import setup_course, start_app
from tests.test_practice_page import (
    HISTORY_PAGE_PATH, carry_to, history_rows, keyed_button, make_practice_state, open_review, open_setup,
    submit_answers,
)

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "2_Practice_Center.py"
CSS = ROOT / "assets" / "paper_practice.css"


def practice_app(mode="topic", question_ids=("q0", "q1", "q2"), *, course=None, scope=None, active=None, extra=None):
    """The practice page with a session in progress (course "insights" unless given)."""
    course = course or setup_course()
    by_id = {question.id: question for question in course.questions}
    questions = [by_id[qid] for qid in question_ids]
    session = ExamSession(session_id="s", mode=mode, question_ids=list(question_ids))
    app = AppTest.from_file(str(PAGE))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = scope or sorted({q.topic_id for q in questions})
    app.session_state[f"active_practice_{course.course_id}"] = {
        "session": session, "questions": questions, "warning": None, "settings": {}, **(active or {}),
    }
    for key, value in (extra or {}).items():
        app.session_state[key] = value
    return app.run()


def block_keys(app, root=None):
    """Keys of every st.container on the page (or inside root), in page order."""
    keys = []

    def walk(node):
        if isinstance(node, Block):
            block_id = getattr(node.proto, "id", "") or ""
            if block_id.startswith("$$ID-"):
                keys.append(block_id.split("-", 2)[2])
        for child in getattr(node, "children", {}).values():
            walk(child)

    walk(root if root is not None else app.main)
    return keys


def cards(app):
    return [key for key in block_keys(app) if key.startswith("practice_question_")]


def turn_key(app):
    turns = [key for key in block_keys(app) if key.startswith("practice_turn_")]
    assert len(turns) == 1
    return turns[0]


def titles(app):
    return [title.value for title in app.title]


def counter(app):
    return [caption.value for caption in find_block(app, "flight_progress_count").caption]


def subheaders(app):
    return [subheader.value for subheader in app.subheader]


def popover_labels(app):
    return [popover.proto.popover.label for popover in app.get("popover")]


def keys_starting(app, prefix):
    return [button.key for button in app.button if (button.key or "").startswith(prefix)]


def index_of(app):
    return app.session_state["active_practice_insights"].get("worksheet_index", 0)


def next_question(app):
    app.button(key="worksheet_next_s").click().run()
    assert not app.exception
    return app


def previous_question(app):
    app.button(key="worksheet_previous_s").click().run()
    assert not app.exception
    return app


def saved_record(course, sid="old"):
    questions = course.questions[:2]
    session = ExamSession(session_id=sid, mode="topic", question_ids=[q.id for q in questions])
    result = grade_exam(session, questions, {questions[0].id: 0, questions[1].id: 1})
    return {"session": session, "questions": questions, "attempts": result["attempts"], "result": result}


# 2 · The question screen holds the question and nothing else -----------------------------

@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_question_screen_has_no_settings_drafts_saved_sessions_checklist_or_submit(mode):
    course = setup_course()
    draft = {"session": ExamSession(session_id="d", mode="topic", question_ids=["q0"]),
             "questions": [course.questions[0]], "warning": None, "settings": {}}
    app = practice_app(mode, course=course, extra={
        # Both exist, so the setup screen would list them.
        "practice_drafts_insights": {"d": draft},
        "practice_history_insights": {"old": saved_record(course)},
    })
    assert not app.exception
    assert titles(app) == ["Practice · Topic" if mode == "topic" else "Practice · Mock Exam"]
    # No settings control of any kind.
    assert not [radio for radio in app.radio if (radio.key or "").startswith("practice_mode_")]
    assert not app.number_input and not app.selectbox
    assert not [group for group in app.button_group if (group.key or "").startswith("practice_topic_")]
    assert not keys_starting(app, "practice_start_")
    # No expander at all: no settings, drafts or saved sessions.
    assert [expander.label for expander in app.expander] == []
    assert not keys_starting(app, "resume_draft_") and not keys_starting(app, "open_saved_result_")
    # No overview box, no checklist, no submit, no "Work on this question".
    assert "Practice session" not in subheaders(app)
    assert "practice_overview" not in block_keys(app)
    assert "Review before submit" not in subheaders(app) and not app.dataframe
    labels = [button.label for button in app.button]
    assert "Submit answers" not in labels and "Work on this question" not in labels
    assert [key for key in keys_starting(app, "focus_") if not key.startswith("focus_pause_")] == []
    assert not any(caption.value.startswith(("Answered", "Choose a mode")) for caption in app.caption)
    assert len(cards(app)) == 1 and len(badges(app)) == 1


def test_title_row_carries_the_session_menu_and_the_panel_toggle():
    app = practice_app()
    row = find_block(app, "practice_title_row")
    assert row.proto.flex_container.direction == BlockProto.FlexContainer.Direction.HORIZONTAL
    assert row.proto.flex_container.wrap
    assert [title.value for title in row.title] == ["Practice · Topic"]
    tools = find_block(app, "practice_title_tools")
    menu = next(popover for popover in app.get("popover") if popover.proto.popover.label == "This session")
    assert menu.proto.popover.icon == ":material/more_horiz:"
    assert [button.label for button in menu.button] == ["Review and submit", "Change settings"]
    assert [button.key for button in tools.button] == [
        "worksheet_review_s", "practice_change_settings_s", "practice_side_panel_toggle_insights",
    ]


# 3 · One card; Previous and Next move one question -----------------------------------------

@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_one_card_at_a_time_and_previous_next_move_one_question(mode):
    app = practice_app(mode)
    title = "Practice · Topic" if mode == "topic" else "Practice · Mock Exam"
    for number in (1, 2, 3):
        assert len(cards(app)) == 1 and badges(app) == [f"Q{number:02}"]
        assert cards(app) == [f"practice_question_q{number - 1}"]
        assert counter(app) == [f"Question {number:02} / 03"]
        assert titles(app) == [title]
        assert index_of(app) == number - 1
        if number < 3:
            next_question(app)
    for number in (2, 1):
        previous_question(app)
        assert badges(app) == [f"Q{number:02}"] and counter(app) == [f"Question {number:02} / 03"]
        assert len(cards(app)) == 1


@pytest.mark.parametrize(("mode", "expected"), [
    ("topic", ["Practice · Topic", "Practice · Other"]),
    ("mock", ["Practice · Mock Exam", "Practice · Mock Exam"]),
])
def test_title_and_counter_follow_the_question_on_screen(mode, expected):
    app = practice_app(mode, ("q2", "q3"), scope=["other", "t"])
    assert titles(app) == expected[:1] and counter(app) == ["Question 01 / 02"]
    next_question(app)
    assert titles(app) == expected[1:] and counter(app) == ["Question 02 / 02"]


@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_repeated_clicks_at_either_end_never_raise(mode):
    app = practice_app(mode, ("q0", "q1"))
    assert app.button(key="worksheet_previous_s").disabled
    for _ in range(3):
        previous_question(app)
        assert index_of(app) == 0 and badges(app) == ["Q01"]
    next_question(app)
    # The last question has Finish instead of Next.
    assert not keys_starting(app, "worksheet_next_")
    assert app.button(key="worksheet_finish_s").label == "Finish"
    assert app.button(key="worksheet_finish_s").proto.type == "primary"
    # A late Next click: Next was on screen, but an earlier click already reached the end.
    app.session_state["active_practice_insights"]["worksheet_index"] = 0
    app.run()
    app.session_state["active_practice_insights"]["worksheet_index"] = 1
    app.button(key="worksheet_next_s").click().run()
    assert not app.exception
    assert index_of(app) == 1 and badges(app) == ["Q02"]
    app.button(key="worksheet_finish_s").click().run()
    assert not app.exception
    assert titles(app) == ["Practice · Review"]
    assert not keys_starting(app, "worksheet_finish_")  # a second Finish click has nothing to hit


# 4 · Answers and confidence off screen are kept --------------------------------------------

@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_answers_and_confidence_survive_paging_and_the_review_step(mode):
    app = practice_app(mode)
    app.radio(key="answer_s_q0").set_value(2).run()
    app.button_group(key="confidence_s_q0").set_value("unsure").run()
    next_question(app)
    assert app.radio(key="answer_s_q1").value is None
    assert app.button_group(key="confidence_s_q1").value is None
    app.radio(key="answer_s_q1").set_value(1).run()
    app.button_group(key="confidence_s_q1").set_value("guessed").run()
    next_question(app)
    previous_question(app)
    previous_question(app)
    assert app.radio(key="answer_s_q0").value == 2
    assert app.button_group(key="confidence_s_q0").value == "unsure"
    next_question(app)
    assert app.radio(key="answer_s_q1").value == 1
    assert app.button_group(key="confidence_s_q1").value == "guessed"
    open_review(app)
    assert "2 of 3 answered" in page_markdown(app)
    table = app.dataframe[0].value
    assert list(table["Check"]) == ["Unsure", "Guessed", "Unanswered"]
    app.button(key="worksheet_back_s").click().run()
    assert badges(app) == ["Q02"]
    assert app.radio(key="answer_s_q1").value == 1
    assert app.button_group(key="confidence_s_q1").value == "guessed"
    previous_question(app)
    assert app.radio(key="answer_s_q0").value == 2
    assert app.button_group(key="confidence_s_q0").value == "unsure"


def test_hints_shown_survive_paging():
    course = setup_course()
    course.questions[0].hints = ["Compare both values.", "Check the units."]
    app = practice_app(course=course)
    app.button(key="hint_button_s_q0").click().run()
    next_question(app)
    previous_question(app)
    assert [info.value for info in app.info] == ["Hint 1 of 2: Compare both values."]
    assert app.button(key="hint_button_s_q0").label == "Next hint"


# 5 · Submitting from the review step ---------------------------------------------------------

@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_submit_from_review_grades_every_question_and_stores_the_same_record(mode):
    app = practice_app(mode)
    app.radio(key="answer_s_q0").set_value(0).run()  # correct
    next_question(app)
    app.radio(key="answer_s_q1").set_value(1).run()  # incorrect
    next_question(app)  # q2 stays unanswered
    app.button(key="worksheet_finish_s").click().run()
    app.button(key="practice_submit_s").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    result = active["result"]
    assert [(a.question_id, a.selected_index, a.is_correct) for a in result["attempts"]] == [
        ("q0", 0, True), ("q1", 1, False), ("q2", None, False),
    ]
    assert (result["correct_count"], result["total_count"]) == (1, 3)
    record = app.session_state["practice_history_insights"]["s"]
    assert set(record) == {"session", "questions", "attempts", "result"}
    assert record["session"] == active["session"] and record["result"] is result
    assert record["questions"] == active["questions"] and record["attempts"] == result["attempts"]
    rows = app.session_state["current_course"].learning_state["practice_insights"]["s"]
    assert set(rows) == {"q0", "q1", "q2"}
    # The result screen: overview, score, and a way to a new practice; no settings.
    assert "Practice session" in subheaders(app) and "Your result" in subheaders(app)
    assert "practice_overview" in block_keys(app)
    assert titles(app) == ["Practice"]
    assert app.button(key="practice_new_insights").label == "New practice"
    assert not [radio for radio in app.radio if (radio.key or "").startswith("practice_mode_")]
    # Each answer is on the Review answers page, opened from here.
    assert not badges(app) and app.button(key="open_answer_review").label == "Review answers"


def test_mock_exam_offers_no_hints_on_any_question():
    course = setup_course()
    for question in course.questions:
        question.hints = ["Compare both values.", "Check the units."]
    app = practice_app("mock", course=course)
    for _ in range(3):
        assert not keys_starting(app, "hint_button_")
        assert not [info for info in app.info if info.value.startswith("Hint ")]
        if keys_starting(app, "worksheet_next_"):
            next_question(app)
    topic = practice_app("topic", course=setup_course())
    topic.session_state["active_practice_insights"]["questions"][0].hints = ["Compare both values.", "Check the units."]
    topic.run()
    assert topic.button(key="hint_button_s_q0").label == "Hint"


# 6 · The review step ----------------------------------------------------------------------------

def test_review_step_from_the_session_menu_and_from_finish():
    app = practice_app()
    app.radio(key="answer_s_q0").set_value(0).run()
    app.button_group(key="confidence_s_q0").set_value("guessed").run()
    next_question(app)
    for _ in range(2):  # the menu offers it on every question
        assert app.button(key="worksheet_review_s").label == "Review and submit"
        if keys_starting(app, "worksheet_next_"):
            next_question(app)
    previous_question(app)  # back on question 2
    open_review(app)
    assert titles(app) == ["Practice · Review"]
    assert "1 of 3 answered" in page_markdown(app)
    assert "Review before submit" in subheaders(app)
    table = app.dataframe[0].value
    assert list(table["Question"]) == [1, 2, 3]
    assert list(table["Check"]) == ["Guessed", "Unanswered", "Unanswered"]
    assert ("Go back to the questions to change these answers, or submit them as they are."
            in [caption.value for caption in app.caption])
    assert [(button.label, button.proto.type) for button in app.button] == [
        ("Back to questions", "secondary"), ("Submit answers", "primary"),
    ]
    # Nothing from the question screen.
    assert not badges(app) and clock_html(app) is None and not app.radio
    app.button(key="worksheet_back_s").click().run()
    assert badges(app) == ["Q02"]  # the question the student came from
    next_question(app)
    app.button(key="worksheet_finish_s").click().run()
    assert titles(app) == ["Practice · Review"]
    app.button(key="worksheet_back_s").click().run()
    assert badges(app) == ["Q03"]


def test_review_submit_error_stays_short(monkeypatch):
    from services import exam_engine

    def broken_grade(*args):
        raise ValueError("questions must match the question IDs in session q0")

    monkeypatch.setattr(exam_engine, "grade_exam", broken_grade)
    app = practice_app()
    submit_answers(app)
    assert not app.exception
    assert titles(app) == ["Practice · Review"]
    assert [error.value for error in app.error] == ["Could not grade this practice. Please try again."]


# 7 · The side panel ----------------------------------------------------------------------------

def test_side_panel_hides_and_shows_with_one_click_and_stays_as_chosen():
    app = practice_app()
    assert "flight_worksheet_margin" in block_keys(app) and "Quick Notes" in subheaders(app)
    toggle = app.button(key="practice_side_panel_toggle_insights")
    assert (toggle.label, toggle.proto.icon) == ("Hide side panel", ":material/right_panel_close:")
    toggle.click().run()
    assert not app.exception
    assert "flight_worksheet_margin" not in block_keys(app)
    assert "Quick Notes" not in subheaders(app) and "Topic" not in [c.value for c in app.caption]
    assert "practice_main_full" in block_keys(app)
    toggle = app.button(key="practice_side_panel_toggle_insights")
    assert (toggle.label, toggle.proto.icon) == ("Show side panel", ":material/right_panel_open:")
    # Paging, any rerun and the review step keep the choice.
    next_question(app)
    app.run()
    open_review(app)
    app.button(key="worksheet_back_s").click().run()
    assert "flight_worksheet_margin" not in block_keys(app) and "Quick Notes" not in subheaders(app)
    app.button(key="practice_side_panel_toggle_insights").click().run()
    assert "flight_worksheet_margin" in block_keys(app) and "Quick Notes" in subheaders(app)
    assert "practice_main_full" not in block_keys(app)


def test_side_panel_choice_survives_leaving_the_page_and_returning():
    state = make_practice_state(graded=False)
    active = state["active_practice_course-1"]
    active["session"] = active["session"].model_copy(update={"mode": "topic"})
    app = signed_in_app(ROOT / "app.py").run()
    for key, value in state.items():
        app.session_state[key] = value
    app.session_state["practice_history_course-1"] = {}
    app.switch_page("pages/2_Practice_Center.py").run()
    assert "Quick Notes" in subheaders(app)
    app.button(key="practice_side_panel_toggle_course-1").click().run()
    assert "Quick Notes" not in subheaders(app)
    app.switch_page("pages/3_Performance.py").run()
    app.switch_page("pages/2_Practice_Center.py").run()
    assert not app.exception
    assert "Quick Notes" not in subheaders(app)
    assert app.button(key="practice_side_panel_toggle_course-1").label == "Show side panel"


def test_mock_exam_without_the_radar_shows_no_panel_and_no_toggle():
    app = practice_app("mock")
    assert "flight_worksheet_margin" not in block_keys(app)
    assert not keys_starting(app, "practice_side_panel_toggle_")
    assert "Quick Notes" not in subheaders(app)
    assert "practice_main_full" in block_keys(app)


@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_radar_panel_in_both_modes_notes_only_in_topic_practice(monkeypatch, mode):
    fake = FakeRadarChart(monkeypatch)
    course = calculus()
    scope = ["calc_limits", "calc_derivatives"]
    exam = create_exam(package=course, mode=mode, requested_count=2, confirmed_topic_ids=scope,
                       topic_id="calc_limits" if mode == "topic" else None)
    app = signed_in_app(PAGE)
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = scope
    app.session_state[f"active_practice_{course.course_id}"] = {
        "session": exam["session"], "questions": exam["questions"], "warning": None, "settings": {},
    }
    app.run()
    assert not app.exception
    sid = exam["session"].session_id
    assert len(fake.charts) == 1 and fake.charts[0][2] == exam["questions"][0].topic_id
    assert "Learning Radar" in subheaders(app)
    assert ("Quick Notes" in subheaders(app)) == (mode == "topic")
    app.button(key=f"practice_side_panel_toggle_{course.course_id}").click().run()
    # Hidden: nothing of the panel is drawn (the stuck menu under the question stays).
    assert len(fake.charts) == 1
    assert "Learning Radar" not in subheaders(app) and "Quick Notes" not in subheaders(app)
    assert not keys_starting(app, f"worksheet_radar_{sid}")
    assert popover_labels(app) == ["This session", "Learning Radar"]


# 8 · The setup screen -------------------------------------------------------------------------

def setup_app(scope, course=None, extra=None):
    course = course or setup_course()
    app = AppTest.from_file(str(PAGE))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = scope
    for key, value in (extra or {}).items():
        app.session_state[key] = value
    return app.run()


def test_setup_screen_shows_the_settings_on_the_page_and_starts_a_question_screen():
    app = setup_app(["t", "other"])
    assert not app.exception
    assert titles(app) == ["Practice"]
    assert app.radio(key="practice_mode_insights").options == ["Mock Exam", "Topic Practice"]
    assert app.number_input(key="practice_count_insights").value == 10
    assert not app.expander and not keys_starting(app, "practice_return_previous")
    app.radio(key="practice_mode_insights").set_value("Topic Practice").run()
    pills = app.button_group(key="practice_topic_insights")
    assert pills.options == ["Topic", "Other"] and pills.value == "t"
    assert not app.selectbox
    pills.set_value("other").run()
    app.number_input(key="practice_count_insights").set_value(1).run()
    start = app.button(key="practice_start_insights")
    assert (start.label, start.proto.type) == ("Start practice", "primary")
    start.click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["settings"] == {"mode": "topic", "requested_count": 1,
                                  "confirmed_topic_ids": ["other", "t"], "topic_id": "other"}
    assert active["session"].question_ids == ["q3"]
    assert titles(app) == ["Practice · Other"] and badges(app) == ["Q01"]
    assert not [radio for radio in app.radio if (radio.key or "").startswith("practice_mode_")]


def test_a_changed_count_and_mode_arrive_with_the_start_click():
    app = setup_app(["t"])
    app.radio(key="practice_mode_insights").set_value("Topic Practice")
    app.number_input(key="practice_count_insights").set_value(2)
    app.button(key="practice_start_insights").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["session"].mode == "topic" and len(active["questions"]) == 2
    assert active["settings"]["topic_id"] == "t"


@pytest.mark.parametrize(("count", "pills"), [(6, True), (7, False)])
def test_knowledge_point_is_pills_up_to_six_topics_and_a_selectbox_above(count, pills):
    course = calculus()
    scope = [topic.id for topic in course.topics][:count]
    names = {topic.id: topic.name for topic in course.topics}
    app = setup_app(scope, course)
    app.radio(key=f"practice_mode_{course.course_id}").set_value("Topic Practice").run()
    assert not app.exception
    key = f"practice_topic_{course.course_id}"
    groups = [group for group in app.button_group if group.key == key]
    boxes = [box for box in app.selectbox if box.key == key]
    assert (len(groups), len(boxes)) == ((1, 0) if pills else (0, 1))
    widget = groups[0] if pills else boxes[0]
    assert list(widget.options) == [names[topic_id] for topic_id in scope]
    assert widget.value == scope[0]  # the same value (a topic id) either way


def test_clicking_the_chosen_pill_off_keeps_the_choice():
    app = setup_app(["t", "other"])
    app.radio(key="practice_mode_insights").set_value("Topic Practice").run()
    app.button_group(key="practice_topic_insights").set_value("other").run()
    # What the browser sends when the chosen pill is clicked again.
    app.session_state["practice_topic_insights"] = None
    app.run()
    assert not app.exception
    assert app.button_group(key="practice_topic_insights").value == "other"


def test_change_settings_then_return_to_the_same_question_with_nothing_changed():
    app = practice_app()
    app.radio(key="answer_s_q0").set_value(1).run()
    next_question(app)
    app.button_group(key="confidence_s_q1").set_value("sure").run()
    active = app.session_state["active_practice_insights"]
    clock_keys = ("focus_timer", "focus_seconds", "session_seconds")
    before = {key: deepcopy(value) for key, value in active.items() if key not in clock_keys}
    app.button(key="practice_change_settings_s").click().run()
    assert not app.exception
    assert titles(app) == ["Practice"]
    assert app.radio(key="practice_mode_insights") and not badges(app)
    back = app.button(key="practice_return_previous")
    assert back.label == "Return to your session"
    # The setup screen pauses nothing.
    assert app.session_state["active_practice_insights"]["focus_timer"]["since"] is not None
    back.click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"] is active
    assert {key: value for key, value in active.items() if key not in clock_keys} == before
    assert badges(app) == ["Q02"] and app.button_group(key="confidence_s_q1").value == "sure"
    previous_question(app)
    assert app.radio(key="answer_s_q0").value == 1


def test_return_to_your_session_only_while_a_session_is_in_progress():
    assert not keys_starting(setup_app(["t"]), "practice_return_previous")
    app, _ = start_app(graded=True)
    open_setup(app)  # "New practice" on the result screen
    assert titles(app) == ["Practice"]
    assert not [button for button in app.button if button.label == "Return to your session"]


# 9 · Existing flows ------------------------------------------------------------------------------

@pytest.mark.parametrize(("topic_id", "notice"), [
    ("t", "New practice: Topic"), (None, "New practice for your confirmed topics."),
])
def test_pending_entry_from_another_page_opens_the_setup_screen(topic_id, notice):
    app = practice_app()
    app.radio(key="answer_s_q0").set_value(1).run()
    app.session_state["practice_entry_insights"] = {"topic_id": topic_id}
    if topic_id:  # what stage_practice does on the other page
        app.session_state["practice_mode_insights"] = "Topic Practice"
        app.session_state["practice_topic_insights"] = topic_id
    app.run()
    assert not app.exception
    assert [info.value for info in app.info] == [notice]
    assert app.button(key="practice_return_previous").label == "Return to your session"
    assert not badges(app)
    app.button(key="practice_start_insights").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["session"].session_id != "s" and active["session"].mode == ("topic" if topic_id else "mock")
    assert "practice_entry_insights" not in app.session_state
    assert badges(app) == ["Q01"] and keys_starting(app, "worksheet_next_")
    draft = app.session_state["practice_drafts_insights"]["s"]
    assert draft["_draft_widgets"]["answer_s_q0"] == 1


def test_resuming_lands_on_the_saved_question_with_the_review_step_closed(monkeypatch):
    monkeypatch.setattr(st, "switch_page", lambda page: None)  # Practice history then opens Practice
    app = practice_app()
    app.radio(key="answer_s_q0").set_value(2).run()
    next_question(app)
    app.radio(key="answer_s_q1").set_value(3).run()
    open_review(app)
    # Another page asks for a new practice while the review step is open.
    app.session_state["practice_entry_insights"] = {"topic_id": None}
    app.run()
    app.button(key="practice_start_insights").click().run()
    history = carry_to(app, HISTORY_PAGE_PATH)
    assert history_rows(history) == [("1 · Topic practice · 3 questions · Unfinished", "Resume")]
    history.button(key="practice_history_resume_s").click().run()
    assert not history.exception
    app = carry_to(history, PAGE)
    active = app.session_state["active_practice_insights"]
    assert active["session"].session_id == "s" and "worksheet_step" not in active
    assert badges(app) == ["Q02"] and app.radio(key="answer_s_q1").value == 3
    # The archived clock was stopped; it now points at the question on screen.
    assert active["focus_timer"] == {"question_id": "q1", "since": None}
    previous_question(app)
    assert app.radio(key="answer_s_q0").value == 2


def test_reopening_a_saved_result_shows_the_result_screen(monkeypatch):
    monkeypatch.setattr(st, "switch_page", lambda page: None)  # Practice history then opens Practice
    app, _ = start_app(graded=True)
    open_setup(app)
    history = carry_to(app, HISTORY_PAGE_PATH)
    history.button(key="practice_history_open_s").click().run()
    assert not history.exception
    app = carry_to(history, PAGE)
    assert not app.exception
    assert "Your result" in subheaders(app) and titles(app) == ["Practice"]
    assert not [radio for radio in app.radio if (radio.key or "").startswith("practice_mode_")]


def test_practising_missed_questions_lands_on_the_new_question_screen():
    app, _ = start_app(graded=True, picks=(1, 1))
    app.button(key="review_mistakes_s").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["session"].session_id != "s" and "result" not in active
    assert "Your result" not in subheaders(app)
    # "All missed topics" is recorded as a Mock Exam.
    assert active["session"].mode == "mock"
    assert titles(app) == ["Practice · Mock Exam"] and badges(app) == ["Q01"]
    assert keys_starting(app, "worksheet_next_")


@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_the_clock_and_its_pause_are_in_the_header_of_every_question(mode):
    app = practice_app(mode)
    for _ in range(3):
        clock = find_block(app, "flight_progress_clock")
        assert [button.key for button in clock.button] == ["focus_pause_s"]
        if keys_starting(app, "worksheet_next_"):
            next_question(app)
    app.button(key="focus_pause_s").click().run()
    assert app.session_state["active_practice_insights"]["focus_timer"]["since"] is None
    assert app.button(key="focus_pause_s").label == "Resume"


# 10 · The focus timer follows the question on screen ----------------------------------------------

def test_focus_timer_follows_the_question_on_screen_without_a_button():
    app = practice_app()
    timer = lambda: app.session_state["active_practice_insights"]["focus_timer"]  # noqa: E731
    assert timer()["question_id"] == "q0" and timer()["since"] is not None
    next_question(app)
    assert timer()["question_id"] == "q1" and timer()["since"] is not None
    next_question(app)
    previous_question(app)
    assert timer()["question_id"] == "q1"
    assert set(app.session_state["active_practice_insights"]["focus_seconds"]) == {"q0", "q1", "q2"}


def test_first_render_of_a_resumed_session_tracks_the_question_shown():
    # A running timer on another question moves to the one on screen (time so far stays with q0).
    app = practice_app(active={"worksheet_index": 2, "session_seconds": 0.0, "focus_seconds": {},
                               "focus_timer": {"question_id": "q0", "since": time.monotonic() - 5}})
    active = app.session_state["active_practice_insights"]
    assert badges(app) == ["Q03"]
    assert active["focus_timer"]["question_id"] == "q2" and active["focus_timer"]["since"] is not None
    assert active["focus_seconds"]["q0"] == pytest.approx(5, abs=1)
    # A paused timer only changes its question.
    app = practice_app(active={"worksheet_index": 1, "focus_timer": {"question_id": "q0", "since": None}})
    assert app.session_state["active_practice_insights"]["focus_timer"] == {"question_id": "q1", "since": None}
    # No timer yet: it starts on the question shown.
    app = practice_app(active={"worksheet_index": 2})
    timer = app.session_state["active_practice_insights"]["focus_timer"]
    assert timer["question_id"] == "q2" and timer["since"] is not None


# 11 · The page turn -------------------------------------------------------------------------------

def test_page_turn_plays_only_when_the_question_changes():
    course = setup_course()
    course.questions[0].hints = ["Compare both values.", "Check the units."]
    app = practice_app(course=course)
    assert turn_key(app) == "practice_turn_none_s"  # arrival
    next_question(app)
    first = turn_key(app)
    assert re.fullmatch(r"practice_turn_next_[ab]_s", first)
    next_question(app)
    second = turn_key(app)
    assert re.fullmatch(r"practice_turn_next_[ab]_s", second) and second != first  # a, then b
    previous_question(app)
    assert re.fullmatch(r"practice_turn_prev_[ab]_s", turn_key(app))
    previous_question(app)
    # Answering, confidence, a hint and the clock keep the question: no turn.
    app.radio(key="answer_s_q0").set_value(1).run()
    assert turn_key(app) == "practice_turn_none_s"
    previous_question(app)  # a late click on the first question
    assert turn_key(app) == "practice_turn_none_s"
    next_question(app)
    app.button_group(key="confidence_s_q1").set_value("sure").run()
    assert turn_key(app) == "practice_turn_none_s"
    previous_question(app)
    app.button(key="hint_button_s_q0").click().run()
    assert turn_key(app) == "practice_turn_none_s"
    app.button(key="focus_pause_s").click().run()
    assert turn_key(app) == "practice_turn_none_s"
    open_review(app)
    app.button(key="worksheet_back_s").click().run()
    assert turn_key(app) == "practice_turn_none_s"
    # The card sits inside the turning container.
    turning = find_block(app, "practice_turn_none_s")
    assert any("paper-question-badge" in m.value for m in turning.markdown)


def test_page_turn_is_css_only_with_identical_a_and_b_keyframes():
    css = CSS.read_text(encoding="utf-8")
    for move in ("next", "prev"):
        bodies = [re.search(rf"@keyframes practice-turn-{move}-{ab} \{{\n(.*?)\n\}}", css, re.DOTALL).group(1)
                  for ab in "ab"]
        assert bodies[0] == bodies[1]
        for ab in "ab":
            rule = re.search(rf'\[class\*="st-key-practice_turn_{move}_{ab}_"\] \{{(.*?)\}}', css, re.DOTALL).group(1)
            assert f"animation: practice-turn-{move}-{ab} " in rule
    assert "st-key-practice_turn_none_" not in css  # "none" has no animation
    reduced = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    assert re.match(r'@media \(prefers-reduced-motion: reduce\) \{\s*\[data-testid="stMain"\] '
                    r'\[class\*="st-key-practice_turn_"\] \{\s*animation: none !important;', reduced)
    source = PAGE.read_text(encoding="utf-8")
    for banned in ("<script", "st.html(", "components.html", "setTimeout"):
        assert banned not in source


# 12 · Chinese interface ----------------------------------------------------------------------------

def chinese_course():
    questions = [
        Question(id=f"z{n}", topic_id="zt", question=f"第 {n + 1} 道：抛物线的顶点在哪里？",
                 options=["甲", "乙", "丙", "丁"], correct_index=0, explanation="顶点在对称轴上。",
                 hints=["先找对称轴。", "再代入求值。"])
        for n in range(3)
    ]
    return StudyPackage(course_id="zh-course", course_name="函数", topics=[
        {"id": "zt", "name": "二次函数", "summary": "二次函数的图像是抛物线。"},
    ], relationships=[], questions=questions)


def shown_strings(app):
    """Every interface string on the page. Radio options are left out: their A-D letters
    label the course's own options."""
    values = titles(app) + [re.sub(r"<[^>]+>", " ", value) for value in page_markdown(app)]
    for kind in ("caption", "info", "warning", "error", "success", "subheader"):
        values += [item.value for item in app.get(kind)]
    values += [expander.label for expander in app.expander] + popover_labels(app)
    for button in app.button:
        values += [button.label, button.help or ""]
    values += [radio.label for radio in app.radio]
    for group in app.button_group:
        values += [group.label, *group.options]
    for frame in app.dataframe:
        values += [str(column) for column in frame.value.columns]
        values += [str(cell) for cell in frame.value.to_numpy().ravel()]
    return values


@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_question_screen_and_review_step_are_fully_chinese(mode):
    course = chinese_course()
    app = practice_app(mode, ("z0", "z1", "z2"), course=course, extra={LANGUAGE_KEY: True})
    assert not app.exception
    assert titles(app) == ["练习 · 二次函数" if mode == "topic" else "练习 · 模拟考试"]
    if mode == "topic":
        app.button(key="hint_button_s_z0").click().run()
        assert "提示 1 / 2：先找对称轴。" in [info.value for info in app.info]
    shown = shown_strings(app)
    assert counter(app) == ["题目 01 / 03"]
    assert [value for value in shown if re.search(r"[A-Za-z]", value)] == []
    labels = {button.key: button.label for button in app.button}
    assert labels["worksheet_review_s"] == "检查并交卷" and labels["practice_change_settings_s"] == "修改设置"
    assert popover_labels(app)[0] == "本次练习"
    if mode == "topic":
        assert labels["practice_side_panel_toggle_zh-course"] == "收起右栏"
        app.button(key="practice_side_panel_toggle_zh-course").click().run()
        assert app.button(key="practice_side_panel_toggle_zh-course").label == "展开右栏"
    app.radio(key="answer_s_z0").set_value(0).run()
    next_question(app)
    next_question(app)
    assert app.button(key="worksheet_finish_s").label == "完成"
    assert not [value for value in shown_strings(app) if re.search(r"[A-Za-z]", value)]
    app.button(key="worksheet_finish_s").click().run()
    assert titles(app) == ["练习 · 检查"]
    assert "已作答 1 / 3" in page_markdown(app)
    assert {button.label for button in app.button} == {"返回题目", "提交答案"}
    assert "可以返回题目修改这些答案，也可以按现在的答案提交。" in [c.value for c in app.caption]
    assert [value for value in shown_strings(app) if re.search(r"[A-Za-z]", value)] == []


def test_setup_and_result_screen_labels_are_translated():
    app, _ = start_app(graded=True)
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    assert app.button(key="practice_new_insights").label == "新的练习"
    app = practice_app(extra={LANGUAGE_KEY: True})
    app.button(key="practice_change_settings_s").click().run()
    assert app.button(key="practice_return_previous").label == "回到当前练习"


# 13 · Layout rules -------------------------------------------------------------------------------

def test_layout_rules_for_the_title_row_the_floating_button_and_phones():
    css = CSS.read_text(encoding="utf-8")
    tools = re.search(r'\.st-key-practice_title_row > \[data-testid="stLayoutWrapper"\]'
                      r':has\(> \.st-key-practice_title_tools\) \{(.*?)\}', css, re.DOTALL).group(1)
    assert "margin-left: auto;" in tools and "flex: 0 0 auto;" in tools
    title = re.search(r'\.st-key-practice_title_row > \[data-testid="stElementContainer"\] \{(.*?)\}',
                      css, re.DOTALL).group(1)
    assert "min-width: 0;" in title
    clear = re.search(r'\.st-key-practice_main_full \[class\*="st-key-paper_actions_"\],\n'
                      r'\[data-testid="stMain"\] \.st-key-practice_review_actions,\n(?:[^{]*,\n)*[^{]*\{(.*?)\}',
                      css, re.DOTALL).group(1)
    assert "padding-right: 5rem;" in clear and "box-sizing: border-box;" in clear
    # Below 760px the side panel stacks under the question (the shared worksheet rule).
    academic = (ROOT / "assets" / "academic_ui.css").read_text(encoding="utf-8")
    assert re.search(r'@media \(max-width: 760px\) \{\s*\[data-testid="stHorizontalBlock"\]'
                     r':has\(\.st-key-flight_worksheet_margin\) \{\s*flex-direction: column;', academic)
    # Without the panel, the actions row sits in the full-width container those rules name.
    app = practice_app("mock")
    assert "paper_actions_q0" in block_keys(app, find_block(app, "practice_main_full"))
    app = practice_app("topic")
    assert "paper_actions_q0" not in block_keys(app, find_block(app, "practice_title_row"))
    assert find_block(app, "practice_main_full") is None


# ---- What the browser is told when a question comes back on screen ------------------

@pytest.mark.parametrize("mode", ["topic", "mock"])
@pytest.mark.parametrize("reruns", [0, 1, 2, 3])
def test_the_browser_is_told_the_answer_when_a_question_comes_back_on_screen(mode, reruns):
    # A browser shows a widget's own default unless the run that draws it also
    # assigns its key, and the next click then saves "no answer" over the
    # student's answer. Whether an earlier run had already restored the value
    # depends on how many reruns happened in between, so each count is checked.
    app = practice_app(mode)
    app.radio(key="answer_s_q0").set_value(2).run()
    app.button_group(key="confidence_s_q0").set_value("unsure").run()
    next_question(app)
    for _ in range(reruns):
        app.run()
    previous_question(app)
    answer = app.radio(key="answer_s_q0")
    confidence = app.button_group(key="confidence_s_q0")
    assert answer.value == 2 and answer.proto.set_value
    assert confidence.value == "unsure" and confidence.proto.set_value
    # And it stays that way on the next run, with nothing clicked.
    app.run()
    assert app.radio(key="answer_s_q0").value == 2
    assert app.button_group(key="confidence_s_q0").value == "unsure"
