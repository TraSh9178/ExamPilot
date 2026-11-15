"""Example report on the built-in demo courses: deterministic, labelled, never stored or mixed."""

import html
import re
from copy import deepcopy
from pathlib import Path

import pytest

from models.schemas import ExamSession, StudyPackage
from services.demo_updates import FILES
from services.example_report import build_example_report, example_report_for, has_real_practice
from services.exam_engine import grade_exam
from services.i18n import LANGUAGE_KEY
from services.learning_dna import MIN_EVIDENCE, evidence_profile
from services.mastery_engine import calculate_topic_stats, get_mastery_status
from tests.test_progress_charts import (
    LATIN,
    bar_rows,
    chart,
    charts,
    chart_course_and_history,
    course_strings,
    interface_strings,
    progress_app,
    session_values,
    visible_text,
)

ROOT = Path(__file__).resolve().parents[1]
DEMOS = sorted(FILES.items())
BANNER = "Example report · These numbers are sample data. Finish a practice session to see your own."


def demo(filename):
    return StudyPackage.model_validate_json((ROOT / "data" / filename).read_text(encoding="utf-8"))


def stats_for(report, mode):
    sessions = [record["session"] for record in report.history.values()]
    attempts = [a for record in report.history.values() for a in record["attempts"]]
    return {
        item.topic_id: item
        for item in calculate_topic_stats(attempts, sessions, report.course.questions)
        if item.mode == mode
    }


def page_texts(app):
    """Everything the page draws, including chart labels, as one string (style sheet excepted)."""
    parts = [element.value for element in [*app.title, *app.subheader, *app.caption, *app.info]]
    parts += [m.value for m in app.markdown if not m.value.startswith("<style")]
    parts += [f"{metric.label} {metric.value}" for metric in app.metric]
    parts += [button.label for button in app.button] + [e.label for e in app.expander]
    return html.unescape(" ".join(parts))


def real_session(course, mode, count=2, session_id="real-1"):
    questions = [q for q in course.questions if q.topic_id == course.topics[0].id][:count]
    session = ExamSession(session_id=session_id, mode=mode, question_ids=[q.id for q in questions])
    result = grade_exam(session, questions, {q.id: q.correct_index for q in questions})
    return {session_id: {"session": session, "questions": questions, "attempts": result["attempts"],
                         "result": result}}


# ---- The example itself -------------------------------------------------------------------


@pytest.mark.parametrize("course_id,filename", DEMOS)
def test_example_is_deterministic_and_built_from_the_course(course_id, filename):
    course = demo(filename)
    first, second = build_example_report(course), build_example_report(demo(filename))
    assert first == second
    assert first.course is not course and first.course.course_id == course_id
    question_ids = {q.id for q in course.questions}
    for sid, record in first.history.items():
        assert sid.startswith("example-") and record["session"].session_id == sid
        assert set(record["session"].question_ids) <= question_ids
        assert [a.question_id for a in record["attempts"]] == record["session"].question_ids
    assert first.course.learning_state["session_order"] == list(first.history)
    # Questions still awaiting review are used too (only aggregates are shown).
    pending = {qid for qid, status in course.learning_state["question_reviews"].items() if status == "pending"}
    used = {qid for record in first.history.values() for qid in record["session"].question_ids}
    assert used & pending


@pytest.mark.parametrize("course_id,filename", DEMOS)
def test_example_covers_statuses_both_dimensions_time_and_both_modes(course_id, filename):
    report = build_example_report(demo(filename))
    sessions = [record["session"] for record in report.history.values()]
    attempts = [a for record in report.history.values() for a in record["attempts"]]
    for mode in ("mock", "topic"):
        assert [s for s in sessions if s.mode == mode], mode
        statuses = {get_mastery_status(item) for item in stats_for(report, mode).values()}
        assert len(statuses) >= 3, (mode, statuses)
        assert "insufficient_evidence" in statuses or mode == "mock"
        profile, _ = evidence_profile(attempts, sessions, report.course.questions, mode)
        for dimension in ("computation", "conceptual"):
            shown = [p for p in profile if p.dimension == dimension and p.count >= MIN_EVIDENCE]
            assert shown, (mode, dimension)
            assert len([p for p in profile if p.dimension == dimension and p.count]) >= 2
    mock = {get_mastery_status(item) for item in stats_for(report, "mock").values()}
    assert {"mastered", "developing", "weak"} <= mock
    # Some topics show more answers than different questions (a retried question).
    assert any(item.attempted > item.unique_attempted for item in stats_for(report, "mock").values())
    insights = report.course.learning_state["practice_insights"]
    for sid, record in report.history.items():
        assert set(insights[sid]) == set(record["session"].question_ids)
        assert all(row["focus_seconds"] > 0 for row in insights[sid].values())


