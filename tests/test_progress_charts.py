"""Progress page charts: markup, numbers from the existing calculations, layout and wording."""

import ast
import html
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from components import progress_charts
from components.progress_charts import (
    BarRow,
    SessionPoint,
    bar_chart_html,
    dna_rows,
    duration_text,
    example_banner_html,
    mastery_rows,
    session_chart_html,
    session_points,
    time_rows,
)
from models.schemas import Question, StudyPackage
from services.exam_engine import grade_exam
from services.i18n import LANGUAGE_KEY, _DYNAMIC, _TRANSLATIONS
from services.learning_dna import evidence_profile
from services.mastery_engine import calculate_topic_stats, get_mastery_status
from services.practice_insights import set_session_insights

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "3_Performance.py"
CSS = ROOT / "assets" / "paper_progress.css"
COURSE_ID = "chart-course"
TOPICS = [("rates", "Rates & <Ratios>"), ("limits", "Limits"), ("series", "Series")]
TOPIC_NAMES = {topic_id: name for topic_id, name in TOPICS}
STATUS_WORDS = {
    "unattempted": "Unattempted", "insufficient_evidence": "Insufficient evidence",
    "weak": "Weak", "developing": "Developing", "mastered": "Mastered",
}


# ---- A real practice history in both modes ---------------------------------------


def _question(qid, topic, dimension):
    return Question(id=qid, topic_id=topic, question=f"Question {qid}?", options=["A", "B", "C", "D"],
                    correct_index=0, explanation="Because.", cognitive_dimension=dimension)


# Session id, mode and {question id: answered correctly}, oldest first.
SESSIONS = [
    ("m1", "mock", {"r0": True, "r1": False, "r2": True, "r3": True, "l0": False, "l1": True}),
    ("t1", "topic", {"r0": False, "r1": True, "r2": True, "r4": True}),
    ("m2", "mock", {"r1": True, "r4": True, "l2": False, "s0": True}),
    ("t2", "topic", {"l0": True, "l1": True, "l2": True, "l3": False}),
]
FOCUS = {
    "m1": {"r0": 30.0, "r1": 45.5, "r2": 20.0, "l0": 70.0, "l1": 12.0},
    "t1": {"r0": 61.0, "r1": 40.0},
    "m2": {"r1": 15.0, "s0": 95.0},
}


def chart_course_and_history():
    questions = (
        [_question(f"r{i}", "rates", "computation" if i % 2 == 0 else "conceptual") for i in range(6)]
        + [_question(f"l{i}", "limits", "conceptual" if i % 2 == 0 else "computation") for i in range(4)]
        + [_question(f"s{i}", "series", "computation") for i in range(2)]
    )
    by_id = {question.id: question for question in questions}
    course = StudyPackage(
        course_id=COURSE_ID, course_name="Chart course",
        topics=[{"id": topic_id, "name": name, "summary": "Summary."} for topic_id, name in TOPICS],
        relationships=[], questions=questions,
        learning_state={"session_order": [sid for sid, _, _ in SESSIONS]},
    )
    history = {}
    from models.schemas import ExamSession

    for sid, mode, answers in SESSIONS:
        picked = [by_id[qid] for qid in answers]
        session = ExamSession(session_id=sid, mode=mode, question_ids=list(answers))
        result = grade_exam(session, picked, {qid: 0 if ok else 1 for qid, ok in answers.items()})
        history[sid] = {"session": session, "questions": picked, "attempts": result["attempts"], "result": result}
        rows = {qid: {"focus_seconds": seconds} for qid, seconds in FOCUS.get(sid, {}).items()}
        if rows:
            course = set_session_insights(course, sid, rows)
    return course, history


def progress_app(course, history=None, *, mode=None, chinese=False, extra=None):
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.session_state["current_course"] = course
    if history is not None:
        app.session_state[f"practice_history_{course.course_id}"] = history
    if mode is not None:
        app.session_state[f"performance_mode_{course.course_id}"] = mode
    if chinese:
        app.session_state[LANGUAGE_KEY] = True
    for key, value in (extra or {}).items():
        app.session_state[key] = value
    return app.run()


