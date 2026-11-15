"""Small, session-local teaching controls for the Calculus experiments.

Each experiment is worked through one step at a time in the left column:
1 Predict, 2 Explore, 3 Explain. The chart beside it stays the same in every
step. Nothing here adds an exam attempt, a score or a mastery change, and
nothing leaves the session.
"""
from services.ui_help import help_heading
import html

import streamlit as st
from services.i18n import tr

DISTANCES = [1, 0.5, 0.1, 0.05, 0.01, 0.001]
STEP_NAMES = ('Predict', 'Explore', 'Explain')

# Step 2: each experiment's controls (widget keys) and their starting values.
EXPLORE_DEFAULTS = {
    'limits': {'concept_lab_limit_distance': 0.1},
    'derivatives': {'concept_lab_x0': 1.0, 'concept_lab_h': 0.5,
                    'concept_lab_side': 'Right', 'concept_lab_zoom': True},
    'corner': {'concept_lab_corner_h': 0.5},
}

# Step 1: the question and its choices; the first choice is the right one.
PREDICTIONS = {
    'limits': ('As x approaches 2, what do the nearby function values approach?',
               ['4', '0', 'Undefined because f(2) is undefined']),
    'derivatives': ('As h approaches 0, what should the secant slope approach?',
                    ['The tangent slope at x₀', 'Always zero', 'The function value f(x₀)']),
    'corner': ('At x = 0, which statement describes f(x) = |x|?',
               ['Continuous, but not differentiable at 0',
                'Continuous and differentiable at 0', 'Discontinuous at 0']),
}

FEEDBACK = {
    '0': 'A zero numerator does not make this limit zero. Compare nearby values after cancelling x − 2.',
    'Undefined because f(2) is undefined': 'A missing point and a missing limit are different. Track the nearby values from both sides.',
    'Always zero': 'A smaller interval does not imply a horizontal line. Keep x₀ fixed and compare the two slopes.',
    'The function value f(x₀)': 'A function value is a height; a derivative is a slope. Compare rise divided by run.',
    'Continuous and differentiable at 0': 'Continuity alone does not guarantee a derivative. Compare the left and right slopes at the corner.',
    'Discontinuous at 0': 'Both sides of |x| approach its value 0. Now compare slopes rather than heights.',
}

# Step 3: the question, then (formula or None, answer) behind "Show answer".
EXPLANATIONS = {
    'limits': (
        'Why can a missing point still have a limit?',
        r"\frac{x^2-4}{x-2}=x+2\quad (x\ne2)",
        'The limit describes nearby values, not the value at the missing point. Both sides approach 4 even though f(2) is undefined.',
    ),
    'derivatives': (
        'Why does the secant approach the tangent?',
        r"\frac{f(x_0+h)-f(x_0)}{h}\to f'(x_0)=3x_0^2-5",
        'The secant measures change over an interval. Shrinking that interval from either side gives the instantaneous slope at x₀. The slope gap measures how far the two slopes are apart.',
    ),
    'corner': (
        'Why is the corner continuous but not differentiable?',
        None,
        'The nearby heights approach f(0) = 0, so |x| is continuous. The left slopes stay −1 and the right slopes stay 1, so no single derivative exists at 0.',
    ),
}

SELF_CHECKS = {'right': 'I had it right', 'missed': 'I missed something'}


# ---- Which step an experiment is on ----------------------------------------------

def step_key(topic):
    return f'lab_{topic}_step'


def current_step(topic):
    """1, 2 or 3; a new session, or any other value, starts at step 1."""
    step = st.session_state.get(step_key(topic), 1)
    return step if type(step) is int and 1 <= step <= 3 else 1


def go_to_step(topic, step):
    st.session_state[step_key(topic)] = step


def _widget_keys(topic):
    """Every widget whose value the student sets in this experiment's steps."""
    return (f'lab_{topic}_prediction', *EXPLORE_DEFAULTS[topic], f'lab_{topic}_explanation')


def _kept(key):
    return f'lab_kept_{key}'


# Streamlit drops a widget's value after a run that does not draw it: a step
# that is not on screen, or another page. So each of these widgets copies its
# value into a plain session key when it changes (keep_value), and every run
# writes the copies back before any widget is drawn (restore_values).

def keep_value(key):
    """on_change for the widgets in _widget_keys()."""
    st.session_state[_kept(key)] = st.session_state[key]


def _set_value(key, value):
    st.session_state[key] = value
    st.session_state[_kept(key)] = value


def restore_values():
    """Put back the prediction, slider positions and typed explanation.

    Call it at the top of the page, before any widget is drawn.
    """
    for topic in EXPLORE_DEFAULTS:
        for key in _widget_keys(topic):
            if _kept(key) in st.session_state:
                st.session_state[key] = st.session_state[_kept(key)]


def reset_experiment(topic):
    """Start this experiment again: default controls, no prediction, step 1."""
    if topic == 'derivatives':
        st.session_state.pop('lab_saved_secant', None)
    for key, value in EXPLORE_DEFAULTS[topic].items():
        _set_value(key, value)
    for key in (f'lab_{topic}_prediction', f'lab_{topic}_checked', f'lab_{topic}_explanation',
                f'lab_{topic}_answer_shown', f'lab_{topic}_self_check'):
        st.session_state.pop(key, None)
        st.session_state.pop(_kept(key), None)
    go_to_step(topic, 1)


def step_indicator(step):
    """The three steps in a row; the current one is marked by style and for screen readers."""
    items = []
    for number, name in enumerate(STEP_NAMES, start=1):
        marker = ' class="lab-step is-current" aria-current="step"' if number == step else ' class="lab-step"'
        items.append(f'<li{marker}><span class="lab-step-number">{number}</span> {html.escape(tr(name))}</li>')
    st.markdown(
        f'<ol class="lab-steps" aria-label="{html.escape(tr("Steps"))}">{"".join(items)}</ol>',
        unsafe_allow_html=True,
    )