def test_example_only_for_built_in_demos_without_real_practice():
    course = demo("calculus_i_demo.json")
    assert example_report_for(course, {}) == build_example_report(course)
    assert example_report_for(course, None) is not None
    assert example_report_for(course, real_session(course, "topic")) is None
    restored = course.model_copy(update={"learning_state": {**course.learning_state, "session_order": ["s"]}})
    assert has_real_practice(restored, {}) and example_report_for(restored, {}) is None
    other, _ = chart_course_and_history()
    other.learning_state.clear()
    assert example_report_for(other, {}) is None


@pytest.mark.parametrize("course_id,filename", DEMOS)
def test_building_the_example_changes_nothing_in_the_course(course_id, filename):
    course = demo(filename)
    before = course.model_dump(mode="json")
    state_before = deepcopy(course.learning_state)
    report = build_example_report(course)
    assert course.model_dump(mode="json") == before and course.learning_state == state_before
    assert "practice_insights" not in course.learning_state and "session_order" not in course.learning_state
    report.course.learning_state["session_order"].append("x")
    assert "session_order" not in course.learning_state


# ---- The page ----------------------------------------------------------------------------


@pytest.mark.parametrize("course_id,filename", DEMOS)
def test_demo_without_practice_shows_the_labelled_example(course_id, filename):
    course = demo(filename)
    before = course.model_dump(mode="json")
    app = progress_app(course)
    assert not app.exception
    markdown = [m.value for m in app.markdown if not m.value.startswith("<style")]
    assert visible_text(next(m for m in markdown if "progress-example-banner" in m)) == BANNER
    # The banner comes before the mode choice and the tiles.
    assert markdown.index(next(m for m in markdown if "progress-example-banner" in m)) == 0
    headings = [s.value for s in app.subheader][1:]
    assert headings == ["Example · Mastery by topic", "Example · Accuracy by session",
                        "Example · Learning DNA", "Example · Time by topic"]
    # No per-question tables: no evidence, no review list.
    assert not app.dataframe and not app.expander
    assert "Your next review" not in headings
    assert not [info.value for info in app.info]

    report = build_example_report(course)
    mock_ids = [sid for sid in report.history if report.history[sid]["session"].mode == "mock"]
    mock_attempts = [a for sid in mock_ids for a in report.history[sid]["attempts"]]
    tiles = {metric.label: metric.value for metric in app.metric}
    assert tiles == {
        "Graded practice sessions": str(len(mock_ids)),
        "Answers": str(len(mock_attempts)),
        "Accuracy": f"{100 * sum(a.is_correct for a in mock_attempts) / len(mock_attempts):.2f}%",
    }
    stats = stats_for(report, "mock")
    rows = bar_rows(chart(app, "mastery"))
    assert [row["chip"] for row in rows] == [
        {"unattempted": "Unattempted", "insufficient_evidence": "Insufficient evidence", "weak": "Weak",
         "developing": "Developing", "mastered": "Mastered"}[get_mastery_status(stats[t.id])]
        for t in course.topics
    ]
    assert session_values(chart(app, "sessions")) == [
        round(100 * sum(a.is_correct for a in report.history[sid]["attempts"]) / len(report.history[sid]["attempts"]))
        for sid in mock_ids
    ]
    assert len(charts(app, "dna")) == len(course.topics) and chart(app, "time")
    for kind in ("mastery", "sessions", "time"):
        assert re.search(r'aria-label="Example · ', chart(app, kind))

    # Nothing was written anywhere.
    assert app.session_state["current_course"].model_dump(mode="json") == before
    assert course.model_dump(mode="json") == before
    state = app.session_state.filtered_state
    assert f"practice_history_{course_id}" not in state
    assert set(state) == {"current_course", f"performance_mode_{course_id}"}
    assert "example-" not in repr(state)


