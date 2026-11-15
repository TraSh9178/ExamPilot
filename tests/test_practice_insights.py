from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from models.schemas import Question, StudyPackage, ExamSession, AttemptResult
from services.practice_insights import (ResponseInsight, ExplanationFeedback, before_submit, focus_question,
    settle_focus, session_insights, set_session_insights, analytics, transfer_session, priority_session)
from services.exam_engine import grade_exam

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/'pages/2_Practice_Center.py'
REVIEW=ROOT/'pages/13_Answer_Review.py'  # answers, explanations and reflections
HISTORY=ROOT/'pages/8_Practice_History.py'


def setup_course():
    qs=[Question(id=f'q{i}',topic_id='t' if i<3 else 'other',question=f'Question {i}',
        options=['A','B','C','D'],correct_index=0,explanation='Reason',
        practice_structure='evaluation' if i==0 else 'interpretation') for i in range(4)]
    return StudyPackage(course_id='insights',course_name='Test',topics=[{'id':'t','name':'Topic','summary':'Topic'},
        {'id':'other','name':'Other','summary':'Other'}],relationships=[],questions=qs)


def start_app(graded=False, picks=(0,1), page=PAGE):
    course=setup_course()
    qs=course.questions[:2]
    session=ExamSession(session_id='s',mode='topic',question_ids=[q.id for q in qs])
    result=grade_exam(session,qs,{q.id:pick for q,pick in zip(qs,picks)})
    active={'session':session,'questions':qs,'warning':None,'settings':{}}
    if graded:active['result']=result
    app=AppTest.from_file(str(page))
    app.session_state['current_course']=course
    app.session_state['confirmed_scope_insights']=['t']
    app.session_state['active_practice_insights']=active
    if graded:app.session_state['practice_history_insights']={'s':{'session':session,'questions':qs,'attempts':result['attempts'],'result':result}}
    return app.run(),course


def test_focus_estimates_switch_pause_idle_cap_and_clock_regression():
    course=setup_course()
    active={'session':ExamSession(session_id='s',mode='topic',question_ids=['q0','q1'])}
    focus_question(active,'q0',100)
    focus_question(active,'q1',110)
    settle_focus(active,115)
    assert active['focus_seconds']=={'q0':10,'q1':5}
    assert active['session_seconds']==15
    active['focus_timer']['since']=None
    settle_focus(active,1000)
    assert active['focus_seconds']['q1']==5
    assert active['session_seconds']==15  # paused: the session clock stops too
    focus_question(active,'q1',1000)
    settle_focus(active,2000)
    assert active['focus_seconds']['q1']==125
    assert active['session_seconds']==1015  # the clock counts the whole 1000 s gap
    settle_focus(active,1999)
    assert active['focus_seconds']['q1']==125
    assert active['session_seconds']==1015
    with pytest.raises(ValueError):focus_question(active,'other',2001)


def test_smart_review_list_is_on_the_page_not_behind_an_expander():
    app,_=start_app(graded=True)
    assert not app.exception
    labels=[e.label for e in app.expander]
    assert 'Why this review order' not in labels and 'Time breakdown' not in labels
    # The ranked list is rendered directly, with the one question that was missed.
    ranked=[f.value for f in app.dataframe if 'Why review' in f.value.columns]
    assert len(ranked)==1
    assert list(ranked[0]['Question'])==['Question 1']
    assert list(ranked[0]['Rank'])==[1]
    for expander in app.expander:
        assert not any('Why review' in f.value.columns for f in expander.dataframe)
    # The note on how the order is decided stays, as a line of text under the list.
    assert any(c.value.startswith('Priority uses incorrect/unanswered responses') for c in app.caption)
    assert app.button(key='priorities_insights').label=='Practise review priorities'


def test_checklist_identifies_unanswered_uncertain_guessed_without_grading():
    qs=setup_course().questions
    rows=before_submit(qs,{'q0':0,'q1':1,'q2':0},{'q0':'sure','q1':'unsure','q2':'guessed'})
    assert [r['Question'] for r in rows]==[2,3,4]
    assert [r['Check'] for r in rows]==['Unsure','Guessed','Unanswered']


