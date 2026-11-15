export default function(component) {
  const { parentElement, data, setTriggerValue } = component;
  const root = parentElement.querySelector('[data-testid="tutor-root"]');
  const namespace = '__examPilotFloatingTutor';
  if (!root || !data || typeof data.session_id !== 'string') return;
  const zh = data.ui_language_zh === true;
  const text = (english, chinese) => zh ? chinese : english;
  root.hidden = false;

  // In-memory UI state survives Streamlit page reruns. It never goes to browser
  // storage, and a different server session discards the previous session's state.
  // Components v2 can invoke a renderer again when its data changes before its
  // unmount cleanup runs. Remove the previous renderer's handlers ourselves.
  if (typeof window[namespace]?.cleanup === 'function') window[namespace].cleanup();
  if (!window[namespace] || window[namespace].sessionId !== data.session_id) {
    window[namespace] = { sessionId: data.session_id, state: {
      x: null, y: null, hasMoved: false, open: false, draft: '', courseId: data.course_id || null,
      pending: null, clearPending: false, validation: '', focused: null,
      selectionStart: null, selectionEnd: null,
    }};
  }
  const state = window[namespace].state;
  const courseId = data.course_id || null;
  if (state.courseId !== courseId) {
    state.courseId = courseId;
    state.draft = '';
    state.pending = null;
    state.validation = '';
    state.focused = null;
  }
  const responseArrived = Boolean(state.pending && data.last_request_id === state.pending.request_id);
  if (responseArrived) state.pending = null;
  state.clearPending = false;

  const bubble = root.querySelector('[data-testid="tutor-launcher"]');
  root.querySelector('.tutor-small-pilot').src = bubble.querySelector('.tutor-pilot').src;
  bubble.title = text('Pilot · Your AI study assistant · Drag to move, or use arrow keys when focused', 'Pilot · 你的 AI 学习助手 · 拖动可移动，也可在聚焦时使用方向键');
  const panel = root.querySelector('[data-testid="tutor-panel"]');
  const header = root.querySelector('[data-testid="tutor-drag-handle"]');
  const close = root.querySelector('[data-testid="tutor-close"]');
  const clear = root.querySelector('[data-testid="tutor-clear"]');
  const course = root.querySelector('[data-testid="tutor-course"]');
  const messages = root.querySelector('[data-testid="tutor-messages"]');
  const status = root.querySelector('[data-testid="tutor-status"]');
  const form = root.querySelector('[data-testid="tutor-form"]');
  const question = root.querySelector('[data-testid="tutor-question"]');
  const send = root.querySelector('[data-testid="tutor-send"]');
  const counter = root.querySelector('[data-testid="tutor-counter"]');
  const maxChars = Math.max(1, Number(data.max_question_chars) || 4000);
  root.querySelector('.tutor-title-group p').textContent = text('Your AI study copilot', '你的 AI 学习助手');
  clear.setAttribute('aria-label', text('Clear conversation', '清空对话'));
  clear.title = text('Clear conversation', '清空对话');
  close.setAttribute('aria-label', text('Close Pilot', '关闭 Pilot'));
  close.title = text('Close Pilot', '关闭 Pilot');
  root.querySelector('label[for="tutor-question"]').textContent = text('Your question', '你的问题');
  root.querySelector('.tutor-input-help').textContent = text('Enter to send · Shift + Enter for a new line', '回车发送 · Shift + 回车换行');
  root.querySelector('.tutor-form-note > span').textContent = text('Each question uses this course’s summaries', '每次提问都会使用本课程的知识点摘要');
  send.firstChild.textContent = text('Send ', '发送 ');
  const listeners = [];
  let destroyed = false;
  let drag = null;
  let suppressClick = false;
  let focusFrame = null;
  const on = (target, type, handler, options) => {
    target.addEventListener(type, handler, options);
    listeners.push(() => target.removeEventListener(type, handler, options));
  };
  const viewport = () => {
    const visual = window.visualViewport;
    return { width: visual ? visual.width : window.innerWidth,
      height: visual ? visual.height : window.innerHeight,
      left: visual ? visual.offsetLeft : 0, top: visual ? visual.offsetTop : 0 };
  };
  const clamp = (value, min, max) => Math.min(Math.max(value, min), Math.max(min, max));
  const position = () => {
    const view = viewport();
    const margin = 12;
    const size = 64;
    if (!state.hasMoved || state.x === null || state.y === null) {
      state.x = view.left + view.width - size - 24;
      state.y = view.top + view.height - size - 24;
    }
    // On narrow screens the app header holds the sidebar expand button at the
    // top-left; keep the launcher below it so the navigation stays reachable.
    const appHeader = view.width <= 760
      ? document.querySelector('[data-testid="stHeader"]')?.getBoundingClientRect()
      : null;
    const upper = appHeader && appHeader.bottom > view.top
      ? Math.max(view.top + margin, appHeader.bottom + margin)
      : view.top + margin;
    const lower = view.top + view.height - size - margin;
    state.x = clamp(state.x, view.left + margin, view.left + view.width - size - margin);
    state.y = clamp(state.y, Math.min(upper, lower), lower);
    bubble.style.left = `${state.x}px`;
    bubble.style.top = `${state.y}px`;
    const panelWidth = Math.min(388, Math.max(200, view.width - 2 * margin));
    const desiredHeight = Math.min(560, Math.max(0, view.height - 2 * margin));
    const below = state.y + size + margin;
    const belowSpace = view.top + view.height - margin - below;
    const aboveSpace = state.y - margin - (view.top + margin);
    const leftSpace = state.x - margin - (view.left + margin);
    const rightSpace = view.left + view.width - margin - (state.x + size + margin);
    let panelHeight = desiredHeight;
    let left = clamp(state.x + size - panelWidth, view.left + margin, view.left + view.width - panelWidth - margin);
    let top;
    let overlap = false;
    if (Math.max(aboveSpace, belowSpace) >= desiredHeight) {
      top = aboveSpace >= belowSpace ? state.y - panelHeight - margin : below;
    } else if (Math.max(leftSpace, rightSpace) >= panelWidth) {
      left = leftSpace >= rightSpace ? state.x - panelWidth - margin : state.x + size + margin;
      top = clamp(state.y + size / 2 - panelHeight / 2, view.top + margin, view.top + view.height - panelHeight - margin);
    } else if (Math.max(aboveSpace, belowSpace) >= 310) {
      panelHeight = Math.min(desiredHeight, Math.max(aboveSpace, belowSpace));
      top = aboveSpace >= belowSpace ? state.y - panelHeight - margin : below;
    } else {
      // A short mobile/keyboard viewport has no space beside the launcher.
      // Keep every panel control reachable; closing restores the launcher.
      top = view.top + margin;
      overlap = true;
    }
    panel.style.width = `${panelWidth}px`;
    panel.style.height = `${panelHeight}px`;
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.classList.toggle('is-compact', panelHeight < 400);
    panel.classList.toggle('is-short', panelHeight < 310);
    bubble.classList.toggle('is-panel-overlap', state.open && overlap);
    bubble.tabIndex = state.open && overlap ? -1 : 0;
    bubble.setAttribute('aria-hidden', String(state.open && overlap));
  };
  const updateInput = () => {
    const busy = Boolean(state.pending);
    question.disabled = !courseId || busy;
    question.maxLength = maxChars;
    send.disabled = !courseId || busy || !question.value.trim();
    clear.disabled = busy || state.clearPending || !(data.messages || []).length;
    counter.textContent = `${question.value.length} / ${maxChars}`;
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
    question.placeholder = courseId ? text('What would you like to understand?', '你想了解什么？') : text('Open a course to ask a question', '先打开一门课程再提问');
  };
  const updateStatus = () => {
    const serverError = typeof data.error === 'string' ? data.error : '';
    const shownInMessages = (data.messages || []).some(message => message.role === 'error' && message.content === serverError);
    const error = state.validation || (shownInMessages ? '' : serverError);
    status.hidden = !state.pending && !error;
    status.classList.toggle('is-error', Boolean(error) && !state.pending);
    status.classList.toggle('is-pending', Boolean(state.pending));
    status.textContent = state.pending ? text('Thinking about your question…', '正在思考你的问题…') : error;
  };
  const appendMessage = (role, content, pending = false) => {
    const safeRole = ['user', 'assistant', 'error'].includes(role) ? role : 'assistant';
    const item = document.createElement('div');
    item.className = `tutor-message tutor-message-${safeRole}${pending ? ' tutor-message-pending' : ''}`;
    item.dataset.role = safeRole;
    const label = document.createElement('span');
    label.className = 'tutor-message-label';
    label.textContent = safeRole === 'user' ? text('You', '你') : safeRole === 'error' ? text('Couldn’t answer', '无法回答') : 'Pilot';
    const body = document.createElement('div');
    body.className = 'tutor-message-body';
    body.textContent = typeof content === 'string' ? content : '';
    item.append(label, body);
    messages.append(item);
  };
  const renderMessages = () => {
    messages.replaceChildren();
    const history = Array.isArray(data.messages) ? data.messages : [];
    if (!history.length && !state.pending) {
      const empty = document.createElement('div');
      empty.className = 'tutor-empty';
      const title = document.createElement('strong');
      title.textContent = courseId ? text('Let’s work through it together', '我们一起弄懂它') : text('Choose a course to get started', '先选择一门课程');
      const hint = document.createElement('p');
      hint.textContent = courseId ? (zh ? '可以提问概念解释、例题或知识点。' : 'Ask for an explanation, a worked example, or help understanding a topic.') : (zh ? '从主页打开课程后，可以在这里询问课程笔记。' : 'Open a course from the Dashboard, then ask about its study notes here.');
      empty.append(title, hint);
      messages.append(empty);
    }
    for (const message of history) appendMessage(message.role, message.content);
    if (state.pending) {
      const last = history.at(-1);
      if (!last || last.role !== 'user' || last.content !== state.pending.question) appendMessage('user', state.pending.question, true);
    }
    messages.scrollTop = messages.scrollHeight;
  };
  const openPanel = () => {
    state.open = true;
    panel.hidden = false;
    bubble.setAttribute('aria-expanded', 'true');
    bubble.setAttribute('aria-label', text('Close Pilot, your AI study assistant', '关闭 Pilot AI 学习助手'));
    position();
    focusFrame = requestAnimationFrame(() => {
      if (!destroyed && !question.disabled) question.focus({ preventScroll: true });
    });
  };
  const closePanel = () => {
    state.open = false;
    panel.hidden = true;
    bubble.setAttribute('aria-expanded', 'false');
    bubble.setAttribute('aria-label', text('Open Pilot, your AI study assistant', '打开 Pilot AI 学习助手'));
    position();
    bubble.focus({ preventScroll: true });
  };
  const submit = (event) => {
    if (event) event.preventDefault();
    if (!courseId || state.pending) return;
    const value = question.value.trim();
    if (!value) {
      state.validation = text('Write a question first.', '请先输入问题。');
      updateStatus();
      question.focus();
      return;
    }
    if (value.length > maxChars) {
      state.validation = zh ? `问题请勿超过 ${maxChars} 个字符。` : `Keep your question within ${maxChars} characters.`;
      updateStatus();
      return;
    }
    const requestId = crypto.randomUUID();
    state.pending = { request_id: requestId, session_id: data.session_id, course_id: courseId, question: value };
    state.draft = '';
    state.validation = '';
    question.value = '';
    renderMessages();
    updateInput();
    updateStatus();
    setTriggerValue('submit', state.pending);
  };

  question.value = state.draft;
  panel.dataset.currentCourseId = courseId || '';
  course.textContent = courseId ? `${text('Course', '课程')} · ${data.course_name || text('Current course', '当前课程')}` : text('No course selected', '尚未选择课程');
  course.title = course.textContent;
  panel.hidden = !state.open;
  bubble.setAttribute('aria-expanded', String(state.open));
  bubble.setAttribute('aria-label', state.open ? text('Close Pilot, your AI study assistant', '关闭 Pilot AI 学习助手') : text('Open Pilot, your AI study assistant', '打开 Pilot AI 学习助手'));
  renderMessages();
  updateInput();
  updateStatus();
  position();

  on(bubble, 'click', event => {
    if (suppressClick && event.detail > 0) {
      suppressClick = false;
      event.preventDefault();
      return;
    }
    suppressClick = false;
    state.open ? closePanel() : openPanel();
  });
  const startDrag = (event, target) => {
    if (event.button !== 0 || (target === header && event.target.closest('button'))) return;
    // Touch drags can finish without a compatibility click. Suppress only the
    // drag gesture's own click, never the first tap of the next gesture.
    suppressClick = false;
    drag = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY,
      baseX: state.x, baseY: state.y, moved: false, target };
    target.setPointerCapture(event.pointerId);
  };
  on(bubble, 'pointerdown', event => startDrag(event, bubble));
  on(header, 'pointerdown', event => startDrag(event, header));
  on(window, 'pointermove', event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    drag.moved = true;
    drag.target.classList.add('is-dragging');
    state.hasMoved = true;
    state.x = drag.baseX + dx;
    state.y = drag.baseY + dy;
    position();
    event.preventDefault();
  }, { passive: false });
  const endDrag = event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (drag.moved && drag.target === bubble) suppressClick = true;
    drag.target.classList.remove('is-dragging');
    if (drag.target.hasPointerCapture(event.pointerId)) drag.target.releasePointerCapture(event.pointerId);
    drag = null;
  };
  on(window, 'pointerup', endDrag);
  on(window, 'pointercancel', event => {
    endDrag(event);
    suppressClick = false;
  });
  on(bubble, 'keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') suppressClick = false;
    const step = event.shiftKey ? 40 : 12;
    const directions = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (directions[event.key]) {
      event.preventDefault();
      const [dx, dy] = directions[event.key];
      state.hasMoved = true;
      state.x += dx;
      state.y += dy;
      position();
    }
  });
  on(document, 'keydown', event => {
    if (event.key === 'Escape' && !event.isComposing && state.open) {
      event.preventDefault();
      event.stopPropagation();
      closePanel();
    }
  }, { capture: true });
  on(close, 'click', closePanel);
  on(form, 'submit', submit);
  on(question, 'keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) submit(event);
  });
  on(question, 'input', () => {
    state.draft = question.value;
    state.validation = '';
    updateInput();
    updateStatus();
  });
  on(clear, 'click', () => {
    if (state.pending || state.clearPending || !(data.messages || []).length) return;
    state.clearPending = true;
    clear.disabled = true;
    state.validation = '';
    setTriggerValue('clear', { request_id: crypto.randomUUID(), session_id: data.session_id, course_id: courseId });
  });
  on(window, 'resize', position);
  if (window.visualViewport) {
    on(window.visualViewport, 'resize', position);
    on(window.visualViewport, 'scroll', position);
  }
  if (state.open && (state.focused === 'question' || responseArrived) && !question.disabled) {
    focusFrame = requestAnimationFrame(() => {
      if (destroyed) return;
      question.focus({ preventScroll: true });
      if (state.selectionStart !== null) question.setSelectionRange(state.selectionStart, state.selectionEnd);
    });
  } else if (state.focused === 'bubble') bubble.focus({ preventScroll: true });

  const cleanup = () => {
    if (destroyed) return;
    destroyed = true;
    if (focusFrame !== null) cancelAnimationFrame(focusFrame);
    const active = parentElement.activeElement || document.activeElement;
    state.focused = active === question ? 'question' : active === bubble ? 'bubble' : null;
    state.selectionStart = question.selectionStart;
    state.selectionEnd = question.selectionEnd;
    state.draft = question.value;
    if (drag) {
      drag.target.classList.remove('is-dragging');
      if (drag.target.hasPointerCapture(drag.pointerId)) drag.target.releasePointerCapture(drag.pointerId);
    }
    for (const remove of listeners) remove();
    if (window[namespace]?.cleanup === cleanup) window[namespace].cleanup = null;
  };
  const entry = window[namespace];
  entry.cleanup = cleanup;
  // Auth's separate logout utility calls reset without mounting this Tutor on
  // the login screen. Normal component cleanup preserves rerun UI state.
  entry.reset = () => {
    cleanup();
    state.open = false;
    state.draft = '';
    state.pending = null;
    state.validation = '';
    state.courseId = null;
    state.focused = null;
    state.selectionStart = null;
    state.selectionEnd = null;
    question.value = '';
    messages.replaceChildren();
    root.hidden = true;
    if (window[namespace] === entry) delete window[namespace];
  };
  return cleanup;
}
