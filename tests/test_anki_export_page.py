"""Flashcards page (pages/5_Export_Anki.py): one card at a time, Anki export at the bottom."""

import csv
import html
import re
from io import StringIO
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from models.schemas import AttemptResult, ExamSession, StudyPackage
from services.anki_export_service import export_anki_tsv
from services.i18n import LANGUAGE_KEY
from services.question_editor import available_questions


ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "pages" / "5_Export_Anki.py"
CID = "python-basics-demo"


def _python_basics_course() -> StudyPackage:
    path = ROOT / "data" / "demo_python_basics.json"
    course = StudyPackage.model_validate_json(path.read_text(encoding="utf-8"))
    # These export/mastery fixtures exercise the nine originally available cards.
    return course.model_copy(update={"questions": available_questions(course), "learning_state": {}})


def _app_with_course(course: StudyPackage | None = None, chinese: bool = False) -> AppTest:
    app = AppTest.from_file(str(PAGE_PATH))
    if course is not None:
        app.session_state["current_course"] = course
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    return app.run()


def _history(app: AppTest, course: StudyPackage) -> dict:
    history_key = f"practice_history_{course.course_id}"
    history = (
        app.session_state[history_key]
        if history_key in app.session_state
        else {}
    )
    app.session_state[history_key] = history
    return history


def _add_history(
    app: AppTest,
    course: StudyPackage,
    mode: str,
    topic_id: str,
    correct_count: int,
    session_id: str,
) -> None:
    questions = [
        question for question in course.questions
        if question.topic_id == topic_id
    ]
    session = ExamSession(
        session_id=session_id,
        mode=mode,
        question_ids=[question.id for question in questions],
    )
    attempts = [
        AttemptResult(
            session_id=session_id,
            question_id=question.id,
            selected_index=question.correct_index,
            is_correct=index < correct_count,
        )
        for index, question in enumerate(questions)
    ]
    _history(app, course)[session_id] = {
        "session": session,
        "attempts": attempts,
        "questions": questions,
    }


def _add_answers(app: AppTest, course: StudyPackage, session_id: str, mode: str, answers: list) -> None:
    """answers: (question number 1-9, selected index or None, is_correct)."""
    questions = [course.questions[number - 1] for number, _, _ in answers]
    _history(app, course)[session_id] = {
        "session": ExamSession(
            session_id=session_id, mode=mode, question_ids=[question.id for question in questions],
        ),
        "questions": questions,
        "attempts": [
            AttemptResult(
                session_id=session_id, question_id=question.id,
                selected_index=selected, is_correct=correct,
            )
            for question, (_, selected, correct) in zip(questions, answers)
        ],
    }


def _capture_downloads(monkeypatch) -> dict:
    download_args = {}

    def capture_download_button(label, **kwargs):
        download_args.clear()
        download_args.update(kwargs, label=label)

    monkeypatch.setattr(st, "download_button", capture_download_button)
    return download_args


def _rows(download_args: dict) -> list[list[str]]:
    return list(
        csv.reader(
            StringIO(download_args["data"].decode("utf-8"), newline=""),
            delimiter="\t",
        )
    )


# ---- Helpers that read the rendered page -------------------------------------

def _keyed_blocks(node) -> list[tuple[str, Block]]:
    found = []
    for child in node.children.values():
        if isinstance(child, Block):
            block_id = getattr(child.proto, "id", "") if child.proto is not None else ""
            if block_id:
                # Element IDs look like "$$ID-<hash>-<key>"; keys may contain "-".
                found.append((block_id.split("-", 2)[2], child))
            found += _keyed_blocks(child)
    return found


def _cards(app: AppTest) -> list[tuple[str, Block]]:
    return [(key, block) for key, block in _keyed_blocks(app.main) if key.startswith("flashcard_")]


def _card(app: AppTest) -> tuple[str, Block]:
    cards = _cards(app)
    assert len(cards) == 1, [key for key, _ in cards]
    return cards[0]


def _plain(markup: str) -> str:
    return html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", " ", markup))).strip()


def _card_text(app: AppTest) -> str:
    _, block = _card(app)
    parts = [item.value for item in block.caption]
    parts += [_plain(item.value) for item in block.markdown]
    return "\n".join(parts)


def _card_caption(app: AppTest) -> str:
    return _card(app)[1].caption[0].value


