import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

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


def convert_graph_data(graph: dict) -> tuple[list[Node], list[Edge]]:
    """Convert build_mastery_graph output for streamlit-agraph.

    A prerequisite edge from A to B means A must be learned before B.
    """
    nodes = [
        Node(
            id=node["id"],
            label=node["label"],
            color=node["color"],
            font={
                "color": "#F8FAFC",
                "strokeWidth": 3,
                "strokeColor": "#0F172A",
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
                font={"size": 12},
                **_RELATIONSHIP_STYLES[relationship_type],
            )
        )

    return nodes, edges


def render_knowledge_graph(
    package: StudyPackage,
    stats: list[TopicStats],
    mode: str,
) -> str | None:
    graph = build_mastery_graph(package, stats, mode)
    nodes, edges = convert_graph_data(graph)
    config = Config(
        height=560,
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

    return agraph(nodes, edges, config)


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


def render_topic_details(details: dict | None) -> None:
    if details is None:
        st.info("Click a knowledge point to see its details.")
        return

    st.subheader(details["name"])
    st.write(details["summary"])

    source_pages = details["source_pages"]
    if source_pages:
        st.caption(f"Source pages: {', '.join(map(str, source_pages))}")
    else:
        st.caption("Source pages not provided")

    st.metric("Mastery status", details["status"])
