"""Example progress for the built-in demo courses.

A student who opens a demo course's Progress page before finishing any
practice sees this report, clearly labelled as sample data, so the page can
be demonstrated straight away. Everything is built from the course alone: no
clock, no randomness and no session state, so two builds are equal.

The page keeps the result in local variables only. Nothing here is written to
session state, the course, the account or any file, and the example is never
mixed with real practice: one real graded session (in either mode) and it is
gone for good.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.schemas import ExamSession, Question, StudyPackage
from services.demo_updates import FILES
from services.exam_engine import grade_exam

MODES = ("mock", "topic")
# Example sessions per practice mode, oldest first.
SESSIONS_PER_MODE = 3
# The outcome each topic is given, in course order; the pattern repeats.
MOCK_PLAN = ("mastered", "developing", "weak", "insufficient", "developing")
# Topic practice covers only the first few topics; later ones stay unattempted.
TOPIC_PLAN = ("developing", "insufficient", "mastered", "weak")
# Different questions answered per topic, and how many of their latest answers
# are correct, so the topic lands in the planned mastery band (60% / 80%).
MAX_QUESTIONS = 6
CORRECT = {
    3: {"mastered": 3, "developing": 2, "weak": 1},
    4: {"mastered": 4, "developing": 3, "weak": 2},
    5: {"mastered": 4, "developing": 3, "weak": 2},
    6: {"mastered": 5, "developing": 4, "weak": 2},
}
INSUFFICIENT_QUESTIONS = 2


@dataclass(frozen=True)
class ExampleReport:
    """Sample practice in the shape the Progress page reads.

    ``course`` is a separate copy of the course whose learning_state carries
    the example chronology and tracked time; ``history`` maps session ids to
    ``{"session", "questions", "attempts", "result"}`` records.
    """

    course: StudyPackage
    history: dict


def is_built_in_demo(course: StudyPackage) -> bool:
    return course.course_id in FILES


def has_real_practice(course: StudyPackage, history: dict | None) -> bool:
    """True once the student has any graded session for this course.

    The saved chronology counts too, so a restored course whose history has
    not been loaded yet never falls back to the example.
    """
    return bool(history) or bool(course.learning_state.get("session_order"))


def example_report_for(course: StudyPackage, history: dict | None) -> ExampleReport | None:
    """The example for a built-in demo course with no graded session, else None."""
    if not is_built_in_demo(course) or has_real_practice(course, history):
        return None
    return build_example_report(course)


def _family_roots(course: StudyPackage, topic_id: str) -> list[Question]:
    """One question per question family (its first version), in course order."""
    return [
        question for question in course.questions
        if question.topic_id == topic_id and question.version_of is None
    ]


def _interleave(questions: list[Question]) -> list[Question]:
    """Alternate computation and conceptual questions; untagged ones go last."""
    computation = [q for q in questions if q.cognitive_dimension == "computation"]
    conceptual = [q for q in questions if q.cognitive_dimension == "conceptual"]
    untagged = [q for q in questions if q.cognitive_dimension is None]
    mixed = []
    for index in range(max(len(computation), len(conceptual))):
        mixed.extend(group[index] for group in (computation, conceptual) if index < len(group))
    return mixed + untagged


def _plan(mode: str, index: int) -> str:
    if mode == "mock":
        return MOCK_PLAN[index % len(MOCK_PLAN)]
    return TOPIC_PLAN[index] if index < len(TOPIC_PLAN) else "unattempted"


def _topic_answers(questions: list[Question], plan: str, index: int) -> list[tuple[Question, bool]]:
    """The chosen questions with their latest-answer correctness, wrong ones first."""
    if plan == "unattempted" or not questions:
        return []
    if plan == "insufficient" or len(questions) < 3:
        chosen = questions[:INSUFFICIENT_QUESTIONS]
        return [(question, position > 0) for position, question in enumerate(chosen)]
    chosen = _interleave(questions)[:MAX_QUESTIONS]
    correct = CORRECT[len(chosen)][plan]
    # Alternate which dimension takes the wrong answers so the Learning DNA
    # comparison differs from topic to topic.
    first, second = ("conceptual", "computation") if index % 2 == 0 else ("computation", "conceptual")
    wrong_order = (
        [q for q in chosen if q.cognitive_dimension == first]
        + [q for q in chosen if q.cognitive_dimension == second]
        + [q for q in chosen if q.cognitive_dimension is None]
    )
    wrong = {q.id for q in wrong_order[: len(chosen) - correct]}
    ordered = [q for q in chosen if q.id in wrong] + [q for q in chosen if q.id not in wrong]
    return [(question, question.id not in wrong) for question in ordered]


def _focus_seconds(question: Question, position: int) -> float:
    """A plausible, fixed time on one question."""
    base = 48.0 if question.cognitive_dimension == "computation" else 34.0
    return base + 7.5 * (position % 5)


def _mode_sessions(course: StudyPackage, mode: str) -> list[list[tuple[Question, bool]]]:
    """Each session's answers in order; answers are spread round-robin over the sessions."""
    sessions: list[list[tuple[Question, bool]]] = [[] for _ in range(SESSIONS_PER_MODE)]
    for index, topic in enumerate(course.topics):
        answers = _topic_answers(_family_roots(course, topic.id), _plan(mode, index), index)
        placed = []
        for position, (question, correct) in enumerate(answers):
            session = position % SESSIONS_PER_MODE
            sessions[session].append((question, correct))
            placed.append((session, question, correct))
        if len(answers) >= 3:
            # One question answered wrongly first and correctly later, so the
            # topic shows more answers than different questions.
            retry = next(
                (question for session, question, correct in reversed(placed) if session > 0 and correct),
                None,
            )
            if retry is not None:
                sessions[0].append((retry, False))
    return [answers for answers in sessions if answers]


def build_example_report(course: StudyPackage) -> ExampleReport | None:
    """Build the example from the course's own topics and questions.

    Questions awaiting review are used too: only aggregates are shown. Returns
    None when the course has nothing to practise.
    """
    by_mode = {mode: _mode_sessions(course, mode) for mode in MODES}
    history: dict = {}
    insights: dict = {}
    # Oldest first, the two modes taking turns.
    for number in range(SESSIONS_PER_MODE):
        for mode in MODES:
            if number >= len(by_mode[mode]):
                continue
            answers = by_mode[mode][number]
            questions = [question for question, _ in answers]
            session = ExamSession(
                session_id=f"example-{mode}-{number + 1}",
                mode=mode,
                question_ids=[question.id for question in questions],
            )
            picks = {
                question.id: question.correct_index if correct else (question.correct_index + 1) % 4
                for question, correct in answers
            }
            result = grade_exam(session, questions, picks)
            history[session.session_id] = {
                "session": session,
                "questions": questions,
                "attempts": result["attempts"],
                "result": result,
            }
            insights[session.session_id] = {
                question.id: {"focus_seconds": _focus_seconds(question, position)}
                for position, question in enumerate(questions)
            }
    if not history:
        return None
    data = course.model_dump(mode="json")
    data["learning_state"] = {
        **data["learning_state"],
        "session_order": list(history),
        "practice_insights": insights,
    }
    return ExampleReport(course=StudyPackage.model_validate(data), history=history)
