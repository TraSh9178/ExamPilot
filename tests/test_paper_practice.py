"""Paper practice page: question card, one-click choices, Learning Radar and clean wording."""
import ast
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import components
from components.knowledge_graph import radar_count_text
from models.schemas import ExamSession, Question
from services import practice_insights_ui
from services.account_sync import SyncOutcome
from services.exam_engine import create_exam, grade_exam
from services.i18n import LANGUAGE_KEY, _DYNAMIC, _TRANSLATIONS
from services.practice_insights import session_insights, set_session_insights
from tests.auth_helpers import TEST_USER, signed_in_app
from tests.test_learning_flow_ux import calculus
from tests.test_practice_insights import setup_course, start_app
from tests.test_practice_page import open_review, open_setup, submit_answers

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "2_Practice_Center.py"
RAW_DB_ERROR = "connection to db.internal:5432 failed: FATAL password authentication failed"


def page_markdown(app):
    """Markdown on the page, without the stylesheet the app injects as markdown."""
    return [m.value for m in app.markdown if not m.value.lstrip().startswith("<style")]


def texts(app):
    """Every visible text value on the page, for checks that wording is gone."""
    values = page_markdown(app)
    for kind in ("caption", "info", "warning", "error", "success", "subheader"):
        values += [item.value for item in app.get(kind)]
    values += [item.label for item in app.expander]
    return values


def badges(app):
    return re.findall(r'class="paper-question-badge">([^<]+)<', " ".join(page_markdown(app)))


def mock_app(graded=False):
    course = setup_course()
    questions = course.questions[:2]
    session = ExamSession(session_id="m", mode="mock", question_ids=[q.id for q in questions])
    active = {"session": session, "questions": questions, "warning": None, "settings": {}}
    if graded:
        active["result"] = grade_exam(session, questions, {questions[0].id: 0, questions[1].id: 1})
    app = AppTest.from_file(str(PAGE))
    app.session_state["current_course"] = course
    app.session_state["confirmed_scope_insights"] = ["t"]
    app.session_state["active_practice_insights"] = active
    return app.run()


# 1 · Question card -------------------------------------------------------

def test_topic_question_card_has_two_digit_badge_and_lettered_options():
    app, _ = start_app()
    assert not app.exception
    assert badges(app) == ["Q01"]
    assert not any(c.value.startswith("QUESTION") for c in app.caption)
    answer = app.radio(key="answer_s_q0")
    assert answer.options == ["A. A", "B. B", "C. C", "D. D"]
    answer.set_value(2).run()
    assert app.radio(key="answer_s_q0").value == 2
    assert app.session_state["active_practice_insights"]["_draft_widgets"]["answer_s_q0"] == 2
    app.button(key="worksheet_next_s").click().run()
    assert badges(app) == ["Q02"]


def test_mock_exam_and_review_use_the_same_badges():
    app = mock_app()
    assert not app.exception
    # One question at a time in Mock Exam too.
    assert badges(app) == ["Q01"]
    app.button(key="worksheet_next_m").click().run()
    assert badges(app) == ["Q02"]
    assert app.radio(key="answer_m_q1").options[0] == "A. A"
    app = mock_app(graded=True)
    assert badges(app) == ["Q01", "Q02"]
    assert not any(c.value.startswith("QUESTION") for c in app.caption)


def test_question_text_is_escaped_and_keeps_line_breaks():
    app, course = start_app()
    question = app.session_state["active_practice_insights"]["questions"][0]
    question.question = "What is printed?\nif x < 3:\n    print('<b>')"
    app.run()
    card = next(value for value in page_markdown(app) if "paper-question-badge" in value)
    assert "if x &lt; 3:<br>    print('&lt;b&gt;')" in card
    assert "<b>" not in card


def test_badge_is_translated_with_the_interface():
    app, _ = start_app()
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    assert badges(app) == ["第 1 题"]


# 2 · Confidence in one click ---------------------------------------------

