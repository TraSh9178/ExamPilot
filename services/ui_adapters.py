PENDING_INTEGRATION_MESSAGES: dict[str, str] = {
    "tutor": "Answers use this course's topics and relationships.",
    "anki": "Export a UTF-8 TSV for Anki import; AnkiWeb sync is not supported.",
    "database": "Saved in the current session only; the database is not connected yet.",
}


def tutor_question_key(course_id: str) -> str:
    return f"tutor_question_{course_id}"


def tutor_result_key(course_id: str) -> str:
    return f"tutor_result_{course_id}"
