
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Topic(BaseModel):
    id: str
    name: str
    summary: str
    source_pages: list[int] = Field(default_factory=list)


class Relationship(BaseModel):
    from_topic: str
    to_topic: str
    type: Literal["related", "prerequisite"] = "related"


class Question(BaseModel):
    version_of: str | None = None
    id: str
    topic_id: str
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str
    source_pages: list[int] = Field(default_factory=list)


class StudyPackage(BaseModel):
    course_id: str
    course_name: str
    topics: list[Topic]
    relationships: list[Relationship]
    questions: list[Question]
    learning_state: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self):
        topic_ids = [topic.id for topic in self.topics]
        question_ids = [question.id for question in self.questions]

        if len(topic_ids) != len(set(topic_ids)):
            raise ValueError("Duplicate topic IDs")

        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Duplicate question IDs")

        for question in self.questions:
            if question.topic_id not in topic_ids:
                raise ValueError(
                    f"Unknown topic ID: {question.topic_id}"
                )

        for relation in self.relationships:
            if relation.from_topic not in topic_ids:
                raise ValueError("Invalid relationship source")
            if relation.to_topic not in topic_ids:
                raise ValueError("Invalid relationship target")

        by_id = {question.id: question for question in self.questions}
        for question in self.questions:
            seen = {question.id}
            parent = question.version_of
            while parent is not None:
                if parent not in by_id or parent in seen:
                    raise ValueError("Invalid question version chain")
                if by_id[parent].topic_id != question.topic_id:
                    raise ValueError("Question versions must remain in the same topic")
                seen.add(parent)
                parent = by_id[parent].version_of
        from services.learning_state import validate_metadata
        validate_metadata(self.learning_state, topic_ids, question_ids)
        return self


class ExamSession(BaseModel):
    session_id: str
    mode: Literal["mock", "topic"]
    question_ids: list[str]


class AttemptResult(BaseModel):
    session_id: str
    question_id: str
    selected_index: int | None
    is_correct: bool


class TopicStats(BaseModel):
    topic_id: str
    mode: Literal["mock", "topic"]
    correct: int = Field(ge=0)
    attempted: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0, le=100)
    unique_attempted: int | None = Field(default=None, ge=0)
    evidence_accuracy: float | None = Field(default=None, ge=0, le=100)
