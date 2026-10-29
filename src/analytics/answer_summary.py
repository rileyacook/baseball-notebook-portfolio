"""Short deterministic plain-English summaries for validated result frames."""

from __future__ import annotations

import re
from calendar import month_name
from typing import Any

import pandas as pd

from .entity_resolution import (
    find_team_mentions,
    player_display_name,
    team_display_name,
)
from .query_registry import AnalyticsRequest


METRIC_LABELS = {
    "avg": "AVG", "obp": "OBP", "slg": "SLG", "ops": "OPS",
    "era": "ERA", "fip": "FIP", "home_runs": "HR",
    "strikeouts": "strikeouts", "hits": "hits", "wins": "wins",
    "losses": "losses", "saves": "saves", "stolen_bases": "stolen bases",
    "plate_appearances": "PA", "at_bats": "AB",
    "walk_percentage": "BB%", "walks_per_nine": "BB/9",
    "runs_batted_in": "RBI",
    "strikeouts_per_nine": "K/9",
    "strikeout_percentage": "K%",
    "home_run_percentage": "HR%",
    "hits_allowed": "hits allowed", "home_runs_allowed": "HR allowed",
    "runs_allowed": "runs allowed", "earned_runs_allowed": "earned runs allowed",
    "walks_allowed": "walks allowed", "batters_faced": "batters faced",
    "innings_outs": "recorded pitching outs",
    "errors": "errors",
}


def _value(value: Any, metric: str | None = None) -> str:
    if value is None or pd.isna(value):
        return "not available"
    if hasattr(value, "item"):
        value = value.item()
    if metric in {"avg", "obp", "slg", "ops"}:
        return f"{float(value):.3f}".lstrip("0")
    if metric in {"era", "fip"}:
        return f"{float(value):.2f}"
    if metric and metric.endswith("percentage"):
        return f"{float(value):.1f}%"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, int) else str(value)


def _scope(row: pd.Series) -> str:
    if "season" in row and not pd.isna(row["season"]):
        return f" in {int(row['season'])}"
    if all(field in row and not pd.isna(row[field]) for field in ("start_season", "end_season")):
        return f" in {int(row['start_season'])}" if row['start_season'] == row['end_season'] else f" from {int(row['start_season'])} through {int(row['end_season'])}"
    if all(
        field in row and not pd.isna(row[field])
        for field in ("requested_start_season", "requested_end_season")
    ):
        start = int(row["requested_start_season"])
        end = int(row["requested_end_season"])
        return f" in {start}" if start == end else f" from {start} through {end}"
    return ""


def _leader_name(row: pd.Series) -> str:
    if "player_id" in row and not pd.isna(row["player_id"]):
        return player_display_name(str(row["player_id"]))
    for field in ("team_name", "player_name"):
        if field in row and not pd.isna(row[field]):
            return str(row[field])
    if "season" in row and not pd.isna(row["season"]):
        return str(int(row["season"]))
    return "The first result"


def _possessive(value: str) -> str:
    return f"{value}'" if value.endswith("s") else f"{value}'s"


def _requested_batting_total(question: str) -> str | None:
    """Return one explicitly requested batting total for focused prose."""
    if not re.search(r"\bhow many\b", question, flags=re.IGNORECASE):
        return None
    patterns = (
        ("home_runs", r"\b(?:home[- ]runs?|homers?|hrs?)\b"),
        ("runs_batted_in", r"\b(?:runs? batted in|rbis?)\b"),
        ("stolen_bases", r"\b(?:stolen bases?|steals?|sb)\b"),
        ("plate_appearances", r"\b(?:plate appearances?|pas?)\b"),
        ("at_bats", r"\b(?:at[- ]?bats?|abs?)\b"),
        ("strikeouts", r"\b(?:strike[- ]?outs?|ks?)\b"),
        ("doubles", r"\bdoubles?\b"),
        ("triples", r"\btriples?\b"),
        ("walks", r"\bwalks?\b"),
        ("hits", r"\bhits?\b"),
        ("runs", r"\bruns?\b"),
    )
    for metric, pattern in patterns:
        if re.search(pattern, question, flags=re.IGNORECASE):
            return metric
    return None


