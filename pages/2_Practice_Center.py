from services.ui_help import help_heading
from services.i18n import tr
from html import escape
import time

import streamlit as st

from services.account_sync import render_last_save_status, save_exam_to_account
from services.accessibility import display_question, display_text
from services.question_editor import available_questions
from services.exam_engine import create_exam, grade_exam
from services.guided_limits_ui import render_guided_review
from services.hints import hint_state_key, hints_for
from services.question_review import create_mistake_review, mistake_questions
from services.practice_insights_ui import (
    start_focus_controls, answer_controls, checklist, capture_submission,
    result_overview,
)
from services.practice_insights import focus_question
from services.practice_pages_ui import (
    ANSWER_REVIEW_PAGE, HISTORY_PAGE, has_practice_history, history_visit_key, page_turn_key,
    render_question_heading,
)
from services.auth_session import current_user
from services import learning_radar
from components.knowledge_graph import load_course_radar, render_topic_radar
from components.page_links import open_page_button
from services.learning_flow import install_practice, remember_widget, hydrate_widgets, open_lab
from services.ui_style import apply_app_styles

try:
    from components import radar_chart
except ImportError:  # merged later
    radar_chart = None

# "All missed topics" choice of the review-topic pills; it means no topic filter.
ALL_MISSED_TOPICS = "__all_missed_topics__"
# Up to this many confirmed topics, the knowledge point is a row of one-click pills.
TOPIC_PILLS_LIMIT = 6
DEFAULT_COUNT = 10
MAX_COUNT = 50

# The page shows one screen at a time:
#   setup    - mode, knowledge point, number of questions;
#   question - one question of the session in progress, nothing else;
#   review   - the check before submitting (active["worksheet_step"] == "review");
#   result   - the graded session, without the per-question answers.
# practice_setup_<course> holds the id of the session for which the student asked
# for the setup screen; any other session (a new one, a resumed one) ignores it.
# Unfinished and graded sessions are listed on the Practice history page, and the
# answers of a result on the Review answers page.


def current_session(practice_key, session_id, *, graded):
    """The open practice, if it is still the session a button was drawn for.

    A late or repeated click can arrive after another session was opened; it is ignored.
    """
    active = st.session_state.get(practice_key)
    if not active or active["session"].session_id != session_id or ("result" in active) != graded:
        return None
    return active


def submit_practice(course, practice_key, session_id):
    active = current_session(practice_key, session_id, graded=False)
    if active is None:
        return
    session, questions = active["session"], active["questions"]
    hydrate_widgets(st.session_state, active)
    answers = {q.id: st.session_state.get(f"answer_{session.session_id}_{q.id}") for q in questions}
    try:
        result = grade_exam(session, questions, answers)
    except ValueError:
        st.session_state["practice_submit_error"] = True
        return
    updated = capture_submission(course, active)
    active["result"] = result
    history = st.session_state.setdefault(f"practice_history_{course.course_id}", {})
    history[session.session_id] = {
        "session": session, "questions": questions.copy(),
        "attempts": result["attempts"].copy(), "result": result,
    }
    save_exam_to_account(st.session_state, updated, session, result["attempts"])


def begin_mistake_review(practice_key, course, session, questions, confirmed_ids, topic_id):
    graded = current_session(practice_key, session.session_id, graded=True)
    if graded is None:
        return  # a second click: the review session is already open
    try:
        install_practice(st.session_state, course.course_id, create_mistake_review(
            session, questions, graded["result"]["attempts"],
            confirmed_ids, topic_id, approved_ids={q.id for q in available_questions(course)},
        ))
    except ValueError as error:
        st.session_state["practice_launch_error"] = str(error)
    else:
        st.session_state.pop(f"practice_setup_{course.course_id}", None)


# ---- Screen changes (button callbacks; they run before the page) -------------------

def open_setup(course_id, session_id):
    """Show the setup screen; the session itself stays exactly as it is."""
    st.session_state[f"practice_setup_{course_id}"] = session_id