# ---- Reading the charts back --------------------------------------------------------

ROW = re.compile(
    r'<div class="progress-bar-row is-(?P<style>\w+)"><div class="progress-bar-head">'
    r'<span class="progress-bar-label">(?P<label>.*?)</span>'
    r'(?:<span class="progress-chip is-\w+">(?P<chip>.*?)</span>)?'
    r'<span class="progress-bar-value"><strong>(?P<value>.*?)</strong>'
    r'(?: <span class="progress-bar-detail">· (?P<detail>.*?)</span>)?</span></div>'
    r'(?:<div class="progress-track is-empty"></div>|<div class="progress-track">'
    r'<span class="progress-fill is-\w+" style="width:(?P<fill>[\d.]+)%"></span></div>)</div>'
)


def bar_rows(markup):
    rows = []
    for match in ROW.finditer(markup):
        found = {key: html.unescape(value) if isinstance(value, str) else value
                 for key, value in match.groupdict().items()}
        found["fill"] = None if match["fill"] is None else float(match["fill"])
        rows.append(found)
    return rows


def visible_text(markup):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup))).strip()


def aria_label(markup):
    return html.unescape(re.search(r'role="img" aria-label="([^"]*)"', markup).group(1))


def charts(app, kind):
    marker = ('class="progress-chart progress-sessions"' if kind == "sessions"
              else f'class="progress-chart progress-bars progress-{kind}"')
    return [m.value for m in app.markdown if marker in m.value]


def chart(app, kind):
    found = charts(app, kind)
    assert len(found) == 1, (kind, len(found))
    return found[0]


def session_values(markup):
    return [int(value) for value in re.findall(r'class="ps-value[^"]*"[^>]*>(\d+)%</text>', markup)]


def elements_with_ancestors(node, ancestors=()):
    for child in node.children.values():
        if isinstance(child, Block):
            yield from elements_with_ancestors(child, (*ancestors, child.type))
        else:
            yield child, ancestors


def block_ids(node):
    for child in node.children.values():
        if isinstance(child, Block):
            yield getattr(child.proto, "id", "") or ""
            yield from block_ids(child)


# ---- Markup ------------------------------------------------------------------------


def test_bar_chart_is_one_worded_image_with_escaped_course_text():
    rows = [
        BarRow('Rates & <Ratios> "x"', 72.0, "developing", "Developing", "72%", "5 different questions · 7 answers"),
        BarRow("Limits", None, "empty", "Unattempted", "0 answers"),
    ]
    markup = bar_chart_html("Mastery by topic", rows, kind="mastery")

    assert markup.startswith('<div class="progress-chart progress-bars progress-mastery" role="img" aria-label="')
    assert "<Ratios>" not in markup and "&lt;Ratios&gt;" in markup and "&quot;x&quot;" in markup
    assert aria_label(markup) == (
        'Mastery by topic: Rates & <Ratios> "x", Developing, 72%, 5 different questions · 7 answers; '
        "Limits, Unattempted, 0 answers"
    )
    parsed = bar_rows(markup)
    assert [(row["label"], row["chip"], row["value"], row["fill"]) for row in parsed] == [
        ('Rates & <Ratios> "x"', "Developing", "72%", 72.0), ("Limits", "Unattempted", "0 answers", None),
    ]
    # An empty track draws no coloured bar at all.
    assert markup.count("progress-fill") == 1
    assert "<script" not in markup.lower() and not re.search(r"\son\w+=", markup)
    assert "\n" not in markup  # one raw HTML block for Markdown


def test_bar_chart_without_rows_says_so_in_words():
    markup = bar_chart_html("Mastery by topic", [], kind="mastery", empty_text="This course has no topics yet.")
    assert aria_label(markup) == "Mastery by topic: This course has no topics yet."
    assert "This course has no topics yet." in visible_text(markup)


