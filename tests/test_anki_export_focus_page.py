"""Export to Anki (pages/11_Anki_Export.py): the Flashcards download on a page of its own."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block as BlockProto
from streamlit.testing.v1 import AppTest

from models.schemas import AttemptResult, ExamSession, StudyPackage
from services.anki_export_service import export_anki_tsv
from services.anki_export_ui import safe_filename
from services.i18n import LANGUAGE_KEY
from tests.test_anki_export_page import (
    CID,
    _add_answers,
    _add_history,
    _assert_no_internal_words,
    _capture_downloads,
    _english_leftovers,
    _history,
    _keyed_blocks,
    _python_basics_course,
    _rows,
    _top_level_order,
    _visible_texts,
)


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "pages" / "11_Anki_Export.py"
MIME = "text/tab-separated-values; charset=utf-8"


def _export_app(course: StudyPackage | None = None, chinese: bool = False) -> AppTest:
    app = AppTest.from_file(str(EXPORT_PATH))
    if course is not None:
        app.session_state["current_course"] = course
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    return app.run()


# ---- Page structure ------------------------------------------------------------

def test_page_has_the_way_back_the_title_and_only_the_export(monkeypatch):
    destinations = []
    monkeypatch.setattr(st, "switch_page", lambda page: destinations.append(page))
    app = _export_app(_python_basics_course())

    assert not app.exception
    assert [item.value for item in app.title] == ["Export to Anki"]
    # Back button first (top-left), then the title, then the export itself.
    order = [entry for entry in _top_level_order(app) if entry != "markdown"][:2]
    assert order == ["page_link_anki_export_back", "title"]
    holder = dict(_keyed_blocks(app.main))["page_link_anki_export_back"].proto.flex_container
    assert holder.justify == BlockProto.FlexContainer.Justify.JUSTIFY_START
    back = app.button(key="anki_export_back")
    assert back.label == "Back to Flashcards"
    assert back.proto.icon == ":material/arrow_back:"

    assert [item.label for item in app.button] == ["Back to Flashcards"]
    assert [radio.label for radio in app.radio] == ["Questions to export"]
    assert [item.proto.label for item in app.get("download_button")] == ["Download Anki TSV"]
    assert "9 cards · All Questions" in [item.value for item in app.caption]
    assert any(
        item.value.startswith("Download the file, then in Anki") for item in app.markdown
    )
    # Nothing from the Flashcards page.
    assert not app.expander and not app.get("button_group")
    assert not [key for key, _ in _keyed_blocks(app.main) if key.startswith("flashcard")]

    back.click().run()
    assert destinations == ["pages/5_Export_Anki.py"]


def test_app_registers_the_page_as_a_hidden_focus_page(monkeypatch):
    from tests.test_paper_shell import sidebar_navigation

    visible, hidden, _ = sidebar_navigation(monkeypatch)
    page = next(page for page in hidden if page.url_path == "Anki_Export")

    assert page.title == "Export to Anki"
    assert Path(page._page).resolve() == EXPORT_PATH.resolve()
    assert "Export to Anki" not in [item.title for item in visible]


# ---- The download (same as the Flashcards expander produced) -------------------------

def test_download_payload_is_utf8_tsv_with_safe_filename_and_mime(monkeypatch):
    course = _python_basics_course()
    course.course_name = "../Python Basics/Intro"
    course.questions[0].question = "What is café?"
    download_args = _capture_downloads(monkeypatch)
    app = _export_app(course)

    assert not app.exception
    content = download_args["data"]
    assert isinstance(content, bytes)
    assert content == export_anki_tsv(course).encode("utf-8")
    assert "café" in content.decode("utf-8")
    assert len(_rows(download_args)) == 9
    assert download_args["label"] == "Download Anki TSV"
    assert download_args["file_name"] == "anki_python_basics_intro.tsv"
    assert download_args["mime"] == MIME
    assert "9 cards · All Questions" in [item.value for item in app.caption]


def test_safe_filename_is_unchanged():
    assert safe_filename("../Python Basics/Intro") == "anki_python_basics_intro.tsv"
    assert safe_filename("  ") == "anki_course.tsv"
    assert safe_filename("微积分") == "anki_course.tsv"
    assert safe_filename("x" * 100) == f"anki_{'x' * 80}.tsv"


def test_download_works_with_no_practice_history(monkeypatch):
    course = _python_basics_course()
    download_args = _capture_downloads(monkeypatch)
    app = _export_app(course)

    assert not app.exception
    assert f"practice_history_{CID}" not in app.session_state
    assert download_args["data"] == export_anki_tsv(course).encode("utf-8")
    assert download_args["file_name"] == "anki_python_basics.tsv"


def test_weak_topics_filter_uses_selected_mode_only(monkeypatch):
    download_args = _capture_downloads(monkeypatch)
    course = _python_basics_course()
    app = _export_app(course)
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
    assert download_args["mime"] == MIME
    assert "3 cards · Weak Topics" in [item.value for item in app.caption]

    app.radio[1].set_value("Topic Practice").run()
    assert not app.exception
    exported_rows = _rows(download_args)
    assert len(exported_rows) == 3
    assert all(row[2].endswith(f"topic_{second_topic}") for row in exported_rows)
    assert download_args["data"] == export_anki_tsv(course, topic_ids={second_topic}).encode("utf-8")


def test_choices_made_before_still_apply(monkeypatch):
    download_args = _capture_downloads(monkeypatch)
    course = _python_basics_course()
    app = AppTest.from_file(str(EXPORT_PATH))
    app.session_state["current_course"] = course
    _add_history(app, course, "topic", course.topics[2].id, 0, "topic-weak")
    # The same session keys the export has always used.
    app.session_state[f"anki_export_scope_{CID}"] = "Weak Topics"
    app.session_state[f"anki_export_mode_{CID}"] = "Topic Practice"
    app.run()

    assert not app.exception
    assert [radio.key for radio in app.radio] == [f"anki_export_scope_{CID}", f"anki_export_mode_{CID}"]
    assert [radio.value for radio in app.radio] == ["Weak Topics", "Topic Practice"]
    assert download_args["data"] == export_anki_tsv(
        course, topic_ids={course.topics[2].id},
    ).encode("utf-8")


def test_course_history_and_filter_state_are_isolated(monkeypatch):
    download_args = _capture_downloads(monkeypatch)
    first = _python_basics_course()
    second = first.model_copy(
        update={"course_id": "different-course", "course_name": "Other course"}
    )
    app = _export_app(first)
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
    assert download_args["file_name"] == "anki_other_course.tsv"


# ---- Messages on the page ------------------------------------------------------------

def test_no_course_shows_empty_state_and_no_download():
    app = _export_app()

    assert not app.exception
    assert [item.value for item in app.info] == ["Load a course from the dashboard first."]
    assert len(app.get("download_button")) == 0
    assert app.button(key="anki_export_back").label == "Back to Flashcards"


def test_course_without_questions_shows_empty_state_and_no_download():
    course = StudyPackage(
        course_id="empty",
        course_name="Empty course",
        topics=[],
        relationships=[],
        questions=[],
    )
    app = _export_app(course)

    assert not app.exception
    assert [item.value for item in app.info] == ["This course has no questions to export."]
    assert len(app.get("download_button")) == 0
    assert not app.radio


def test_no_weak_topics_shows_a_message_and_no_download():
    app = _export_app(_python_basics_course())
    app.radio[0].set_value("Weak Topics").run()

    assert not app.exception
    assert [item.value for item in app.info] == ["No weak or developing topics in this practice mode."]
    assert len(app.get("download_button")) == 0


def test_weak_topic_without_course_questions_shows_no_matching_state():
    course = _python_basics_course()
    app = _export_app(course)
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
    assert [item.value for item in app.info] == ["No questions match the weak or developing topics."]
    assert len(app.get("download_button")) == 0


def test_unreadable_history_shows_an_error_on_the_page():
    course = _python_basics_course()
    app = _export_app(course)
    _add_answers(app, course, "s1", "mock", [(1, 2, False)])
    # The attempt names a question that is not part of its session.
    _history(app, course)["s1"]["session"] = ExamSession(session_id="s1", mode="mock", question_ids=["other"])
    app.run()
    assert not app.exception
    assert len(app.get("download_button")) == 1  # All Questions needs no history

    app.radio[0].set_value("Weak Topics").run()
    assert not app.exception
    assert [item.value for item in app.error] == [
        "Couldn't find your weak topics from this practice history."
    ]
    assert len(app.get("download_button")) == 0


# ---- Wording ------------------------------------------------------------------------

def _texts_for_every_choice(app: AppTest, weak_label: str, topic_label: str) -> list[str]:
    texts = _visible_texts(app)
    app.radio[0].set_value(weak_label).run()
    texts += _visible_texts(app)
    app.radio[1].set_value(topic_label).run()
    texts += _visible_texts(app)
    return texts


def _with_weak_history(chinese: bool = False) -> tuple[AppTest, StudyPackage]:
    course = _python_basics_course()
    app = _export_app(course, chinese=chinese)
    _add_history(app, course, "topic", course.topics[0].id, 1, "topic-weak")
    app.run()
    return app, course


def test_no_internal_ids_tags_or_status_words_are_visible():
    app, course = _with_weak_history()

    _assert_no_internal_words(_texts_for_every_choice(app, "Weak Topics", "Topic Practice"), course)


@pytest.mark.parametrize("chinese,expected", [
    (False, ["Back to Flashcards", "Export to Anki", "Questions to export", "Download Anki TSV", "9 cards · All Questions"]),
    (True, ["返回复习卡片", "导出到 Anki", "导出的题目", "下载 Anki TSV", "9 张卡片 · 全部题目"]),
])
def test_labels_follow_the_interface_language(chinese, expected):
    app = _export_app(_python_basics_course(), chinese=chinese)

    assert not app.exception
    back, title, scope, download, summary = expected
    assert app.button(key="anki_export_back").label == back
    assert app.title[0].value == title
    assert app.radio[0].label == scope
    assert app.get("download_button")[0].proto.label == download
    assert summary in [item.value for item in app.caption]


def test_chinese_interface_shows_no_english_interface_text():
    app, course = _with_weak_history(chinese=True)
    texts = _texts_for_every_choice(app, "薄弱知识点", "知识点练习")
    for chinese_course in (None, StudyPackage(course_id="empty", course_name="Empty", topics=[], relationships=[], questions=[])):
        texts += _visible_texts(_export_app(chinese_course, chinese=True))

    assert "返回复习卡片" in texts and "导出到 Anki" in texts
    assert _english_leftovers(texts, course) == set()
