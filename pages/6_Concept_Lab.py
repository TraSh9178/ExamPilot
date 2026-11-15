"""Interactive Calculus I concept experiments for the public demo."""

from services.i18n import tr

import altair as alt
import pandas as pd
import streamlit as st

from services.concept_lab import (
    cubic, cubic_derivative, limit_example, limit_table, secant_slope, tangent_line,
)
from services.ui_style import apply_app_styles
from services.learning_flow import stage_practice
from services.concept_lab_ui import DISTANCES, prediction, observation


def practice_topic(topic_id: str) -> None:
    """Use the Practice page's existing course-scoped widget contract."""
    if not st.button(tr("Practice this topic"), key=f"concept_lab_practice_{topic_id}"):
        return
    course = st.session_state.get("current_course")
    if course is None or course.course_id != "calculus-i-demo":
        st.info(tr("Open the Calculus I Demo course on the Dashboard to practise this topic."))
        return
    confirmed = st.session_state.get(f"confirmed_scope_{course.course_id}", [])
    if topic_id not in confirmed:
        st.info(tr("Confirm this topic in Study Plan first."))
        st.page_link("pages/1_Study_Hub.py", label=tr("Go to Study Plan"))
        return
    stage_practice(st.session_state, course, topic_id)
    st.switch_page("pages/2_Practice_Center.py")


apply_app_styles()

st.title(tr("Concept Lab"))
st.caption(tr("Predict, move the controls, then explain what changed."))
for key, value in {"concept_lab_limit_distance": 0.1, "concept_lab_x0": 1.0,
                   "concept_lab_h": 0.5, "concept_lab_zoom": True}.items():
    st.session_state.setdefault(key, value)

requested_topic = st.session_state.get("concept_lab_topic_calculus-i-demo", "calc_limits")
limits_tab, derivatives_tab = st.tabs(
    ["Limits", "Derivatives"],
    default="Derivatives" if requested_topic == "calc_derivatives" else "Limits",
)

with limits_tab:
    st.subheader(tr("Limits: approaching x = 2"))
    st.latex(r"f(x)=\frac{x^2-4}{x-2},\quad x\ne 2")
    prediction("limits")
    st.markdown(tr("**2 · Explore**"))
    st.write(
        tr("Move closer to x = 2 from both sides. Compare the two values as the distance shrinks.")
    )

    distances = DISTANCES
    distance = st.select_slider(
        tr("Distance from x = 2"),
        options=distances,
        key="concept_lab_limit_distance",
    )
    observation("limits", "concept_lab_limit_distance")
    selected = limit_table([float(distance)])[0]

    # Plot two separate segments: the original function is not defined at x = 2.
    curve_rows = []
    for side, start, end in (
        ("left", 1.0, 1.999),
        ("right", 2.001, 3.0),
    ):
        for step in range(101):
            x = start + (end - start) * step / 100
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

    with st.expander(tr("Compare values from both sides")):
        st.dataframe(
            pd.DataFrame(limit_table(distances)).rename(
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
    st.markdown(tr("**3 · Explain**"))
    with st.expander(tr("Why can a missing point still have a limit?")):
        st.latex(r"\frac{x^2-4}{x-2}=x+2\quad (x\ne2)")
        st.write(tr("The limit describes nearby values, not the value at the missing point. Both sides approach 4 even though f(2) is undefined."))

    practice_topic("calc_limits")

with derivatives_tab:
    st.subheader(tr("Derivatives: from secant to tangent"))
    st.write(tr("For f(x) = x³ − 5x, shrink h and compare the secant with the tangent at x₀."))
    prediction("derivatives")
    st.markdown(tr("**2 · Explore**"))
    x0 = st.slider("x₀", -3.0, 3.0, step=0.5, key="concept_lab_x0")
    h = st.select_slider(
        tr("h"), options=distances, key="concept_lab_h",
    )
    side = st.radio(tr("Approach from"), ["Right", "Left"], format_func=tr,
                    horizontal=True, key="concept_lab_side")
    h = float(h) if side == "Right" else -float(h)
    st.caption(f"h = {h:g}")
    observation("derivatives", "concept_lab_h")
    zoom = st.toggle(tr("Zoom around x₀"), key="concept_lab_zoom")
    slope = secant_slope(x0, h)
    exact, intercept = tangent_line(x0)
    rows = []
    start, end = (x0 - 1.3, x0 + 1.3) if zoom else (-4.2, 4.2)
    for step in range(201):
        x = start + (end - start) * step / 200
        rows.extend([
            {"x": x, "y": cubic(x), "Line": tr("Curve f(x)")},
            {"x": x, "y": cubic(x0) + slope * (x - x0), "Line": tr("Secant")},
            {"x": x, "y": exact * x + intercept, "Line": tr("Tangent")},
        ])
    lines = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2).encode(
        x=alt.X("x:Q", title="x"),
        y=alt.Y("y:Q", title="y", scale=alt.Scale(zero=False)),
        color=alt.Color("Line:N", scale=alt.Scale(
            domain=[tr("Curve f(x)"), tr("Secant"), tr("Tangent")],
            range=["#2166DB", "#16A085", "#CC3344"],
        )),
        strokeDash=alt.StrokeDash("Line:N", scale=alt.Scale(domain=["Curve f(x)", "Secant", "Tangent"], range=[[], [7, 4], []])),
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
    st.altair_chart(alt.layer(lines, points, labels).properties(height=360), width="stretch")
    st.caption(tr("Blue: function · Green dashed: secant · Red: tangent. Hover over the two points to inspect their coordinates."))
    secant_column, derivative_column = st.columns(2)
    secant_column.metric(tr("Secant slope"), f"{slope:.6f}")
    derivative_column.metric(tr("Derivative f′(x₀)"), f"{cubic_derivative(x0):.6f}")
    st.caption(tr("Slope gap: ") + f"{abs(slope-exact):.6f}")
    st.markdown(tr("**3 · Explain**"))
    with st.expander(tr("Why does the secant approach the tangent?")):
        st.latex(r"\frac{f(x_0+h)-f(x_0)}{h}\to f'(x_0)=3x_0^2-5")
        st.write(tr("The secant measures change over an interval. Shrinking that interval from either side gives the instantaneous slope at x₀. The slope gap measures how far the two slopes are apart."))
    practice_topic("calc_derivatives")