def test_example_switches_modes_and_still_reads_as_example():
    course = demo("sample_course.json")
    app = progress_app(course)
    app.radio(key="performance_mode_econ101").set_value("Topic Practice").run()
    assert not app.exception
    report = build_example_report(course)
    stats = stats_for(report, "topic")
    rows = bar_rows(chart(app, "mastery"))
    assert [row["value"] for row in rows if row["fill"] is not None] == [
        f"{stats[t.id].evidence_accuracy:.0f}%" for t in course.topics
        if get_mastery_status(stats[t.id]) in {"weak", "developing", "mastered"}
    ]
    assert all(s.value.startswith("Example · ") for s in app.subheader[1:])
    assert not app.dataframe and not app.expander


@pytest.mark.parametrize("real_mode,viewed", [
    ("topic", "Mock Exam"), ("topic", "Topic Practice"), ("mock", "Mock Exam"), ("mock", "Topic Practice"),
])
def test_one_real_session_removes_every_trace_of_the_example(real_mode, viewed):
    course = demo("calculus_i_demo.json")
    history = real_session(course, real_mode)
    app = progress_app(course, deepcopy(history), mode=viewed)
    assert not app.exception
    text = page_texts(app)
    assert "Example" not in text and "sample data" not in text and "example-" not in text
    assert "progress-example-banner" not in text
    real = real_mode == ("mock" if viewed == "Mock Exam" else "topic")
    tiles = {metric.label: metric.value for metric in app.metric}
    assert tiles["Graded practice sessions"] == ("1" if real else "0")
    assert tiles["Answers"] == ("2" if real else "0")
    assert tiles["Accuracy"] == ("100.00%" if real else "—")
    rows = bar_rows(chart(app, "mastery"))
    if real:
        assert rows[0]["value"] == "2 different questions" and rows[0]["chip"] == "Insufficient evidence"
        assert all(row["value"] == "0 answers" for row in rows[1:])
        assert session_values(chart(app, "sessions")) == [100]
    else:
        assert all(row["value"] == "0 answers" and row["chip"] == "Unattempted" for row in rows)
        assert "No graded sessions in this mode yet." in visible_text(chart(app, "sessions"))
    # Only the real answers count: no example tracked time either.
    assert not charts(app, "time")
    for markup in charts(app, "dna"):
        assert all(row["fill"] is None for row in bar_rows(markup))
    assert app.session_state[f"practice_history_{course.course_id}"] == history


def test_restored_chronology_without_loaded_history_shows_no_example():
    course = demo("sample_course.json")
    course.learning_state["session_order"] = ["saved-session"]
    app = progress_app(course)
    assert not app.exception
    assert "Example" not in page_texts(app)


def test_custom_course_never_shows_the_example():
    course, _ = chart_course_and_history()
    course.learning_state.clear()
    app = progress_app(course)
    assert not app.exception
    assert "Example" not in page_texts(app)
    assert [info.value for info in app.info] == [
        "No graded practice sessions yet. Your topic list will update after you complete a practice session."
    ]


@pytest.mark.parametrize("filename", ["sample_course.json", "calculus_i_demo.json"])
def test_chinese_example_shows_no_english_interface_text(filename):
    course = demo(filename)
    app = progress_app(course, chinese=True)
    assert not app.exception
    collected = interface_strings(app, course_strings(course))
    assert "示例报告 · 这些数字是示例数据。完成一次练习后就会显示你自己的结果。" in collected
    assert [s.value for s in app.subheader][1:] == [
        "示例 · 各知识点掌握情况", "示例 · 各次练习正确率", "示例 · 学习画像", "示例 · 各知识点用时",
    ]
    assert [text for text in collected if LATIN.search(text)] == []
    app.radio(key=f"performance_mode_{course.course_id}").set_value("知识点练习").run()
    assert not app.exception
    assert [text for text in interface_strings(app, course_strings(course)) if LATIN.search(text)] == []
    assert app.session_state[LANGUAGE_KEY] is True
