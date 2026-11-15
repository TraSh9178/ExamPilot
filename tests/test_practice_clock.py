"""Session clock in the practice header: one source of truth, shown without a click, CSS-only ticking."""
import random
import re
import time
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.proto.Block_pb2 import Block as BlockProto

from models.schemas import ExamSession
from services import practice_insights_ui
from services.i18n import LANGUAGE_KEY
from services.practice_insights import (
    clock_text, focus_question, pause_or_resume_for_page, session_seconds, settle_focus,
)
from tests.auth_helpers import signed_in_app
from tests.test_paper_practice import mock_app, page_markdown, texts
from tests.test_practice_insights import start_app
from tests.test_practice_page import submit_answers

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "2_Practice_Center.py"
UI = ROOT / "services" / "practice_insights_ui.py"
CSS = ROOT / "assets" / "paper_practice.css"
INTERNAL_RULES = ("120", "estimate", "capped", "interactions", "attention")


def new_active(question_ids=("q0", "q1", "q2")):
    return {"session": ExamSession(session_id="s", mode="topic", question_ids=list(question_ids))}


def leave_page(active, now):
    """What app.py does when the student opens another page."""
    pause_or_resume_for_page(active, False, now)


def return_to_practice(active, now):
    """What app.py does when the student comes back to the practice page."""
    pause_or_resume_for_page(active, True, now)


def find_block(app, key):
    """The st.container created with this key."""
    def walk(node):
        block_id = getattr(getattr(node, "proto", None), "id", None)
        if isinstance(block_id, str) and block_id.endswith(f"-{key}"):
            return node
        for child in getattr(node, "children", {}).values():
            if (found := walk(child)) is not None:
                return found
        return None
    return walk(app.main)


def clock_html(app):
    clocks = [value for value in page_markdown(app) if 'class="flight-clock' in value]
    assert len(clocks) <= 1
    return clocks[0] if clocks else None


def clock_state(app):
    html = clock_html(app)
    assert html is not None
    return {
        "base": int(re.search(r'style="--clock-base: (\d+)"', html).group(1)),
        "text": re.search(r'class="flight-clock-static">([^<]+)<', html).group(1),
        "label": re.search(r'aria-label="([^"]+)"', html).group(1),
        "running": "is-running" in html,
        "paused": "is-paused" in html,
        "restart": re.search(r"\brestart-(\d+)\b", html).group(1),
    }


def visible_text(html):
    return re.sub(r"<[^>]+>", " ", html)


# 1 · One source of truth: settle_focus --------------------------------------------

def test_clock_counts_a_long_gap_in_full_while_focus_stays_capped():
    active = new_active()
    focus_question(active, "q0", 100)
    settle_focus(active, 400)  # 300 s without a click
    assert active["session_seconds"] == 300
    assert active["focus_seconds"] == {"q0": 120}
    settle_focus(active, 410)
    assert active["session_seconds"] == 310
    assert active["focus_seconds"] == {"q0": 130}


def test_pausing_stops_the_clock_and_resuming_continues_it():
    active = new_active()
    focus_question(active, "q0", 0)
    settle_focus(active, 40)
    # Pause button: settle, then stop.
    settle_focus(active, 50)
    active["focus_timer"]["since"] = None
    settle_focus(active, 5000)
    assert active["session_seconds"] == 50
    # Resume button: start again from now.
    active["focus_timer"]["since"] = 5000
    settle_focus(active, 5030)
    assert active["session_seconds"] == 80
    assert active["focus_seconds"] == {"q0": 80}


def test_changing_question_does_not_reset_the_clock():
    active = new_active()
    focus_question(active, "q0", 0)
    focus_question(active, "q1", 30)
    focus_question(active, "q2", 230)  # 200 s on q1: focus capped, clock not
    focus_question(active, "q0", 240)
    settle_focus(active, 250)
    assert active["session_seconds"] == 250
    assert active["focus_seconds"] == {"q0": 40, "q1": 120, "q2": 10}


def test_leaving_the_page_pauses_the_clock_with_the_right_total():
    active = new_active()
    focus_question(active, "q0", 1000)
    leave_page(active, 1095)
    assert active["session_seconds"] == 95
    assert active["focus_timer"]["since"] is None
    # Back on the practice page much later: the page settles before it draws the clock.
    settle_focus(active, 9000)
    assert active["session_seconds"] == 95
    assert active["focus_seconds"] == {"q0": 95}
    # Leaving again while paused changes nothing.
    leave_page(active, 9500)
    assert active["session_seconds"] == 95


