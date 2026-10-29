"""Backend-owned browser presentation of verified evidence, without new stats."""
from __future__ import annotations

import math
from typing import Any

from .cli_formatting import FIELD_LABELS, _format_value, format_cli_result
from .query_registry import load_catalog, parse_request
from .entity_resolution import team_display_name


def _label(field: str, row: dict) -> str:
    if field in {'team_id', 'opponent_team_id'}:
        return 'Team' if field == 'team_id' else 'Opponent'
    if field in {'runs_for', 'runs_against', 'result'}:
        return {'runs_for': 'Team runs', 'runs_against': 'Opponent runs', 'result': 'Result'}[field]
    if field == 'venue':
        return 'Venue'
    if field == 'matching_season_list':
        return 'Seasons'
    if field == 'matching_seasons':
        return 'Matching season count'
    if field == 'incomplete_seasons':
        return 'Seasons with missing data'
    if field == 'rate_value':
        return row.get('rate_label', 'Rate')
    if field == 'denominator_value':
        return str(row.get('denominator', 'Denominator')).capitalize()
    if field == 'average_value' and row.get('metric') == 'walk_percentage':
        return 'Walk percentage'
    return FIELD_LABELS.get(field, field.replace('_', ' ').title())


def _formatted(field: str, value: Any, row: dict) -> str:
    if value is None:
        return 'Not available'
    if field == 'win_percentage':
        return f'{100*float(value):.1f}%'
    if field == 'venue':
        return {'home':'Home','away':'Road','all':'All venues'}.get(value,str(value))
    if field == 'pitching_population':
        return {'relief_appearances':'Relief appearances only','zero_starts':'Pitchers with zero starts'}.get(value,str(value))
    if field == 'matching_season_list':
        return ', '.join(str(v) for v in value) if value else 'None recorded'
    if field in {'strikeout_percentage','walk_percentage'}:
        return f'{float(value):.2f}%'
    if field in {'strikeouts_per_nine','walks_per_nine'}:
        return f'{float(value):.2f}'
    if field in {'team_id', 'opponent_team_id'}:
        return team_display_name(str(value), row.get('season'))
    if field == 'result':
        return {'W': 'Win', 'L': 'Loss', 'T': 'Tie'}.get(value, str(value))
    if field == 'date':
        return str(value).split('T')[0]
    if field == 'average_value':
        metric = row.get('metric')
        if metric == 'walk_percentage':
            return f'{float(value):.1f}%'
        if metric in {'avg', 'obp', 'slg', 'ops'}:
            return f'{float(value):.3f}'.lstrip('0')
    if field == 'rate_value' and str(row.get('rate_label', '')).endswith('%'):
        return f'{float(value):g}%'
    if field == 'fip' or field.endswith('_fip'):
        return f'{float(value):.2f}'
    if field == 'innings_pitched' or field.endswith('_innings_pitched'):
        return f'{float(value):.1f}'
    return _format_value(field, value)


