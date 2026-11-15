"""Small, session-local teaching controls for the two Calculus experiments."""
import streamlit as st
from services.i18n import tr

DISTANCES = [1, 0.5, 0.1, 0.05, 0.01, 0.001]


def reset_experiment(topic):
    defaults = ({'concept_lab_limit_distance': 0.1} if topic == 'limits' else
                {'concept_lab_x0': 1.0, 'concept_lab_h': 0.5,
                 'concept_lab_side': 'Right', 'concept_lab_zoom': True})
    st.session_state.update(defaults)
    for suffix in ('prediction', 'checked'):
        st.session_state.pop(f'lab_{topic}_{suffix}', None)


def approach(key):
    current = st.session_state[key]
    st.session_state[key] = DISTANCES[min(DISTANCES.index(current)+1, len(DISTANCES)-1)]


def prediction(topic):
    """Optional formative feedback; never adds an exam attempt or mastery score."""
    is_limit = topic == 'limits'
    prompt = ('As x approaches 2, what do the nearby function values approach?' if is_limit else
              'As h approaches 0, what should the secant slope approach?')
    choices = (['4', '0', 'Undefined because f(2) is undefined'] if is_limit else
               ['The tangent slope at x₀', 'Always zero', 'The function value f(x₀)'])
    st.markdown(tr('**1 · Predict**'))
    selected = st.radio(tr(prompt), choices, index=None, format_func=tr, horizontal=True,
                        key=f'lab_{topic}_prediction')
    if st.button(tr('Check my prediction'), key=f'lab_{topic}_check'):
        st.session_state[f'lab_{topic}_checked'] = selected
    checked = st.session_state.get(f'lab_{topic}_checked')
    if checked is not None and checked == selected:
        if checked == choices[0]:
            st.success(tr('Your prediction matches the experiment. Try to explain why.'))
        else:
            st.info(tr('Try the experiment below, then compare your prediction again.'))
    elif f'lab_{topic}_checked' in st.session_state and selected is None:
        st.info(tr('Choose a prediction first.'))


def observation(topic, key):
    a, b = st.columns(2)
    a.button(tr('Move one step closer'), key=f'lab_{topic}_approach',
             disabled=st.session_state[key] == DISTANCES[-1], on_click=approach, args=(key,))
    b.button(tr('Reset experiment'), key=f'lab_{topic}_reset',
             on_click=reset_experiment, args=(topic,))
