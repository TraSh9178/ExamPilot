import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

from streamlit_agraph import Edge, Node
import pytest
from streamlit.testing.v1 import AppTest

import components.knowledge_graph as knowledge_graph
from components.knowledge_graph import MIN_NODE_SIZE, convert_graph_data
from models.schemas import StudyPackage, TopicStats
from services import learning_radar
from services.postgres_store import PersistenceResult
from tests.auth_helpers import TEST_USER, signed_in_app


def test_convert_graph_data_preserves_node_ids_labels_and_mastery_colors():
    graph = {
        "nodes": [
            {
                "id": "t1",
                "label": "Topic 1",
                "status": "unattempted",
                "color": "#94A3B8",
            },
            {
                "id": "t2",
                "label": "Topic 2",
                "status": "insufficient_evidence",
                "color": "#A78BFA",
            },
            {
                "id": "t3",
                "label": "Topic 3",
                "status": "weak",
                "color": "#EF4444",
            },
            {
                "id": "t4",
                "label": "Topic 4",
                "status": "developing",
                "color": "#F59E0B",
            },
            {
                "id": "t5",
                "label": "Topic 5",
                "status": "mastered",
                "color": "#22C55E",
            },
        ],
        "edges": [],
    }

    nodes, edges = convert_graph_data(graph)

    assert all(isinstance(node, Node) for node in nodes)
    assert [
        (node.id, node.label, node.color, node.size, node.font)
        for node in nodes
    ] == [
        (
            "t1",
            "Topic 1",
            "#94A3B8",
            MIN_NODE_SIZE,
            {
                "color": "#102044",
                "size": 16,
                "face": "Arial",
                "strokeWidth": 4,
                "strokeColor": "#FFFFFF",
            },
        ),
        (
            "t2",
            "Topic 2",
            "#A78BFA",
            MIN_NODE_SIZE,
            {
                "color": "#102044",
                "size": 16,
                "face": "Arial",
                "strokeWidth": 4,
                "strokeColor": "#FFFFFF",
            },
        ),
        (
            "t3",
            "Topic 3",
            "#EF4444",
            MIN_NODE_SIZE,
            {
                "color": "#102044",
                "size": 16,
                "face": "Arial",
                "strokeWidth": 4,
                "strokeColor": "#FFFFFF",
            },
        ),
        (
            "t4",
            "Topic 4",
            "#F59E0B",
            MIN_NODE_SIZE,
            {
                "color": "#102044",
                "size": 16,
                "face": "Arial",
                "strokeWidth": 4,
                "strokeColor": "#FFFFFF",
            },
        ),
        (
            "t5",
            "Topic 5",
            "#22C55E",
            MIN_NODE_SIZE,
            {
                "color": "#102044",
                "size": 16,
                "face": "Arial",
                "strokeWidth": 4,
                "strokeColor": "#FFFFFF",
            },
        ),
    ]
    assert edges == []


def test_convert_graph_data_distinguishes_relationship_types():
    graph = {
        "nodes": [],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "type": "prerequisite",
            },
            {
                "source": "a",
                "target": "c",
                "type": "related",
            },
        ],
    }

    nodes, edges = convert_graph_data(graph)
    prerequisite, related = edges

    assert nodes == []
    assert all(isinstance(edge, Edge) for edge in edges)
    assert (prerequisite.source, prerequisite.to) == ("a", "b")
    assert prerequisite.label == "Prerequisite"
    assert prerequisite.color == "#2563EB"
    assert prerequisite.dashes is True
    assert prerequisite.arrows == {"to": {"enabled": True}}
    assert prerequisite.font == {"size": 14}
    assert (related.source, related.to) == ("a", "c")
    assert related.label == "Related"
    assert related.color == "#64748B"
    assert related.font == {"size": 14}
    assert related.arrows == {
        "from": {"enabled": False},
        "to": {"enabled": False},
    }


def test_convert_graph_data_handles_empty_graph():
    assert convert_graph_data({"nodes": [], "edges": []}) == ([], [])

    assert MIN_NODE_SIZE == 36


def test_agraph_sends_existing_graph_data_to_bounded_component(monkeypatch):
    nodes = [Node(id="topic-1", label="Topic 1", color="#94A3B8")]
    edges = [Edge(source="topic-1", target="topic-2", label="Related")]
    config = knowledge_graph.Config(height=540, width=900)
    config.width = "100%"
    config.layout["randomSeed"] = 47
    calls = []

    def render_component(**kwargs):
        calls.append(kwargs)
        return "topic-1"

    monkeypatch.setattr(
        knowledge_graph,
        "_bounded_graph_component",
        render_component,
    )

    result = knowledge_graph.agraph(nodes, edges, config)

    assert result == "topic-1"
    assert calls[0]["payload"] == {
        "graph": {
            "nodes": [node.to_dict() for node in nodes],
            "edges": [edge.to_dict() for edge in edges],
        },
        "config": config.to_dict(),
        "nodeScale": 1.0,
    }
    assert calls[0]["key"] == "bounded_graph_47"
    assert calls[0]["default"] is None


def test_agraph_preserves_none_for_deselection(monkeypatch):
    config = knowledge_graph.Config(height=540, width="100%")
    config.layout["randomSeed"] = 42
    monkeypatch.setattr(
        knowledge_graph,
        "_bounded_graph_component",
        lambda **kwargs: None,
    )

    assert knowledge_graph.agraph([], [], config) is None


def test_convert_graph_data_rejects_unknown_relationship_type():
    graph = {
        "nodes": [],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "type": "unknown",
            },
        ],
    }

    with pytest.raises(ValueError, match="Unknown relationship type: unknown"):
        convert_graph_data(graph)


def test_render_knowledge_graph_builds_config_and_returns_selection(monkeypatch):
    package = object()
    stats = []
    graph = {"nodes": [], "edges": []}
    nodes = [Node(id="t1", label="Topic 1", color="#94A3B8")]
    edges = [Edge(source="t1", target="t2")]
    actual_config = knowledge_graph.Config
    selected_node_id = "t1"
    build_calls = []
    conversion_calls = []
    config_calls = []
    agraph_calls = []

    def build(package_arg, stats_arg, mode_arg):
        build_calls.append((package_arg, stats_arg, mode_arg))
        return graph

    def convert(graph_arg):
        conversion_calls.append(graph_arg)
        return nodes, edges

    def make_config(**kwargs):
        config_calls.append(kwargs)
        return actual_config(**kwargs)

    def render(nodes_arg, edges_arg, config_arg, node_scale_arg):
        agraph_calls.append(
            (nodes_arg, edges_arg, config_arg, node_scale_arg)
        )
        return selected_node_id

    monkeypatch.setattr(knowledge_graph, "build_mastery_graph", build)
    monkeypatch.setattr(knowledge_graph, "convert_graph_data", convert)
    monkeypatch.setattr(knowledge_graph, "Config", make_config)
    monkeypatch.setattr(knowledge_graph, "agraph", render)

    result = knowledge_graph.render_knowledge_graph(
        package,
        stats,
        "mock",
        node_scale=1.15,
    )

    assert result == selected_node_id
    assert build_calls == [(package, stats, "mock")]
    assert conversion_calls == [graph]
    assert config_calls == [
        {
            "height": 540,
            "width": 900,
            "physics": True,
            "hierarchical": False,
            "groups": {},
            "interaction": {
                "dragNodes": True,
                "zoomView": True,
                "dragView": True,
            },
        }
    ]
    assert len(agraph_calls) == 1
    assert agraph_calls[0][:2] == (nodes, edges)
    actual_config = agraph_calls[0][2]
    assert agraph_calls[0][3] == 1.15
    assert actual_config.width == "100%"
    assert actual_config.layout["randomSeed"] == 42