def _button(app: AppTest, name: str):
    return app.button(key=f"flashcards_{name}_{CID}")


def _decks(app: AppTest):
    return app.button_group(key=f"flashcards_deck_{CID}")


def _visible_texts(app: AppTest) -> list[str]:
    texts = [item.value for kind in ("title", "header", "subheader", "caption") for item in app.get(kind)]
    texts += [_plain(item.value) for item in app.markdown if not item.value.startswith("<style")]
    texts += [item.value for kind in ("info", "error", "warning", "success") for item in app.get(kind)]
    texts += [item.label for item in app.button]
    texts += [item.proto.label for item in app.get("download_button")]
    texts += [item.label for item in app.expander]
    for radio in app.radio:
        texts += [radio.label, *radio.options]
    for group in app.get("button_group"):
        texts += [group.label, *group.options]
    return texts


def _top_level_order(app: AppTest) -> list[str]:
    """Types (and keys, for keyed blocks) of the main area's top-level children."""
    order = []
    for child in app.main.children.values():
        block_id = getattr(child.proto, "id", "") if isinstance(child, Block) and child.proto is not None else ""
        order.append(block_id.split("-", 2)[2] if block_id else child.type)
    return order


# ---- Page structure ------------------------------------------------------------

def test_navigation_lists_the_page_as_flashcards(monkeypatch):
    from tests.test_paper_shell import sidebar_navigation

    visible, _, _ = sidebar_navigation(monkeypatch)
    page = next(page for page in visible if page.title == "Flashcards")

    assert page.url_path == "Flashcards"
    assert page.icon == ":material/style:"
    assert Path(page._page).name == "5_Export_Anki.py"
    assert "Export to Anki" not in [item.title for item in visible]


def test_page_is_flashcards_with_one_card_and_the_export_collapsed_at_the_bottom():
    course = _python_basics_course()
    app = _app_with_course(course)

    assert not app.exception
    assert [item.value for item in app.title] == ["Flashcards"]
    headings = [item.value for kind in ("title", "header", "subheader") for item in app.get(kind)]
    assert not any("Export to Anki" in heading for heading in headings)
    assert app.caption[0].value == "One card at a time, from your mistakes, weak topics and key ideas."

    key, card = _card(app)
    assert key == f"flashcard_none_{CID}"
    assert card.caption[0].value == "Card 1 of 9 · Variables and Expressions"
    front = _card_text(app)
    question = course.questions[0]
    assert question.question in front
    for letter, option in zip("ABCD", question.options):
        assert f"{letter}. {option}" in front
    assert "Think of your answer first, then flip the card." in front
    assert question.explanation not in front

    assert [(item.label, item.disabled) for item in app.button] == [
        ("Previous", True), ("Show answer", False), ("Next", False),
    ]
    assert _button(app, "flip").proto.type == "primary"

    # The export is one collapsed expander, below the card and its buttons.
    assert [item.label for item in app.expander] == ["Export to Anki"]
    export = app.expander[0]
    assert not export.proto.expanded
    assert len(export.get("download_button")) == 1
    assert export.get("download_button")[0].proto.label == "Download Anki TSV"
    order = _top_level_order(app)
    assert order.index(f"flashcard_none_{CID}") < order.index(f"flashcards_actions_{CID}") < order.index("expander")
    assert order[-1] == "expander"


def test_next_and_previous_move_one_card_and_extra_clicks_never_raise():
    app = _app_with_course(_python_basics_course())

    # Previous is disabled on card 1; a click that still arrives changes nothing.
    for _ in range(3):
        _button(app, "previous").click().run()
        assert not app.exception
    assert _card_caption(app).startswith("Card 1 of 9")

    _button(app, "next").click().run()
    assert _card_caption(app).startswith("Card 2 of 9")
    assert not _button(app, "previous").disabled
    _button(app, "previous").click().run()
    assert _card_caption(app).startswith("Card 1 of 9")

    for number in range(2, 10):
        _button(app, "next").click().run()
        assert not app.exception
        assert _card_caption(app).startswith(f"Card {number} of 9")
    assert _button(app, "next").label == "Start over"
    assert [item.label for item in app.button].count("Next") == 0

    _button(app, "next").click().run()
    assert not app.exception
    assert _card_caption(app).startswith("Card 1 of 9")
    assert _button(app, "next").label == "Next"
    assert _button(app, "previous").disabled
    assert len(_cards(app)) == 1


