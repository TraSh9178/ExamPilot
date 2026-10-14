from copy import deepcopy
from pathlib import Path
import json
import pytest
from streamlit.testing.v1 import AppTest
from models.schemas import Question
from services.question_review import validate_question_content, create_mistake_review, question_sources
from tests.test_practice_page import make_practice_state, PAGE_PATH


def question(stem="What is x²?", options=None):
    return Question(id="q", topic_id="t", question=stem, options=options or ["a", "b", "c", "d"], correct_index=0, explanation="Because.")


def test_duplicate_stems_with_distinct_ids_are_rejected():
    first = question()
    second = first.model_copy(update={"id": "different", "question": "  WHAT   is x²?  "})
    with pytest.raises(ValueError, match="repeat"):
        validate_question_content([first, second])


def test_normalized_duplicate_options_are_rejected():
    with pytest.raises(ValueError, match="options"):
        validate_question_content([question(options=["a b", " A  B ", "c", "d"])])


def test_mathematical_operators_and_exponents_remain_distinct():
    validate_question_content([question("What is x-1?"), question("What is x1?")])
    validate_question_content([question("What is x²?"), question("What is x2?")])


def test_generated_duplicate_batch_is_rejected_without_mutating_course(monkeypatch):
    from tests.test_gemini_service import make_questions, make_txt_document, make_study_package, install_fake_client, FAKE_API_KEY
    from services.gemini_service import generate_questions
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_API_KEY)
    candidates = make_questions()
    candidates[1]["question"] = candidates[0]["question"]
    install_fake_client(monkeypatch, text=json.dumps(candidates))
    course = make_study_package()
    before = course.model_dump()
    result = generate_questions(make_txt_document(), course, ["topic-1"])
    assert not result["ok"] and result["error_code"] == "INVALID_QUESTIONS"
    assert course.model_dump() == before


@pytest.mark.parametrize("selected", [None, 1])
def test_review_gets_fresh_session_id_and_keeps_original_result(selected):
    state = make_practice_state(selected_index=selected)
    old = state["active_practice_course-1"]
    before = deepcopy(old)
    review = create_mistake_review(old["session"], old["questions"], old["result"]["attempts"], ["topic-1"])
    assert review["session"].session_id != old["session"].session_id
    assert review["session"].question_ids == old["session"].question_ids
    assert "result" not in review and old == before
    with pytest.raises(ValueError):
        create_mistake_review(old["session"], old["questions"], old["result"]["attempts"], ["other-topic"])


def test_correct_answers_are_not_reintroduced_as_mistakes():
    state = make_practice_state(selected_index=0)
    old = state["active_practice_course-1"]
    with pytest.raises(ValueError, match="No missed"):
        create_mistake_review(old["session"], old["questions"], old["result"]["attempts"], ["topic-1"])


def test_source_text_is_only_taken_from_existing_cited_pages():
    q = question().model_copy(update={"source_pages": [2, 9]})
    assert question_sources(q, None) == []
    assert question_sources(q, {"pages": [{"page": 1, "text": "Uncited"}, {"page": 2, "text": "Real extracted text"}]}) == [(2, "Real extracted text")]


def test_review_button_starts_blank_practice_and_retains_history():
    state = make_practice_state(selected_index=None)
    app = AppTest.from_file(str(PAGE_PATH))
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    previous = deepcopy(app.session_state["practice_history_course-1"])
    app.button(key="review_mistakes_session-1").click().run()
    assert not app.exception
    active = app.session_state["active_practice_course-1"]
    assert active["session"].session_id != "session-1"
    assert "result" not in active
    answer = app.radio(key=f"answer_{active['session'].session_id}_question-1")
    assert answer.value is None
    assert app.session_state["practice_history_course-1"] == previous
    answer.set_value(0).run()
    next(button for button in app.button if button.label == "Submit answers").click().run()
    assert not app.exception
    assert len(app.session_state["practice_history_course-1"]) == len(previous) + 1
    assert app.session_state["practice_history_course-1"]["session-1"] == previous["session-1"]


def test_generation_cannot_reuse_existing_question_id_with_new_content():
    original = question()
    changed = original.model_copy(update={"question": "Different question?"})
    with pytest.raises(ValueError, match="existing question ID"):
        validate_question_content([changed], [original])
    validate_question_content([original], [original])


def test_generation_cannot_duplicate_existing_stem_under_a_new_id():
    original = question()
    changed = original.model_copy(update={"id": "new-id"})
    with pytest.raises(ValueError, match="already in this course"):
        validate_question_content([changed], [original])


def test_review_filters_multiple_topics_without_regrading_old_answers():
    from models.schemas import ExamSession
    from services.exam_engine import grade_exam
    first = question().model_copy(update={"id": "one", "topic_id": "t1"})
    second = question().model_copy(update={"id": "two", "topic_id": "t2"})
    session = ExamSession(session_id="original", mode="mock", question_ids=["one", "two"])
    graded = grade_exam(session, [first, second], {"one": None, "two": 1})
    review = create_mistake_review(session, [first, second], graded["attempts"], ["t1", "t2"], "t2")
    assert review["session"].mode == "topic"
    assert review["session"].question_ids == ["two"]
    assert graded["correct_count"] == 0


def test_feedback_shows_only_retained_source_text():
    state = make_practice_state(selected_index=1)
    state["active_practice_course-1"]["questions"][0].source_pages = [2]
    state["course_document_course-1"] = {"pages": [{"page": 2, "text": "Original page two text."}, {"page": 3, "text": "Uncited page three."}]}
    app = AppTest.from_file(str(PAGE_PATH))
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    assert "Original page two text." in [entry.value for entry in app.text]
    assert "Uncited page three." not in [entry.value for entry in app.text]