def return_to_session(course_id):
    st.session_state.pop(f"practice_entry_{course_id}", None)
    st.session_state.pop(f"practice_setup_{course_id}", None)


# The setup screen keeps the student's choice in a plain key, practice_choice_<course>
# ({"mode", "topic_id", "count"}), updated by the widgets' on_change. Each run that draws
# the screen assigns the three widget keys from it before the widgets, so the browser
# always shows the value the page uses (Streamlit sends a value to the browser only when
# the key is assigned in the run that draws the widget).

def choice_key(course_id):
    return f"practice_choice_{course_id}"


def opening_choice(course_id, confirmed_topic_ids, active, pending_entry):
    """What the setup screen shows when it opens, in this order of preference: a request
    staged by another page, the open session's settings, the student's last choice, the
    defaults."""
    choice = {"mode": "mock", "topic_id": confirmed_topic_ids[0], "count": DEFAULT_COUNT}
    settings = (active or {}).get("settings") or {}
    staged_topic = (pending_entry or {}).get("topic_id")
    if staged_topic:
        staged = {"mode": "topic", "topic_id": staged_topic}
    elif pending_entry is not None:
        # "New practice for your confirmed topics": across the whole scope, so a mock exam.
        staged = {"mode": "mock"}
    else:
        staged = {}
    sources = (  # lowest preference first; later ones win
        st.session_state.get(choice_key(course_id)) or {},
        {"mode": settings.get("mode"), "topic_id": settings.get("topic_id"), "count": settings.get("requested_count")},
        staged,
    )
    for source in sources:
        if source.get("mode") in ("mock", "topic"):
            choice["mode"] = source["mode"]
        if source.get("topic_id") in confirmed_topic_ids:
            choice["topic_id"] = source["topic_id"]
        count = source.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= MAX_COUNT:
            choice["count"] = count
    return choice


def remember_choice(course_id, field, confirmed_topic_ids):
    """on_change of a setup widget: keep the new value as the student's choice."""
    choice = st.session_state.setdefault(choice_key(course_id), {})
    value = st.session_state.get(f"practice_{field}_{course_id}")
    if field == "mode":
        choice["mode"] = "mock" if value == tr("Mock Exam") else "topic"
    elif field == "topic":
        if value in confirmed_topic_ids:  # clicking the chosen pill again keeps it
            choice["topic_id"] = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        choice["count"] = int(value)


def shown_settings(course_id, confirmed_topic_ids):
    """The settings Start uses: the widgets' latest values, which are what the screen shows.

    The knowledge point counts only if it was on screen; otherwise it is the kept choice,
    which is what the screen shows as soon as Topic Practice is chosen.
    """
    state = st.session_state
    choice = state.get(choice_key(course_id)) or {}
    mode = "mock" if state.get(f"practice_mode_{course_id}", tr("Mock Exam")) == tr("Mock Exam") else "topic"
    topic_id = None
    if mode == "topic":
        shown = state.get(f"practice_topic_{course_id}") if state.get(f"practice_topic_drawn_{course_id}") else None
        topic_id = next((value for value in (shown, choice.get("topic_id"))
                         if value in confirmed_topic_ids), confirmed_topic_ids[0])
    count = state.get(f"practice_count_{course_id}")
    if not isinstance(count, (int, float)) or isinstance(count, bool):
        count = choice.get("count", DEFAULT_COUNT)
    return mode, topic_id, int(count)


def start_practice(course, confirmed_topic_ids, session_id):
    """Start button: a new session from the settings on screen."""
    state = st.session_state
    course_id = course.course_id
    active = state.get(f"active_practice_{course_id}")
    if (active["session"].session_id if active else None) != session_id:
        return  # a second click: the new session is already open
    mode, topic_id, requested_count = shown_settings(course_id, confirmed_topic_ids)
    try:
        exam = create_exam(
            package=course,
            mode=mode,
            requested_count=requested_count,
            confirmed_topic_ids=list(confirmed_topic_ids),
            topic_id=topic_id,
        )
    except ValueError:
        state["practice_create_error"] = True
        return
    install_practice(state, course_id, {
        "settings": {
            "mode": mode,
            "requested_count": requested_count,
            "confirmed_topic_ids": sorted(confirmed_topic_ids),
            "topic_id": topic_id,
        },
        "session": exam["session"],
        "questions": exam["questions"],
        "warning": exam["warning"],
    })
    state.pop(f"practice_setup_{course_id}", None)