def test_flip_shows_the_answer_and_explanation_and_new_cards_start_on_the_front():
    course = _python_basics_course()
    app = _app_with_course(course)
    first, second = course.questions[0], course.questions[1]

    _button(app, "flip").click().run()
    assert not app.exception
    back = _card_text(app)
    assert "Answer" in back
    assert f"A. {first.options[0]}" in back  # correct_index 0
    assert first.explanation in back
    assert first.question in back
    assert f"B. {first.options[1]}" not in back
    assert "Last time" not in back  # not a mistake
    assert _button(app, "flip").label == "Show question"

    _button(app, "flip").click().run()
    front = _card_text(app)
    assert f"D. {first.options[3]}" in front
    assert first.explanation not in front
    assert _button(app, "flip").label == "Show answer"

    # Flip, then move: the next card shows its question first.
    _button(app, "flip").click().run()
    _button(app, "next").click().run()
    front = _card_text(app)
    assert second.question in front
    assert second.explanation not in front
    assert _button(app, "flip").label == "Show answer"
    _button(app, "flip").click().run()
    assert f"B. {second.options[1]}" in _card_text(app)  # correct_index 1
    _button(app, "previous").click().run()
    assert first.explanation not in _card_text(app)
    assert len(_cards(app)) == 1


def test_mistake_cards_remember_the_last_choice():
    course = _python_basics_course()
    app = _app_with_course(course)
    _add_answers(app, course, "s1", "mock", [(1, 2, False), (4, None, False), (7, 0, True)])
    app.run()

    assert not app.exception
    decks = _decks(app)
    assert decks.value == "mistakes"
    assert decks.options[0] == "My mistakes · 2"
    _button(app, "flip").click().run()
    assert "Last time you chose C." in _card_text(app)
    _button(app, "next").click().run()
    assert "Last time" not in _card_text(app)  # front
    _button(app, "flip").click().run()
    assert "Last time you left this blank." in _card_text(app)
    assert course.questions[3].explanation in _card_text(app)


# ---- Decks ---------------------------------------------------------------------

def test_without_history_ideas_and_all_questions_are_offered_with_a_note():
    app = _app_with_course(_python_basics_course())

    decks = _decks(app)
    assert decks.options == ["Key ideas · 3", "All questions · 9"]
    assert decks.value == "all"
    assert not app.selectbox
    assert "After some practice, your mistakes will appear here as their own deck." in [
        item.value for item in app.caption
    ]


def test_deck_choice_is_one_click_and_switching_returns_to_card_one_front():
    course = _python_basics_course()
    app = _app_with_course(course)
    first_topic = course.topics[0].id
    # Topic practice: 1 of 3 correct in the first topic -> weak, with two current mistakes.
    _add_history(app, course, "topic", first_topic, 1, "topic-weak")
    app.run()

    decks = _decks(app)
    assert decks.options == [
        "My mistakes · 2", "Weak topics · 3", "Key ideas · 3", "All questions · 9",
    ]
    assert decks.value == "mistakes"
    assert not app.selectbox
    assert not any("their own deck" in item.value for item in app.caption)

    _button(app, "next").click().run()
    _button(app, "flip").click().run()
    assert _card_caption(app).startswith("Card 2 of 2")

    _decks(app).set_value("all").run()
    assert not app.exception
    assert _decks(app).value == "all"
    assert _card_caption(app) == "Card 1 of 9 · Variables and Expressions"
    assert _button(app, "flip").label == "Show answer"
    assert course.questions[0].explanation not in _card_text(app)

    # Weak topics: current mistakes first, then course order.
    _decks(app).set_value("weak").run()
    assert _card_caption(app) == "Card 1 of 3 · Variables and Expressions"
    assert course.questions[1].question in _card_text(app)

    # Key ideas: the topic name on the front, its summary on the back.
    _decks(app).set_value("ideas").run()
    assert _card_caption(app) == "Card 1 of 3"
    front = _card_text(app)
    assert "Key idea" in front and course.topics[0].name in front
    assert "Recall what you know about this idea, then flip the card." in front
    assert course.topics[0].summary not in front
    _button(app, "flip").click().run()
    assert course.topics[0].summary in _card_text(app)

    # Clicking the chosen deck again does not leave the page without a deck.
    _decks(app).set_value(None).run()
    assert not app.exception
    assert _decks(app).value == "ideas"
    assert len(_cards(app)) == 1