def test_session_chart_with_no_sessions_draws_the_frame_and_one_line():
    markup = session_chart_html([], title="Accuracy by session", empty_text="No graded sessions in this mode yet.")
    assert 'role="img"' in markup
    assert aria_label(markup) == "Accuracy by session: No graded sessions in this mode yet."
    assert markup.count("<line") == 3 and ">0%<" in markup and ">100%<" in markup
    assert "<circle" not in markup and "<polyline" not in markup
    assert "No graded sessions in this mode yet." in visible_text(markup)


def test_session_chart_with_one_session_shows_a_single_dot_and_the_latest_value():
    markup = session_chart_html([SessionPoint(1, 2 / 3 * 100)], title="Accuracy by session", empty_text="-")
    assert markup.count("<circle") == 1 and "<polyline" not in markup
    assert session_values(markup) == [67]
    assert "Latest session: 67%" in visible_text(markup)
    assert aria_label(markup) == "Accuracy by session: Session 1: 67%. Latest session: 67%"


def test_session_chart_labels_every_point_and_lists_values_when_crowded():
    few = [SessionPoint(i + 1, value) for i, value in enumerate([0, 50, 100, 25])]
    markup = session_chart_html(few, title="Accuracy by session", empty_text="-")
    assert session_values(markup) == [0, 50, 100, 25]
    assert markup.count("<circle") == 4 and markup.count("<polyline") == 1

    many = [SessionPoint(i + 1, (i * 7) % 101) for i in range(14)]
    markup = session_chart_html(many, title="Accuracy by session", empty_text="-")
    listed = re.findall(r"<li>(\d+) · (\d+)%</li>", markup)
    assert [(int(n), int(v)) for n, v in listed] == [(p.number, round(p.accuracy)) for p in many]
    assert session_values(markup)[-1] == round(many[-1].accuracy)
    assert all(f"Session {p.number}: {p.accuracy:.0f}%" in aria_label(markup) for p in many)


def test_example_banner_is_a_note_with_the_agreed_wording():
    markup = example_banner_html()
    assert 'role="note"' in markup
    assert visible_text(markup) == (
        "Example report · These numbers are sample data. Finish a practice session to see your own."
    )


def test_rows_follow_the_thresholds_and_counts():
    course, history = chart_course_and_history()
    sessions = [record["session"] for record in history.values()]
    attempts = [a for record in history.values() for a in record["attempts"]]
    stats = {s.topic_id: s for s in calculate_topic_stats(attempts, sessions, course.questions) if s.mode == "mock"}
    rows = mastery_rows(course.topics, stats)
    for row, (topic_id, name) in zip(rows, TOPICS):
        status = get_mastery_status(stats[topic_id])
        assert row.label == name and row.chip == STATUS_WORDS[status]
        assert (row.fill is None) == (status in {"unattempted", "insufficient_evidence"})

    profile, _ = evidence_profile(attempts, sessions, course.questions, "topic")
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    rows = dna_rows({d: by_key[("limits", d)] for d in ("computation", "conceptual")})
    assert [row.label for row in rows] == ["Computation", "Conceptual understanding"]
    assert rows[0] == BarRow("Computation", None, "empty", None, "Not enough answers yet", "2 different questions")
    assert rows[1] == BarRow("Conceptual understanding", None, "empty", None, "Not enough answers yet",
                             "2 different questions")
    missing = dna_rows({})
    assert [row.detail for row in missing] == ["0 different questions", "0 different questions"]

    timed = time_rows({"a": 30.0, "b": 125.4, "c": 0.0}, {"a": "A", "b": "B"}, "Topic")
    assert [(row.label, row.value, round(row.fill)) for row in timed] == [
        ("B", "2 min 5 s", 100), ("A", "30 s", 24), ("Topic", "0 s", 0),
    ]
    assert duration_text(59.6) == "1 min 0 s" and duration_text(59.4) == "59 s"