def move_question(practice_key, session_id, step):
    """Previous / Next: one question, never out of range (a late click changes nothing)."""
    active = current_session(practice_key, session_id, graded=False)
    if active is None:
        return
    questions = active["questions"]
    current = max(0, min(active.get("worksheet_index", 0), len(questions) - 1))
    target = max(0, min(len(questions) - 1, current + step))
    if target == current:
        return
    active["worksheet_index"] = target
    # Read once by the next render: it names the page-turn (see paper_practice.css).
    active["worksheet_move"] = "next" if step > 0 else "prev"
    active["worksheet_turns"] = active.get("worksheet_turns", 0) + 1
    timer = active.get("focus_timer", {})
    if timer.get("since") is not None:
        focus_question(active, questions[target].id, time.monotonic())
    elif timer:
        timer["question_id"] = questions[target].id


def open_review(practice_key, session_id):
    active = current_session(practice_key, session_id, graded=False)
    if active is not None:
        active["worksheet_step"] = "review"


def close_review(practice_key, session_id):
    active = current_session(practice_key, session_id, graded=False)
    if active is not None:
        active.pop("worksheet_step", None)


def toggle_side_panel(course_id):
    key = f"practice_side_panel_{course_id}"
    st.session_state[key] = not st.session_state.get(key, True)


def toggle_original_wording(state_key):
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def tell_browser(*keys):
    """Assign each widget key again in this run, before its widget is drawn.

    The browser is told a widget's value only when its key was assigned in the
    run that draws the widget. A value restored in an earlier run (a question
    that was off screen, a resumed session) is used by the script while the
    browser shows an empty widget, and the next click then saves that empty
    value over the student's answer. Writing the current value back changes
    nothing in the session and makes the browser agree with it.
    """
    for key in keys:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def follow_question(active, question_id):
    """The focus timer follows the question on screen; a paused timer stays paused."""
    timer = active.get("focus_timer")
    if timer is None or (timer.get("since") is not None and timer.get("question_id") != question_id):
        focus_question(active, question_id, time.monotonic())
    elif timer.get("question_id") != question_id:
        timer["question_id"] = question_id


# ---- Screens ------------------------------------------------------------------------

def setup_heading():
    help_heading(tr("Practice"), tr("Choose a mode, then focus on one question at a time."), level='title')


def choose_topic(course_id, confirmed_topic_ids, topic_names):
    """Knowledge point: one-click pills for a short scope, a selectbox for a long one."""
    widget = st.selectbox if len(confirmed_topic_ids) > TOPIC_PILLS_LIMIT else st.pills
    options = {"selection_mode": "single"} if widget is st.pills else {}
    widget(
        tr("Knowledge point"),
        options=confirmed_topic_ids,
        format_func=lambda value: topic_names[value],
        key=f"practice_topic_{course_id}",
        on_change=remember_choice, args=(course_id, "topic", confirmed_topic_ids),
        **options,
    )