def test_deck_choice_survives_count_changes_and_the_card_index_is_clamped():
    course = _python_basics_course()
    app = _app_with_course(course)
    _add_answers(app, course, "s1", "mock", [(1, 1, False), (2, 0, False), (3, 2, False)])
    app.run()
    assert _decks(app).options[0] == "My mistakes · 3"
    _button(app, "next").click().run()
    _button(app, "next").click().run()
    _button(app, "flip").click().run()
    assert _card_caption(app).startswith("Card 3 of 3")

    # Two of the three are answered correctly later: the deck shrinks to one card,
    # and the card now on screen is a different one, so it shows its front.
    _add_answers(app, course, "s2", "mock", [(3, 0, True), (2, 1, True)])
    app.run()
    assert not app.exception
    assert _decks(app).value == "mistakes"
    assert _decks(app).options[0] == "My mistakes · 1"
    assert _card_caption(app).startswith("Card 1 of 1")
    assert course.questions[0].question in _card_text(app)
    assert _button(app, "flip").label == "Show answer"
    assert _button(app, "previous").disabled
    assert _button(app, "next").label == "Start over"
    for _ in range(3):
        _button(app, "next").click().run()
        _button(app, "previous").click().run()
        assert not app.exception

    # The last mistake is fixed too: the empty deck disappears and another takes over.
    _add_answers(app, course, "s3", "mock", [(1, 0, True)])
    app.run()
    assert not app.exception
    assert not any(option.startswith("My mistakes") for option in _decks(app).options)
    assert _decks(app).value in {"weak", "all"}
    assert _card_caption(app).startswith("Card 1 of")


def test_the_default_deck_follows_new_mistakes_until_a_deck_is_picked():
    course = _python_basics_course()
    app = _app_with_course(course)
    assert _decks(app).value == "all"

    # New mistakes from practice: the page now opens on them.
    _add_answers(app, course, "s1", "mock", [(5, 0, False)])
    app.run()
    assert _decks(app).value == "mistakes"
    assert _card_caption(app) == "Card 1 of 1 · Conditionals"

    # A deck the student picked stays picked when more mistakes arrive.
    _decks(app).set_value("ideas").run()
    _add_answers(app, course, "s2", "mock", [(6, 0, False)])
    app.run()
    assert not app.exception
    assert _decks(app).value == "ideas"
    assert _decks(app).options[0] == "My mistakes · 2"


# ---- Animation keys --------------------------------------------------------------

def test_card_key_names_each_move_and_alternates_so_the_animation_replays():
    course = _python_basics_course()
    app = _app_with_course(course)

    def key() -> str:
        return _card(app)[0]

    assert key() == f"flashcard_none_{CID}"
    _button(app, "next").click().run()
    assert key() == f"flashcard_next_b_{CID}"
    _button(app, "next").click().run()
    assert key() == f"flashcard_next_a_{CID}"
    _button(app, "previous").click().run()
    assert key() == f"flashcard_prev_b_{CID}"
    _button(app, "previous").click().run()
    assert key() == f"flashcard_prev_a_{CID}"
    _button(app, "flip").click().run()
    assert key() == f"flashcard_flip_b_{CID}"
    _button(app, "flip").click().run()
    assert key() == f"flashcard_flip_a_{CID}"

    # Unrelated reruns keep the key, so nothing replays.
    app.run()
    assert key() == f"flashcard_flip_a_{CID}"
    app.radio[0].set_value("Weak Topics").run()
    assert key() == f"flashcard_flip_a_{CID}"

    # A deck switch shows card 1 without a page turn.
    _decks(app).set_value("ideas").run()
    assert key() == f"flashcard_none_{CID}"
    _button(app, "flip").click().run()
    assert key().startswith("flashcard_flip_")

    # Leaving the page and coming back shows the card without replaying the flip.
    app.session_state["current_course"] = None
    app.run()
    assert not _cards(app)
    app.session_state["current_course"] = course
    app.run()
    assert key() == f"flashcard_none_{CID}"
    assert _decks(app).value == "ideas"
    assert course.topics[0].summary in _card_text(app)  # still showing the back


