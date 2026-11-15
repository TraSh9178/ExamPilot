from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from services.concept_lab import secant_slope, cubic_derivative

PAGE=Path(__file__).resolve().parents[1]/'pages/6_Concept_Lab.py'


def test_prediction_feedback_is_optional_and_does_not_record_an_exam():
    app=AppTest.from_file(str(PAGE)).run()
    app.button(key='lab_limits_check').click().run()
    assert any('Choose a prediction' in x.value for x in app.info)
    app.radio(key='lab_limits_prediction').set_value('0').run()
    app.button(key='lab_limits_check').click().run()
    assert any('zero numerator' in x.value for x in app.info)
    app.radio(key='lab_limits_prediction').set_value('4').run()
    assert not any('Your prediction' in x.value for x in app.success)
    app.button(key='lab_limits_check').click().run()
    assert any('Your prediction' in x.value for x in app.success)
    assert not any(k.startswith('practice_history_') for k in app.session_state.filtered_state)


@pytest.mark.parametrize('topic,key,start',[('limits','concept_lab_limit_distance',0.1),('derivatives','concept_lab_h',0.5)])
def test_step_closer_has_a_finite_end_and_reset_restores_controls(topic,key,start):
    app=AppTest.from_file(str(PAGE)).run()
    app.session_state['private_record']={'score':42}
    for _ in range(6):
        button=app.button(key=f'lab_{topic}_approach')
        if not button.disabled: button.click().run()
    assert app.select_slider(key=key).value==0.001
    assert app.button(key=f'lab_{topic}_approach').disabled
    app.button(key=f'lab_{topic}_reset').click().run()
    assert not app.exception
    assert app.select_slider(key=key).value==start
    assert app.session_state['private_record']=={'score':42}
    assert not any('Session State API' in w.value for w in app.warning)


@pytest.mark.parametrize('x0',[-3.,0.,1.,3.])
def test_left_approach_uses_signed_h_and_converges(x0):
    app=AppTest.from_file(str(PAGE)).run()
    app.slider(key='concept_lab_x0').set_value(x0).run()
    app.radio(key='concept_lab_side').set_value('Left').run()
    errors=[]
    for size in [1,0.001]:
        app.select_slider(key='concept_lab_h').set_value(size).run()
        assert not app.exception
        actual=float(app.metric[2].value)
        assert actual==pytest.approx(secant_slope(x0,-size),abs=1e-6)
        errors.append(abs(actual-cubic_derivative(x0)))
    assert errors[-1]<errors[0]
    app.button(key='lab_derivatives_reset').click().run()
    assert app.radio(key='concept_lab_side').value=='Right'
    assert app.slider(key='concept_lab_x0').value==1.0


def test_new_controls_translate_without_changing_widget_contracts():
    from services.i18n import LANGUAGE_KEY
    app=AppTest.from_file(str(PAGE))
    app.session_state[LANGUAGE_KEY]=True
    app.run()
    assert not app.exception
    assert app.button(key='lab_limits_reset').label=='重置实验'
    assert app.radio(key='concept_lab_side').options==['右侧','左侧']
    assert app.button(key='concept_lab_practice_calc_derivatives').label
