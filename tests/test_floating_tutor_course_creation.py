import json
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

from services import gemini_service
from tests.auth_helpers import signed_in_app


def test_generated_course_is_immediately_available_to_global_tutor(monkeypatch):
    uploaded = SimpleNamespace(
        name="notes.txt", getvalue=lambda: b"A course about opportunity cost."
    )
    monkeypatch.setattr(st, "file_uploader", lambda *_args, **_kwargs: uploaded)
    generated_ids = []

    def generate_topics(document, course_id, course_name):
        generated_ids.append(course_id)
        return {
            "ok": True,
            "package": {
                "course_id": course_id,
                "course_name": course_name,
                "topics": [
                    {
                        "id": "opportunity-cost",
                        "name": "Opportunity cost",
                        "summary": document["text"],
                    }
                ],
                "relationships": [],
                "questions": [],
            },
        }

    monkeypatch.setattr(gemini_service, "generate_topics", generate_topics)
    app = signed_in_app(Path(__file__).resolve().parents[1] / "app.py").run()
    assert not app.exception
    assert json.loads(app.get("bidi_component")[0].proto.json)["course_id"] is None
    app.button(key="create_course_button").click().run()
    app.text_input(key="setup_course_name").set_value("New course").run()
    next(button for button in app.button if button.label == "Extract text").click().run()
    next(button for button in app.button if button.label == "Generate topics").click().run()

    assert not app.exception
    assert len(generated_ids) == 1
    tutor_data = json.loads(app.get("bidi_component")[0].proto.json)
    assert tutor_data["course_id"] == generated_ids[0]
    assert tutor_data["course_name"] == "New course"
    assert tutor_data["messages"] == []
    assert any("Topics generated." in notice.value for notice in app.success)