def test_render_knowledge_graph_with_isolated_topics(monkeypatch):
    package = StudyPackage(
        course_id="calculus",
        course_name="Calculus I Demo",
        topics=[
            {
                "id": topic_id,
                "name": topic_name,
                "summary": f"Summary for {topic_name}.",
            }
            for topic_id, topic_name in (
                ("limits", "Limits"),
                ("derivatives", "Derivatives"),
                ("integrals", "Integrals"),
            )
        ],
        relationships=[],
        questions=[],
    )
    render_calls = []

    def render(nodes, edges, config, node_scale):
        render_calls.append((nodes, edges, config, node_scale))
        return None

    monkeypatch.setattr(knowledge_graph, "agraph", render)

    assert knowledge_graph.render_knowledge_graph(package, [], "mock") is None

    assert len(render_calls) == 1
    nodes, edges, config, node_scale = render_calls[0]
    assert len(nodes) == 3
    assert {node.id for node in nodes} == {
        "limits",
        "derivatives",
        "integrals",
    }
    assert edges == []
    assert node_scale == 1.0

    serialized_config = json.loads(json.dumps(config.__dict__))
    assert serialized_config["groups"] == {}
    assert config.physics["enabled"] is True
    assert config.physics["solver"] == "forceAtlas2Based"
    assert config.physics["forceAtlas2Based"] == {
        "gravitationalConstant": -50,
        "centralGravity": 0.015,
        "springLength": 160,
        "springConstant": 0.08,
        "damping": 0.4,
        "avoidOverlap": 0.8,
    }
    assert config.physics["solver"] == "forceAtlas2Based"
    assert config.physics["forceAtlas2Based"] == {
        "gravitationalConstant": -50,
        "centralGravity": 0.015,
        "springLength": 160,
        "springConstant": 0.08,
        "damping": 0.4,
        "avoidOverlap": 0.8,
    }
    assert config.layout["hierarchical"]["enabled"] is False
    assert config.physics["stabilization"] == {
        "enabled": True,
        "iterations": 1000,
        "fit": True,
    }
    assert config.interaction == {
        "dragNodes": True,
        "zoomView": True,
        "dragView": True,
    }


def test_render_knowledge_graph_changes_layout_seed_for_view_reset(monkeypatch):
    render_calls = []
    monkeypatch.setattr(
        knowledge_graph,
        "agraph",
        lambda nodes, edges, config, node_scale: (
            render_calls.append((config, node_scale)) or None
        ),
    )
    package = StudyPackage(
        course_id="course",
        course_name="Course",
        topics=[],
        relationships=[],
        questions=[],
    )

    knowledge_graph.render_knowledge_graph(
        package,
        [],
        "mock",
        view_reset=3,
    )

    assert render_calls[0][0].layout["randomSeed"] == 45
    assert render_calls[0][1] == 1.0


def test_knowledge_graph_zoom_buttons_update_scale_and_are_course_scoped():
    page_path = (
        Path(__file__).resolve().parents[1]
        / "pages"
        / "4_Knowledge_Graph.py"
    )
    course = StudyPackage(
        course_id="zoom-course",
        course_name="Zoom Course",
        topics=[
            {"id": "topic-1", "name": "Topic", "summary": "Summary."}
        ],
        relationships=[],
        questions=[],
    )
    app = AppTest.from_file(str(page_path))
    app.session_state["current_course"] = course

    app.run()

    assert not app.exception
    assert not any(
        "transform: scale(" in item.value
        for item in app.markdown
    )

    app.button(key="graph_zoom_in_zoom-course_mock").click().run()

    assert not app.exception
    assert app.session_state["graph_zoom_zoom-course_mock"] == 1
    assert not any(
        "transform: scale(" in item.value
        for item in app.markdown
    )

    app.button(key="graph_zoom_out_zoom-course_mock").click().run()

    assert not app.exception
    assert app.session_state["graph_zoom_zoom-course_mock"] == 0


def test_graph_page_updates_cached_calculus_demo_relationships():
    demo_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "calculus_i_demo.json"
    )
    current_course = StudyPackage.model_validate_json(
        demo_path.read_text(encoding="utf-8")
    )
    old_course = current_course.model_copy(update={"relationships": []})
    page_path = (
        Path(__file__).resolve().parents[1]
        / "pages"
        / "4_Knowledge_Graph.py"
    )
    app = AppTest.from_file(str(page_path))
    app.session_state["current_course"] = old_course

    app.run()

    assert not app.exception
    updated_course = app.session_state["current_course"]
    assert [
        (relation.from_topic, relation.to_topic)
        for relation in updated_course.relationships
    ] == [
        ("calc_limits", "calc_derivatives"),
        ("calc_derivatives", "calc_derivative_applications"),
    ]
    assert updated_course.questions == old_course.questions
    assert app.session_state["courses"][0] == updated_course


@pytest.mark.parametrize(
    "source_pages",
    [
        [2, 5],
        [],
    ],
)
def test_get_selected_topic_details_returns_topic_and_mastery_data(
    source_pages,
):
    package = StudyPackage(
        course_id="course",
        course_name="Course",
        topics=[
            {
                "id": "t1",
                "name": "Topic 1",
                "summary": "Topic summary",
                "source_pages": source_pages,
            }
        ],
        relationships=[],
        questions=[],
    )
    graph = {
        "nodes": [
            {
                "id": "t1",
                "label": "Topic 1",
                "status": "developing",
                "color": "#F59E0B",
            }
        ],
        "edges": [],
    }

    details = knowledge_graph.get_selected_topic_details(
        "t1", package, graph
    )

    assert details == {
        "id": "t1",
        "name": "Topic 1",
        "summary": "Topic summary",
        "source_pages": source_pages,
        "status": "developing",
        "color": "#F59E0B",
    }
    assert details["source_pages"] is not package.topics[0].source_pages