def test_analytics_explains_priority_correct_guesses_hint_use_and_topic_time():
    course=setup_course()
    attempts=[AttemptResult(session_id='s',question_id=q.id,selected_index=0 if i in [0,2] else 1,is_correct=i in [0,2]) for i,q in enumerate(course.questions)]
    rows={'q0':{'confidence':'guessed','hints_used':0,'focus_seconds':5},
          'q1':{'confidence':'sure','hints_used':1,'focus_seconds':40},
          'q2':{'confidence':'sure','hints_used':0,'focus_seconds':5}}
    data=analytics(course.questions,attempts,rows)
    assert data['correct_guesses']==['q0']
    assert data['assisted']==['q1'] and data['unknown_hints']==['q3']
    assert data['topic_seconds']=={'t':50}
    assert data['priorities'][0]['question_id']=='q1'
    assert 'Confident but incorrect' in data['priorities'][0]['reasons']
    assert 'Longer tracked focus time' in data['priorities'][0]['reasons']


@pytest.mark.parametrize('row',[{'confidence':'maybe'},{'hints_used':-1},{'hints_used':True},
    {'focus_seconds':float('nan')},{'focus_seconds':-1},{'mistake_reason':'AI diagnosed anxiety'},
    {'explanation':'a'*4001},{'unknown':3}])
def test_bad_metadata_rejected(row):
    with pytest.raises(ValidationError):ResponseInsight.model_validate(row)


def test_insights_json_roundtrip_unknown_vs_zero_and_course_isolation():
    old=setup_course()
    updated=set_session_insights(old,'s',{'q0':{'confidence':'guessed','hints_used':0},'q1':{}})
    restored=StudyPackage.model_validate_json(updated.model_dump_json())
    assert not old.learning_state
    assert session_insights(restored,'s')['q0']['hints_used']==0
    assert session_insights(restored,'s')['q1']['hints_used'] is None
    assert session_insights(setup_course(),'s')=={}
    with pytest.raises(ValueError):set_session_insights(old,'s',{'not-a-question':{}})


def test_transfer_requires_same_topic_different_structure_and_approved_family():
    course=setup_course()
    source=course.questions[0]
    session=ExamSession(session_id='original',mode='topic',question_ids=['q0'])
    new=transfer_session(course,source,session,['t'])
    assert new['session'].question_ids==['q1'] and new['session'].session_id!='original'
    assert 'result' not in new and new['transfer_from']=='q0'
    assert new['questions'][0].practice_structure!=source.practice_structure
    course.learning_state['question_reviews']={'q1':'pending','q2':'flagged'}
    with pytest.raises(ValueError,match='No approved'):transfer_session(course,source,session,['t'])
    with pytest.raises(ValueError,match='Confirm'):transfer_session(course,source,session,[])


def test_transfer_rejects_revisions_and_untagged_source():
    course=setup_course()
    source=course.questions[0]
    course.questions[1].version_of='q0'
    course.questions[2].practice_structure='evaluation'
    s=ExamSession(session_id='s',mode='topic',question_ids=['q0'])
    with pytest.raises(ValueError,match='No approved'):transfer_session(course,source,s,['t'])
    source.practice_structure=None
    with pytest.raises(ValueError,match='no reviewed structure'):transfer_session(course,source,s,['t'])


def test_priority_session_preserves_order_filters_scope_pending_and_creates_new_id():
    course=setup_course()
    course.learning_state['question_reviews']={'q2':'pending'}
    ranking=[{'question_id':qid} for qid in ['q2','q1','q3','q0']]
    selected=priority_session(course,ranking,['t'])
    assert selected['session'].question_ids==['q1','q0']
    assert selected['session'].mode=='topic'
    assert 'result' not in selected
    with pytest.raises(ValueError):priority_session(course,ranking,[])


def test_submission_persists_confidence_and_hint_snapshots_without_changing_grade():
    app,course=start_app()
    app.radio(key='answer_s_q0').set_value(0).run()
    app.button_group(key='confidence_s_q0').set_value('guessed').run()
    app.button(key="worksheet_next_s").click().run()
    app.radio(key='answer_s_q1').set_value(1).run()
    app.button_group(key='confidence_s_q1').set_value('unsure').run()
    app.button(key="worksheet_previous_s").click().run()
    assert app.radio(key="answer_s_q0").value == 0
    assert app.button_group(key="confidence_s_q0").value == 'guessed'
    app.button(key='worksheet_review_s').click().run()
    assert 'Review before submit' in [h.value for h in app.subheader]
    app.button(key='practice_submit_s').click().run()
    assert not app.exception
    assert app.session_state['active_practice_insights']['result']['correct_count']==1
    saved=app.session_state['current_course']
    assert session_insights(saved,'s')['q0']['confidence']=='guessed'
    assert session_insights(saved,'s')['q1']['confidence']=='unsure'
    assert session_insights(saved,'s')['q0']['hints_used']==0
    assert '1 correct answer was marked Guessed. Revisit it before treating it as secure knowledge.' in [i.value for i in app.info]
    assert all(b.label!='Submit answers' for b in app.button)