def render_setup_screen(course, confirmed_topic_ids, topic_names, active_practice, pending_entry, opening):
    cid = course.course_id
    in_progress = active_practice is not None and "result" not in active_practice
    choice = st.session_state.get(choice_key(cid))
    if opening or not isinstance(choice, dict):
        choice = st.session_state[choice_key(cid)] = opening_choice(
            cid, confirmed_topic_ids, active_practice, pending_entry)
    if choice.get("topic_id") not in confirmed_topic_ids:  # the scope changed since
        choice["topic_id"] = confirmed_topic_ids[0]
    # Assigned in the run that draws the widgets, so the browser shows what Start uses.
    st.session_state[f"practice_mode_{cid}"] = tr("Topic Practice") if choice["mode"] == "topic" else tr("Mock Exam")
    st.session_state[f"practice_count_{cid}"] = choice["count"]
    st.session_state[f"practice_topic_drawn_{cid}"] = choice["mode"] == "topic"
    if choice["mode"] == "topic":
        st.session_state[f"practice_topic_{cid}"] = choice["topic_id"]

    setup_heading()
    if pending_entry is not None:
        target = pending_entry.get("topic_id")
        st.info(
            (tr("New practice: ") + topic_names[target]) if target
            else tr("New practice for your confirmed topics.")
        )
    if in_progress or (pending_entry is not None and active_practice is not None):
        st.button(
            tr("Return to your session") if in_progress else tr("Return to previous session"),
            icon=":material/arrow_back:", key="practice_return_previous",
            on_click=return_to_session, args=(course.course_id,),
        )

    with st.container(border=True, key="practice_setup"):
        st.caption(
            tr("Confirmed topics") + ": "
            + " · ".join(topic_names[value] for value in confirmed_topic_ids)
        )
        st.radio(
            tr("Practice mode"),
            options=[tr("Mock Exam"), tr("Topic Practice")],
            key=f"practice_mode_{cid}",
            horizontal=True,
            width="stretch",
            on_change=remember_choice, args=(cid, "mode", confirmed_topic_ids),
        )

        if choice["mode"] == "topic":
            choose_topic(cid, confirmed_topic_ids, topic_names)

        # No default value: the key is always assigned above.
        st.number_input(
            tr("Number of questions"),
            min_value=1,
            max_value=MAX_COUNT,
            step=1,
            key=f"practice_count_{cid}",
            width=240,
            on_change=remember_choice, args=(cid, "count", confirmed_topic_ids),
        )

        start_label = (
            "Start new practice"
            if active_practice is not None
            else "Start practice"
        )
        # A callback, so the next run already draws the new session's question screen.
        st.button(
            tr(start_label), type="primary", key=f"practice_start_{cid}",
            on_click=start_practice,
            args=(course, confirmed_topic_ids, active_practice["session"].session_id if active_practice else None),
        )
        if st.session_state.pop("practice_create_error", None):
            st.error(tr("Could not create practice. Try another topic or check your exam scope in Study Plan."))

    # Unfinished and graded sessions are listed on a page of their own.
    if has_practice_history(st.session_state, course.course_id):
        open_page_button(
            tr("Practice history"), HISTORY_PAGE, key="open_practice_history",
            icon=":material/history:", align="right",
        )


def practice_title(session, question, topic_names):
    if session.mode == "mock":
        return tr(f"Practice · {tr('Mock Exam')}")
    return tr(f"Practice · {topic_names.get(question.topic_id, tr('Topic'))}")


