from pathlib import Path
from copy import deepcopy
import re
import pytest

from tests.auth_helpers import signed_in_app
from tests.test_practice_page import make_practice_state

ROOT=Path(__file__).resolve().parents[1]


def test_return_from_secondary_page_keeps_answer_question_and_manual_pause():
    app=signed_in_app(ROOT/'app.py').run()
    for key,value in make_practice_state(graded=False).items(): app.session_state[key]=value
    app.session_state['practice_history_course-1']={}
    app.switch_page('pages/2_Practice_Center.py').run()
    app.radio(key='answer_session-1_question-1').set_value(0).run()
    app.button(key='focus_pause_session-1').click().run()
    assert not app.exception
    active=app.session_state['active_practice_course-1']
    assert active['focus_timer']['since'] is None
    sid=active['session'].session_id
    app.switch_page('pages/3_Performance.py').run()
    assert not app.exception
    # A pending new-topic intent must not displace the session explicitly resumed.
    app.session_state['practice_entry_course-1']={'topic_id':'topic-1'}
    app.button(key='study_return_course-1').click().run()
    assert not app.exception
    assert app.session_state['active_practice_course-1']['session'].session_id==sid
    assert app.session_state['active_practice_course-1']['focus_timer']['since'] is None
    assert app.radio(key='answer_session-1_question-1').value==0
    assert app.button(key='focus_pause_session-1').label=='Resume'
    assert any('Timer paused. Your answers are kept.' in m.value for m in app.markdown)
    assert 'practice_entry_course-1' not in app.session_state


def test_no_extra_return_action_on_home_or_after_grading():
    app=signed_in_app(ROOT/'app.py').run()
    for key,value in make_practice_state(graded=False).items():app.session_state[key]=value
    app.run()
    assert not any(b.key=='study_return_course-1' for b in app.button)
    for key,value in make_practice_state(graded=True).items():app.session_state[key]=value
    app.switch_page('pages/3_Performance.py').run()
    assert not app.exception
    assert not any(b.key=='study_return_course-1' for b in app.button)


def test_paused_notice_disappears_after_resuming_without_changing_answer():
    app=signed_in_app(ROOT/'app.py').run()
    for key,value in make_practice_state(graded=False).items():app.session_state[key]=value
    app.session_state['practice_history_course-1']={}
    app.switch_page('pages/2_Practice_Center.py').run()
    app.radio(key='answer_session-1_question-1').set_value(0).run()
    app.button(key='focus_pause_session-1').click().run()
    app.button(key='focus_pause_session-1').click().run()
    assert not app.exception
    assert not any('Timer paused. Your answers are kept.' in m.value for m in app.markdown)
    assert app.radio(key='answer_session-1_question-1').value==0


def test_pilot_uses_shared_tokens_and_brand_vector(monkeypatch):
    from services import tutor_assistant_ui as ui
    calls=[]
    monkeypatch.setattr(ui.components,'component',lambda *a,**kw: calls.append(kw))
    ui._component.cache_clear()
    ui._component()
    assert calls
    import base64
    uri=re.search(r'src="data:image/svg\+xml;base64,([^"]+)"',calls[0]['html']).group(1)
    assert base64.b64decode(uri)==(ROOT/'assets/brand-plane.svg').read_bytes()
    assert '--ep-surface-page' in calls[0]['css'] and '--tutor-blue: var(--ep-action)' in calls[0]['css']
    ui._component.cache_clear()


def test_shared_text_and_action_tokens_meet_normal_text_contrast():
    css=(ROOT/'assets/ui_tokens.css').read_text()
    values=dict(re.findall(r'(--ep-[\w-]+):\s*(#[A-Fa-f0-9]{6})',css))
    def luminance(hex):
        channels=[int(hex[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(a*b for a,b in zip(linear,[.2126,.7152,.0722]))
    def contrast(a,b):
        l=sorted([luminance(a),luminance(b)])
        return (l[1]+.05)/(l[0]+.05)
    assert contrast(values['--ep-blue-700'],'#FFFFFF')>=4.5
    assert contrast(values['--ep-navy-900'],values['--ep-cream-white'])>=4.5
    assert contrast(values['--ep-slate-700'],values['--ep-cream-50'])>=4.5


def context_script():
    import streamlit as st
    from services.study_navigation import render_study_context
    render_study_context(st.session_state['current_course'], 'Flashcards', 'Flashcards')


def test_flashcards_context_returns_to_existing_session_without_replacing_it(monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    destinations=[]
    monkeypatch.setattr(st, 'switch_page', lambda path: destinations.append(path))
    app=AppTest.from_function(context_script)
    state=make_practice_state(graded=False)
    for key,value in state.items():app.session_state[key]=value
    old=deepcopy(state['active_practice_course-1'])
    app.session_state['practice_entry_course-1']={'topic_id':'topic-1'}
    app.run().button(key='study_return_course-1').click().run()
    assert not app.exception
    assert destinations==['pages/2_Practice_Center.py']
    assert app.session_state['active_practice_course-1']==old
    assert 'practice_entry_course-1' not in app.session_state
