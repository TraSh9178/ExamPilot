from collections.abc import Sequence

from models.schemas import AttemptResult, ExamSession, Question, TopicStats


def get_mastery_status(stats: TopicStats) -> str:
    """Classify mastery using the confirmed evidence-count and accuracy thresholds."""
    if stats.attempted == 0:
        return "unattempted"
    if stats.attempted < 3:
        return "insufficient_evidence"
    if stats.accuracy is None:
        raise ValueError("accuracy is required when attempted is at least 3")
    if stats.accuracy < 60:
        return "weak"
    if stats.accuracy < 80:
        return "developing"
    return "mastered"


def calculate_topic_stats(
    attempts: Sequence[AttemptResult],
    sessions: Sequence[ExamSession],
    questions: Sequence[Question],
) -> list[TopicStats]:
    """Calculate per-topic statistics separately for mock and topic practice."""
    sessions_by_id = {session.session_id: session for session in sessions}
    questions_by_id = {question.id: question for question in questions}

    stats: dict[tuple[str, str], dict[str, int]] = {}
    for question in questions:
        for mode in ("mock", "topic"):
            stats.setdefault(
                (question.topic_id, mode),
                {"correct": 0, "attempted": 0},
            )

    processed_attempts: set[tuple[str, str]] = set()
    for attempt in attempts:
        session = sessions_by_id.get(attempt.session_id)
        if session is None:
            raise ValueError(
                f"Attempt references unknown session ID: {attempt.session_id}"
            )

        question = questions_by_id.get(attempt.question_id)
        if question is None:
            raise ValueError(
                f"Attempt references unknown question ID: {attempt.question_id}"
            )

        if attempt.question_id not in session.question_ids:
            raise ValueError(
                f"Attempt question ID {attempt.question_id} is not part of "
                f"session {attempt.session_id}"
            )

        attempt_key = (attempt.session_id, attempt.question_id)
        if attempt_key in processed_attempts:
            raise ValueError(
                f"Duplicate attempt for session {attempt.session_id} and "
                f"question {attempt.question_id}"
            )
        processed_attempts.add(attempt_key)

        topic_stats = stats[(question.topic_id, session.mode)]
        topic_stats["attempted"] += 1
        if attempt.is_correct:
            topic_stats["correct"] += 1

    return [
        TopicStats(
            topic_id=topic_id,
            mode=mode,
            correct=values["correct"],
            attempted=values["attempted"],
            accuracy=(
                values["correct"] / values["attempted"] * 100
                if values["attempted"]
                else None
            ),
        )
        for (topic_id, mode), values in stats.items()
    ]
