"""Student-facing pages use one-click choices and hide storage bookkeeping."""

from pathlib import Path
from types import SimpleNamespace

import streamlit as st
from streamlit.testing.v1 import AppTest

from models.schemas import Question, StudyPackage
from services.i18n import LANGUAGE_KEY

ROOT = Path(__file__).resolve().parents[1]
STUDY_PLAN_PATH = ROOT / "pages" / "1_Study_Hub.py"
DASHBOARD_PATH = ROOT / "pages" / "0_Dashboard.py"
PROGRESS_PATH = ROOT / "pages" / "3_Performance.py"
ANKI_PATH = ROOT / "pages" / "5_Export_Anki.py"


def make_reviewed_course() -> StudyPackage:
    questions = [
        Question(
            id=f"q{index}",
            topic_id="t1",
            question=f"Question {index}?",
            options=["a", "b", "c", "d"],
            correct_index=1,
            explanation="Because.",
        )
        for index in range(1, 5)
    ]
    return StudyPackage(
        course_id="c1",
        course_name="Course",
        topics=[
            {"id": "t1", "name": "Limits", "summary": "Summary."},
            {"id": "t2", "name": "Series", "summary": "Summary."},
        ],
        relationships=[],
        questions=questions,
        learning_state={
            # q2 has no review decision recorded.
            "question_reviews": {"q1": "pending", "q3": "flagged", "q4": "approved"},
        },
    )


def study_plan(course: StudyPackage, chinese: bool = False) -> AppTest:
    app = AppTest.from_file(str(STUDY_PLAN_PATH))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = ["t1"]
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    return app.run()


def test_exam_scope_is_one_click_pills_with_topic_ids():
    app = study_plan(make_reviewed_course())

    assert not app.exception
    assert not app.multiselect
    scope = app.button_group(key="scope_selection_c1")
    assert scope.options == ["Limits", "Series"]
    assert scope.value == ["t1"]

    scope.select("t2").run()
    assert not app.exception
    assert app.session_state["scope_selection_c1"] == ["t1", "t2"]
    assert "confirmed_scope_c1" not in app.session_state


def test_review_form_uses_horizontal_radios_and_keeps_question_dropdown():
    app = study_plan(make_reviewed_course())

    assert not app.exception
    assert app.selectbox(key="editor_question_c1").label == "Question to review"
    correct = next(item for item in app.radio if item.label == "Correct answer")
    assert correct.horizontal
    assert correct.options == ["A", "B", "C", "D"]
    assert correct.value == 1
    dimension = next(
        item for item in app.radio if item.label == "Learning DNA evidence type"
    )
    assert dimension.horizontal
    assert not any(
        item.label in {"Correct answer", "Learning DNA evidence type"}
        for item in app.selectbox
    )


def test_review_list_shows_plain_status_words_instead_of_internal_codes():
    app = study_plan(make_reviewed_course())

    assert not app.exception
    options = app.selectbox(key="editor_question_c1").options
    assert options == [
        "Needs check · Question 1?",
        "Question 2?",
        "Flagged · Question 3?",
        "Approved · Question 4?",
    ]
    assert not any("[" in option for option in options)
    captions = [item.value for item in app.caption]
    assert "1 new question needs your check" in captions
    assert "2 questions ready" in captions
    assert not any("legacy" in text.lower() for text in captions)
    assert (
        "Check the answer and explanation before approving; edits never change past results."
        in captions
    )


def test_review_texts_are_translated():
    app = study_plan(make_reviewed_course(), chinese=True)

    assert not app.exception
    captions = [item.value for item in app.caption]
    assert "有 1 道新题需要你检查" in captions
    assert "2 道题可以练习" in captions
    assert app.selectbox(key="editor_question_c1").options[0] == "待检查 · Question 1?"


def test_saving_a_review_still_maps_the_untagged_choice_to_none():
    app = study_plan(make_reviewed_course())
    next(item for item in app.radio if item.label == "Correct answer").set_value(2)
    next(b for b in app.button if b.label == "Save review").click().run()

    assert not app.exception
    saved = app.session_state["current_course"]
    assert saved.questions[-1].correct_index == 2
    assert saved.questions[-1].cognitive_dimension is None


def test_anonymous_course_tools_do_not_mention_the_database():
    app = study_plan(make_reviewed_course())

    assert not app.exception
    captions = [item.value for item in app.caption]
    assert "Log in to back up this course." in captions
    assert not any("database" in text.lower() for text in captions)


def test_dashboard_hides_raw_validation_errors_from_generated_topics(monkeypatch):
    from services import ai_service

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    uploaded = SimpleNamespace(name="notes.txt", getvalue=lambda: b"Course notes.")
    monkeypatch.setattr(st, "file_uploader", lambda *_args, **_kwargs: uploaded)
    monkeypatch.setattr(
        ai_service, "generate_topics",
        lambda **_kwargs: {"ok": True, "package": {"course_id": "broken"}},
    )
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    app.text_input(key="setup_course_name").set_value("New course").run()
    next(button for button in app.button if button.label == "Extract text").click().run()
    next(button for button in app.button if button.label == "Generate topics").click().run()

    assert not app.exception
    assert [item.value for item in app.error] == [
        "Couldn't use the generated topics. Try generating them again."
    ]
    assert not any("Extracted text:" in item.value for item in app.caption)


def test_progress_page_keeps_legend_but_not_storage_notes():
    from tests.test_demo_courses import load_demo

    app = AppTest.from_file(str(PROGRESS_PATH))
    app.session_state["current_course"] = load_demo("sample_course.json")
    app.run()

    assert not app.exception
    captions = " ".join(item.value for item in app.caption)
    assert "Below 60%: Weak" in captions
    assert "Signed-in users" not in captions
    assert "excluded" not in captions
    assert "Uses your latest answer to each question." in captions
    assert not any(
        item.label == "Question labels and saved history" for item in app.expander
    )


def test_anki_page_uses_plain_wording():
    from tests.test_demo_courses import load_demo

    app = AppTest.from_file(str(ANKI_PATH))
    app.session_state["current_course"] = load_demo("demo_python_basics.json")
    app.run()

    assert not app.exception
    texts = [item.value for item in [*app.caption, *app.markdown]]
    assert not any("UTF-8" in text or "not been verified" in text for text in texts)
    assert any(text.endswith("cards · All Questions") for text in texts)
