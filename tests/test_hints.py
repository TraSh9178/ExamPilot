import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import StudyPackage
from services.accessibility import BILINGUAL_KEY, display_text
from services.hints import MAX_HINTS, hint_state_key, hints_for, validate_hints

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "pages" / "2_Practice_Center.py"
CALCULUS_DEMO = "calculus_i_demo.json"


def read_data(filename):
    return json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))


def test_demo_hints_cover_original_available_questions():
    hint_bank = read_data("hints/demo_hints.json")
    questions = {
        question["id"]: question
        for filename in ("sample_course.json", CALCULUS_DEMO, "demo_python_basics.json")
        for question in read_data(filename)["questions"]
    }

    assert len(questions) == 126
    pending = {
        qid
        for filename in ("sample_course.json", CALCULUS_DEMO, "demo_python_basics.json")
        for qid, status in read_data(filename).get("learning_state", {}).get("question_reviews", {}).items()
        if status == "pending"
    }
    assert len(pending) == 111
    assert hint_bank.keys() == questions.keys() - pending
    for question_id, hints in hint_bank.items():
        question = questions[question_id]
        assert 2 <= len(hints) <= MAX_HINTS
        validate_hints(hints, question["options"][question["correct_index"]])


def test_hints_for_uses_first_nonempty_source():
    question = SimpleNamespace(
        id="calc_q001", version_of="q001", hints=["An attached hint."]
    )
    assert hints_for(question) == ["An attached hint."]

    demo_hints = hints_for(SimpleNamespace(id="calc_q001"))
    parent_hints = hints_for(SimpleNamespace(id="q001"))
    assert demo_hints and parent_hints and demo_hints != parent_hints
    question.hints = []
    assert hints_for(question) == demo_hints

    question.id = "edited-question"
    assert hints_for(question) == parent_hints
    question.version_of = None
    assert hints_for(question) == []


@pytest.mark.parametrize(
    ("hints", "answer"),
    [
        (["Read the prompt."] * (MAX_HINTS + 1), "Elastic"),
        ([" \t"], "Elastic"),
        (["Demand is ELASTIC."], "Elastic"),
        (["The derivative is 3x² − 5."], "3x² − 5"),
    ],
)
def test_validate_hints_rejects_invalid_hints(hints, answer):
    with pytest.raises(ValueError):
        validate_hints(hints, answer)


def test_validate_hints_allows_substrings_and_short_answers():
    validate_hints(["Compare price elasticity."], "Elastic")
    validate_hints(["Factor the expression x² − 4."], "4")
    validate_hints([], "Elastic")


def start_practice(mode, *, use_demo_question=True, bilingual=None):
    data = read_data(CALCULUS_DEMO)
    question = data["questions"][0]
    if not use_demo_question:
        question["id"] = "custom-question"
    data["questions"] = [question]
    # This fixture isolates one original question, not the expanded review bank.
    data["learning_state"] = {}
    course = StudyPackage.model_validate(data)

    app = AppTest.from_file(str(PAGE_PATH))
    app.session_state["current_course"] = course
    app.session_state[f"confirmed_scope_{course.course_id}"] = [question["topic_id"]]
    if bilingual is not None:
        # The sidebar toggle lives in app.py; set its session-state key directly.
        app.session_state[BILINGUAL_KEY] = bilingual
    app.run()
    app.radio(key=f"practice_mode_{course.course_id}").set_value(mode)
    app.number_input(key=f"practice_count_{course.course_id}").set_value(1)
    next(button for button in app.button if button.label == "Start practice").click().run()

    assert not app.exception
    practice = app.session_state[f"active_practice_{course.course_id}"]
    return app, practice["session"], course.questions[0]


@pytest.mark.parametrize("use_hints", [False, True])
def test_topic_hints_reveal_in_order_preserve_answer_and_leave_score_unchanged(use_hints):
    app, session, question = start_practice("Topic Practice")
    hints = hints_for(question)
    answer_key = f"answer_{session.session_id}_{question.id}"
    button_key = f"hint_button_{session.session_id}_{question.id}"

    assert app.button(key=button_key).label == "Show a hint"
    assert not [item for item in app.info if item.value.startswith("Hint ")]
    app.radio(key=answer_key).set_value(question.correct_index).run()

    revealed = []
    if use_hints:
        for number, hint in enumerate(hints, start=1):
            app.button(key=button_key).click().run()

            assert not app.exception
            revealed.append(f"Hint {number} of {len(hints)}: {hint}")
            assert [item.value for item in app.info if item.value.startswith("Hint ")] == revealed
            assert app.radio(key=answer_key).value == question.correct_index
            assert app.session_state[hint_state_key(session.session_id, question.id)] == number
            if number < len(hints):
                assert app.button(key=button_key).label == "Show next hint"
            else:
                assert all(button.key != button_key for button in app.button)

    next(button for button in app.button if button.label == "Submit answers").click().run()

    assert not app.exception
    assert f"Hints used: {len(revealed)} of {len(hints)}" in [item.value for item in app.caption]
    assert next(metric.value for metric in app.metric if metric.label == "Score") == "1 / 1"


@pytest.mark.parametrize("bilingual", [False, True])
def test_hint_text_shows_chinese_key_terms_only_when_toggle_is_on(bilingual):
    app, session, question = start_practice("Topic Practice", bilingual=bilingual)
    hints = hints_for(question)
    answer_key = f"answer_{session.session_id}_{question.id}"
    button_key = f"hint_button_{session.session_id}_{question.id}"
    state_key = hint_state_key(session.session_id, question.id)

    app.radio(key=answer_key).set_value(question.correct_index).run()
    for number in range(1, len(hints) + 1):
        app.button(key=button_key).click().run()

        assert not app.exception
        assert app.radio(key=answer_key).value == question.correct_index
        assert app.session_state[state_key] == number
    assert all(button.key != button_key for button in app.button)

    shown = [item.value for item in app.info if item.value.startswith("Hint ")]
    original = [f"Hint {number} of {len(hints)}: {hint}" for number, hint in enumerate(hints, start=1)]
    if bilingual:
        # Each hint is annotated on its own; the counter prefix is untouched.
        assert shown == [
            f"Hint {number} of {len(hints)}: {display_text(hint, {BILINGUAL_KEY: True})}"
            for number, hint in enumerate(hints, start=1)
        ]
        assert shown != original
        assert "the limit (极限)" in shown[0]
    else:
        assert shown == original

    next(button for button in app.button if button.label == "Submit answers").click().run()

    assert not app.exception
    assert f"Hints used: {len(hints)} of {len(hints)}" in [item.value for item in app.caption]
    assert next(metric.value for metric in app.metric if metric.label == "Score") == "1 / 1"


@pytest.mark.parametrize(
    ("mode", "use_demo_question"),
    [("Mock Exam", True), ("Topic Practice", False)],
)
def test_hints_are_absent_during_practice_and_review_when_unavailable(mode, use_demo_question):
    app, _, _ = start_practice(mode, use_demo_question=use_demo_question)

    assert not any(button.label in {"Show a hint", "Show next hint"} for button in app.button)
    assert not any(item.value.startswith("Hint ") for item in app.info)

    next(button for button in app.button if button.label == "Submit answers").click().run()

    assert not app.exception
    assert not any(item.value.startswith("Hints used:") for item in app.caption)
