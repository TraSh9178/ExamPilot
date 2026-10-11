PENDING_INTEGRATION_MESSAGES: dict[str, str] = {
    "tutor": "Gemini Tutor 接口待接入。",
    "anki": "Anki 负责人和生成接口待确认；CSV/APKG 格式待确认。",
    "database": "仅保存在当前会话；数据库待接入。",
}


def tutor_question_key(course_id: str) -> str:
    return f"tutor_question_{course_id}"
