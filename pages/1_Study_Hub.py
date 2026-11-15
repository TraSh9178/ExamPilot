from services.ui_help import help_heading
from services.i18n import tr
import streamlit as st

from components.knowledge_graph import load_course_radar, radar_count_text, radar_display_order
from components.page_links import open_page_button
from models.schemas import StudyPackage
from services import learning_radar
from services.account_sync import SAVE_FAILED_MESSAGE, save_course_to_account
from services.auth_session import current_user
from services.question_editor import available_questions, status_for
from services.course_state import save_course
from services.ai_service import generate_questions, generation_available
from services.ui_style import apply_app_styles
from services.learning_flow import stage_practice

apply_app_styles()

help_heading(tr("Study Plan"), tr("Review course topics and choose the scope for your exam."), level='title')

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard to start studying."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

with st.container(key="study_plan_overview"):
    st.subheader(course.course_name)
    st.caption(tr(f"{len(course.topics)} knowledge points"))

# Keep scope confirmation separate for each course.
scope_key = f"scope_selection_{course.course_id}"
confirmed_key = f"confirmed_scope_{course.course_id}"
save_failed_notice_key = f"study_save_failed_notice_{course.course_id}"
# Hydrate widgets on first entry, before their frontend defaults can clear
# the separately saved confirmation. Subsequent edits still require confirmation.
initialised_key = f"scope_initialised_{course.course_id}"
draft_key = f"scope_draft_{course.course_id}"
if not st.session_state.get(initialised_key, False):
    saved_scope = st.session_state.get(confirmed_key, course.learning_state.get("confirmed_scope"))
    if saved_scope:
        st.session_state[confirmed_key] = list(saved_scope)
        st.session_state[scope_key] = list(saved_scope)
    # Back from Topic summaries or Course tools: the selection as the student
    # left it, unless the saved scope it was made against has changed since.
    draft = st.session_state.pop(draft_key, None)
    if draft is not None and draft["saved"] == list(course.learning_state.get("confirmed_scope") or []):
        valid_ids = {topic.id for topic in course.topics}
        st.session_state[scope_key] = [topic_id for topic_id in draft["selection"] if topic_id in valid_ids]
    st.session_state[initialised_key] = True
# Restore the selection when returning from another page.
if scope_key not in st.session_state:
    st.session_state[scope_key] = list(
        st.session_state.get(confirmed_key, [])
    )

def keep_scope_selection(course_id: str) -> None:
    """Runs on the click that opens Topic summaries or Course tools.

    Those pages do not draw the scope pills, so Streamlit would forget a
    selection that is not confirmed yet. Put it aside, with the saved scope it
    was made against, for the way back.
    """
    selection = st.session_state.get(f"scope_selection_{course_id}")
    current = st.session_state.get("current_course")
    if selection is not None and current is not None:
        st.session_state[f"scope_draft_{course_id}"] = {
            "selection": list(selection),
            "saved": list(current.learning_state.get("confirmed_scope") or []),
        }


def render_most_flagged_topics(course, confirmed_key: str) -> None:
    """Show a demo course's three most flagged topics with a practice shortcut.

    The radar comes from the session cache shared with the Knowledge Map, so
    reruns of this page do not query the database again.
    """
    user = current_user(st.session_state)
    radar, _ = load_course_radar(
        st.session_state,
        course.course_id,
        user.user_id if user is not None else None,
    )
    topic_names = {topic.id: topic.name for topic in course.topics}
    # Ranked for display first, then cut to three, so neither the order nor the
    # cut reveals a count hidden by the privacy rule.
    most_flagged = [
        topic_radar
        for topic_radar in radar_display_order(
            learning_radar.top_hard_topics(radar, limit=max(3, len(radar.topics))),
            list(topic_names),
        )
        if topic_radar.real_count + topic_radar.sample_count > 0
    ][:3]

    with st.container(border=True, key="study_radar_panel"):
        help_heading(tr("Most flagged topics · Top 3"), tr("Topics students marked \"I'm stuck here\" on the Knowledge Map."))
        if not most_flagged:
            st.caption(tr("No topics have been flagged yet."))
        for rank, topic_radar in enumerate(most_flagged, start=1):
            topic_id = topic_radar.topic_id
            topic_name = topic_names[topic_id]
            row = st.columns([3, 1], vertical_alignment="center")
            row[0].markdown(
                f"**{rank}. {topic_name}** — {tr(radar_count_text(topic_radar))}"
            )
            if row[1].button(
                tr("Practice now"),
                key=f"study_radar_practice_{course.course_id}_{topic_id}",
            ):
                # Topic Practice only offers topics from the confirmed scope.
                if topic_id in (st.session_state.get(confirmed_key) or []):
                    stage_practice(st.session_state, course, topic_id)
                    st.switch_page("pages/2_Practice_Center.py")
                else:
                    st.info(
                        tr(f"Confirm {topic_name} in your exam scope above, "
                        "then select Practice now again.")
                    )
        if radar.has_sample:
            st.caption(tr("Includes sample data"))


if not course.topics:
    st.info(tr("This course has no topics yet."))
else:
    # The summaries have a page of their own; a small button on the left opens it.
    open_page_button(
        tr("Topic summaries"), "pages/10_Topic_Summaries.py",
        key="open_topic_summaries",
        icon=":material/menu_book:", align="left",
        on_click=keep_scope_selection, args=(course.course_id,),
    )

