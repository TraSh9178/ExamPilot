"""Interactive Calculus I concept experiments for the public demo.

Each tab keeps its chart on the right and walks through one step at a time on
the left: predict, explore, explain (services/concept_lab_ui.py).
"""

from services.i18n import tr

import altair as alt
import pandas as pd
import streamlit as st

from services.concept_lab import (
    cubic, cubic_derivative, limit_example, limit_table, secant_slope, tangent_line, corner_slopes,
)
from services.ui_style import apply_app_styles
from components.topic_practice_link import open_topic_practice
from services.concept_lab_ui import (
    DISTANCES, current_step, explanation, explore_navigation, keep_value, observation,
    prediction, restore_values, step_indicator,
)


def practice_topic(topic_id: str, suffix: str = "") -> None:
    """Use the Practice page's existing course-scoped widget contract."""
    if not st.button(tr("Practice this topic"), key=f"concept_lab_practice_{topic_id}{suffix}"):
        return
    course = st.session_state.get("current_course")
    if course is None or course.course_id != "calculus-i-demo":
        st.info(tr("Open the Calculus I Demo course on the Dashboard to practise this topic."))
        return
    open_topic_practice(course, topic_id)


def start_step(topic: str) -> int:
    """Show where this tab is in its three steps and return the current one."""
    step = current_step(topic)
    step_indicator(step)
    return step


apply_app_styles()

st.title(tr("Concept Lab"))
st.caption(tr("Predict, move the controls, then explain what changed."))
# Values of steps that are not on screen (or were set before leaving the page).
restore_values()
# Written again on every run, not only the first: the browser shows a control's
# own default unless the run that first draws it also sets its value, and the
# controls first appear in step 2, after the chart has used these values.
for key, value in {"concept_lab_limit_distance": 0.1, "concept_lab_x0": 1.0,
                   "concept_lab_h": 0.5, "concept_lab_zoom": True, "concept_lab_corner_h": 0.5}.items():
    st.session_state[key] = st.session_state.get(key, value)

requested_topic = st.session_state.get("concept_lab_topic_calculus-i-demo", "calc_limits")
limits_label, derivatives_label = tr("Limits"), tr("Derivatives")
limits_tab, derivatives_tab, corner_tab = st.tabs(
    [limits_label, derivatives_label, tr("Corners & differentiability")],
    default=derivatives_label if requested_topic == "calc_derivatives" else limits_label,
)

with limits_tab:
    st.subheader(tr("Limits: approaching x = 2"))
    st.latex(r"f(x)=\frac{x^2-4}{x-2},\quad x\ne 2")
    controls, visual = st.columns([1, 1.7], gap="large")
    with controls:
        step = start_step("limits")
        if step == 1:
            prediction("limits")
        elif step == 2:
            st.write(
                tr("Move closer to x = 2 from both sides. Compare the two values as the distance shrinks.")
            )
            st.select_slider(
                tr("Distance from x = 2"),
                options=DISTANCES,
                key="concept_lab_limit_distance",
                on_change=keep_value,
                args=("concept_lab_limit_distance",),
            )
            observation("limits", "concept_lab_limit_distance")
            explore_navigation("limits")
        else:
            explanation("limits")
            practice_topic("calc_limits")
    # The slider's value, also in the steps that do not draw the slider.
    distance = st.session_state["concept_lab_limit_distance"]
    selected = limit_table([float(distance)])[0]

    # Plot two separate segments: the original function is not defined at x = 2.
    curve_rows = []
    for side, start, end in (
        ("left", 1.0, 1.999),
        ("right", 2.001, 3.0),
    ):
        for point in range(101):
            x = start + (end - start) * point / 100
            curve_rows.append(
                {"x": x, "y": limit_example(x), "side": side}
            )

    x_axis = alt.X("x:Q", title="x", scale=alt.Scale(domain=[0.9, 3.1]))
    y_axis = alt.Y(
        "y:Q",
        title="f(x)",
        scale=alt.Scale(domain=[2.9, 5.1]),
    )

    curve = (
        alt.Chart(pd.DataFrame(curve_rows))
        .mark_line(color="#2166DB", strokeWidth=2.5)
        .encode(x=x_axis, y=y_axis, detail="side:N")
    )
    selected_points = (
        alt.Chart(
            pd.DataFrame(
                [
                    {"x": selected["left_x"], "y": selected["left_value"]},
                    {"x": selected["right_x"], "y": selected["right_value"]},
                ]
            )
        )
        .mark_point(filled=True, color="#16A085", size=90)
        .encode(x=x_axis, y=y_axis, tooltip=["x:Q", "y:Q"])
    )
    # Draw the hollow marker last so it stays visible for small distances.
    hole = (
        alt.Chart(pd.DataFrame([{"x": 2.0, "y": 4.0}]))
        .mark_point(
            filled=False,
            stroke="#CC3344",
            strokeWidth=3,
            size=220,
        )
        .encode(x=x_axis, y=y_axis)
    )

    with visual:
        st.altair_chart(
            alt.layer(curve, selected_points, hole).properties(height=320),
            width="stretch",
        )
        st.caption(tr("The open circle at (2, 4) marks a point where f(x) is undefined."))

        left_column, right_column = st.columns(2)
        left_column.metric(
            tr(f"f(2 − {distance:g})"),
            f"{selected['left_value']:.3f}",
        )
        right_column.metric(
            tr(f"f(2 + {distance:g})"),
            f"{selected['right_value']:.3f}",
        )

    if step == 2:
        # Exploring data: too wide for the left column, so it runs under both.
        st.markdown(f"**{tr('Compare values from both sides')}**")
        st.dataframe(
            pd.DataFrame(limit_table(DISTANCES)).rename(
                columns={
                    "distance": tr("Distance"),
                    "left_x": tr("Left x"),
                    "left_value": tr("f(Left x)"),
                    "right_x": tr("Right x"),
                    "right_value": tr("f(Right x)"),
                }
            ),
            hide_index=True,
            width="stretch",
        )

