"""Hold Claude's suggested topic connections until the user applies them.

Suggestions live only in the browser session. Applying them validates the
result as a full StudyPackage, so stale suggestions that name topics no longer
in the course are rejected instead of saved.
"""

from models.schemas import StudyPackage
from services.i18n import tr


def suggestions_key(course_id: str) -> str:
    return f"relationship_suggestions_{course_id}"


def notice_key(course_id: str) -> str:
    return f"relationship_notice_{course_id}"


def describe_suggestions(course: StudyPackage, suggestions: list[dict]) -> list[str]:
    """Return one human-readable label per suggestion, using topic names.

    An unknown topic shows as the plain word "Topic", never its internal ID.
    """
    names = {topic.id: topic.name for topic in course.topics}
    fallback = tr("Topic")
    labels = []
    for suggestion in suggestions:
        source = names.get(suggestion.get("from_topic"), fallback)
        target = names.get(suggestion.get("to_topic"), fallback)
        labels.append(f"{source} ↔ {target}")
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
