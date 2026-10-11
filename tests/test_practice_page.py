from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import ExamSession, Question, StudyPackage
from services.exam_engine import grade_exam


PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "2_Practice_Center.py"


def make_practice_state(
    selected_index: int | None = None,
    *,
    graded: bool = True,
) -> dict:
    question = Question(
        id="question-1",
        topic_id="topic-1",
        question="What is 2 + 2?",
        options=["4", "3", "5", "6"],
        correct_index=0,
        explanation="Add two and two.",
    )
    course = StudyPackage(
        course_id="course-1",
        course_name="Introduction to Microeconomics",
        topics=[
            {
                "id": "topic-1",
                "name": "Supply and Demand",
                "summary": "A short summary.",
            }
        ],
        relationships=[],
        questions=[question],
    )
    session = ExamSession(
        session_id="session-1",
        mode="mock",
        question_ids=[question.id],
    )
    result = grade_exam(
        session,
        [question],
        {question.id: selected_index},
    )
    active_practice = {
        "settings": {
            "mode": "mock",
            "requested_count": 10,
            "confirmed_topic_ids": ["topic-1"],
            "topic_id": None,
        },
        "session": session,
        "questions": [question],
        "warning": None,
    }
    if graded:
        active_practice["result"] = result

    history = (
        {
            session.session_id: {
                "session": session,
                "questions": [question],
                "attempts": result["attempts"],
                "result": result,
            }
        }
        if graded
        else {"previous-session": {"result": "saved"}}
    )

    return {
        "current_course": course,
        "confirmed_scope_course-1": ["topic-1"],
        "active_practice_course-1": active_practice,
        "practice_history_course-1": history,
        "answer_session-1_question-1": selected_index,
    }


@pytest.mark.parametrize(
    ("selected_index", "expected_success", "expected_error", "expected_warning"),
    [
        (0, "✓ Your answer: 4", None, None),
        (1, "✓ Correct answer: 4", "✕ Your answer: 3", None),
        (None, "✓ Correct answer: 4", None, "Unanswered"),
    ],
)
def test_practice_result_displays_correct_incorrect_and_unanswered_states(
    selected_index,
    expected_success,
    expected_error,
    expected_warning,
):
    app = AppTest.from_file(str(PAGE_PATH))
    for key, value in make_practice_state(selected_index).items():
        app.session_state[key] = value

    app.run()

    assert not app.exception
    success_text = [item.value for item in app.success]
    error_text = [item.value for item in app.error]
    warning_text = [item.value for item in app.warning]
    assert expected_success in success_text
    assert ("✓ Correct answer: 4" in success_text) == (
        selected_index != 0
    )
    assert (expected_error in error_text) if expected_error else not error_text
    assert expected_warning in warning_text if expected_warning else not warning_text
    assert "Add two and two." in [item.value for item in app.markdown] + [
        item.value for item in app.text
    ]


def test_changing_settings_does_not_discard_active_practice_or_history():
    state = make_practice_state(1, graded=False)
    active = state["active_practice_course-1"]
    history = state["practice_history_course-1"]
    app = AppTest.from_file(str(PAGE_PATH))
    for key, value in state.items():
        app.session_state[key] = value

    app.run()
    app.radio(key="practice_mode_course-1").set_value("Topic Practice").run()
    app.number_input(key="practice_count_course-1").set_value(4).run()

    assert not app.exception
    assert app.session_state["active_practice_course-1"] is active
    assert app.session_state["practice_history_course-1"] is history
    assert app.session_state["answer_session-1_question-1"] == 1
    assert app.session_state["active_practice_course-1"]["session"].session_id == (
        "session-1"
    )


def test_change_settings_start_keeps_graded_history():
    state = make_practice_state(0)
    previous_session_id = "session-1"
    app = AppTest.from_file(str(PAGE_PATH))
    for key, value in state.items():
        app.session_state[key] = value

    app.run()
    app.radio(key="practice_mode_course-1").set_value("Topic Practice").run()
    app.number_input(key="practice_count_course-1").set_value(1).run()
    next(
        button
        for button in app.button
        if button.label == "Start new practice"
    ).click().run()

    assert not app.exception
    assert previous_session_id in app.session_state[
        "practice_history_course-1"
    ]
    assert app.session_state["active_practice_course-1"]["session"].session_id != (
        previous_session_id
    )
