from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.learning_flow import stage_practice, install_practice, resume_draft, open_lab
from tests.auth_helpers import signed_in_app
from tests.test_practice_insights import setup_course, start_app
from models.schemas import StudyPackage

ROOT=Path(__file__).resolve().parents[1]


def calculus():
    return StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))


def test_stage_topic_does_not_discard_previous_result_or_history():
    app,course=start_app(graded=True)
    state={k:deepcopy(app.session_state[k]) for k in ['current_course','active_practice_insights','practice_history_insights','confirmed_scope_insights']}
    before=deepcopy(state)
    stage_practice(state,course,'t')
    assert state['active_practice_insights']==before['active_practice_insights']
    assert state['practice_history_insights']==before['practice_history_insights']
    assert state['practice_mode_insights']=='Topic Practice'
    assert state['practice_topic_insights']=='t'
    with pytest.raises(ValueError):stage_practice(state,course,'not-confirmed')


def test_new_entry_shows_settings_instead_of_old_graded_result():
    app,course=start_app(graded=True)
    old=deepcopy(app.session_state['active_practice_insights'])
    app.session_state['practice_entry_insights']={'topic_id':'t'}
    app.session_state['practice_mode_insights']='Topic Practice'
    app.session_state['practice_topic_insights']='t'
    app.run()
    assert not app.exception
    assert 'Your result' not in [s.value for s in app.subheader]
    assert app.session_state['active_practice_insights']==old
    assert any(e.label=='Practice settings' and e.proto.expanded for e in app.expander)
    app.button(key='practice_return_previous').click().run()
    assert not app.exception
    assert 'Your result' in [s.value for s in app.subheader]


def test_starting_new_session_preserves_unfinished_answers_confidence_and_hints():
    app,course=start_app()
    app.radio(key='answer_s_q0').set_value(0).run()
    app.button_group(key='confidence_s_q0').set_value('unsure').run()
    old=deepcopy(app.session_state['active_practice_insights'])
    replacement=deepcopy(old)
    replacement['session']=replacement['session'].model_copy(update={'session_id':'replacement'})
    state={'active_practice_insights':old}
    install_practice(state,'insights',replacement)
    assert state['practice_drafts_insights']['s']['_draft_widgets']['answer_s_q0']==0
    resume_draft(state,'insights','s')
    assert state['active_practice_insights']['session'].session_id=='s'
    assert state['answer_s_q0']==0 and state['confidence_s_q0']=='unsure'
    assert 'replacement' in state['practice_drafts_insights']


def test_draft_widgets_survive_registered_page_navigation():
    from tests.test_practice_page import make_practice_state
    app=signed_in_app(ROOT/'app.py').run()
    for key,value in make_practice_state(graded=False).items():app.session_state[key]=value
    app.session_state['practice_history_course-1']={}
    app.switch_page('pages/2_Practice_Center.py').run()
    app.radio(key='answer_session-1_question-1').set_value(0).run()
    app.button_group(key='confidence_session-1_question-1').set_value('guessed').run()
    app.switch_page('pages/3_Performance.py').run()
    assert not app.exception
    app.switch_page('pages/2_Practice_Center.py').run()
    assert not app.exception
    assert app.radio(key='answer_session-1_question-1').value==0
    assert app.button_group(key='confidence_session-1_question-1').value=='guessed'
    # Leaving stopped the clock; coming back starts it again (not a student's own pause).
    timer=app.session_state['active_practice_course-1']['focus_timer']
    assert timer['since'] is not None and 'away' not in timer


def test_lab_default_matches_requested_topic():
    course=calculus()
    state={}
    open_lab(state,course.course_id,'calc_derivatives')
    app=AppTest.from_file(str(ROOT/'pages/6_Concept_Lab.py'))
    for key,value in state.items():app.session_state[key]=value
    app.run()
    assert not app.exception
    assert app.get('tab_container')[0].proto.tab_container.default_tab_index==1
    app.slider(key='concept_lab_x0').set_value(2.0).run()
    assert not app.exception
    assert app.get('tab_container')[0].proto.tab_container.default_tab_index==1