def test_returning_to_practice_restarts_a_clock_that_leaving_stopped():
    active = new_active()
    focus_question(active, "q0", 1000)
    leave_page(active, 1060)
    assert active["focus_timer"] == {"question_id": "q0", "since": None, "away": True}
    # Ten minutes on other pages, including a second page change, are not counted.
    leave_page(active, 1300)
    return_to_practice(active, 1660)
    assert active["focus_timer"] == {"question_id": "q0", "since": 1660}
    assert active["session_seconds"] == 60
    settle_focus(active, 1690)
    assert active["session_seconds"] == 90
    assert active["focus_seconds"] == {"q0": 90}


def test_a_pause_the_student_chose_survives_leaving_and_returning():
    active = new_active()
    focus_question(active, "q0", 1000)
    settle_focus(active, 1040)
    active["focus_timer"]["since"] = None  # the Pause button
    leave_page(active, 1100)
    assert "away" not in active["focus_timer"]
    return_to_practice(active, 1500)
    assert active["focus_timer"]["since"] is None
    assert active["session_seconds"] == 40


def test_page_changes_without_a_timer_are_ignored():
    active = new_active()
    leave_page(active, 10)
    return_to_practice(active, 20)
    assert "focus_timer" not in active and "session_seconds" not in active


def test_older_state_without_a_clock_starts_from_its_focus_totals():
    active = new_active()
    active["focus_seconds"] = {"q0": 30.0, "q1": 12.5}
    active["focus_timer"] = {"question_id": "q1", "since": None}
    assert session_seconds(active) == 42.5
    active["focus_timer"]["since"] = 100
    settle_focus(active, 110)
    assert active["session_seconds"] == 52.5  # counted once, not twice
    assert active["focus_seconds"] == {"q0": 30.0, "q1": 22.5}
    assert session_seconds(new_active()) == 0


def test_clock_ignores_backward_time_and_stays_bounded():
    active = new_active()
    focus_question(active, "q0", 100)
    settle_focus(active, 90)
    assert active["session_seconds"] == 0
    assert active["focus_seconds"] == {"q0": 0}
    active["session_seconds"] = 999_990.0
    settle_focus(active, 10_090)
    assert active["session_seconds"] == 1_000_000


def previous_settle_focus(active, now):
    """settle_focus as it was before the session clock, kept to pin per-question totals."""
    timer = active.get('focus_timer')
    if timer is None or timer.get('since') is None:
        return
    elapsed = max(0.0, min(120.0, now - timer['since']))
    totals = active.setdefault('focus_seconds', {})
    qid = timer['question_id']
    totals[qid] = min(1_000_000.0, totals.get(qid, 0.0) + elapsed)
    timer['since'] = now


def previous_focus_question(active, qid, now):
    if qid not in active['session'].question_ids:
        raise ValueError('Unknown focus question')
    previous_settle_focus(active, now)
    active['focus_timer'] = {'question_id': qid, 'since': now}


@pytest.mark.parametrize("seed", range(5))
def test_per_question_focus_is_unchanged_by_the_clock(seed):
    rng = random.Random(seed)
    new, old = new_active(), new_active()
    now = 0.0
    focus_question(new, "q0", now)
    previous_focus_question(old, "q0", now)
    for _ in range(200):
        now += rng.choice([0, 0.4, 3, 59.9, 119.5, 120, 121, 600, -5])
        step = rng.choice(["settle", "switch", "pause", "resume", "leave"])
        if step == "settle":
            settle_focus(new, now)
            previous_settle_focus(old, now)
        elif step == "switch":
            qid = rng.choice(["q0", "q1", "q2"])
            focus_question(new, qid, now)
            previous_focus_question(old, qid, now)
        elif step in ("pause", "leave"):
            settle_focus(new, now)
            previous_settle_focus(old, now)
            new["focus_timer"]["since"] = old["focus_timer"]["since"] = None
        else:
            new["focus_timer"]["since"] = old["focus_timer"]["since"] = now
        assert new.get("focus_seconds") == old.get("focus_seconds")
        assert new["focus_timer"] == old["focus_timer"]
    assert new["focus_seconds"] == old["focus_seconds"]
    assert new["session_seconds"] >= sum(new["focus_seconds"].values())


@pytest.mark.parametrize(("seconds", "text"), [
    (0, "00:00"), (5.9, "00:05"), (312, "05:12"), (3599, "59:59"),
    (3600, "1:00:00"), (4503, "1:15:03"), (36000, "10:00:00"), (-3, "00:00"),
])
def test_clock_text_is_mm_ss_then_h_mm_ss(seconds, text):
    assert clock_text(seconds) == text


