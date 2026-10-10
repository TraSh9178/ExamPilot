
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
