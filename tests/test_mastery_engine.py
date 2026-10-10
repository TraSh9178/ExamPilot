import pytest

from models.schemas import AttemptResult, ExamSession, Question, TopicStats
from services.mastery_engine import calculate_topic_stats, get_mastery_status


@pytest.fixture
def questions() -> list[Question]:
    return [
        Question(
            id="q-a1",
            topic_id="topic-a",
            question="Question A1",
            options=["A", "B", "C", "D"],
            correct_index=0,
            explanation="Explanation",
        ),
        Question(
            id="q-b1",
            topic_id="topic-b",
            question="Question B1",
            options=["A", "B", "C", "D"],
            correct_index=1,
            explanation="Explanation",
        ),
    ]


@pytest.fixture
def sessions() -> list[ExamSession]:
    return [
        ExamSession(session_id="mock-session", mode="mock", question_ids=["q-a1"]),
        ExamSession(session_id="mock-session-2", mode="mock", question_ids=["q-a1"]),
        ExamSession(session_id="topic-session", mode="topic", question_ids=["q-a1"]),
    ]


def test_calculate_topic_stats_separates_modes_and_counts_multiple_attempts(
    questions: list[Question],
    sessions: list[ExamSession],
) -> None:
    attempts = [
        AttemptResult(
            session_id="mock-session",
            question_id="q-a1",
            selected_index=0,
            is_correct=True,
        ),
        AttemptResult(
            session_id="mock-session-2",
            question_id="q-a1",
            selected_index=1,
            is_correct=False,
        ),
        AttemptResult(
            session_id="topic-session",
            question_id="q-a1",
            selected_index=1,
            is_correct=False,
        ),
    ]

    stats = calculate_topic_stats(attempts, sessions, questions)
    stats_by_key = {(stat.topic_id, stat.mode): stat for stat in stats}

    assert len(stats) == 4
    assert stats_by_key[("topic-a", "mock")] == TopicStats(
        topic_id="topic-a",
        mode="mock",
        correct=1,
        attempted=2,
        accuracy=50,
    )
    assert stats_by_key[("topic-a", "topic")] == TopicStats(
        topic_id="topic-a",
        mode="topic",
        correct=0,
        attempted=1,
        accuracy=0,
    )


def test_calculate_topic_stats_rejects_duplicate_attempt_in_same_session(
    questions: list[Question],
    sessions: list[ExamSession],
) -> None:
    attempts = [
        AttemptResult(
            session_id="mock-session",
            question_id="q-a1",
            selected_index=0,
            is_correct=True,
        ),
        AttemptResult(
            session_id="mock-session",
            question_id="q-a1",
            selected_index=1,
            is_correct=False,
        ),
    ]

    with pytest.raises(ValueError, match="Duplicate attempt"):
        calculate_topic_stats(attempts, sessions, questions)


def test_calculate_topic_stats_rejects_attempt_for_question_outside_session(
    questions: list[Question],
    sessions: list[ExamSession],
) -> None:
    attempt = AttemptResult(
        session_id="mock-session",
        question_id="q-b1",
        selected_index=1,
        is_correct=True,
    )

    with pytest.raises(ValueError, match="not part of session"):
        calculate_topic_stats([attempt], sessions, questions)


def test_calculate_topic_stats_includes_unattempted_topics_for_both_modes(
    questions: list[Question],
) -> None:
    stats = calculate_topic_stats([], [], questions)
    stats_by_key = {(stat.topic_id, stat.mode): stat for stat in stats}

    assert set(stats_by_key) == {
        ("topic-a", "mock"),
        ("topic-a", "topic"),
        ("topic-b", "mock"),
        ("topic-b", "topic"),
    }
    for stat in stats:
        assert stat.correct == 0
        assert stat.attempted == 0
        assert stat.accuracy is None


def test_calculate_topic_stats_rejects_attempt_with_unknown_session(
    questions: list[Question],
) -> None:
    attempt = AttemptResult(
        session_id="missing-session",
        question_id="q-a1",
        selected_index=0,
        is_correct=True,
    )

    with pytest.raises(ValueError, match="unknown session ID"):
        calculate_topic_stats([attempt], [], questions)


def test_calculate_topic_stats_rejects_attempt_with_unknown_question(
    sessions: list[ExamSession],
) -> None:
    attempt = AttemptResult(
        session_id="mock-session",
        question_id="missing-question",
        selected_index=0,
        is_correct=True,
    )

    with pytest.raises(ValueError, match="unknown question ID"):
        calculate_topic_stats([attempt], sessions, [])


@pytest.mark.parametrize(
    ("attempted", "accuracy", "expected_status"),
    [
        (0, None, "unattempted"),
        (1, 100, "insufficient_evidence"),
        (2, 100, "insufficient_evidence"),
        (3, 59.99, "weak"),
        (3, 60, "developing"),
        (3, 79.99, "developing"),
        (3, 80, "mastered"),
    ],
)
def test_get_mastery_status_uses_attempt_count_and_accuracy_thresholds(
    attempted: int,
    accuracy: float | None,
    expected_status: str,
) -> None:
    stats = TopicStats(
        topic_id="topic-a",
        mode="mock",
        correct=0,
        attempted=attempted,
        accuracy=accuracy,
    )

    assert get_mastery_status(stats) == expected_status


def test_get_mastery_status_rejects_missing_accuracy_with_enough_attempts() -> None:
    stats = TopicStats(
        topic_id="topic-a",
        mode="mock",
        correct=0,
        attempted=3,
        accuracy=None,
    )

    with pytest.raises(ValueError, match="accuracy is required"):
        get_mastery_status(stats)
