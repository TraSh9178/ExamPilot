"""Practice history and Review answers: the last collapsed blocks of the practice page,
each on a page of its own, plus the in-place reveal of a question's original wording."""
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest

from models.schemas import ExamSession, Question, StudyPackage
from services.accessibility import SIMPLIFY_KEY
from services.exam_engine import grade_exam
from services.i18n import LANGUAGE_KEY
from services.practice_insights import set_session_insights
from tests.auth_helpers import signed_in_app
from tests.test_paper_practice import badges, page_markdown
from tests.test_practice_clock import find_block
from tests.test_practice_focus import block_keys, practice_app, shown_strings, subheaders, titles, turn_key
from tests.test_practice_insights import setup_course, start_app
from tests.test_practice_page import carry_to, history_rows, open_review, open_setup

ROOT = Path(__file__).resolve().parents[1]
PRACTICE = ROOT / "pages" / "2_Practice_Center.py"
HISTORY = ROOT / "pages" / "8_Practice_History.py"
REVIEW = ROOT / "pages" / "13_Answer_Review.py"
CSS = ROOT / "assets" / "paper_practice.css"
LEFT = BlockProto.FlexContainer.Justify.JUSTIFY_START


def record(course, sid, picks, mode="topic"):
    """A graded session as the practice page saves it in the history."""
    questions = course.questions[:len(picks)]
    session = ExamSession(session_id=sid, mode=mode, question_ids=[q.id for q in questions])
    result = grade_exam(session, questions, {q.id: pick for q, pick in zip(questions, picks)})
    return {"session": session, "questions": questions, "attempts": result["attempts"], "result": result}


def draft(course, sid, count, **extra):
    """An unfinished session as install_practice archives it."""
    questions = course.questions[:count]
    session = ExamSession(session_id=sid, mode="topic", question_ids=[q.id for q in questions])
    return {"session": session, "questions": questions, "warning": None, "settings": {}, **extra}


def page_app(path, course=None, extra=None, scope=("t",)):
    course = course or setup_course()
    app = AppTest.from_file(str(path))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = list(scope)
    for key, value in (extra or {}).items():
        app.session_state[key] = value
    return app.run()


def keyed(app, key):
    """The container with this key."""
    block = find_block(app, key)
    assert block is not None, key
    return block


