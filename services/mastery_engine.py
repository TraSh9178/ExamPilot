from collections.abc import Sequence

from models.schemas import AttemptResult, ExamSession, Question, TopicStats


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
