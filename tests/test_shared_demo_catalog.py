from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services.demo_updates import sync_demo_catalog, FILES
from tests.test_calculus_expansion import legacy, latest
from tests.auth_helpers import signed_in_app

ROOT = Path(__file__).resolve().parents[1]


def test_new_accounts_get_identical_full_catalog_with_independent_objects():
    first, second = {}, {}
    sync_demo_catalog(first)
    sync_demo_catalog(second)
    assert first['courses'] == second['courses']
    assert {c.course_id for c in first['courses']} == set(FILES)
    calc = next(c for c in first['courses'] if c.course_id=='calculus-i-demo')
    assert len(calc.topics)==15 and len(calc.questions)==66
    calc.learning_state['confirmed_scope']=['calc_limits']
    assert first['courses'] != second['courses']
    assert second['current_course'] is None


def test_legacy_account_is_updated_without_touching_private_work():
    old = legacy()
    state = {'courses':[old], 'current_course':old,
             'confirmed_scope_calculus-i-demo':['calc_limits'],
             'practice_history_calculus-i-demo':{'old':{'score':42}},
             'active_practice_calculus-i-demo':{'draft':'keep'},
             'default_demo_courses_v3_loaded':True}
    before = deepcopy(state)
    sync_demo_catalog(state)
    assert len(state['current_course'].topics)==15
    assert len(state['current_course'].questions)==66
    assert state['current_course'].questions[:30]==old.questions
    for key in ('confirmed_scope_calculus-i-demo','practice_history_calculus-i-demo','active_practice_calculus-i-demo'):
        assert state[key]==before[key]
    snapshot=deepcopy(state)
    sync_demo_catalog(state)
    assert state==snapshot


def test_account_entering_graph_directly_gets_upgrade_before_render():
    app=signed_in_app(ROOT/'app.py').run()
    old=legacy()
    app.session_state['courses']=[old]
    app.session_state['current_course']=old
    app.switch_page('pages/4_Knowledge_Graph.py').run()
    assert not app.exception
    assert len(app.session_state['current_course'].topics)==15
    assert any('15 knowledge points' in c.value for c in app.caption)


def test_builtin_examples_have_no_delete_or_manual_update_action():
    app=signed_in_app(ROOT/'app.py').run()
    assert not app.exception
    keys={b.key for b in app.button}
    assert all(f'remove_course_{cid}' not in keys for cid in FILES)
    assert all(f'update_demo_{cid}' not in keys for cid in FILES)


def test_current_course_work_is_preserved_when_course_list_is_stale():
    old = legacy()
    state = {'courses':[latest()], 'current_course':old}
    sync_demo_catalog(state)
    assert state['current_course'].topics[0].summary == 'My saved summary'
    assert state['current_course'].questions[:30] == old.questions
    assert len(state['current_course'].topics) == 15
