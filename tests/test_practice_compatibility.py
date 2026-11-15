from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services import account_sync, postgres_store
from services.demo_updates import demo_update
from services.exam_engine import grade_exam
from services.practice_insights import set_session_insights, session_insights
from tests.test_practice_insights import setup_course
from tests.test_postgres_store import FakeConnection, use_connection, make_attempts
from tests.test_account_sync import FakeStore, signed_in_state, seed, make_exam
from tests.auth_helpers import TEST_USER
from models.schemas import ExamSession

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename,old_count',[('calculus_i_demo.json',3),('sample_course.json',3),('demo_python_basics.json',9)])
def test_demo_update_appends_drafts_preserving_old_questions_metadata_and_scope(filename,old_count):
    current=StudyPackage.model_validate_json((ROOT/'data'/filename).read_text(encoding='utf-8'))
    data=current.model_dump()
    data['questions']=data['questions'][:old_count]
    for q in data['questions']:
        q['cognitive_dimension']=None
        q['practice_structure']=None
        q['hints']=[]
    data['learning_state']={'confirmed_scope':[current.topics[0].id],'session_order':['old']}
    old=StudyPackage.model_validate(data)
    before=deepcopy(old)
    updated,count=demo_update(old)
    assert count==len(current.questions)-old_count and len(updated.questions)==len(current.questions)
    assert updated.questions[:old_count]==old.questions
    assert old==before
    assert updated.learning_state['confirmed_scope']==old.learning_state['confirmed_scope']
    assert updated.learning_state['session_order']==['old']
    assert set(updated.learning_state['question_reviews'].values())=={'pending'}
    assert demo_update(updated)==(updated,0)


def test_demo_update_dashboard_button_preserves_history_and_adds_questions():
    from tests.auth_helpers import signed_in_app
    current=StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))
    data=current.model_dump();data['questions']=data['questions'][:3];data['learning_state']={}
    old=StudyPackage.model_validate(data)
    app=signed_in_app(ROOT/'app.py').run()
    app.session_state['courses']=[old]
    app.session_state['current_course']=old
    app.session_state['practice_history_calculus-i-demo']={}
    app.run()
    assert not app.exception
    assert len(app.session_state['current_course'].questions)==len(current.questions)
    assert app.session_state['practice_history_calculus-i-demo']=={}


def test_store_preserves_saved_optional_annotations_and_rejects_changed_core():
    old=setup_course()
    incoming=deepcopy(old)
    incoming.questions[0].cognitive_dimension='conceptual'
    incoming.questions[0].hints=['A new hint.']
    incoming.questions[0].practice_structure='new-label'
    merged=postgres_store._merge_course_packages(old,incoming)
    assert merged.questions[0]==old.questions[0]
    assert old.questions[0]!=incoming.questions[0]
    for field,value in [('question','Changed question'),('correct_index',1),('options',['W','X','Y','Z']),('explanation','Changed explanation')]:
        changed=deepcopy(incoming)
        setattr(changed.questions[0],field,value)
        with pytest.raises(postgres_store._PersistenceError):postgres_store._merge_course_packages(old,changed)


def test_store_merges_distinct_session_metadata_without_losing_older_rows():
    old=set_session_insights(setup_course(),'old',{'q0':{'confidence':'sure'}})
    incoming=set_session_insights(setup_course(),'new',{'q1':{'mistake_reason':'careless'}})
    merged=postgres_store._merge_course_packages(old,incoming)
    assert session_insights(merged,'old')['q0']['confidence']=='sure'
    assert session_insights(merged,'new')['q1']['mistake_reason']=='careless'