def test_get_selected_topic_details_returns_none_without_selection():
    package = StudyPackage(
        course_id="course",
        course_name="Course",
        topics=[],
        relationships=[],
        questions=[],
    )

    assert knowledge_graph.get_selected_topic_details(
        None, package, {"nodes": []}
    ) is None


def test_get_selected_topic_details_returns_none_for_unknown_node():
    package = StudyPackage(
        course_id="course",
        course_name="Course",
        topics=[
            {
                "id": "t1",
                "name": "Topic 1",
                "summary": "Topic summary",
                "source_pages": [],
            }
        ],
        relationships=[],
        questions=[],
    )
    graph = {"nodes": [], "edges": []}

    assert knowledge_graph.get_selected_topic_details(
        "unknown", package, graph
    ) is None


def test_render_topic_details_displays_details_with_source_pages(monkeypatch):
    info = Mock()
    subheader = Mock()
    write = Mock()
    caption = Mock()
    metric = Mock()
    badge = Mock()
    monkeypatch.setattr(
        knowledge_graph.st,
        "container",
        lambda **kwargs: nullcontext(),
    )
    monkeypatch.setattr(knowledge_graph.st, "info", info)
    monkeypatch.setattr(knowledge_graph.st, "subheader", subheader)
    monkeypatch.setattr(knowledge_graph.st, "write", write)
    monkeypatch.setattr(knowledge_graph.st, "caption", caption)
    monkeypatch.setattr(knowledge_graph.st, "metric", metric)
    monkeypatch.setattr(knowledge_graph.st, "badge", badge)

    knowledge_graph.render_topic_details(
        {
            "name": "Topic 1",
            "summary": "A short summary.",
            "source_pages": [2, 5],
            "status": "developing",
            "color": "#F59E0B",
        }
    )

    assert [
        args.args for args in subheader.call_args_list
    ] == [
        ("Topic 1",),
        ("Summary",),
    ]
    write.assert_called_once_with("A short summary.")
    caption.assert_called_once_with("Source pages: 2, 5")
    badge.assert_called_once_with("Developing", color="orange")
    metric.assert_not_called()
    info.assert_not_called()

def test_render_topic_details_displays_topic_statistics(monkeypatch):
    answers_column = Mock()
    accuracy_column = Mock()
    monkeypatch.setattr(
        knowledge_graph.st,
        "container",
        lambda **kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        knowledge_graph.st,
        "columns",
        Mock(return_value=[answers_column, accuracy_column]),
    )
    monkeypatch.setattr(knowledge_graph.st, "subheader", Mock())
    monkeypatch.setattr(knowledge_graph.st, "write", Mock())
    monkeypatch.setattr(knowledge_graph.st, "caption", Mock())
    monkeypatch.setattr(knowledge_graph.st, "badge", Mock())

    knowledge_graph.render_topic_details(
        {
            "name": "Topic 1",
            "summary": "A short summary.",
            "source_pages": [],
            "status": "developing",
            "color": "#F59E0B",
        },
        TopicStats(
            topic_id="t1",
            mode="mock",
            correct=2,
            attempted=3,
            accuracy=66.67,
        ),
    )

    answers_column.metric.assert_called_once_with("Answers", 3)
    accuracy_column.metric.assert_called_once_with("Accuracy", "66.67%")


def test_render_topic_details_shows_missing_pages_message(monkeypatch):
    caption = Mock()
    monkeypatch.setattr(
        knowledge_graph.st,
        "container",
        lambda **kwargs: nullcontext(),
    )
    monkeypatch.setattr(knowledge_graph.st, "caption", caption)
    monkeypatch.setattr(knowledge_graph.st, "subheader", Mock())
    monkeypatch.setattr(knowledge_graph.st, "write", Mock())
    monkeypatch.setattr(knowledge_graph.st, "badge", Mock())

    knowledge_graph.render_topic_details(
        {
            "name": "Topic 1",
            "summary": "A short summary.",
            "source_pages": [],
            "status": "unattempted",
            "color": "#94A3B8",
        }
    )

    caption.assert_called_once_with("Source pages not provided")


def test_render_topic_details_prompts_when_no_topic_is_selected(monkeypatch):
    info = Mock()
    subheader = Mock()
    write = Mock()
    caption = Mock()
    metric = Mock()
    badge = Mock()
    container = Mock()
    monkeypatch.setattr(knowledge_graph.st, "container", container)
    monkeypatch.setattr(knowledge_graph.st, "info", info)
    monkeypatch.setattr(knowledge_graph.st, "subheader", subheader)
    monkeypatch.setattr(knowledge_graph.st, "write", write)
    monkeypatch.setattr(knowledge_graph.st, "caption", caption)
    monkeypatch.setattr(knowledge_graph.st, "metric", metric)
    monkeypatch.setattr(knowledge_graph.st, "badge", badge)

    knowledge_graph.render_topic_details(None)

    info.assert_called_once_with(
        "Click a knowledge point to see its details."
    )
    subheader.assert_not_called()
    write.assert_not_called()
    caption.assert_not_called()
    metric.assert_not_called()
    badge.assert_not_called()
    container.assert_not_called()


# --- Learning Radar -------------------------------------------------------

PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "4_Knowledge_Graph.py"
CALCULUS_DEMO_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "calculus_i_demo.json"
)
CALCULUS_ID = "calculus-i-demo"
CACHE_KEY = f"learning_radar_cache_{CALCULUS_ID}"
RADAR_FUNCTIONS = (
    "radar_enabled",
    "get_course_radar",
    "get_user_flags",
    "top_hard_topics",
    "set_flag",
    "clear_flag",
)


def _badge_graph():
    return {
        "nodes": [
            {"id": "t1", "label": "Topic 1", "status": "weak", "color": "#EF4444"},
            {"id": "t2", "label": "Topic 2", "status": "mastered", "color": "#22C55E"},
        ],
        "edges": [{"source": "t1", "target": "t2", "type": "prerequisite"}],
    }


def _as_dicts(converted):
    nodes, edges = converted
    return [node.to_dict() for node in nodes], [edge.to_dict() for edge in edges]


def test_convert_graph_data_appends_badge_to_matching_node_label_only():
    plain_nodes, plain_edges = _as_dicts(convert_graph_data(_badge_graph()))

    badged_nodes, badged_edges = _as_dicts(
        convert_graph_data(
            _badge_graph(),
            node_badges={"t2": "🔥 4 stuck", "not-a-node": "🔥 9 stuck"},
        )
    )

    assert badged_nodes[1]["label"] == "Topic 2\n🔥 4 stuck"
    assert badged_nodes[0] == plain_nodes[0]
    assert {key: value for key, value in badged_nodes[1].items() if key != "label"} == {
        key: value for key, value in plain_nodes[1].items() if key != "label"
    }
    assert len(badged_nodes) == len(plain_nodes) == 2
    assert badged_edges == plain_edges


