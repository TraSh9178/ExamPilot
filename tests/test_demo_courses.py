from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import AttemptResult, StudyPackage
from services.course_state import save_course, select_course
from services.exam_engine import create_exam, grade_exam
from services.mastery_engine import calculate_topic_stats, get_mastery_status


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIRECTORY = ROOT / "data"


def load_demo(filename: str) -> StudyPackage:
    return StudyPackage.model_validate_json(
        (DEMO_DIRECTORY / filename).read_text(encoding="utf-8")
    )


def test_both_demo_packages_validate_and_have_distinct_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    economics = load_demo("sample_course.json")
    calculus = load_demo("calculus_i_demo.json")

    assert economics.course_id == "econ101"
    assert economics.course_name == "Introduction to Microeconomics"
    assert calculus.course_id == "calculus-i-demo"
    assert [topic.name for topic in calculus.topics] == [
        "Limits",
        "Derivatives",
        "Applications of Derivatives",
    ]
    assert len(calculus.questions) >= 3
    assert [
        question.correct_index for question in calculus.questions
    ] == [2, 0, 2]
    assert [
        question.options[question.correct_index]
        for question in calculus.questions
    ] == ["4", "3x² − 5", "x = 2"]

    economics_topic_ids = {topic.id for topic in economics.topics}
    calculus_topic_ids = {topic.id for topic in calculus.topics}
    economics_question_ids = {question.id for question in economics.questions}
    calculus_question_ids = {question.id for question in calculus.questions}

    assert economics_topic_ids.isdisjoint(calculus_topic_ids)
    assert economics_question_ids.isdisjoint(calculus_question_ids)
    assert calculus.relationships == []


def test_calculus_demo_can_be_practiced_and_graded_offline() -> None:
    calculus = load_demo("calculus_i_demo.json")

    exam = create_exam(
        package=calculus,
        mode="mock",
        requested_count=len(calculus.questions),
        confirmed_topic_ids=[topic.id for topic in calculus.topics],
    )
    expected_answers = {
        question.id: question.correct_index
        for question in exam["questions"]
    }

    result = grade_exam(
        exam["session"],
        exam["questions"],
        expected_answers,
    )

    assert result["correct_count"] == 3
    assert result["total_count"] == 3
    assert result["accuracy"] == 100
    assert all(review["is_correct"] for review in result["question_results"])
    assert all(
        review["explanation"]
        for review in result["question_results"]
    )
    assert [
        review["correct_index"]
        for review in result["question_results"]
    ] == [
        question.correct_index for question in exam["questions"]
    ]


def test_demo_course_state_and_mastery_remain_isolated() -> None:
    economics = load_demo("sample_course.json")
    calculus = load_demo("calculus_i_demo.json")
    state = {}

    save_course(state, economics)
    save_course(state, calculus)
    saved_history = {"existing-session": {"score": 100}}
    saved_practice = {"settings": {"mode": "mock"}}
    state[f"practice_history_{calculus.course_id}"] = saved_history
    state[f"active_practice_{calculus.course_id}"] = saved_practice
    save_course(state, load_demo("calculus_i_demo.json"))

    assert len(state["courses"]) == 2
    assert state[f"practice_history_{calculus.course_id}"] is saved_history
    assert state[f"active_practice_{calculus.course_id}"] is saved_practice
    assert select_course(state, economics.course_id) == economics
    assert select_course(state, calculus.course_id) == calculus

    economics_topic = economics.topics[0]
    calculus_topic = calculus.topics[0]
    economics_question = next(
        question
        for question in economics.questions
        if question.topic_id == economics_topic.id
    )
    calculus_question = next(
        question
        for question in calculus.questions
        if question.topic_id == calculus_topic.id
    )
    economics_session = create_exam(
        economics,
        "mock",
        1,
        [economics_topic.id],
    )["session"]
    calculus_session = create_exam(
        calculus,
        "mock",
        1,
        [calculus_topic.id],
    )["session"]
    assert economics_session.question_ids == [economics_question.id]
    assert calculus_session.question_ids == [calculus_question.id]

    economics_scope_key = f"confirmed_scope_{economics.course_id}"
    calculus_scope_key = f"confirmed_scope_{calculus.course_id}"
    economics_history_key = f"practice_history_{economics.course_id}"
    calculus_history_key = f"practice_history_{calculus.course_id}"
    state[economics_scope_key] = [economics_topic.id]
    state[calculus_scope_key] = [calculus_topic.id]
    state[economics_history_key] = {
        "econ-session": {
            "session": economics_session,
            "questions": [economics_question],
            "attempts": [
                AttemptResult(
                    session_id=economics_session.session_id,
                    question_id=economics_question.id,
                    selected_index=economics_question.correct_index,
                    is_correct=True,
                )
            ],
        }
    }
    state[calculus_history_key] = {
        "calc-session": {
            "session": calculus_session,
            "questions": [calculus_question],
            "attempts": [
                AttemptResult(
                    session_id=calculus_session.session_id,
                    question_id=calculus_question.id,
                    selected_index=calculus_question.correct_index,
                    is_correct=True,
                )
            ],
        }
    }

    assert state[economics_scope_key] == [economics_topic.id]
    assert state[calculus_scope_key] == [calculus_topic.id]
    for course, history_key, topic in (
        (economics, economics_history_key, economics_topic),
        (calculus, calculus_history_key, calculus_topic),
    ):
        history = state[history_key]
        stats = calculate_topic_stats(
            attempts=[
                attempt
                for record in history.values()
                for attempt in record["attempts"]
            ],
            sessions=[
                record["session"] for record in history.values()
            ],
            questions=course.questions,
        )
        topic_stats = next(
            stat
            for stat in stats
            if stat.topic_id == topic.id and stat.mode == "mock"
        )
        assert topic_stats.attempted == 1
        assert topic_stats.correct == 1


