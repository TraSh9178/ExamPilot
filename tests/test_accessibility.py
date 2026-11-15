"""Tests for the data-independent accessibility presentation contract."""

import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import Question, StudyPackage, ExamSession
from services.exam_engine import grade_exam
from services.question_editor import available_questions
from services.accessibility import (
    BILINGUAL_KEY,
    SIMPLIFY_KEY,
    annotate_terms,
    display_question,
    display_text,
)


def test_disabled_controls_return_original_question() -> None:
    question = Question(
        id="sample", topic_id="topic", question="Find the derivative.",
        options=["x", "2x", "3x", "4x"], correct_index=1,
        explanation="Use the derivative rule.",
    )
    display = display_question("unknown-course", question, {})
    assert display.question == question.question
    assert display.options == question.options
    assert display.explanation == question.explanation
    assert display.simplified is False
    assert question.options == ["x", "2x", "3x", "4x"]


def test_missing_simplified_question_falls_back_to_original() -> None:
    question = Question(
        id="custom", topic_id="topic", question="What is x + 1?",
        options=["1", "x", "x + 1", "0"], correct_index=2,
        explanation="Add one to x.",
    )
    display = display_question("custom-course", question, {SIMPLIFY_KEY: True})
    assert display.question == question.question
    assert display.options == question.options
    assert display.simplified is False


def test_annotate_terms_case_whole_words_longest_and_once() -> None:
    glossary = {"line": "线", "tangent line": "切线", "derivative": "导数"}
    text = "Tangent line and LINE. Derivative, derivative, derivatives, pipeline."
    assert annotate_terms(text, glossary) == (
        "Tangent line (切线) and LINE (线). "
        "Derivative (导数), derivative, derivatives, pipeline."
    )


def test_annotate_terms_preserves_code_math_and_existing_labels() -> None:
    glossary = {"derivative": "导数"}
    text = "`derivative` $derivative$ \\(derivative\\) derivative (导数) derivative"
    assert annotate_terms(text, glossary) == text
    assert display_text(text, {BILINGUAL_KEY: False}) == text


def test_display_text_reads_glossary_only_when_enabled(monkeypatch) -> None:
    from services import accessibility

    monkeypatch.setattr(accessibility, "_read_mapping", lambda _: {"limit": "极限"})
    assert display_text("Limit and limit", {BILINGUAL_KEY: True}) == (
        "Limit (极限) and limit"
    )


ROOT = Path(__file__).resolve().parents[1]
DEMO_FILES = {
    "econ101": "sample_course.json",
    "calculus-i-demo": "calculus_i_demo.json",
    "python-basics-demo": "demo_python_basics.json",
}


def test_accessibility_controls_have_expected_labels_and_keys() -> None:
    app = AppTest.from_string(
        "from services.accessibility import render_accessibility_controls\n"
        "render_accessibility_controls()"
    ).run()
    assert not app.exception
    assert "Accessibility" in [element.value for element in app.subheader]
    assert [(item.label, item.key) for item in app.get("toggle")] == [
        ("Simplified English", SIMPLIFY_KEY),
        ("中文界面 / Chinese interface", BILINGUAL_KEY),
    ]


@pytest.mark.parametrize("course_id,filename", DEMO_FILES.items())
def test_demo_variants_cover_original_questions_without_changing_numbers(
    course_id: str, filename: str,
) -> None:
    source = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))
    package = StudyPackage.model_validate(source)
    variants = json.loads(
        (ROOT / "data" / "accessibility" / f"simplified_{course_id}.json")
        .read_text(encoding="utf-8")
    )["questions"]
    # Reviewed original questions have simplified variants; new drafts use
    # the documented original-wording fallback until variants are authored.
    assert set(variants) == {question.id for question in available_questions(package)}
    for question in available_questions(package):
        variant = variants[question.id]
        assert set(variant) == {"question", "options", "explanation"}
        assert len(variant["options"]) == len(question.options) == 4
        for original, simplified in zip(
            [question.question, *question.options],
            [variant["question"], *variant["options"]],
        ):
            assert re.findall(r"\d+", original) == re.findall(r"\d+", simplified)
        assert variant["explanation"]
        display = display_question(course_id, question, {SIMPLIFY_KEY: True})
        assert display.simplified is True
        assert display.options == variant["options"]