def test_session_points_skip_nothing_and_keep_order():
    _, history = chart_course_and_history()
    points = session_points(record for record in history.values() if record["session"].mode == "mock")
    assert [point.number for point in points] == [1, 2]
    assert [point.accuracy for point in points] == pytest.approx([4 / 6 * 100, 3 / 4 * 100])


def test_markup_builders_do_not_use_streamlit():
    tree = ast.parse((ROOT / "components" / "progress_charts.py").read_text(encoding="utf-8"))

    def imported(node):
        names = []
        for inner in ast.walk(node):
            if isinstance(inner, ast.Import):
                names.extend(alias.name for alias in inner.names)
            elif isinstance(inner, ast.ImportFrom):
                names.append(inner.module or "")
        return names

    top_level = [name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                 for name in imported(node)]
    assert not any(name.startswith(("streamlit", "services.i18n")) for name in top_level)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    streamlit_users = {name for name, node in functions.items()
                       if any(item.startswith(("streamlit", "services.i18n")) for item in imported(node))}
    assert streamlit_users == {"_draw", "_translator"}
    builders = ("bar_chart_html", "session_chart_html", "example_banner_html", "mastery_rows",
                "dna_rows", "time_rows", "session_points")
    for name in builders:
        assert not any(isinstance(inner, ast.Name) and inner.id in {"st", "_draw", "_translator"}
                       for inner in ast.walk(functions[name])), name


# ---- Stylesheet -----------------------------------------------------------------------


def test_stylesheet_uses_paper_tokens_and_fits_narrow_screens():
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.DOTALL)
    from services import ui_style

    assert CSS in ui_style.paper_stylesheets()
    # Colours come from the paper tokens (white text on the solid chip aside).
    assert set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", css)) <= {"#FFFFFF"}
    for token in ("--paper-card", "--paper-badge", "--paper-select", "--ink", "--ink-muted",
                  "--accent-blue-fill", "--accent-rust-text", "--font-title"):
        assert f"var({token}" in css
    # Nothing has a fixed width that could push past a phone screen.
    assert not re.search(r"(?<![-\w])(min-)?width:\s*\d{3,}px", css)
    assert "overflow-wrap: anywhere" in css
    narrow = css[css.index("@media (max-width: 759.98px)"):]
    assert "flex: 1 1 100%" in narrow and "max-width: 100%" in narrow
    # Each status look differs in more than hue: solid, outlined, striped, dashed.
    assert re.search(r"\.progress-fill\.is-developing \{[^}]*border: 2px solid", css)
    assert re.search(r"\.progress-fill\.is-weak \{[^}]*repeating-linear-gradient", css)
    assert re.search(r"\.progress-track\.is-empty \{[^}]*dashed", css)


def test_chip_and_value_text_meet_contrast():
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(foreground, background):
        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    for foreground, background in [
        ("#FFFFFF", "#557A99"),  # Mastered chip
        ("#4A6C8A", "#FFFCF7"),  # Developing chip
        ("#9A5426", "#FAE5D2"),  # Weak chip
        ("#6B7280", "#FFFCF7"),  # empty chip, details, axis labels on the card
        ("#9A5426", "#FFFCF7"),  # latest session value
        ("#2A2F33", "#FAE5D2"),  # example banner text
    ]:
        assert contrast(foreground, background) >= 4.5, (foreground, background)


# ---- The page ---------------------------------------------------------------------------


