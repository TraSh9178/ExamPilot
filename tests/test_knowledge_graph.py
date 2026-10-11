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