@pytest.mark.parametrize("badges", [None, {}])
def test_convert_graph_data_without_badges_is_unchanged(badges):
    assert _as_dicts(
        convert_graph_data(_badge_graph(), node_badges=badges)
    ) == _as_dicts(convert_graph_data(_badge_graph()))
    assert [
        node.label
        for node in convert_graph_data(_badge_graph(), node_badges=badges)[0]
    ] == ["Topic 1", "Topic 2"]


def _install_graph_fakes(monkeypatch, convert):
    graph = {"nodes": [], "edges": []}
    monkeypatch.setattr(
        knowledge_graph, "build_mastery_graph", lambda *args: graph
    )
    monkeypatch.setattr(knowledge_graph, "convert_graph_data", convert)
    monkeypatch.setattr(
        knowledge_graph,
        "agraph",
        lambda nodes, edges, config, node_scale: None,
    )
    return graph


def test_render_knowledge_graph_passes_badges_to_converter(monkeypatch):
    conversions = []

    def convert(graph_arg, node_badges=None):
        conversions.append((graph_arg, node_badges))
        return [], []

    graph = _install_graph_fakes(monkeypatch, convert)

    knowledge_graph.render_knowledge_graph(
        object(), [], "mock", node_badges={"t1": "🔥 3 stuck"}
    )

    assert conversions == [(graph, {"t1": "🔥 3 stuck"})]


@pytest.mark.parametrize("badges", [None, {}])
def test_render_knowledge_graph_calls_converter_with_one_argument_without_badges(
    monkeypatch, badges,
):
    conversions = []

    def convert(*args, **kwargs):
        conversions.append((args, kwargs))
        return [], []

    graph = _install_graph_fakes(monkeypatch, convert)

    knowledge_graph.render_knowledge_graph(
        object(), [], "mock", node_badges=badges
    )

    assert conversions == [((graph,), {})]


def _topic(topic_id, real=0, sample=0, display="total"):
    return learning_radar.TopicRadar(
        topic_id=topic_id,
        real_count=real,
        sample_count=sample,
        reasons={},
        display_count=real + sample if display == "total" else display,
    )


@pytest.mark.parametrize(
    ("topic_radar", "count_text", "badge"),
    [
        (None, "No one has flagged this topic yet.", None),
        (_topic("t", real=1, sample=0, display=None), "Some students flagged this", "🔥 flagged"),
        (_topic("t", real=0, sample=1), "1 student is stuck here", "🔥 1 stuck"),
        (_topic("t", real=3, sample=5), "8 students are stuck here", "🔥 8 stuck"),
    ],
)
def test_radar_text_helpers(topic_radar, count_text, badge):
    assert knowledge_graph.radar_count_text(topic_radar) == count_text
    if badge is not None:
        assert knowledge_graph.radar_badge(topic_radar) == badge


def _calculus_course():
    return StudyPackage.model_validate_json(
        CALCULUS_DEMO_PATH.read_text(encoding="utf-8")
    )


def _other_course():
    return StudyPackage(
        course_id="course-1",
        course_name="Course One",
        topics=[
            {"id": "topic-1", "name": "Limits", "summary": "Limits summary."},
            {"id": "topic-2", "name": "Series", "summary": "Series summary."},
        ],
        relationships=[],
        questions=[],
    )


class RadarFake:
    """Scripted replacement for the learning_radar functions.

    Every call is recorded. Successful writes update the scripted state, so a
    refetch after a flag or clear returns the new counts.
    """

    def __init__(
        self,
        monkeypatch,
        topics=(),
        *,
        enabled=True,
        live=True,
        has_sample=False,
        user_flags=None,
        write_result=None,
        ranked=None,
    ):
        self.topics = {topic.topic_id: topic for topic in topics}
        self.enabled = enabled
        self.live = live
        self.has_sample = has_sample
        self.user_flags = dict(user_flags or {})
        self.write_result = write_result
        self.ranked = ranked
        self.calls = {name: [] for name in RADAR_FUNCTIONS}
        for name in RADAR_FUNCTIONS:
            monkeypatch.setattr(learning_radar, name, getattr(self, name))

    def radar_enabled(self, course_id):
        self.calls["radar_enabled"].append(course_id)
        return self.enabled

    def get_course_radar(self, course_id):
        self.calls["get_course_radar"].append(course_id)
        return learning_radar.CourseRadar(
            topics=dict(self.topics), live=self.live, has_sample=self.has_sample
        )

    def get_user_flags(self, user_id, course_id):
        self.calls["get_user_flags"].append((user_id, course_id))
        return dict(self.user_flags)

    def top_hard_topics(self, radar, limit=3):
        self.calls["top_hard_topics"].append((radar, limit))
        if self.ranked is not None:
            return [radar.topics[topic_id] for topic_id in self.ranked][:limit]
        return sorted(
            radar.topics.values(),
            key=lambda topic: -(topic.real_count + topic.sample_count),
        )[:limit]

    def _change(self, topic_id, delta):
        current = self.topics.get(topic_id, _topic(topic_id))
        self.topics[topic_id] = _topic(
            topic_id, real=current.real_count + delta, sample=current.sample_count
        )

    def set_flag(self, user_id, course_id, topic_id, reason=None):
        self.calls["set_flag"].append((user_id, course_id, topic_id))
        if self.write_result is not None:
            return self.write_result
        self._change(topic_id, 1)
        self.user_flags[topic_id] = reason
        return PersistenceResult(success=True, message="Flag saved.")

    def clear_flag(self, user_id, course_id, topic_id):
        self.calls["clear_flag"].append((user_id, course_id, topic_id))
        if self.write_result is not None:
            return self.write_result
        self._change(topic_id, -1)
        self.user_flags.pop(topic_id, None)
        return PersistenceResult(success=True, message="Flag removed.")


def _graph_page(course, *, signed_in=False, focus=None):
    app = signed_in_app(PAGE_PATH) if signed_in else AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = course
    if focus is not None:
        app.session_state[f"graph_pending_focus_{course.course_id}"] = focus
    return app.run()


def _markdown(app):
    return [item.value for item in app.markdown]


def _captions(app):
    return [item.value for item in app.caption]


def _radar_buttons(app):
    return [
        button for button in app.button
        if button.key and button.key.startswith("radar_flag_")
    ]


