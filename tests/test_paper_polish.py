from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from streamlit.testing.v1 import AppTest
from services.demo_teaching import LESSONS, calculus_lesson
from models.schemas import StudyPackage
from services.paper_progress import progress_route

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('chinese', [False, True])
def test_every_calculus_demo_topic_has_a_complete_offline_lesson(chinese):
    course = StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))
    assert set(LESSONS) == {t.id for t in course.topics}
    for topic in course.topics:
        steps, worked, mistake = calculus_lesson(topic.id, chinese)
        assert len(steps) == 3 and all(step.strip() for step in steps)
        assert len(worked) > 40 and len(mistake) > 5


def test_demo_teaching_needs_no_ai_and_hides_examples_until_chosen(monkeypatch):
    from components import topic_explanation
    monkeypatch.setattr(topic_explanation, 'ask_tutor', lambda *a, **k: pytest.fail('Demo must work offline'))
    app = AppTest.from_file(str(ROOT/'pages/14_Topic_Details.py'))
    course = StudyPackage.model_validate_json((ROOT/'data/calculus_i_demo.json').read_text(encoding='utf-8'))
    app.session_state['current_course'] = course
    app.session_state['topic_details_calculus-i-demo'] = 'calc_limits'
    monkeypatch.setattr('streamlit.switch_page', lambda *a, **k: None)
    app.run()
    assert not app.exception and not app.warning
    assert 'Step-by-step explanation' in [s.value for s in app.subheader]
    assert not app.radio and not app.checkbox
    assert app.selectbox[0].value is None
    app.selectbox[0].select(course.questions[0].id).run()
    assert not app.exception
    assert not app.selectbox
    assert len(app.radio) == 1


@pytest.mark.parametrize('index,previous,total', [(0,None,1),(2,1,6),(0,5,6),(99,-2,24)])
def test_route_is_valid_svg_with_a_winding_path_and_bounded_flight(index, previous, total):
    svg = ET.fromstring(progress_route(index,total,previous))
    # Markdown gives this outer SVG its namespace in the browser; XML is literal.
    circles = [node for node in svg if node.tag == 'circle']
    assert len(circles) == min(total,12)
    route = next(node for node in svg if node.tag == 'path')
    assert len(set(pair.split(',')[1] for pair in route.attrib['d'].split(' L')[1:])) > 10
    import math
    plane = next(node for node in svg if node.attrib.get('class') == 'route-plane-moving')
    fraction = max(0, min(index/max(1,total-1),1))
    assert plane.attrib['transform'].startswith(f'translate({20+560*fraction:.2f} {48+22*math.sin(4*math.pi*fraction):.2f}) rotate(')
    style = next(node.text for node in svg if node.tag == 'style')
    assert '@keyframes route-flight-' in style and '100%' in style


def test_tooltip_escapes_text_and_connects_native_focus_target():
    text = '<script>never run</script> & "quote"'
    app = AppTest.from_string('from services.ui_help import help_tip\nhelp_tip(' + repr(text) + ')').run()
    assert not app.exception
    markup = app.markdown[0].value
    assert '<script>' not in markup and '&lt;script&gt;' in markup
    assert 'role="tooltip"' in markup and 'aria-describedby="help-' in markup
