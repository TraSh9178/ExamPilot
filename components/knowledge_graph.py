import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_agraph import Config, Edge, Node

from models.schemas import StudyPackage, TopicStats
from services.graph_service import build_mastery_graph


_RELATIONSHIP_STYLES = {
    "prerequisite": {
        "label": "Prerequisite",
        "color": "#2563EB",
        "dashes": True,
        "arrows": {"to": {"enabled": True}},
    },
    "related": {
        "label": "Related",
        "color": "#64748B",
        "arrows": {
            "from": {"enabled": False},
            "to": {"enabled": False},
        },
    },
}

_MASTERY_LABELS = {
    "unattempted": "Unattempted",
    "insufficient_evidence": "Insufficient evidence",
    "weak": "Weak",
    "developing": "Developing",
    "mastered": "Mastered",
}

_MASTERY_BADGE_COLORS = {
    "unattempted": "gray",
    "insufficient_evidence": "violet",
    "weak": "red",
    "developing": "orange",
    "mastered": "green",
}

MIN_NODE_SIZE = 36

_bounded_graph_component = components.declare_component(
    "exampilot_bounded_knowledge_graph",
    path=str(Path(__file__).with_name("bounded_graph_frontend")),
)


def agraph(nodes, edges, config, node_scale: float = 1.0):
    return _bounded_graph_component(
        payload={
            "graph": {
                "nodes": [node.to_dict() for node in nodes],
                "edges": [edge.to_dict() for edge in edges],
            },
            "config": config.to_dict(),
            "nodeScale": node_scale,
        },
        default=None,
        key=f"bounded_graph_{config.layout['randomSeed']}",
    )


def convert_graph_data(graph: dict) -> tuple[list[Node], list[Edge]]:
    """Convert build_mastery_graph output for streamlit-agraph.

    A prerequisite edge from A to B means A must be learned before B.
    """
    nodes = [
        Node(
            id=node["id"],
            label=node["label"],
            color=node["color"],
            size=MIN_NODE_SIZE,
            font={
                "color": "#102044",
                "size": 16,
                "face": "Arial",
                "strokeWidth": 4,
                "strokeColor": "#FFFFFF",
            },
        )
        for node in graph["nodes"]
    ]

    edges = []
    for edge in graph["edges"]:
        relationship_type = edge["type"]
        if relationship_type not in _RELATIONSHIP_STYLES:
            raise ValueError(
                f"Unknown relationship type: {relationship_type}"
            )

        edges.append(
            Edge(
                source=edge["source"],
                target=edge["target"],
                font={"size": 14},
                **_RELATIONSHIP_STYLES[relationship_type],
            )
        )

    return nodes, edges


def render_knowledge_graph(
    package: StudyPackage,
    stats: list[TopicStats],
    mode: str,
    view_reset: int = 0,
    node_scale: float = 1.0,
) -> str | None:
    graph = build_mastery_graph(package, stats, mode)
    nodes, edges = convert_graph_data(graph)
    config = Config(
        height=540,
        width=900,
        physics=True,
        hierarchical=False,
        groups={},
        interaction={
            "dragNodes": True,
            "zoomView": True,
            "dragView": True,
        },
    )
    config.width = "100%"
    config.layout["randomSeed"] = 42 + view_reset
    config.physics["forceAtlas2Based"] = {
        "gravitationalConstant": -50,
        "centralGravity": 0.015,
        "springLength": 160,
        "springConstant": 0.08,
        "damping": 0.4,
        "avoidOverlap": 0.8,
    }
    config.physics["solver"] = "forceAtlas2Based"
    config.physics["stabilization"].update(
        enabled=True,
        fit=True,
        iterations=1000,
    )

    return agraph(nodes, edges, config, node_scale)


def get_selected_topic_details(
    selected_node_id: str | None,
    package: StudyPackage,
    graph: dict,
) -> dict[str, str | list[int]] | None:
    if selected_node_id is None:
        return None

    topic = next(
        (topic for topic in package.topics if topic.id == selected_node_id),
        None,
    )
    node = next(
        (
            node
            for node in graph["nodes"]
            if node["id"] == selected_node_id
        ),
        None,
    )
    if topic is None or node is None:
        return None

    return {
        "id": topic.id,
        "name": topic.name,
        "summary": topic.summary,
        "source_pages": list(topic.source_pages),
        "status": node["status"],
        "color": node["color"],
    }


def render_topic_details(
    details: dict | None,
    topic_stats: TopicStats | None = None,
) -> None:
    if details is None:
        st.info("Click a knowledge point to see its details.")
        return

    with st.container(key="knowledge_topic_heading"):
        st.subheader(details["name"])
        status = details["status"]
        st.badge(
            _MASTERY_LABELS[status],
            color=_MASTERY_BADGE_COLORS[status],
        )

    if topic_stats is not None:
        with st.container(key="knowledge_topic_stats"):
            stats_columns = st.columns(2)
            stats_columns[0].metric("Answers", topic_stats.attempted)
            stats_columns[1].metric(
                "Accuracy",
                (
                    "—"
                    if topic_stats.accuracy is None
                    else f"{topic_stats.accuracy:.2f}%"
                ),
            )

    with st.container(border=True):
        st.subheader("Summary")
        st.write(details["summary"])

    source_pages = details["source_pages"]
    if source_pages:
        st.caption(f"Source pages: {', '.join(map(str, source_pages))}")
    else:
        st.caption("Source pages not provided")