def test_reflection_saves_self_report_and_own_words_without_modifying_result(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    app,course=start_app(graded=True,page=REVIEW)
    result=deepcopy(app.session_state['active_practice_insights']['result'])
    app.button(key='review_next_s').click().run()  # q1, the missed question
    reasons=app.button_group(key='reason_s_q1')
    assert reasons.value is None
    assert reasons.options==['Knowledge gap','Careless error','Time pressure','Misread the question','Other','Not sure yet']
    reasons.set_value('time_pressure')
    app.text_area(key='explain_s_q1').set_value('I rushed the final comparison.')
    buttons=[b for b in app.button if b.label=='Save reflection']
    assert len(buttons)==1  # one question per screen
    buttons[0].click().run()
    assert not app.exception
    saved=session_insights(app.session_state['current_course'],'s')['q1']
    assert saved['mistake_reason']=='time_pressure'
    assert saved['explanation']=='I rushed the final comparison.'
    assert app.session_state['active_practice_insights']['result']==result
    assert all(b.disabled for b in app.button if b.label=='Check explanation with AI')
    assert 'Saved.' in [s.value for s in app.success]
    assert app.button_group(key='reason_s_q1').value=='time_pressure'


def test_ai_review_is_explicit_bounded_and_cannot_change_grade(monkeypatch):
    from services import practice_insights_ui
    monkeypatch.setattr(practice_insights_ui,'generation_available',lambda:True)
    calls=[]
    def check(q,text):
        calls.append(text)
        return {'ok':True,'feedback':{'verdict':'partial','reasoning':'One step is missing.','next_step':'Explain the comparison.'}}
    monkeypatch.setattr(practice_insights_ui,'check_explanation',check)
    app,_=start_app(graded=True,page=REVIEW)
    assert calls==[]
    app.text_area(key='explain_s_q0').set_value('I compared the values.')
    next(b for b in app.button if b.label=='Check explanation with AI').click().run()
    assert not app.exception and calls==['I compared the values.']
    saved=app.session_state['current_course']
    assert session_insights(saved,'s')['q0']['feedback']['verdict']=='partial'
    assert app.session_state['active_practice_insights']['result']['correct_count']==1
    app.text_area(key='explain_s_q0').set_value('A revised explanation.')
    next(b for b in app.button if b.label=='Save reflection').click().run()
    assert not app.exception
    assert session_insights(app.session_state['current_course'],'s')['q0']['feedback'] is None


def test_ai_service_validates_output_and_missing_configuration_without_network(monkeypatch):
    from services import ai_service
    q=setup_course().questions[0]
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    assert ai_service.check_explanation(q,'A reason')['error_code']=='MISSING_API_KEY'
    assert ai_service.check_explanation(q,' ')['error_code']=='INVALID_EXPLANATION'
    monkeypatch.setattr(ai_service,'_generate',lambda *args:(ExplanationFeedback(verdict='supported',reasoning='Valid steps.',next_step='Try a new question.'),None))
    assert ai_service.check_explanation(q,'A reason')['ok']
    monkeypatch.setattr(ai_service,'_generate',lambda *args:(object(),None))
    assert not ai_service.check_explanation(q,'A reason')['ok']


def test_transfer_and_priority_buttons_launch_fresh_practice(monkeypatch):
    import streamlit as st
    from tests.test_practice_page import carry_to
    destinations=[]
    monkeypatch.setattr(st,'switch_page',lambda page:destinations.append(page))
    app,_=start_app(graded=True,picks=(1,0),page=REVIEW)
    app.button(key='transfer_s_q0').click().run()
    assert not app.exception
    active=app.session_state['active_practice_insights']
    assert active['session'].question_ids==['q2']  # q1 was already in the source session.
    assert 'result' not in active
    # Review answers sends the student to the new session on the practice page.
    assert destinations==['pages/2_Practice_Center.py']
    practice=carry_to(app,PAGE)
    practice.radio(key=f"answer_{active['session'].session_id}_q2").set_value(0).run()
    assert not practice.exception
    app,_=start_app(graded=True)
    app.button(key='priorities_insights').click().run()
    assert not app.exception
    active=app.session_state['active_practice_insights']
    assert active['session'].question_ids==['q1'] and 'result' not in active


def test_saved_result_reopens_after_restoration_without_regrading(monkeypatch):
    import streamlit as st
    from tests.test_practice_page import carry_to
    destinations=[]
    monkeypatch.setattr(st,'switch_page',lambda page:destinations.append(page))
    app,_=start_app(graded=True)
    record=deepcopy(app.session_state['practice_history_insights']['s'])
    app.session_state['active_practice_insights']=None
    app.run()
    app=carry_to(app,HISTORY)  # saved sessions are reopened from Practice history
    app.button(key='practice_history_open_s').click().run()
    assert not app.exception
    assert destinations==['pages/2_Practice_Center.py']
    assert app.session_state['active_practice_insights']['result']==record['result']
    assert app.session_state['practice_history_insights']['s']==record


def test_hint_count_is_frozen_in_grade_snapshot_and_available_after_rerun():
    app,_=start_app()
    active=app.session_state['active_practice_insights']
    active['questions'][0].hints=['Compare both values.','Check the units.']
    app.run()
    app.button(key='hint_button_s_q0').click().run()
    app.radio(key='answer_s_q0').set_value(0).run()
    app.button(key='worksheet_review_s').click().run()
    app.button(key='practice_submit_s').click().run()
    assert not app.exception
    assert session_insights(app.session_state['current_course'],'s')['q0']['hints_used']==1
    app.session_state['hints_shown_s_q0']=0
    app.run()
    from tests.test_practice_page import carry_to
    assert 'Hints used: 1 of 2' in [c.value for c in carry_to(app).caption]


def test_progress_review_and_time_use_selected_mode_and_latest_family():
    course=setup_course()
    s=ExamSession(session_id='s',mode='topic',question_ids=['q0','q1'])
    result=grade_exam(s,course.questions[:2],{'q0':1,'q1':0})
    course=set_session_insights(course,'s',{'q0':{'confidence':'sure','focus_seconds':30.0},'q1':{'focus_seconds':10.0}})
    app=AppTest.from_file(str(ROOT/'pages/3_Performance.py'))
    app.session_state['current_course']=course
    app.session_state['confirmed_scope_insights']=['t']
    app.session_state['performance_mode_insights']='Topic Practice'
    app.session_state['practice_history_insights']={'s':{'session':s,'questions':course.questions[:2],'attempts':result['attempts'],'result':result}}
    app.run()
    assert not app.exception
    from tests.test_progress_charts import bar_rows, charts
    tables=[f.value for f in app.dataframe]
    # Time by topic is a chart now: one bar for Topic, 30 s + 10 s.
    assert [(row['label'],row['value']) for markup in charts(app,'time') for row in bar_rows(markup)]==[('Topic','40 s')]
    assert any('Why review' in t.columns and 'Confident but incorrect' in t.iloc[0]['Why review'] for t in tables)
    app.radio(key='performance_mode_insights').set_value('Mock Exam').run()
    assert not app.exception
    assert not charts(app,'time')


def test_answer_evidence_is_one_short_line_without_completion_claims():
    app,course=start_app(graded=True,picks=(0,None),page=REVIEW)
    course=set_session_insights(course,'s',{'q0':{'confidence':'sure','hints_used':1,'focus_seconds':42.4},
                                            'q1':{'hints_used':0}})
    app.session_state['current_course']=course
    app.run()
    assert not app.exception
    captions=[c.value for c in app.caption]
    assert 'Sure · 1 hint · 42 s' in captions
    app.button(key='review_next_s').click().run()
    captions+=[c.value for c in app.caption]
    assert 'No hints' in captions  # unanswered: no claim that it was completed without hints
    assert not any(c.startswith(('Answered questions','Completion evidence','In-app hints shown','Tracked focus time',
                                 'Confidence:','Hint exposure')) for c in captions)
    course=set_session_insights(course,'s',{'q0':{'hints_used':2}})
    app.session_state['current_course']=course
    app.button(key='review_previous_s').click().run()
    assert '2 hints' in [c.value for c in app.caption]


def test_oversize_reflection_is_rejected_without_overwriting_course_or_grade():
    app,course=start_app(graded=True,page=REVIEW)
    course.learning_state={'padding':'x'*511000}
    app.session_state['current_course']=course
    app.run()
    app.text_area(key='explain_s_q0').set_value('a'*4000)
    next(b for b in app.button if b.label=='Save reflection').click().run()
    assert not app.exception
    errors=[e.value for e in app.error]
    assert "Couldn't save your reflection. Your score is unchanged." in errors
    assert not any('storage limit' in e or 'metadata' in e for e in errors)
    assert not session_insights(app.session_state['current_course'],'s')
    assert app.session_state['active_practice_insights']['result']['correct_count']==1