def _back_button(topic, to_step):
    st.button(tr('Back'), key=f'lab_{topic}_back_to_{to_step}', type='tertiary',
              icon=':material/arrow_back:', on_click=go_to_step, args=(topic, to_step))


# ---- Step 1: predict ---------------------------------------------------------------

def prediction(topic):
    """Optional formative feedback; never adds an exam attempt or mastery score.

    Once a prediction has been checked, "Next: explore" leads on to step 2.
    """
    prompt, choices = PREDICTIONS[topic]
    with st.container(border=True, key=f'lab_{topic}_prediction_choices'):
        selected = st.radio(tr(prompt), choices, index=None, format_func={choice: tr(choice) for choice in choices}.get, horizontal=False,
                            key=f'lab_{topic}_prediction', on_change=keep_value, args=(f'lab_{topic}_prediction',))
    with st.container(key=f'lab_{topic}_prediction_actions'):
        if st.button(tr('Check my prediction'), key=f'lab_{topic}_check', type='primary', width='stretch'):
            st.session_state[f'lab_{topic}_checked'] = selected
    checked = st.session_state.get(f'lab_{topic}_checked')
    if checked is not None and checked == selected:
        if checked == choices[0]:
            st.success(tr('Your prediction matches the experiment. Try to explain why.'))
        else:
            st.info(tr(FEEDBACK[checked]))
            st.caption(tr('Change your prediction and check again after exploring.'))
    elif f'lab_{topic}_checked' in st.session_state and selected is None:
        st.info(tr('Choose a prediction first.'))
    if checked is not None:
        st.button(tr('Next: explore'), key=f'lab_{topic}_next_explore', type='primary',
                  on_click=go_to_step, args=(topic, 2))


# ---- Step 2: explore ---------------------------------------------------------------

def approach(key):
    current = st.session_state[key]
    _set_value(key, DISTANCES[min(DISTANCES.index(current)+1, len(DISTANCES)-1)])


def observation(topic, key):
    a, b = st.columns(2)
    a.button(tr('Move one step closer'), key=f'lab_{topic}_approach',
             disabled=st.session_state[key] == DISTANCES[-1], on_click=approach, args=(key,))
    b.button(tr('Reset experiment'), key=f'lab_{topic}_reset',
             on_click=reset_experiment, args=(topic,))


def explore_navigation(topic):
    """Back to the prediction, or on to step 3."""
    with st.container(horizontal=True, horizontal_alignment='left', key=f'lab_{topic}_explore_nav'):
        _back_button(topic, 1)
        st.button(tr('Next: explain'), key=f'lab_{topic}_next_explain', type='primary',
                  on_click=go_to_step, args=(topic, 3))


# ---- Step 3: explain ---------------------------------------------------------------

def _set_answer_shown(topic, shown):
    """Show or hide the answer; a double click asks for the same thing twice."""
    st.session_state[f'lab_{topic}_answer_shown'] = shown


def _set_self_check(topic, choice):
    st.session_state[f'lab_{topic}_self_check'] = choice


def _prediction_outcome(topic):
    """How the prediction checked in step 1 turned out."""
    checked = st.session_state.get(f'lab_{topic}_checked')
    if checked is None:
        return
    correct = PREDICTIONS[topic][1][0]
    if checked == correct:
        st.success(tr('Your prediction was right.'))
    else:
        st.info(tr(f'Your prediction was “{tr(checked)}”; the experiment shows “{tr(correct)}”.'))


def explanation(topic, practice_action=None):
    """The question, an optional private note, and the answer behind a button.

    Nothing of the answer is on the page until "Show answer" is clicked, so the
    student explains first. The note is kept in this session only: it is not
    saved, graded or sent anywhere.
    """
    question, formula, answer = EXPLANATIONS[topic]
    shown = st.session_state.get(f'lab_{topic}_answer_shown', False)
    with st.container(key=f'lab_{topic}_explain'):
        help_heading(tr(question), tr('Only you see this. Write it first, then compare.'), level='subheader')
        st.text_area(tr('Your explanation'), key=f'lab_{topic}_explanation',
                     on_change=keep_value, args=(f'lab_{topic}_explanation',))
        st.button(tr('Hide answer') if shown else tr('Show answer'), key=f'lab_{topic}_show_answer',
                  width='content', on_click=_set_answer_shown, args=(topic, not shown))
        if shown:
            if formula is not None:
                st.latex(formula)
            st.write(tr(answer))
            _prediction_outcome(topic)
            st.markdown('**' + tr('Self-check') + '**')
            with st.container(horizontal=True, horizontal_alignment='left', key=f'lab_{topic}_self_check_row'):
                for choice, label in SELF_CHECKS.items():
                    st.button(tr(label), key=f'lab_{topic}_self_{choice}',
                              type='primary' if st.session_state.get(f'lab_{topic}_self_check') == choice else 'secondary',
                              on_click=_set_self_check, args=(topic, choice))
    if st.session_state.get(f'lab_{topic}_self_check') in SELF_CHECKS and practice_action is not None:
        with st.container(key=f'lab_{topic}_practice_action'):
            practice_action()
    with st.container(horizontal=True, horizontal_alignment='distribute', key=f'lab_{topic}_explain_nav'):
        _back_button(topic, 2)
        st.button(tr('Start again'), key=f'lab_{topic}_start_again',
                  on_click=reset_experiment, args=(topic,))
