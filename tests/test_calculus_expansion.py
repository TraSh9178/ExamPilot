"""The expanded calculus graph and append-only upgrades preserve learner work."""
from copy import deepcopy
from pathlib import Path
import math

from streamlit.testing.v1 import AppTest
from models.schemas import StudyPackage
from services.demo_updates import demo_update
from services.graph_exploration import local_graph, related_topics
from services.postgres_store import _merge_course_packages
from services.question_editor import available_questions

ROOT = Path(__file__).resolve().parents[1]


def latest():
    return StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))


def legacy():
    data = latest().model_dump()
    data['topics'] = data['topics'][:3]
    data['relationships'] = data['relationships'][:2]
    data['questions'] = data['questions'][:30]
    data['learning_state'] = {'question_reviews': {'calc_q004': 'approved'},
        'confirmed_scope': ['calc_limits'], 'session_order': ['old-exam']}
    data['topics'][0]['summary'] = 'My saved summary'
    return StudyPackage.model_validate(data)


def test_upgrade_adds_graph_and_drafts_without_replacing_saved_content():
    old = legacy()
    before = deepcopy(old)
    updated, count = demo_update(old)
    assert old == before
    assert count == 36
    assert len(updated.topics) == 15 and len(updated.questions) == 66
    assert len(updated.relationships) == 20
    assert updated.topics[:3] == old.topics
    assert updated.questions[:30] == old.questions
    assert updated.relationships[:2] == old.relationships
    for key in ('confirmed_scope', 'session_order'):
        assert updated.learning_state[key] == old.learning_state[key]
    assert updated.learning_state['question_reviews']['calc_q004'] == 'approved'
    assert all(updated.learning_state['question_reviews'][q.id] == latest().learning_state['question_reviews'][q.id] for q in updated.questions[30:])
    assert demo_update(updated) == (updated, 0)
    # The persistence merge accepts preserved IDs and retains the original rows.
    assert _merge_course_packages(old, updated) == updated


def test_graph_only_update_is_not_lost_when_questions_already_exist():
    full = latest()
    stripped = full.model_copy(update={'relationships': full.relationships[:2]})
    updated, count = demo_update(stripped)
    assert count == 0 and updated.relationships == full.relationships
    assert updated != stripped


def test_expanded_graph_is_connected_and_prerequisites_are_acyclic():
    course = latest()
    ids = {t.id for t in course.topics}
    outgoing = {tid: [] for tid in ids}
    for edge in course.relationships:
        assert edge.type == 'prerequisite' and edge.from_topic != edge.to_topic
        outgoing[edge.from_topic].append(edge.to_topic)
    visited, visiting = set(), set()
    def visit(tid):
        assert tid not in visiting
        if tid in visited: return
        visiting.add(tid)
        for target in outgoing[tid]: visit(target)
        visiting.remove(tid)
        visited.add(tid)
    visit('calc_limits')
    assert visited == ids
    assert 'calc_fundamental_theorem' in related_topics(course, 'calc_definite_integrals')['next_topics']
    assert {'calc_differentiation_rules', 'calc_chain_rule', 'calc_implicit_differentiation'}.issubset(
        {t.id for t in local_graph(course, 'calc_chain_rule').topics})
    assert len(available_questions(course)) == 30


def test_new_topic_is_searchable_and_has_teaching_summary():
    app = AppTest.from_file(str(ROOT/'pages/4_Knowledge_Graph.py'))
    app.session_state['current_course'] = latest()
    app.run()
    app.selectbox(key='graph_focus_calculus-i-demo').set_value('calc_fundamental_theorem').run()
    assert not app.exception
    assert any(x.value == 'Fundamental Theorem of Calculus' for x in app.subheader)
    assert any('Variable upper bounds' in x.value for x in app.markdown)
    assert any('15 knowledge points' in x.value for x in app.caption)


def test_dashboard_legacy_upgrade_exposes_new_topics_and_keeps_scope():
    from tests.auth_helpers import signed_in_app
    old = legacy()
    app = signed_in_app(ROOT/'app.py').run()
    app.session_state['courses'] = [old]
    app.session_state['current_course'] = old
    app.session_state['confirmed_scope_calculus-i-demo'] = ['calc_limits']
    from models.schemas import ExamSession
    from services.exam_engine import grade_exam
    session = ExamSession(session_id='old-exam', mode='mock', question_ids=[old.questions[0].id])
    result = grade_exam(session, old.questions[:1], {old.questions[0].id: 2})
    history = {'old-exam': {'session': session, 'questions': old.questions[:1], 'result': result, 'attempts': result['attempts']}}
    app.session_state['practice_history_calculus-i-demo'] = deepcopy(history)
    app.run()
    assert not app.exception
    assert len(app.session_state['current_course'].topics) == 15
    assert app.session_state['confirmed_scope_calculus-i-demo'] == ['calc_limits']
    assert app.session_state['practice_history_calculus-i-demo'] == history


def test_new_numerical_answers_against_independent_calculations():
    qs = {q.id:q for q in latest().questions}
    def answer(slug, number=1):
        q = qs[f'calc_{slug}_q{number:02d}']
        return q.options[q.correct_index]
    assert answer('limit_laws') == str(2*2+3)
    assert answer('limit_laws',3) == str(3**2+2*3-1)
    assert answer('continuity') == str(2+2)
    assert answer('trig_limits') == str(5)
    # Numerical limits and finite differences cross-check independently of prose.
    assert math.isclose(math.sin(5e-6)/1e-6, float(answer('trig_limits')), rel_tol=1e-8)
    h=1e-5
    def slope(f,x): return (f(x+h)-f(x-h))/(2*h)
    assert math.isclose(slope(lambda x:(x*x+1)*(x-1),2), 3*2**2-2*2+1, rel_tol=1e-8)
    assert math.isclose(slope(lambda x:x/(x+1),2), 1/9, rel_tol=1e-8)
    assert math.isclose(slope(lambda x:(3*x+1)**4,1), 12*4**3, rel_tol=1e-8)
    assert math.isclose(slope(lambda x:math.sin(x*x),1), 2*math.cos(1), rel_tol=1e-8)
    assert answer('implicit_differentiation') == '−3/4'
    assert math.isclose(slope(lambda x:math.sqrt(25-x*x),3), -3/4, rel_tol=1e-8)
    assert answer('implicit_differentiation',3) == '−3/2'
    assert answer('related_rates') == '12π cm²/s'
    assert math.isclose(slope(lambda t:math.pi*(3+2*t)**2,0), 12*math.pi, rel_tol=1e-8)
    assert answer('related_rates',2) == '−3/4 m/s'
    assert answer('mean_value_theorem') == str(((9-1)/(3-1))/2).removesuffix('.0')
    assert answer('antiderivatives',3) == 'x² + 4'
    assert answer('definite_integrals') == str(int((2**2/2-2)-0))
    assert answer('definite_integrals',3) == str(2*(1/2)).removesuffix('.0')
    assert answer('fundamental_theorem',2) == str(2**3-0**3)


def test_legacy_graph_backfill_never_references_missing_topics():
    old = legacy().model_copy(update={'relationships': []})
    app = AppTest.from_file(str(ROOT/'pages/4_Knowledge_Graph.py'))
    app.session_state['current_course'] = old
    app.run()
    assert not app.exception
    restored = app.session_state['current_course']
    assert len(restored.topics) == 3 and len(restored.relationships) == 2
    StudyPackage.model_validate(restored.model_dump())
