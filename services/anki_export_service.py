import csv
from collections.abc import Collection
from io import StringIO
import re

from models.schemas import StudyPackage, TopicStats
from services.mastery_engine import get_mastery_status
from services.question_editor import available_questions


def _tag_token(value: str) -> str:
    return re.sub(r"\s+", "_", value.strip())


def get_weak_topic_ids(stats: list[TopicStats], mode: str) -> set[str]:
    """Return topic IDs classified as weak or developing for one mode."""
    if mode not in ("mock", "topic"):
        raise ValueError(f"Invalid mode: {mode}")

    selected_stats: dict[str, TopicStats] = {}
    for item in stats:
        if item.mode != mode:
            continue
        if item.topic_id in selected_stats:
            raise ValueError(
                f"Duplicate topic stats for mode {mode}: {item.topic_id}"
            )
        selected_stats[item.topic_id] = item

    return {
        topic_id
        for topic_id, item in selected_stats.items()
        if get_mastery_status(item) in ("weak", "developing")
    }


def export_anki_tsv(
    package: StudyPackage,
    topic_ids: Collection[str] | None = None,
) -> str:
    """Return Anki Front/Back/Tags fields as UTF-8-ready TSV text.

    Optionally filters to topic IDs. The first occurrence of each Question ID
    is exported, preserving order.
    """
    output = StringIO(newline="")
    writer = csv.writer(
        output,
        delimiter="\t",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )

    seen_question_ids: set[str] = set()
    for question in available_questions(package):
        if topic_ids is not None and question.topic_id not in topic_ids:
            continue
        if question.id in seen_question_ids:
            continue
        seen_question_ids.add(question.id)

        options = "\n".join(
            f"{chr(ord('A') + index)}. {option}"
            for index, option in enumerate(question.options)
        )
        front = f"{question.question}\n{options}"

        answer_label = chr(ord("A") + question.correct_index)
        answer_text = question.options[question.correct_index]
        back = (
            f"Correct answer: {answer_label}. {answer_text}\n"
            f"Explanation: {question.explanation}"
        )
        tags = (
            f"course_{_tag_token(package.course_id)} "
            f"topic_{_tag_token(question.topic_id)}"
        )
        writer.writerow((front, back, tags))

    return output.getvalue()