# 2 · Shown in the header, without a click ----------------------------------------

def test_topic_practice_shows_the_clock_in_the_header_without_a_click():
    app, _ = start_app()
    assert not app.exception
    labels = [e.label for e in app.expander]
    assert "Focus controls" not in labels and "About focus time" not in labels
    assert not any("About focus time" in value or "Focus time is an estimate" in value for value in texts(app))
    header = find_block(app, "flight_practice_progress")
    assert header is not None
    flex = header.proto.flex_container
    assert flex.direction == BlockProto.FlexContainer.Direction.HORIZONTAL and flex.wrap
    assert [c.value for c in find_block(app, "flight_progress_count").caption] == ["Question 01 / 02"]
    assert any('class="flight-route"' in m.value for m in find_block(app, "flight_progress_track").markdown)
    clock = find_block(app, "flight_progress_clock")
    assert any('class="flight-clock' in m.value for m in clock.markdown)
    assert [b.key for b in clock.button] == ["focus_pause_s"]
    # The header, clock included, comes before the question card.
    markdown = page_markdown(app)
    card = next(i for i, value in enumerate(markdown) if "paper-question-badge" in value)
    assert markdown.index(clock_html(app)) < card
    state = clock_state(app)
    assert state["running"] and not state["paused"]


def test_mock_exam_shows_the_clock_until_the_answers_are_submitted():
    app = mock_app()
    assert not app.exception
    assert "Focus controls" not in [e.label for e in app.expander]
    clock = find_block(app, "flight_progress_clock")
    assert clock is not None and any('class="flight-clock' in m.value for m in clock.markdown)
    # The same header as Topic Practice: counter and flight path, no progress bar.
    assert not find_block(app, "flight_progress_track").get("progress")
    assert any('class="flight-route"' in m.value for m in find_block(app, "flight_progress_track").markdown)
    assert [c.value for c in find_block(app, "flight_progress_count").caption] == ["Question 01 / 02"]
    submit_answers(app)
    assert not app.exception
    assert "result" in app.session_state["active_practice_insights"]
    assert clock_html(app) is None
    assert not any(b.key == "focus_pause_m" for b in app.button)


def test_graded_session_has_no_clock():
    app, _ = start_app(graded=True)
    assert not app.exception
    assert clock_html(app) is None
    assert find_block(app, "flight_progress_clock") is None
    assert not any(b.key == "focus_pause_s" for b in app.button)


# 3 · The page keeps one running total ---------------------------------------------

def test_long_idle_gap_shows_in_full_on_the_clock():
    app, _ = start_app()
    active = app.session_state["active_practice_insights"]
    active["session_seconds"] = 0.0
    active["focus_seconds"] = {}
    active["focus_timer"] = {"question_id": "q0", "since": time.monotonic() - 300}
    app.run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert 300 <= active["session_seconds"] < 330
    assert active["focus_seconds"]["q0"] == pytest.approx(120, abs=1)
    assert clock_state(app)["base"] == int(active["session_seconds"])


def test_changing_question_keeps_the_clock_running():
    app, _ = start_app()
    active = app.session_state["active_practice_insights"]
    active["session_seconds"] = 500.0
    app.run()
    app.button(key="worksheet_next_s").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["focus_timer"]["question_id"] == "q1" and active["focus_timer"]["since"] is not None
    assert active["session_seconds"] >= 500
    assert clock_state(app)["base"] >= 500 and clock_state(app)["running"]
    app.run()  # any other rerun on the same question
    assert app.session_state["active_practice_insights"]["focus_timer"]["question_id"] == "q1"
    assert app.session_state["active_practice_insights"]["session_seconds"] >= 500
    app.button(key="worksheet_previous_s").click().run()
    assert app.session_state["active_practice_insights"]["session_seconds"] >= 500
    assert clock_state(app)["base"] >= 500


