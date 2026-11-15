"""Dashboard interface strings follow the Chinese interface setting."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import ExamSession, Question, StudyPackage
from services.i18n import LANGUAGE_KEY

DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "pages" / "0_Dashboard.py"


def make_course() -> StudyPackage:
    return StudyPackage(
        course_id="my-course",
        course_name="Biology",
        topics=[{"id": "t1", "name": "Cells", "summary": "Summary."}],
        relationships=[],
        questions=[
            Question(
                id="q1", topic_id="t1", question="Question?",
                options=["a", "b", "c", "d"], correct_index=0, explanation="Because.",
            )
        ],
    )


def dashboard(chinese: bool, **state) -> AppTest:
    app = AppTest.from_file(str(DASHBOARD_PATH))
    app.session_state[LANGUAGE_KEY] = chinese
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


@pytest.mark.parametrize("chinese,label", [(False, "Open Study Plan"), (True, "打开学习计划")])
def test_open_study_plan_button_follows_language(chinese, label):
    course = make_course()
    app = dashboard(chinese, courses=[course], current_course=course)

    assert not app.exception
    assert app.button(key="dashboard_continue_learning").label == label


@pytest.mark.parametrize("chinese,label", [(False, "Continue practice"), (True, "继续练习")])
def test_continue_practice_button_follows_language(chinese, label):
    course = make_course()
    session = ExamSession(session_id="s1", mode="mock", question_ids=["q1"])
    app = dashboard(
        chinese, courses=[course], current_course=course,
        **{
            "confirmed_scope_my-course": ["t1"],
            "active_practice_my-course": {"session": session, "questions": course.questions},
        },
    )

    assert not app.exception
    assert app.button(key="dashboard_continue_learning").label == label


@pytest.mark.parametrize("chinese,expected", [
    (False, "Delete Biology? Its materials and practice progress will be removed from this session."),
    (True, "删除“Biology”？课程资料和练习进度将从本次会话中移除。"),
])
def test_delete_course_confirmation_follows_language(chinese, expected):
    course = make_course()
    app = dashboard(chinese, courses=[course], current_course=None)
    app.button(key="remove_course_my-course").click().run()

    assert not app.exception
    assert expected in [item.value for item in app.warning]
