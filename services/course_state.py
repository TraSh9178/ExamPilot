from collections.abc import MutableMapping
from typing import Any

from models.schemas import StudyPackage


def initialize_courses(
    session_state: MutableMapping[str, Any],
) -> None:
    """Initialize the course list, migrating a legacy current course once."""
    if "courses" not in session_state:
        current_course = session_state.get("current_course")
        session_state["courses"] = (
            [current_course] if current_course is not None else []
        )

    if "current_course" not in session_state:
        session_state["current_course"] = None


def save_course(
    session_state: MutableMapping[str, Any],
    course: StudyPackage,
) -> None:
    """Add a course or replace its saved copy, then make it current."""
    initialize_courses(session_state)
    courses = session_state["courses"]

    for index, saved_course in enumerate(courses):
        if saved_course.course_id == course.course_id:
            courses[index] = course
            break
    else:
        courses.append(course)

    session_state["current_course"] = course


def select_course(
    session_state: MutableMapping[str, Any],
    course_id: str,
) -> StudyPackage:
    """Set the saved course with this ID as the current course."""
    initialize_courses(session_state)

    for course in session_state["courses"]:
        if course.course_id == course_id:
            session_state["current_course"] = course
            return course

    raise KeyError(f"Course not found: {course_id}")
