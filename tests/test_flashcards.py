"""Flashcard decks: mistakes, weak topics, key ideas and all questions."""

from models.schemas import AttemptResult, ExamSession, Question, StudyPackage
from services import flashcards
from services.flashcards import (
    DECK_LABELS,
    DECK_ORDER,
    Flashcard,
    answer_text,
    build_decks,
    current_mistakes,
    default_deck,
    option_letter,
    weak_topic_ids,
)


def make_course(learning_state: dict | None = None) -> StudyPackage:
    """Limits q1-q3, Derivatives q4-q6, Series q7 (+ q8 waiting for review)."""
    layout = {
        "q1": "t1", "q2": "t1", "q3": "t1",
        "q4": "t2", "q5": "t2", "q6": "t2",
        "q7": "t3", "q8": "t3",
    }
    questions = [
        Question(
            id=question_id,
            topic_id=topic_id,
            question=f"Question {question_id}?",
            options=[f"{question_id} first", f"{question_id} second", f"{question_id} third", f"{question_id} fourth"],
            correct_index=1,
            explanation=f"Because {question_id}.",
        )
        for question_id, topic_id in layout.items()
    ]
    state = {"question_reviews": {"q8": "pending"}}
    state.update(learning_state or {})
    return StudyPackage(
        course_id="c1",
        course_name="Calculus",
        topics=[
            {"id": "t1", "name": "Limits", "summary": "Limits describe nearby values."},
            {"id": "t2", "name": "Derivatives", "summary": "A derivative is a rate of change."},
            {"id": "t3", "name": "Series", "summary": "   "},
        ],
        relationships=[],
        questions=questions,
        learning_state=state,
    )


def add_session(history: dict, course: StudyPackage, session_id: str, mode: str, answers: list) -> dict:
    """answers: (question_id, selected_index, is_correct) in session order."""
    by_id = {question.id: question for question in course.questions}
    history[session_id] = {
        "session": ExamSession(session_id=session_id, mode=mode, question_ids=[qid for qid, _, _ in answers]),
        "questions": [by_id[qid] for qid, _, _ in answers],
        "attempts": [
            AttemptResult(session_id=session_id, question_id=qid, selected_index=selected, is_correct=correct)
            for qid, selected, correct in answers
        ],
    }
    return history


def question_ids(cards: list[Flashcard]) -> list[str]:
    return [card.question.id for card in cards]


def test_without_history_only_key_ideas_and_all_questions_are_offered():
    course = make_course()

    for history in ({}, None):
        decks = build_decks(course, history)

        assert list(decks) == ["ideas", "all"]
        assert default_deck(decks) == "all"
        # Every available question in course order; the question waiting for review is left out.
        assert question_ids(decks["all"]) == ["q1", "q2", "q3", "q4", "q5", "q6", "q7"]
        # One card per topic with a summary; Series has only blank space.
        assert [(card.kind, card.topic_name, card.summary) for card in decks["ideas"]] == [
            ("idea", "Limits", "Limits describe nearby values."),
            ("idea", "Derivatives", "A derivative is a rate of change."),
        ]
        assert not any(card.mistake for card in decks["all"])


def test_mistakes_are_newest_first_and_remember_the_last_choice():
    course = make_course()
    history = add_session({}, course, "s1", "mock", [("q1", 2, False), ("q3", None, False), ("q2", 1, True)])
    add_session(history, course, "s2", "topic", [("q6", 0, False)])

    decks = build_decks(course, history)

    assert default_deck(decks) == "mistakes"
    assert question_ids(decks["mistakes"]) == ["q6", "q1", "q3"]
    assert [(card.mistake, card.last_choice) for card in decks["mistakes"]] == [
        (True, 0), (True, 2), (True, None),
    ]
    # The same mistake information follows the question into the other decks.
    by_id = {card.question.id: card for card in decks["all"]}
    assert (by_id["q1"].mistake, by_id["q1"].last_choice) == (True, 2)
    assert (by_id["q2"].mistake, by_id["q2"].last_choice) == (False, None)


def test_a_question_answered_correctly_later_is_no_longer_a_mistake():
    course = make_course()
    history = add_session({}, course, "s1", "mock", [("q1", 0, False), ("q2", 1, True)])
    add_session(history, course, "s2", "mock", [("q1", 1, True), ("q2", 3, False)])

    assert [question.id for question, _ in current_mistakes(course, history)] == ["q2"]
    assert question_ids(build_decks(course, history)["mistakes"]) == ["q2"]


