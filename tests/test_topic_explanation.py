from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from components import topic_explanation


def app_script():
    import streamlit as st
    from models.schemas import StudyPackage
    from components.topic_explanation import render_topic_explanation
    from services.i18n import LANGUAGE_KEY
    st.toggle('Chinese', key=LANGUAGE_KEY)
    selected = st.selectbox('Topic', ['t1', 't2'])
    course = StudyPackage.model_validate({
        'course_id': 'course', 'course_name': 'Test',
        'topics': [dict(id='t1', name='Addition', summary='Combine numbers.'),
                   dict(id='t2', name='Other', summary='Other topic.')],
        'relationships': [],
        'questions': [dict(id='q1', topic_id='t1', question='1 + 1?',
                           options=['2', '3', '4', '5'], correct_index=0,
                           explanation='One plus one makes two.')],
    })
    render_topic_explanation(course, selected)


def test_examples_are_offline_and_answers_require_action(monkeypatch):
    tutor = Mock()
    monkeypatch.setattr(topic_explanation, 'ask_tutor', tutor)
    app = AppTest.from_function(app_script).run()
    assert not app.exception
    assert not tutor.called
    assert not any('One plus one' in item.value for item in app.markdown)
    app.checkbox[0].check().run()
    assert any('One plus one' in item.value for item in app.markdown)
    assert not tutor.called


def test_explicit_generation_language_and_topic_isolation(monkeypatch):
    tutor = Mock(return_value={'ok': True, 'answer': 'Worked explanation'})
    monkeypatch.setattr(topic_explanation, 'ask_tutor', tutor)
    app = AppTest.from_function(app_script).run()
    app.button[0].click().run()
    assert tutor.call_count == 1
    assert tutor.call_args.args[2] == 't1'
    assert any(item.value == 'Worked explanation' for item in app.markdown)
    app.run()
    assert tutor.call_count == 1
    app.toggle[0].set_value(True).run()
    assert not any(item.value == 'Worked explanation' for item in app.markdown)
    assert tutor.call_count == 1
    app.selectbox[0].select('t2').run()
    assert not any(item.value == 'Worked explanation' for item in app.markdown)
    assert any("暂时没有" in item.value for item in app.caption)
    app.toggle[0].set_value(True).run()
    assert not app.expander
    app.button[0].click().run()
    assert 'Simplified Chinese' in tutor.call_args.args[1]
    assert tutor.call_args.args[2] == 't2'
    assert not app.exception


def test_failure_keeps_examples_and_allows_retry(monkeypatch):
    tutor = Mock(side_effect=[{'ok': False}, {'ok': True, 'answer': 'Recovered'}])
    monkeypatch.setattr(topic_explanation, 'ask_tutor', tutor)
    app = AppTest.from_function(app_script).run()
    app.button[0].click().run()
    assert len(app.warning) == 1
    assert app.checkbox[0].label == 'Show answer and explanation'
    app.button[0].click().run()
    assert any(item.value == 'Recovered' for item in app.markdown)
    assert not app.exception


def test_map_details_open_dedicated_page_and_return_to_same_topic(monkeypatch):
    from pathlib import Path
    from tests.auth_helpers import signed_in_app
    from models.schemas import StudyPackage
    root = Path(__file__).resolve().parents[1]
    course = StudyPackage.model_validate_json((root/'data/calculus_i_demo.json').read_text(encoding='utf-8'))
    app = signed_in_app(root/'app.py').run()
    app.session_state['current_course'] = course
    app.session_state[f'graph_pending_focus_{course.course_id}'] = 'calc_limits'
    app.switch_page('pages/4_Knowledge_Graph.py').run()
    app.button(key='topic_details_open').click().run()
    assert not app.exception
    assert app.title[0].value == 'Detailed explanation & examples'
    assert app.session_state[f'topic_details_{course.course_id}'] == 'calc_limits'
    assert app.selectbox[0].options
    assert not any(e.label == "Detailed explanation & examples" for e in app.expander)
    # Back links preserve the course-scoped graph focus.
    assert app.session_state[f'graph_pending_focus_{course.course_id}'] == 'calc_limits'
    assert app.button(key='topic_details_back').label == 'Back to Knowledge Map'
