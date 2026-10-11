from pathlib import Path
from types import SimpleNamespace

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "pages" / "0_Dashboard.py"


def install_upload_mock(monkeypatch):
    upload = {"file": None, "kwargs": None}

    def fake_file_uploader(*_args, **kwargs):
        upload["kwargs"] = kwargs
        return upload["file"]

    monkeypatch.setattr(st, "file_uploader", fake_file_uploader)
    return upload


def make_upload(filename: str, content: bytes):
    return SimpleNamespace(name=filename, getvalue=lambda: content)


def click_extract(app: AppTest) -> None:
    next(
        button for button in app.button if button.label == "Extract text"
    ).click().run()


def test_dashboard_allows_pptx_upload_and_shows_supported_contract(monkeypatch):
    upload = install_upload_mock(monkeypatch)
    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()

    upload["file"] = make_upload("slides.pptx", b"pptx-bytes")
    app.run()

    assert upload["kwargs"]["type"] == ["pdf", "txt", "pptx"]
    assert any("text-based PPTX" in item.value for item in app.caption)
    assert any("PPTX images, scanned content" in item.value for item in app.caption)

    def fake_extract_document(file_bytes, filename):
        assert file_bytes == b"pptx-bytes"
        assert filename == "slides.pptx"
        return {
            "ok": True,
            "filename": filename,
            "text": "Slide one content.",
            "sources": [{"filename": filename, "page": 1}],
            "pages": [{"page": 1, "text": "Slide one content."}],
        }

    monkeypatch.setattr(
        "services.document_service.extract_document",
        fake_extract_document,
    )
    click_extract(app)

    assert not app.exception
    assert app.session_state["setup_document"]["filename"] == "slides.pptx"
    assert "Slide one content." in [item.value for item in app.text]


def test_dashboard_pptx_failure_message_invalidates_old_document(monkeypatch):
    upload = install_upload_mock(monkeypatch)

    def fake_extract_document(file_bytes, filename):
        if filename == "old.pptx":
            return {
                "ok": True,
                "filename": filename,
                "text": "Past slide text.",
                "sources": [{"filename": filename, "page": 1}],
                "pages": [{"page": 1, "text": "Past slide text."}],
            }
        return {
            "ok": False,
            "error_code": "INVALID_PPTX",
            "message": "无法读取 PPTX，文件可能已损坏或内容不是有效的 PPTX。",
        }

    monkeypatch.setattr(
        "services.document_service.extract_document",
        fake_extract_document,
    )

    app = AppTest.from_file(str(DASHBOARD_PATH)).run()
    app.button(key="create_course_button").click().run()

    upload["file"] = make_upload("old.pptx", b"valid")
    app.run()
    click_extract(app)
    assert app.session_state["setup_document"]["filename"] == "old.pptx"

    upload["file"] = make_upload("broken.pptx", b"bad")
    app.run()
    assert "setup_document" not in app.session_state
    click_extract(app)

    assert not app.exception
    assert "setup_document" not in app.session_state
    assert any(
        "无法读取 PPTX" in item.value for item in app.error
    )
    assert not any(button.label == "Generate topics" for button in app.button)