def test_radar_panel_lists_flagged_topics_most_flagged_first(monkeypatch):
    radar = RadarFake(
        monkeypatch,
        [
            _topic("calc_limits", real=2, display=None),
            _topic("calc_derivative_applications", real=5),
            _topic("calc_derivatives", real=8),
        ],
        ranked=["calc_derivatives", "calc_derivative_applications", "calc_limits"],
    )

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert "**Learning Radar**" in _markdown(app)
    assert (
        "1. **Derivatives** — 8 students are stuck here\n"
        "2. **Applications of Derivatives** — 5 students are stuck here\n"
        "3. **Limits** — Some students flagged this"
    ) in _markdown(app)
    assert "No topics have been flagged yet." not in _captions(app)
    assert [limit for _, limit in radar.calls["top_hard_topics"]] == [3]
    assert radar.calls["radar_enabled"][0] == CALCULUS_ID


def test_radar_panel_says_when_nothing_is_flagged(monkeypatch):
    RadarFake(monkeypatch, [])

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert "No topics have been flagged yet." in _captions(app)
    assert not any(value.startswith("1. ") for value in _markdown(app))


def test_knowledge_map_badges_flagged_topics(monkeypatch):
    RadarFake(
        monkeypatch,
        [
            _topic("calc_derivatives", real=3, sample=5),
            _topic("calc_limits", real=1, display=None),
        ],
    )
    rendered = []
    monkeypatch.setattr(
        knowledge_graph,
        "agraph",
        lambda nodes, edges, config, node_scale: rendered.append(nodes) or None,
    )

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert {node.id: node.label for node in rendered[-1]} == {
        "calc_limits": "Limits\n🔥 flagged",
        "calc_derivatives": "Derivatives\n🔥 8 stuck",
        "calc_derivative_applications": "Applications of Derivatives",
    }


def test_non_demo_course_shows_no_radar_ui_and_fetches_nothing(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("topic-1", real=9)], enabled=False)
    rendered = []
    monkeypatch.setattr(
        knowledge_graph,
        "agraph",
        lambda nodes, edges, config, node_scale: rendered.append(nodes) or None,
    )

    app = _graph_page(_other_course(), signed_in=True, focus="topic-1")

    assert not app.exception
    assert "Limits summary." in _markdown(app)
    assert radar.calls["radar_enabled"] == ["course-1"]
    assert all(
        calls == [] for name, calls in radar.calls.items() if name != "radar_enabled"
    )
    assert not any("Learning Radar" in value for value in _markdown(app))
    assert not any(
        "stuck" in value or "flagged" in value for value in _markdown(app)
    )
    assert not any(
        value in {
            "Includes sample data",
            "Live flags are unavailable right now.",
            "No topics have been flagged yet.",
        }
        for value in _captions(app)
    )
    assert _radar_buttons(app) == []
    assert "learning_radar_cache_course-1" not in app.session_state
    assert [node.label for node in rendered[-1]] == ["Limits", "Series"]


@pytest.mark.parametrize("live", [True, False])
def test_radar_panel_reports_when_live_flags_are_unavailable(monkeypatch, live):
    RadarFake(monkeypatch, [_topic("calc_derivatives", sample=8)], live=live)

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert ("Live flags are unavailable right now." in _captions(app)) is (not live)


@pytest.mark.parametrize("has_sample", [True, False])
def test_radar_panel_marks_sample_data(monkeypatch, has_sample):
    RadarFake(
        monkeypatch, [_topic("calc_derivatives", real=4)], has_sample=has_sample
    )

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert _captions(app).count("Includes sample data") == (1 if has_sample else 0)


@pytest.mark.parametrize(
    ("focus", "sample_captions"),
    [("calc_derivatives", 2), ("calc_limits", 1)],
)
def test_topic_details_mark_sample_data_per_topic(monkeypatch, focus, sample_captions):
    RadarFake(
        monkeypatch,
        [
            _topic("calc_derivatives", real=3, sample=5),
            _topic("calc_limits", real=4, sample=0),
        ],
        has_sample=True,
    )

    app = _graph_page(_calculus_course(), focus=focus)

    assert not app.exception
    # One caption from the panel, plus one when the selected topic has samples.
    assert _captions(app).count("Includes sample data") == sample_captions


@pytest.mark.parametrize(
    ("topics", "count_line"),
    [
        ([_topic("calc_derivatives", real=8)], "8 students are stuck here"),
        ([_topic("calc_derivatives", sample=1)], "1 student is stuck here"),
        ([_topic("calc_limits", real=6)], "No one has flagged this topic yet."),
    ],
)
def test_topic_details_show_radar_count(monkeypatch, topics, count_line):
    RadarFake(monkeypatch, topics)

    app = _graph_page(_calculus_course(), focus="calc_derivatives")

    assert not app.exception
    assert count_line in _markdown(app)


