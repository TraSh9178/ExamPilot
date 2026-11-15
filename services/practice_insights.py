"""Optional reflection evidence alongside immutable answers and grades."""
from copy import deepcopy
from statistics import median
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from models.schemas import ExamSession
from services.question_editor import available_questions
from services.question_review import normalized_text

CONFIDENCE = {None: 'Not recorded', 'sure': 'Sure', 'unsure': 'Unsure', 'guessed': 'Guessed'}
REASONS = {None: 'Not recorded', 'knowledge_gap': 'Knowledge gap', 'careless': 'Careless error',
           'time_pressure': 'Time pressure', 'misread': 'Misread the question', 'other': 'Other', 'not_sure': 'Not sure yet'}


class ExplanationFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdict: Literal['supported', 'partial', 'needs_review', 'unclear']
    reasoning: str = Field(min_length=1, max_length=2000)
    next_step: str = Field(min_length=1, max_length=2000)


class ResponseInsight(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confidence: Literal['sure', 'unsure', 'guessed'] | None = None
    hints_used: int | None = Field(default=None, ge=0, le=100)
    focus_seconds: float | None = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    mistake_reason: Literal['knowledge_gap', 'careless', 'time_pressure', 'misread', 'other', 'not_sure'] | None = None
    explanation: str = Field(default='', max_length=4000)
    feedback: ExplanationFeedback | None = None
    checked_explanation: str | None = Field(default=None, max_length=4000)


def validate_insights(data, question_ids):
    if not isinstance(data, dict) or len(data) > 2000:
        raise ValueError('Invalid practice insights')
    for sid, rows in data.items():
        if not isinstance(sid, str) or not sid or len(sid) > 200 or not isinstance(rows, dict):
            raise ValueError('Invalid practice insight session')
        for qid, row in rows.items():
            if qid not in question_ids:
                raise ValueError('Practice insight references an unknown question')
            ResponseInsight.model_validate(row)


def set_session_insights(course, sid, rows):
    metadata = deepcopy(course.learning_state)
    metadata.setdefault('practice_insights', {})[sid] = {
        qid: ResponseInsight.model_validate(row).model_dump(mode='json') for qid, row in rows.items()
    }
    data = course.model_dump(mode='json')
    data['learning_state'] = metadata
    return type(course).model_validate(data)


def session_insights(course, sid):
    return course.learning_state.get('practice_insights', {}).get(sid, {})


def session_seconds(active):
    """Running time of the whole session; older state starts from its per-question totals."""
    if 'session_seconds' in active:
        return active['session_seconds']
    return min(1_000_000.0, sum(active.get('focus_seconds', {}).values()))


def clock_text(seconds):
    """Whole seconds as mm:ss, or h:mm:ss from one hour."""
    hours, rest = divmod(int(max(0, seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    return f'{hours}:{minutes:02}:{secs:02}' if hours else f'{minutes:02}:{secs:02}'


def settle_focus(active, now):
    """Count selected-question wall time, capped between interactions (not attention).

    The session clock gets the same gap uncapped, so it shows all running time.
    """
    timer = active.get('focus_timer')
    if timer is None or timer.get('since') is None:
        return
    gap = now - timer['since']
    session = session_seconds(active)  # before this gap reaches the per-question totals
    elapsed = max(0.0, min(120.0, gap))
    totals = active.setdefault('focus_seconds', {})
    qid = timer['question_id']
    totals[qid] = min(1_000_000.0, totals.get(qid, 0.0) + elapsed)
    active['session_seconds'] = min(1_000_000.0, session + max(0.0, gap))
    timer['since'] = now


def focus_question(active, qid, now):
    if qid not in active['session'].question_ids:
        raise ValueError('Unknown focus question')
    settle_focus(active, now)
    active['focus_timer'] = {'question_id': qid, 'since': now}


def before_submit(questions, answers, confidences):
    rows = []
    for number, question in enumerate(questions, 1):
        flags = []
        if answers.get(question.id) is None: flags.append('Unanswered')
        if confidences.get(question.id) in {'unsure', 'guessed'}: flags.append(CONFIDENCE[confidences[question.id]])
        if not flags: continue
        rows.append({'Question': number, 'Prompt': question.question, 'Check': ', '.join(flags)})
    return rows


def family_id(question, by_id):
    seen = set()
    while question.version_of is not None:
        if question.id in seen or question.version_of not in by_id:
            raise ValueError('Invalid question version chain')
        seen.add(question.id)
        question = by_id[question.version_of]
    return question.id


def transfer_session(course, source, source_session, confirmed_ids):
    """Curated task labels suggest structural contrast; never generate unreviewed items."""
    if source.topic_id not in confirmed_ids:
        raise ValueError('Confirm this topic in Study Plan first.')
    if not source.practice_structure:
        raise ValueError('This question has no reviewed structure label; no transfer match can be selected.')
    by_id = {q.id:q for q in course.questions}
    by_id.setdefault(source.id, source)
    used = {family_id(by_id[qid], by_id) for qid in source_session.question_ids if qid in by_id}
    used.add(family_id(source, by_id))
    candidates = [q for q in available_questions(course)
                  if q.topic_id == source.topic_id and q.practice_structure
                  and q.practice_structure != source.practice_structure
                  and family_id(q, by_id) not in used
                  and normalized_text(q.question) != normalized_text(source.question)]
    if not candidates:
        raise ValueError('No approved question with a different structure is available. Review more questions in Study Plan first.')
    question = candidates[0]
    session = ExamSession(session_id=str(uuid4()), mode='topic', question_ids=[question.id])
    return {'session':session, 'questions':[question], 'warning':None,
            'settings':{'mode':'topic','requested_count':1,'confirmed_topic_ids':sorted(confirmed_ids),'topic_id':source.topic_id},
            'transfer_from':source.id}


def analytics(questions, attempts, rows):
    by_id = {q.id:q for q in questions}
    timing = {}
    correct_guesses, assisted, unknown = [], [], []
    priorities = []
    measured = [r.get('focus_seconds') for r in rows.values() if r.get('focus_seconds') is not None]
    typical = median(measured) if measured else None
    for a in attempts:
        q = by_id[a.question_id]
        r = rows.get(q.id, {})
        seconds = r.get('focus_seconds')
        if seconds is not None:
            timing[q.topic_id] = timing.get(q.topic_id, 0.0) + seconds
        confidence = r.get('confidence')
        hints = r.get('hints_used')
        if a.is_correct and confidence == 'guessed': correct_guesses.append(q.id)
        if hints is None: unknown.append(q.id)
        elif hints: assisted.append(q.id)
        reasons, score = [], 0
        if a.selected_index is None: reasons.append('Unanswered'); score += 6
        elif not a.is_correct: reasons.append('Incorrect'); score += 5
        if confidence == 'sure' and not a.is_correct and a.selected_index is not None:
            reasons.append('Confident but incorrect'); score += 2
        if confidence in {'unsure','guessed'}:
            reasons.append('Low confidence' if confidence=='unsure' else 'Guessed'); score += 3
        if hints: reasons.append('Used hints'); score += 2
        if seconds is not None and typical is not None and seconds > max(10, typical*1.5):
            reasons.append('Longer tracked focus time'); score += 1
        if score:
            priorities.append({'question_id':q.id,'question':q.question,'topic_id':q.topic_id,
                               'priority':score,'reasons':reasons})
    return {'correct_guesses':correct_guesses,'assisted':assisted,'unknown_hints':unknown,
            'topic_seconds':timing, 'priorities':sorted(priorities,key=lambda r:(-r['priority'],r['question_id']))}


def priority_session(course, priorities, confirmed_ids, count=10):
    """Create fresh practice from approved current versions, preserving rank order."""
    by_id={q.id:q for q in course.questions}
    allowed={}
    for q in available_questions(course):
        if q.topic_id in confirmed_ids:
            allowed[family_id(q,by_id)]=q
    questions=[]
    seen=set()
    for row in priorities:
        q=by_id.get(row['question_id'])
        if q is None:continue
        root=family_id(q,by_id)
        if root in seen or root not in allowed:continue
        seen.add(root)
        questions.append(allowed[root])
        if len(questions)>=count:break
    if not questions:
        raise ValueError('No approved review questions are in the confirmed scope. Review questions or confirm your scope in Study Plan first.')
    topics={q.topic_id for q in questions}
    mode='topic' if len(topics)==1 else 'mock'
    session=ExamSession(session_id=str(uuid4()),mode=mode,question_ids=[q.id for q in questions])
    return {'session':session,'questions':questions,
            'warning':'Mixed-topic smart review is recorded in Mock Exam mode.' if mode=='mock' else None,
            'settings':{'mode':mode,'requested_count':len(questions),'confirmed_topic_ids':sorted(confirmed_ids),
                        'topic_id':next(iter(topics)) if mode=='topic' else None}}