with derivatives_tab:
    st.subheader(tr("Derivatives: from secant to tangent"))
    st.write(tr("For f(x) = x³ − 5x, shrink h and compare the secant with the tangent at x₀."))
    controls, visual = st.columns([1, 1.7], gap="large")
    with controls:
        step = start_step("derivatives")
        if step == 1:
            prediction("derivatives")
        elif step == 2:
            x0 = st.slider("x₀", -3.0, 3.0, step=0.5, key="concept_lab_x0",
                           on_change=keep_value, args=("concept_lab_x0",))
            h = st.select_slider(
                tr("h"), options=DISTANCES, key="concept_lab_h",
                on_change=keep_value, args=("concept_lab_h",),
            )
            side = st.radio(tr("Approach from"), ["Right", "Left"], format_func={"Right": tr("Right"), "Left": tr("Left")}.get,
                            horizontal=True, key="concept_lab_side",
                            on_change=keep_value, args=("concept_lab_side",))
            h = float(h) if side == "Right" else -float(h)
            st.caption(f"h = {h:g}")
            observation("derivatives", "concept_lab_h")
            st.toggle(tr("Zoom around x₀"), key="concept_lab_zoom",
                      on_change=keep_value, args=("concept_lab_zoom",))
            if st.button(tr("Save this secant for comparison"), key="lab_save_secant"):
                st.session_state['lab_saved_secant'] = {'x0': x0, 'h': h, 'slope': secant_slope(x0, h)}
            explore_navigation("derivatives")
        else:
            explanation("derivatives")
            practice_topic("calc_derivatives")
    # The controls' values, also in the steps that do not draw them.
    x0 = st.session_state["concept_lab_x0"]
    h = float(st.session_state["concept_lab_h"])
    if st.session_state.get("concept_lab_side", "Right") != "Right":
        h = -h
    zoom = st.session_state["concept_lab_zoom"]
    slope = secant_slope(x0, h)
    exact, intercept = tangent_line(x0)
    saved = st.session_state.get('lab_saved_secant')
    comparable = saved is not None and saved['x0'] == x0
    names = [tr("Curve f(x)"), tr("Secant"), tr("Tangent")]
    colors = ["#2166DB", "#16A085", "#CC3344"]
    dashes = [[], [7, 4], []]
    if comparable:
        names.append(tr("Saved secant"))
        colors.append("#8054C7")
        dashes.append([2, 4])
    rows = []
    start, end = (x0 - 1.3, x0 + 1.3) if zoom else (-4.2, 4.2)
    for point in range(201):
        x = start + (end - start) * point / 200
        rows.extend([
            {"x": x, "y": cubic(x), "Line": tr("Curve f(x)")},
            {"x": x, "y": cubic(x0) + slope * (x - x0), "Line": tr("Secant")},
            {"x": x, "y": exact * x + intercept, "Line": tr("Tangent")},
        ])
        if comparable:
            rows.append({'x': x, 'y': cubic(x0) + saved['slope'] * (x-x0), 'Line': tr('Saved secant')})
    lines = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2).encode(
        x=alt.X("x:Q", title="x"),
        y=alt.Y("y:Q", title="y", scale=alt.Scale(zero=False)),
        color=alt.Color("Line:N", scale=alt.Scale(
            domain=names, range=colors,
        )),
        strokeDash=alt.StrokeDash("Line:N", scale=alt.Scale(domain=names, range=dashes)),
    )
    points = alt.Chart(pd.DataFrame([
        {"x": x0, "y": cubic(x0), "Point": "x₀"},
        {"x": x0 + h, "y": cubic(x0 + h), "Point": "x₀ + h"},
    ])).mark_point(filled=True, color="#222222", size=80).encode(
        x="x:Q", y="y:Q", tooltip=["Point:N", "x:Q", "y:Q"],
    )
    labels = alt.Chart(pd.DataFrame([
        {"x": x0, "y": cubic(x0), "Point": "x₀"},
    ])).mark_text(align="left", dx=8, dy=-14, fontSize=13).encode(x="x:Q", y="y:Q", text="Point:N")
    with visual:
        st.altair_chart(alt.layer(lines, points, labels).properties(height=360), width="stretch")
        st.caption(tr("Blue: function · Green dashed: secant · Red: tangent. Hover over the two points to inspect their coordinates."))
        secant_column, derivative_column = st.columns(2)
        secant_column.metric(tr("Secant slope"), f"{slope:.6f}")
        derivative_column.metric(tr("Derivative f′(x₀)"), f"{cubic_derivative(x0):.6f}")
        st.caption(tr("Slope gap: ") + f"{abs(slope-exact):.6f}")
        if comparable:
            st.caption(tr('Saved comparison: ') + f"h = {saved['h']:g} · " + tr('Secant slope') + f" = {saved['slope']:.6f}")
        elif saved:
            st.caption(tr('x₀ changed. Save a new secant to compare slopes at the same point.'))