def test_saved_session_order_decides_which_attempt_is_newest():
    # s2 was added to this browser session first, but the saved chronology says it is older.
    course = make_course({"session_order": ["s2", "s1"]})
    history = add_session({}, course, "s2", "mock", [("q1", 0, False)])
    add_session(history, course, "s1", "mock", [("q1", 1, True), ("q4", 0, False)])

    assert question_ids(build_decks(course, history)["mistakes"]) == ["q4"]


def test_unavailable_questions_and_unknown_choices_are_handled():
    course = make_course()
    history = add_session({}, course, "s1", "mock", [("q8", 0, False), ("q7", 9, False)])

    mistakes = current_mistakes(course, history)

    # q8 is waiting for review, so it is not offered; an impossible choice reads as blank.
    assert [(question.id, choice) for question, choice in mistakes] == [("q7", None)]


def test_weak_topics_cover_both_practice_modes_with_mistakes_first():
    course = make_course()
    # Topic practice: Derivatives 1 of 3 correct -> weak.
    history = add_session({}, course, "s1", "topic", [("q4", 0, False), ("q5", 2, False), ("q6", 1, True)])
    # Mock exam: Limits 2 of 3 correct -> developing.
    add_session(history, course, "s2", "mock", [("q1", 1, True), ("q2", 1, True), ("q3", 3, False)])

    assert weak_topic_ids(course, history) == {"t1", "t2"}
    decks = build_decks(course, history)

    assert list(decks) == ["mistakes", "weak", "ideas", "all"]
    assert question_ids(decks["mistakes"]) == ["q3", "q4", "q5"]
    assert question_ids(decks["weak"]) == ["q3", "q4", "q5", "q1", "q2", "q6"]


def test_key_ideas_put_weak_topics_first():
    course = make_course()
    history = add_session({}, course, "s1", "topic", [("q4", 0, False), ("q5", 2, False), ("q6", 0, False)])

    decks = build_decks(course, history)

    assert weak_topic_ids(course, history) == {"t2"}
    assert [card.topic_name for card in decks["ideas"]] == ["Derivatives", "Limits"]
    assert question_ids(decks["weak"]) == ["q4", "q5", "q6"]


def test_unreadable_history_means_no_weak_topics_but_mistakes_still_work():
    course = make_course()
    history = add_session({}, course, "s1", "mock", [("q1", 0, False)])
    # The attempt names a question that is not part of its session.
    history["s1"]["session"] = ExamSession(session_id="s1", mode="mock", question_ids=["q2"])

    assert weak_topic_ids(course, history) == set()
    decks = build_decks(course, history)
    assert "weak" not in decks
    assert question_ids(decks["mistakes"]) == ["q1"]


def test_weak_topics_without_current_mistakes_become_the_default(monkeypatch):
    course = make_course()
    monkeypatch.setattr(flashcards, "weak_topic_ids", lambda *_args: {"t2"})

    decks = build_decks(course, {})

    assert list(decks) == ["weak", "ideas", "all"]
    assert default_deck(decks) == "weak"
    assert question_ids(decks["weak"]) == ["q4", "q5", "q6"]


def test_default_deck_and_deck_names():
    card = Flashcard(kind="idea", topic_id="t1", topic_name="Limits", summary="Summary.")

    assert default_deck({"ideas": [card]}) == "ideas"
    assert default_deck({}) is None
    assert default_deck({"ideas": [card], "all": [card]}) == "all"
    assert DECK_ORDER == ("mistakes", "weak", "ideas", "all")
    assert DECK_LABELS == {
        "mistakes": "My mistakes", "weak": "Weak topics",
        "ideas": "Key ideas", "all": "All questions",
    }


def test_answer_text_and_card_identity():
    course = make_course()
    question = course.questions[0]
    question_card = build_decks(course, {})["all"][0]
    idea_card = build_decks(course, {})["ideas"][0]

    assert option_letter(0) == "A" and option_letter(3) == "D"
    assert answer_text(question) == "B. q1 second"
    assert question_card.ident == "question:q1"
    assert idea_card.ident == "idea:t1"
    assert question_card.topic_name == "Limits"