def test_page_has_no_tabs_and_nothing_analytical_behind_a_click():
    course, history = chart_course_and_history()
    app = progress_app(course, history, mode="Topic Practice")
    assert not app.exception
    assert not app.tabs and not app.get("tab_container")
    # No expander at all: the answers behind each topic open on their own page.
    assert not app.expander
    assert [b.key for b in app.button if b.label == "View answers"] == [
        "learning_evidence_open_rates", "learning_evidence_open_limits",
    ]
    for element, ancestors in elements_with_ancestors(app.main):
        if element.type == "markdown" and "progress-chart" in element.value:
            assert "expander" not in ancestors and "tab" not in ancestors
    for kind in ("mastery", "sessions", "time"):
        chart(app, kind)
    assert len(charts(app, "dna")) == len(TOPICS)
    captions = [caption.value for caption in app.caption]
    assert any(text.startswith("How to read this profile · These are question-based observations")
               for text in captions)
    headings = [s.value for s in app.subheader]
    assert {"Mastery by topic", "Accuracy by session", "Learning DNA", "Time by topic"} <= set(headings)
    # The per-topic boxes of the old details tab are gone: one list, in the chart.
    ids = list(block_ids(app.main))
    assert any("progress_mastery" in block for block in ids)
    assert not any("progress_topic_" in block for block in ids)
    # The review list is in view too, with its reasons and its button.
    assert any("Why review" in frame.value.columns for frame in app.dataframe)
    assert app.button(key=f"priorities_{COURSE_ID}").label == "Practise review priorities"


def test_review_list_button_on_progress_still_starts_a_practice_session():
    from tests.auth_helpers import signed_in_app

    course, history = chart_course_and_history()
    app = signed_in_app(ROOT / "app.py").run()
    app.session_state["current_course"] = course
    app.session_state[f"practice_history_{COURSE_ID}"] = history
    app.session_state[f"confirmed_scope_{COURSE_ID}"] = [topic_id for topic_id, _ in TOPICS]
    app.session_state[f"performance_mode_{COURSE_ID}"] = "Topic Practice"
    app.switch_page("pages/3_Performance.py").run()
    assert not app.exception and app.title[0].value == "Progress"
    app.button(key=f"priorities_{COURSE_ID}").click().run()
    assert not app.exception
    # A mixed-topic review session is recorded in Mock Exam mode, and the
    # question screen names the mode in its title.
    assert app.title[0].value == "Practice · Mock Exam"
    active = app.session_state[f"active_practice_{COURSE_ID}"]
    assert "result" not in active and active["session"].session_id not in history
    assert app.session_state[f"practice_history_{COURSE_ID}"] == history


@pytest.mark.parametrize("mode_label,mode", [("Mock Exam", "mock"), ("Topic Practice", "topic")])
def test_chart_numbers_come_from_the_existing_calculations(mode_label, mode):
    course, history = chart_course_and_history()
    app = progress_app(course, history, mode=mode_label)
    assert not app.exception
    sessions = [history[sid]["session"] for sid in course.learning_state["session_order"]]
    attempts = [a for record in history.values() for a in record["attempts"]]
    stats = {s.topic_id: s for s in calculate_topic_stats(attempts, sessions, course.questions) if s.mode == mode}

    rows = bar_rows(chart(app, "mastery"))
    assert [row["label"] for row in rows] == [name for _, name in TOPICS]
    for row, (topic_id, _) in zip(rows, TOPICS):
        item = stats[topic_id]
        status = get_mastery_status(item)
        assert row["chip"] == STATUS_WORDS[status]
        different = f"{item.unique_attempted} different question{'s' if item.unique_attempted != 1 else ''}"
        answers = f"{item.attempted} answer{'s' if item.attempted != 1 else ''}"
        if status in {"unattempted", "insufficient_evidence"}:
            assert row["fill"] is None and row["style"] == "empty"
            assert row["value"] == (different if item.attempted else "0 answers")
        else:
            assert row["fill"] == pytest.approx(item.evidence_accuracy, abs=0.05)
            assert row["value"] == f"{item.evidence_accuracy:.0f}%"
            assert row["detail"] == f"{different} · {answers}"

    expected_points = [
        100 * sum(a.is_correct for a in history[sid]["attempts"]) / len(history[sid]["attempts"])
        for sid in course.learning_state["session_order"] if history[sid]["session"].mode == mode
    ]
    markup = chart(app, "sessions")
    assert session_values(markup) == [round(value) for value in expected_points]
    assert f"Latest session: {expected_points[-1]:.0f}%" in visible_text(markup)

    profile, _ = evidence_profile(attempts, sessions, course.questions, mode)
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    for markup, (topic_id, name) in zip(charts(app, "dna"), TOPICS):
        assert f'<p class="progress-chart-heading">{html.escape(name)}</p>' in markup
        for row, dimension in zip(bar_rows(markup), ("computation", "conceptual")):
            item = by_key[(topic_id, dimension)]
            assert row["detail"] == f"{item.count} different question{'s' if item.count != 1 else ''}"
            if item.count >= 3:
                assert row["value"] == f"{item.accuracy:.0f}%" and row["chip"] == item.status
            else:
                assert row["value"] == "Not enough answers yet" and row["fill"] is None

    totals = {}
    for sid, record in history.items():
        if record["session"].mode == mode:
            for question in record["questions"]:
                seconds = FOCUS.get(sid, {}).get(question.id)
                if seconds is not None:
                    totals[question.topic_id] = totals.get(question.topic_id, 0.0) + seconds
    rows = bar_rows(chart(app, "time"))
    assert [(row["label"], row["value"]) for row in rows] == [
        (TOPIC_NAMES[topic_id], duration_text(seconds))
        for topic_id, seconds in sorted(totals.items(), key=lambda pair: -pair[1])
    ]

    tiles = {metric.label: metric.value for metric in app.metric}
    mode_attempts = [a for a in attempts if history[a.session_id]["session"].mode == mode]
    assert tiles["Graded practice sessions"] == str(len(expected_points))
    assert tiles["Answers"] == str(len(mode_attempts))
    assert tiles["Accuracy"] == f"{100 * sum(a.is_correct for a in mode_attempts) / len(mode_attempts):.2f}%"


