"""Bounded server-side continuation; analytics semantics remain catalog-owned."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .model_gateway import post_model
from .clarification_guidance import clarification_detail

from .conditions import METRIC_ALIASES, parse_metric_conditions
from .entity_resolution import find_player_mentions, find_team_mentions, normalize_entity_text
from .frontier_scope import unsupported_frontier_reason
from .ollama_client import (
    DEFAULT_MODEL, DEFAULT_OLLAMA_URL, OllamaConnectionError,
    RANKING_METRIC_PATTERNS, TranslationError, explicit_years,
    find_deferred_metric, has_unsafe_instruction, translate_question,
)
from .query_registry import load_catalog
from .result_contract import answer_translation
from .ui_presentation import present_result

GROUPS = {
    'entity': ('player_id',), 'team': ('team_id', 'opponent_team_id'),
    'time': ('season', 'start_season', 'end_season', 'month', 'day'),
    'metric': ('metric',), 'conditions': ('conditions',),
    'qualification': ('min_pa', 'min_ip_outs', 'min_starts'),
    'direction': ('direction',), 'tiebreaker': ('secondary_metric',),
    'ranking_size': ('top_n', 'limit'),
    'venue': ('venue',),
}
TIME_PATTERN = re.compile(
    r'\b(?:from|between)\s+(?:18|19|20)\d{2}\s+(?:through|to|and|[-–])\s+(?:18|19|20)\d{2}'
    r'|\b(?:since|before|after)\s+(?:18|19|20)\d{2}'
    r'|\b(?:in|for|during)\s+(?:the\s+)?(?:18|19|20)\d{2}(?:\s+season)?'
    r'|\b(?:latest|first)(?:\s+recorded)?(?:\s+(?:batting|pitching))?\s+season'
    r'|\b(?:entire\s+)?career\b', re.I,
)
EDIT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'edits': {'type': 'array', 'maxItems': 4, 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'old': {'type': 'string'}, 'new': {'type': 'string'}},
            'required': ['old', 'new'],
        }},
        'append': {'type': 'string'},
        'clarification': {'type': ['string', 'null']},
    }, 'required': ['edits', 'append', 'clarification'],
}


@dataclass
class Context:
    question: str
    result: dict[str, Any]


@dataclass
class Resolution:
    question: str
    route: str = 'standalone'
    allowed: set[str] = field(default_factory=set)
    selected: dict[str, str] = field(default_factory=dict)
    message: str | None = None


def facets(text: str) -> set[str]:
    """Identify which facets the actual user fragment explicitly discusses."""
    lower = text.casefold()
    groups: set[str] = set()
    if explicit_years(text) or re.search(r'\b(career|latest|first|last|final|season|year|since|before|after)\b', lower):
        groups.add('time')
    if find_player_mentions(text):
        groups.add('entity')
    if find_team_mentions(text):
        groups.add('team')
    if any(re.search(p, lower) for p in RANKING_METRIC_PATTERNS.values()) or re.search(r'\b(errors?|walks?|rates?|percent(?:age)?|k/9|bb/9)\b', lower):
        groups.add('metric')
    if parse_metric_conditions(text):
        groups.add('conditions')
    if re.search(r'\b(pa|plate appearances?|ip|innings?|starts?|qualif\w*|minimum|minima)\b', lower):
        groups.add('qualification')
    if re.search(r'\b(top|rank\w*|ascending|descending|highest|lowest|most|fewest|tiebreak\w*)\b', lower):
        groups.add('ranking')
    if re.search(r'\b(ascending|descending|highest|lowest|most|fewest)\b', lower):
        groups.add('direction')
    if re.search(r'\btiebreak\w*\b', lower):
        groups.add('tiebreaker')
    if re.search(r'\b(top|limit)\s+\d+', lower):
        groups.add('ranking_size')
    if re.search(r'\b(?:home(?![- ]runs?)|road|away|venue)\b', lower):
        groups.add('venue')
    if re.search(r'\b(batting|hitting|pitching|fielder|fielding|two-way)\b', lower):
        groups.add('domain')
    if re.search(r'\b(per|percentage|percent|denominator|k/9|bb/9)\b|%', lower):
        groups.add('denominator')
    if re.search(r'\b(pooled|weighted|unweighted|population|all hitters|all players)\b', lower):
        groups.add('population')
    return groups


def _replace_alias(question: str, alias: str, replacement: str) -> str:
    words = normalize_entity_text(alias).split()
    pattern = r'(?<!\w)' + r'[\W_]+'.join(map(re.escape, words)) + r'(?!\w)'
    updated, count = re.subn(pattern, lambda _: replacement, question, count=1, flags=re.I)
    if not count:
        raise ValueError('The chosen name could not be safely matched. Please use its full name in a complete question.')
    return updated


def _time_fragment(fragment: str) -> str | None:
    value = fragment.strip(' ?.\n').casefold()
    value = re.sub(r'^(?:what about|how about|and|instead|make that)\s+', '', value)
    value = re.sub(r'^(?:in|for|during)\s+', '', value)
    if re.fullmatch(r'(?:18|19|20)\d{2}', value):
        return 'in ' + value
    if re.fullmatch(r'(?:from|between)\s+\d{4}\s+(?:through|to|and)\s+\d{4}', value):
        return value
    if re.fullmatch(r'(?:since|before|after)\s+\d{4}', value):
        return value
    if value in {'career', 'his career', 'her career', 'their career', 'the entire career'}:
        return 'career'
    return None


def _model_edits(previous: str, fragment: str) -> dict[str, Any]:
    payload = {
        'model': DEFAULT_MODEL, 'stream': False, 'think': False,
        'format': EDIT_SCHEMA,
        'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 512},
        'messages': [
            {'role': 'system', 'content': (
                'Resolve a baseball follow-up only by minimal exact-substring edits of the prior complete question. '
                'Never answer, calculate, generate SQL, remove an unmentioned constraint, or infer identity. '
                'old must be an exact unique substring of the previous question, at most 120 characters. '
                'new and append must be exact substrings of the follow-up (case-insensitive). '
                'Use append for added information, preserving its wording. Use edits only for explicitly replaced facets. '
                'Preserve player, team, time, population, domain, denominator, conditions, qualification, direction and tiebreaker. '
                'Return clarification rather than guessing any unclear reference. Return exactly the supplied JSON schema. '
                'For adding a denominator or qualification, append that portion of the fragment. '
                'For changing a metric, replace only the old metric phrase. Never rewrite the whole question.'
            )},
            {'role': 'user', 'content': json.dumps({'previous_question': previous, 'follow_up': fragment})},
        ],
    }
    try:
        response = post_model(DEFAULT_OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        content = response.json()['message']['content']
        data = json.loads(content)
    except httpx.HTTPError as error:
        raise OllamaConnectionError('The AI service is busy or unavailable. Please try again in about a minute.') from error
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise TranslationError('The follow-up could not be interpreted safely. Please spell out the complete question.') from error
    return data


def _apply_edits(previous: str, fragment: str, proposal: dict, allowed: set[str], *, retain_fragment: bool = True) -> Resolution:
    if not isinstance(proposal, dict) or set(proposal) != {'edits', 'append', 'clarification'}:
        raise TranslationError('Invalid continuation proposal; no query was executed.')
    clarification_value = proposal['clarification']
    # A model may use an empty string for an absent clarification. Continue
    # through every edit validator rather than treating it as a question.
    if isinstance(clarification_value, str) and not clarification_value.strip():
        clarification_value = None
    if clarification_value is not None:
        if not isinstance(clarification_value, str):
            raise TranslationError('Invalid continuation clarification.')
        # Use controlled, specific wording when the model identifies a missing
        # season. Never ask again for a year the user already supplied, and
        # never show untrusted model instructions verbatim.
        needs_time = bool(re.search(r'\b(?:season|year|time period|time range)\b', clarification_value, re.I))
        supplied_time = bool(explicit_years(fragment) or re.search(r'\bcareer\b', fragment, re.I))
        message = ('Which season do you mean? Please specify one season or a range of seasons.'
                   if needs_time and not supplied_time else
                   'I could not connect this follow-up to the earlier question. Please write the question you want answered in full.')
        return Resolution(previous, 'clarification', message=message)
    edits, append = proposal['edits'], proposal['append']
    if not isinstance(edits, list) or len(edits) > 4 or not isinstance(append, str):
        raise TranslationError('Invalid continuation edits.')
    resolved = previous
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'old', 'new'}:
            raise TranslationError('Invalid continuation edit.')
        old, new = edit['old'], edit['new']
        if not isinstance(old, str) or not isinstance(new, str) or not old or len(old) > 120 or resolved.count(old) != 1:
            raise TranslationError('Continuation edit did not identify a unique phrase.')
        edit_groups = facets(old)
        if not edit_groups or not edit_groups <= allowed:
            raise TranslationError('The follow-up attempted to change an unmentioned constraint.')
        if new and normalize_entity_text(new) not in normalize_entity_text(fragment):
            raise TranslationError('The follow-up attempted to introduce unrequested wording.')
        if not new and not re.search(r'\b(?:remove|without|no|drop)\b', fragment, re.I):
            raise TranslationError('The follow-up attempted to remove a constraint.')
        resolved = resolved.replace(old, new, 1)
    if append:
        if normalize_entity_text(append) not in normalize_entity_text(fragment):
            raise TranslationError('The follow-up attempted to invent added meaning.')
        resolved = resolved.rstrip(' ?.') + '. ' + append
    if not edits and not append:
        return Resolution(previous, 'clarification', message='Please describe what should change, or ask a complete new question.')
    # Visible scope words cannot disappear from a model proposal.
    for pattern in [r'\b(?:road|away|home|pooled|unweighted|weighted|relief|starter|qualified)\b', r'\b(?:postseason|playoffs?|franchise)\b']:
        for token in re.findall(pattern, fragment, re.I):
            if not re.search(r'\b' + re.escape(token) + r'\b', resolved, re.I):
                raise TranslationError('A follow-up scope was not preserved.')
    for year in explicit_years(fragment):
        if year not in explicit_years(resolved):
            raise TranslationError('A follow-up year was not preserved.')
    new_conditions = parse_metric_conditions(fragment)
    if any(condition not in parse_metric_conditions(resolved) for condition in new_conditions):
        raise TranslationError('A follow-up condition was not preserved.')
    # Count-question grammar must not let a leftover verb such as "hit" become
    # the requested metric. Keep the player and complete trailing scope intact.
    if 'metric' in allowed:
        match = re.fullmatch(r"How many (.+?) did (.+?) (?:hit|have|record|allow) (.+?)\??", resolved, re.I)
        if match and any(re.fullmatch(pattern, match[1], re.I) for pattern in RANKING_METRIC_PATTERNS.values()):
            resolved = f"What was {match[2]}'s {match[1]} {match[3].rstrip(' ?')}?"
    # A fully represented, season-only command has no extra scope to retain.
    # Keep the entire fragment for every other follow-up so unconsumed meaning
    # still reaches the completeness gate.
    season_command = re.fullmatch(
        r'(?:change|switch)\s+(?:the\s+)?(?:season|year)\s+to\s+((?:18|19|20)\d{2})',
        fragment.strip(' ?.\n'), re.I,
    )
    if (season_command and allowed == {'time'}
            and explicit_years(resolved) == [int(season_command[1])]):
        retain_fragment = False
    if retain_fragment:
        # The completeness gate must see the entire actual user fragment,
        # including meaning the model proposal may have failed to consume.
        resolved = resolved.rstrip(' ?. ') + '. ' + fragment
    return Resolution(resolved, 'bounded_model_edit', allowed)


def resolve(question: str, context: Context | None, selection: dict | None = None) -> Resolution:
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError('Enter a question between 1 and 2,000 characters.')
    question = question.strip()
    catalog = load_catalog()
    if has_unsafe_instruction(question) or find_deferred_metric(question, catalog) or unsupported_frontier_reason(question):
        return Resolution(question, 'policy_refusal')
    if selection is not None:
        if context is None or context.result.get('status') != 'needs_clarification':
            raise ValueError('There is no pending choice. Please ask the complete question.')
        if not isinstance(selection, dict) or len(selection) != 1 or next(iter(selection)) not in {'player_id', 'team_id'}:
            raise ValueError('Select one of the offered player or team identities.')
        key, identity = next(iter(selection.items()))
        candidates = context.result.get('clarification_options', [])
        option = next((o for o in candidates if o.get(key) == identity), None)
        if option is None:
            raise ValueError('That choice is no longer available. Select a listed option.')
        original = context.question
        if key == 'player_id':
            mentions = find_player_mentions(original)
            if not mentions:
                raise ValueError('Use the selected documented name in a complete question.')
            original = _replace_alias(original, mentions[0].matched_alias, option['resolution_text'])
            group = 'entity'
        else:
            mentions = find_team_mentions(original)
            if not mentions:
                raise ValueError('Use the selected team in a complete question.')
            original = _replace_alias(original, mentions[0].matched_alias, identity)
            group = 'team'
        return Resolution(original, 'identity_selection', {group}, {key: identity})
    if context is None:
        return Resolution(question)
    if re.fullmatch(r'\d{1,2}', question):
        return Resolution(context.question, 'clarification', message='Choose a player or team using the buttons, or provide a name and context.')
    # Explicit complete questions start fresh even when an earlier clarification is pending.
    players, teams = find_player_mentions(question), find_team_mentions(question)
    contextual = bool(
        re.search(r'^(?:and\b|what about\b|how about\b|instead\b|make that\b|same\b)|\bthose\b', question, re.I)
        or (not players and re.search(r'\b(?:his|her|that player)\b', question, re.I))
        or (not (players or teams) and re.search(r'\btheir\b', question, re.I))
        or (not teams and re.search(r'\bthat team\b', question, re.I))
    )
    if not contextual and re.search(r'^(?:what|who|which|how|show|rank|compare|tell|top|bottom|list)\b', question, re.I) and (
        players or teams or 'metric' in facets(question) or re.search(r'\b(?:mlb|all players|all hitters|pitchers|hitters)\b', question, re.I)
    ):
        return Resolution(question)
    allowed = facets(question)
    time = _time_fragment(question)
    if time:
        previous = context.question
        matches = list(TIME_PATTERN.finditer(previous))
        if len(matches) > 1:
            return Resolution(previous, 'clarification', message='Which time scope should change? Please ask the complete question.')
        old_request = context.result.get('validated_request') or {}
        if (not matches and old_request.get('query_id') in {'team_season_first_game', 'team_season_final_game'}
                and len(explicit_years(previous)) == 1 and re.fullmatch(r'in \d{4}', time)):
            previous = re.sub(r'(?<!\d)' + str(old_request['season']) + r'(?!\d)', time[3:], previous, count=1)
        else:
            previous = TIME_PATTERN.sub(lambda _: time, previous, count=1) if matches else previous.rstrip(' ?. ') + ' ' + time + '?'
        return Resolution(previous, 'time_replacement', {'time'})
    simple = re.sub(r'^(?:what about|how about|and|instead|make that)\s+', '', question.strip(' ?.\n'), flags=re.I)
    # Common metric-only changes require no model proposal. Use the explicit
    # count noun, or a unique approved metric span; never replace a threshold.
    if any(re.fullmatch(pattern, simple, re.I) for pattern in RANKING_METRIC_PATTERNS.values()):
        count = re.match(r'How many (.+?) did ', context.question, re.I)
        metric_spans = []
        if count and any(re.fullmatch(pattern, count[1], re.I) for pattern in RANKING_METRIC_PATTERNS.values()):
            metric_spans = [count[1]]
        else:
            old_request = context.result.get('validated_request') or {}
            metric = old_request.get('metric')
            patterns = [RANKING_METRIC_PATTERNS[metric]] if metric in RANKING_METRIC_PATTERNS else list(RANKING_METRIC_PATTERNS.values())
            metric_spans = list(dict.fromkeys(match[0] for pattern in patterns for match in re.finditer(pattern, context.question, re.I)))
        if len(metric_spans) == 1 and not parse_metric_conditions(context.question):
            result = _apply_edits(context.question, question, {'edits': [{'old': metric_spans[0], 'new': simple}], 'append': '', 'clarification': None}, allowed, retain_fragment=False)
            result.route = 'metric_replacement'
            return result
    new_teams = find_team_mentions(question)
    old_teams = find_team_mentions(context.question)
    if contextual and new_teams and old_teams and len({t.matched_alias for t in new_teams}) == 1:
        if normalize_entity_text(re.sub(r'^the\s+', '', simple, flags=re.I)) == new_teams[0].matched_alias:
            updated = _replace_alias(context.question, old_teams[0].matched_alias, new_teams[0].matched_alias)
            return Resolution(updated, 'team_replacement', {'team'})
    new_players = find_player_mentions(question)
    old_players = find_player_mentions(context.question)
    if contextual and new_players and old_players and len({p.matched_alias for p in new_players}) == 1:
        updated = _replace_alias(context.question, old_players[0].matched_alias, new_players[0].matched_alias)
        remaining = re.sub(r'^(?:what about|how about|and)\s+', '', question, flags=re.I).strip(' ?. ')
        if normalize_entity_text(remaining) == new_players[0].matched_alias:
            return Resolution(updated, 'player_replacement', {'entity'})
    if context.result.get('status') == 'needs_clarification' and not contextual:
        supplement = re.sub(r'\bper batters faced\b', 'per batter faced', question, flags=re.I)
        supplement = re.sub(r'\bper plate appearances\b', 'per plate appearance', supplement, flags=re.I)
        return Resolution(context.question.rstrip(' ?. ') + '. ' + supplement, 'clarification_supplement', allowed)
    return _apply_edits(context.question, question, _model_edits(context.question, question), allowed)


def _inheritance_guard(context: Context, resolution: Resolution, translation: Any, catalog: dict, fragment: str = '') -> str | None:
    old = context.result.get('validated_request') or context.result.get('conversation', {}).get('parent_request')
    if not old or translation.request is None:
        return None
    from dataclasses import asdict
    new = asdict(translation.request)
    for group, fields in GROUPS.items():
        if group in resolution.allowed:
            continue
        for key in fields:
            before, after = old.get(key), new.get(key)
            if key == 'conditions':
                before, after = list(before or []), list(after or [])
            if before != after:
                return f'The follow-up could not preserve the previous {group} scope. Please ask the complete question.'
    # Mentioning one threshold/minimum cannot authorize dropping the others.
    changed_metrics = {c.metric for c in parse_metric_conditions(fragment)}
    removing = bool(re.search(r'\b(?:remove|without|no|drop)\b', fragment, re.I))
    for condition in old.get('conditions', []):
        metric = condition['metric']
        explicit_removal = removing and re.search(METRIC_ALIASES.get(metric, re.escape(metric)), fragment, re.I)
        if condition not in list(new.get('conditions') or []) and metric not in changed_metrics and not explicit_removal:
            return 'The follow-up could not preserve every previous condition. Please ask the complete question.'
    for key, pattern in {'min_pa': r'\b(?:PA|plate appearances?)\b', 'min_ip_outs': r'\b(?:IP|innings?)\b', 'min_starts': r'\bstarts?\b'}.items():
        if old.get(key) != new.get(key) and not re.search(pattern, fragment, re.I):
            return 'The follow-up could not preserve every previous qualification. Please ask the complete question.'
    old_semantics = catalog['queries'][old['query_id']].get('semantics', {})
    new_semantics = catalog['queries'][new['query_id']].get('semantics', {})
    for meaning in ['stat_domain', 'aggregation_grain', 'average_method', 'ranking_population']:
        allowed_group = {'stat_domain': 'domain', 'average_method': 'population', 'ranking_population': 'population', 'aggregation_grain': 'time'}[meaning]
        broad_time_change = (meaning == 'stat_domain' and resolution.route == 'time_replacement'
                             and not (facets(context.question) & {'domain', 'metric'}))
        if not broad_time_change and allowed_group not in resolution.allowed and old_semantics.get(meaning) != new_semantics.get(meaning):
            return 'The follow-up would change the statistical meaning. Please ask the complete question.'
    return None


def clarification(message: str) -> dict:
    return {'status': 'needs_clarification', 'plain_english_answer': None,
            'clarification_message': message, 'clarification_options': [],
            'validated_request': None, 'query_id': None, 'result_rows': [],
            'result_columns': [], 'displayed_row_count': 0}


def respond(question: str, context: Context | None = None, selection: dict | None = None) -> dict:
    """Check continuity before any approved SQL executes; normalize errors."""
    resolution = Resolution(context.question, 'clarification') if context else Resolution(question)
    try:
        resolution = resolve(question, context, selection)
        if resolution.message:
            result = clarification(resolution.message)
        else:
            catalog = load_catalog()
            translation = translate_question(resolution.question, catalog=catalog)
            failure = None
            if resolution.route == 'bounded_model_edit' and translation.status == 'unsupported' and translation.reason_code == 'unsupported_filter':
                failure = 'I could not safely represent that follow-up. Please ask the complete question, including its qualifications and scope.'
            if context and resolution.route not in {'standalone', 'policy_refusal'}:
                failure = failure or _inheritance_guard(context, resolution, translation, catalog, question)
            if translation.request:
                for key, identity in resolution.selected.items():
                    if getattr(translation.request, key) != identity:
                        failure = 'The selected identity could not be preserved. Please ask with the documented name or team ID.'
            if failure and context:
                resolution.question = context.question
            result = clarification(failure) if failure else answer_translation(resolution.question, translation, catalog)
        result = present_result(result)
    except OllamaConnectionError:
        result = {'status': 'error', 'error_code': 'ollama_unavailable', 'error_message': 'The AI service is busy or unavailable. Please try again in about a minute.', 'retryable': True}
    except TranslationError:
        result = present_result(clarification('I could not safely interpret that follow-up. Please name what should change or ask the complete question.'))
    except ValueError as error:
        result = {'status': 'error', 'error_code': 'invalid_question', 'error_message': str(error), 'retryable': False}
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Conversation request failed')
        result = {'status': 'error', 'error_code': 'unexpected_error', 'error_message': 'Something went wrong while retrieving the answer. Your question is saved; please retry.', 'retryable': True}
    result['conversation'] = {'resolved_question': resolution.question, 'route': resolution.route}
    if result.get('status') == 'needs_clarification':
        result['clarification_detail'] = clarification_detail(result)
    if result.get('status') == 'needs_clarification' and context and resolution.route not in {'standalone', 'policy_refusal'}:
        parent = context.result.get('validated_request') or context.result.get('conversation', {}).get('parent_request')
        if parent:
            result['conversation']['parent_request'] = parent
    return result