def present_result(result: dict) -> dict:
    if result.get('status') != 'supported':
        from .result_explanation import failure_title
        result['presentation'] = {'state': result.get('status'), 'title':failure_title(result), 'columns': [], 'rows': [], 'chart': None}
        return result
    catalog = load_catalog()
    definition = catalog['queries'][result['query_id']]
    allowed = {'query_id', *definition.get('request_fields', ['limit'])}
    request = parse_request({key: value for key, value in result['validated_request'].items()
                             if key in allowed and value is not None
                             and not (key == 'conditions' and not value)}, catalog)
    rows = result['result_rows']
    from .ollama_client import requested_ranking_metrics
    named_metrics = requested_ranking_metrics(result.get('question', ''))
    fields = list((result.get('display') or {}).get('primary_columns') or [])
    # Fixed legacy leaderboards lack metric metadata; use their catalog definition.
    metric = request.metric or definition.get('semantics', {}).get('ranking_metric')
    if not metric and len(named_metrics) == 1:
        named = next(iter(named_metrics))
        if named in result['result_columns']:
            metric = named
    if metric in result['result_columns'] and metric not in fields:
        fields.append(metric)
    fields = [f for f in fields if f in result['result_columns']]
    if len(rows) == 1:
        identity = [f for f in fields if f in {'player_name', 'team_name', 'team_id', 'opponent_team_id', 'season', 'start_season', 'end_season', 'first_observed_season', 'last_observed_season'}]
        if request.query_id.endswith('_record'):
            fields = identity + [f for f in fields if f in {'games', 'wins', 'losses', 'ties', 'win_percentage'}]
        elif metric in fields:
            fields = identity + [metric]
        elif 'matching_games' in fields:
            fields = identity + ['matching_games']
        elif 'rate_value' in fields:
            fields = identity + [f for f in fields if f.startswith('numerator_') or f.startswith('denominator_')] + ['rate_value']
        elif 'average_value' in fields:
            fields = identity + ['average_value']
        else:
            focused = [f for f in fields if f in {'home_runs', 'avg', 'ops', 'wins', 'strikeouts', 'era', 'errors', 'matching_seasons', 'batting_home_runs', 'batting_ops', 'pitching_strikeouts', 'pitching_era', 'pooled_ops', 'pooled_era', 'combined_home_runs', 'combined_strikeouts', 'documented_seasons'}]
            fields = identity + focused if focused else fields[:7]
    from .question_intent import named_metrics, named_rates, requested_fields
    requested = list(requested_fields(result.get('question','')))
    # Primary output must reflect the actual request, including metric sets.
    projected = [f for f in requested if f in result['result_columns']]
    if projected:
        identities = [f for f in ('season','player_name','team_name','venue','first_observed_season','last_observed_season') if f in result['result_columns']]
        fields = identities + projected
    semantics=definition.get('semantics',{})
    profile=catalog.get('presentation_profiles',{}).get(semantics.get('stat_domain','').removeprefix('team_'))
    if not requested and semantics.get('operation') in {'player_summary','team_summary'} and profile:
        fields=[f for f in ('season','player_name','team_name','first_observed_season','last_observed_season') if f in result['result_columns'] and any(row.get(f) is not None for row in rows)] + [f for f in profile['fields'] if f in result['result_columns']]
    if 'matching_season_list' in result['result_columns']:
        fields = [f for f in ('player_name','matching_seasons','matching_season_list','incomplete_seasons') if f in result['result_columns']]
    if request.query_id == 'team_season_venue_records':
        fields = ['venue','wins','losses','win_percentage','games','ties']
    if request.query_id == 'mlb_batting_period_total':
        fields = ['start_season','end_season',request.metric,'recorded_component_subtotal','covered_batting_rows','recorded_batting_rows','metric_component_coverage_percent']
    if 'pitching_population' in result['result_columns']:
        fields.insert(0,'pitching_population')
    fields = list(dict.fromkeys(fields))
    exemplar = rows[0] if rows else {}
    columns = [{'key': f, 'label': _label(f, exemplar)} for f in fields]
    formatted_rows = [{f: _formatted(f, row.get(f), row) for f in fields} for row in rows]
    chart_field = metric
    if request.query_id in {'player_pitching_rate_summary', 'player_batting_rate_summary'}:
        chart_field = 'rate_value'
    if request.query_id.startswith('mlb_season_') and 'average_value' in result['result_columns']:
        chart_field = 'average_value'
    if 'matching_games' in result['result_columns']:
        chart_field = 'matching_games'
    if not chart_field and len(rows) > 1:
        chart_field = next((f for f in ('home_runs', 'combined_wins', 'pooled_ops', 'pooled_era') if f in result['result_columns']), None)
    if not chart_field:
        # Requested scalar summaries may use fixed families with no request metric.
        chart_field = next((f for f in fields if f in {'home_runs', 'strikeouts', 'errors', 'wins', 'ops', 'avg', 'era'}), None)
    points = []
    for row in rows:
        value = row.get(chart_field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            entity = ' · '.join((_formatted(f,row[f],row) if f=='venue' else str(row[f])) for f in ('player_name','team_name','season','venue') if row.get(f) is not None) or 'Recorded result'
            points.append({'label': str(entity), 'value': value, 'formatted': _formatted(chart_field, value, row)})
    chart = {'type': 'bar', 'metric': chart_field, 'label': _label(chart_field, exemplar), 'points': points} if len(points) >= 2 else None
    import pandas as pd
    frame = pd.DataFrame(rows, columns=result['result_columns'])
    detail = format_cli_result(frame, request=request, full_evidence=True, width=110) if rows else 'No matching regular-season data was found.'
    from .result_explanation import explain_result
    explanation=explain_result(result,request,fields)
    result['presentation'] = {
        **explanation, 'ranked':any(field.endswith('_rank') for field in result['result_columns']), 'state': 'result' if rows else 'no_results', 'columns': columns,
        'rows': formatted_rows, 'chart': chart, 'detail_text': detail,
        'provenance': f"Read-only DuckDB · {len(rows):,} result {'row' if len(rows) == 1 else 'rows'}",
    }
    return result