def test_confidence_is_one_click_and_survives_worksheet_paging():
    app, course = start_app()
    confidence = app.button_group(key="confidence_s_q0")
    assert confidence.options == ["Sure", "Unsure", "Guessed"]
    assert confidence.value is None
    assert not app.selectbox  # no confidence dropdown left
    confidence.set_value("guessed").run()
    app.button(key="worksheet_next_s").click().run()
    assert app.button_group(key="confidence_s_q1").value is None
    app.button(key="worksheet_previous_s").click().run()
    assert app.button_group(key="confidence_s_q0").value == "guessed"
    # (AppTest cannot clear a single-select button group: set_value(None) keeps the old value.)
    app.button_group(key="confidence_s_q0").set_value("sure").run()
    app.button(key="worksheet_next_s").click().run()
    app.button(key="worksheet_previous_s").click().run()
    assert app.button_group(key="confidence_s_q0").value == "sure"
    submit_answers(app)
    assert not app.exception
    rows = session_insights(app.session_state["current_course"], "s")
    assert rows["q0"]["confidence"] == "sure"
    assert rows["q1"]["confidence"] is None


def test_unrecorded_confidence_is_not_flagged_before_submit():
    app, _ = start_app()
    app.radio(key="answer_s_q0").set_value(0).run()
    open_review(app)
    table = next(frame.value for frame in app.dataframe)
    assert list(table["Check"]) == ["Unanswered"]  # q1 only; q0 has no confidence yet
    app.button(key="worksheet_back_s").click().run()
    app.button_group(key="confidence_s_q0").set_value("unsure").run()
    open_review(app)
    table = next(frame.value for frame in app.dataframe)
    assert list(table["Check"]) == ["Unsure", "Unanswered"]


# 3 · Pills ------------------------------------------------------------------

def test_review_topic_is_a_pill_choice_that_defaults_to_all_missed_topics():
    app, _ = start_app(graded=True, picks=(1, 1))
    topics = app.button_group(key="mistake_topic_insights_s")
    assert topics.options == ["All missed topics", "Topic"]
    assert topics.indices == [0]
    topics.set_value("t").run()
    app.button(key="review_mistakes_s").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["session"].session_id != "s"
    assert active["session"].question_ids == ["q0", "q1"]
    assert {q.topic_id for q in active["questions"]} == {"t"}


# 4 & 5 · Learning Radar ---------------------------------------------------------

class FakeRadarChart:
    def __init__(self, monkeypatch):
        self.charts, self.stuck = [], []
        module = ModuleType("components.radar_chart")
        module.render_radar_figure = self.render_radar_figure
        module.render_stuck_buttons = self.render_stuck_buttons
        monkeypatch.setitem(sys.modules, "components.radar_chart", module)
        monkeypatch.setattr(components, "radar_chart", module, raising=False)

    def render_radar_figure(self, course, radar, *, focus_topic_id=None, limit=6, key):
        self.charts.append((course, radar, focus_topic_id, key))
        st.markdown("fake spider chart")

    def render_stuck_buttons(self, session_state, course_id, topic_id, user_id, *, key):
        self.stuck.append((course_id, topic_id, user_id, key))
        st.caption("fake stuck buttons")


def radar_app(signed_in=True):
    course = calculus()
    topic_id = "calc_limits"
    exam = create_exam(package=course, mode="topic", requested_count=2,
                       confirmed_topic_ids=[topic_id], topic_id=topic_id)
    app = signed_in_app(PAGE) if signed_in else AppTest.from_file(str(PAGE))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = [topic_id]
    app.session_state[f"active_practice_{course.course_id}"] = {
        "session": exam["session"], "questions": exam["questions"], "warning": None, "settings": {},
    }
    return app.run(), course, exam


def test_margin_chart_and_stuck_popover_use_the_radar_component(monkeypatch):
    fake = FakeRadarChart(monkeypatch)
    app, course, exam = radar_app()
    assert not app.exception
    sid, first = exam["session"].session_id, exam["questions"][0]
    cached = app.session_state[f"learning_radar_cache_{course.course_id}"]["radar"]
    assert len(fake.charts) == 1
    chart_course, chart_radar, focus, key = fake.charts[0]
    assert chart_course.course_id == course.course_id and chart_radar == cached
    assert (focus, key) == (first.topic_id, "practice_radar")
    assert fake.stuck == [(course.course_id, first.topic_id, TEST_USER.user_id, f"practice_stuck_{sid}_{first.id}")]
    popovers = app.get("popover")
    # The session menu in the title row, then Learning Radar in the actions row.
    assert [p.proto.popover.label for p in popovers] == ["This session", "Learning Radar"]
    assert "fake stuck buttons" in [c.value for c in popovers[1].caption]
    # The chart sits above the existing count, and the Explore button stays below.
    markdown = page_markdown(app)
    count_text = radar_count_text(cached.topics.get(first.topic_id))
    assert markdown.index("fake spider chart") == markdown.index(count_text) - 1
    assert any(b.key == f"worksheet_radar_{sid}" for b in app.button)
    assert any(m.value == "Quick Notes" for m in app.subheader)