def test_real_store_json_save_restore_preserves_insights_and_immutable_grade(monkeypatch):
    connection=FakeConnection();use_connection(monkeypatch,connection)
    course=setup_course()
    q=course.questions[0]
    session=ExamSession(session_id='s',mode='topic',question_ids=[q.id])
    result=grade_exam(session,[q],{q.id:0})
    course=set_session_insights(course,'s',{q.id:{'confidence':'guessed','hints_used':1,'focus_seconds':22.0,'explanation':'My reasoning.'}})
    assert postgres_store.save_course_history('student',course,[(session,result['attempts'])]).success
    restored=postgres_store.load_course_history('student',course.course_id)
    assert restored.success
    assert session_insights(restored.package,'s')[q.id]['explanation']=='My reasoning.'
    assert restored.attempts[0].is_correct
    assert session_insights(restored.package,'s')[q.id]['hints_used']==1
    # A second account does not receive this evidence.
    assert postgres_store.load_course_history('other-student',course.course_id).package is None


def test_failed_restore_blocks_fallback_saves_until_successful_retry(monkeypatch):
    store=FakeStore();store.install(monkeypatch)
    course=setup_course()
    seed(store,TEST_USER,course)
    store.fail_course_ids.add(course.course_id)
    state=signed_in_state()
    assert not account_sync.restore_all(state).success
    state['courses']=[course];state['current_course']=course
    assert not account_sync.save_course_to_account(state,course).success
    assert store.names('save_course')==[]
    store.fail_course_ids.clear()
    assert account_sync.restore_all(state).success
    assert account_sync.save_course_to_account(state,state['courses'][0]).success


def test_optional_annotations_do_not_overwrite_local_historical_snapshots(monkeypatch):
    store=FakeStore();store.install(monkeypatch)
    course=setup_course()
    session,result=make_exam(course,'old',picks=(0,0,0,0))
    state=signed_in_state()
    state[f'practice_history_{course.course_id}']={'old':{'session':session,'questions':deepcopy(course.questions),'attempts':result,'result':{}}}
    modern=deepcopy(course);modern.questions[0].cognitive_dimension='conceptual'
    assert account_sync.save_course_to_account(state,modern).success
    stored=store.courses[TEST_USER.user_id][course.course_id]
    assert stored.questions[0]==course.questions[0]


def test_account_restore_keeps_new_tracking_records_and_grades(monkeypatch):
    store=FakeStore();store.install(monkeypatch)
    course=set_session_insights(setup_course(),'s',{'q0':{'confidence':'guessed','hints_used':2,'focus_seconds':12.0,'mistake_reason':'careless'}})
    s=ExamSession(session_id='s',mode='topic',question_ids=['q0'])
    result=grade_exam(s,[course.questions[0]],{'q0':0})
    state=signed_in_state()
    state[f'practice_history_{course.course_id}']={'s':{'session':s,'questions':[course.questions[0]],'attempts':result['attempts'],'result':result}}
    assert account_sync.save_exam_to_account(state,course,s,result['attempts']).success
    fresh=signed_in_state()
    assert account_sync.restore_all(fresh).success
    restored=fresh['courses'][0]
    assert session_insights(restored,'s')['q0']['confidence']=='guessed'
    assert session_insights(restored,'s')['q0']['hints_used']==2
    assert fresh[f'practice_history_{course.course_id}']['s']['result']['correct_count']==1


def test_ai_error_preserves_written_reflection_and_shows_no_fake_feedback(monkeypatch):
    from services import practice_insights_ui
    from tests.test_practice_insights import start_app
    monkeypatch.setattr(practice_insights_ui,'generation_available',lambda:True)
    monkeypatch.setattr(practice_insights_ui,'check_explanation',lambda *args:{'ok':False,'message':'AI service unavailable.'})
    app,_=start_app(graded=True)
    app.text_area(key='explain_s_q0').set_value('This is my own explanation.')
    next(b for b in app.button if b.label=='Check explanation with AI').click().run()
    assert not app.exception
    assert 'AI service unavailable.' in [e.value for e in app.error]
    row=session_insights(app.session_state['current_course'],'s')['q0']
    assert row['explanation']=='This is my own explanation.' and row['feedback'] is None
