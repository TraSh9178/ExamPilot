"""Interactive Calculus I concept experiments for the public demo."""

import altair as alt
import pandas as pd
import streamlit as st

from services.concept_lab import (
    cubic, cubic_derivative, limit_example, limit_table, secant_slope, tangent_line,
)
from services.ui_style import apply_app_styles


def practice_topic(topic_id: str) -> None:
    """Use the Practice page's existing course-scoped widget contract."""
    if not st.button("Practice this topic", key=f"concept_lab_practice_{topic_id}"):
        return
    course = st.session_state.get("current_course")
    if course is None or course.course_id != "calculus-i-demo":
        st.info("Open the Calculus I Demo course on the Dashboard to practise this topic.")
        return
    confirmed = st.session_state.get(f"confirmed_scope_{course.course_id}", [])
    if topic_id not in confirmed:
        st.info("Confirm this topic in Study Plan first.")
        st.page_link("pages/1_Study_Hub.py", label="Go to Study Plan")
        return
    st.session_state[f"practice_mode_{course.course_id}"] = "Topic Practice"
    st.session_state[f"practice_topic_{course.course_id}"] = topic_id
    st.switch_page("pages/2_Practice_Center.py")


apply_app_styles()

st.title("Concept Lab")
st.caption("Move the sliders and watch the idea happen.")

limits_tab, derivatives_tab = st.tabs(["Limits", "Derivatives"])

with limits_tab:
    st.subheader("Limits: approaching x = 2")
    st.write(
        "Move closer to x = 2 from both sides and watch the function values "
        "approach 4."
    )

    distances = [1, 0.5, 0.1, 0.05, 0.01, 0.001]
    distance = st.select_slider(
        "Distance from x = 2",
        options=distances,
        value=0.1,
        key="concept_lab_limit_distance",
    )
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
    st.caption("The open circle at (2, 4) marks a point where f(x) is undefined.")

    left_column, right_column = st.columns(2)
    left_column.metric(
        f"f(2 − {distance:g})",
        f"{selected['left_value']:.3f}",
    )
    right_column.metric(
        f"f(2 + {distance:g})",
        f"{selected['right_value']:.3f}",
    )

    st.dataframe(
        pd.DataFrame(limit_table(distances)).rename(
            columns={
                "distance": "Distance",
                "left_x": "Left x",
                "left_value": "f(Left x)",
                "right_x": "Right x",
                "right_value": "f(Right x)",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.info("f(2) is undefined, but f(x) gets as close to 4 as we like.")

    practice_topic("calc_limits")

with derivatives_tab:
    st.subheader("Derivatives: from secant to tangent")
    st.write("For f(x) = x³ − 5x, shrink h and compare the secant with the tangent at x₀.")
    x0 = st.slider("x₀", -3.0, 3.0, 1.0, 0.5, key="concept_lab_x0")
    h = st.select_slider(
        "h", options=distances, value=0.5, key="concept_lab_h",
    )
    slope = secant_slope(x0, h)
    exact, intercept = tangent_line(x0)
    rows = []
    for step in range(201):
        x = -3.5 + 8 * step / 200
        rows.extend([
            {"x": x, "y": cubic(x), "Line": "Curve f(x)"},
            {"x": x, "y": cubic(x0) + slope * (x - x0), "Line": "Secant"},
            {"x": x, "y": exact * x + intercept, "Line": "Tangent"},
        ])
    lines = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2).encode(
        x=alt.X("x:Q", title="x"),
        y=alt.Y("y:Q", title="y", scale=alt.Scale(zero=False)),
        color=alt.Color("Line:N", scale=alt.Scale(
            domain=["Curve f(x)", "Secant", "Tangent"],
            range=["#2166DB", "#16A085", "#CC3344"],
        )),
        strokeDash=alt.StrokeDash("Line:N"),
    )
    points = alt.Chart(pd.DataFrame([
        {"x": x0, "y": cubic(x0), "Point": "x₀"},
        {"x": x0 + h, "y": cubic(x0 + h), "Point": "x₀ + h"},
    ])).mark_point(filled=True, color="#222222", size=80).encode(
        x="x:Q", y="y:Q", tooltip=["Point:N", "x:Q", "y:Q"],
    )
    st.altair_chart(alt.layer(lines, points).properties(height=360), width="stretch")
    secant_column, derivative_column = st.columns(2)
    secant_column.metric("Secant slope", f"{slope:.6f}")
    derivative_column.metric("Derivative f′(x₀)", f"{cubic_derivative(x0):.6f}")
    st.info("As h approaches 0, the secant slope approaches f′(x₀) = 3x₀² − 5.")
    practice_topic("calc_derivatives")
