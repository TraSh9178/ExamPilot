"""Interactive Calculus I concept experiments for the public demo."""

import altair as alt
import pandas as pd
import streamlit as st

from services.concept_lab import limit_example, limit_table
from services.ui_style import apply_app_styles


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

with derivatives_tab:
    st.info("The derivatives experiment is coming in the next development step.")