def test_leaving_the_practice_page_stops_the_clock_and_returning_restarts_it():
    from tests.test_practice_page import make_practice_state
    app = signed_in_app(ROOT / "app.py").run()
    for key, value in make_practice_state(graded=False).items():
        app.session_state[key] = value
    app.session_state["practice_history_course-1"] = {}
    app.switch_page("pages/2_Practice_Center.py").run()
    assert not app.exception
    assert clock_state(app)["running"]
    app.session_state["active_practice_course-1"]["session_seconds"] = 700.0
    app.switch_page("pages/3_Performance.py").run()
    assert not app.exception
    active = app.session_state["active_practice_course-1"]
    assert active["focus_timer"]["since"] is None
    total = active["session_seconds"]
    assert 700 <= total < 760
    assert active["focus_timer"]["away"] is True
    app.switch_page("pages/2_Practice_Center.py").run()
    assert not app.exception
    # Back on the practice page the clock runs again from where it stopped.
    state = clock_state(app)
    assert state["running"] and not state["paused"]
    assert int(total) <= state["base"] <= int(total) + 2
    assert "away" not in app.session_state["active_practice_course-1"]["focus_timer"]
    assert app.button(key="focus_pause_session-1").label == "Pause"


# 5 · Clock markup -------------------------------------------------------------------

def test_clock_markup_carries_role_label_base_and_state():
    app, _ = start_app()
    active = app.session_state["active_practice_insights"]
    active["focus_timer"] = {"question_id": "q0", "since": None}
    active["session_seconds"] = 312.9
    app.run()
    html = clock_html(app)
    assert 'role="timer"' in html
    assert 'aria-label="Session time 05:12"' in html
    assert 'style="--clock-base: 312"' in html
    assert 'class="flight-clock-static">05:12<' in html
    assert re.search(r'class="flight-clock is-paused restart-\d"', html)
    assert 'class="flight-clock-label">Session<' in html
    assert '<span class="flight-clock-icon" aria-hidden="true"><svg' in html
    assert "<script" not in html and "<link" not in html and "<img" not in html
    active["session_seconds"] = 4503.2
    app.run()
    state = clock_state(app)
    assert (state["text"], state["base"], state["label"]) == ("1:15:03", 4503, "Session time 1:15:03")
    assert "has-hours" in clock_html(app)


def test_running_clock_base_is_the_settled_session_time():
    app, _ = start_app()
    active = app.session_state["active_practice_insights"]
    active["session_seconds"] = 61.0
    active["focus_timer"] = {"question_id": "q0", "since": time.monotonic()}
    app.run()
    state = clock_state(app)
    assert state["running"] and not state["paused"]
    assert state["base"] == int(app.session_state["active_practice_insights"]["session_seconds"])
    assert state["text"] == clock_text(state["base"])


def test_each_render_restarts_the_css_count():
    app, _ = start_app()
    seen = [clock_state(app)["restart"]]
    for _ in range(practice_insights_ui.CLOCK_RESTARTS):
        app.run()
        seen.append(clock_state(app)["restart"])
    # Consecutive renders never share a keyframes name, so the CSS count starts from the new base.
    assert all(a != b for a, b in zip(seen, seen[1:]))
    assert set(seen) == {str(n) for n in range(practice_insights_ui.CLOCK_RESTARTS)}


# 7 · One-click pause and resume -------------------------------------------------------

def test_pause_and_resume_are_one_click_each():
    app, _ = start_app()
    button = app.button(key="focus_pause_s")
    assert button.label == "Pause"
    assert button.help == "Pause when you take a break."
    button.click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["focus_timer"]["since"] is None
    paused_total = active["session_seconds"]
    assert clock_state(app)["paused"]
    assert app.button(key="focus_pause_s").label == "Resume"
    app.run()
    assert app.session_state["active_practice_insights"]["session_seconds"] == paused_total
    app.button(key="focus_pause_s").click().run()
    assert not app.exception
    active = app.session_state["active_practice_insights"]
    assert active["focus_timer"]["since"] is not None
    assert active["session_seconds"] >= paused_total
    assert clock_state(app)["running"]
    assert app.button(key="focus_pause_s").label == "Pause"


def test_no_internal_timing_rules_on_the_page():
    app, _ = start_app()
    button = app.button(key="focus_pause_s")
    shown = texts(app) + [button.label, button.help or ""] + [b.label for b in app.button]
    shown = [visible_text(value) for value in shown]
    for rule in INTERNAL_RULES:
        assert not any(rule in value.lower() for value in shown), rule
    app.button(key="focus_pause_s").click().run()
    button = app.button(key="focus_pause_s")
    assert not any(rule in f"{button.label} {button.help}".lower() for rule in INTERNAL_RULES)


# 8 · Chinese interface ------------------------------------------------------------------

