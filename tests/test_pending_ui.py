from pathlib import Path
from types import SimpleNamespace

import pymupdf
import streamlit as st
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services.ui_adapters import tutor_question_key, tutor_result_key


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "pages" / "0_Dashboard.py"
STUDY_PLAN_PATH = ROOT / "pages" / "1_Study_Hub.py"


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    file_bytes = document.tobytes()
    document.close()
    return file_bytes


def install_upload_mock(monkeypatch):
    upload = {"file": None}

    def fake_file_uploader(*_args, **_kwargs):
        return upload["file"]

    monkeypatch.setattr(st, "file_uploader", fake_file_uploader)
    return upload


def make_upload(filename: str, content: bytes):
    return SimpleNamespace(name=filename, getvalue=lambda: content)


def click_extract(app: AppTest) -> None:
    next(
        button for button in app.button if button.label == "Extract text"
    ).click().run()


def test_dashboard_extracts_txt_and_shows_limits_preview_and_source(monkeypatch):
    upload = install_upload_mock(monkeypatch)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    app.text_input(key="setup_course_name").set_value("TXT course")
    upload["file"] = make_upload(
        "notes.txt",
        "A local TXT fixture.".encode("utf-8"),
    )
    app.run()
    click_extract(app)

    assert not app.exception
    assert app.session_state["setup_document"]["text"] == (
        "A local TXT fixture."
    )
    assert app.session_state["setup_document"]["sources"] == [
        {"filename": "notes.txt", "page": None}
    ]
    assert any("50,000 characters" in item.value for item in app.caption)
    assert any(
        "text-based PPTX" in item.value
        and "PPTX slide notes and image OCR" in item.value
        for item in app.caption
    )
    assert any(
        "notes.txt · TXT file (no page number)" in item.value
        for item in app.caption
    )
    assert "A local TXT fixture." in [item.value for item in app.text]


def test_dashboard_extracts_pdf_and_displays_actual_page_sources(monkeypatch):
    upload = install_upload_mock(monkeypatch)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    pdf_bytes = make_pdf("Page one content.")
    upload["file"] = make_upload("course.pdf", pdf_bytes)
    app.run()
    click_extract(app)

    assert not app.exception
    document = app.session_state["setup_document"]
    assert document["sources"] == [{"filename": "course.pdf", "page": 1}]
    assert document["pages"][0]["page"] == 1
    assert any("course.pdf · Page 1" in item.value for item in app.caption)
    assert any("PDF pages (1)" in item.label for item in app.expander)


def test_dashboard_failure_message_clears_old_document_and_disables_generation(
    monkeypatch,
):
    upload = install_upload_mock(monkeypatch)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    upload["file"] = make_upload("old.txt", b"old content")
    app.run()
    click_extract(app)
    assert app.session_state["setup_document"]["filename"] == "old.txt"

    upload["file"] = make_upload("invalid.txt", b"\xff")
    app.run()

    assert "setup_document" not in app.session_state
    click_extract(app)

    assert not app.exception
    assert "setup_document" not in app.session_state
    assert any(
        "文件必须使用有效的 UTF-8 编码。" in item.value
        for item in app.error
    )
    assert not any(button.label == "Generate topics" for button in app.button)


def test_dashboard_file_replacement_and_removal_never_reuse_old_extraction(
    monkeypatch,
):
    upload = install_upload_mock(monkeypatch)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    upload["file"] = make_upload("first.txt", b"First file.")
    app.run()
    click_extract(app)
    assert app.session_state["setup_document"]["filename"] == "first.txt"

    upload["file"] = make_upload("second.txt", b"Second file.")
    app.run()
    assert "setup_document" not in app.session_state
    assert not any(button.label == "Generate topics" for button in app.button)

    click_extract(app)
    assert app.session_state["setup_document"]["filename"] == "second.txt"

    upload["file"] = None
    app.run()
    assert "setup_document" not in app.session_state
    assert not any(button.label == "Generate topics" for button in app.button)


def make_study_course(course_id: str, course_name: str) -> StudyPackage:
    return StudyPackage(
        course_id=course_id,
        course_name=course_name,
        topics=[
            {
                "id": f"{course_id}-topic",
                "name": "Course topic",
                "summary": "A short course summary.",
            }
        ],
        relationships=[],
        questions=[],
    )


