from streamlit.testing.v1 import AppTest

from components import ai_assistant
from models.schemas import StudyPackage


def _course(course_id: str) -> StudyPackage:
    return StudyPackage(
        course_id=course_id,
        course_name=f"Course {course_id}",
        topics=[],
        relationships=[],
        questions=[],
    )


def _script():
    from components.ai_assistant import render_ai_assistant

    render_ai_assistant()


def _app(course=None) -> AppTest:
    app = AppTest.from_function(_script)
    if course is not None:
        app.session_state["current_course"] = course
    app.run()
    return app


def test_no_course_prompts_to_open_course_and_never_calls_tutor(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ai_assistant, "ask_tutor", lambda *args, **kwargs: calls.append(args)
    )
    app = _app()

    assert not app.exception
    assert any("Open a course first" in i.value for i in app.info)
    assert calls == []


def test_ask_only_on_submit_with_course_dict_and_shows_answer(monkeypatch):
    calls = []

    def fake(package, question, topic_id=None):
        calls.append((package, question, topic_id))
        return {"ok": True, "answer": "Because."}

    monkeypatch.setattr(ai_assistant, "ask_tutor", fake)
    course = _course("a")
    app = _app(course)
    assert calls == []

    app.text_area[0].set_value("Why?")
    app.run()
    assert calls == []

    app.button[0].click()
    app.run()

    assert len(calls) == 1
    package, question, topic_id = calls[0]
    assert isinstance(package, dict)
    assert package == course.model_dump()
    assert (question, topic_id) == ("Why?", None)
    assert any("Because." == m.value for m in app.markdown)

    app.run()
    assert len(calls) == 1


def test_failure_is_local_and_results_are_course_scoped(monkeypatch):
    monkeypatch.setattr(
        ai_assistant,
        "ask_tutor",
        lambda *a, **k: {"ok": False, "message": "请配置 GEMINI_API_KEY"},
    )
    app = _app(_course("a"))
    app.text_area[0].set_value("Q")
    app.run()
    app.button[0].click()
    app.run()

    assert not app.exception
    assert [e.value for e in app.error] == ["请配置 GEMINI_API_KEY"]

    app.session_state["current_course"] = _course("b")
    app.run()
    assert not app.error
    assert app.text_area[0].value == ""
