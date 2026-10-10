from collections.abc import Mapping, Sequence
from typing import TypedDict
from uuid import uuid4

from models.schemas import AttemptResult, ExamSession, Question, StudyPackage


class QuestionReview(TypedDict):
    question_id: str
    selected_index: int | None
    correct_index: int
    correct_answer: str
    is_correct: bool
    explanation: str


class ExamCreationResult(TypedDict):
    session: ExamSession
    questions: list[Question]
    warning: str | None


class ExamGradeResult(TypedDict):
    session_id: str
    attempts: list[AttemptResult]
    question_results: list[QuestionReview]
    correct_count: int
    total_count: int
    accuracy: float


def create_exam(
    package: StudyPackage,
    mode: str,
    requested_count: int,
    confirmed_topic_ids: Sequence[str],
    topic_id: str | None = None,
) -> ExamCreationResult:
    """Create an exam limited to the topics explicitly confirmed by the user."""
    if mode not in ("mock", "topic"):
        raise ValueError("mode must be 'mock' or 'topic'")
    if isinstance(requested_count, bool) or not isinstance(requested_count, int):
        raise ValueError("requested_count must be a positive integer")
    if requested_count <= 0:
        raise ValueError("requested_count must be a positive integer")
    if (
        not isinstance(confirmed_topic_ids, Sequence)
        or isinstance(confirmed_topic_ids, (str, bytes))
        or not confirmed_topic_ids
    ):
        raise ValueError("confirmed_topic_ids must contain at least one topic ID")

    confirmed_ids = list(confirmed_topic_ids)
    if any(not isinstance(topic, str) or not topic for topic in confirmed_ids):
        raise ValueError("confirmed_topic_ids must contain only non-empty topic IDs")
    if len(confirmed_ids) != len(set(confirmed_ids)):
        raise ValueError("confirmed_topic_ids must not contain duplicates")

    available_topic_ids = {topic.id for topic in package.topics}
    unknown_topic_ids = [topic for topic in confirmed_ids if topic not in available_topic_ids]
    if unknown_topic_ids:
        raise ValueError(f"Unknown confirmed topic ID(s): {unknown_topic_ids}")

    if mode == "topic":
        if topic_id is None:
            raise ValueError("topic_id is required when mode is 'topic'")
        if not isinstance(topic_id, str) or not topic_id:
            raise ValueError("topic_id must be a non-empty topic ID")
        if topic_id not in available_topic_ids:
            raise ValueError(f"Unknown topic ID: {topic_id}")
        if topic_id not in confirmed_ids:
            raise ValueError("topic_id must be included in confirmed_topic_ids")
        scoped_topic_ids = {topic_id}
    else:
        if topic_id is not None:
            raise ValueError("topic_id can only be specified when mode is 'topic'")
        scoped_topic_ids = set(confirmed_ids)

    questions_by_topic = {
        confirmed_topic_id: [
            question
            for question in package.questions
            if question.topic_id == confirmed_topic_id
        ]
        for confirmed_topic_id in confirmed_ids
        if confirmed_topic_id in scoped_topic_ids
    }
    eligible_questions = [
        question
        for topic_questions in questions_by_topic.values()
        for question in topic_questions
    ]
    if not eligible_questions:
        raise ValueError("No questions are available in the confirmed topic scope")

    if mode == "mock":
        selected_questions = []
        topic_question_lists = list(questions_by_topic.values())
        while len(selected_questions) < requested_count:
            added_question = False
            for topic_questions in topic_question_lists:
                if topic_questions:
                    selected_questions.append(topic_questions.pop(0))
                    added_question = True
                    if len(selected_questions) == requested_count:
                        break
            if not added_question:
                break
    else:
        selected_questions = eligible_questions[:requested_count]

    warning = None
    if len(eligible_questions) < requested_count:
        warning = (
            f"Requested {requested_count} questions, but only "
            f"{len(eligible_questions)} are available in the confirmed topic scope; "
            "all available questions were included."
        )

    session = ExamSession(
        session_id=str(uuid4()),
        mode=mode,
        question_ids=[question.id for question in selected_questions],
    )
    return {
        "session": session,
        "questions": selected_questions,
        "warning": warning,
    }


def grade_exam(
    session: ExamSession,
    questions: Sequence[Question],
    selected_answers: Mapping[str, int | None],
) -> ExamGradeResult:
    """Grade an exam and return per-question attempts, review, and percentage."""
    question_ids = [question.id for question in questions]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("questions must not contain duplicate question IDs")
    if question_ids != session.question_ids:
        raise ValueError("questions must match the question IDs in the exam session")

    unknown_answer_ids = [
        question_id
        for question_id in selected_answers
        if not isinstance(question_id, str) or question_id not in session.question_ids
    ]
    if unknown_answer_ids:
        raise ValueError(
            f"selected_answers contains question ID(s) outside the session: "
            f"{unknown_answer_ids}"
        )
    attempts: list[AttemptResult] = []
    question_results: list[QuestionReview] = []
    correct_count = 0

    for question in questions:
        selected_index = selected_answers.get(question.id)
        if selected_index is not None and (
            isinstance(selected_index, bool)
            or not isinstance(selected_index, int)
            or not 0 <= selected_index <= 3
        ):
            raise ValueError(
                f"Answer for question {question.id!r} must be an index from 0 to 3 or None"
            )

        is_correct = selected_index == question.correct_index
        correct_count += is_correct
        attempts.append(
            AttemptResult(
                session_id=session.session_id,
                question_id=question.id,
                selected_index=selected_index,
                is_correct=is_correct,
            )
        )
        question_results.append(
            {
                "question_id": question.id,
                "selected_index": selected_index,
                "correct_index": question.correct_index,
                "correct_answer": question.options[question.correct_index],
                "is_correct": is_correct,
                "explanation": question.explanation,
            }
        )

    total_count = len(questions)
    accuracy = round(correct_count / total_count * 100, 2) if total_count else 0.0
    return {
        "session_id": session.session_id,
        "attempts": attempts,
        "question_results": question_results,
        "correct_count": correct_count,
        "total_count": total_count,
        "accuracy": accuracy,
    }
