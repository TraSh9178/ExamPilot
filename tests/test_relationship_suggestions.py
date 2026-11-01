from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services import gemini_service
from services.relationship_suggestions import (
    apply_suggested_relationships,
    describe_suggestions,
    suggestions_key,
)

PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "4_Knowledge_Graph.py"
SUGGESTION = {"from_topic": "topic-1", "to_topic": "topic-2", "type": "related"}


def make_course() -> StudyPackage:
    return StudyPackage.model_validate(
        {
            "course_id": "course-1",
            "course_name": "Course One",
            "topics": [
                {"id": "topic-1", "name": "Limits", "summary": "Limits summary."},
                {
                    "id": "topic-2",
                    "name": "Derivatives",
                    "summary": "Derivatives summary.",
                },
            ],
            "relationships": [],
            "questions": [],
        }
    )


def make_document() -> dict:
    return {
        "ok": True,
        "filename": "notes.txt",
        "text": "Limits lead to derivatives.",
        "sources": [{"filename": "notes.txt", "page": None}],
    }


def ok_result(course: StudyPackage, relationships: list[dict]) -> dict:
    package = course.model_dump(mode="json")
    package["relationships"] = relationships
    return {
        "ok": True,
        "package": package,
        "review_required": True,
        "relationships_are_suggestions": True,
    }


def install_generate(monkeypatch, result: dict) -> list[tuple]:
    calls = []

    def fake_generate_relationships(document, package):
        calls.append((document, package))
        return result

    monkeypatch.setattr(
        gemini_service, "generate_relationships", fake_generate_relationships
    )
    return calls


def run_page(course: StudyPackage, document: dict | None = None) -> AppTest:
    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = course
    if document is not None:
        app.session_state[f"course_document_{course.course_id}"] = document
    return app.run()


def test_apply_replaces_connections_and_keeps_everything_else():
    course = make_course()

    updated = apply_suggested_relationships(course, [SUGGESTION])

    assert [
        (relation.from_topic, relation.to_topic, relation.type)
        for relation in updated.relationships
    ] == [("topic-1", "topic-2", "related")]
    assert updated.topics == course.topics
    assert updated.questions == course.questions
    assert course.relationships == []


def test_apply_rejects_suggestions_for_unknown_topics():
    with pytest.raises(ValueError):
        apply_suggested_relationships(
            make_course(),
            [{"from_topic": "topic-1", "to_topic": "missing", "type": "related"}],
        )


def test_describe_uses_topic_names_and_falls_back_to_ids():
    labels = describe_suggestions(
        make_course(),
        [SUGGESTION, {"from_topic": "topic-1", "to_topic": "gone", "type": "related"}],
    )

    assert labels == ["Limits ↔ Derivatives", "Limits ↔ gone"]


def test_page_hides_suggestions_without_saved_material():
    app = run_page(make_course())

    assert not app.exception
    assert not any(
        button.key == "suggest_relationships_course-1" for button in app.button
    )


def test_page_lists_suggestions_and_applies_them_after_confirmation(monkeypatch):
    course = make_course()
    document = make_document()
    calls = install_generate(monkeypatch, ok_result(course, [SUGGESTION]))
    app = run_page(course, document)
    assert not app.exception

    app.button(key="suggest_relationships_course-1").click().run()

    assert not app.exception
    assert calls == [(document, course)]
    assert app.session_state[suggestions_key("course-1")] == [SUGGESTION]
    assert app.session_state["current_course"].relationships == []
    assert any("Limits ↔ Derivatives" in item.value for item in app.markdown)

    app.button(key="apply_relationships_course-1").click().run()

    assert not app.exception
    applied = app.session_state["current_course"]
    assert [
        (relation.from_topic, relation.to_topic) for relation in applied.relationships
    ] == [("topic-1", "topic-2")]
    assert app.session_state["courses"][0] == applied
    assert suggestions_key("course-1") not in app.session_state
    assert any(
        "Applied 1 suggested connection." in item.value for item in app.success
    )


def test_page_discard_leaves_course_unchanged(monkeypatch):
    course = make_course()
    install_generate(monkeypatch, ok_result(course, [SUGGESTION]))
    app = run_page(course, make_document())
    app.button(key="suggest_relationships_course-1").click().run()

    app.button(key="discard_relationships_course-1").click().run()

    assert not app.exception
    assert suggestions_key("course-1") not in app.session_state
    assert app.session_state["current_course"].relationships == []


def test_page_shows_service_error_without_storing_suggestions(monkeypatch):
    install_generate(
        monkeypatch,
        {
            "ok": False,
            "error_code": "MISSING_API_KEY",
            "message": "GEMINI_API_KEY is not configured.",
        },
    )
    app = run_page(make_course(), make_document())

    app.button(key="suggest_relationships_course-1").click().run()

    assert not app.exception
    assert any(
        "GEMINI_API_KEY is not configured." in item.value for item in app.error
    )
    assert suggestions_key("course-1") not in app.session_state


def test_page_reports_empty_suggestions_and_disables_apply(monkeypatch):
    course = make_course()
    install_generate(monkeypatch, ok_result(course, []))
    app = run_page(course, make_document())

    app.button(key="suggest_relationships_course-1").click().run()

    assert not app.exception
    assert app.session_state[suggestions_key("course-1")] == []
    assert app.button(key="apply_relationships_course-1").disabled
    assert any("no evidence-supported connections" in item.value for item in app.info)


def test_page_rejects_stale_suggestions(monkeypatch):
    course = make_course()
    app = run_page(course, make_document())
    app.session_state[suggestions_key("course-1")] = [
        {"from_topic": "topic-1", "to_topic": "gone", "type": "related"}
    ]
    app.run()

    app.button(key="apply_relationships_course-1").click().run()

    assert not app.exception
    assert any("no longer match" in item.value for item in app.error)
    assert app.session_state["current_course"].relationships == []
