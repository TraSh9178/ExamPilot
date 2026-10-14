"""Structural question checks and new-session review of graded mistakes."""
from collections.abc import Sequence
import unicodedata
from uuid import uuid4

from models.schemas import ExamSession, Question
from services.exam_engine import grade_exam


def normalized_text(value: str) -> str:
    # Preserve mathematical operators: x-1 and x1 are not the same question.
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def validate_question_content(questions: Sequence[Question], existing: Sequence[Question] = ()) -> None:
    saved_by_id = {question.id: question for question in existing}
    saved_stems = {normalized_text(question.question): question for question in existing}
    seen = set()
    for question in questions:
        stem = normalized_text(question.question)
        saved = saved_by_id.get(question.id)
        if saved is not None and saved != question:
            raise ValueError("An existing question ID cannot be reused with changed content.")
        if stem in saved_stems and saved_stems[stem] != question:
            raise ValueError("Candidate repeats a question already in this course.")
        if not stem or stem in seen:
            raise ValueError("Candidate questions repeat the same question text.")
        seen.add(stem)
        options = [normalized_text(option) for option in question.options]
        if any(not option for option in options) or len(set(options)) != 4:
            raise ValueError("Candidate options must be distinct and non-empty.")


def mistake_questions(session: ExamSession, questions: Sequence[Question], attempts) -> list[Question]:
    if len({a.question_id for a in attempts}) != len(attempts):
        raise ValueError("Duplicate answers in practice history.")
    if any(a.session_id != session.session_id for a in attempts):
        raise ValueError("Answers belong to another session.")
    answers = {a.question_id: a.selected_index for a in attempts}
    if set(answers) != set(session.question_ids):
        raise ValueError("Incomplete practice history.")
    result = grade_exam(session, questions, answers)
    missed = {entry["question_id"] for entry in result["question_results"] if not entry["is_correct"]}
    by_id = {question.id: question for question in questions}
    return [by_id[qid] for qid in session.question_ids if qid in missed]


def create_mistake_review(session: ExamSession, questions: Sequence[Question], attempts,
                          confirmed_topic_ids: Sequence[str], topic_id: str | None = None) -> dict:
    missed = mistake_questions(session, questions, attempts)
    confirmed = set(confirmed_topic_ids)
    if topic_id is not None and topic_id not in confirmed:
        raise ValueError("Review topic is outside the confirmed scope.")
    eligible = [question for question in missed if question.topic_id in confirmed
                and (topic_id is None or question.topic_id == topic_id)]
    if not eligible:
        raise ValueError("No missed questions in this confirmed topic scope.")
    review = ExamSession(session_id=str(uuid4()), mode="topic" if topic_id else "mock",
                         question_ids=[question.id for question in eligible])
    return {
        "session": review, "questions": eligible, "warning": None,
        "settings": {"mode": review.mode, "requested_count": len(eligible),
                     "confirmed_topic_ids": sorted(confirmed), "topic_id": topic_id},
    }


def question_sources(question: Question, document: dict | None) -> list[tuple[int, str]]:
    """Return only actual extracted text for cited pages; never generate excerpts."""
    if not document:
        return []
    return [(entry["page"], entry["text"]) for entry in document.get("pages", [])
            if entry.get("page") in question.source_pages and isinstance(entry.get("text"), str)]