def test_one_course_attempt_does_not_change_other_course_mastery() -> None:
    economics = load_demo("sample_course.json")
    calculus = load_demo("calculus_i_demo.json")
    economics_topic = economics.topics[0]
    calculus_topic = calculus.topics[0]
    calculus_question = next(
        question
        for question in calculus.questions
        if question.topic_id == calculus_topic.id
    )
    calculus_session = create_exam(
        calculus,
        "mock",
        1,
        [calculus_topic.id],
    )["session"]
    calculus_attempt = AttemptResult(
        session_id=calculus_session.session_id,
        question_id=calculus_question.id,
        selected_index=calculus_question.correct_index,
        is_correct=True,
    )
    histories = {
        economics.course_id: {
            "sessions": [],
            "attempts": [],
        },
        calculus.course_id: {
            "sessions": [calculus_session],
            "attempts": [calculus_attempt],
        },
    }

    calculus_stats = calculate_topic_stats(
        histories[calculus.course_id]["attempts"],
        histories[calculus.course_id]["sessions"],
        calculus.questions,
    )
    economics_stats = calculate_topic_stats(
        histories[economics.course_id]["attempts"],
        histories[economics.course_id]["sessions"],
        economics.questions,
    )
    calculus_mastery = next(
        stat
        for stat in calculus_stats
        if stat.topic_id == calculus_topic.id and stat.mode == "mock"
    )
    economics_mastery = next(
        stat
        for stat in economics_stats
        if stat.topic_id == economics_topic.id and stat.mode == "mock"
    )

    assert calculus_mastery.attempted == 1
    assert get_mastery_status(calculus_mastery) == "insufficient_evidence"
    assert economics_mastery.attempted == 0
    assert get_mastery_status(economics_mastery) == "unattempted"

    state = {}
    save_course(state, economics)
    save_course(state, calculus)
    state[f"practice_history_{calculus.course_id}"] = histories[
        calculus.course_id
    ]
    select_course(state, economics.course_id)
    assert state["practice_history_calculus-i-demo"] == histories[
        "calculus-i-demo"
    ]
    select_course(state, calculus.course_id)
    assert state["practice_history_calculus-i-demo"] == histories[
        "calculus-i-demo"
    ]


def test_homepage_loads_both_demos_reuses_ids_and_opens_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app_path = ROOT / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    assert not app.exception

    assert [
        course.course_id for course in app.session_state["courses"]
    ] == ["econ101", "calculus-i-demo"]
    assert "Introduction to Microeconomics" in [
        header.value for header in app.subheader
    ]
    assert "Calculus I Demo" in [
        header.value for header in app.subheader
    ]

    app.run()
    assert not app.exception
    assert [
        course.course_id for course in app.session_state["courses"]
    ] == ["econ101", "calculus-i-demo"]
    assert len(
        [button for button in app.button if button.label == "Open course"]
    ) == 2

    economics_button = next(
        button
        for button in app.button
        if button.key == "open_course_econ101"
    )
    economics_button.click().run()
    assert not app.exception
    assert app.session_state["current_course"].course_id == "econ101"
    assert "Introduction to Microeconomics" in [
        header.value for header in app.subheader
    ]

    calculus_app = AppTest.from_file(str(app_path)).run()
    next(
        button
        for button in calculus_app.button
        if button.key == "open_course_calculus-i-demo"
    ).click().run()
    assert not calculus_app.exception
    assert calculus_app.session_state["current_course"].course_id == (
        "calculus-i-demo"
    )
    assert "Calculus I Demo" in [
        header.value for header in calculus_app.subheader
    ]