def test_review_form_is_collapsed_and_the_page_does_not_prompt_for_it():
    course=calculus()
    app=AppTest.from_file(str(ROOT/'pages/1_Study_Hub.py'))
    app.session_state['current_course']=course
    app.run()
    assert not app.exception
    panel=next(e for e in app.expander if e.label=='Review and edit questions')
    assert not panel.proto.expanded
    assert app.button_group(key='scope_selection_calculus-i-demo') and not app.multiselect
    assert not app.checkbox
    # Reviewing questions is maintenance: no count, no button asking for it.
    assert not [b for b in app.button if b.key=='open_question_review_calculus-i-demo']
    assert not any('need your check' in c.value or 'needs your check' in c.value for c in app.caption)
    # The tool itself is still there, inside Course tools.
    assert app.selectbox(key='editor_question_calculus-i-demo').options


def test_progress_shows_every_section_on_one_page_without_tabs():
    app=AppTest.from_file(str(ROOT/'pages/3_Performance.py'))
    app.session_state['current_course']=calculus()
    app.run()
    assert not app.exception
    assert not app.tabs and not app.get('tab_container')
    headings=[s.value for s in app.subheader]
    assert headings[1:]==['Example · Mastery by topic','Example · Accuracy by session',
                          'Example · Learning DNA','Example · Time by topic']
    # The Dashboard still records which part to open; it no longer selects anything.
    app.session_state['progress_tab_calculus-i-demo']='Learning DNA'
    app.run()
    assert not app.exception
    assert not app.tabs and [s.value for s in app.subheader]==headings


def test_dashboard_prioritizes_course_over_secondary_features():
    app=signed_in_app(ROOT/'app.py').run()
    app.session_state['current_course']=calculus()
    app.session_state['confirmed_scope_calculus-i-demo']=['calc_derivatives']
    app.run()
    assert not app.exception
    assert app.button(key='dashboard_continue_learning').label=='Start practice'
    assert any(e.label=='Study totals' and not e.proto.expanded for e in app.expander)
    app.button(key='dashboard_continue_learning').click().run()
    assert not app.exception
    assert app.title[0].value=='Practice'
    assert 'Your result' not in [s.value for s in app.subheader]


def test_map_to_derivatives_lab_to_practice_preserves_context_and_old_result(monkeypatch):
    from components import knowledge_graph
    from services.exam_engine import grade_exam
    from models.schemas import ExamSession
    monkeypatch.setattr(knowledge_graph,'render_knowledge_graph',lambda *args,**kwargs:'calc_derivatives')
    course=calculus()
    session=ExamSession(session_id='previous',mode='mock',question_ids=['calc_q001'])
    result=grade_exam(session,[course.questions[0]],{'calc_q001':0})
    old={'session':session,'questions':[course.questions[0]],'result':result,'settings':{},'warning':None}
    history={'previous':{'session':session,'questions':[course.questions[0]],'attempts':result['attempts'],'result':result}}
    app=signed_in_app(ROOT/'app.py').run()
    app.session_state['current_course']=course
    app.session_state['confirmed_scope_calculus-i-demo']=['calc_derivatives']
    app.session_state['active_practice_calculus-i-demo']=deepcopy(old)
    app.session_state['practice_history_calculus-i-demo']=deepcopy(history)
    app.switch_page('pages/4_Knowledge_Graph.py').run()
    assert not app.exception
    app.button(key='radar_concept_lab_calculus-i-demo_calc_derivatives').click().run()
    assert not app.exception
    assert app.get('tab_container')[0].proto.tab_container.default_tab_index==1
    # AppTest retains stale custom-graph widget nodes after the switch. Use
    # a clean runner with the same saved state for the next leg; the map button
    # and its actual landing/default tab were checked above.
    carried = {key: deepcopy(app.session_state[key]) for key in (
        'current_course', 'confirmed_scope_calculus-i-demo',
        'active_practice_calculus-i-demo', 'practice_history_calculus-i-demo',
        'concept_lab_topic_calculus-i-demo',
    )}
    app=signed_in_app(ROOT/'app.py').run()
    for key,value in carried.items():app.session_state[key]=value
    app.switch_page('pages/6_Concept_Lab.py').run()
    app.button(key='concept_lab_practice_calc_derivatives').click().run()
    assert not app.exception
    assert app.radio(key='practice_mode_calculus-i-demo').value=='Topic Practice'
    assert app.selectbox(key='practice_topic_calculus-i-demo').value=='calc_derivatives'
    assert 'Your result' not in [s.value for s in app.subheader]
    assert app.session_state['practice_history_calculus-i-demo']==history



