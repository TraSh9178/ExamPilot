from copy import deepcopy
from pathlib import Path

import pytest
from models.schemas import ExamSession, StudyPackage
from services.demo_updates import FILES, demo_update
from services.practice_insights import transfer_session
from services.question_editor import available_questions
from services.math_text import math_markdown

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename', list(FILES.values()))
def test_each_available_demo_question_has_a_different_structure_for_a_one_question_session(filename):
    course = StudyPackage.model_validate_json((ROOT/'data'/filename).read_text(encoding='utf-8'))
    scope = [topic.id for topic in course.topics]
    for question in available_questions(course):
        session = ExamSession(session_id='original',mode='topic',question_ids=[question.id])
        transfer = transfer_session(course,question,session,scope)
        alternate = transfer['questions'][0]
        assert alternate.id != question.id and alternate.topic_id == question.topic_id
        assert alternate.practice_structure != question.practice_structure
        assert alternate in available_questions(course)


def test_catalog_review_preserves_rejections_edits_history_and_scope():
    course = StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))
    data = course.model_dump()
    data['learning_state']['question_reviews']['calc_q004'] = 'flagged'
    data['learning_state']['question_reviews']['calc_q013'] = 'pending'
    next(q for q in data['questions'] if q['id']=='calc_q013')['question'] += ' Learner edit.'
    data['learning_state']['question_reviews']['calc_q022'] = 'pending'
    data['learning_state']['confirmed_scope'] = ['calc_limits']
    data['learning_state']['session_order'] = ['old-session']
    old = StudyPackage.model_validate(data)
    before = deepcopy(old)
    updated, added = demo_update(old)
    assert added == 0 and old == before and updated.questions == old.questions
    assert updated.learning_state['question_reviews']['calc_q004'] == 'flagged'
    assert updated.learning_state['question_reviews']['calc_q013'] == 'pending'
    assert updated.learning_state['question_reviews']['calc_q022'] == 'approved'
    assert updated.learning_state['confirmed_scope'] == ['calc_limits']
    assert updated.learning_state['session_order'] == ['old-session']


def test_legacy_missing_labels_supports_transfer_without_mutating_saved_questions():
    course = StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))
    rows = [q.model_copy(update={'practice_structure':None,'cognitive_dimension':None,'hints':[]}) for q in course.questions]
    metadata = deepcopy(course.learning_state)
    metadata['question_reviews']['calc_q004'] = 'pending'
    old = course.model_copy(update={'questions':rows,'learning_state':metadata})
    updated,_ = demo_update(old)
    assert updated.questions == old.questions
    source = updated.questions[0]
    session = ExamSession(session_id='old',mode='topic',question_ids=[source.id])
    followup = transfer_session(updated,source,session,['calc_limits'])
    assert followup['questions'][0].id == 'calc_q004'
    assert source.practice_structure is None


def test_known_summary_formulas_use_math_delimiters_and_protect_existing_math_and_code():
    original = 'With angles in radians, lim(x→0) sin(x)/x = 1.'
    assert math_markdown(original) == r'With angles in radians, $\lim_{x\to0}\frac{\sin x}{x}=1$.'
    text = r'Already $f(x)$ and `f(x)` and ```f(x)```.'
    assert math_markdown(text) == text
