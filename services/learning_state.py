"""Bounded, JSON-only learning metadata stored atomically with the course."""
import json
from copy import deepcopy

MAX_TEXT = 50_000


def validate_metadata(metadata, topic_ids, question_ids):
    if not isinstance(metadata, dict):
        raise ValueError("Learning state must be an object.")
    try:
        encoded = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("Learning state must contain JSON-only data.") from error
    if len(encoded) > 512_000:
        raise ValueError("Saved learning state exceeds the storage limit.")
    stage = metadata.get("stage")
    if stage is not None and stage not in ("topics_only", "questions_generated"):
        raise ValueError("Invalid learning stage.")
    order = metadata.get("session_order", [])
    if not isinstance(order, list) or any(not isinstance(sid, str) for sid in order) or len(order) != len(set(order)):
        raise ValueError("Invalid practice chronology.")
    scope = metadata.get("confirmed_scope")
    if scope is not None and (not isinstance(scope, list) or any(not isinstance(x, str) for x in scope)
                              or len(scope) != len(set(scope)) or not set(scope).issubset(topic_ids)):
        raise ValueError("Saved scope is invalid.")
    document = metadata.get("document")
    if document is not None:
        if not isinstance(document, dict) or not isinstance(document.get("text"), str) or len(document["text"]) > MAX_TEXT:
            raise ValueError("Saved material must contain at most 50,000 extracted characters.")
        filename = document.get("filename", "")
        if not isinstance(filename, str) or len(filename) > 255:
            raise ValueError("Invalid material filename.")
        pages = document.get("pages", [])
        if not isinstance(pages, list) or len(pages) > 1000:
            raise ValueError("Invalid material pages.")
        seen = set()
        total = 0
        for page in pages:
            if not isinstance(page, dict) or type(page.get("page")) is not int or page["page"] < 1 or page["page"] in seen or not isinstance(page.get("text"), str):
                raise ValueError("Invalid material page.")
            seen.add(page["page"])
            total += len(page["text"])
        if total > MAX_TEXT:
            raise ValueError("Saved page text exceeds 50,000 characters.")
    reviews = metadata.get("question_reviews", {})
    if not isinstance(reviews, dict) or any(qid not in question_ids or (not isinstance(status, str) or status not in {"pending", "approved", "flagged", "superseded"}) for qid, status in reviews.items()):
        raise ValueError("Invalid question review state.")


def capture_learning_state(course, state):
    metadata = deepcopy(course.learning_state)
    document_key = f"course_document_{course.course_id}"
    if document_key in state:
        document = state[document_key]
        metadata["document"] = {key: deepcopy(document[key]) for key in ("filename", "text", "pages", "sources", "ok") if key in document}
    if f"confirmed_scope_{course.course_id}" in state or "confirmed_scope" in metadata:
        metadata["confirmed_scope"] = deepcopy(state.get(f"confirmed_scope_{course.course_id}"))
    if f"course_stage_{course.course_id}" in state:
        metadata["stage"] = state[f"course_stage_{course.course_id}"]
    order = list(metadata.get("session_order", []))
    for session_id in state.get(f"practice_history_{course.course_id}", {}):
        if session_id not in order:
            order.append(session_id)
    if order:
        metadata["session_order"] = order
    data = course.model_dump(mode="json")
    data["learning_state"] = metadata
    return type(course).model_validate(data)


def restored_learning_state(course):
    metadata = course.learning_state
    updates = {}
    if metadata.get("document") is not None:
        updates[f"course_document_{course.course_id}"] = deepcopy(metadata["document"])
    if metadata.get("confirmed_scope"):
        for prefix in ("confirmed_scope", "scope_selection"):
            updates[f"{prefix}_{course.course_id}"] = list(metadata["confirmed_scope"])
    if metadata.get("stage"):
        updates[f"course_stage_{course.course_id}"] = metadata["stage"]
    return updates