def test_simplified_display_keeps_answer_index_and_grade() -> None:
    package = StudyPackage.model_validate(json.loads(
        (ROOT / "data" / "calculus_i_demo.json").read_text(encoding="utf-8")
    ))
    questions = package.questions
    for question in questions:
        display = display_question(package.course_id, question, {SIMPLIFY_KEY: True})
        assert display.options[question.correct_index] == question.options[question.correct_index]
    required_formulas = {
        "calc_q001": ["lim(x→2) (x² − 4)/(x − 2)", "x ≠ 2", "(x² − 4)/(x − 2) = (x − 2)(x + 2)/(x − 2) = x + 2"],
        "calc_q002": ["f(x) = x³ − 5x", "f′(x)", "3x² − 5", "−5x"],
        "calc_q003": ["f(x) = x² − 4x", "f′(x) = 2x − 4", "f″(x) = 2 > 0", "x = 2"],
    }
    for question in questions:
        display = display_question(package.course_id, question, {SIMPLIFY_KEY: True})
        combined = " ".join([display.question, *display.options, display.explanation])
        for formula in required_formulas.get(question.id, []):
            assert formula in combined
    session = ExamSession(session_id="accessibility-test", mode="mock", question_ids=[q.id for q in questions])
    answers = {q.id: q.correct_index for q in questions}
    assert grade_exam(session, questions, answers)["correct_count"] == len(questions)


def test_practice_page_shows_simplified_wording_and_original(monkeypatch) -> None:
    import streamlit as st
    # Standalone pages do not register navigation for the review-drafts link.
    monkeypatch.setattr(st, "page_link", lambda *args, **kwargs: None)
    package = StudyPackage.model_validate(json.loads(
        (ROOT / "data" / "sample_course.json").read_text(encoding="utf-8")
    ))
    question = package.questions[0]
    session = ExamSession(session_id="accessibility-page", mode="mock", question_ids=[question.id])
    page = ROOT / "pages" / "2_Practice_Center.py"
    app = AppTest.from_file(str(page))
    app.session_state["current_course"] = package
    app.session_state[f"confirmed_scope_{package.course_id}"] = [question.topic_id]
    app.session_state[f"active_practice_{package.course_id}"] = {
        "session": session, "questions": [question], "warning": None,
        "settings": {"mode": "mock", "requested_count": 1,
                     "confirmed_topic_ids": [question.topic_id], "topic_id": None},
    }
    app.session_state[SIMPLIFY_KEY] = True
    app.run()
    assert not app.exception
    assert any("Demand rises. Supply stays the same." in element.value for element in app.markdown)
    assert any(element.label == "Show original wording" for element in app.expander)

    # The same displayed wording is used for the result; grading still reads
    # the original question and selected option index.
    app.session_state[f"active_practice_{package.course_id}"]["result"] = grade_exam(
        session, [question], {question.id: question.correct_index}
    )
    app.run()
    assert not app.exception
    assert any("Demand rises. Supply stays the same." in item.value for item in app.markdown)
    assert any(item.label == "Score" and item.value == "1 / 1" for item in app.metric)


def test_glossary_has_course_terms_and_two_modes_work_together() -> None:
    glossary = json.loads(
        (ROOT / "data" / "accessibility" / "glossary_zh.json")
        .read_text(encoding="utf-8")
    )
    assert 40 <= len(glossary) <= 60
    package = StudyPackage.model_validate(json.loads(
        (ROOT / "data" / "sample_course.json").read_text(encoding="utf-8")
    ))
    display = display_question(package.course_id, package.questions[0],
                               {SIMPLIFY_KEY: True, BILINGUAL_KEY: True})
    assert display.simplified is True
    assert "需求" in display.question
