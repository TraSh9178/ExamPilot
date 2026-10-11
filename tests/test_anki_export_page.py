import csv
from io import StringIO
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from models.schemas import AttemptResult, ExamSession, StudyPackage


ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "pages" / "5_Export_Anki.py"


def _python_basics_course() -> StudyPackage:
    path = ROOT / "data" / "demo_python_basics.json"
    return StudyPackage.model_validate_json(path.read_text(encoding="utf-8"))


def _app_with_course(course: StudyPackage | None = None) -> AppTest:
    app = AppTest.from_file(str(PAGE_PATH))
    if course is not None:
        app.session_state["current_course"] = course
    return app.run()


def _add_history(
    app: AppTest,
    course: StudyPackage,
    mode: str,
    topic_id: str,
    correct_count: int,
    session_id: str,
) -> None:
    questions = [
        question for question in course.questions
        if question.topic_id == topic_id
    ]
    session = ExamSession(
        session_id=session_id,
        mode=mode,
        question_ids=[question.id for question in questions],
    )
    attempts = [
        AttemptResult(
            session_id=session_id,
            question_id=question.id,
            selected_index=question.correct_index,
            is_correct=index < correct_count,
        )
        for index, question in enumerate(questions)
    ]
    history_key = f"practice_history_{course.course_id}"
    history = (
        app.session_state[history_key]
        if history_key in app.session_state
        else {}
    )
    history[session_id] = {
        "session": session,
        "attempts": attempts,
        "questions": questions,
    }
    app.session_state[history_key] = history


def test_all_questions_exports_python_basics_nine_question_utf8_tsv():
    app = _app_with_course(_python_basics_course())

    assert not app.exception
    assert len(app.get("download_button")) == 1
    button = app.get("download_button")[0]
    assert button.label == "Download Anki TSV"
    assert "UTF-8 TSV for Anki text import only." in [
        item.value for item in app.caption
    ][0]


def test_download_payload_is_utf8_tsv_with_safe_filename_and_mime(monkeypatch):
    course = _python_basics_course()
    course.course_name = "../Python Basics/Intro"
    course.questions[0].question = "What is café?"
    download_args = {}

    def capture_download_button(label, **kwargs):
        download_args.update(kwargs)

    monkeypatch.setattr(st, "download_button", capture_download_button)
    app = _app_with_course(course)

    assert not app.exception
    content = download_args["data"]
    assert isinstance(content, bytes)
    assert "café" in content.decode("utf-8")
    assert len(
        list(csv.reader(StringIO(content.decode("utf-8")), delimiter="\t"))
    ) == 9
    assert download_args["file_name"] == "anki_python_basics_intro.tsv"
    assert download_args["mime"] == "text/tab-separated-values; charset=utf-8"


def test_weak_topics_filter_uses_selected_mode_only(monkeypatch):
    download_args = {}

    def capture_download_button(label, **kwargs):
        download_args.update(kwargs)

    monkeypatch.setattr(st, "download_button", capture_download_button)
    course = _python_basics_course()
    app = _app_with_course(course)
    first_topic = course.topics[0].id
    second_topic = course.topics[1].id
    _add_history(app, course, "mock", first_topic, 0, "mock-weak")
    _add_history(app, course, "topic", first_topic, 3, "topic-mastered")
    _add_history(app, course, "topic", second_topic, 2, "topic-developing")
    app.run()

    app.radio[0].set_value("Weak Topics").run()
    assert not app.exception
    exported_rows = list(
        csv.reader(
            StringIO(download_args["data"].decode("utf-8"), newline=""),
            delimiter="\t",
        )
    )
    assert len(exported_rows) == 3
    assert all(row[2].endswith(f"topic_{first_topic}") for row in exported_rows)

    app.radio[1].set_value("Topic Practice").run()
    assert not app.exception
    exported_rows = list(
        csv.reader(
            StringIO(download_args["data"].decode("utf-8"), newline=""),
            delimiter="\t",
        )
    )
    assert len(exported_rows) == 3
    assert all(row[2].endswith(f"topic_{second_topic}") for row in exported_rows)


def test_course_history_and_filter_state_are_isolated(monkeypatch):
    download_args = {}

    def capture_download_button(label, **kwargs):
        download_args.update(kwargs)

    monkeypatch.setattr(st, "download_button", capture_download_button)
    first = _python_basics_course()
    second = first.model_copy(
        update={"course_id": "different-course", "course_name": "Other course"}
    )
    app = _app_with_course(first)
    _add_history(app, first, "mock", first.topics[0].id, 0, "first-weak")
    _add_history(app, second, "mock", second.topics[1].id, 0, "second-weak")
    app.session_state["anki_export_scope_different-course"] = "Weak Topics"
    app.session_state["current_course"] = second
    app.run()

    assert not app.exception
    assert app.session_state["anki_export_scope_different-course"] == "Weak Topics"
    assert [radio.value for radio in app.radio] == ["Weak Topics", "Mock Exam"]
    rows = list(
        csv.reader(
            StringIO(
                download_args["data"].decode("utf-8"),
                newline="",
            ),
            delimiter="\t",
        )
    )
    assert len(rows) == 3
    assert all(
        row[2].endswith(f"topic_{second.topics[1].id}") for row in rows
    )


def test_no_course_shows_empty_state_and_no_download():
    app = _app_with_course()

    assert not app.exception
    assert "Load a course from the dashboard first." in [
        item.value for item in app.info
    ]
    assert len(app.get("download_button")) == 0


def test_course_without_questions_shows_empty_state_and_no_download():
    course = StudyPackage(
        course_id="empty",
        course_name="Empty course",
        topics=[],
        relationships=[],
        questions=[],
    )
    app = _app_with_course(course)

    assert not app.exception
    assert "This course has no questions to export." in [
        item.value for item in app.info
    ]
    assert len(app.get("download_button")) == 0


def test_no_weak_topics_shows_empty_state_and_no_download():
    app = _app_with_course(_python_basics_course())
    app.radio[0].set_value("Weak Topics").run()

    assert not app.exception
    assert "No weak or developing topics in this practice mode." in [
        item.value for item in app.info
    ]
    assert len(app.get("download_button")) == 0


def test_weak_topic_without_course_questions_shows_no_matching_state():
    course = _python_basics_course()
    app = _app_with_course(course)
    old_questions = [
        course.questions[0].model_copy(
            update={
                "id": f"removed-question-{index}",
                "topic_id": "removed-topic",
            }
        )
        for index in range(3)
    ]
    session = ExamSession(
        session_id="removed-session",
        mode="mock",
        question_ids=[question.id for question in old_questions],
    )
    attempts = [
        AttemptResult(
            session_id=session.session_id,
            question_id=question.id,
            selected_index=0,
            is_correct=False,
        )
        for question in old_questions
    ]
    app.session_state[f"practice_history_{course.course_id}"] = {
        session.session_id: {
            "session": session,
            "attempts": attempts,
            "questions": old_questions,
        }
    }
    app.run()
    app.radio[0].set_value("Weak Topics").run()

    assert not app.exception
    assert "No questions match the weak or developing topics." in [
        item.value for item in app.info
    ]
    assert len(app.get("download_button")) == 0


def test_preview_uses_exported_front_back_and_card_count():
    app = _app_with_course(_python_basics_course())

    assert not app.exception
    assert any("9 cards will be exported." == c.value for c in app.caption)
    texts = [element.value for element in app.text]
    assert len(texts) == 6
    assert texts[0].startswith(_python_basics_course().questions[0].question)
    assert texts[1].startswith("Correct answer: ")
