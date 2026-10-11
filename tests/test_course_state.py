from pathlib import Path

from streamlit.testing.v1 import AppTest

from models.schemas import AttemptResult, ExamSession, StudyPackage
from services.course_state import (
    initialize_courses,
    save_course,
    select_course,
)
from services.mastery_engine import calculate_topic_stats


def make_course(course_id: str, name: str) -> StudyPackage:
    return StudyPackage.model_validate(
        {
            "course_id": course_id,
            "course_name": name,
            "topics": [
                {"id": f"{course_id}-topic", "name": "Topic", "summary": ""}
            ],
            "relationships": [],
            "questions": [
                {
                    "id": f"{course_id}-question",
                    "topic_id": f"{course_id}-topic",
                    "question": "Question",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "",
                }
            ],
        }
    )


def add_question(course: StudyPackage, question_id: str) -> StudyPackage:
    new_question = course.questions[0].model_copy(
        update={"id": question_id, "question": "Generated question"}
    )
    return StudyPackage.model_validate(
        {
            **course.model_dump(),
            "questions": [
                *course.questions,
                new_question,
            ],
        }
    )


def test_save_course_keeps_multiple_courses_and_selects_each() -> None:
    state = {}
    first = make_course("course-1", "First course")
    second = make_course("course-2", "Second course")

    save_course(state, first)
    save_course(state, second)

    assert [course.course_id for course in state["courses"]] == [
        "course-1",
        "course-2",
    ]
    assert select_course(state, "course-1") == first
    assert select_course(state, "course-2") == second
    assert state["current_course"] == second


def test_save_course_replaces_existing_course_without_duplicates() -> None:
    state = {}
    original = make_course("demo", "Demo")
    updated = add_question(original, "demo-question-new")

    save_course(state, original)
    save_course(state, updated)

    assert state["courses"] == [updated]
    assert state["current_course"] == updated


def test_initialize_courses_migrates_existing_single_course() -> None:
    legacy_course = make_course("legacy", "Legacy course")
    state = {"current_course": legacy_course}

    initialize_courses(state)
    initialize_courses(state)

    assert state["courses"] == [legacy_course]
    assert state["current_course"] == legacy_course


def test_generated_question_update_survives_course_switches() -> None:
    state = {}
    first = make_course("course-1", "First course")
    second = make_course("course-2", "Second course")
    updated_first = add_question(first, "course-1-question-new")

    save_course(state, first)
    save_course(state, second)
    save_course(state, updated_first)
    select_course(state, "course-2")

    assert select_course(state, "course-1").questions == updated_first.questions
    assert len(state["courses"]) == 2


def test_scope_practice_history_and_mastery_are_course_specific() -> None:
    first = make_course("course-1", "First course")
    second = make_course("course-2", "Second course")
    first_scope = f"confirmed_scope_{first.course_id}"
    second_scope = f"confirmed_scope_{second.course_id}"
    first_history = f"practice_history_{first.course_id}"
    second_history = f"practice_history_{second.course_id}"
    state = {
        first_scope: ["course-1-topic"],
        second_scope: ["course-2-topic"],
        first_history: {"session-1": {"course_id": first.course_id}},
        second_history: {"session-2": {"course_id": second.course_id}},
    }

    assert state[first_scope] != state[second_scope]
    assert state[first_history] != state[second_history]

    first_session = ExamSession(
        session_id="first-session",
        mode="mock",
        question_ids=["course-1-question"],
    )
    first_attempt = AttemptResult(
        session_id="first-session",
        question_id="course-1-question",
        selected_index=0,
        is_correct=True,
    )
    first_stats = calculate_topic_stats(
        [first_attempt],
        [first_session],
        first.questions,
    )
    second_stats = calculate_topic_stats(
        [],
        [],
        second.questions,
    )

    assert next(
        stat for stat in first_stats if stat.mode == "mock"
    ).attempted == 1
    assert next(
        stat for stat in second_stats if stat.mode == "mock"
    ).attempted == 0


def test_dashboard_renders_all_saved_courses_and_deduplicates_demo() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    assert not app.exception

    app.button[0].click().run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert len(
        [button for button in app.button if button.label == "Open course"]
    ) == 1

    first = make_course("course-1", "First course")
    second = make_course("course-2", "Second course")
    save_course(app.session_state, first)
    save_course(app.session_state, second)
    app.run()

    assert "First course" in [header.value for header in app.subheader]
    assert "Second course" in [header.value for header in app.subheader]
    open_buttons = [
        button for button in app.button if button.label == "Open course"
    ]
    assert len(open_buttons) == 3

    next(
        button
        for button in open_buttons
        if button.key == "open_course_course-1"
    ).click().run()
    assert not app.exception
    assert app.session_state["current_course"].course_id == "course-1"
    assert "First course" in [header.value for header in app.subheader]

    second_app = AppTest.from_file(str(app_path)).run()
    save_course(second_app.session_state, first)
    save_course(second_app.session_state, second)
    second_app.run()
    open_buttons = [
        button for button in second_app.button if button.label == "Open course"
    ]
    assert len(open_buttons) == 2
    next(
        button
        for button in open_buttons
        if button.key == "open_course_course-2"
    ).click().run()
    assert not second_app.exception
    assert second_app.session_state["current_course"].course_id == "course-2"
    assert "Second course" in [header.value for header in second_app.subheader]