def test_explicit_new_practice_replaces_old_result_only_after_start(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    from models.schemas import ExamSession
    from services.exam_engine import grade_exam
    course=calculus()
    session=ExamSession(session_id='previous',mode='mock',question_ids=['calc_q001'])
    result=grade_exam(session,[course.questions[0]],{'calc_q001':0})
    history={'previous':{'session':session,'questions':[course.questions[0]],'attempts':result['attempts'],'result':result}}
    state={'current_course':course,'confirmed_scope_calculus-i-demo':['calc_derivatives'],
           'active_practice_calculus-i-demo':{'session':session,'questions':[course.questions[0]],'result':result,'settings':{},'warning':None},
           'practice_history_calculus-i-demo':deepcopy(history)}
    stage_practice(state,course,'calc_derivatives')
    app=AppTest.from_file(str(ROOT/'pages/2_Practice_Center.py'))
    for key,value in state.items():app.session_state[key]=value
    app.run()
    next(b for b in app.button if b.label=='Start new practice').click().run()
    assert not app.exception
    assert app.session_state['active_practice_calculus-i-demo']['session'].question_ids==['calc_q002']
    assert 'result' not in app.session_state['active_practice_calculus-i-demo']
    assert app.session_state['practice_history_calculus-i-demo']==history


def test_practice_result_opens_the_same_topic_in_concept_lab():
    from services.exam_engine import create_exam, grade_exam

    course = calculus()
    topic_id = "calc_limits"
    active = create_exam(
        package=course, mode="topic", requested_count=1,
        confirmed_topic_ids=[topic_id], topic_id=topic_id,
    )
    session, questions = active["session"], active["questions"]
    active["result"] = grade_exam(session, questions, {questions[0].id: None})

    app = signed_in_app(ROOT / "app.py").run()
    # Home and Practice are sidebar pages now, not links in a top header row.
    assert not {"Home", "Practice"} & {link.proto.label for link in app.get("page_link")}
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = [topic_id]
    app.session_state[f"active_practice_{course.course_id}"] = active
    app.switch_page("pages/2_Practice_Center.py").run()
    app.button(key=f"flight_lab_{session.session_id}").click().run()

    assert not app.exception
    assert app.session_state[f"concept_lab_topic_{course.course_id}"] == topic_id
    assert app.session_state[f"active_practice_{course.course_id}"]["session"] == session

def test_sidebar_lists_every_study_page_and_opens_each_one(monkeypatch):
    from tests.test_paper_shell import expected_sidebar_titles, sidebar_navigation

    visible, hidden, position = sidebar_navigation(monkeypatch)
    assert position == "sidebar"
    assert [page.title for page in visible] == expected_sidebar_titles()
    assert [page.url_path for page in hidden] == ["account"]

    # Opening a page from the list leaves no top review menu behind.
    app = signed_in_app(ROOT / "app.py").run()
    app.switch_page("pages/1_Study_Hub.py").run()
    assert not app.exception
    assert app.title[0].value == "Study Plan"
    assert not any((box.key or "").startswith("flight_review") for box in app.selectbox)
