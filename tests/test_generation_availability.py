from pathlib import Path
from types import SimpleNamespace

import streamlit as st
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "pages" / "0_Dashboard.py"
STUDY_PLAN_PATH = ROOT / "pages" / "1_Study_Hub.py"
UNAVAILABLE_TEXT = "GEMINI_API_KEY is not configured"


def dashboard_with_extracted_text(monkeypatch) -> AppTest:
    uploaded = SimpleNamespace(name="notes.txt", getvalue=lambda: b"Course notes.")
    monkeypatch.setattr(st, "file_uploader", lambda *_args, **_kwargs: uploaded)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    app.text_input(key="setup_course_name").set_value("New course").run()
    next(
        button for button in app.button if button.label == "Extract text"
    ).click().run()
    assert not app.exception
    return app


def generate_topics_button(app: AppTest):
    return next(button for button in app.button if button.label == "Generate topics")


def study_plan_with_scope() -> AppTest:
    course = StudyPackage(
        course_id="course-1",
        course_name="Course",
        topics=[{"id": "topic-1", "name": "Topic", "summary": "Summary."}],
        relationships=[],
        questions=[],
    )
    app = AppTest.from_file(str(STUDY_PLAN_PATH))
    app.session_state["current_course"] = course
    app.session_state["confirmed_scope_course-1"] = ["topic-1"]
    app.session_state["course_document_course-1"] = {"text": "Course material"}
    return app.run()


def test_dashboard_disables_topic_generation_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    app = dashboard_with_extracted_text(monkeypatch)

    assert generate_topics_button(app).disabled
    assert any(UNAVAILABLE_TEXT in item.value for item in app.info)


def test_dashboard_enables_topic_generation_with_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    app = dashboard_with_extracted_text(monkeypatch)

    assert not generate_topics_button(app).disabled
    assert not any(UNAVAILABLE_TEXT in item.value for item in app.info)


def test_study_plan_disables_question_generation_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    app = study_plan_with_scope()

    assert not app.exception
    assert app.button(key="generate_questions_course-1").disabled
    assert any(UNAVAILABLE_TEXT in item.value for item in app.info)


def test_study_plan_enables_question_generation_with_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    app = study_plan_with_scope()

    assert not app.exception
    assert not app.button(key="generate_questions_course-1").disabled
    assert not any(UNAVAILABLE_TEXT in item.value for item in app.info)