with st.container(border=True, key="study_scope_panel"):
    st.subheader(tr("Choose your exam scope"))
    # One click per topic; the value stays a list of topic IDs.
    selected_topic_ids = st.pills(
        tr("Knowledge points"),
        options=[topic.id for topic in course.topics],
        format_func=lambda topic_id: next(
            topic.name
            for topic in course.topics
            if topic.id == topic_id
        ),
        selection_mode="multi",
        key=scope_key,
    )
    st.caption(
        tr(f"Selected {len(selected_topic_ids)} / {len(course.topics)} "
        "knowledge points")
    )

    if st.button(tr("Confirm exam scope"), type="primary"):
        valid_topic_ids = {topic.id for topic in course.topics}

        if not selected_topic_ids:
            st.error(tr("Select at least one topic."))
        elif len(selected_topic_ids) != len(set(selected_topic_ids)):
            st.error(tr("Each topic can be selected only once."))
        elif not set(selected_topic_ids).issubset(valid_topic_ids):
            st.error(tr("The selection contains an invalid topic."))
        else:
            st.session_state[confirmed_key] = selected_topic_ids.copy()
            sync_outcome = save_course_to_account(st.session_state, course)
            if sync_outcome is not None and not sync_outcome.success:
                # Shown after the rerun below, which would wipe it now.
                st.session_state[save_failed_notice_key] = True
            st.rerun()

if st.session_state.pop(save_failed_notice_key, False):
    st.warning(tr(SAVE_FAILED_MESSAGE))

# A changed selection requires confirmation again.
if st.session_state.get(confirmed_key) != selected_topic_ids:
    st.session_state.pop(confirmed_key, None)

confirmed_topic_ids = st.session_state.get(confirmed_key)
practice_history = st.session_state.get(
    f"practice_history_{course.course_id}", {}
)
has_practice_history = bool(practice_history)

if confirmed_topic_ids:
    topic_count = len(confirmed_topic_ids)
    topic_label = "topic" if topic_count == 1 else "topics"

    st.success(tr(f"Exam scope confirmed: {topic_count} {topic_label}."))

    document = st.session_state.get(
        f"course_document_{course.course_id}"
    )

    if document is not None:
        with st.container(border=True):
            st.subheader(tr("Questions from your material"))
            st.caption(
                tr("Generate candidate questions from this course material "
                "using only the confirmed topics. AI-generated questions "
                "may contain errors.")
            )

            if has_practice_history:
                st.warning(
                    tr("Question generation is disabled because this course "
                    "has exam history. Regenerating questions could make "
                    "those results impossible to restore.")
                )

            ai_available = generation_available()
            if not ai_available:
                st.info(tr("AI generation is unavailable right now."))

            if st.button(
                tr("Generate questions"),
                type="primary",
                disabled=has_practice_history or not ai_available,
                key=f"generate_questions_{course.course_id}",
            ):
                if has_practice_history:
                    st.error(
                        tr("Questions were not generated because this course "
                        "has exam history.")
                    )
                    st.stop()

                with st.spinner(tr("Generating questions...")):
                    generated = generate_questions(
                        document,
                        course,
                        list(confirmed_topic_ids),
                    )

                if not generated["ok"]:
                    st.error(tr(generated["message"]))
                else:
                    try:
                        updated_course = StudyPackage.model_validate(
                            generated["package"]
                        )
                    except ValueError:
                        st.error(
                            tr("Couldn't use the generated questions. Try generating them again.")
                        )
                    else:
                        st.session_state[
                            f"course_stage_{course.course_id}"
                        ] = "questions_generated"
                        save_course(st.session_state, updated_course)
                        sync_outcome = save_course_to_account(
                            st.session_state, updated_course
                        )
                        if sync_outcome is not None and not sync_outcome.success:
                            # Shown after the rerun below, which would wipe it now.
                            st.session_state[save_failed_notice_key] = True

                        # Previous practice used the old question set.
                        st.session_state.pop(
                            f"active_practice_{course.course_id}",
                            None,
                        )
                        st.rerun()

    available_count = sum(
        question.topic_id in confirmed_topic_ids
        for question in available_questions(course)
    )

    st.caption(
        tr(f"{available_count} question ready" if available_count == 1
           else f"{available_count} questions ready")
    )

    if available_count:
        active = st.session_state.get(f"active_practice_{course.course_id}")
        start_label = "Continue practice" if active and "result" not in active else "Start practice"
        if st.button(tr(start_label), type="primary"):
            if not active or "result" in active:
                stage_practice(st.session_state, course)
            else:
                st.session_state.pop(f"practice_entry_{course.course_id}", None)
            st.switch_page("pages/2_Practice_Center.py")
    elif any(status_for(course, q.id) == "pending" for q in course.questions):
        st.info(tr("Review and approve your generated questions in Course tools before starting practice."))
    elif document is not None:
        st.info(
            tr("Generate questions for the confirmed scope "
            "before starting practice.")
        )
    else:
        st.info(tr("No questions are available in the confirmed scope."))
else:
    st.info(tr("Confirm your topic selection before starting practice."))

# Learning Radar is only available for the built-in demo courses.
if learning_radar.radar_enabled(course.course_id):
    render_most_flagged_topics(course, confirmed_key)

# Question review, backups and source material are course maintenance, not a
# study step: a small button on the right opens them on a page of their own.
open_page_button(
    tr("Course tools"), "pages/9_Course_Tools.py",
    key="open_course_tools",
    icon=":material/build:", align="right",
    on_click=keep_scope_selection, args=(course.course_id,),
)
