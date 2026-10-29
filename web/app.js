(() => {
  'use strict';
  const vm = window.BaseballViewModel;
  const $ = id => document.getElementById(id);
  const state = { chat: null, chats: [], busy: false, pending: null };
  let toastTimer;
  const safeStorage = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* Conversation data is saved by the local server. */ } }
  };
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, className, handler) => {
    const node = el('button', className, text);
    node.type = 'button';
    node.addEventListener('click', handler);
    return node;
  };
  function toast(text) {
    $('toast').textContent = text;
    $('toast').hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6500);
  }
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    let data;
    try { data=await response.json(); } catch { throw new Error('The website did not return a usable response. Please retry later.'); }
    if (!response.ok) {
      if (response.status === 401 && window.BaseballAccess) window.BaseballAccess.showSignIn(data.error || 'Please sign in again.');
      const error=new Error(data.error || 'The website could not complete this request.');
      Object.assign(error,data,{request_id:response.headers.get('X-Request-ID')});
      throw error;
    }
    return data;
  }
  function closeSidebar() {
    $('sidebar').classList.remove('open');
    $('sidebar-shade').hidden = true;
  }
  function scrollBottom() {
    const scroll = $('conversation-scroll');
    requestAnimationFrame(() => { scroll.scrollTop = scroll.scrollHeight; });
  }
  function busy(value) {
    state.busy = value;
    $('send').disabled = value;
    $('question').disabled = value;
    $('new-chat').disabled = value;
    $('context-hint').textContent = value ? 'Checking the records. Your question is saved when the answer returns.' :
      state.chat?.context ? 'Follow up with a player, a statistic, or another season.' : 'Ask in your own words.';
    document.querySelectorAll('.history-item, .starter, .choice, .primary-button').forEach(node => { node.disabled = value; });
  }
  async function refreshHistory() {
    state.chats = (await api('/api/chats')).chats;
    const history = $('history');
    history.replaceChildren();
    $('chat-count').textContent = state.chats.length;
    if (!state.chats.length) history.append(el('p', 'history-empty', 'Your temporary conversations will appear here.'));
    state.chats.forEach(chat => {
      const item = button('', 'history-item' + (state.chat?.id === chat.id ? ' active' : ''), () => openChat(chat.id));
      item.append(el('span', 'history-title', chat.title));
      item.append(el('small', '', `${chat.turn_count} ${chat.turn_count === 1 ? 'question' : 'questions'} · ${new Date(chat.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`));
      item.title = chat.title;
      if (state.chat?.id === chat.id) item.setAttribute('aria-current', 'page');
      item.disabled = state.busy;
      history.append(item);
    });
  }
  async function openChat(id) {
    if (state.busy) return;
    try {
      state.chat = await api(`/api/chats/${id}`);
      safeStorage.set('baseball-active-chat', id);
      renderChat();
      await refreshHistory();
      closeSidebar();
      $('question').focus();
    } catch (error) { toast(error.message); }
  }
  async function newChat() {
    if (state.busy) return;
    try {
      state.chat = await api('/api/chats', {});
      safeStorage.set('baseball-active-chat', state.chat.id);
      renderChat();
      await refreshHistory();
      closeSidebar();
      $('question').focus();
    } catch (error) { toast(error.message); }
  }
  function renderStats(presentation) {
    const fragment = document.createDocumentFragment();
    const columns = presentation.columns || [];
    const rows = presentation.rows || [];
    if (rows.length === 1) {
      const cards = el('div', 'stat-cards');
      columns.forEach(column => {
        const card = el('div', 'stat-card' + (['player_name', 'team_name'].includes(column.key) ? ' identity' : ''));
        card.append(el('span', 'stat-label', column.label), el('span', 'stat-value', rows[0][column.key]));
        cards.append(card);
      });
      fragment.append(cards);
    } else if (rows.length) {
      const wrap = el('div', 'table-wrap');
      wrap.tabIndex = 0;
      wrap.setAttribute('aria-label', 'Baseball statistics; scroll for all rows and columns');
      const table = el('table',presentation.ranked ? 'ranked' : '');
      const thead = el('thead'); const heading = el('tr');
      columns.forEach(column => { const th = el('th', '', column.label); th.scope = 'col'; th.dataset.field = column.key; heading.append(th); });
      thead.append(heading); table.append(thead);
      const tbody = el('tbody');
      rows.forEach(row => { const tr = el('tr'); columns.forEach(column => { const cell = el('td', '', row[column.key]); cell.dataset.field = column.key; tr.append(cell); }); tbody.append(tr); });
      table.append(tbody); wrap.append(table); fragment.append(wrap);
    }
    return fragment;
  }
  function renderChart(chart) {
    const panel = el('figure', 'chart-panel');
    const heading = el('figcaption', 'chart-heading');
    heading.append(el('h3', '', chart.label), el('small', '', 'Recorded results'));
    panel.append(heading);
    const bars = el('div', 'chart-bars');
    vm.chartRows(chart).forEach(point => {
      const row = el('div', 'chart-row');
      const label = el('span', 'chart-label', point.label); label.title = point.label;
      const track = el('div', 'chart-track');
      const bar = el('div', 'chart-bar'); bar.style.width = `${point.width}%`; bar.style.marginLeft = `${point.start}%`;
      const baseline = el('span', 'chart-zero'); baseline.style.left = `${point.zero}%`; track.append(baseline);
      track.setAttribute('aria-hidden', 'true'); track.append(bar);
      row.append(label, track, el('span', 'chart-value', point.formatted));
      bars.append(row);
    });
    panel.append(bars);
    return panel;
  }
  function renderDetails(result, turn) {
    const details = el('details', 'details');
    details.append(el('summary', '', 'How this answer was calculated'));
    const body = el('div', 'details-body');
    if (result.conversation?.resolved_question !== turn.question) {
      body.append(el('h4', '', 'Question answered'), el('p', '', result.conversation.resolved_question));
    }
    body.append(el('pre', '', result.presentation?.detail_text || ''));
    const meaning = { scope: result.filters, conditions: result.conditions,
      rate_definition: result.rate_definition, average_method: result.average_method,
      population: result.population, qualification: result.qualification,
      tie_policy: result.tie_policy, coverage: result.coverage };
    Object.entries(meaning).forEach(([name, value]) => {
      if (value == null || (typeof value === 'object' && !Object.keys(value).length)) return;
      body.append(el('h4', '', name.replaceAll('_', ' ')), el('pre', 'detail-json', typeof value === 'string' ? value : JSON.stringify(value, null, 2)));
    });
    details.append(body);
    return details;
  }
  function addChoices(container, turn) {
    const result = turn.result;
    const choices = el('div', 'choice-list');
    (result.clarification_options || []).forEach(option => {
      const item = button('', 'choice', () => sendQuestion(option.label, vm.selectionFor(option)));
      item.append(el('span', '', option.label), el('span', '', '→'));
      choices.append(item);
    });
    container.append(choices);
  }
  function renderTurn(turn, index) {
    const result = turn.result;
    const outcome = vm.outcome(result);
    const article = el('article', 'turn'); article.dataset.turnId = turn.id;
    const user = el('div', 'user-question'); user.append(el('div', 'user-bubble', turn.question)); article.append(user);
    const answer = el('div', 'answer');
    const top = el('div', 'answer-top'); const ball = el('img'); ball.src = '/ball.svg'; ball.alt = '';
    top.append(ball, el('span', '', 'Answer')); answer.append(top);
    if (outcome === 'result' || outcome === 'no_results') {
      answer.append(el('p', 'answer-text', result.plain_english_answer || 'No matching regular-season data was found.'));
      const presentation = result.presentation || {};
      if (presentation.context?.length) {
        const scope=el('dl','answer-scope');
        presentation.context.forEach(item=>{ const pair=el('div');pair.append(el('dt','',item.label),el('dd','',item.value));scope.append(pair); });
        answer.append(scope);
      }
      (presentation.warnings || []).forEach(message=>answer.append(el('p','coverage-warning',message)));
      answer.append(renderStats(presentation));
      if (vm.hasComparison(presentation.chart)) {
        const chart = renderChart(presentation.chart);
        const key = `baseball-chart-${turn.id}`;
        chart.hidden = safeStorage.get(key) === 'hidden';
        const actions = el('div', 'answer-actions');
        const toggle = button(chart.hidden ? '▥ Show chart' : '▥ Hide chart', 'text-button', () => {
          chart.hidden = !chart.hidden;
          toggle.textContent = chart.hidden ? '▥ Show chart' : '▥ Hide chart';
          toggle.setAttribute('aria-pressed', String(!chart.hidden));
          safeStorage.set(key, chart.hidden ? 'hidden' : 'shown');
        });
        toggle.setAttribute('aria-pressed', String(!chart.hidden));
        actions.append(toggle); answer.append(actions, chart);
      }
      answer.append(renderDetails(result, turn));
      answer.append(el('div', 'provenance', presentation.provenance || 'Read-only DuckDB'));
    } else if (outcome === 'needs_clarification') {
      const guidance = vm.clarificationGuidance(turn);
      answer.append(el('div', 'state-label', guidance.title), el('p', 'answer-text notice', guidance.message));
      const isPending = index === state.chat.turns.length - 1 || state.chat.context?.result?.conversation?.resolved_question === result.conversation?.resolved_question;
      if (isPending && state.chat.context?.result?.status === 'needs_clarification') {
        addChoices(answer, turn);
        answer.append(button('Choose or add a detail ↗', 'text-button', () => openClarification(turn)));
      } else answer.append(el('p', 'provenance', 'Clarification recorded in this conversation.'));
    } else if (outcome === 'unsupported') {
      answer.append(el('div', 'state-label', result.presentation?.title || 'Not supported in this version'), el('p', 'answer-text notice', result.unsupported_reason || 'This question is not supported yet. No substitute query was run.'));
    } else {
      const notice=vm.operationalNotice(result);
      answer.append(el('div','state-label',notice.title),el('p','answer-text notice error-text',notice.message));
      if (notice.retryable) answer.append(retryButton(turn.question,turn.selection,notice));
      if (notice.requestId) answer.append(el('small','provenance',`Support reference: ${notice.requestId}`));
    }
    article.append(answer);
    return article;
  }
  function renderChat() {
    if ($('clarification-dialog').open) $('clarification-dialog').close();
    $('turns').replaceChildren(); state.pending = null;
    const turns = state.chat?.turns || [];
    $('welcome').hidden = turns.length > 0;
    $('chat-title').textContent = turns.length ? state.chat.title : 'New conversation';
    turns.forEach((turn, index) => $('turns').append(renderTurn(turn, index)));
    if (state.chat?.context?.result?.status === 'needs_clarification') {
      state.pending = [...turns].reverse().find(turn => turn.result.status === 'needs_clarification');
    }
    busy(state.busy);
    if (turns.length) scrollBottom();
    else requestAnimationFrame(() => { $('conversation-scroll').scrollTop = 0; });
  }
  function openClarification(turn) {
    if (state.busy || !turn) return;
    state.pending = turn;
    const result = turn.result;
    const guidance = vm.clarificationGuidance(turn);
    $('clarification-title').textContent = guidance.title;
    $('clarification-question').textContent = guidance.question;
    $('clarification-message').textContent = guidance.message;
    $('clarification-label').textContent = guidance.label;
    $('clarification-input').placeholder = guidance.placeholder;
    $('clarification-example').textContent = guidance.example ? `Example: ${guidance.example}` : '';
    $('clarification-example').hidden = !guidance.example;
    const options = $('dialog-options'); options.replaceChildren();
    (result.clarification_options || []).forEach(option => {
      const item = button('', 'choice', () => {
        $('clarification-dialog').close();
        sendQuestion(option.label, vm.selectionFor(option));
      });
      item.append(el('span', '', option.label), el('span', '', '→')); options.append(item);
    });
    $('clarification-input').value = '';
    $('clarification-dialog').showModal();
  }
  function retryButton(question,selection,notice) {
    const retry=button('Retry question ↻','text-button',()=>sendQuestion(question,selection));
    if (notice.retryAfter !== null && notice.retryAfter > 0) {
      retry.disabled=true;
      const readyAt=new Date(Date.now()+notice.retryAfter*1000);
      retry.textContent=`Retry after ${readyAt.toLocaleTimeString([], {hour:'numeric',minute:'2-digit',second:'2-digit'})}`;
      const wait=Math.min(notice.retryAfter*1000,2147483647);
      setTimeout(()=>{ if (Date.now()>=readyAt.getTime()) {retry.disabled=false;retry.textContent='Retry question ↻';} },wait);
    }
    return retry;
  }
  function showRequestProblem(error,question,selection) {
    const notice=vm.operationalNotice(error);
    let panel=$('request-problem');
    if (!panel) {panel=el('section','request-problem');panel.id='request-problem';panel.setAttribute('role','status');$('composer-form').before(panel);}
    panel.replaceChildren(el('strong','',notice.title),el('p','',notice.message+' Your question remains in the text box.'));
    if (notice.retryable) panel.append(retryButton(question,selection,notice));
    if (notice.requestId) panel.append(el('small','',`Support reference: ${notice.requestId}`));
  }
  async function sendQuestion(question, selection) {
    if (state.busy) return;
    question = question?.trim();
    if (!question) return;
    const draft = $('question').value;
    busy(true);
    $('request-problem')?.remove();
    if ($('clarification-dialog').open) $('clarification-dialog').close();
    try {
      if (!state.chat) state.chat = await api('/api/chats', {});
      const payload = vm.sendPayload(question, state.chat, selection);
      $('welcome').hidden = true;
      const loading = el('div', 'loading'); loading.id = 'loading';
      const dots = el('span', 'loading-dots'); dots.append(el('i'), el('i'), el('i'));
      const pendingUser = el('div', 'user-question'); pendingUser.id = 'pending-user'; pendingUser.append(el('div', 'user-bubble', question));
      $('turns').append(pendingUser); loading.append(dots, el('span', '', 'Checking the records…')); $('turns').append(loading); scrollBottom();
      state.chat = await api(`/api/chats/${state.chat.id}/messages`, payload);
      safeStorage.set('baseball-active-chat', state.chat.id);
      $('question').value = ''; resizeComposer();
      busy(false); renderChat(); await refreshHistory();
      const latest = state.chat.turns.at(-1);
      if (latest.result.status === 'needs_clarification') openClarification(latest);
      else $('question').focus();
    } catch (error) {
      $('loading')?.remove(); $('pending-user')?.remove();
      $('question').value = draft || question; resizeComposer();
      showRequestProblem(error,question,selection);
      if (state.chat) { try { state.chat = await api(`/api/chats/${state.chat.id}`); renderChat(); } catch { /* Preserve the local draft if the server stopped. */ } }
    } finally { busy(false); }
  }
  function resizeComposer() { $('question').style.height = 'auto'; $('question').style.height = Math.min($('question').scrollHeight, 132) + 'px'; }
  $('composer-form').addEventListener('submit', event => { event.preventDefault(); sendQuestion($('question').value); });
  $('question').addEventListener('keydown', event => { if (vm.sendKey(event)) { event.preventDefault(); sendQuestion($('question').value); } });
  $('question').addEventListener('input', resizeComposer);
  $('new-chat').addEventListener('click', newChat);
  $('menu-button').addEventListener('click', () => { $('sidebar').classList.add('open'); $('sidebar-shade').hidden = false; });
  $('sidebar-shade').addEventListener('click', closeSidebar);
  $('starters').addEventListener('click', event => { const starter = event.target.closest('[data-question]'); if (starter) sendQuestion(starter.dataset.question); });
  $('close-dialog').addEventListener('click', () => { $('clarification-dialog').close(); $('question').focus(); });
  $('clarification-form').addEventListener('submit', event => { event.preventDefault(); sendQuestion($('clarification-input').value); });
  const theme = safeStorage.get('baseball-theme') || 'system';
  $('theme').value = ['system', 'light', 'dark'].includes(theme) ? theme : 'system';
  function setTheme(value) { if (value === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = value; }
  setTheme($('theme').value);
  $('theme').addEventListener('change', () => { setTheme($('theme').value); safeStorage.set('baseball-theme', $('theme').value); });
  (async () => {
    try {
      if (window.BaseballAccess && !await window.BaseballAccess.ready) return;
      await refreshHistory();
      const active = safeStorage.get('baseball-active-chat');
      if (active && state.chats.some(chat => chat.id === active)) await openChat(active);
      else renderChat();
    } catch (error) { toast('The free preview is temporarily busy or unavailable. Please try again shortly.'); }
  })();
})();