def test_stylesheet_animates_moves_with_distinct_keyframes_and_respects_reduced_motion():
    from services import ui_style

    css = (ROOT / "assets" / "paper_flashcards.css").read_text(encoding="utf-8")
    assert ROOT / "assets" / "paper_flashcards.css" in ui_style.paper_stylesheets()

    def rule(selector: str) -> str:
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert match, selector
        return match.group(1)

    for move in ("next", "prev", "flip"):
        names = []
        for marker in ("a", "b"):
            body = rule(f'[data-testid="stMain"] [class*="st-key-flashcard_{move}_{marker}_"]')
            name = re.search(r"animation:\s*(flashcard-[\w-]+)", body).group(1)
            assert name == f"flashcard-{move}-{marker}"
            names.append(name)
        assert names[0] != names[1]
        frames = [
            re.search(r"@keyframes " + name + r"\s*\{(.*?)\n\}", css, re.DOTALL).group(1)
            for name in names
        ]
        assert frames[0] == frames[1]
        assert "perspective(" in frames[0] and "rotate" in frames[0]
    assert "flashcard_none_" not in re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    reduced = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    assert "animation: none" in reduced.split("}\n}")[0]
    for token in ("--paper-card", "--paper-line", "--font-title", "--ink-muted", "--accent-rust"):
        assert f"var({token}" in css
    narrow = css[css.index("@media (max-width: 759.98px)"):]
    assert "st-key-flashcards_actions_" in narrow and "min-width: 0" in narrow


# ---- Export (unchanged content) ------------------------------------------------------

def test_download_payload_is_utf8_tsv_with_safe_filename_and_mime(monkeypatch):
    course = _python_basics_course()
    course.course_name = "../Python Basics/Intro"
    course.questions[0].question = "What is café?"
    download_args = _capture_downloads(monkeypatch)
    app = _app_with_course(course)

    assert not app.exception
    content = download_args["data"]
    assert isinstance(content, bytes)
    assert content == export_anki_tsv(course).encode("utf-8")
    assert "café" in content.decode("utf-8")
    assert len(_rows(download_args)) == 9
    assert download_args["label"] == "Download Anki TSV"
    assert download_args["file_name"] == "anki_python_basics_intro.tsv"
    assert download_args["mime"] == "text/tab-separated-values; charset=utf-8"
    assert "9 cards · All Questions" in [item.value for item in app.caption]


def test_weak_topics_filter_uses_selected_mode_only(monkeypatch):
    download_args = _capture_downloads(monkeypatch)
    course = _python_basics_course()
    app = _app_with_course(course)
    first_topic = course.topics[0].id
    second_topic = course.topics[1].id
    _add_history(app, course, "mock", first_topic, 0, "mock-weak")
    _add_history(app, course, "topic", first_topic, 3, "topic-mastered")
    _add_history(app, course, "topic", second_topic, 2, "topic-developing")
    app.run()

    app.radio[0].set_value("Weak Topics").run()
    assert not app.exception
    exported_rows = _rows(download_args)
    assert len(exported_rows) == 3
    assert all(row[2].endswith(f"topic_{first_topic}") for row in exported_rows)
    assert download_args["data"] == export_anki_tsv(course, topic_ids={first_topic}).encode("utf-8")
    assert len(_cards(app)) == 1

    app.radio[1].set_value("Topic Practice").run()
    assert not app.exception
    exported_rows = _rows(download_args)
    assert len(exported_rows) == 3
    assert all(row[2].endswith(f"topic_{second_topic}") for row in exported_rows)
    assert download_args["data"] == export_anki_tsv(course, topic_ids={second_topic}).encode("utf-8")
    assert len(_cards(app)) == 1


def test_course_history_and_filter_state_are_isolated(monkeypatch):
    download_args = _capture_downloads(monkeypatch)
    first = _python_basics_course()
    second = first.model_copy(
        update={"course_id": "different-course", "course_name": "Other course"}
    )
    app = _app_with_course(first)
    _add_history(app, first, "mock", first.topics[0].id, 0, "first-weak")
    _add_history(app, second, "mock", second.topics[1].id, 0, "second-weak")
    app.session_state["anki_export_scope_different-course"] = "Weak Topics"
    app.session_state["current_course"] = second
    app.run()

    assert not app.exception
    assert app.session_state["anki_export_scope_different-course"] == "Weak Topics"
    assert [radio.value for radio in app.radio] == ["Weak Topics", "Mock Exam"]
    rows = _rows(download_args)
    assert len(rows) == 3
    assert all(
        row[2].endswith(f"topic_{second.topics[1].id}") for row in rows
    )
    # Review state is kept per course too.
    assert "flashcards_different-course" in app.session_state
    assert [key for key, _ in _cards(app)] == ["flashcard_none_different-course"]


