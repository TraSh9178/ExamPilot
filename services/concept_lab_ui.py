"""Small, session-local teaching controls for the two Calculus experiments."""
import streamlit as st
from services.i18n import tr

DISTANCES = [1, 0.5, 0.1, 0.05, 0.01, 0.001]


def reset_experiment(topic):
    defaults = {'limits': {'concept_lab_limit_distance': 0.1},
                'derivatives': {'concept_lab_x0': 1.0, 'concept_lab_h': 0.5,
                                'concept_lab_side': 'Right', 'concept_lab_zoom': True},
                'corner': {'concept_lab_corner_h': 0.5}}[topic]
    if topic == 'derivatives':
        st.session_state.pop('lab_saved_secant', None)
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
    if topic == 'corner':
        prompt = 'At x = 0, which statement describes f(x) = |x|?'
        choices = ['Continuous, but not differentiable at 0',
                   'Continuous and differentiable at 0', 'Discontinuous at 0']
    # The first step of the flow is always on screen. Only the "Why ...?"
    # explanations further down stay folded until the student has predicted.
    with st.container(border=True, key=f'lab_{topic}_predict_step'):
        st.markdown(f"**{tr('1 · Predict before exploring')}**")
        selected = st.radio(tr(prompt), choices, index=None, format_func={choice: tr(choice) for choice in choices}.get, horizontal=True,
                            key=f'lab_{topic}_prediction')
        if st.button(tr('Check my prediction'), key=f'lab_{topic}_check'):
            st.session_state[f'lab_{topic}_checked'] = selected
        checked = st.session_state.get(f'lab_{topic}_checked')
        if checked is not None and checked == selected:
            if checked == choices[0]:
                st.success(tr('Your prediction matches the experiment. Try to explain why.'))
            else:
                feedback = {
                    '0': 'A zero numerator does not make this limit zero. Compare nearby values after cancelling x − 2.',
                    'Undefined because f(2) is undefined': 'A missing point and a missing limit are different. Track the nearby values from both sides.',
                    'Always zero': 'A smaller interval does not imply a horizontal line. Keep x₀ fixed and compare the two slopes.',
                    'The function value f(x₀)': 'A function value is a height; a derivative is a slope. Compare rise divided by run.',
                    'Continuous and differentiable at 0': 'Continuity alone does not guarantee a derivative. Compare the left and right slopes at the corner.',
                    'Discontinuous at 0': 'Both sides of |x| approach its value 0. Now compare slopes rather than heights.',
                }
                st.info(tr(feedback[checked]))
                st.caption(tr('Change your prediction and check again after exploring.'))
        elif f'lab_{topic}_checked' in st.session_state and selected is None:
            st.info(tr('Choose a prediction first.'))


def observation(topic, key):
    a, b = st.columns(2)
    a.button(tr('Move one step closer'), key=f'lab_{topic}_approach',
             disabled=st.session_state[key] == DISTANCES[-1], on_click=approach, args=(key,))
    b.button(tr('Reset experiment'), key=f'lab_{topic}_reset',
             on_click=reset_experiment, args=(topic,))