with corner_tab:
    # The full title answers the step-1 question, so it waits until the student has predicted.
    st.subheader(
        tr("Continuous does not always mean differentiable") if current_step("corner") > 1
        else tr("A corner at x = 0")
    )
    st.latex(r"f(x)=|x|,\quad x_0=0")
    controls, visual = st.columns([1, 1.7], gap="large")
    with controls:
        step = start_step("corner")
        if step == 1:
            prediction("corner")
        elif step == 2:
            st.select_slider(tr("Distance from the corner"), options=DISTANCES,
                             key="concept_lab_corner_h",
                             on_change=keep_value, args=("concept_lab_corner_h",))
            observation("corner", "concept_lab_corner_h")
            explore_navigation("corner")
        else:
            explanation("corner")
            practice_topic('calc_derivatives', '_corner')
    distance = st.session_state["concept_lab_corner_h"]
    left, right = corner_slopes(float(distance))
    samples = [{'x': -1.2 + i*2.4/200, 'y': abs(-1.2+i*2.4/200)} for i in range(201)]
    curve = alt.Chart(pd.DataFrame(samples)).mark_line(color="#2166DB", strokeWidth=3).encode(x='x:Q', y='y:Q')
    points = alt.Chart(pd.DataFrame([
        {'x': -float(distance), 'y': float(distance), 'Point': tr('Left')},
        {'x': 0., 'y': 0., 'Point': '0'},
        {'x': float(distance), 'y': float(distance), 'Point': tr('Right')},
    ])).mark_point(filled=True, size=100, color="#8054C7").encode(x='x:Q', y='y:Q', tooltip=['Point:N','x:Q','y:Q'])
    with visual:
        st.altair_chart(alt.layer(curve, points).properties(height=320), width="stretch")
        a, b = st.columns(2)
        a.metric(tr('Left secant slope'), f'{left:.0f}')
        b.metric(tr('Right secant slope'), f'{right:.0f}')
        # This line answers the step-1 prediction, so it waits until the student has predicted.
        if step > 1:
            st.info(tr('The two slopes disagree: no derivative at 0.'))