def render_question_screen(course, active, topic_names):
    """One question of the session in progress, and only what answering it needs."""
    practice_key = f"active_practice_{course.course_id}"
    session, questions = active["session"], active["questions"]
    sid = session.session_id
    index = max(0, min(active.get("worksheet_index", 0), len(questions) - 1))
    question = questions[index]
    follow_question(active, question.id)
    tell_browser(f"answer_{sid}_{question.id}", f"confidence_{sid}_{question.id}")

    radar_on = learning_radar.radar_enabled(course.course_id)
    user = current_user(st.session_state) if radar_on else None
    # The "I'm stuck" choices are only offered to signed-in users of demo courses.
    offer_stuck = radar_chart is not None and user is not None
    topic = next((topic for topic in course.topics if topic.id == question.topic_id), None)
    # Mock Exam keeps exam conditions: no notes, as there are no hints.
    notes = session.mode == "topic" and topic is not None
    has_panel = radar_on or notes
    panel_shown = has_panel and st.session_state.get(f"practice_side_panel_{course.course_id}", True)

    if has_panel:
        st.markdown(f'<span class="practice-panel-state" data-open="{str(panel_shown).lower()}"></span>', unsafe_allow_html=True)
        paper, margin = st.columns([3, 1], gap="large")
    else:
        paper, margin = st.container(key="practice_main_full"), None

    with paper:
        with st.container(key="practice_title_row", horizontal=True, vertical_alignment="center"):
            st.title(practice_title(session, question, topic_names))
            with st.container(
                key="practice_title_tools", horizontal=True, width="content",
                vertical_alignment="center", gap="small",
            ):
                with st.popover(
                    tr("This session"), icon=":material/more_horiz:", type="tertiary",
                    key=f"practice_session_menu_{sid}",
                ):
                    st.button(
                        tr("Review and submit"), icon=":material/fact_check:", width="stretch",
                        key=f"worksheet_review_{sid}", on_click=open_review, args=(practice_key, sid),
                    )
                    st.button(
                        tr("Change settings"), icon=":material/tune:", width="stretch",
                        key=f"practice_change_settings_{sid}", on_click=open_setup,
                        args=(course.course_id, sid),
                    )
                if has_panel:
                    st.button(
                        tr("Hide side panel") if panel_shown else tr("Show side panel"),
                        icon=":material/right_panel_close:" if panel_shown else ":material/right_panel_open:",
                        type="tertiary", key=f"practice_side_panel_toggle_{course.course_id}",
                        on_click=toggle_side_panel, args=(course.course_id,),
                    )

        with st.container(key="flight_worksheet"):
            if active.get("transfer_from"):
                st.badge(tr("Transfer practice") + " · " + tr("Same topic · Different structure"))
            # One row above the question: counter · flight path · session clock (wraps on phones).
            with st.container(key="flight_practice_progress", horizontal=True, vertical_alignment="center"):
                with st.container(key="flight_progress_count", width="content"):
                    st.caption(tr("Question") + f" {index + 1:02} / {len(questions):02}")
                with st.container(key="flight_progress_track"):
                    from services.paper_progress import progress_route
                    route_key = f'practice_route_index_{sid}'
                    st.markdown(progress_route(index, len(questions), st.session_state.get(route_key)),
                                unsafe_allow_html=True)
                    st.session_state[route_key] = index
                with st.container(
                    key="flight_progress_clock", horizontal=True, width="content", vertical_alignment="center",
                    gap="xsmall",
                ):
                    start_focus_controls(active)

            if active.get("focus_timer", {}).get("since") is None:
                with st.container(key="practice_paused_notice"):
                    st.markdown('<p role="status">' + escape(tr("Timer paused. Your answers are kept. Resume above when you are ready.")) + '</p>', unsafe_allow_html=True)

            if active.get("warning") and index == 0:
                st.caption(tr(active["warning"]))

            # The key names the last move and alternates a/b, so the stylesheet replays the
            # page-turn only when the question changes; any other rerun renders "none".
            turn_key = page_turn_key(active.pop("worksheet_move", None), active.get("worksheet_turns", 0), sid)
            display = display_question(course.course_id, question, st.session_state)
            hints = hints_for(question) if session.mode == "topic" else []
            state_key = hint_state_key(sid, question.id)
            shown = st.session_state.get(state_key, 0) if hints else 0
            with st.container(key=turn_key), st.container(key=f"practice_question_{question.id}"):
                render_question_heading(index + 1, display.question)
                if display.simplified:
                    st.caption(tr("Simplified wording"))
                    # Revealed in place by one quiet button; not on the page until asked for.
                    original_key = f"practice_original_shown_{sid}_{question.id}"
                    original_shown = st.session_state.get(original_key, False)
                    with st.container(horizontal=True, key=f"original_wording_row_{question.id}"):
                        st.button(
                            tr("Hide original wording") if original_shown else tr("Show original wording"),
                            icon=":material/visibility_off:" if original_shown else ":material/visibility:",
                            type="tertiary", key=f"original_wording_toggle_{sid}_{question.id}",
                            on_click=toggle_original_wording, args=(original_key,),
                        )
                    if original_shown:
                        with st.container(key=f"original_text_{question.id}"):
                            st.write(question.question)
                            for option in question.options:
                                st.write(option)

                st.radio(
                    tr("Choose an answer"),
                    options=list(range(len(question.options))),
                    format_func=lambda option, options=display.options: (
                        f"{chr(ord('A') + option)}. {options[option]}"
                    ),
                    index=None,
                    width="stretch",
                    key=f"answer_{sid}_{question.id}",
                    on_change=remember_widget,
                    args=(st.session_state, course.course_id, sid, f"answer_{sid}_{question.id}"),
                )

                answer_controls(active, question, course.course_id)

                for number, hint in enumerate(hints[:shown], start=1):
                    st.info(tr(f"Hint {number} of {len(hints)}: {display_text(hint, st.session_state)}"))

            # Actions under the question: Previous · Hint · Learning Radar · Next (or Finish).
            with st.container(
                horizontal=True, horizontal_alignment="distribute",
                vertical_alignment="center", key=f"paper_actions_{question.id}",
            ):
                st.button(
                    tr("Previous"), icon=":material/arrow_back:", disabled=index == 0,
                    key=f"worksheet_previous_{sid}", on_click=move_question, args=(practice_key, sid, -1),
                )
                if shown < len(hints) and st.button(
                    tr("Hint") if shown == 0 else tr("Next hint"), icon=":material/lightbulb:",
                    key=f"hint_button_{sid}_{question.id}",
                ):
                    st.session_state[state_key] = shown + 1
                    remember_widget(st.session_state, course.course_id, sid, state_key)
                    st.rerun()
                if offer_stuck:
                    with st.popover(
                        tr("Learning Radar"), icon=":material/radar:",
                        key=f"practice_radar_menu_{sid}_{question.id}",
                    ):
                        radar_chart.render_stuck_buttons(
                            st.session_state, course.course_id, question.topic_id, user.user_id,
                            key=f"practice_stuck_{sid}_{question.id}",
                        )
                if index == len(questions) - 1:
                    st.button(
                        tr("Finish"), icon=":material/flag:", type="primary",
                        key=f"worksheet_finish_{sid}", on_click=open_review, args=(practice_key, sid),
                    )
                else:
                    st.button(
                        tr("Next"), icon=":material/arrow_forward:", icon_position="right", type="primary",
                        key=f"worksheet_next_{sid}", on_click=move_question, args=(practice_key, sid, 1),
                    )

    if margin is not None:
        with margin, st.container(key="flight_worksheet_margin"):
            if radar_on:
                st.subheader(tr("Learning Radar"))
                radar, _ = load_course_radar(st.session_state, course.course_id, user.user_id if user else None)
                if radar_chart is not None:
                    # Chart only: the count below already says when sample data is included.
                    radar_chart.render_radar_figure(
                        course, radar, focus_topic_id=question.topic_id, key="practice_radar",
                    )
                render_topic_radar(radar.topics.get(question.topic_id))
                if st.button(tr("Explore this topic"), key=f"worksheet_radar_{sid}"):
                    st.session_state[f"graph_pending_focus_{course.course_id}"] = question.topic_id
                    st.switch_page("pages/4_Knowledge_Graph.py")
                if notes:
                    st.divider()
            if notes:
                st.subheader(tr("Quick Notes"))
                st.caption(topic.name)
                st.write(display_text(topic.summary, st.session_state))