def test_signed_out_student_sees_the_chart_but_no_stuck_popover(monkeypatch):
    fake = FakeRadarChart(monkeypatch)
    app, _, _ = radar_app(signed_in=False)
    assert not app.exception
    assert len(fake.charts) == 1
    assert fake.stuck == []
    assert [p.proto.popover.label for p in app.get("popover")] == ["This session"]


def test_page_works_before_the_radar_component_is_merged(monkeypatch):
    monkeypatch.delattr(components, "radar_chart", raising=False)
    monkeypatch.setitem(sys.modules, "components.radar_chart", None)
    app, _, exam = radar_app()
    assert not app.exception
    assert [p.proto.popover.label for p in app.get("popover")] == ["This session"]
    assert "Learning Radar" in [s.value for s in app.subheader]
    assert any(b.key == f"worksheet_radar_{exam['session'].session_id}" for b in app.button)


def test_mock_exam_offers_the_stuck_popover_under_the_question(monkeypatch):
    fake = FakeRadarChart(monkeypatch)
    course = calculus()
    scope = ["calc_limits", "calc_derivatives"]
    exam = create_exam(package=course, mode="mock", requested_count=2, confirmed_topic_ids=scope)
    app = signed_in_app(PAGE)
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = scope
    app.session_state[f"active_practice_{course.course_id}"] = {
        "session": exam["session"], "questions": exam["questions"], "warning": None, "settings": {},
    }
    app.run()
    assert not app.exception
    sid = exam["session"].session_id
    for question in exam["questions"]:
        radar_menus = [p for p in app.get("popover") if p.proto.popover.label == "Learning Radar"]
        assert len(radar_menus) == 1
        assert fake.stuck[-1] == (course.course_id, question.topic_id, TEST_USER.user_id, f"practice_stuck_{sid}_{question.id}")
        # The side panel shows the radar for the question on screen, but no notes in Mock Exam.
        assert fake.charts[-1][2] == question.topic_id
        assert "Quick Notes" not in [s.value for s in app.subheader]
        if question is not exam["questions"][-1]:
            app.button(key=f"worksheet_next_{sid}").click().run()
    assert len(fake.stuck) == len(fake.charts) == 2


# 6 · Clean-up ---------------------------------------------------------------

def test_bookkeeping_text_is_gone_from_practice_and_result():
    app, _ = start_app()
    shown = " ".join(texts(app))
    for removed in ("Selected for focus-time tracking", "Saved practice sessions", "pending, flagged",
                    "Question availability"):
        assert removed not in shown
    app, course = start_app(graded=True)
    shown = " ".join(texts(app))
    for removed in ("Confidence is self-reported", "Answered questions:", "used in-app hints",
                    "Hint use was not recorded", "No focus-time measurements", "Saved practice sessions",
                    "No source page was provided", "Source text is not available", "A review creates"):
        assert removed not in shown
    open_setup(app)  # "New practice": saved sessions can still be reopened from there
    assert app.button(key="open_saved_result_insights")


def test_pending_questions_no_longer_show_an_availability_note(monkeypatch):
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    course = calculus()
    app = AppTest.from_file(str(PAGE))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = ["calc_limits"]
    app.run()
    assert not app.exception
    assert all(e.label != "Question availability" for e in app.expander)


def test_short_availability_notice_and_new_practice_line():
    app, course = start_app(graded=True)
    app.session_state["practice_entry_insights"] = {"topic_id": "t"}
    app.session_state["practice_mode_insights"] = "Topic Practice"
    app.session_state["practice_topic_insights"] = "t"
    app.run()
    assert "New practice: Topic" in [i.value for i in app.info]
    app.number_input(key="practice_count_insights").set_value(10)
    next(b for b in app.button if b.label == "Start new practice").click().run()
    assert not app.exception
    # On the question screen the notice is one quiet line under the header, first question only.
    assert not app.warning
    assert "3 questions available; all included." in [c.value for c in app.caption]
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    assert "仅有 3 道题可用，已全部加入。" in [c.value for c in app.caption]
    sid = app.session_state["active_practice_insights"]["session"].session_id
    app.button(key=f"worksheet_next_{sid}").click().run()
    assert "仅有 3 道题可用，已全部加入。" not in [c.value for c in app.caption]