def test_hidden_count_shows_some_students_flagged_this(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_limits", real=2, display=None)])

    app = _graph_page(_calculus_course(), focus="calc_limits")

    assert not app.exception
    assert "Some students flagged this" in _markdown(app)
    assert "1. **Limits** — Some students flagged this" in _markdown(app)
    assert not any("2 student" in value for value in _markdown(app))


def test_signed_in_user_can_flag_topic_and_sees_new_count(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")

    assert not app.exception
    button = app.button(key=f"radar_flag_{CALCULUS_ID}_calc_derivatives")
    assert button.label == "I'm stuck here"
    assert "4 students are stuck here" in _markdown(app)
    assert radar.calls["get_user_flags"] == [(TEST_USER.user_id, CALCULUS_ID)]

    button.click().run()

    assert not app.exception
    assert radar.calls["set_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert radar.calls["clear_flag"] == []
    assert len(radar.calls["get_course_radar"]) == 2
    assert len(radar.calls["get_user_flags"]) == 2
    assert "5 students are stuck here" in _markdown(app)
    assert app.button(
        key=f"radar_flag_{CALCULUS_ID}_calc_derivatives"
    ).label == "Not stuck anymore"
    assert app.warning == []


def test_flagged_topic_offers_not_stuck_anymore(monkeypatch):
    radar = RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        user_flags={"calc_derivatives": None},
    )

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")

    assert not app.exception
    button = app.button(key=f"radar_flag_{CALCULUS_ID}_calc_derivatives")
    assert button.label == "Not stuck anymore"

    button.click().run()

    assert not app.exception
    assert radar.calls["clear_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert radar.calls["set_flag"] == []
    assert len(radar.calls["get_course_radar"]) == 2
    assert "3 students are stuck here" in _markdown(app)
    assert app.button(
        key=f"radar_flag_{CALCULUS_ID}_calc_derivatives"
    ).label == "I'm stuck here"


def test_failed_flag_shows_message_and_does_not_raise(monkeypatch):
    message = "Live flags are unavailable right now. Please try again later."
    radar = RadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        write_result=PersistenceResult(success=False, message=message),
    )

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")
    app.button(key=f"radar_flag_{CALCULUS_ID}_calc_derivatives").click().run()

    assert not app.exception
    assert radar.calls["set_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert [item.value for item in app.warning] == [message]
    assert len(radar.calls["get_course_radar"]) == 1
    assert "4 students are stuck here" in _markdown(app)
    assert app.button(
        key=f"radar_flag_{CALCULUS_ID}_calc_derivatives"
    ).label == "I'm stuck here"


def test_no_flag_button_without_signed_in_user(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), focus="calc_derivatives")

    assert not app.exception
    assert "4 students are stuck here" in _markdown(app)
    assert _radar_buttons(app) == []
    assert radar.calls["get_user_flags"] == []


def test_radar_is_reused_for_fifteen_seconds(monkeypatch):
    radar = RadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")
    app.run()
    app.button(key=f"graph_zoom_in_{CALCULUS_ID}_mock").click().run()

    assert not app.exception
    assert len(radar.calls["get_course_radar"]) == 1
    assert len(radar.calls["get_user_flags"]) == 1

    snapshot = dict(app.session_state[CACHE_KEY])
    snapshot["fetched_at"] -= 16
    app.session_state[CACHE_KEY] = snapshot
    app.run()

    assert not app.exception
    assert len(radar.calls["get_course_radar"]) == 2
    assert len(radar.calls["get_user_flags"]) == 2


# --- Learning Radar: reasons, privacy, hints, Concept Lab ------------------

WORDING_HINT_TEXT = (
    "Turn on Accessibility in the sidebar for simpler wording and Chinese key terms."
)
LIMITS_HINT_TEXT = "Many students are stuck here. Reviewing Limits first may help."
REASON_DISPLAY_LABELS = [
    "No specific reason",
    "Concept unclear",
    "Calculation errors",
    "Can't understand the question",
    "Don't know where to start",
]
_NOT_PASSED = object()


class ReasonRadarFake(RadarFake):
    """RadarFake that also records the reason argument given to set_flag."""

    def __init__(self, *args, **kwargs):
        self.flag_reasons = []
        super().__init__(*args, **kwargs)

    def set_flag(self, user_id, course_id, topic_id, *args, **kwargs):
        self.flag_reasons.append(args[0] if args else kwargs.get("reason", _NOT_PASSED))
        return super().set_flag(user_id, course_id, topic_id, *args, **kwargs)


def _reason_topic(topic_id, *, real=0, sample=0, reasons=None, display="total"):
    return learning_radar.TopicRadar(
        topic_id=topic_id,
        real_count=real,
        sample_count=sample,
        reasons=dict(reasons or {}),
        display_count=real + sample if display == "total" else display,
    )


def _custom_course(course_id, topics, relationships=()):
    return StudyPackage(
        course_id=course_id,
        course_name="Custom Course",
        topics=[
            {"id": topic_id, "name": name, "summary": f"{name} summary."}
            for topic_id, name in topics
        ],
        relationships=[
            {"from_topic": source, "to_topic": target, "type": "prerequisite"}
            for source, target in relationships
        ],
        questions=[],
    )


def _econ_course():
    return StudyPackage.model_validate_json(
        (CALCULUS_DEMO_PATH.parent / "sample_course.json").read_text(encoding="utf-8")
    )


def _reason_picker(app, topic_id, course_id=CALCULUS_ID):
    return app.selectbox(key=f"radar_reason_{course_id}_{topic_id}")


def _reason_picker_keys(app):
    return [
        box.key for box in app.selectbox
        if box.key and box.key.startswith("radar_reason_")
    ]


def _flag_button(app, topic_id):
    return app.button(key=f"radar_flag_{CALCULUS_ID}_{topic_id}")


def _infos(app):
    return [item.value for item in app.info]


def _concept_lab_buttons(app):
    return [button for button in app.button if button.label == "Open Concept Lab"]


def _record_graph_nodes(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        knowledge_graph,
        "agraph",
        lambda nodes, edges, config, node_scale: rendered.append(nodes) or None,
    )
    return rendered


def test_reason_options_list_no_reason_first_then_every_code():
    assert knowledge_graph.RADAR_REASON_OPTIONS == (
        None, "concept", "calculation", "wording", "start",
    )
    assert [
        knowledge_graph.radar_reason_label(option)
        for option in knowledge_graph.RADAR_REASON_OPTIONS
    ] == REASON_DISPLAY_LABELS


@pytest.mark.parametrize(
    ("topic_radar", "breakdown"),
    [
        (
            _reason_topic("t", real=5, reasons={"calculation": 3, "concept": 2}),
            "Concept unclear 2 · Calculation errors 3",
        ),
        (
            _reason_topic("t", real=1, sample=6, reasons={"start": 1, "wording": 4}),
            "Can't understand the question 4 · Don't know where to start 1",
        ),
        (_reason_topic("t", real=5, reasons={}), None),
        (_reason_topic("t", real=2, reasons={"concept": 2}, display=None), None),
        (None, None),
    ],
)
def test_radar_reason_breakdown(topic_radar, breakdown):
    assert knowledge_graph.radar_reason_breakdown(topic_radar) == breakdown


@pytest.mark.parametrize(
    ("names", "joined"),
    [
        (["Limits"], "Limits"),
        (["Limits", "Series"], "Limits and Series"),
        (["Limits", "Series", "Sums"], "Limits, Series, and Sums"),
    ],
)
def test_join_names(names, joined):
    assert knowledge_graph.join_names(names) == joined


@pytest.mark.parametrize(
    ("topic_radar", "names", "hint"),
    [
        (_reason_topic("t", real=5), ["Limits"], LIMITS_HINT_TEXT),
        (
            _reason_topic("t", real=3, sample=6),
            ["Limits", "Series"],
            "Many students are stuck here. Reviewing Limits and Series first may help.",
        ),
        (_reason_topic("t", real=4), ["Limits"], None),
        (_reason_topic("t", real=2, display=None), ["Limits"], None),
        (_reason_topic("t", real=8), [], None),
        (None, ["Limits"], None),
    ],
)
def test_radar_prerequisite_hint(topic_radar, names, hint):
    assert knowledge_graph.radar_prerequisite_hint(topic_radar, names) == hint


@pytest.mark.parametrize(
    ("course_id", "topic_id", "available"),
    [
        (CALCULUS_ID, "calc_limits", True),
        (CALCULUS_ID, "calc_derivatives", True),
        (CALCULUS_ID, "calc_derivative_applications", False),
        ("econ101", "calc_limits", False),
        ("econ101", "supply_demand", False),
        ("course-1", "calc_derivatives", False),
    ],
)
def test_concept_lab_available_only_for_the_two_calculus_topics(
    course_id, topic_id, available
):
    assert knowledge_graph.concept_lab_available(course_id, topic_id) is available


@pytest.mark.parametrize("reason", ["concept", "calculation", "wording", "start"])
def test_chosen_reason_reaches_set_flag_and_is_shown_once_flagged(monkeypatch, reason):
    radar = ReasonRadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")

    assert not app.exception
    picker = _reason_picker(app, "calc_derivatives")
    assert picker.label == "Why are you stuck?"
    assert picker.options == REASON_DISPLAY_LABELS
    assert picker.value is None

    picker.set_value(reason).run()
    _flag_button(app, "calc_derivatives").click().run()

    assert not app.exception
    assert radar.flag_reasons == [reason]
    assert radar.calls["set_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert f"Your reason: {learning_radar.REASON_LABELS[reason]}" in _captions(app)
    assert _flag_button(app, "calc_derivatives").label == "Not stuck anymore"
    assert _reason_picker_keys(app) == []


@pytest.mark.parametrize("pick_another_first", [False, True])
def test_no_specific_reason_sends_none(monkeypatch, pick_another_first):
    radar = ReasonRadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")
    if pick_another_first:
        _reason_picker(app, "calc_derivatives").set_value("concept").run()
        _reason_picker(app, "calc_derivatives").set_value(None).run()
    _flag_button(app, "calc_derivatives").click().run()

    assert not app.exception
    assert radar.flag_reasons == [None]
    assert radar.user_flags == {"calc_derivatives": None}
    assert "Your reason: No specific reason" in _captions(app)


@pytest.mark.parametrize(
    ("saved", "label"),
    [("calculation", "Calculation errors"), (None, "No specific reason")],
)
def test_saved_reason_is_shown_and_changed_by_flagging_again(monkeypatch, saved, label):
    radar = ReasonRadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        user_flags={"calc_derivatives": saved},
    )

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")

    assert not app.exception
    assert f"Your reason: {label}" in _captions(app)
    assert _flag_button(app, "calc_derivatives").label == "Not stuck anymore"
    assert _reason_picker_keys(app) == []

    # Changing the reason: remove the flag, then flag again with a new one.
    _flag_button(app, "calc_derivatives").click().run()

    assert not app.exception
    assert radar.calls["clear_flag"] == [
        (TEST_USER.user_id, CALCULUS_ID, "calc_derivatives")
    ]
    assert not any(value.startswith("Your reason:") for value in _captions(app))
    assert _reason_picker(app, "calc_derivatives").value is None

    _reason_picker(app, "calc_derivatives").set_value("start").run()
    _flag_button(app, "calc_derivatives").click().run()

    assert not app.exception
    assert radar.flag_reasons == ["start"]
    assert "Your reason: Don't know where to start" in _captions(app)
    assert f"Your reason: {label}" not in _captions(app)


@pytest.mark.parametrize(
    ("picked", "shown"),
    [
        ("wording", True),
        ("concept", False),
        ("calculation", False),
        ("start", False),
        (None, False),
    ],
)
def test_accessibility_pointer_follows_picked_reason(monkeypatch, picked, shown):
    ReasonRadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")
    assert WORDING_HINT_TEXT not in _infos(app)

    _reason_picker(app, "calc_derivatives").set_value(picked).run()

    assert not app.exception
    assert _infos(app).count(WORDING_HINT_TEXT) == (1 if shown else 0)


def test_accessibility_pointer_disappears_when_another_reason_is_picked(monkeypatch):
    ReasonRadarFake(monkeypatch, [_topic("calc_derivatives", real=4)])

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")
    _reason_picker(app, "calc_derivatives").set_value("wording").run()
    assert WORDING_HINT_TEXT in _infos(app)

    _reason_picker(app, "calc_derivatives").set_value("concept").run()

    assert not app.exception
    assert WORDING_HINT_TEXT not in _infos(app)


@pytest.mark.parametrize(
    ("saved", "shown"),
    [("wording", True), ("concept", False), (None, False)],
)
def test_accessibility_pointer_follows_saved_reason(monkeypatch, saved, shown):
    ReasonRadarFake(
        monkeypatch,
        [_topic("calc_derivatives", real=4)],
        user_flags={"calc_derivatives": saved},
    )

    app = _graph_page(_calculus_course(), signed_in=True, focus="calc_derivatives")

    assert not app.exception
    assert _flag_button(app, "calc_derivatives").label == "Not stuck anymore"
    assert _infos(app).count(WORDING_HINT_TEXT) == (1 if shown else 0)


def test_signed_out_user_sees_no_reason_controls(monkeypatch):
    radar = ReasonRadarFake(
        monkeypatch,
        [_reason_topic("calc_derivatives", real=4, reasons={"wording": 4})],
    )

    app = _graph_page(_calculus_course(), focus="calc_derivatives")

    assert not app.exception
    assert "4 students are stuck here" in _markdown(app)
    assert _reason_picker_keys(app) == []
    assert _radar_buttons(app) == []
    assert not any(value.startswith("Your reason:") for value in _captions(app))
    assert WORDING_HINT_TEXT not in _infos(app)
    assert radar.calls["get_user_flags"] == []
    assert radar.flag_reasons == []


def test_radar_panel_shows_reason_breakdown_with_labels(monkeypatch):
    RadarFake(
        monkeypatch,
        [
            _reason_topic(
                "calc_derivatives",
                real=3,
                sample=5,
                reasons={"calculation": 3, "concept": 2},
            ),
            _reason_topic("calc_limits", real=4, reasons={}),
            _reason_topic(
                "calc_derivative_applications", real=3, reasons={"wording": 1}
            ),
        ],
        ranked=["calc_derivatives", "calc_limits", "calc_derivative_applications"],
    )

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert (
        "1. **Derivatives** — 8 students are stuck here\n"
        "   - Concept unclear 2 · Calculation errors 3\n"
        "2. **Limits** — 4 students are stuck here\n"
        "3. **Applications of Derivatives** — 3 students are stuck here\n"
        "   - Can't understand the question 1"
    ) in _markdown(app)


def test_radar_panel_shows_no_breakdown_without_reasons(monkeypatch):
    RadarFake(monkeypatch, [_reason_topic("calc_derivatives", real=8, reasons={})])

    app = _graph_page(_calculus_course())

    assert not app.exception
    assert "1. **Derivatives** — 8 students are stuck here" in _markdown(app)
    assert not any(
        label in value
        for value in _markdown(app)
        for label in learning_radar.REASON_LABELS.values()
    )


def _threshold_topic(real):
    # display_count comes from the backend's own rule, so this checks the page
    # against the real threshold (MIN_VISIBLE_COUNT) rather than a copy of it.
    return learning_radar.TopicRadar(
        topic_id="calc_derivatives",
        real_count=real,
        sample_count=0,
        reasons={"concept": 1, "start": real - 1},
        display_count=learning_radar._display_count(real, 0),
    )


def test_hidden_count_shows_no_number_and_no_breakdown_anywhere(monkeypatch):
    topic = _threshold_topic(2)
    assert topic.display_count is None
    RadarFake(monkeypatch, [topic])
    rendered = _record_graph_nodes(monkeypatch)

    app = _graph_page(_calculus_course(), focus="calc_derivatives")

    assert not app.exception
    # Topic details: no count.
    assert "Some students flagged this" in _markdown(app)
    assert not any("student is" in value or "students are" in value for value in _markdown(app))
    # Node badge: no number.
    badge_label = {node.id: node.label for node in rendered[-1]}["calc_derivatives"]
    assert badge_label == "Derivatives\n🔥 flagged"
    assert not any(char.isdigit() for char in badge_label)
    # Panel: no number and no reason breakdown.
    assert "1. **Derivatives** — Some students flagged this" in _markdown(app)
    shown_text = _markdown(app) + _captions(app) + _infos(app)
    assert not any(
        label in value
        for value in shown_text
        for label in learning_radar.REASON_LABELS.values()
    )
    # No prerequisite hint either, even though Derivatives has one.
    assert not any(value.startswith("Many students") for value in _infos(app))


def test_exactly_three_real_flags_show_numbers_and_breakdown(monkeypatch):
    topic = _threshold_topic(learning_radar.MIN_VISIBLE_COUNT)
    assert topic.display_count == 3
    RadarFake(monkeypatch, [topic])
    rendered = _record_graph_nodes(monkeypatch)

    app = _graph_page(_calculus_course(), focus="calc_derivatives")

    assert not app.exception
    assert "3 students are stuck here" in _markdown(app)
    assert {node.id: node.label for node in rendered[-1]}["calc_derivatives"] == (
        "Derivatives\n🔥 3 stuck"
    )
    assert (
        "1. **Derivatives** — 3 students are stuck here\n"
        "   - Concept unclear 1 · Don't know where to start 2"
    ) in _markdown(app)
    assert "Some students flagged this" not in _markdown(app)


@pytest.mark.parametrize(
    ("topic", "shown"),
    [
        (_topic("calc_derivatives", real=5), True),
        (_topic("calc_derivatives", real=3, sample=5), True),
        (_topic("calc_derivatives", real=4), False),
        (_topic("calc_derivatives", real=2, display=None), False),
    ],
)
def test_prerequisite_hint_needs_five_visible_flags(monkeypatch, topic, shown):
    RadarFake(monkeypatch, [topic])

    app = _graph_page(_calculus_course(), focus="calc_derivatives")

    assert not app.exception
    assert _infos(app).count(LIMITS_HINT_TEXT) == (1 if shown else 0)
    assert not any(
        value.startswith("Many students") and value != LIMITS_HINT_TEXT
        for value in _infos(app)
    )


def test_prerequisite_hint_needs_a_prerequisite(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_limits", real=9)])

    app = _graph_page(_calculus_course(), focus="calc_limits")

    assert not app.exception
    assert "9 students are stuck here" in _markdown(app)
    assert not any(value.startswith("Many students") for value in _infos(app))


def test_prerequisite_hint_names_every_prerequisite(monkeypatch):
    course = _custom_course(
        "course-1",
        [("topic-1", "Limits"), ("topic-2", "Series"), ("topic-3", "Integrals")],
        relationships=[("topic-1", "topic-3"), ("topic-2", "topic-3")],
    )
    RadarFake(monkeypatch, [_topic("topic-3", real=6)])

    app = _graph_page(course, focus="topic-3")

    assert not app.exception
    assert (
        "Many students are stuck here. Reviewing Limits and Series first may help."
        in _infos(app)
    )


@pytest.mark.parametrize("signed_in", [False, True])
@pytest.mark.parametrize("topic_id", ["calc_limits", "calc_derivatives"])
def test_concept_lab_button_switches_to_concept_lab(monkeypatch, topic_id, signed_in):
    import streamlit as st

    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    RadarFake(monkeypatch, [_topic(topic_id, real=4)])

    app = _graph_page(_calculus_course(), signed_in=signed_in, focus=topic_id)

    assert not app.exception
    button = app.button(key=f"radar_concept_lab_{CALCULUS_ID}_{topic_id}")
    assert button.label == "Open Concept Lab"
    assert len(_concept_lab_buttons(app)) == 1
    assert destinations == []

    button.click().run()

    assert not app.exception
    assert destinations == ["pages/6_Concept_Lab.py"]


@pytest.mark.parametrize(
    ("course_factory", "focus"),
    [
        (_calculus_course, "calc_derivative_applications"),
        (_econ_course, "supply_demand"),
        (
            lambda: _custom_course(
                "course-1", [("calc_limits", "Limits"), ("calc_derivatives", "Derivatives")]
            ),
            "calc_limits",
        ),
    ],
)
def test_no_concept_lab_button_for_other_topics_or_courses(
    monkeypatch, course_factory, focus
):
    RadarFake(monkeypatch, [_topic(focus, real=4)])

    app = _graph_page(course_factory(), signed_in=True, focus=focus)

    assert not app.exception
    assert "4 students are stuck here" in _markdown(app)
    assert _concept_lab_buttons(app) == []


def test_registered_app_opens_concept_lab_from_knowledge_map(monkeypatch):
    RadarFake(monkeypatch, [_topic("calc_limits", real=4)])
    app = signed_in_app(PAGE_PATH.parents[1] / "app.py").run()
    assert not app.exception
    app.session_state["current_course"] = _calculus_course()
    app.session_state[f"graph_pending_focus_{CALCULUS_ID}"] = "calc_limits"

    app.switch_page("pages/4_Knowledge_Graph.py").run()

    assert not app.exception
    assert app.title[0].value == "Knowledge Map"
    app.button(key=f"radar_concept_lab_{CALCULUS_ID}_calc_limits").click().run()

    assert not app.exception
    assert app.title[0].value == "Concept Lab"


def test_non_demo_course_shows_no_reason_hint_or_concept_lab_controls(monkeypatch):
    radar = ReasonRadarFake(
        monkeypatch,
        [_reason_topic("calc_derivatives", real=9, reasons={"wording": 9})],
        enabled=False,
        user_flags={"calc_derivatives": "wording"},
    )
    course = _custom_course(
        "course-1",
        [("calc_limits", "Limits"), ("calc_derivatives", "Derivatives")],
        relationships=[("calc_limits", "calc_derivatives")],
    )

    app = _graph_page(course, signed_in=True, focus="calc_derivatives")

    assert not app.exception
    assert "Derivatives summary." in _markdown(app)
    assert radar.calls["radar_enabled"] == ["course-1"]
    assert all(
        calls == [] for name, calls in radar.calls.items() if name != "radar_enabled"
    )
    assert _reason_picker_keys(app) == []
    assert _concept_lab_buttons(app) == []
    assert not any(value.startswith("Your reason:") for value in _captions(app))
    assert _infos(app) == []
