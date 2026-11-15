from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests.test_learning_dna import course_and_history
from tests.test_practice_insights import start_app

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_uses_learning_details_without_internal_identifiers():
    course, history = course_and_history()
    course.learning_state['practice_insights'] = {'s': {'q0': {'confidence': 'sure'}}}
    app = AppTest.from_file(str(ROOT/'pages/3_Performance.py'))
    app.session_state['current_course'] = course
    app.session_state['performance_mode_test-dna'] = 'Topic Practice'
    app.session_state['practice_history_test-dna'] = history
    app.run()
    assert not app.exception
    frames = [frame.value for frame in app.dataframe if 'Dimension' in frame.value.columns]
    assert frames
    for frame in frames:
        assert 'Question ID' not in frame.columns and 'Session' not in frame.columns
        assert {'Question','Latest answer','Confidence','In-app hints shown'}.issubset(frame.columns)
    assert 'Sure' in frames[0]['Confidence'].values


def test_course_maintenance_is_grouped_on_its_own_page_with_pending_review():
    from tests.test_learning_flow_ux import calculus
    app = AppTest.from_file(str(ROOT/'pages/1_Study_Hub.py'))
    app.session_state['current_course'] = calculus()
    app.run()
    assert not app.exception
    # Study Plan keeps one small Course tools button and none of the tools.
    assert [b.label for b in app.button].count('Course tools') == 1
    assert not app.expander
    top_labels = [getattr(node,'label',None) for node in app.main.children.values()]
    assert 'Review and edit questions' not in top_labels
    assert 'Save / Restore' not in top_labels and 'Saved course material' not in top_labels
    # Pending questions do not put a review prompt on the student's page.
    assert 'Review pending questions' not in [b.label for b in app.button]

    tools = AppTest.from_file(str(ROOT/'pages/9_Course_Tools.py'))
    tools.session_state['current_course'] = calculus()
    tools.run()
    assert not tools.exception
    # One tool at a time; the review tool first, its classification collapsed.
    assert tools.button_group(key='course_tools_choice_calculus-i-demo').value == 'review'
    assert not any((b.key or '').startswith('database_') for b in tools.button)
    assert not tools.checkbox
    assert not next(e for e in tools.expander if e.label=='Question classification (advanced)').proto.expanded


def test_saved_session_display_is_readable_and_selection_keeps_stable_ids():
    app,_ = start_app(graded=True)
    selector = app.selectbox(key='saved_session_insights')
    assert selector.value == 's'
    assert list(selector.options) == ['1 · Topic practice · 2 questions · 1/2 correct']
    app.button(key='open_saved_result_insights').click().run()
    assert not app.exception
    assert app.session_state['active_practice_insights']['session'].session_id == 's'
