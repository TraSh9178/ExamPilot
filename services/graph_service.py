from models.schemas import TopicStats
from services.mastery_engine import get_mastery_status

from models.schemas import Topic, Relationship, StudyPackage


def build_nodes(topics: list[Topic]) -> list[dict]:
    nodes = []

    for topic in topics:
        node = {
            "id": topic.id,
            "label": topic.name,
        }

        nodes.append(node)

    return nodes

def build_edges(relationships: list[Relationship]) -> list[dict]:
    edges = []

    for relationship in relationships:
        edge = {
            "source": relationship.from_topic,
            "target": relationship.to_topic,
            "type": relationship.type,
        }

        edges.append(edge)

    return edges

def build_graph(package: StudyPackage) -> dict:
    nodes = build_nodes(package.topics)
    edges = build_edges(package.relationships)

    return {
        "nodes": nodes,
        "edges": edges,
    }

MASTERY_COLORS = {
    "unattempted": "#94A3B8",
    "insufficient_evidence": "#A78BFA",
    "weak": "#EF4444",
    "developing": "#F59E0B",
    "mastered": "#22C55E",
}


def get_node_color(status: str) -> str:
    if status not in MASTERY_COLORS:
        raise ValueError(f"Unknown mastery status: {status}")

    return MASTERY_COLORS[status]

def apply_mastery_to_nodes(
    nodes: list[dict],
    status_by_topic: dict[str, str],
) -> list[dict]:
    updated_nodes = []

    for node in nodes:
        topic_id = node["id"]

        status = status_by_topic.get(
            topic_id, "unattempted"
        )

        updated_node = node.copy()
        updated_node["status"] = status
        updated_node["color"] = get_node_color(status)

        updated_nodes.append(updated_node)

    return updated_nodes

def get_status_by_topic(
    stats: list[TopicStats],
    mode: str,
) -> dict[str, str]:
    if mode not in ("mock", "topic"):
        raise ValueError(f"Invalid mode: {mode}")

    status_by_topic = {}

    for item in stats:
        if item.mode != mode:
            continue

        if item.topic_id in status_by_topic:
            raise ValueError(f"Duplicate topic stats: {item.topic_id}")

        status_by_topic[item.topic_id] = get_mastery_status(item)

    return status_by_topic

def build_mastery_graph(
    package: StudyPackage,
    stats: list[TopicStats],
    mode: str,
) -> dict:
    graph = build_graph(package)

    status_by_topic = get_status_by_topic(stats, mode)

    graph["nodes"] = apply_mastery_to_nodes(
        graph["nodes"],
        status_by_topic,
    )

    return graph