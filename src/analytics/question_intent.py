"""Shared question vocabulary and query-independent completeness checks.

No player facts or answers live here. The catalog defines metrics; SQL computes
values. Ambiguous names/rates are clarified rather than guessed.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import re
from .database import PROJECT_ROOT

METRIC_PATTERNS = {k: v['pattern'] for k, v in json.loads(
    (PROJECT_ROOT / 'config/analytics_catalog.json').read_text()
)['metric_definitions'].items()}


def normalize_wording(question: str) -> str:
    # Orthographic and grammatical equivalents, never numeric or entity guesses.
    question = question.replace('’', "'")
    if re.search(r'\b(?:top\s+\d+|led|lead|leader)\b', question, re.I):
        question = re.sub(r'^how often\b', 'How many seasons', question, flags=re.I)
    return question


def named_metrics(question: str) -> tuple[str, ...]:
    hits = [(m.start(), m.end(), key) for key, pattern in METRIC_PATTERNS.items()
            for m in re.finditer(pattern, question, re.I)]
    # Longest matches own their spans: intentional walks is not ordinary walks,
    # and runs batted in is not runs.
    selected = []
    for start, end, key in sorted(hits, key=lambda h: (-(h[1]-h[0]), h[0])):
        if not any(start < b and end > a for a, b, _ in selected):
            selected.append((start, end, key))
    return tuple(dict.fromkeys(k for _, _, k in sorted(selected)))


RATE_PATTERNS = {
    'strikeouts_per_nine': r'(?<!\w)k\s*/\s*9(?!\d)|\bstrikeouts? per (?:nine|9) innings?\b',
    'walks_per_nine': r'(?<!\w)bb\s*/\s*9(?!\d)|\bwalks? per (?:nine|9) innings?\b',
    'strikeout_percentage': r'(?<!\w)k\s*%|\bstrikeout (?:percentage|percent)\b',
    'walk_percentage': r'(?<!\w)bb\s*%|\bwalk (?:percentage|percent)\b',
}


def rate_mentions(question: str):
    hits = [(m.start(),m.end(),key) for key,p in RATE_PATTERNS.items() for m in re.finditer(p,question,re.I)]
    # Natural rate wording must name its denominator in the same clause.
    edges = list(re.finditer(r'\band\b|;',question,re.I))
    starts = [0]+[m.end() for m in edges]
    ends = [m.start() for m in edges]+[len(question)]
    for start,end in zip(starts,ends):
        clause=question[start:end]
        basis=re.search(r'\bper\s+(?:(?:nine|9)\s+innings?|batters?\s+faced|plate\s+appearances?)\b',clause,re.I)
        if not basis:
            continue
        for noun in re.finditer(r'\b(strikeouts?|walks?)\s+rate\b',clause,re.I):
            prefix='strikeout' if noun[1].lower().startswith('strikeout') else 'walk'
            key=prefix+('s_per_nine' if re.search(r'\b(?:nine|9)\b',basis[0]) else '_percentage')
            hits.append((start+min(noun.start(),basis.start()),start+max(noun.end(),basis.end()),key))
    return sorted(hits)


def named_rates(question: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(key for _,_,key in rate_mentions(question)))


def requested_fields(question: str) -> tuple[str, ...]:
    # A rate's numerator noun is not an additional count. A separate request
    # for that count remains visible, even when the same rate is also asked.
    spans=rate_mentions(question)
    masked=list(question)
    for start,end,_ in spans:
        masked[start:end]=' '*(end-start)
    return tuple(dict.fromkeys([*named_rates(question),*named_metrics(''.join(masked))]))


@dataclass(frozen=True)
class QuestionIntent:
    metrics: tuple[str, ...]
    rates: tuple[str, ...]
    role: str | None
    both_venues: bool

    @classmethod
    def read(cls, text: str):
        role = None
        if re.search(r'\b(?:relief|relievers?|bullpen)\b', text, re.I):
            role = ('zero_starts' if re.search(r'\b(?:zero|no|0) starts\b', text, re.I)
                    else 'relief_appearances' if re.search(r'\brelief appearances?\b', text, re.I)
                    else 'ambiguous_relief')
        elif re.search(r'\b(?:starters|starting pitchers?)\b', text, re.I):
            role = 'ambiguous_starter'
        both = bool(re.search(r'\bhome\b', text, re.I) and re.search(r'\b(?:road|away)\b', text, re.I))
        return cls(named_metrics(text), named_rates(text), role, both)


def requests_relationship_scope(question: str) -> bool:
    return bool(re.search(r'\b(?:related|relatives?|siblings?|brothers?|father|sons?|duos?|pairs?)\b', question, re.I))


def contract_mismatch(question, request, catalog):
    from .conditions import parse_metric_conditions, ambiguous_numeric_metric
    from .entity_resolution import find_player_mentions
    intent = QuestionIntent.read(question)
    definition = catalog['queries'][request.query_id]
    semantics = definition.get('semantics', {})
    def failure(message):
        return 'unsupported_query', message + ' No query was executed.'
    # Calendar filters cannot disappear in a season-only query. Full date
    # intervals have no approved request fields yet and are refused.
    from calendar import month_name, month_abbr
    months = {name.casefold(): i for i in range(1,13) for name in (month_name[i],month_abbr[i])}
    months['sept'] = 9
    month_pattern = '|'.join(sorted(months,key=len,reverse=True))
    dates = re.findall(rf'\b({month_pattern})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b',question,re.I)
    if len(dates)>1 or re.search(r'(?<!\d)\d{4}-\d{1,2}-\d{1,2}(?!\d)|(?<!\d)\d{1,2}/\d{1,2}/\d{4}(?!\d)',question):
        return failure('The approved interface cannot preserve that exact calendar-date interval.')
    if dates and (request.month,request.day)!=(months[dates[0][0].casefold()],int(dates[0][1])):
        return failure('This query does not preserve the requested calendar day.')
    if re.search(rf'\b(?:in|during|for)\s+({month_pattern})\b',question,re.I) and not dates:
        return failure('This query cannot preserve a calendar-month filter.')
    if requests_relationship_scope(question) and not str(semantics.get('entity_type','')).startswith('related_'):
        return failure('This query does not preserve the requested relationship population.')
    if intent.role and semantics.get('pitching_population') != intent.role:
        return failure('This query does not preserve the requested pitching population.')
    if intent.both_venues and semantics.get('venue_groups') != ['home', 'away']:
        return failure('This query cannot return both home and road groups.')
    if ambiguous_numeric_metric(question):
        return failure('A numeric metric requirement needs an explicit comparison.')
    players = find_player_mentions(question)
    if players and (request.player_id not in {p.player_id for p in players}) and not semantics.get('allows_named_population', False):
        return failure('This query does not preserve the named player.')
    expressed_conditions = parse_metric_conditions(question)
    if expressed_conditions and tuple(request.conditions) != expressed_conditions:
        # Qualification-only minima may be represented by their own validated field.
        fixed = semantics.get('qualification') or {}
        def qualification_consumed(c):
            return c.operator == '>=' and ((c.metric == 'plate_appearances' and c.value == request.min_pa) or (fixed.get('configurable') is False and c.metric == fixed.get('metric') and c.value == fixed.get('minimum')))
        residual = tuple(c for c in expressed_conditions if not qualification_consumed(c))
        if tuple(request.conditions) != residual:
            return failure('This query does not preserve every requested condition.')
    condition_metrics = {x.metric for x in expressed_conditions}
    metrics = set(requested_fields(question)) - set(intent.rates) - condition_metrics
    ranking = (semantics.get('operation') in {'leaderboard', 'player_season_extremum'}
               or bool(semantics.get('ranking_metrics')) or semantics.get('ranking_metric') is not None)
    if ranking:
        ranked = {request.metric, request.secondary_metric, semantics.get('ranking_metric')}
        ranked.update(semantics.get('ranking_metrics', []))
        if metrics - ranked:
            return failure('The ranking statistic does not match every requested statistic.')
    else:
        outputs = set(definition.get('output_metrics', []))
        consumed = set(definition.get('consumed_metrics', []))
        consumed.update(definition.get('metric_components', {}).get(request.metric, []))
        if semantics.get('operation') in {'occurrence_count', 'season_condition_count', 'top_n_season_frequency', 'player_game_condition_count'}:
            consumed |= set(definition.get('allowed_condition_metrics', []))
            if request.metric:
                consumed.add(request.metric)
        if metrics - outputs - consumed:
            return failure('This query cannot supply every requested statistic.')
    if intent.rates:
        represented = set(definition.get('represented_rates', []))
        if request.metric in definition.get('allowed_metrics', []):
            represented.add(request.metric)
        if set(intent.rates) - represented:
            return failure('This query cannot supply every requested rate.')
    return None
