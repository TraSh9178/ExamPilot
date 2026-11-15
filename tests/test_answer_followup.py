from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from services import answer_followup


def followup_app():
    import streamlit as st
    from models.schemas import StudyPackage
    from services.answer_followup import render_answer_followup
    from services.i18n import LANGUAGE_KEY

    st.toggle('Chinese', key=LANGUAGE_KEY)
    topic = st.selectbox('Topic', ['t1', 't2'])
    course = StudyPackage.model_validate({
        'course_id': 'test', 'course_name': 'Test',
        'topics': [{'id': 't1', 'name': 'First', 'summary': 'First.'},
                   {'id': 't2', 'name': 'Second', 'summary': 'Second.'}],
        'relationships': [],
        'questions': [
            {'id': t, 'topic_id': t, 'question': f'Question {t}?',
             'options': ['A', 'B', 'C', 'D'], 'correct_index': 0,
             'explanation': f'Explanation {t}.'} for t in ['t1', 't2']
        ],
    })
    question = next(q for q in course.questions if q.topic_id == topic)
    render_answer_followup(course, question)


def test_followup_only_calls_ai_on_submit_and_is_scoped(monkeypatch):
    tutor = Mock(return_value={'ok': True, 'answer': 'Because of step one.'})
    monkeypatch.setattr(answer_followup, 'ask_tutor', tutor)
    app = AppTest.from_function(followup_app).run()
    assert not tutor.called
    app.text_area[0].set_value('Why?').run()
    assert not tutor.called
    app.button[0].click().run()
    assert tutor.call_count == 1
    assert tutor.call_args.args[2] == 't1'
    assert any('Because of step one.' in item.value for item in app.markdown)
    app.selectbox[0].select('t2').run()
    assert not any('Because of step one.' in item.value for item in app.markdown)
    assert tutor.call_count == 1


def test_blank_and_failure_do_not_record_a_reply(monkeypatch):
    tutor = Mock(return_value={'ok': False, 'message': 'Unavailable'})
    monkeypatch.setattr(answer_followup, 'ask_tutor', tutor)
    app = AppTest.from_function(followup_app).run()
    app.button[0].click().run()
    assert not tutor.called
    app.text_area[0].set_value('Can you explain?').run()
    app.button[0].click().run()
    assert tutor.call_count == 1
    assert any('unavailable' in item.value for item in app.warning)
    assert not app.exception
