import json
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from services.concept_lab import corner_slopes
from services.i18n import LANGUAGE_KEY

PAGE=Path(__file__).resolve().parents[1]/'pages/6_Concept_Lab.py'


@pytest.mark.parametrize('distance',[1.,0.5,0.01,0.001])
def test_absolute_value_one_sided_slopes_disagree_at_every_scale(distance):
    assert corner_slopes(distance)==(-1.,1.)


@pytest.mark.parametrize('distance',[0.,-1.,float('inf'),float('nan')])
def test_corner_distance_must_be_positive_finite(distance):
    with pytest.raises(ValueError):corner_slopes(distance)


def test_saved_comparison_stays_fixed_and_is_hidden_at_another_x0():
    app=AppTest.from_file(str(PAGE)).run()
    app.button(key='lab_save_secant').click().run()
    saved=dict(app.session_state['lab_saved_secant'])
    app.select_slider(key='concept_lab_h').set_value(0.01).run()
    assert not app.exception
    assert app.session_state['lab_saved_secant']==saved
    spec=json.loads(app.get('vega_lite_chart')[1].proto.spec)
    assert 'Saved secant' in spec['layer'][0]['encoding']['color']['scale']['domain']
    app.slider(key='concept_lab_x0').set_value(2.).run()
    spec=json.loads(app.get('vega_lite_chart')[1].proto.spec)
    assert 'Saved secant' not in spec['layer'][0]['encoding']['color']['scale']['domain']
    assert any('x₀ changed' in c.value for c in app.caption)
    app.button(key='lab_derivatives_reset').click().run()
    assert 'lab_saved_secant' not in app.session_state


def test_corner_controls_do_not_change_derivative_controls_or_private_history():
    app=AppTest.from_file(str(PAGE)).run()
    app.session_state['practice_history_calculus-i-demo']={'keep':'unchanged'}
    app.slider(key='concept_lab_x0').set_value(2.).run()
    app.select_slider(key='concept_lab_corner_h').set_value(0.001).run()
    assert float(app.metric[-2].value)==-1 and float(app.metric[-1].value)==1
    app.button(key='lab_corner_reset').click().run()
    assert not app.exception
    assert app.slider(key='concept_lab_x0').value==2.
    assert app.select_slider(key='concept_lab_corner_h').value==0.5
    assert app.session_state['practice_history_calculus-i-demo']=={'keep':'unchanged'}


@pytest.mark.parametrize('key,choice,expected',[
    ('limits','Undefined because f(2) is undefined','missing point'),
    ('derivatives','The function value f(x₀)','height'),
    ('corner','Continuous and differentiable at 0','Continuity alone'),
])
def test_feedback_targets_the_selected_misconception(key,choice,expected):
    app=AppTest.from_file(str(PAGE)).run()
    app.radio(key=f'lab_{key}_prediction').set_value(choice).run()
    app.button(key=f'lab_{key}_check').click().run()
    assert not app.exception
    assert any(expected in i.value for i in app.info)


def test_corner_and_saved_graph_labels_follow_chinese_setting():
    app=AppTest.from_file(str(PAGE))
    app.session_state[LANGUAGE_KEY]=True
    app.run().button(key='lab_save_secant').click().run()
    assert not app.exception
    assert app.tabs[-1].label=='尖点与可导性'
    spec=json.loads(app.get('vega_lite_chart')[1].proto.spec)
    names=spec['layer'][0]['encoding']['color']['scale']['domain']
    assert names==spec['layer'][0]['encoding']['strokeDash']['scale']['domain']
    assert '已保存的割线' in names
