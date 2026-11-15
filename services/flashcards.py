"""Flashcard decks built from a course and its practice history.

Pure logic with no Streamlit imports, so the decks can be unit-tested. The
page turns these cards into one-at-a-time review; the labels are English
source strings that the page passes through tr().
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from models.schemas import AttemptResult, Question, StudyPackage, TopicStats
from services.anki_export_service import get_weak_topic_ids
from services.mastery_engine import calculate_topic_stats
from services.question_editor import available_questions

# Offered in this order; empty decks are left out.
DECK_ORDER = ("mistakes", "weak", "ideas", "all")
# The deck a student starts on: the first non-empty one of these.
DEFAULT_ORDER = ("mistakes", "weak", "all")
DECK_LABELS = {
    "mistakes": "My mistakes",
    "weak": "Weak topics",
    "ideas": "Key ideas",
    "all": "All questions",
}


@dataclass(frozen=True)
class Flashcard:
    """One card: a practice question, or a topic's key idea."""

    kind: str  # "question" or "idea"
    topic_id: str
    topic_name: str
    question: Question | None = None
    summary: str = ""
    # Set when the latest attempt at this question was wrong or left blank.
    mistake: bool = False
    last_choice: int | None = None

    @property
    def ident(self) -> str:
        """Stable identity for review state; never shown to students."""
        if self.question is not None:
            return f"question:{self.question.id}"
        return f"idea:{self.topic_id}"


def option_letter(index: int) -> str:
    return chr(ord("A") + index)


def answer_text(question: Question) -> str:
    """The correct option with its letter, e.g. "B. 4"."""
    index = question.correct_index
    return f"{option_letter(index)}. {question.options[index]}"


def _records(history: Mapping | None) -> Mapping:
    return history if isinstance(history, Mapping) else {}


def ordered_session_ids(course: StudyPackage, history: Mapping | None) -> list[str]:
    """Oldest first: the saved session order, then sessions added since."""
    records = _records(history)
    saved = course.learning_state.get("session_order", [])
    ordered = [sid for sid in dict.fromkeys(saved) if sid in records]
    ordered.extend(sid for sid in records if sid not in ordered)
    return ordered


def latest_attempts(course: StudyPackage, history: Mapping | None) -> dict[str, tuple[int, int, AttemptResult]]:
    """Question ID -> (session rank, position, attempt) of its newest attempt."""
    records = _records(history)
    latest: dict[str, tuple[int, int, AttemptResult]] = {}
    for rank, session_id in enumerate(ordered_session_ids(course, history)):
        record = records.get(session_id)
        if not isinstance(record, Mapping):
            continue
        for position, attempt in enumerate(record.get("attempts", []) or []):
            latest[attempt.question_id] = (rank, position, attempt)
    return latest


def current_mistakes(course: StudyPackage, history: Mapping | None) -> list[tuple[Question, int | None]]:
    """Available questions whose newest attempt is wrong or blank, newest first.

    Each entry carries the option chosen last time (None when left blank).
    Within one practice session the session's own question order is kept.
    """
    latest = latest_attempts(course, history)
    missed = []
    for question in available_questions(course):
        found = latest.get(question.id)
        if found is None or found[2].is_correct:
            continue
        rank, position, attempt = found
        choice = attempt.selected_index
        if choice is not None and not 0 <= choice < len(question.options):
            choice = None
        missed.append((rank, position, question, choice))
    missed.sort(key=lambda item: (-item[0], item[1]))
    return [(question, choice) for _, _, question, choice in missed]


def practice_topic_stats(course: StudyPackage, history: Mapping | None) -> list[TopicStats]:
    """Topic statistics built the same way the export has always built them.

    Raises ValueError when the history cannot be read.
    """
    records = list(_records(history).values())
    sessions = [record["session"] for record in records]
    attempts = [attempt for record in records for attempt in record["attempts"]]
    questions_by_id = {question.id: question for question in course.questions}
    for record in records:
        for question in record["questions"]:
            questions_by_id[question.id] = question
    return calculate_topic_stats(
        attempts=attempts,
        sessions=sessions,
        questions=list(questions_by_id.values()),
    )


def weak_topic_ids(course: StudyPackage, history: Mapping | None) -> set[str]:
    """Topics that are weak or developing in either practice mode.

    A history that cannot be read counts as no weak topics.
    """
    if not _records(history):
        return set()
    try:
        stats = practice_topic_stats(course, history)
        return get_weak_topic_ids(stats, "mock") | get_weak_topic_ids(stats, "topic")
    except ValueError:
        return set()


def build_decks(course: StudyPackage, history: Mapping | None) -> dict[str, list[Flashcard]]:
    """Return the non-empty decks in DECK_ORDER."""
    names = {topic.id: topic.name for topic in course.topics}
    questions = available_questions(course)
    mistakes = current_mistakes(course, history)
    last_choice = {question.id: choice for question, choice in mistakes}
    weak = weak_topic_ids(course, history)

    def card(question: Question) -> Flashcard:
        return Flashcard(
            kind="question",
            topic_id=question.topic_id,
            topic_name=names.get(question.topic_id, ""),
            question=question,
            mistake=question.id in last_choice,
            last_choice=last_choice.get(question.id),
        )

    weak_mistakes = [question for question, _ in mistakes if question.topic_id in weak]
    weak_rest = [
        question for question in questions
        if question.topic_id in weak and question.id not in last_choice
    ]
    topics = [topic for topic in course.topics if topic.summary.strip()]
    ideas = [topic for topic in topics if topic.id in weak]
    ideas += [topic for topic in topics if topic.id not in weak]

    decks = {
        "mistakes": [card(question) for question, _ in mistakes],
        "weak": [card(question) for question in weak_mistakes + weak_rest],
        "ideas": [
            Flashcard(kind="idea", topic_id=topic.id, topic_name=topic.name, summary=topic.summary.strip())
            for topic in ideas
        ],
        "all": [card(question) for question in questions],
    }
    return {key: decks[key] for key in DECK_ORDER if decks[key]}


def default_deck(decks: Mapping[str, list[Flashcard]]) -> str | None:
    """First non-empty deck of mistakes, weak topics, all questions."""
    for key in DEFAULT_ORDER:
        if decks.get(key):
            return key
    return next((key for key in DECK_ORDER if decks.get(key)), None)