def test_known_mastery_numbers_for_the_fixture():
    course, history = chart_course_and_history()
    rows = bar_rows(chart(progress_app(course, history, mode="Mock Exam"), "mastery"))
    # Rates: r1 wrong, then right in m2; Limits: 1 of 3 latest answers right; Series: one answer.
    assert [(row["chip"], row["value"], row["detail"], row["style"]) for row in rows] == [
        ("Mastered", "100%", "5 different questions · 6 answers", "mastered"),
        ("Weak", "33%", "3 different questions · 3 answers", "weak"),
        ("Insufficient evidence", "1 different question", "1 answer", "empty"),
    ]
    time = bar_rows(chart(progress_app(course, history, mode="Mock Exam"), "time"))
    assert [(row["label"], row["value"]) for row in time] == [
        ("Rates & <Ratios>", "1 min 50 s"), ("Series", "1 min 35 s"), ("Limits", "1 min 22 s"),
    ]


def test_mode_without_time_shows_no_time_chart():
    course, history = chart_course_and_history()
    del history["t1"]
    course.learning_state["session_order"].remove("t1")
    app = progress_app(course, history, mode="Topic Practice")
    assert not app.exception
    assert not charts(app, "time")
    assert "Time by topic" not in [s.value for s in app.subheader]


def test_course_without_history_shows_the_message_and_empty_charts_only():
    course, _ = chart_course_and_history()
    course.learning_state.clear()
    app = progress_app(course)
    assert not app.exception
    assert [info.value for info in app.info] == [
        "No graded practice sessions yet. Your topic list will update after you complete a practice session."
    ]
    rows = bar_rows(chart(app, "mastery"))
    assert [(row["label"], row["chip"], row["value"], row["fill"]) for row in rows] == [
        (name, "Unattempted", "0 answers", None) for _, name in TOPICS
    ]
    markup = chart(app, "sessions")
    assert "<circle" not in markup and "No graded sessions in this mode yet." in visible_text(markup)
    for markup in charts(app, "dna"):
        assert [(row["value"], row["detail"]) for row in bar_rows(markup)] == [
            ("Not enough answers yet", "0 different questions")
        ] * 2
    assert not charts(app, "time")
    texts = " ".join(m.value for m in app.markdown if not m.value.startswith("<style"))
    texts += " ".join(s.value for s in app.subheader)
    assert "Example" not in texts and "progress-example-banner" not in texts


