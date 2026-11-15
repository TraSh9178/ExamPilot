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
    assert app.expander[0].label == '详细讲解与例题'
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