def render_review_step(course, active):
    """The check before submitting: every question counts, not only the one last on screen."""
    practice_key = f"active_practice_{course.course_id}"
    session, questions = active["session"], active["questions"]
    sid = session.session_id
    st.title(tr("Practice · Review"))
    answered = sum(st.session_state.get(f"answer_{sid}_{question.id}") is not None for question in questions)
    st.markdown(tr(f"{answered} of {len(questions)} answered"))
    checklist(active)
    with st.container(
        horizontal=True, horizontal_alignment="distribute",
        vertical_alignment="center", key="practice_review_actions",
    ):
        st.button(
            tr("Back to questions"), icon=":material/arrow_back:",
            key=f"worksheet_back_{sid}", on_click=close_review, args=(practice_key, sid),
        )
        st.button(
            tr("Submit answers"), type="primary", key=f"practice_submit_{sid}",
            on_click=submit_practice, args=(course, practice_key, sid),
        )
    if st.session_state.pop("practice_submit_error", None):
        st.error(tr("Could not grade this practice. Please try again."))


def render_result_screen(course, active_practice, confirmed_topic_ids, topic_names):
    practice_key = f"active_practice_{course.course_id}"
    session = active_practice["session"]
    questions = active_practice["questions"]
    mode_name = "Mock Exam" if session.mode == "mock" else "Topic Practice"

    with st.container(key="practice_title_row", horizontal=True, vertical_alignment="center"):
        st.title(tr("Practice"))
        with st.container(key="practice_title_tools", horizontal=True, width="content", vertical_alignment="center"):
            st.button(
                tr("New practice"), icon=":material/add:", key=f"practice_new_{course.course_id}",
                on_click=open_setup, args=(course.course_id, session.session_id),
            )

    st.subheader(tr("Practice session"))
    with st.container(border=True, key="practice_overview"):
        overview = st.columns([3, 1.25, 0.7])
        with overview[0]:
            st.caption(tr("Course"))
            with st.container(key="practice_course_heading"):
                st.markdown(f"**{escape(course.course_name)}**")
        with overview[1]:
            st.caption(tr("Mode"))
            st.markdown(f"**{tr(mode_name)}**")
        with overview[2]:
            st.caption(tr("Questions"))
            st.markdown(f"**{len(questions)}**")

    if active_practice.get("warning"):
        # A note about the session, as on the question screen; not a warning box.
        st.caption(tr(active_practice["warning"]))

    result = active_practice["result"]
    render_last_save_status()

    st.subheader(tr("Your result"))
    if st.session_state.get(f"course_stage_{course.course_id}") == "questions_generated":
        st.caption(tr("AI-generated questions: verify the answer and explanation against your material."))
    missed_ids = {attempt.question_id for attempt in result["attempts"] if not attempt.is_correct}
    next_question = next((q for q in questions if q.id in missed_ids), questions[0])
    with st.container(key="practice_result_overview"):
        stats, next_step = st.columns([1, 1.6], gap="large", vertical_alignment="center")
        with stats:
            with st.container(border=True, key="result_score"):
                st.metric(tr("Score"), f"{result['correct_count']} / {result['total_count']}")
            with st.container(border=True, key="result_accuracy"):
                st.metric(tr("Accuracy"), f"{result['accuracy']:.2f}%")
        with next_step, st.container(border=True, key="flight_next_topic"):
            st.subheader(tr("Take the next step"))
            st.markdown(f"**{escape(topic_names.get(next_question.topic_id, tr('Topic')))}**")
            if next_question.topic_id in topic_names and st.button(
                tr("Open this topic in Knowledge Map"), key=f"flight_map_{session.session_id}", icon=":material/hub:",
            ):
                st.session_state[f"graph_pending_focus_{course.course_id}"] = next_question.topic_id
                st.switch_page("pages/4_Knowledge_Graph.py")
            if course.course_id == "calculus-i-demo" and next_question.topic_id in {"calc_limits", "calc_derivatives"}:
                if st.button(tr("Explore this topic in Concept Lab"), key=f"flight_lab_{session.session_id}"):
                    open_lab(st.session_state, course.course_id, next_question.topic_id)
                    st.switch_page("pages/6_Concept_Lab.py")
    with st.container(horizontal=True, horizontal_alignment="center", key="result_review_action"):
        if st.button(tr("Review answers"), key="open_answer_review", icon=":material/fact_check:",
                     type="primary", width=352):
            st.switch_page(ANSWER_REVIEW_PAGE)
    guided_review_available = render_guided_review(course, session, questions, result)
    result_overview(course, session, questions, result)

    with st.container(border=True, key="practice_mistake_review"):
        try:
            missed = mistake_questions(session, questions, result["attempts"])
        except ValueError:
            missed = []
            st.warning(tr("This result could not be prepared for mistake review."))
        if missed:
            st.markdown(tr("**Review missed questions**"))
            st.caption(
                tr("1 missed question to practise; your score stays the same.") if len(missed) == 1
                else tr(f"{len(missed)} missed questions to practise; your score stays the same.")
            )
            missed_topics = list(dict.fromkeys(q.topic_id for q in missed if q.topic_id in confirmed_topic_ids))
            review_choice = st.pills(
                tr("Review topic"), [ALL_MISSED_TOPICS, *missed_topics], default=ALL_MISSED_TOPICS,
                format_func=lambda value: tr("All missed topics") if value == ALL_MISSED_TOPICS else topic_names[value],
                key=f"mistake_topic_{course.course_id}_{session.session_id}",
            )
            # No pill, or the "All missed topics" pill, keeps every missed topic.
            review_topic = None if review_choice in (None, ALL_MISSED_TOPICS) else review_choice
            st.button(
                tr("Practise missed questions"), type="secondary" if guided_review_available else "primary",
                key=f"review_mistakes_{session.session_id}",
                on_click=begin_mistake_review,
                args=(practice_key, course, session, questions, confirmed_topic_ids, review_topic),
            )
            if error := st.session_state.pop("practice_launch_error", None):
                st.error(tr(error))
        else:
            st.caption(tr("No missed questions to review in this session."))


