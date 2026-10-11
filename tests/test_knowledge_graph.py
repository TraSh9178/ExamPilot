import json

from streamlit_agraph import Edge, Node
import pytest
from unittest.mock import Mock

import components.knowledge_graph as knowledge_graph
from components.knowledge_graph import convert_graph_data
from models.schemas import StudyPackage


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
        (node.id, node.label, node.color, node.font)
        for node in nodes
    ] == [
        (
            "t1",
            "Topic 1",
            "#94A3B8",
            {
                "color": "#F8FAFC",
                "strokeWidth": 3,
                "strokeColor": "#0F172A",
            },
        ),
        (
            "t2",
            "Topic 2",
            "#A78BFA",
            {
                "color": "#F8FAFC",
                "strokeWidth": 3,
                "strokeColor": "#0F172A",
            },
        ),
        (
            "t3",
            "Topic 3",
            "#EF4444",
            {
                "color": "#F8FAFC",
                "strokeWidth": 3,
                "strokeColor": "#0F172A",
            },
        ),
        (
            "t4",
            "Topic 4",
            "#F59E0B",
            {
                "color": "#F8FAFC",
                "strokeWidth": 3,
                "strokeColor": "#0F172A",
            },
        ),
        (
            "t5",
            "Topic 5",
            "#22C55E",
            {
                "color": "#F8FAFC",
                "strokeWidth": 3,
                "strokeColor": "#0F172A",
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
    assert prerequisite.font == {"size": 12}
    assert (related.source, related.to) == ("a", "c")
    assert related.label == "Related"
    assert related.color == "#64748B"
    assert related.font == {"size": 12}
    assert related.arrows == {
        "from": {"enabled": False},
        "to": {"enabled": False},
    }


def test_convert_graph_data_handles_empty_graph():
    assert convert_graph_data({"nodes": [], "edges": []}) == ([], [])


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
    config = object()
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
        return config

    def render(nodes_arg, edges_arg, config_arg):
        agraph_calls.append((nodes_arg, edges_arg, config_arg))
        return selected_node_id

    monkeypatch.setattr(knowledge_graph, "build_mastery_graph", build)
    monkeypatch.setattr(knowledge_graph, "convert_graph_data", convert)
    monkeypatch.setattr(knowledge_graph, "Config", make_config)
    monkeypatch.setattr(knowledge_graph, "agraph", render)

    result = knowledge_graph.render_knowledge_graph(package, stats, "mock")

    assert result == selected_node_id
    assert build_calls == [(package, stats, "mock")]
    assert conversion_calls == [graph]
    assert config_calls == [
        {
            "height": 560,
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
    assert agraph_calls == [(nodes, edges, config)]


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

    def render(nodes, edges, config):
        render_calls.append((nodes, edges, config))
        return None

    monkeypatch.setattr(knowledge_graph, "agraph", render)

    assert knowledge_graph.render_knowledge_graph(package, [], "mock") is None

    assert len(render_calls) == 1
    nodes, edges, config = render_calls[0]
    assert len(nodes) == 3
    assert {node.id for node in nodes} == {
        "limits",
        "derivatives",
        "integrals",
    }
    assert edges == []

    serialized_config = json.loads(json.dumps(config.__dict__))
    assert serialized_config["groups"] == {}
    assert config.physics["enabled"] is True
    assert config.layout["hierarchical"]["enabled"] is False
    assert config.interaction == {
        "dragNodes": True,
        "zoomView": True,
        "dragView": True,
    }


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
    monkeypatch.setattr(knowledge_graph.st, "info", info)
    monkeypatch.setattr(knowledge_graph.st, "subheader", subheader)
    monkeypatch.setattr(knowledge_graph.st, "write", write)
    monkeypatch.setattr(knowledge_graph.st, "caption", caption)
    monkeypatch.setattr(knowledge_graph.st, "metric", metric)

    knowledge_graph.render_topic_details(
        {
            "name": "Topic 1",
            "summary": "A short summary.",
            "source_pages": [2, 5],
            "status": "developing",
            "color": "#F59E0B",
        }
    )

    subheader.assert_called_once_with("Topic 1")
    write.assert_called_once_with("A short summary.")
    caption.assert_called_once_with("Source pages: 2, 5")
    metric.assert_called_once_with("Mastery status", "developing")
    info.assert_not_called()


def test_render_topic_details_shows_missing_pages_message(monkeypatch):
    caption = Mock()
    monkeypatch.setattr(knowledge_graph.st, "caption", caption)
    monkeypatch.setattr(knowledge_graph.st, "subheader", Mock())
    monkeypatch.setattr(knowledge_graph.st, "write", Mock())
    monkeypatch.setattr(knowledge_graph.st, "metric", Mock())

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
    monkeypatch.setattr(knowledge_graph.st, "info", info)
    monkeypatch.setattr(knowledge_graph.st, "subheader", subheader)
    monkeypatch.setattr(knowledge_graph.st, "write", write)
    monkeypatch.setattr(knowledge_graph.st, "caption", caption)
    monkeypatch.setattr(knowledge_graph.st, "metric", metric)

    knowledge_graph.render_topic_details(None)

    info.assert_called_once_with(
        "Click a knowledge point to see its details."
    )
    subheader.assert_not_called()
    write.assert_not_called()
    caption.assert_not_called()
    metric.assert_not_called()
