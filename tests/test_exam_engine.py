import pytest

from models.schemas import ExamSession, StudyPackage
from services.exam_engine import create_exam, grade_exam


@pytest.fixture
def package() -> StudyPackage:
    return StudyPackage.model_validate(
        {
            "course_id": "course-1",
            "course_name": "Test Course",
            "topics": [
                {"id": "topic-a", "name": "A", "summary": "Topic A"},
                {"id": "topic-b", "name": "B", "summary": "Topic B"},
            ],
            "relationships": [],
            "questions": [
                {
                    "id": "q1",
                    "topic_id": "topic-a",
                    "question": "Question 1",
                    "options": ["A1", "B1", "C1", "D1"],
                    "correct_index": 1,
                    "explanation": "Explanation 1",
                },
                {
                    "id": "q2",
                    "topic_id": "topic-b",
                    "question": "Question 2",
                    "options": ["A2", "B2", "C2", "D2"],
                    "correct_index": 0,
                    "explanation": "Explanation 2",
                },
                {
                    "id": "q3",
                    "topic_id": "topic-a",
                    "question": "Question 3",
                    "options": ["A3", "B3", "C3", "D3"],
                    "correct_index": 3,
                    "explanation": "Explanation 3",
                },
            ],
        }
    )


def test_create_exam_limits_questions_to_confirmed_topics(package: StudyPackage) -> None:
    session, questions, warning = create_exam(
        package, "mock", 1, ["topic-b", "topic-a"]
    )

    assert isinstance(session, ExamSession)
    assert session.mode == "mock"
    assert session.question_ids == ["q2"]
    assert [question.id for question in questions] == ["q2"]
    assert warning is None


def test_create_mock_exam_rotates_across_confirmed_topics_without_duplicates(
    package: StudyPackage,
) -> None:
    session, questions, warning = create_exam(
        package, "mock", 3, ["topic-a", "topic-b"]
    )

    assert [question.topic_id for question in questions] == [
        "topic-a",
        "topic-b",
        "topic-a",
    ]
    assert session.question_ids == ["q1", "q2", "q3"]
    assert len(session.question_ids) == len(set(session.question_ids))
    assert warning is None


def test_create_exam_topic_mode_can_narrow_to_a_confirmed_topic(
    package: StudyPackage,
) -> None:
    session, questions, warning = create_exam(
        package, "topic", 5, ["topic-a", "topic-b"], topic_id="topic-b"
    )

    assert session.question_ids == ["q2"]
    assert [question.id for question in questions] == ["q2"]
    assert warning is not None
    assert "only 1 are available" in warning


@pytest.mark.parametrize(
    ("confirmed_topic_ids", "topic_id", "message"),
    [
        ([], None, "at least one"),
        (["topic-a", "topic-a"], None, "duplicates"),
        (["missing"], None, "Unknown confirmed topic"),
        (["topic-a", "topic-b"], None, "topic_id is required"),
        (["topic-a"], "topic-b", "included in confirmed_topic_ids"),
    ],
)
def test_create_exam_rejects_invalid_topic_scope(
    package: StudyPackage,
    confirmed_topic_ids: list[str],
    topic_id: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        create_exam(
            package,
            "topic",
            1,
            confirmed_topic_ids,
            topic_id=topic_id,
        )


def test_create_exam_rejects_unknown_mode_and_nonpositive_count(
    package: StudyPackage,
) -> None:
    with pytest.raises(ValueError, match="mode"):
        create_exam(package, "practice", 1, ["topic-a"])
    with pytest.raises(ValueError, match="positive integer"):
        create_exam(package, "mock", 0, ["topic-a"])


def test_create_exam_rejects_confirmed_scope_without_available_questions(
    package: StudyPackage,
) -> None:
    empty_package = package.model_copy(update={"questions": []})

    with pytest.raises(ValueError, match="No questions are available"):
        create_exam(empty_package, "mock", 1, ["topic-a"])


def test_grade_exam_counts_unanswered_questions_and_returns_question_results(
    package: StudyPackage,
) -> None:
    session, questions, _ = create_exam(package, "mock", 3, ["topic-a", "topic-b"])

    result = grade_exam(session, questions, {"q1": 1, "q2": 2, "q3": None})

    assert result["session_id"] == session.session_id
    assert result["correct_count"] == 1
    assert result["total_count"] == 3
    assert result["accuracy"] == pytest.approx(100 / 3)
    attempts = result["attempts"]
    assert [attempt.question_id for attempt in attempts] == ["q1", "q2", "q3"]
    assert [attempt.is_correct for attempt in attempts] == [True, False, False]
    assert attempts[2].selected_index is None
    question_results = result["question_results"]
    assert question_results[0]["correct_answer"] == "B1"
    assert question_results[0]["explanation"] == "Explanation 1"
    assert question_results[2]["selected_index"] is None
    assert question_results[2]["is_correct"] is False
    assert "review" not in result


def test_grade_exam_rejects_answers_outside_session_and_invalid_indices(
    package: StudyPackage,
) -> None:
    session, questions, _ = create_exam(package, "mock", 1, ["topic-a"])

    with pytest.raises(ValueError, match="outside the session"):
        grade_exam(session, questions, {"unknown": 0})
    with pytest.raises(ValueError, match="index from 0 to 3"):
        grade_exam(session, questions, {"q1": 4})
    with pytest.raises(ValueError, match="index from 0 to 3"):
        grade_exam(session, questions, {"q1": True})


def test_grade_exam_requires_an_entry_for_every_session_question(
    package: StudyPackage,
) -> None:
    session, questions, _ = create_exam(package, "mock", 2, ["topic-a", "topic-b"])

    with pytest.raises(ValueError, match="missing question ID"):
        grade_exam(session, questions, {"q1": 1})
