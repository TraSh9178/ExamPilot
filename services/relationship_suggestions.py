"""Hold Gemini's suggested topic connections until the user applies them.

Suggestions live only in the browser session. Applying them validates the
result as a full StudyPackage, so stale suggestions that name topics no longer
in the course are rejected instead of saved.
"""

from models.schemas import StudyPackage


def suggestions_key(course_id: str) -> str:
    return f"relationship_suggestions_{course_id}"


def notice_key(course_id: str) -> str:
    return f"relationship_notice_{course_id}"


def describe_suggestions(course: StudyPackage, suggestions: list[dict]) -> list[str]:
    """Return one human-readable label per suggestion, using topic names."""
    names = {topic.id: topic.name for topic in course.topics}
    labels = []
    for suggestion in suggestions:
        source = suggestion.get("from_topic", "?")
        target = suggestion.get("to_topic", "?")
        labels.append(f"{names.get(source, source)} ↔ {names.get(target, target)}")
    return labels


def apply_suggested_relationships(
    course: StudyPackage, suggestions: list[dict]
) -> StudyPackage:
    """Return a copy of the course whose connections are exactly the suggestions.

    Raises pydantic.ValidationError (a ValueError) when a suggestion refers to
    a topic that is not in the course.
    """
    data = course.model_dump(mode="json")
    data["relationships"] = [dict(suggestion) for suggestion in suggestions]
    return StudyPackage.model_validate(data)
