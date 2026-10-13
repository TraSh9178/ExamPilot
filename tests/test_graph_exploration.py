from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from models.schemas import StudyPackage
from services.graph_exploration import local_graph, related_topics

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def course():
    return StudyPackage.model_validate_json((ROOT / "data/calculus_i_demo.json").read_text())


def test_local_graph_does_not_mutate_course_or_invent_links(course):
    original = course.model_dump()
    result = local_graph(course, "calc_limits")
    assert [topic.id for topic in result.topics] == ["calc_limits", "calc_derivatives"]
    assert all(q.topic_id in {t.id for t in result.topics} for q in result.questions)
    assert len(result.relationships) == 1
    assert course.model_dump() == original
    assert len(local_graph(course, "calc_limits", 2).topics) == 3


def test_related_topics_preserves_prerequisite_direction(course):
    links = related_topics(course, "calc_derivatives")
    assert links == {"prerequisites": ["calc_limits"], "next_topics": ["calc_derivative_applications"], "related": []}


@pytest.mark.parametrize("depth", [0, 4, -1])
def test_local_graph_rejects_bad_depth(course, depth):
    with pytest.raises(ValueError):
        local_graph(course, "calc_limits", depth)


def test_missing_topic_is_rejected(course):
    for fn in (local_graph, related_topics):
        with pytest.raises(ValueError):
            fn(course, "not-a-topic")


def test_search_shows_summary_and_local_graph_preserves_original_course(course):
    app = AppTest.from_file(str(ROOT / "pages/4_Knowledge_Graph.py"))
    app.session_state["current_course"] = course
    app.run()
    app.selectbox(key="graph_focus_calculus-i-demo").set_value("calc_limits").run()
    assert not app.exception
    assert any(header.value == "Summary" for header in app.subheader)
    assert any("Limits describe" in entry.value for entry in app.markdown)
    app.toggle(key="graph_local_calculus-i-demo").set_value(True).run()
    assert not app.exception
    assert any("Showing 2 of 3" in entry.value for entry in app.caption)
    assert len(app.session_state["current_course"].topics) == 3
    app.selectbox(key="graph_focus_calculus-i-demo").set_value(None).run()
    assert not app.exception
    assert any("Click a knowledge point" in entry.value for entry in app.info)