# ---- Page ---------------------------------------------------------------------------

apply_app_styles()

course = st.session_state.get("current_course")

if course is None:
    setup_heading()
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

confirmed_key = f"confirmed_scope_{course.course_id}"
confirmed_topic_ids = st.session_state.get(confirmed_key)

if not confirmed_topic_ids:
    setup_heading()
    st.warning(tr("Confirm your exam scope in Study Plan first."))
    if st.button(tr("Choose exam scope"), type="primary"):
        st.switch_page("pages/1_Study_Hub.py")
    st.stop()

# Validate the confirmed scope before offering practice settings.
topic_names = {topic.id: topic.name for topic in course.topics}

if (
    len(confirmed_topic_ids) != len(set(confirmed_topic_ids))
    or not set(confirmed_topic_ids).issubset(topic_names)
):
    setup_heading()
    st.error(tr("The confirmed scope is invalid. Confirm it again in Study Plan."))
    st.page_link("pages/1_Study_Hub.py", label=tr("Go to Study Plan"))
    st.stop()

practice_key = f"active_practice_{course.course_id}"
active_practice = st.session_state.get(practice_key)
pending_entry = st.session_state.get(f"practice_entry_{course.course_id}")
st.session_state.pop("priority_ready", None)

# app.py sets this flag when the student arrives from another page: the page then opens
# the session (or its result) again rather than a setup screen asked for earlier. The
# exception is the way back from Practice history, which is opened from the setup screen.
arrived = st.session_state.pop(f"rehydrate_practice_{course.course_id}", False)
back_from_history = st.session_state.pop(history_visit_key(course.course_id), False)
setup_request_key = f"practice_setup_{course.course_id}"
setup_request = st.session_state.get(setup_request_key)
if setup_request is not None and (
    (arrived and not back_from_history)
    or active_practice is None or setup_request != active_practice["session"].session_id
):
    st.session_state.pop(setup_request_key, None)
    setup_request = None

in_progress = active_practice is not None and "result" not in active_practice
if in_progress:
    # Answers, confidence and hints of questions that are not on screen live in the drafts.
    hydrate_widgets(st.session_state, active_practice, force=arrived)

if active_practice is None or pending_entry is not None or setup_request is not None:
    screen = "setup"
elif not in_progress:
    screen = "result"
elif active_practice.get("worksheet_step") == "review":
    screen = "review"
else:
    screen = "question"
# The setup screen "opens" when it was not on screen in this page's last run.
screen_key = f"practice_screen_{course.course_id}"
opening = arrived or st.session_state.get(screen_key) != screen
st.session_state[screen_key] = screen

if screen == "setup":
    render_setup_screen(course, confirmed_topic_ids, topic_names, active_practice, pending_entry, opening)
elif screen == "result":
    render_result_screen(course, active_practice, confirmed_topic_ids, topic_names)
elif screen == "review":
    render_review_step(course, active_practice)
else:
    render_question_screen(course, active_practice, topic_names)
