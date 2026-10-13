"""Read-only topic exploration; never invent links or change course data."""
from models.schemas import StudyPackage


def related_topics(package: StudyPackage, topic_id: str) -> dict[str, list[str]]:
    if topic_id not in {topic.id for topic in package.topics}:
        raise ValueError("Unknown topic.")
    result = {"prerequisites": [], "next_topics": [], "related": []}
    for edge in package.relationships:
        if edge.to_topic == topic_id and edge.type == "prerequisite":
            result["prerequisites"].append(edge.from_topic)
        elif edge.from_topic == topic_id and edge.type == "prerequisite":
            result["next_topics"].append(edge.to_topic)
        elif edge.type == "related":
            if edge.from_topic == topic_id:
                result["related"].append(edge.to_topic)
            elif edge.to_topic == topic_id:
                result["related"].append(edge.from_topic)
    return {key: list(dict.fromkeys(values)) for key, values in result.items()}


def local_graph(package: StudyPackage, topic_id: str, depth: int = 1) -> StudyPackage:
    if depth not in (1, 2, 3):
        raise ValueError("Depth must be 1, 2 or 3.")
    known = {topic.id for topic in package.topics}
    if topic_id not in known:
        raise ValueError("Unknown topic.")
    visible = {topic_id}
    frontier = {topic_id}
    for _ in range(depth):
        neighbors = set()
        for edge in package.relationships:
            if edge.from_topic in frontier:
                neighbors.add(edge.to_topic)
            if edge.to_topic in frontier:
                neighbors.add(edge.from_topic)
        frontier = (neighbors & known) - visible
        visible.update(frontier)
    return package.model_copy(update={
        "topics": [topic for topic in package.topics if topic.id in visible],
        "relationships": [edge for edge in package.relationships if edge.from_topic in visible and edge.to_topic in visible],
        "questions": [question for question in package.questions if question.topic_id in visible],
    })