def test_no_course_shows_empty_state_and_no_download():
    app = _app_with_course()

    assert not app.exception
    assert "Load a course from the dashboard first." in [
        item.value for item in app.info
    ]
    assert len(app.get("download_button")) == 0
    assert not _cards(app)


def test_course_without_questions_shows_empty_state_and_no_download():
    course = StudyPackage(
        course_id="empty",
        course_name="Empty course",
        topics=[],
        relationships=[],
        questions=[],
    )
    app = _app_with_course(course)

    assert not app.exception
    assert "This course has no questions to review yet." in [
        item.value for item in app.info
    ]
    assert len(app.get("download_button")) == 0
    assert not _cards(app)


def test_no_weak_topics_message_stays_in_the_export_and_the_card_still_shows():
    app = _app_with_course(_python_basics_course())
    app.radio[0].set_value("Weak Topics").run()

    assert not app.exception
    export = app.expander[0]
    assert "No weak or developing topics in this practice mode." in [
        item.value for item in export.info
    ]
    assert len(app.get("download_button")) == 0
    assert len(_cards(app)) == 1
    assert [item.label for item in app.button] == ["Previous", "Show answer", "Next"]


def test_weak_topic_without_course_questions_shows_no_matching_state():
    course = _python_basics_course()
    app = _app_with_course(course)
    old_questions = [
        course.questions[0].model_copy(
            update={
                "id": f"removed-question-{index}",
                "topic_id": "removed-topic",
            }
        )
        for index in range(3)
    ]
    session = ExamSession(
        session_id="removed-session",
        mode="mock",
        question_ids=[question.id for question in old_questions],
    )
    attempts = [
        AttemptResult(
            session_id=session.session_id,
            question_id=question.id,
            selected_index=0,
            is_correct=False,
        )
        for question in old_questions
    ]
    app.session_state[f"practice_history_{course.course_id}"] = {
        session.session_id: {
            "session": session,
            "attempts": attempts,
            "questions": old_questions,
        }
    }
    app.run()
    app.radio[0].set_value("Weak Topics").run()

    assert not app.exception
    assert "No questions match the weak or developing topics." in [
        item.value for item in app.expander[0].info
    ]
    assert len(app.get("download_button")) == 0
    assert len(_cards(app)) == 1


def test_unreadable_history_breaks_neither_the_card_nor_the_page():
    course = _python_basics_course()
    app = _app_with_course(course)
    _add_answers(app, course, "s1", "mock", [(1, 2, False)])
    # The attempt names a question that is not part of its session.
    _history(app, course)["s1"]["session"] = ExamSession(session_id="s1", mode="mock", question_ids=["other"])
    app.run()
    app.radio[0].set_value("Weak Topics").run()

    assert not app.exception
    assert [item.value for item in app.expander[0].error] == [
        "Couldn't find your weak topics from this practice history."
    ]
    assert len(_cards(app)) == 1
    assert _decks(app).value == "mistakes"
    assert not any(option.startswith("Weak topics") for option in _decks(app).options)


# ---- Wording ------------------------------------------------------------------------

def _walk_every_card(app: AppTest) -> list[str]:
    """Visible texts of both sides of every card in every deck."""
    texts = []
    for position, deck in enumerate(_deck_values(app)):
        _decks(app).set_value(deck).run()
        total = int(_decks(app).options[position].rsplit(" · ", 1)[1])
        for _ in range(total):
            texts += _visible_texts(app)
            _button(app, "flip").click().run()
            texts += _visible_texts(app)
            _button(app, "next").click().run()
            assert not app.exception
    return texts