@pytest.mark.parametrize("stale", ["Learning DNA", "Practice details", "Overview", "Not a tab", 3])
def test_stale_progress_tab_value_changes_nothing(stale):
    course, history = chart_course_and_history()

    def snapshot(app):
        return [(type(element).__name__, getattr(element, "value", None) if element.type != "dataframe"
                 else element.value.to_dict(), getattr(element, "label", None))
                for element, _ in elements_with_ancestors(app.main)]

    plain = progress_app(course, history, mode="Topic Practice")
    stale_app = progress_app(course, history, mode="Topic Practice",
                             extra={f"progress_tab_{COURSE_ID}": stale})
    assert not stale_app.exception
    assert snapshot(stale_app) == snapshot(plain)
    assert stale_app.session_state[f"progress_tab_{COURSE_ID}"] == stale


# ---- Chinese interface ------------------------------------------------------------------------

LATIN = re.compile(r"[A-Za-z]")


def interface_strings(app, course_text):
    """Every piece of text the page shows (and its chart labels), with course text removed."""
    texts = []
    for element, _ in elements_with_ancestors(app.main):
        kind = element.type
        if kind == "markdown":
            if element.value.startswith("<style"):
                continue
            texts.append(visible_text(element.value))
            texts.extend(html.unescape(label) for label in re.findall(r'aria-label="([^"]*)"', element.value))
        elif kind in {"title", "subheader", "caption", "alert", "info", "warning", "error", "header"}:
            texts.append(element.value)
        elif kind == "metric":
            texts.extend([element.label, str(element.value)])
        elif kind == "radio":
            texts.extend([element.label, *element.options])
        elif kind == "button":
            texts.append(element.label)
        elif kind == "dataframe":
            frame = element.value
            texts.extend(str(column) for column in frame.columns)
            texts.extend(value for value in frame.astype(object).values.ravel() if isinstance(value, str))
        else:
            texts.append(str(getattr(element, "value", "")))
    for element in app.expander:
        texts.append(element.label)
    leftovers = []
    for text in texts:
        for course_item in sorted(course_text, key=len, reverse=True):
            text = text.replace(course_item, "")
        leftovers.append(text)
    return leftovers


def course_strings(course):
    return {course.course_name, *(t.name for t in course.topics), *(q.question for q in course.questions)}


def test_chinese_real_progress_shows_no_english_interface_text():
    course, history = chart_course_and_history()
    course = set_session_insights(course, "t1", {"r0": {"confidence": "sure", "focus_seconds": 61.0},
                                                 "r1": {"focus_seconds": 40.0}})
    # The same reader finds English text when the interface is in English.
    english_app = progress_app(course, history, mode="Topic Practice")
    assert any(LATIN.search(text) for text in interface_strings(english_app, course_strings(course)))
    for mode in ("模拟考试", "知识点练习"):
        app = progress_app(course, history, mode=mode, chinese=True)
        assert not app.exception
        collected = interface_strings(app, course_strings(course))
        assert "开始练习" in collected and any("最近一次练习" in text for text in collected)
        english = [text for text in collected if LATIN.search(text)]
        assert english == []
    assert any("各知识点掌握情况" == s.value for s in app.subheader)
    assert any(s.value == "各知识点用时" for s in app.subheader)
    assert app.button(key="learning_evidence_open_rates").label == "查看作答"


def test_chinese_empty_progress_shows_no_english_interface_text():
    course, _ = chart_course_and_history()
    course.learning_state.clear()
    app = progress_app(course, chinese=True)
    assert not app.exception
    assert [text for text in interface_strings(app, course_strings(course)) if LATIN.search(text)] == []


