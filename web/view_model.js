/* Presentation helpers only. All baseball meaning and calculations come from Python. */
(function (root) {
  'use strict';
  const api = {
    sendKey(event) { return event.key === 'Enter' && !event.shiftKey && !event.isComposing; },
    selectionFor(option) {
      if (option.player_id) return { player_id: option.player_id };
      if (option.team_id) return { team_id: option.team_id };
      throw new Error('A choice needs a stable player or team identity.');
    },
    sendPayload(question, chat, selection) {
      if (typeof question !== 'string' || !question.trim() || question.length > 2000) throw new Error('Enter a question between 1 and 2,000 characters.');
      const payload = { question: question.trim(), expected_turn: chat.turns.length };
      if (selection) payload.selection = selection;
      return payload;
    },
    hasComparison(chart) {
      return Array.isArray(chart?.points) && chart.points.filter(p => typeof p.value === 'number' && Number.isFinite(p.value)).length >= 2;
    },
    chartRows(chart) {
      if (!chart || !Array.isArray(chart.points)) return [];
      // Keep backend order and every cutoff tie. Scaling is geometry, not a new statistic.
      const points = chart.points.filter(p => typeof p.value === 'number' && Number.isFinite(p.value));
      const minimum = Math.min(0, ...points.map(p => p.value));
      const maximum = Math.max(0, ...points.map(p => p.value));
      const extent = Math.max(maximum - minimum, 1e-12);
      const zero = -minimum / extent * 100;
      return points.map(p => ({ ...p, width: Math.abs(p.value) / extent * 100,
        start: p.value < 0 ? (p.value - minimum) / extent * 100 : zero, zero }));
    },
    outcome(result) {
      if (result.status === 'supported') return result.presentation?.state === 'no_results' ? 'no_results' : 'result';
      if (['needs_clarification', 'unsupported', 'error'].includes(result.status)) return result.status;
      return 'error';
    },
    operationalNotice(value) {
      const titles = {per_user_allowance:'Your testing allowance is reached',shared_query_busy:'The app is processing another question',
        request_budget:'Shared website allowance reached',shared_model_limit:'Shared AI allowance reached',provider_rate_limit:'AI provider allowance reached',
        model_timeout:'The AI request timed out',model_configuration:'Owner attention needed',model_invalid_response:'The AI response could not be verified',
        ollama_unavailable:'AI service unavailable',model_unavailable:'AI service unavailable',access_unavailable:'Account service unavailable',conversation_capacity:'Conversation limit reached',conversation_full:'Start another conversation'};
      let wait=Number.isInteger(value.retry_after_seconds) && value.retry_after_seconds >= 0 ? value.retry_after_seconds : null;
      if (typeof value.retry_at === 'string' && Number.isFinite(Date.parse(value.retry_at))) wait=Math.max(0,Math.ceil((Date.parse(value.retry_at)-Date.now())/1000));
      return { title: value.presentation?.title || titles[value.error_code] || 'Could not retrieve the answer',
        message:value.error_message || value.error || value.message || 'Please retry later.',
        retryable:value.retryable !== false,
        retryAfter:wait,
        requestId: /^[a-f0-9]{32}$/.test(value.request_id || '') ? value.request_id : null };
    },
    clarificationGuidance(turn) {
      const result = turn.result || {};
      const generic = /specify the player, statistic, or scope|describe what should change|name what should change|safely interpret that follow-up/i.test(result.clarification_message || '');
      const detail = result.clarification_detail || (generic ? {
        title: 'Restate the question', label: 'Full question to answer',
        placeholder: 'Include the player or team and exactly what you want to know.'
      } : { title: 'One more detail', label: 'Your answer to the question above', placeholder: 'Enter the requested detail…' });
      return { ...detail, question: turn.question,
        message: generic ? 'I could not connect this follow-up to the earlier question. Please write the question you want answered in full.' : result.clarification_message };
    }
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BaseballViewModel = api;
})(typeof window === 'undefined' ? globalThis : window);
