from services.i18n import tr
from pathlib import Path

import streamlit as st
from components.knowledge_graph import (
    concept_lab_available,
    render_knowledge_graph,
    get_selected_topic_details,
    load_course_radar,
    radar_node_badges,
    render_topic_details,
    render_topic_radar,
)
from components.page_links import open_page_button
from components.radar_chart import render_stuck_buttons
from services import learning_radar
from services.account_sync import save_course_to_account
from services.ai_service import generate_relationships
from services.auth_session import current_user
from services.graph_exploration import local_graph, related_topics
from services.graph_service import build_mastery_graph
from services.mastery_engine import calculate_topic_stats
from services.course_state import save_course
from services.relationship_suggestions import (
    apply_suggested_relationships,
    describe_suggestions,
    notice_key,
    suggestions_key,
)
from services.ui_style import apply_app_styles
from components.topic_practice_link import open_topic_practice
from services.learning_flow import open_lab

apply_app_styles()

st.title(tr("Knowledge Map"))
st.caption(tr("Explore connected ideas. Click a topic to read its summary and learning progress."))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

if course.course_id == "calculus-i-demo" and not course.relationships:
    demo_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "calculus_i_demo.json"
    )
    try:
        demo_course = type(course).model_validate_json(
            demo_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        st.error(tr("Couldn't load the Calculus demo course. Try again later."))
        st.stop()

    topic_ids = {topic.id for topic in course.topics}
    compatible_edges = [edge for edge in demo_course.relationships
                        if edge.from_topic in topic_ids and edge.to_topic in topic_ids]
    if compatible_edges:
        course = course.model_copy(
            update={"relationships": compatible_edges}
        )
        save_course(st.session_state, course)

with st.container(key="graph_course_heading"):
    st.subheader(course.course_name)
    topic_count = len(course.topics)
    st.caption(tr(f"{topic_count} knowledge point" if topic_count == 1 else f"{topic_count} knowledge points"))

if not course.topics:
    st.info(tr("This course has no topics yet."))
    st.stop()

mode_column, search_column, local_column = st.columns([1.4, 1.8, .8], vertical_alignment="bottom")
mode_label = mode_column.radio(
    tr("Progress mode"), options=[tr("Mock Exam"), tr("Topic Practice")],
    key=f"graph_mode_{course.course_id}", horizontal=True,
)
mode = "mock" if mode_label == tr("Mock Exam") else "topic"

topic_names = {topic.id: topic.name for topic in course.topics}
pending_key = f"graph_pending_focus_{course.course_id}"
if pending_key in st.session_state:
    st.session_state[f"graph_focus_{course.course_id}"] = st.session_state.pop(pending_key)
focus_id = search_column.selectbox(
    tr("Find a topic"), options=[None, *topic_names],
    format_func=lambda value: tr("All topics") if value is None else topic_names[value],
    key=f"graph_focus_{course.course_id}",
)
local_view = local_column.toggle(
    tr("Local graph"), disabled=focus_id is None,
    key=f"graph_local_{course.course_id}",
    help=tr("Show only this topic and its directly connected neighbors."),
)
view_course = local_graph(course, focus_id) if focus_id and local_view else course

reset_key = f"graph_view_reset_{course.course_id}_{mode}"
zoom_key = f"graph_zoom_{course.course_id}_{mode}"
zoom_level = st.session_state.get(zoom_key, 0)
graph_controls = st.columns([1.4, 3])
with graph_controls[0]:
    if st.button(
        tr("Fit to view / Reset view"),
        key=f"reset_graph_view_{course.course_id}_{mode}",
        icon=":material/fit_screen:",
    ):
        st.session_state[reset_key] = (
            st.session_state.get(reset_key, 0) + 1
        )
        st.session_state[zoom_key] = 0
        st.rerun()
with graph_controls[1]:
    st.caption(tr("Click for details · Drag to rearrange · Scroll to zoom"))

history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

sessions = [
    record["session"] for record in history.values()
]
attempts = [
    attempt
    for record in history.values()
    for attempt in record["attempts"]
]

questions_by_id = {
    question.id: question for question in course.questions
}
for record in history.values():
    for question in record["questions"]:
        questions_by_id[question.id] = question

try:
    stats = calculate_topic_stats(
        attempts=attempts,
        sessions=sessions,
        questions=list(questions_by_id.values()),
    )
except ValueError as error:
    st.error(tr("Couldn't calculate your progress from this practice history."))
    st.stop()

# Learning Radar (demo courses only). Zooming and selecting topics rerun the
# page, so the course radar and the user's flags are reused for a short time.
radar = None
radar_user = None
if learning_radar.radar_enabled(course.course_id):
    radar_user = current_user(st.session_state)
    radar, _ = load_course_radar(
        st.session_state,
        course.course_id,
        radar_user.user_id if radar_user is not None else None,
    )

graph_column, details_column = st.columns([2.5, 1], gap="medium")

with graph_column:
    with st.container(border=True, key="knowledge_graph_canvas"):
        zoom_controls = st.columns([1, 0.08, 0.08])
        with zoom_controls[1]:
            if st.button(
                "−",
                key=f"graph_zoom_out_{course.course_id}_{mode}",
                help=tr("Make nodes smaller"),
                disabled=zoom_level <= -3,
            ):
                st.session_state[zoom_key] = zoom_level - 1
        with zoom_controls[2]:
            if st.button(
                "+",
                key=f"graph_zoom_in_{course.course_id}_{mode}",
                help=tr("Make nodes larger"),
                disabled=zoom_level >= 3,
            ):
                st.session_state[zoom_key] = zoom_level + 1

        zoom_level = st.session_state.get(zoom_key, 0)
        zoom_scale = 1 + zoom_level * 0.15
        selected_node_id = render_knowledge_graph(
            view_course,
            stats,
            mode,
            view_reset=st.session_state.get(reset_key, 0),
            node_scale=zoom_scale,
            focus_topic_id=focus_id,
            node_badges=radar_node_badges(radar) if radar is not None else None,
        )

    if radar is not None:
        # The chart and ranking live on the Learning Radar page; the map
        # keeps only the badges and, per topic, the stuck buttons.
        open_page_button(
            tr("Learning Radar"),
            "pages/7_Learning_Radar.py",
            key="knowledge_map_learning_radar",
            icon=":material/radar:",
            align="right",
        )

    if not course.relationships:
        st.info(tr("This course has no topic relationships yet."))

    # Suggestions need the saved course material; demo courses have none.
    material = st.session_state.get(f"course_document_{course.course_id}")
    if material is not None:
        suggestions_state_key = suggestions_key(course.course_id)
        notice_state_key = notice_key(course.course_id)
        with st.container(border=True, key="graph_suggestions_panel"):
            st.markdown(tr("**Suggest connections from your material**"))
            st.caption(tr(
                "Claude reads the saved course material and proposes "
                "related-topic connections. Nothing changes until you apply "
                "them, and applying replaces the current connections. "
                "AI suggestions may be wrong."
            ))

            notice = st.session_state.pop(notice_state_key, None)
            if notice is not None:
                level, text = notice
                if level == "success":
                    st.success(tr(text))
                else:
                    st.warning(tr(text))

            suggestions = st.session_state.get(suggestions_state_key)
            if suggestions is None:
                if st.button(
                    tr("Suggest connections"),
                    key=f"suggest_relationships_{course.course_id}",
                    icon=":material/auto_awesome:",
                ):
                    with st.spinner(tr("Asking Claude for connections...")):
                        generated = generate_relationships(material, course)
                    if not generated["ok"]:
                        st.error(tr(generated["message"]))
                    else:
                        st.session_state[suggestions_state_key] = list(
                            generated["package"]["relationships"]
                        )
                        st.rerun()
            else:
                if suggestions:
                    st.markdown(
                        "\n".join(
                            f"- {label}"
                            for label in describe_suggestions(course, suggestions)
                        )
                    )
                else:
                    st.info(
                        tr("Claude found no evidence-supported connections "
                        "in the material.")
                    )
                apply_column, discard_column = st.columns(2)
                if apply_column.button(
                    tr("Apply suggestions"),
                    type="primary",
                    key=f"apply_relationships_{course.course_id}",
                    disabled=not suggestions,
                ):
                    try:
                        updated_course = apply_suggested_relationships(
                            course, suggestions
                        )
                    except ValueError:
                        st.error(
                            tr("These suggestions no longer match the course "
                            "topics. Discard them and ask for new suggestions.")
                        )
                    else:
                        save_course(st.session_state, updated_course)
                        sync_outcome = save_course_to_account(
                            st.session_state, updated_course
                        )
                        st.session_state.pop(suggestions_state_key, None)
                        count = len(suggestions)
                        noun = "connection" if count == 1 else "connections"
                        if sync_outcome is not None and not sync_outcome.success:
                            # The stored reason may describe the database, so
                            # the student sees a short notice instead.
                            st.session_state[notice_state_key] = (
                                "warning",
                                "Connections kept in this session but not saved "
                                "to your account. Use Save on the Study Plan "
                                "page to retry.",
                            )
                        else:
                            st.session_state[notice_state_key] = (
                                "success",
                                f"Applied {count} suggested {noun}.",
                            )
                        st.rerun()
                if discard_column.button(
                    tr("Discard"),
                    key=f"discard_relationships_{course.course_id}",
                ):
                    st.session_state.pop(suggestions_state_key, None)
                    st.rerun()

# Synchronize canvas clicks with the keyboard-accessible topic picker.
last_click_key = f"graph_last_click_{course.course_id}_{mode}"
if selected_node_id != st.session_state.get(last_click_key):
    st.session_state[last_click_key] = selected_node_id
    if selected_node_id is None or selected_node_id in topic_names:
        st.session_state[pending_key] = selected_node_id
        st.rerun()
selected_node_id = focus_id

with details_column:
    with st.container(border=True, key="knowledge_graph_details"):
        details = None
        topic_stats = None
        if selected_node_id is not None:
            graph = build_mastery_graph(course, stats, mode)
            details = get_selected_topic_details(
                selected_node_id, course, graph
            )
            topic_stats = next(
                (
                    item
                    for item in stats
                    if item.topic_id == selected_node_id
                    and item.mode == mode
                ),
                None,
            )
        render_topic_details(details, topic_stats, course)
        if details is not None:
            links = related_topics(course, selected_node_id)
            st.divider()
            st.markdown(tr("**Connected topics**"))
            for label, group in (("Prerequisites", "prerequisites"), ("Leads to", "next_topics"), ("Related", "related")):
                if links[group]:
                    st.caption(tr(label) + "：" + ", ".join(topic_names[item] for item in links[group]))
            if not any(links.values()):
                st.caption(tr("No connections recorded for this topic."))
            for linked_id in links["prerequisites"]:
                if st.button(tr("Review ") + topic_names[linked_id], key=f"graph_prerequisite_{course.course_id}_{linked_id}"):
                    st.session_state[pending_key] = linked_id
                    st.rerun()
            if st.button(tr("Practise this topic"), key=f"graph_practice_{course.course_id}_{selected_node_id}", type="primary"):
                open_topic_practice(course, selected_node_id)

            if radar is not None:
                st.divider()
                st.markdown(tr("**Learning Radar**"))
                if radar_user is not None:
                    # One click flags the topic with a reason; to change the
                    # reason, remove the flag and flag again.
                    render_stuck_buttons(
                        st.session_state,
                        course.course_id,
                        selected_node_id,
                        radar_user.user_id,
                        key=f"radar_flag_{course.course_id}_{selected_node_id}",
                    )
                render_topic_radar(
                    radar.topics.get(selected_node_id),
                    prerequisite_names=[
                        topic_names[item]
                        for item in links["prerequisites"]
                        if item in topic_names
                    ],
                    # The buttons above already show the count.
                    show_count=radar_user is None,
                )
                if concept_lab_available(course.course_id, selected_node_id):
                    if st.button(
                        tr("Open Concept Lab"),
                        key=f"radar_concept_lab_{course.course_id}_{selected_node_id}",
                        icon=":material/science:",
                    ):
                        open_lab(st.session_state, course.course_id, selected_node_id)
                        st.switch_page("pages/6_Concept_Lab.py")

    with st.container(border=True, key="knowledge_graph_legend"):
        st.markdown(tr("**Status Legend**"))
        st.markdown(
            f"""
            <div class="graph-legend">
                <span><i style="background:#94A3B8"></i>{tr('Unattempted')}</span>
                <span><i style="background:#A78BFA"></i>{tr('Insufficient evidence')}</span>
                <span><i style="background:#EF4444"></i>{tr('Weak')}</span>
                <span><i style="background:#F59E0B"></i>{tr('Developing')}</span>
                <span><i style="background:#22C55E"></i>{tr('Mastered')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
