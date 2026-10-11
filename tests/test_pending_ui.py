from pathlib import Path
from types import SimpleNamespace

import pymupdf
import streamlit as st
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services.ui_adapters import tutor_question_key


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
    assert any("PPTX, DOCX, images, and OCR" in item.value for item in app.caption)
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


def test_pending_feature_controls_are_disabled_and_tutor_input_is_course_scoped():
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
        assert app.button(key=f"tutor_send_{course_id}").disabled
        assert app.button(key=f"anki_download_{course_id}").disabled
        assert app.button(key=f"database_save_{course_id}").disabled
        assert app.button(key=f"database_restore_{course_id}").disabled
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
            "接口待接入" in element.value
            for element in app.caption
        )
        assert any(
            "仅保存在当前会话；数据库待接入。" == element.value
            for element in app.caption
        )

    first_app.text_area(key=tutor_question_key("course-a")).set_value(
        "Updated question A"
    ).run()
    assert first_app.session_state[tutor_question_key("course-a")] == (
        "Updated question A"
    )
    assert second_app.session_state[tutor_question_key("course-b")] == (
        "Question B"
    )