@pytest.mark.parametrize("relative", [
    "pages/3_Performance.py", "services/learning_dna_ui.py", "components/progress_charts.py",
    "services/practice_insights_ui.py",
])
def test_progress_interface_strings_have_chinese_entries(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    constants = {
        target.id: node.value.value
        for node in ast.walk(tree) if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        for target in node.targets if isinstance(target, ast.Name)
    }
    literal = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"tr", "heading"} and node.args:
            arg = node.args[0]
            text = arg.value if isinstance(arg, ast.Constant) else constants.get(getattr(arg, "id", None))
            if isinstance(text, str):
                literal.append(text)
        # Chart empty-state words are passed on and translated inside the chart.
        for keyword in getattr(node, "keywords", []):
            if keyword.arg == "empty_text" and isinstance(keyword.value, ast.Constant):
                literal.append(keyword.value.value)
    literal.extend(progress_charts.STATUS_LABELS.values())
    literal.extend(progress_charts.DNA_STYLES)
    missing = [text for text in literal if text not in _TRANSLATIONS
               and not any(re.fullmatch(pattern, text, re.DOTALL) for pattern, _ in _DYNAMIC)]
    assert missing == []


def test_numbered_chart_words_have_chinese_patterns(monkeypatch):
    from types import SimpleNamespace

    from services import i18n

    monkeypatch.setattr(i18n, "st", SimpleNamespace(session_state={LANGUAGE_KEY: True}))
    tr = i18n.tr
    words = [
        progress_charts.questions_text(1, tr), progress_charts.questions_text(6, tr),
        progress_charts.answers_text(1, tr), progress_charts.answers_text(0, tr),
        duration_text(42, tr), duration_text(399, tr), tr(progress_charts.NOT_ENOUGH),
    ]
    assert words == ["1 道不同题目", "6 道不同题目", "1 次作答", "0 次作答", "42 秒", "6 分 39 秒", "作答还不够"]
    two = session_chart_html([SessionPoint(1, 50.0), SessionPoint(2, 75.0)], title=tr("Accuracy by session"),
                             empty_text="No graded sessions in this mode yet.", tr=tr)
    none = session_chart_html([], title=tr("Accuracy by session"),
                              empty_text="No graded sessions in this mode yet.", tr=tr)
    for markup in (two, none):
        assert not LATIN.search(visible_text(markup)) and not LATIN.search(aria_label(markup))
    assert "最近一次练习：75%" in visible_text(two)
    assert aria_label(two) == "各次练习正确率: 第 1 次练习：50%; 第 2 次练习：75%. 最近一次练习：75%"
    assert visible_text(example_banner_html(tr)) == (
        "示例报告 · 这些数字是示例数据。完成一次练习后就会显示你自己的结果。"
    )


# ---- Layout: Learning DNA cards side by side, long figure labels wrap ----------------

def test_learning_dna_cards_share_one_block_laid_out_as_a_grid():
    course, history = chart_course_and_history()
    app = progress_app(course, history)
    assert not app.exception

    def find(node, suffix):
        for child in node.children.values():
            if isinstance(child, Block):
                if (getattr(child.proto, "id", "") or "").endswith(suffix):
                    return child
                found = find(child, suffix)
                if found is not None:
                    return found
        return None

    holder = find(app.main, "learning_dna_cards")
    assert holder is not None
    inside = list(block_ids(holder))
    for topic_id, _ in TOPICS:
        assert any(block.endswith(f"learning_dna_{topic_id}") for block in inside)
    css = (ROOT / "assets" / "paper_progress.css").read_text(encoding="utf-8")
    rule = css.split(".st-key-learning_dna_cards {", 1)[1].split("}", 1)[0]
    assert "display: grid" in rule
    # One column on a phone: a card is never forced wider than the page.
    assert "minmax(min(100%," in rule
    # A long label on the three figures wraps; it is not cut off with an ellipsis.
    label_rule = css.split('.st-key-progress_overview [data-testid="stMetricLabel"] * {', 1)[1].split("}", 1)[0]
    assert "white-space: normal" in label_rule