def build_plain_english_answer(
    question: str,
    request: AnalyticsRequest,
    frame: pd.DataFrame,
) -> str:
    """Return one short answer sentence without model-written claims."""
    if frame.empty:
        return "No matching regular-season data was found."
    row = frame.iloc[0]
    if (
        "games" in row
        and (pd.isna(row["games"]) or int(row["games"]) == 0)
        and any(
            field in row and pd.isna(row[field])
            for field in ("wins", "losses", "matching_games")
        )
    ):
        return "No matching regular-season data was found for that exact scope."
    query_id = request.query_id
    player_name = player_display_name(str(row['player_id'])) if 'player_id' in row and not pd.isna(row['player_id']) else row.get('player_name','')
    from .question_intent import named_metrics, named_rates, requested_fields
    requested = list(requested_fields(question))
    if query_id == 'player_pitching_rates_summary':
        parts = [f"{_value(row[field],field)} {METRIC_LABELS.get(field,field.replace('_',' '))}" for field in requested if field in row]
        team = ' with '+team_display_name(request.team_id) if request.team_id else ''
        return f"{player_name}{team}{_scope(row)}: "+'; '.join(parts)+'.'
    if query_id == 'mlb_batting_period_total':
        value = _value(row[request.metric], request.metric)
        if pd.isna(row[request.metric]):
            missing = int(row['recorded_batting_rows']-row['covered_batting_rows'])
            return f"A complete MLB regular-season {request.metric.replace('_',' ')} total{_scope(row)} is unavailable: {missing:,} recorded batting rows lack this statistic. The known-component subtotal is {_value(row['recorded_component_subtotal'])}; it is not a complete historical total."
        return f"Recorded MLB regular-season {request.metric.replace('_', ' ')}{_scope(row)}: {value} ({_value(row['metric_component_coverage_percent'])}% of recorded rows have this component)."
    if query_id == 'team_season_venue_records':
        parts = [f"{item['venue']}: {_value(item['wins'])}-{_value(item['losses'])}" for _,item in frame.iterrows()]
        return f"{team_display_name(request.team_id,request.season)} in {request.season}: "+'; '.join(parts)+'.'
    if query_id in {'batting_condition_player_seasons','player_batting_condition_matches'}:
        years = ', '.join(str(int(y)) for y in frame['season'].drop_duplicates())
        return f"{len(frame)} recorded {'player-season' if query_id == 'batting_condition_player_seasons' else str(player_name)+' season'} matches are shown ({years}); every supplied condition is required."
    if 'batting' in query_id and ('summary' in query_id or query_id == 'player_batting_range_summary') and len(requested)>1:
        parts = [f"{_value(row[field], field)} {METRIC_LABELS.get(field,field.replace('_',' '))}" for field in requested if field in row]
        return f"{player_name}{_scope(row)}: "+', '.join(parts)+'.'
    from .query_registry import load_catalog
    catalog = load_catalog()
    semantics = catalog['queries'][query_id].get('semantics',{})
    profile = catalog.get('presentation_profiles',{}).get(semantics.get('stat_domain','').removeprefix('team_'))
    if not requested and semantics.get('operation') in {'player_summary','team_summary'} and profile:
        name = player_name or (team_display_name(request.team_id,request.season) if request.team_id else 'Recorded result')
        parts = [f"{_value(row[field],field)} {METRIC_LABELS.get(field,field.replace('_',' '))}" for field in profile['summary_fields'] if field in row]
        return f"{name}{_scope(row)}: "+', '.join(parts)+'.'
    player_name = (
        player_display_name(str(row["player_id"]))
        if "player_id" in row and not pd.isna(row["player_id"])
        else row.get("player_name")
    )

    if query_id == "player_team_service":
        count = int(row["distinct_database_team_id_count"])
        return f"{player_name} played for {count} documented team IDs."

    if query_id == "player_batting_condition_seasons":
        operator_words = {
            ">": "over", ">=": "at least", "<": "under",
            "<=": "at most", "=": "exactly",
        }
        descriptions = []
        for condition in request.conditions:
            label = METRIC_LABELS.get(condition.metric, condition.metric)
            value = _value(condition.value, condition.metric)
            descriptions.append(
                f"{label} {operator_words.get(condition.operator, condition.operator)} {value}"
            )
        criteria = " and ".join(descriptions)
        count = int(row['matching_seasons'])
        years = row.get('matching_season_list')
        year_text = ', '.join(str(int(y)) for y in years) if years is not None and hasattr(years, '__iter__') else ''
        answer = f"{player_name} had {count} {'season' if count == 1 else 'seasons'} with {criteria}" + (f": {year_text}." if year_text else '.')
        if row.get('incomplete_seasons',0):
            answer += f" {int(row['incomplete_seasons'])} additional recorded seasons have incomplete components, so this is a count of confirmed matches."
        return answer

    if query_id == "player_batting_top_n_seasons":
        metric = str(row["ranking_metric"])
        return (
            f"{player_name} finished in the top {int(row['top_n'])} in "
            f"{METRIC_LABELS.get(metric, metric)} in {int(row['matching_seasons'])} seasons."
        )

    if query_id == "player_batting_walk_percentage":
        return (
            f"{_possessive(str(player_name))} walk percentage was "
            f"{_value(row['walk_percentage'], 'walk_percentage')}{_scope(row)} "
            f"({_value(row['numerator_walks'])} walks in "
            f"{_value(row['denominator_plate_appearances'])} PA)."
        )

    if query_id in {
        "player_pitching_rate_summary",
        "player_batting_rate_summary",
    }:
        label = str(row["rate_label"])
        if pd.isna(row["rate_value"]):
            return (
                f"{player_name}'s {label} is unavailable because the required "
                "components are incomplete for that scope."
            )
        value = float(row["rate_value"])
        displayed = f"{value:g}%" if label.endswith("%") else f"{value:.2f}"
        team = (
            f" with {row['team_name']}"
            if "team_name" in row and not pd.isna(row["team_name"])
            else ""
        )
        has_explicit_year = bool(
            re.search(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", question)
        )
        if request.team_id is not None and not has_explicit_year:
            first = int(row["first_observed_season"])
            last = int(row["last_observed_season"])
            scope = f" from {first} through {last}"
        elif request.team_id is None and not has_explicit_year:
            scope = " for the documented career"
        else:
            scope = _scope(row)
        rate_name = {
            "K%": "strikeout rate",
            "BB%": "walk rate",
            "HR%": "home-run rate",
        }.get(label, label)
        return (
            f"{_possessive(str(player_name))} {rate_name} was "
            f"{displayed}{team}{scope}."
        )

    if query_id == "player_fielding_period_summary":
        scope = (
            " over the documented career"
            if not re.search(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", question)
            else _scope(row)
        )
        return (
            f"{player_name} committed {int(row['errors'])} documented "
            f"fielding errors{scope}."
        )

    if query_id == "player_game_batting_condition_count":
        threshold = int(row["condition_threshold"])
        metric = str(row["condition_metric"])
        metric_name = "home runs" if metric == "home_runs" else "hits"
        scope = (
            " over the documented career"
            if not re.search(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", question)
            else _scope(row)
        )
        comparison = {'>': 'over', '>=': 'at least', '<': 'under', '<=': 'at most', '=': 'exactly'}[request.conditions[0].operator]
        return f"{player_name} had {int(row['matching_games'])} games with {comparison} {threshold} {metric_name}{scope}."

    if query_id in {"team_batting_period_summary", "team_pitching_period_summary"}:
        metric = str(request.metric)
        exact_season = (
            request.start_season
            if request.start_season == request.end_season
            else None
        )
        team = team_display_name(str(request.team_id), exact_season)
        scope = _scope(row)
        if metric == "team_batting_summary":
            return f"Here are {_possessive(team)} batting stats{scope}."
        if metric == "team_pitching_summary":
            return f"Here are {_possessive(team)} pitching stats{scope}."
        value = _value(row[metric], metric)
        if query_id == "team_batting_period_summary" and metric == "home_runs":
            return f"{team} hit {value} HR{scope}."
        if query_id == "team_pitching_period_summary":
            if metric.endswith("_allowed"):
                allowed_name = METRIC_LABELS.get(
                    metric, metric.replace("_", " ")
                ).removesuffix(" allowed")
                return f"{team} pitchers allowed {value} {allowed_name}{scope}."
            return (
                f"{team} pitchers recorded {value} "
                f"{METRIC_LABELS.get(metric, metric.replace('_', ' '))}{scope}{population}."
            )
        return (
            f"{team} recorded {value} "
            f"{METRIC_LABELS.get(metric, metric.replace('_', ' '))}{scope}{population}."
        )

    if query_id in {
        "mlb_season_pooled_batting_rate",
        "mlb_season_unweighted_player_batting_rate_average",
    }:
        metric = str(row["metric"])
        if metric == "walk_percentage":
            return (
                f"MLB hitters walked in "
                f"{_value(row['average_value'], metric)} of plate appearances "
                f"in {int(row['season'])}."
            )
        return (
            f"The {METRIC_LABELS.get(metric, metric)} average was "
            f"{_value(row['average_value'], metric)} in {int(row['season'])}."
        )

    if query_id == "team_game_batting_condition_count":
        venue = " road" if row.get("venue") == "away" else " home" if row.get("venue") == "home" else ""
        mentions = find_team_mentions(question, season=request.season)
        team = mentions[0].display_name if mentions else str(row["team_id"])
        operator_words = {
            ">": "more than", ">=": "at least", "<": "fewer than",
            "<=": "at most", "=": "exactly",
        }
        metric_words = {
            "home_runs": ("home run", "home runs"),
            "hits": ("hit", "hits"),
            "runs": ("run", "runs"),
            "walks": ("walk", "walks"),
        }
        descriptions = []
        for condition in request.conditions:
            numeric = float(condition.value)
            value = int(numeric) if numeric.is_integer() else numeric
            singular, plural = metric_words.get(
                condition.metric,
                (
                    condition.metric.replace("_", " "),
                    condition.metric.replace("_", " "),
                ),
            )
            metric_name = singular if value == 1 else plural
            descriptions.append(
                f"{operator_words.get(condition.operator, condition.operator)} "
                f"{value} {metric_name}"
            )
        criteria = " and ".join(descriptions)
        return (
            f"{team} had {int(row['matching_games'])}{venue} games "
            f"with {criteria} in {int(row['season'])}."
        )

    if query_id in {'team_season_first_game', 'team_season_final_game'}:
        season = int(row['season'])
        team = team_display_name(str(row['team_id']), season)
        opponent = team_display_name(str(row['opponent_team_id']), season)
        game_date = pd.Timestamp(row['date'])
        day = f'{month_name[game_date.month]} {game_date.day}, {game_date.year}'
        kind = 'first' if query_id == 'team_season_first_game' else 'final'
        sentence = f'{team} played the {opponent} in their {kind} regular-season game of {season} on {day}.'
        if not pd.isna(row['runs_for']) and not pd.isna(row['runs_against']):
            verb = {'W': 'won', 'L': 'lost', 'T': 'tied'}.get(row['result'], 'finished')
            score = f"{int(row['runs_for'])}–{int(row['runs_against'])}"
            sentence += f' {team} {verb} {score}.'
        else:
            sentence += ' The score is unavailable in the recorded snapshot.'
        if not pd.isna(row['game_number']) and int(row['game_number']) > 0:
            sentence += f" This was game {int(row['game_number'])} on that date."
        return sentence

    if query_id == "team_calendar_date_record":
        mentions = find_team_mentions(question)
        team = mentions[0].display_name if mentions else str(row["team_id"])
        month = month_name[int(row["month"])]
        return (
            f"{team} went {int(row['wins'])}-{int(row['losses'])} on "
            f"{month} {int(row['day'])} from {int(row['start_season'])} "
            f"through {int(row['last_observed_season'])}."
        )

    if query_id.endswith("_record"):
        mentions = find_team_mentions(question)
        team = mentions[0].display_name if mentions else str(row["team_id"])
        opponent = mentions[1].display_name if len(mentions) > 1 else None
        against = f" against {opponent}" if opponent else ""
        return f"{team} went {int(row['wins'])}-{int(row['losses'])}{against}{_scope(row)}."

    if "two_way" in query_id:
        scope = _scope(row)
        if not re.search(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", question):
            first_values = [
                int(row[field])
                for field in (
                    "first_observed_batting_season",
                    "first_observed_pitching_season",
                )
                if field in row and not pd.isna(row[field])
            ]
            last_values = [
                int(row[field])
                for field in (
                    "last_observed_batting_season",
                    "last_observed_pitching_season",
                )
                if field in row and not pd.isna(row[field])
            ]
            if first_values and last_values:
                scope = f" from {min(first_values)} through {max(last_values)}"
        return (
            f"{player_name}{scope}: {_value(row['batting_home_runs'])} HR and "
            f"a {_value(row['batting_ops'], 'ops')} OPS; {_value(row['pitching_strikeouts'])} "
            f"strikeouts and a {_value(row['pitching_era'], 'era')} ERA."
        )

    if "pitching_summary" in query_id or query_id == "player_pitching_range_summary":
        if re.search(r"\bsaves?\b", question, re.IGNORECASE):
            return f"{player_name} recorded {_value(row['saves'])} saves{_scope(row)}."
        return (
            f"{player_name}{_scope(row)}: {_value(row['wins'])} wins, "
            f"{_value(row['strikeouts'])} strikeouts and a {_value(row['era'], 'era')} ERA."
        )

    if "batting_summary" in query_id or query_id == "player_batting_range_summary":
        requested_metric = _requested_batting_total(question)
        if requested_metric is not None and requested_metric in row:
            return (
                f"{player_name} recorded {_value(row[requested_metric], requested_metric)} "
                f"{METRIC_LABELS.get(requested_metric, requested_metric.replace('_', ' '))}"
                f"{_scope(row)}."
            )
        return (
            f"{player_name}{_scope(row)}: {_value(row['home_runs'])} HR, "
            f"{_value(row['avg'], 'avg')} AVG and a {_value(row['ops'], 'ops')} OPS."
        )

    fixed_leaders = {
        "career_batting_leaders": ("home_runs", "career"),
        "career_pitching_leaders": ("wins", "career"),
        "single_season_batting_leaders": ("ops", "single-season"),
        "single_season_pitching_leaders": ("fip", "single-season"),
        "season_pitching_fip_leaders": ("fip", "season"),
        "season_pitching_wins_leaders": ("wins", "season"),
    }
    if query_id in fixed_leaders:
        metric, scope_name = fixed_leaders[query_id]
        return (
            f"{_leader_name(row)} leads the {scope_name} ranking with "
            f"{_value(row[metric], metric)} {METRIC_LABELS.get(metric, metric)}{_scope(row)}."
        )

    if query_id == "relative_pair_eligibility":
        return f"Found {len(frame):,} eligible related-player pairs."

    if query_id == "best_related_pitching_pair":
        first = player_display_name(str(row["player_1_id"]))
        second = player_display_name(str(row["player_2_id"]))
        return f"{first} and {second} lead with a {_value(row['pooled_era'], 'era')} pooled ERA."

    if query_id == "best_related_hitting_pair":
        first = player_display_name(str(row["player_1_id"]))
        second = player_display_name(str(row["player_2_id"]))
        return f"{first} and {second} lead with a {_value(row['pooled_ops'], 'ops')} pooled OPS."

    if "ranking_metric" in row and not pd.isna(row["ranking_metric"]):
        metric = str(row["ranking_metric"])
        rank_field = next((field for field in frame.columns if field.endswith('_rank') or field == 'rank'), None)
        leaders = frame[frame[rank_field] == row[rank_field]] if rank_field else frame.iloc[:1]
        if request.query_id == 'player_batting_season_extremum':
            years = ', '.join(str(int(y)) for y in leaders['season'])
            return f"{player_name}'s {'lowest' if request.direction == 'ascending' else 'highest'} recorded season total was {_value(row[metric],metric)} {METRIC_LABELS.get(metric,metric.replace('_',' '))}: {years}."
        names = [_leader_name(item) for _,item in leaders.iterrows()]
        name = ', '.join(names[:-1])+' and '+names[-1] if len(names)>1 else names[0]
        verb = 'tie for first in' if len(names)>1 else 'lead' if 'team_name' in row else 'leads'
        population = {'relief_appearances': ' (relief appearances only)', 'zero_starts': ' (pitchers with zero starts in the period)'}.get(row.get('pitching_population'),'')
        article = "The " if "team_name" in row else ""
        scope = "" if "season_rank" in row else _scope(row)
        if "season_rank" in row:
            return (
                f"{name} was the leading season with {_value(row[metric], metric)} "
                f"{METRIC_LABELS.get(metric, metric.replace('_', ' '))}."
            )
        return (
            f"{article}{name} {verb} this ranking with {_value(row[metric], metric)} "
            f"{METRIC_LABELS.get(metric, metric.replace('_', ' '))}{scope}{population}."
        )

    return f"Found {len(frame):,} matching result{'s' if len(frame) != 1 else ''}."
