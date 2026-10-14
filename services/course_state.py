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


def remove_course(
    session_state: MutableMapping[str, Any],
    course_id: str,
) -> StudyPackage:
    """Remove a saved course and its course-specific session state."""
    initialize_courses(session_state)

    for index, course in enumerate(session_state["courses"]):
        if course.course_id == course_id:
            removed_course = session_state["courses"].pop(index)
            current_course = session_state.get("current_course")
            if (
                current_course is not None
                and current_course.course_id == course_id
            ):
                session_state["current_course"] = None

            practice_key = f"active_practice_{course_id}"
            history_key = f"practice_history_{course_id}"
            practices = [
                session_state.pop(practice_key, None),
                *session_state.pop(history_key, {}).values(),
            ]
            for practice in practices:
                if practice is None:
                    continue
                session = practice.get("session")
                if session is None:
                    continue
                for question in practice.get("questions", []):
                    session_state.pop(
                        f"answer_{session.session_id}_{question.id}",
                        None,
                    )

            for key in (
                f"confirmed_scope_{course_id}",
                f"scope_selection_{course_id}",
                f"scope_initialised_{course_id}",
                f"course_document_{course_id}",
                f"course_stage_{course_id}",
                f"practice_mode_{course_id}",
                f"practice_topic_{course_id}",
                f"practice_count_{course_id}",
                f"performance_mode_{course_id}",
                f"graph_mode_{course_id}",
            ):
                session_state.pop(key, None)

            return removed_course

    raise KeyError(f"Course not found: {course_id}")
