"""Review metadata changes never mutate historical question content."""
from copy import deepcopy
from uuid import uuid4
from models.schemas import Question, StudyPackage


def status_for(course, question_id):
    return course.learning_state.get("question_reviews", {}).get(question_id, "legacy")


def available_questions(course):
    return [question for question in course.questions if status_for(course, question.id) in {"approved", "legacy"}]


def review_question(course: StudyPackage, question_id: str, status: str, changes: dict | None = None) -> StudyPackage:
    if status not in {"approved", "flagged"}:
        raise ValueError("Invalid review decision.")
    old = next((q for q in course.questions if q.id == question_id), None)
    if old is None:
        raise ValueError("Unknown question.")
    if status_for(course, old.id) == "superseded":
        raise ValueError("Review the current question version instead.")
    data = old.model_dump()
    if changes:
        permitted = {"question", "options", "correct_index", "explanation"}
        if not set(changes).issubset(permitted):
            raise ValueError("Cannot change question identity, topic or citations.")
        data.update(changes)
    revised = Question.model_validate(data)
    if not revised.question.strip() or not revised.explanation.strip() or any(not option.strip() for option in revised.options) or len({option.strip().casefold() for option in revised.options}) != 4:
        raise ValueError("Question, explanation and four distinct options are required.")
    from services.question_review import normalized_text
    family = old.version_of or old.id
    for other in course.questions:
        if (other.version_of or other.id) != family and normalized_text(other.question) == normalized_text(revised.question):
            raise ValueError("This question duplicates a different question family.")
    metadata = deepcopy(course.learning_state)
    reviews = metadata.setdefault("question_reviews", {})
    questions = list(course.questions)
    if revised != old:
        revised = revised.model_copy(update={"id": str(uuid4()), "version_of": old.version_of or old.id})
        questions.append(revised)
        reviews[old.id] = "superseded"
        reviews[revised.id] = status
    else:
        reviews[old.id] = status
    package = course.model_dump()
    package.update(questions=[q.model_dump() for q in questions], learning_state=metadata)
    return StudyPackage.model_validate(package)