def test_practice_errors_are_short_and_never_raw(monkeypatch):
    from services import exam_engine

    def broken_create(**kwargs):
        raise ValueError("Unknown topic ID: secret_topic_id")

    def broken_grade(*args):
        raise ValueError("questions must match the question IDs in session q0")

    # The page imports both on each run; patch before the first run.
    monkeypatch.setattr(exam_engine, "create_exam", broken_create)
    monkeypatch.setattr(exam_engine, "grade_exam", broken_grade)
    app, _ = start_app()
    open_setup(app)
    next(b for b in app.button if b.label == "Start new practice").click().run()
    assert not app.exception
    errors = [e.value for e in app.error]
    assert errors == ["Could not create practice. Try another topic or check your exam scope in Study Plan."]

    app.button(key="practice_return_previous").click().run()
    submit_answers(app)
    assert not app.exception
    assert [e.value for e in app.error] == ["Could not grade this practice. Please try again."]
    assert not any("q0" in value or "secret_topic_id" in value for value in texts(app))


def test_unknown_topic_name_falls_back_to_the_word_topic():
    app, course = start_app(graded=True, picks=(1, 1))
    active = app.session_state["active_practice_insights"]
    ghost = Question(id="q1", topic_id="ghost-topic-id", question="Question 1",
                     options=["A", "B", "C", "D"], correct_index=0, explanation="Reason")
    active["questions"] = [active["questions"][0].model_copy(update={"topic_id": "ghost-topic-id"}), ghost]
    app.run()
    assert not app.exception
    shown = texts(app) + [str(frame.value.to_dict()) for frame in app.dataframe]
    assert not any("ghost-topic-id" in value for value in shown)
    assert any("**Topic**" == value for value in page_markdown(app))


def test_transfer_without_a_match_says_no_similar_question_yet():
    app, course = start_app(graded=True, picks=(0, 1))
    course.learning_state["question_reviews"] = {"q2": "pending"}
    course.questions[2].practice_structure = None
    app.session_state["current_course"] = course
    app.run()
    app.button(key="transfer_s_q1").click().run()
    assert not app.exception
    assert "No similar question yet." in [i.value for i in app.info]
    assert not any("structure label" in v or "No approved question" in v for v in texts(app))


# Coordinator 1 · save failures never show the stored reason -------------------

def test_account_save_failure_shows_a_generic_message(monkeypatch):
    monkeypatch.setattr(practice_insights_ui, "save_course_with_history",
                        lambda state, course: SyncOutcome(False, RAW_DB_ERROR))
    app, _ = start_app(graded=True)
    app.text_area(key="explain_s_q0").set_value("My reasoning.")
    next(b for b in app.button if b.label == "Save reflection").click().run()
    assert not app.exception
    assert "Couldn't save to your account. Your work is kept on this device for now." in [w.value for w in app.warning]
    assert [value for value in texts(app) if RAW_DB_ERROR in value or "db.internal" in value] == []
    assert session_insights(app.session_state["current_course"], "s")["q0"]["explanation"] == "My reasoning."


def test_tracking_save_failure_after_grading_is_generic():
    app, _ = start_app(graded=True)
    app.session_state["insights_capture_error"] = True
    app.run()
    warnings = [w.value for w in app.warning]
    assert warnings == ["Your answers were graded, but your practice notes couldn't be saved."]
    assert not any("storage limit" in value for value in texts(app))


# Coordinator 2 · singular and plural ---------------------------------------------