def test_tutor_answers_are_course_scoped_and_sent_only_on_form_submit(
    monkeypatch,
):
    from services import gemini_service

    calls = []

    def fake_ask_tutor(package, question, topic_id=None):
        calls.append((package, question, topic_id))
        return {"ok": True, "answer": f"Answer for {package['course_name']}"}

    monkeypatch.setattr(gemini_service, "ask_tutor", fake_ask_tutor)

    first_course = make_study_course("course-a", "Course A")
    first_app = AppTest.from_file(str(STUDY_PLAN_PATH))
    first_app.session_state["current_course"] = first_course
    first_app.session_state["confirmed_scope_course-a"] = ["course-a-topic"]
    first_app.session_state[tutor_question_key("course-a")] = "Question A"
    first_app.run()

    second_course = make_study_course("course-b", "Course B")
    second_app = AppTest.from_file(str(STUDY_PLAN_PATH))
    second_app.session_state["current_course"] = second_course
    second_app.session_state["confirmed_scope_course-b"] = ["course-b-topic"]
    second_app.session_state[tutor_question_key("course-b")] = "Question B"
    second_app.run()

    for app, course_id, expected_question in (
        (first_app, "course-a", "Question A"),
        (second_app, "course-b", "Question B"),
    ):
        assert not app.exception
        assert app.text_area(key=tutor_question_key(course_id)).value == (
            expected_question
        )
        assert not app.button(key=f"tutor_send_{course_id}").disabled
        assert app.button(key=f"anki_download_{course_id}").disabled
        assert app.button(key=f"database_save_{course_id}").disabled
        assert app.button(key=f"database_restore_{course_id}").disabled
        assert tutor_result_key(course_id) not in app.session_state
        assert "No flashcards are available to preview yet." in [
            element.value for element in app.info
        ]
        assert any(
            "CSV/APKG 格式待确认。" in element.value
            for element in app.caption
        )
        current_course = app.session_state["current_course"]
        assert any(
            f"Current course: {current_course.course_name}" == element.value
            for element in app.caption
        )
        assert any(
            "Answers use this course" in element.value
            for element in app.caption
        )
        assert any(
            "仅保存在当前会话；数据库待接入。" == element.value
            for element in app.caption
        )

    assert calls == []
    first_app.text_area(key=tutor_question_key("course-a")).set_value(
        "Updated question A"
    ).run()
    assert first_app.session_state[tutor_question_key("course-a")] == (
        "Updated question A"
    )
    assert second_app.session_state[tutor_question_key("course-b")] == (
        "Question B"
    )

    first_app.button(key="tutor_send_course-a").click().run()

    assert not first_app.exception
    assert len(calls) == 1
    assert type(calls[0][0]) is dict
    assert calls[0][0]["course_id"] == "course-a"
    assert calls[0][1] == "Updated question A"
    assert calls[0][2] is None
    assert any(
        element.value == "Answer for Course A"
        for element in first_app.markdown
    )
    assert tutor_result_key("course-a") in first_app.session_state
    assert tutor_result_key("course-b") not in second_app.session_state

    first_app.run()
    assert len(calls) == 1


def test_tutor_displays_service_failure_without_retrying(monkeypatch):
    from services import gemini_service

    calls = []

    def fake_ask_tutor(package, question, topic_id=None):
        calls.append((package, question))
        return {
            "ok": False,
            "error_code": "MISSING_API_KEY",
            "message": "Please configure GEMINI_API_KEY.",
        }

    monkeypatch.setattr(gemini_service, "ask_tutor", fake_ask_tutor)
    course = make_study_course("course-failure", "Failure course")
    app = AppTest.from_file(str(STUDY_PLAN_PATH))
    app.session_state["current_course"] = course
    app.session_state[tutor_question_key(course.course_id)] = "Explain this."
    app.run()

    app.button(key=f"tutor_send_{course.course_id}").click().run()

    assert not app.exception
    assert len(calls) == 1
    assert type(calls[0][0]) is dict
    assert calls[0][0]["course_id"] == course.course_id
    assert calls[0][1] == "Explain this."
    assert any(
        error.value == "Please configure GEMINI_API_KEY."
        for error in app.error
    )

    app.run()
    assert len(calls) == 1


def test_dashboard_extracts_pptx_and_displays_actual_slide_sources(monkeypatch):
    from io import BytesIO

    from pptx import Presentation

    upload = install_upload_mock(monkeypatch)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(0, 0, 2_000_000, 500_000)
    shape.text_frame.text = "PPTX extraction fixture."
    output = BytesIO()
    presentation.save(output)
    upload["file"] = make_upload("slides.pptx", output.getvalue())
    app.run()

    click_extract(app)

    assert not app.exception
    document = app.session_state["setup_document"]
    assert document["sources"] == [{"filename": "slides.pptx", "page": 1}]
    assert document["pages"] == [
        {"page": 1, "text": "PPTX extraction fixture."}
    ]
    assert any(
        "slides.pptx · Slide 1" == item.value for item in app.caption
    )
    assert any("PPTX slides (1)" == item.label for item in app.expander)
    assert any(
        "Supports UTF-8 TXT, text-based PDF, and text-based PPTX"
        in item.value
        for item in app.caption
    )
