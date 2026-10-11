import csv
import json
from io import StringIO
from pathlib import Path

import pytest

from models.schemas import Question, StudyPackage, TopicStats
from services.anki_export_service import export_anki_tsv, get_weak_topic_ids


def _load_python_basics_demo() -> StudyPackage:
    path = Path(__file__).parents[1] / "data" / "demo_python_basics.json"
    with path.open(encoding="utf-8") as file:
        return StudyPackage.model_validate(json.load(file))


def _read_tsv(content: str) -> list[list[str]]:
    return list(csv.reader(StringIO(content, newline=""), delimiter="\t"))


def test_exports_all_nine_questions_from_python_basics_demo():
    package = _load_python_basics_demo()

    rows = _read_tsv(export_anki_tsv(package))

    assert len(rows) == 9
    assert all(len(row) == 3 for row in rows)
    assert rows[0][0].startswith(
        "What is the purpose of assignment in relation to a variable?\n"
    )
    assert rows[0][2] == (
        "course_python-basics-demo topic_python-basics-topic-1"
    )


def test_back_contains_correct_answer_and_explanation():
    package = _load_python_basics_demo()

    first_row = _read_tsv(export_anki_tsv(package))[0]

    assert first_row[1] == (
        "Correct answer: A. It binds a value to a variable name.\n"
        "Explanation: Assignment binds a variable name to an object. "
        "Reassignment changes which object the name is bound to; it does "
        "not mean the old object itself was modified or deleted."
    )


def test_tsv_preserves_tabs_newlines_and_quotes_in_fields():
    package = _load_python_basics_demo()
    special_question = Question(
        id="special-q",
        topic_id="special-topic",
        question='Which "value"\tuses a newline?\nChoose:',
        options=[
            "first\toption",
            "second\noption",
            'third "quoted" option',
            "fourth option",
        ],
        correct_index=2,
        explanation='The "quoted"\tanswer\nis correct.',
    )
    package.questions = [special_question]

    content = export_anki_tsv(package)
    rows = _read_tsv(content)

    assert len(rows) == 1
    assert len(rows[0]) == 3
    assert rows[0][0] == (
        'Which "value"\tuses a newline?\nChoose:\n'
        "A. first\toption\n"
        "B. second\noption\n"
        'C. third "quoted" option\n'
        "D. fourth option"
    )
    assert rows[0][1] == (
        'Correct answer: C. third "quoted" option\n'
        'Explanation: The "quoted"\tanswer\nis correct.'
    )
    assert '""value""' in content


def test_duplicate_question_ids_keep_first_occurrence_and_order():
    package = _load_python_basics_demo()
    first_question, second_question, third_question = package.questions[:3]
    duplicate = first_question.model_copy(
        update={"question": "Duplicate with different content"}
    )
    package = StudyPackage.model_construct(
        course_id=package.course_id,
        course_name=package.course_name,
        topics=package.topics,
        relationships=package.relationships,
        questions=[
            first_question,
            second_question,
            duplicate,
            third_question,
        ],
    )

    rows = _read_tsv(export_anki_tsv(package))

    assert len(rows) == 3
    assert "Duplicate with different content" not in "\n".join(row[0] for row in rows)
    assert rows[0][0].startswith(first_question.question)
    assert rows[1][0].startswith(second_question.question)
    assert rows[2][0].startswith(third_question.question)


def test_empty_questions_export_to_empty_tsv():
    package = _load_python_basics_demo()
    package.questions = []

    assert export_anki_tsv(package) == ""


def test_export_is_deterministic_and_does_not_mutate_package():
    package = _load_python_basics_demo()
    original_data = package.model_dump()

    first_export = export_anki_tsv(package)
    second_export = export_anki_tsv(package)

    assert first_export == second_export
    assert package.model_dump() == original_data


def test_weak_topic_ids_include_weak_and_developing_but_not_mastered():
    stats = [
        TopicStats(
            topic_id="weak-topic",
            mode="mock",
            correct=1,
            attempted=3,
            accuracy=33.33,
        ),
        TopicStats(
            topic_id="developing-topic",
            mode="mock",
            correct=2,
            attempted=3,
            accuracy=66.67,
        ),
        TopicStats(
            topic_id="mastered-topic",
            mode="mock",
            correct=3,
            attempted=3,
            accuracy=100,
        ),
    ]
    original_stats = [item.model_dump() for item in stats]

    assert get_weak_topic_ids(stats, "mock") == {
        "weak-topic",
        "developing-topic",
    }
    assert [item.model_dump() for item in stats] == original_stats


def test_weak_topic_ids_do_not_mix_mock_and_topic_practice():
    stats = [
        TopicStats(
            topic_id="same-topic",
            mode="mock",
            correct=0,
            attempted=3,
            accuracy=0,
        ),
        TopicStats(
            topic_id="same-topic",
            mode="topic",
            correct=3,
            attempted=3,
            accuracy=100,
        ),
    ]

    assert get_weak_topic_ids(stats, "mock") == {"same-topic"}
    assert get_weak_topic_ids(stats, "topic") == set()


def test_weak_topic_ids_reject_duplicate_stats_for_selected_mode():
    stats = [
        TopicStats(
            topic_id="same-topic",
            mode="mock",
            correct=1,
            attempted=3,
            accuracy=33.33,
        ),
        TopicStats(
            topic_id="same-topic",
            mode="mock",
            correct=2,
            attempted=3,
            accuracy=66.67,
        ),
    ]

    with pytest.raises(ValueError, match="Duplicate topic stats for mode mock"):
        get_weak_topic_ids(stats, "mock")


def test_weak_topic_filter_exports_only_matching_questions_in_order():
    package = _load_python_basics_demo()
    weak_topics = {"python-basics-topic-1", "python-basics-topic-3"}

    rows = _read_tsv(export_anki_tsv(package, topic_ids=weak_topics))

    assert len(rows) == 6
    assert [row[2].split()[-1] for row in rows] == [
        "topic_python-basics-topic-1",
        "topic_python-basics-topic-1",
        "topic_python-basics-topic-1",
        "topic_python-basics-topic-3",
        "topic_python-basics-topic-3",
        "topic_python-basics-topic-3",
    ]


def test_no_weak_topics_returns_valid_empty_export():
    package = _load_python_basics_demo()
    stats = [
        TopicStats(
            topic_id=topic.id,
            mode="mock",
            correct=3,
            attempted=3,
            accuracy=100,
        )
        for topic in package.topics
    ]

    topic_ids = get_weak_topic_ids(stats, "mock")

    assert topic_ids == set()
    assert export_anki_tsv(package, topic_ids=topic_ids) == ""
    assert export_anki_tsv(package) != ""


def test_empty_stats_have_no_weak_topics_and_export_empty_when_filtered():
    package = _load_python_basics_demo()

    topic_ids = get_weak_topic_ids([], "mock")

    assert topic_ids == set()
    assert export_anki_tsv(package, topic_ids=topic_ids) == ""