@pytest.mark.parametrize(("picks", "priority", "missed"), [
    ((0, 1), "1 question could benefit from another look.", "1 missed question to practise; your score stays the same."),
    ((1, 1), "2 questions could benefit from another look.", "2 missed questions to practise; your score stays the same."),
])
def test_count_sentences_use_singular_and_plural(picks, priority, missed):
    app, _ = start_app(graded=True, picks=picks)
    captions = [c.value for c in app.caption]
    assert priority in captions and missed in captions
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    count = str(sum(pick != 0 for pick in picks))
    captions = [c.value for c in app.caption]
    assert f"有 {count} 道题值得再看一遍。" in captions
    assert f"有 {count} 道错题可再练习；成绩保持不变。" in captions


def test_guessed_note_and_saved_session_label_use_plural_forms():
    app, course = start_app(graded=True, picks=(0, 0))
    app.session_state["current_course"] = set_session_insights(
        course, "s", {"q0": {"confidence": "guessed"}, "q1": {"confidence": "guessed"}})
    app.run()
    assert ("2 correct answers were marked Guessed. Revisit them before treating them as secure knowledge."
            in [i.value for i in app.info])
    open_setup(app)  # saved sessions are listed on the setup screen
    history = app.session_state["practice_history_insights"]
    record = history["s"]
    single = ExamSession(session_id="one", mode="topic", question_ids=["q0"])
    single_result = grade_exam(single, record["questions"][:1], {"q0": 0})
    history["one"] = {"session": single, "questions": record["questions"][:1],
                      "attempts": single_result["attempts"], "result": single_result}
    app.run()
    assert list(app.selectbox(key="saved_session_insights").options) == [
        "1 · Topic practice · 2 questions · 2/2 correct",
        "2 · Topic practice · 1 question · 1/1 correct",
    ]
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    assert list(app.selectbox(key="saved_session_insights").options)[1] == "2 · 知识点练习 · 1 道题 · 答对 1/1"


def test_unfinished_sessions_label_is_translated():
    from services.learning_flow import install_practice
    app, _ = start_app()
    state = app.session_state
    old = state["active_practice_insights"]
    replacement = {**old, "session": old["session"].model_copy(update={"session_id": "replacement"})}
    plain = {"active_practice_insights": old}
    install_practice(plain, "insights", replacement)
    state["active_practice_insights"] = replacement
    state["practice_drafts_insights"] = plain["practice_drafts_insights"]
    app.run()
    open_setup(app)  # drafts are listed on the setup screen
    assert any(e.label == "Unfinished sessions (1)" for e in app.expander)
    assert list(app.selectbox(key="draft_choice_insights").options) == ["1 · Topic practice · 2 questions · Unfinished"]
    state[LANGUAGE_KEY] = True
    app.run()
    assert any(e.label == "未完成的场次（1）" for e in app.expander)


# Coordinator 3 · every literal tr() string has a Chinese entry -------------------

@pytest.mark.parametrize("relative", ["pages/2_Practice_Center.py", "services/practice_insights_ui.py"])
def test_practice_interface_strings_have_chinese_entries(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    constants = {
        target.id: node.value.value
        for node in ast.walk(tree) if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        for target in node.targets if isinstance(target, ast.Name)
    }
    missing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
            arg = node.args[0]
            text = arg.value if isinstance(arg, ast.Constant) else constants.get(getattr(arg, "id", None))
            if isinstance(text, str) and text not in _TRANSLATIONS and not any(
                re.fullmatch(pattern, text, re.DOTALL) for pattern, _ in _DYNAMIC
            ):
                missing.append(text)
    assert missing == []


def test_worksheet_index_stays_in_range_after_a_late_click():
    app, _ = start_app()
    last = len(app.session_state["active_practice_insights"]["questions"]) - 1

    # Next was on screen, but an earlier click already reached the last question.
    app.session_state["active_practice_insights"]["worksheet_index"] = last
    app.button(key="worksheet_next_s").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"]["worksheet_index"] == last
    assert badges(app) == [f"Q{last + 1:02}"]
    assert app.button(key="worksheet_finish_s").proto.type == "primary"

    # Previous was on screen, but an earlier click already reached the first question.
    app.session_state["active_practice_insights"]["worksheet_index"] = 0
    app.button(key="worksheet_previous_s").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"]["worksheet_index"] == 0
    assert badges(app) == ["Q01"]
    assert app.button(key="worksheet_previous_s").disabled
    # A click on the disabled Previous changes nothing either.
    app.button(key="worksheet_previous_s").click().run()
    assert not app.exception
    assert app.session_state["active_practice_insights"]["worksheet_index"] == 0
