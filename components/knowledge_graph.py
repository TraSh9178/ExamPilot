import json
import time
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from streamlit_agraph import Config, Edge, Node

from models.schemas import StudyPackage, TopicStats
from services import learning_radar
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


def _badged_label(label: str, badge: str | None) -> str:
    # vis-network renders "\n" in a label as a line break.
    return f"{label}\n{badge}" if badge else label


def convert_graph_data(
    graph: dict,
    node_badges: dict[str, str] | None = None,
) -> tuple[list[Node], list[Edge]]:
    """Convert build_mastery_graph output for streamlit-agraph.

    A prerequisite edge from A to B means A must be learned before B.
    ``node_badges`` maps a topic ID to a short badge shown under its label.
    """
    badges = node_badges or {}
    nodes = [
        Node(
            id=node["id"],
            label=_badged_label(node["label"], badges.get(node["id"])),
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
    focus_topic_id: str | None = None,
    node_badges: dict[str, str] | None = None,
) -> str | None:
    graph = build_mastery_graph(package, stats, mode)
    if node_badges:
        nodes, edges = convert_graph_data(graph, node_badges=node_badges)
    else:
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
    config.focusTopic = focus_topic_id
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

    with st.container(key="knowledge_topic_summary"):
        st.subheader("Summary")
        st.write(details["summary"])

    source_pages = details["source_pages"]
    if source_pages:
        st.caption(f"Source pages: {', '.join(map(str, source_pages))}")
    else:
        st.caption("Source pages not provided")

    st.divider()
    st.markdown("**Your Progress**")
    if topic_stats is not None:
        with st.container(key="knowledge_topic_stats"):
            stats_columns = st.columns(2)
            stats_columns[0].metric("Answers", topic_stats.attempted)
            st.caption(f"Different questions: {topic_stats.unique_attempted if topic_stats.unique_attempted is not None else topic_stats.attempted}")
            stats_columns[1].metric(
                "Accuracy",
                "—" if topic_stats.accuracy is None else f"{topic_stats.accuracy:.2f}%",
            )
    status = details["status"]
    st.badge(_MASTERY_LABELS[status], color=_MASTERY_BADGE_COLORS[status])


RADAR_CACHE_SECONDS = 15


def radar_cache_key(course_id: str) -> str:
    return f"learning_radar_cache_{course_id}"


def load_course_radar(
    session_state: MutableMapping[str, Any],
    course_id: str,
    user_id: str | None,
) -> tuple[learning_radar.CourseRadar, dict[str, str | None]]:
    """Return the course radar and this user's flags, reused for a short time.

    Pages rerun often (zooming, selecting topics, switching pages), so the
    result is kept in the session for RADAR_CACHE_SECONDS. Every page that
    shows the radar shares this copy.
    """
    key = radar_cache_key(course_id)
    snapshot = session_state.get(key)
    now = time.monotonic()
    fresh = (
        isinstance(snapshot, dict)
        and snapshot.get("user_id") == user_id
        and isinstance(snapshot.get("fetched_at"), (int, float))
        and 0 <= now - snapshot["fetched_at"] < RADAR_CACHE_SECONDS
    )
    if not fresh:
        snapshot = {
            "fetched_at": now,
            "user_id": user_id,
            "radar": learning_radar.get_course_radar(course_id),
            "user_flags": (
                learning_radar.get_user_flags(user_id, course_id)
                if user_id is not None
                else {}
            ),
        }
        session_state[key] = snapshot
    return snapshot["radar"], snapshot["user_flags"]


def forget_course_radar(
    session_state: MutableMapping[str, Any], course_id: str
) -> None:
    """Drop the shared copy so the next rerun reads fresh counts."""
    session_state.pop(radar_cache_key(course_id), None)


def _has_flags(topic_radar: learning_radar.TopicRadar | None) -> bool:
    return (
        topic_radar is not None
        and topic_radar.real_count + topic_radar.sample_count > 0
    )


def radar_badge(topic_radar: learning_radar.TopicRadar) -> str:
    """Short map badge; a hidden count (privacy threshold) shows no number."""
    if topic_radar.display_count is None:
        return "🔥 flagged"
    return f"🔥 {topic_radar.display_count} stuck"


def radar_node_badges(radar: learning_radar.CourseRadar) -> dict[str, str]:
    return {
        topic_id: radar_badge(topic_radar)
        for topic_id, topic_radar in radar.topics.items()
        if _has_flags(topic_radar)
    }


def radar_count_text(topic_radar: learning_radar.TopicRadar | None) -> str:
    if not _has_flags(topic_radar):
        return "No one has flagged this topic yet."
    count = topic_radar.display_count
    if count is None:
        return "Some students flagged this"
    if count == 1:
        return "1 student is stuck here"
    return f"{count} students are stuck here"


NO_REASON_LABEL = "No specific reason"
# Choices offered before flagging: no reason (stored as None), then each code.
RADAR_REASON_OPTIONS: tuple[str | None, ...] = (
    None,
    *learning_radar.REASON_LABELS,
)
WORDING_HINT = (
    "Turn on Accessibility in the sidebar for simpler wording and "
    "Chinese key terms."
)
PREREQUISITE_HINT_MIN_COUNT = 5
# Topics that pages/6_Concept_Lab.py has an experiment for, by course.
CONCEPT_LAB_TOPICS = {
    "calculus-i-demo": frozenset({"calc_limits", "calc_derivatives"}),
}


def radar_reason_label(reason: str | None) -> str:
    """Readable label for a stored reason code; None means no reason."""
    if reason is None:
        return NO_REASON_LABEL
    return learning_radar.REASON_LABELS.get(reason, NO_REASON_LABEL)


def radar_reason_breakdown(
    topic_radar: learning_radar.TopicRadar | None,
) -> str | None:
    """Reason counts such as "Concept unclear 2 · Calculation errors 3".

    Returns None when there are no reasons, and also when the topic's count
    is hidden by the privacy threshold: the backend does not threshold
    ``reasons``, so the numbers must not be shown either.
    """
    if not _has_flags(topic_radar) or topic_radar.display_count is None:
        return None
    parts = [
        f"{label} {topic_radar.reasons[code]}"
        for code, label in learning_radar.REASON_LABELS.items()
        if topic_radar.reasons.get(code, 0) > 0
    ]
    return " · ".join(parts) or None


def join_names(names: Sequence[str]) -> str:
    """Join names as English prose: "A", "A and B", "A, B, and C"."""
    names = list(names)
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def radar_prerequisite_hint(
    topic_radar: learning_radar.TopicRadar | None,
    prerequisite_names: Sequence[str],
) -> str | None:
    """Suggest reviewing prerequisites when many students are stuck here.

    Only a visible count can trigger the hint, so a hidden count (privacy
    threshold) never implies how many students flagged the topic.
    """
    if not prerequisite_names or topic_radar is None:
        return None
    count = topic_radar.display_count
    if count is None or count < PREREQUISITE_HINT_MIN_COUNT:
        return None
    return (
        "Many students are stuck here. "
        f"Reviewing {join_names(prerequisite_names)} first may help."
    )


def concept_lab_available(course_id: str, topic_id: str) -> bool:
    """True when the Concept Lab page has an experiment for this topic."""
    return topic_id in CONCEPT_LAB_TOPICS.get(course_id, frozenset())


def render_reason_hint(reason: str | None) -> None:
    """Point users who cannot understand the wording to Accessibility mode."""
    if reason == "wording":
        st.info(WORDING_HINT)


def render_saved_reason(reason: str | None) -> None:
    """Show the reason the user gave when flagging the selected topic."""
    st.caption(f"Your reason: {radar_reason_label(reason)}")
    render_reason_hint(reason)


def render_topic_radar(
    topic_radar: learning_radar.TopicRadar | None,
    prerequisite_names: Sequence[str] = (),
) -> None:
    """Show how many students are stuck on the selected topic."""
    st.markdown(radar_count_text(topic_radar))
    if topic_radar is not None and topic_radar.sample_count > 0:
        st.caption("Includes sample data")
    hint = radar_prerequisite_hint(topic_radar, prerequisite_names)
    if hint is not None:
        st.info(hint)


def render_radar_panel(
    radar: learning_radar.CourseRadar,
    ranked_topics: list[learning_radar.TopicRadar],
    topic_names: dict[str, str],
) -> None:
    """List the course's flagged topics in the order given (most flagged first)."""
    st.markdown("**Learning Radar**")
    st.caption("Topics where students marked \"I'm stuck here\", most flagged first.")
    flagged = [
        topic_radar
        for topic_radar in ranked_topics
        if _has_flags(topic_radar) and topic_radar.topic_id in topic_names
    ]
    if flagged:
        lines = []
        for index, topic_radar in enumerate(flagged, start=1):
            marker = f"{index}. "
            lines.append(
                f"{marker}**{topic_names[topic_radar.topic_id]}** — "
                f"{radar_count_text(topic_radar)}"
            )
            breakdown = radar_reason_breakdown(topic_radar)
            if breakdown is not None:
                # Indent to the item's content so it renders as a nested bullet.
                lines.append(f"{' ' * len(marker)}- {breakdown}")
        st.markdown("\n".join(lines))
    else:
        st.caption("No topics have been flagged yet.")
    if radar.has_sample:
        st.caption("Includes sample data")
    if not radar.live:
        st.caption("Live flags are unavailable right now.")