def capture_switches(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    return destinations


# 1 · The setup screen: one small button instead of two expanders -------------------------

def test_setup_screen_has_no_expanders_and_one_history_button_only_when_there_are_sessions():
    course = setup_course()
    app = page_app(PRACTICE, course)
    assert titles(app) == ["Practice"]
    assert not app.expander and not app.selectbox
    assert not [b for b in app.button if b.key == "open_practice_history"]

    for extra in ({"practice_history_insights": {"h": record(course, "h", (0, 1))}},
                  {"practice_drafts_insights": {"d": draft(course, "d", 2)}}):
        app = page_app(PRACTICE, course, extra)
        assert not app.exception
        assert not app.expander and not app.selectbox
        assert [b.key for b in app.button if b.label == "Practice history"] == ["open_practice_history"]
        button = app.button(key="open_practice_history")
        assert button.proto.icon == ":material/history:"
        keys = block_keys(app)
        # Under the setup card, on the right edge.
        assert keys.index("practice_setup") < keys.index("page_link_open_practice_history")
        assert keyed(app, "page_link_open_practice_history").proto.flex_container.justify == (
            BlockProto.FlexContainer.Justify.JUSTIFY_END)


# 2 & 4 · The Practice history page ------------------------------------------------------------

def test_history_lists_every_session_directly_newest_first_with_one_button_each():
    course = setup_course()
    app = page_app(HISTORY, course, {
        "practice_drafts_insights": {"d1": draft(course, "d1", 2), "d2": draft(course, "d2", 1)},
        "practice_history_insights": {"h1": record(course, "h1", (0, 1)), "h2": record(course, "h2", (0,))},
    })
    assert not app.exception
    assert titles(app) == ["Practice history"]
    assert subheaders(app) == ["Unfinished sessions", "Finished sessions"]
    assert history_rows(app) == [
        ("2 · Topic practice · 1 question · Unfinished", "Resume"),
        ("1 · Topic practice · 2 questions · Unfinished", "Resume"),
        ("2 · Topic practice · 1 question · 1/1 correct", "Open result"),
        ("1 · Topic practice · 2 questions · 1/2 correct", "Open result"),
    ]
    # Nothing to unfold or pick from.
    assert not app.expander and not app.selectbox and not app.tabs and not app.radio
    assert not app.get("button_group")
    # The way back: first, small, on the left.
    keys = block_keys(app)
    assert keys[0] == "page_link_practice_history_back"
    assert keyed(app, "page_link_practice_history_back").proto.flex_container.justify == LEFT
    back = app.button(key="practice_history_back")
    assert (back.label, back.proto.icon) == ("Back to Practice", ":material/arrow_back:")


@pytest.mark.parametrize(("drafts", "history", "sections"), [
    (True, False, ["Unfinished sessions"]),
    (False, True, ["Finished sessions"]),
])
def test_history_shows_a_section_only_when_it_has_rows(drafts, history, sections):
    course = setup_course()
    extra = {}
    if drafts:
        extra["practice_drafts_insights"] = {"d": draft(course, "d", 2)}
    if history:
        extra["practice_history_insights"] = {"h": record(course, "h", (0, 1))}
    app = page_app(HISTORY, course, extra)
    assert subheaders(app) == sections and len(history_rows(app)) == 1


def test_history_empty_state_and_no_course(monkeypatch):
    app = page_app(HISTORY)
    assert not app.exception
    assert [caption.value for caption in app.caption] == [
        "No practice sessions yet. Finished and unfinished sessions will appear here."]
    assert [button.label for button in app.button] == ["Back to Practice"]
    assert not history_rows(app) and not app.subheader
    links = []
    monkeypatch.setattr(st, "page_link", lambda page, **kwargs: links.append(page))
    app = AppTest.from_file(str(HISTORY)).run()
    assert not app.exception
    assert [info.value for info in app.info] == ["Load a course from the dashboard to start studying."]
    assert links == ["pages/0_Dashboard.py"]
    assert [button.label for button in app.button] == ["Back to Practice"]


# 3 · Resume and Open result -------------------------------------------------------------------

def test_resume_drops_pending_requests_and_lands_where_the_student_left_off(monkeypatch):
    destinations = capture_switches(monkeypatch)
    course = setup_course()
    saved = {"h": record(course, "h", (0, 1))}
    unfinished = draft(course, "d", 3, worksheet_index=1, worksheet_step="review",
                       _draft_widgets={"answer_d_q0": 2, "answer_d_q1": 3, "confidence_d_q1": "unsure"})
    in_progress = draft(course, "a", 2)
    app = page_app(HISTORY, course, {
        "practice_drafts_insights": {"d": unfinished},
        "practice_history_insights": saved,
        "active_practice_insights": in_progress,
        "practice_entry_insights": {"topic_id": None},  # a request from another page
        "practice_setup_insights": "a",  # and a "Change settings" request
    })
    before = deepcopy(saved)
    app.button(key="practice_history_resume_d").click().run()
    assert not app.exception
    assert destinations == ["pages/2_Practice_Center.py"]
    state = app.session_state
    active = state["active_practice_insights"]
    assert active["session"].session_id == "d" and "worksheet_step" not in active
    assert "practice_entry_insights" not in state and "practice_setup_insights" not in state
    assert state["practice_history_insights"] == before
    # The session that was open is kept as unfinished, as when any session replaces it.
    assert list(state["practice_drafts_insights"]) == ["a"]
    practice = carry_to(app, PRACTICE)
    assert titles(practice) == ["Practice · Topic"] and badges(practice) == ["Q02"]
    assert practice.radio(key="answer_d_q1").value == 3
    assert practice.button_group(key="confidence_d_q1").value == "unsure"
    practice.button(key="worksheet_previous_d").click().run()
    assert practice.radio(key="answer_d_q0").value == 2


def test_open_result_drops_pending_requests_and_shows_that_result(monkeypatch):
    destinations = capture_switches(monkeypatch)
    course = setup_course()
    saved = {"h1": record(course, "h1", (0, 1)), "h2": record(course, "h2", (1,))}
    drafts = {"d": draft(course, "d", 2)}
    app = page_app(HISTORY, course, {
        "practice_history_insights": saved, "practice_drafts_insights": drafts,
        "practice_entry_insights": {"topic_id": "t"},
    })
    before = deepcopy((saved, drafts))
    app.button(key="practice_history_open_h1").click().run()
    assert not app.exception
    assert destinations == ["pages/2_Practice_Center.py"]
    state = app.session_state
    assert state["active_practice_insights"]["session"].session_id == "h1"
    assert state["active_practice_insights"]["result"] == saved["h1"]["result"]
    assert "practice_entry_insights" not in state
    assert (state["practice_history_insights"], state["practice_drafts_insights"]) == before
    practice = carry_to(app, PRACTICE)
    assert "Your result" in subheaders(practice)
    assert [metric.value for metric in practice.metric][:1] == ["1 / 2"]


# 6 · The result screen: no tabs, next steps shown directly ------------------------------------

def test_result_screen_has_no_tabs_and_a_review_answers_button_under_the_score():
    app, _ = start_app(graded=True, picks=(1, 1))
    assert not app.exception
    assert not app.tabs and not app.get("tab_container")
    keys = block_keys(app)
    order = [keys.index(key) for key in (
        "practice_result_overview", "page_link_open_answer_review", "flight_next_topic",
        "practice_mistake_review",
    )]
    assert order == sorted(order)
    button = app.button(key="open_answer_review")
    assert (button.label, button.proto.icon) == ("Review answers", ":material/fact_check:")
    assert keyed(app, "page_link_open_answer_review").proto.flex_container.justify == (
        BlockProto.FlexContainer.Justify.JUSTIFY_END)
    # The summary, shown directly: next step, insights, review list, missed questions.
    assert "Take the next step" in [caption.value for caption in app.caption]
    assert "Practice insights" in subheaders(app)
    assert app.button(key="review_mistakes_s") and app.button(key="priorities_insights")
    # The per-question answers are not on this screen any more.
    assert not badges(app) and not app.text_area
    assert not [b for b in app.button if (b.key or "").startswith("transfer_")]


# 7 · The Review answers page ---------------------------------------------------------------------

def review_course():
    course = setup_course()
    course.questions[1].hints = ["Compare both values.", "Check the units."]
    course.questions[1].source_pages = [2]
    return set_session_insights(course, "s", {
        "q0": {"confidence": "sure", "hints_used": 0, "focus_seconds": 12.0},
        "q1": {"confidence": "guessed", "hints_used": 1, "focus_seconds": 42.4},
    })


def review_app(picks=(0, 1), course=None, extra=None):
    course = course or review_course()
    return page_app(REVIEW, course, {
        "active_practice_insights": {**record(course, "s", picks), "warning": None, "settings": {}},
        "course_document_insights": {"pages": [{"page": 2, "text": "Page two says compare both values."}]},
        **(extra or {}),
    })


def test_review_page_shows_one_question_with_everything_visible():
    app = review_app()
    assert not app.exception
    assert titles(app) == ["Review answers"]
    assert block_keys(app)[0] == "page_link_review_answers_back"
    assert keyed(app, "page_link_review_answers_back").proto.flex_container.justify == LEFT
    back = app.button(key="review_answers_back")
    assert (back.label, back.proto.icon) == ("Back to result", ":material/arrow_back:")
    assert "Question 01 / 02" in [caption.value for caption in app.caption]
    assert badges(app) == ["Q01"]
    assert [s.value for s in app.success] == ["✓ Your answer: A"]
    app.button(key="review_next_s").click().run()
    assert badges(app) == ["Q02"] and "Question 02 / 02" in [c.value for c in app.caption]
    # A missed question: everything about it is on the page, no expander and no tabs.
    assert not app.expander and not app.tabs
    assert subheaders(app) == ["Answer", "Explanation", "Reflect and explain your answer", "Source material"]
    assert [e.value for e in app.error] == ["✕ Your answer: B"]
    assert [s.value for s in app.success] == ["✓ Correct answer: A"]
    captions = [caption.value for caption in app.caption]
    assert "Hints used: 1 of 2" in captions and "Guessed · 1 hint · 42 s" in captions
    assert "Reason" in page_markdown(app)  # the explanation
    assert app.button_group(key="reason_s_q1") and app.text_area(key="explain_s_q1")
    assert app.button(key="transfer_s_q1").label == "Try a different structure"
    assert "Cited pages: 2" in captions and "Page / slide 2" in captions
    assert [text.value for text in app.text] == ["Page two says compare both values."]
    # The heading order reads top to bottom: answer, explanation, reflection, source.
    order = [subheader.value for subheader in app.subheader]
    assert order == ["Answer", "Explanation", "Reflect and explain your answer", "Source material"]


def test_review_page_shows_the_original_wording_of_a_simplified_question():
    package = StudyPackage.model_validate(json.loads(
        (ROOT / "data" / "sample_course.json").read_text(encoding="utf-8")))
    question = package.questions[0]
    session = ExamSession(session_id="simple", mode="mock", question_ids=[question.id])
    result = grade_exam(session, [question], {question.id: question.correct_index})
    app = page_app(REVIEW, package, {
        SIMPLIFY_KEY: True,
        f"active_practice_{package.course_id}": {
            "session": session, "questions": [question], "result": result, "warning": None, "settings": {}},
    }, scope=[question.topic_id])
    assert not app.exception
    assert "Simplified wording" in [caption.value for caption in app.caption]
    assert subheaders(app)[0] == "Original wording"
    markdown = page_markdown(app)
    assert question.question in markdown and all(option in markdown for option in question.options)
    assert not app.expander


# 8 · Previous / Next, the page turn and the remembered position ------------------------------------

def test_review_previous_next_turn_the_page_and_stay_in_range():
    app = review_app()
    previous, nxt = app.button(key="review_previous_s"), app.button(key="review_next_s")
    assert previous.disabled and not nxt.disabled and nxt.proto.type == "primary"
    assert turn_key(app) == "practice_turn_none_s"
    nxt.click().run()
    first = turn_key(app)
    assert re.fullmatch(r"practice_turn_next_[ab]_s", first)
    assert app.button(key="review_next_s").disabled
    app.button(key="review_next_s").click().run()  # a late click at the end
    assert not app.exception and badges(app) == ["Q02"]
    assert turn_key(app) == "practice_turn_none_s"
    # Any other rerun (here, saving a reflection) does not turn the page.
    app.text_area(key="explain_s_q1").set_value("I misread the values.")
    next(b for b in app.button if b.label == "Save reflection").click().run()
    assert turn_key(app) == "practice_turn_none_s" and badges(app) == ["Q02"]
    app.button(key="review_previous_s").click().run()
    assert re.fullmatch(r"practice_turn_prev_[ab]_s", turn_key(app)) and turn_key(app)[-3] != first[-3]
    assert badges(app) == ["Q01"]


def test_review_position_is_remembered_per_session():
    course = review_course()
    app = review_app(course=course)
    app.button(key="review_next_s").click().run()
    assert badges(app) == ["Q02"]
    app.run()
    assert badges(app) == ["Q02"]
    # Another result starts at question 1; the first one keeps its place.
    app.session_state["active_practice_insights"] = {**record(course, "other", (1, 1)), "warning": None, "settings": {}}
    app.run()
    assert badges(app) == ["Q01"] and app.button(key="review_previous_other").disabled
    app.session_state["active_practice_insights"] = {**record(course, "s", (0, 1)), "warning": None, "settings": {}}
    app.run()
    assert badges(app) == ["Q02"]


# 9 · Reflection without an expander; "Try a different structure"; nothing open ------------------------

def test_reflection_is_shown_directly_and_saves_as_before():
    app = review_app()
    app.button(key="review_next_s").click().run()
    assert not app.expander
    assert "Reflect and explain your answer" in subheaders(app)
    assert ("Write your reasoning in your own words. This reflection is after feedback and never changes your score."
            in [caption.value for caption in app.caption])
    app.button_group(key="reason_s_q1").set_value("misread")
    app.text_area(key="explain_s_q1").set_value("I read B as A.")
    next(b for b in app.button if b.label == "Save reflection").click().run()
    assert not app.exception
    row = app.session_state["current_course"].learning_state["practice_insights"]["s"]["q1"]
    assert (row["mistake_reason"], row["explanation"]) == ("misread", "I read B as A.")
    assert "Saved." in [success.value for success in app.success]


def test_try_a_different_structure_goes_to_the_new_session(monkeypatch):
    destinations = capture_switches(monkeypatch)
    app = review_app(picks=(1, 0), course=setup_course())
    app.button(key="transfer_s_q0").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert "result" not in active and active["session"].question_ids == ["q2"]
    assert destinations == ["pages/2_Practice_Center.py"]
    practice = carry_to(app, PRACTICE)
    assert badges(practice) == ["Q01"] and practice.radio(key=f"answer_{active['session'].session_id}_q2")


def test_review_page_without_an_open_result():
    app = page_app(REVIEW)
    assert not app.exception
    assert [caption.value for caption in app.caption] == ["No result to review yet. Finish a practice session first."]
    assert [button.label for button in app.button] == ["Back to result"]
    assert not badges(app)


# 10 & 3 · Through the registered app: both hidden pages open and return --------------------------------

PRACTICE_PATH = "pages/2_Practice_Center.py"
HISTORY_PATH = "pages/8_Practice_History.py"
REVIEW_PATH = "pages/13_Answer_Review.py"
# Plain session values a student's session keeps between pages (widgets belong to their page).
CARRIED = ("current_course", "confirmed_scope_{cid}", "active_practice_{cid}", "practice_history_{cid}",
           "practice_drafts_{cid}", "practice_entry_{cid}", "practice_setup_{cid}",
           "practice_history_visited_{cid}", "practice_side_panel_{cid}", "review_position_{cid}",
           "practice_choice_{cid}", "practice_screen_{cid}", "_learning_page_path")


def registered_practice(state):
    app = signed_in_app(ROOT / "app.py").run()
    for key, value in state.items():
        app.session_state[key] = value
    app.switch_page(PRACTICE_PATH).run()
    assert not app.exception
    return app


def next_leg(app, page):
    """Continue after a button opened another page.

    In AppTest a page switch made by the script lasts one run: the next run starts on
    the old page again, with the old page's nodes still in the tree. So every switch ends
    a runner, and the next leg is a clean runner with the same session state, on the page
    the click opened.
    """
    cid = app.session_state["current_course"].course_id
    fresh = signed_in_app(ROOT / "app.py").run()
    for key in CARRIED:
        key = key.format(cid=cid)
        if key in app.session_state:
            fresh.session_state[key] = app.session_state[key]
    fresh.switch_page(page).run()
    assert not fresh.exception
    return fresh


def test_review_answers_opens_from_the_result_and_returns_to_the_same_result():
    course = setup_course()
    saved = record(course, "s", (0, 1))
    app = registered_practice({
        "current_course": course, "confirmed_scope_insights": ["t"],
        "active_practice_insights": {**saved, "warning": None, "settings": {}},
        "practice_history_insights": {"s": saved},
    })
    assert "Your result" in subheaders(app)
    app.button(key="open_answer_review").click().run()
    assert not app.exception
    assert "Review answers" in titles(app) and badges(app) == ["Q01"]
    assert app.session_state["_learning_page_path"] == "Answer_Review"
    app = next_leg(app, REVIEW_PATH)
    app.button(key="review_next_s").click().run()
    assert badges(app) == ["Q02"]
    app.button(key="review_answers_back").click().run()
    assert not app.exception
    assert app.session_state["_learning_page_path"] == "Practice_Center"
    # The same result, not the setup screen.
    assert "Practice" in titles(app) and "Your result" in subheaders(app)
    assert not [radio for radio in app.radio if (radio.key or "").startswith("practice_mode_")]
    assert app.session_state["active_practice_insights"]["session"].session_id == "s"
    # Coming back to the answers keeps the place.
    app = next_leg(app, PRACTICE_PATH)
    app.button(key="open_answer_review").click().run()
    assert badges(app) == ["Q02"]


def test_practice_history_opens_from_setup_returns_to_it_and_resumes_or_opens():
    course = setup_course()
    saved = record(course, "h", (0, 1))
    app = registered_practice({
        "current_course": course, "confirmed_scope_insights": ["t"],
        "active_practice_insights": draft(course, "a", 2),
        "practice_drafts_insights": {"d": draft(course, "d", 2, worksheet_index=1,
                                                _draft_widgets={"answer_d_q1": 2})},
        "practice_history_insights": {"h": saved},
    })
    app.button(key="practice_change_settings_a").click().run()
    app.button(key="open_practice_history").click().run()
    assert not app.exception
    assert "Practice history" in titles(app)
    assert app.session_state["_learning_page_path"] == "Practice_History"
    app = next_leg(app, HISTORY_PATH)
    # Back to Practice returns to the setup screen it was opened from.
    app.button(key="practice_history_back").click().run()
    assert not app.exception
    assert app.session_state["_learning_page_path"] == "Practice_Center"
    assert app.radio(key="practice_mode_insights") and app.button(key="open_practice_history")
    app = next_leg(app, PRACTICE_PATH)
    app.button(key="open_practice_history").click().run()
    app = next_leg(app, HISTORY_PATH)
    app.button(key="practice_history_resume_d").click().run()
    assert not app.exception
    assert "Practice · Topic" in titles(app) and badges(app) == ["Q02"]
    assert app.radio(key="answer_d_q1").value == 2
    # Open result works the same way.
    app = next_leg(app, PRACTICE_PATH)
    app.button(key="practice_change_settings_d").click().run()
    app.button(key="open_practice_history").click().run()
    app = next_leg(app, HISTORY_PATH)
    app.button(key="practice_history_open_h").click().run()
    assert not app.exception
    assert "Your result" in subheaders(app)
    assert app.session_state["active_practice_insights"]["session"].session_id == "h"
    # Both sessions that were open on the way are kept as unfinished.
    assert set(app.session_state["practice_drafts_insights"]) == {"a", "d"}


def test_history_works_while_a_request_from_another_page_is_pending():
    course = setup_course()
    app = registered_practice({
        "current_course": course, "confirmed_scope_insights": ["t"],
        "practice_drafts_insights": {"d": draft(course, "d", 2)},
        "practice_entry_insights": {"topic_id": "t"},
    })
    assert "New practice: Topic" in [info.value for info in app.info]
    app.button(key="open_practice_history").click().run()
    app = next_leg(app, HISTORY_PATH)
    app.button(key="practice_history_resume_d").click().run()
    assert not app.exception
    assert "practice_entry_insights" not in app.session_state
    assert badges(app) == ["Q01"] and "Practice · Topic" in titles(app)


# R1 · Opening a result or another session keeps the open session ---------------------------

def answer_two_questions(app, sid):
    """Answers on question 1 (with confidence) and 2; question 2 stays on screen."""
    app.radio(key=f"answer_{sid}_q0").set_value(2).run()
    app.button_group(key=f"confidence_{sid}_q0").set_value("unsure").run()
    app.button(key=f"worksheet_next_{sid}").click().run()
    app.radio(key=f"answer_{sid}_q1").set_value(1).run()
    return app


def assert_answers_intact(app, sid):
    assert badges(app) == ["Q02"] and app.radio(key=f"answer_{sid}_q1").value == 1
    app.button(key=f"worksheet_previous_{sid}").click().run()
    assert app.radio(key=f"answer_{sid}_q0").value == 2
    assert app.button_group(key=f"confidence_{sid}_q0").value == "unsure"


def open_history_from(app, sid):
    app.button(key=f"practice_change_settings_{sid}").click().run()
    app.button(key="open_practice_history").click().run()
    return next_leg(app, HISTORY_PATH)


def test_opening_a_result_keeps_the_session_in_progress_as_unfinished():
    course = setup_course()
    saved = record(course, "h", (0, 1))
    app = registered_practice({
        "current_course": course, "confirmed_scope_insights": ["t"],
        "active_practice_insights": draft(course, "a", 3),
        "practice_history_insights": {"h": saved},
    })
    answer_two_questions(app, "a")
    app = open_history_from(app, "a")
    app.button(key="practice_history_open_h").click().run()
    assert "Your result" in subheaders(app)
    # The session that was open is listed as unfinished, with its answers.
    app = next_leg(app, HISTORY_PATH)
    assert ("1 · Topic practice · 3 questions · Unfinished", "Resume") in history_rows(app)
    app.button(key="practice_history_resume_a").click().run()
    app = next_leg(app, PRACTICE_PATH)
    assert_answers_intact(app, "a")


def test_resuming_another_session_keeps_the_session_in_progress_as_unfinished():
    course = setup_course()
    app = registered_practice({
        "current_course": course, "confirmed_scope_insights": ["t"],
        "active_practice_insights": draft(course, "a", 3),
        "practice_drafts_insights": {"d": draft(course, "d", 2)},
    })
    answer_two_questions(app, "a")
    app = open_history_from(app, "a")
    app.button(key="practice_history_resume_d").click().run()
    assert badges(app) == ["Q01"]
    assert app.session_state["active_practice_insights"]["session"].session_id == "d"
    app = next_leg(app, PRACTICE_PATH)
    app = open_history_from(app, "d")
    # The session that was open is the unfinished one now.
    assert history_rows(app) == [("1 · Topic practice · 3 questions · Unfinished", "Resume")]
    app.button(key="practice_history_resume_a").click().run()
    app = next_leg(app, PRACTICE_PATH)
    assert_answers_intact(app, "a")


# 11 · Original wording on the question screen ----------------------------------------------------------

def simplified_question_app():
    package = StudyPackage.model_validate(json.loads(
        (ROOT / "data" / "sample_course.json").read_text(encoding="utf-8")))
    questions = package.questions[:2]
    session = ExamSession(session_id="simple", mode="topic", question_ids=[q.id for q in questions])
    app = page_app(PRACTICE, package, {
        SIMPLIFY_KEY: True,
        f"active_practice_{package.course_id}": {
            "session": session, "questions": questions, "warning": None, "settings": {}},
    }, scope=sorted({q.topic_id for q in questions}))
    return app, questions[0]


def test_original_wording_is_revealed_in_place_by_one_quiet_button():
    app, question = simplified_question_app()
    assert not app.exception and not app.expander
    toggle_key = f"original_wording_toggle_simple_{question.id}"
    toggle = app.button(key=toggle_key)
    assert (toggle.label, toggle.proto.type) == ("Show original wording", "tertiary")
    assert keyed(app, f"original_wording_row_{question.id}").proto.flex_container.justify == LEFT
    # Not on the page before the click.
    assert question.question not in page_markdown(app)
    answer_key = f"answer_simple_{question.id}"
    app.radio(key=answer_key).set_value(1).run()
    app.button(key=toggle_key).click().run()
    assert not app.exception
    assert question.question in page_markdown(app)
    assert all(option in page_markdown(app) for option in question.options)
    assert app.button(key=toggle_key).label == "Hide original wording"
    # No page turn, and the chosen answer stays selected.
    assert turn_key(app) == "practice_turn_none_simple"
    assert app.radio(key=answer_key).value == 1
    app.button(key=toggle_key).click().run()
    assert question.question not in page_markdown(app)
    assert app.button(key=toggle_key).label == "Show original wording"


def test_original_wording_choice_is_kept_per_question():
    app, question = simplified_question_app()
    app.button(key=f"original_wording_toggle_simple_{question.id}").click().run()
    app.button(key="worksheet_next_simple").click().run()
    second = app.session_state["active_practice_econ101"]["questions"][1]
    toggles = [b for b in app.button if (b.key or "").startswith("original_wording_toggle_")]
    assert all(b.label == "Show original wording" for b in toggles)
    assert second.question not in page_markdown(app)
    app.button(key="worksheet_previous_simple").click().run()
    assert question.question in page_markdown(app)


# 12 · Chinese interface on both pages ---------------------------------------------------------------------

def chinese_course():
    questions = [
        Question(id=f"z{n}", topic_id="zt", question=f"第 {n + 1} 道：抛物线的顶点在哪里？",
                 options=["甲", "乙", "丙", "丁"], correct_index=0, explanation="顶点在对称轴上。",
                 hints=["先找对称轴。", "再代入求值。"], source_pages=[1])
        for n in range(2)
    ]
    course = StudyPackage(course_id="zh-course", course_name="函数", topics=[
        {"id": "zt", "name": "二次函数", "summary": "二次函数的图像是抛物线。"},
    ], relationships=[], questions=questions)
    return set_session_insights(course, "zs", {"z1": {"confidence": "guessed", "hints_used": 1, "focus_seconds": 5.0}})


def latin(app):
    # "AI" is part of the Chinese wording of the AI check, as elsewhere in the app.
    return [value for value in shown_strings(app) if re.search(r"[A-Za-z]", value.replace("AI", ""))]


def test_both_pages_are_fully_chinese_with_the_chinese_interface():
    course = chinese_course()
    session = ExamSession(session_id="zs", mode="topic", question_ids=["z0", "z1"])
    result = grade_exam(session, course.questions, {"z0": 0, "z1": 1})
    saved = {"session": session, "questions": course.questions, "attempts": result["attempts"], "result": result}
    unfinished = {"session": ExamSession(session_id="zd", mode="mock", question_ids=["z0"]),
                  "questions": course.questions[:1], "warning": None, "settings": {}}
    state = {
        LANGUAGE_KEY: True,
        "practice_history_zh-course": {"zs": saved},
        "practice_drafts_zh-course": {"zd": unfinished},
        "active_practice_zh-course": {**saved, "warning": None, "settings": {}},
        "course_document_zh-course": {"pages": [{"page": 1, "text": "第一页：顶点。"}]},
    }
    history = page_app(HISTORY, course, state, scope=["zt"])
    assert titles(history) == ["练习记录"]
    assert history_rows(history) == [("1 · 模拟考试 · 1 道题 · 未完成", "继续"), ("1 · 知识点练习 · 2 道题 · 答对 1/2", "查看成绩")]
    assert latin(history) == []
    review = page_app(REVIEW, course, state, scope=["zt"])
    assert titles(review) == ["查看答案"]
    assert latin(review) == []
    review.button(key="review_next_zs").click().run()
    assert "已使用提示：1 / 2" in [caption.value for caption in review.caption]
    assert latin(review) == []
    empty = page_app(HISTORY, course, {LANGUAGE_KEY: True}, scope=["zt"])
    assert latin(empty) == [] and empty.caption
    nothing = page_app(REVIEW, course, {LANGUAGE_KEY: True}, scope=["zt"])
    assert latin(nothing) == [] and nothing.caption


def test_new_labels_on_the_practice_page_are_translated():
    app, question = simplified_question_app()
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    toggle_key = f"original_wording_toggle_simple_{question.id}"
    assert app.button(key=toggle_key).label == "查看原始表述"
    app.button(key=toggle_key).click().run()
    assert app.button(key=toggle_key).label == "收起原始表述"
    app, _ = start_app(graded=True)
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    assert app.button(key="open_answer_review").label == "查看答案"
    open_setup(app)
    assert app.button(key="open_practice_history").label == "练习记录"


# 375px: rows and buttons wrap, the right end stays clear of the floating button -----------------------------

def test_phone_width_rules_for_the_two_pages():
    css = CSS.read_text(encoding="utf-8")
    clear = re.search(r"([^{}]*)\{\s*box-sizing: border-box;\s*padding-right: 5rem;", css).group(1)
    assert ".st-key-review_nav" in clear and '[class*="st-key-practice_history_row_"]' in clear
    row = re.search(r'\[class\*="st-key-practice_history_row_"\] > \[data-testid="stElementContainer"\]'
                    r':has\(\[data-testid="stMarkdown"\]\) \{(.*?)\}', css, re.DOTALL).group(1)
    assert "min-width: 0;" in row and "flex: 1 1 12rem;" in row
    app = page_app(HISTORY, extra={"practice_history_insights": {"h": record(setup_course(), "h", (0, 1))}})
    row_block = keyed(app, "practice_history_row_h")
    assert row_block.proto.flex_container.direction == BlockProto.FlexContainer.Direction.HORIZONTAL
    assert row_block.proto.flex_container.wrap
    nav = keyed(review_app(), "review_nav")
    assert nav.proto.flex_container.wrap


# R2 · The setup screen shows what Start uses, and tells the browser ------------------------------

def setup_widgets(app, cid="insights"):
    topics = [group for group in app.button_group if group.key == f"practice_topic_{cid}"]
    return app.radio(key=f"practice_mode_{cid}"), (topics[0] if topics else None), app.number_input(
        key=f"practice_count_{cid}")


def started_settings(app):
    return app.session_state["active_practice_insights"]["settings"]


SESSION_SETTINGS = {"mode": "topic", "requested_count": 3, "confirmed_topic_ids": ["other", "t"], "topic_id": "other"}


def test_change_settings_shows_the_open_session_settings_and_start_uses_them():
    app = practice_app(active={"settings": SESSION_SETTINGS}, scope=["other", "t"])
    app.button(key="practice_change_settings_s").click().run()
    mode, topic, count = setup_widgets(app)
    assert (mode.value, topic.value, count.value) == ("Topic Practice", "other", 3)
    # Assigned in the run that draws them, so the browser shows these values too.
    assert mode.proto.set_value and topic.proto.set_value and count.proto.set_value
    app.button(key="practice_start_insights").click().run()
    assert not app.exception
    assert started_settings(app) == SESSION_SETTINGS
    assert app.session_state["active_practice_insights"]["session"].question_ids == ["q3"]


def test_a_request_staged_by_another_page_comes_first():
    app = practice_app(active={"settings": {**SESSION_SETTINGS, "mode": "mock", "topic_id": None, "requested_count": 5}},
                       scope=["other", "t"])
    # What stage_practice stores on another page.
    app.session_state["practice_entry_insights"] = {"topic_id": "other"}
    app.session_state["practice_mode_insights"] = "Topic Practice"
    app.session_state["practice_topic_insights"] = "other"
    app.run()
    mode, topic, count = setup_widgets(app)
    assert (mode.value, topic.value, count.value) == ("Topic Practice", "other", 5)
    assert mode.proto.set_value and topic.proto.set_value and count.proto.set_value
    app.button(key="practice_start_insights").click().run()
    assert started_settings(app) == {**SESSION_SETTINGS, "requested_count": 5}


def test_without_a_session_the_last_choice_then_the_defaults():
    app = page_app(PRACTICE, scope=("t", "other"))
    mode, topic, count = setup_widgets(app)
    assert (mode.value, topic, count.value) == ("Mock Exam", None, 10)
    assert mode.proto.set_value and count.proto.set_value
    app.radio(key="practice_mode_insights").set_value("Topic Practice").run()
    app.button_group(key="practice_topic_insights").set_value("other").run()
    app.number_input(key="practice_count_insights").set_value(4).run()
    # Another visit to the page shows the last choice again.
    again = carry_to(app, PRACTICE)
    mode, topic, count = setup_widgets(again)
    assert (mode.value, topic.value, count.value) == ("Topic Practice", "other", 4)
    assert mode.proto.set_value and topic.proto.set_value and count.proto.set_value


def test_a_value_staged_before_the_widgets_existed_never_comes_back():
    # Another page staged Topic Practice on "other" before the setup widgets existed.
    app = page_app(PRACTICE, scope=("t", "other"), extra={
        "practice_entry_insights": {"topic_id": "other"},
        "practice_mode_insights": "Topic Practice", "practice_topic_insights": "other",
    })
    assert setup_widgets(app)[1].value == "other"
    app.button_group(key="practice_topic_insights").set_value("t").run()
    app.button(key="practice_start_insights").click().run()
    sid = app.session_state["active_practice_insights"]["session"].session_id
    assert started_settings(app)["topic_id"] == "t"
    app.button(key=f"practice_change_settings_{sid}").click().run()
    assert setup_widgets(app)[1].value == "t"
    # The knowledge point leaves the screen and comes back: still the student's "t".
    app.radio(key="practice_mode_insights").set_value("Mock Exam").run()
    assert setup_widgets(app)[1] is None
    app.radio(key="practice_mode_insights").set_value("Topic Practice").run()
    topic = setup_widgets(app)[1]
    assert topic.value == "t" and topic.proto.set_value
    app.button(key="practice_start_insights").click().run()
    assert started_settings(app)["topic_id"] == "t"


# R3 · A button of another session changes nothing -------------------------------------------------

def other_session(**extra):
    course = setup_course()
    return {"session": ExamSession(session_id="b", mode="topic", question_ids=["q0", "q1"]),
            "questions": course.questions[:2], "warning": None, "settings": {}, **extra}


@pytest.mark.parametrize(("question_ids", "key"), [
    (("q0", "q1"), "worksheet_next_s"),
    (("q0", "q1"), "worksheet_review_s"),
    (("q0",), "worksheet_finish_s"),
])
def test_question_screen_buttons_of_another_session_change_nothing(question_ids, key):
    app = practice_app(question_ids=question_ids)
    current = other_session()
    app.session_state["active_practice_insights"] = current  # opened meanwhile, e.g. on another page
    app.button(key=key).click().run()
    assert not app.exception
    assert "worksheet_index" not in current and "worksheet_step" not in current


def test_review_step_buttons_of_another_session_change_nothing():
    app = practice_app()
    open_review(app)
    current = other_session(worksheet_step="review")
    app.session_state["active_practice_insights"] = current
    app.button(key="practice_submit_s").click().run()
    assert not app.exception
    assert "result" not in current and "practice_history_insights" not in app.session_state
    app = practice_app()
    open_review(app)
    current = other_session(worksheet_step="review")
    app.session_state["active_practice_insights"] = current
    app.button(key="worksheet_back_s").click().run()
    assert current["worksheet_step"] == "review"


# R4 · A repeated click finds its target gone and does nothing --------------------------------------

def test_resume_twice_changes_nothing_the_second_time(monkeypatch):
    from services.practice_pages_ui import resume_session

    destinations = capture_switches(monkeypatch)
    course = setup_course()
    state = {"practice_drafts_insights": {"d": draft(course, "d", 2)}}
    assert resume_session(state, "insights", "d") and resume_session(state, "insights", "d")
    assert state["practice_drafts_insights"] == {}
    # On the page: the second click arrives after the first one resumed the session.
    app = page_app(HISTORY, course, {"practice_drafts_insights": {"d": draft(course, "d", 2)}})
    app.session_state["active_practice_insights"] = draft(course, "d", 2)
    app.session_state["practice_drafts_insights"] = {}
    app.button(key="practice_history_resume_d").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"]["session"].session_id == "d"
    assert destinations == [] and not history_rows(app)


def test_practise_missed_questions_twice_starts_one_session():
    app, _ = start_app(graded=True, picks=(1, 1))
    first = other_session()  # the first click already opened the review session
    app.session_state["active_practice_insights"] = first
    app.button(key="review_mistakes_s").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"] is first
    assert "practice_drafts_insights" not in app.session_state


def test_start_twice_starts_one_session():
    app = page_app(PRACTICE)
    first = other_session()  # the first click already started a session
    app.session_state["active_practice_insights"] = first
    app.button(key="practice_start_insights").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"] is first
    assert "practice_drafts_insights" not in app.session_state


def test_try_a_different_structure_twice_starts_one_session(monkeypatch):
    capture_switches(monkeypatch)
    app = review_app(picks=(1, 0), course=setup_course())
    first = other_session()  # the first click already opened the new session
    app.session_state["active_practice_insights"] = first
    app.button(key="transfer_s_q0").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"] is first
    assert "practice_drafts_insights" not in app.session_state


# R5 · One radio, a trip to another page, a one-question session --------------------------------------

@pytest.mark.parametrize("mode", ["topic", "mock"])
def test_the_question_screen_has_exactly_one_answer_radio(mode):
    app = practice_app(mode)
    for _ in range(3):
        assert len(app.radio) == 1
        if [b for b in app.button if b.key == "worksheet_next_s"]:
            app.button(key="worksheet_next_s").click().run()


def test_answers_off_screen_survive_a_trip_to_another_page():
    course = setup_course()
    app = registered_practice({
        "current_course": course, "confirmed_scope_insights": ["t"],
        "active_practice_insights": draft(course, "a", 3),
    })
    answer_two_questions(app, "a")
    app.button(key="worksheet_next_a").click().run()  # question 3 on screen
    app.switch_page("pages/3_Performance.py").run()
    assert not app.exception
    app.switch_page(PRACTICE_PATH).run()
    assert not app.exception
    assert badges(app) == ["Q03"] and app.radio(key="answer_a_q2").value is None
    app.button(key="worksheet_previous_a").click().run()
    assert_answers_intact(app, "a")


def test_finish_and_the_review_step_in_a_one_question_session():
    app = practice_app(question_ids=("q0",))
    assert app.button(key="worksheet_previous_s").disabled
    assert not [b for b in app.button if b.key == "worksheet_next_s"]
    assert app.button(key="worksheet_finish_s").label == "Finish"
    app.radio(key="answer_s_q0").set_value(0).run()
    app.button(key="worksheet_finish_s").click().run()
    assert titles(app) == ["Practice · Review"]
    assert "1 of 1 answered" in page_markdown(app)
    assert "No unanswered, unsure or guessed answers to review." in [c.value for c in app.caption]
    app.button(key="worksheet_back_s").click().run()
    assert badges(app) == ["Q01"] and app.radio(key="answer_s_q0").value == 0
    app.button(key="worksheet_finish_s").click().run()
    app.button(key="practice_submit_s").click().run()
    assert not app.exception
    assert [metric.value for metric in app.metric][:1] == ["1 / 1"]


# R6 · The availability note on the result screen ---------------------------------------------------

def test_result_screen_shows_the_availability_note_as_a_caption():
    app, _ = start_app(graded=True)
    app.session_state["active_practice_insights"]["warning"] = "3 questions available; all included."
    app.run()
    assert not app.exception
    assert not app.warning
    top = list(app.main.children.values())
    overview = next(i for i, node in enumerate(top)
                    if "practice_overview" in (getattr(getattr(node, "proto", None), "id", "") or ""))
    note = next(i for i, node in enumerate(top)
                if getattr(node, "type", "") == "caption" and node.value == "3 questions available; all included.")
    assert note == overview + 1
