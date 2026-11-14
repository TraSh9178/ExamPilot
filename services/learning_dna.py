"""Descriptive, course-scoped evidence profiles; no latent ability inference."""
from dataclasses import dataclass, field

from models.schemas import AttemptResult, ExamSession, Question
from services.mastery_engine import calculate_topic_stats

DIMENSIONS = {"computation": "Computation", "conceptual": "Conceptual understanding"}
MIN_EVIDENCE = 3


@dataclass
class DimensionEvidence:
    topic_id: str
    dimension: str
    evidence: list[dict] = field(default_factory=list)

    @property
    def count(self):
        return len(self.evidence)

    @property
    def accuracy(self):
        return 100 * sum(row['correct'] for row in self.evidence) / self.count if self.count else None

    @property
    def status(self):
        if self.count < MIN_EVIDENCE:
            return "Insufficient evidence"
        if self.accuracy < 60:
            return "Needs review"
        if self.accuracy < 80:
            return "Mixed answers"
        return "Consistent answers"


def evidence_profile(attempts: list[AttemptResult], sessions: list[ExamSession],
                     questions: list[Question], mode: str) -> tuple[list[DimensionEvidence], int]:
    """Use each family's latest recorded response in the selected practice mode.

    Callers supply sessions in saved chronological order. Untagged and unanswered
    latest responses cannot support a dimension. Historical question snapshots
    supply the tag used at the time; current edits never relabel past responses.
    """
    if mode not in {"mock", "topic"}:
        raise ValueError("Invalid practice mode")
    if len({s.session_id for s in sessions}) != len(sessions):
        raise ValueError("Duplicate session ID")
    if len({q.id for q in questions}) != len(questions):
        raise ValueError("Duplicate question ID")
    # Reuse existing validation for references, duplicate answers and version chains.
    calculate_topic_stats(attempts, sessions, questions)
    by_id = {q.id: q for q in questions}
    by_session = {s.session_id: s for s in sessions}
    rank = {s.session_id: i for i, s in enumerate(sessions)}
    latest = {}
    for attempt in attempts:
        session = by_session[attempt.session_id]
        if session.mode != mode:
            continue
        question = by_id[attempt.question_id]
        root = question
        while root.version_of is not None:
            parent = by_id[root.version_of]
            if parent.topic_id != root.topic_id:
                raise ValueError("Question versions must stay in the same topic")
            root = parent
        key = (question.topic_id, root.id)
        previous = latest.get(key)
        if previous is not None and previous[0] == rank[session.session_id]:
            raise ValueError("Multiple versions of one question family in a session")
        if previous is None or rank[session.session_id] > previous[0]:
            latest[key] = (rank[session.session_id], question, attempt)
    topics = list(dict.fromkeys(q.topic_id for q in questions))
    groups = {(topic, dim): DimensionEvidence(topic, dim) for topic in topics for dim in DIMENSIONS}
    excluded = 0
    for _, question, attempt in latest.values():
        if question.cognitive_dimension is None or attempt.selected_index is None:
            excluded += 1
            continue
        groups[(question.topic_id, question.cognitive_dimension)].evidence.append({
            'question_id': question.id, 'question': question.question,
            'session_id': attempt.session_id, 'correct': attempt.is_correct,
        })
    return list(groups.values()), excluded


def comparison(computation: DimensionEvidence, conceptual: DimensionEvidence) -> str:
    if min(computation.count, conceptual.count) < MIN_EVIDENCE:
        return "Answer more different questions in both dimensions before comparing them."
    gap = computation.accuracy - conceptual.accuracy
    if gap >= 20:
        return "Computation answers are more consistent here. Review the meaning of the rules and explain why each step works."
    if gap <= -20:
        return "Conceptual answers are more consistent here. Practise calculations and check each intermediate step."
    return "The two dimensions have similar latest-answer accuracy. Try fresh questions to check whether this pattern continues."
