"""Regression checks for one help target per module and direction-aware flight."""
import math
import re
import xml.etree.ElementTree as ET

import pytest
from services.paper_progress import progress_route
from tests.test_practice_pages import review_app, start_app, keyed


@pytest.mark.parametrize('index,previous', [(5,0),(0,5)])
def test_plane_nose_follows_the_measured_route_tangent_in_both_directions(index, previous):
    svg = ET.fromstring(progress_route(index, 6, previous))
    style = next(node.text for node in svg if node.tag == 'style')
    frames = [(float(x),float(y),float(angle)) for x,y,angle in re.findall(
        r'translate\(([-\d.]+)px,([-\d.]+)px\) rotate\(([-\d.]+)deg\)',style)]
    assert len(frames) == 21
    assert len({angle for _,_,angle in frames}) > 5
    # Compare the artwork's nose with the actual neighboring path positions,
    # independently of the analytic tangent used by the implementation.
    for before, frame, after in zip(frames, frames[1:], frames[2:]):
        heading = math.atan2(after[1]-before[1],after[0]-before[0])
        nose = math.radians(frame[2]-25)
        assert math.cos(nose-heading) > math.cos(math.radians(3))


def test_reflection_has_one_combined_help_target_and_primary_transfer(monkeypatch):
    monkeypatch.setattr('services.practice_insights_ui.generation_available',lambda:False)
    app = review_app(picks=(1,1))
    assert not app.exception
    tips = [m.value for m in app.markdown if 'role="tooltip"' in m.value]
    reflection = [tip for tip in tips if 'Write your reasoning' in tip]
    assert len(reflection) == 1
    assert 'Save before you go' in reflection[0] and 'AI checking is not configured' in reflection[0]
    assert reflection[0].count('<br><br>') == 2 and '\n\n' not in reflection[0]
    assert sum(tip.count('role="tooltip"') for tip in tips) == 2  # Follow-up + reflection.
    assert app.button(key='transfer_s_q0').proto.type == 'primary'


def test_result_review_action_is_outside_the_two_summary_columns():
    app,_ = start_app(graded=True,picks=(1,1))
    assert not app.exception
    overview = keyed(app,'practice_result_overview')
    assert not any(button.key=='open_answer_review' for button in overview.button)
    action = keyed(app,'result_review_action')
    assert action.button[0].key == 'open_answer_review'
    assert app.button(key='priorities_insights').proto.type == 'primary'