def _deck_values(app: AppTest) -> list[str]:
    labels = {
        "My mistakes": "mistakes", "Weak topics": "weak", "Key ideas": "ideas", "All questions": "all",
        "我的错题": "mistakes", "薄弱知识点": "weak", "知识点": "ideas", "全部题目": "all",
    }
    return [labels[option.rsplit(" · ", 1)[0]] for option in _decks(app).options]


def _with_mistakes_and_weak_topics(chinese: bool = False) -> tuple[AppTest, StudyPackage]:
    course = _python_basics_course()
    app = _app_with_course(course, chinese=chinese)
    _add_answers(app, course, "s1", "topic", [(1, 2, False), (2, None, False), (3, 0, True)])
    app.run()
    return app, course


def test_no_internal_ids_tags_or_status_words_are_visible():
    app, course = _with_mistakes_and_weak_topics()
    texts = _walk_every_card(app)
    app.radio[0].set_value("Weak Topics").run()
    texts += _visible_texts(app)

    assert texts
    blob = "\n".join(texts)
    for identifier in [course.course_id, *(t.id for t in course.topics), *(q.id for q in course.questions)]:
        assert identifier not in blob
    assert "topic_" not in blob and "course_" not in blob
    for word in ("legacy", "approved", "pending", "flagged", "superseded", "unattempted", "insufficient"):
        assert not re.search(rf"\b{word}\b", blob, re.IGNORECASE), word


@pytest.mark.parametrize("chinese,expected", [
    (False, ["Flashcards", "Previous", "Show answer", "Next", "Export to Anki"]),
    (True, ["复习卡片", "上一题", "看答案", "下一题", "导出到 Anki"]),
])
def test_main_labels_follow_the_interface_language(chinese, expected):
    app = _app_with_course(_python_basics_course(), chinese=chinese)

    assert not app.exception
    title, previous, flip, following, export = expected
    assert app.title[0].value == title
    assert [item.label for item in app.button] == [previous, flip, following]
    assert app.expander[0].label == export


def test_chinese_interface_translates_every_flashcard_string():
    app, course = _with_mistakes_and_weak_topics(chinese=True)

    assert not app.exception
    assert app.title[0].value == "复习卡片"
    assert app.caption[0].value == "一次一张卡片，复习你的错题、薄弱知识点和知识点。"
    assert _decks(app).options == ["我的错题 · 2", "薄弱知识点 · 3", "知识点 · 3", "全部题目 · 9"]
    assert _card_caption(app) == "第 1 / 2 张 · Variables and Expressions"
    assert "先想好答案，再翻开卡片。" in _card_text(app)
    _button(app, "flip").click().run()
    back = _card_text(app)
    assert "答案" in back and "上次你选了 C。" in back
    assert _button(app, "flip").label == "看题目"
    _button(app, "next").click().run()
    assert _button(app, "next").label == "从头再来"
    _button(app, "flip").click().run()
    assert "上次你没有作答。" in _card_text(app)
    _decks(app).set_value("ideas").run()
    assert _card_caption(app) == "第 1 / 3 张"
    assert "知识点" in _card_text(app)
    assert "先回想你对这个知识点的了解，再翻开卡片。" in _card_text(app)

    empty = _app_with_course(_python_basics_course(), chinese=True)
    assert "练习之后，你的错题会单独成组，出现在这里。" in [item.value for item in empty.caption]
    no_questions = _app_with_course(
        StudyPackage(course_id="empty", course_name="Empty", topics=[], relationships=[], questions=[]),
        chinese=True,
    )
    assert [item.value for item in no_questions.info] == ["此课程还没有可复习的题目。"]


def test_chinese_interface_shows_no_english_interface_text():
    app, course = _with_mistakes_and_weak_topics(chinese=True)
    texts = _walk_every_card(app)
    app.radio[0].set_value("薄弱知识点").run()
    texts += _visible_texts(app)

    content = [course.course_name]
    for topic in course.topics:
        content += [topic.name, topic.summary]
    for question in course.questions:
        content += [question.question, question.explanation, *question.options]
    content.sort(key=len, reverse=True)
    # Anki's own field and file names stay as they are in the Chinese wording.
    allowed = {"Anki", "AnkiWeb", "TSV", "Front", "Back", "Tags"}
    leftovers = set()
    for text in texts:
        for piece in content:
            text = text.replace(piece, " ")
        leftovers |= set(re.findall(r"[A-Za-z]{2,}", text)) - allowed
    assert not leftovers