@pytest.mark.parametrize("make", [lambda: start_app()[0], mock_app])
def test_header_is_fully_chinese_with_the_chinese_interface(make):
    app = make()
    app.session_state[LANGUAGE_KEY] = True
    app.run()
    assert not app.exception
    header = find_block(app, "flight_practice_progress")
    shown = [c.value for c in header.caption]
    shown += [visible_text(m.value) for m in header.markdown]
    shown += [b.label for b in header.button] + [b.help for b in header.button]
    assert shown and not [value for value in shown if re.search(r"[A-Za-z]", value)]
    state = clock_state(app)
    assert state["label"] == f"本次用时 {state['text']}"
    assert 'class="flight-clock-label">本次用时<' in clock_html(app)
    button = header.button[0]
    assert (button.label, button.help) == ("暂停", "休息时可以暂停。")
    button.click().run()
    assert find_block(app, "flight_practice_progress").button[0].label == "继续"


# 6 · CSS-only ticking ---------------------------------------------------------------------

def test_ticking_is_css_only():
    css = CSS.read_text(encoding="utf-8")
    prop = re.search(r"@property --flight-clock-run \{(.*?)\}", css, re.DOTALL).group(1)
    assert 'syntax: "<integer>";' in prop and "inherits: false;" in prop and "initial-value: 0;" in prop
    names = re.findall(r"@keyframes (flight-clock-run-\d+) \{ from \{ --flight-clock-run: 0; \} "
                       r"to \{ --flight-clock-run: 360000; \} \}", css)
    assert names == [f"flight-clock-run-{n}" for n in range(practice_insights_ui.CLOCK_RESTARTS)]
    guard = css.index("@supports (width: round(down, 5px, 2px))")
    live = css[guard:]
    assert "animation: flight-clock-run-0 360000s steps(360000, end) forwards;" in live
    assert re.search(r"counter-reset:\s+flight-clock-m round\(down, \(var\(--clock-base, 0\) \+ "
                     r"var\(--flight-clock-run, 0\)\) / 60, 1\)\s+flight-clock-s mod\(", live)
    assert 'content: counter(flight-clock-m, decimal-leading-zero) ":" counter(flight-clock-s, decimal-leading-zero);' in live
    for n in range(1, practice_insights_ui.CLOCK_RESTARTS):
        assert f".flight-clock.restart-{n} .flight-clock-time {{ animation-name: flight-clock-run-{n}; }}" in live
    # The server text hides only where the live count works, and a paused clock never ticks.
    assert ".flight-clock-static {\n    display: none;\n  }" in live
    assert "flight-clock-static" not in css[:guard]
    paused = live.index(".flight-clock.is-paused .flight-clock-time { animation: none; }")
    assert all(paused > live.index(f".flight-clock.restart-{n}") for n in range(1, practice_insights_ui.CLOCK_RESTARTS))
    assert "font-variant-numeric: lining-nums tabular-nums;" in css
    for token in ("--paper-card", "--paper-line", "--ink", "--ink-muted", "--accent-rust", "--font-title"):
        assert f"var({token}" in css


def test_no_script_fragment_timer_or_component_for_the_clock():
    for path in (PAGE, UI, CSS):
        source = path.read_text(encoding="utf-8")
        for banned in ("<script", "run_every", "st.fragment", "components.html", "st.html(", "setInterval"):
            assert banned not in source, (path.name, banned)


def test_header_layout_wraps_on_phones():
    css = CSS.read_text(encoding="utf-8")
    track = re.search(r'\.st-key-flight_practice_progress > \[data-testid="stLayoutWrapper"\]'
                      r':has\(> \.st-key-flight_progress_track\) \{(.*?)\}', css, re.DOTALL).group(1)
    assert "flex: 1 1 9rem;" in track and "min-width: 0;" in track
    clock = re.search(r"\n\.flight-clock \{(.*?)\}", css, re.DOTALL).group(1)
    assert "white-space: nowrap;" in clock and "display: inline-flex;" in clock
    assert "width" not in clock  # sized by its short content, so it fits a 375px screen


def test_clock_state_survives_a_draft_round_trip():
    from services.learning_flow import install_practice, resume_draft
    app, _ = start_app()
    old = deepcopy(app.session_state["active_practice_insights"])
    old["session_seconds"] = 250.0
    replacement = {**deepcopy(old), "session": old["session"].model_copy(update={"session_id": "replacement"})}
    state = {"active_practice_insights": old}
    install_practice(state, "insights", replacement)
    resume_draft(state, "insights", "s")
    resumed = state["active_practice_insights"]
    assert resumed["session_seconds"] == 250.0 and resumed["focus_timer"]["since"] is None
