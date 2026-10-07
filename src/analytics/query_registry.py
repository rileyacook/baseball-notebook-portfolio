"""Validate and execute structured analytics requests safely."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .conditions import MetricCondition
from .database import PROJECT_ROOT, connect_read_only


DEFAULT_CATALOG_PATH = PROJECT_ROOT / "config" / "analytics_catalog.json"
ALLOWED_REQUEST_FIELDS = {
    "query_id",
    "limit",
    "season",
    "team_id",
    "month",
    "day",
    "start_season",
    "end_season",
    "player_id",
    "venue",
    "opponent_team_id",
    "metric",
    "secondary_metric",
    "direction",
    "min_pa",
    "min_ip_outs",
    "min_starts",
    "top_n",
    "conditions",
}


@dataclass(frozen=True)
class AnalyticsRequest:
    """A constrained request that references one approved saved query."""

    query_id: str
    limit: int = 25
    season: int | None = None
    team_id: str | None = None
    month: int | None = None
    day: int | None = None
    start_season: int | None = None
    end_season: int | None = None
    player_id: str | None = None
    venue: str | None = None
    opponent_team_id: str | None = None
    metric: str | None = None
    secondary_metric: str | None = None
    direction: str | None = None
    min_pa: int | None = None
    min_ip_outs: int | None = None
    min_starts: int | None = None
    top_n: int | None = None
    conditions: tuple[MetricCondition, ...] = ()


def load_catalog(
    catalog_path: Path | str = DEFAULT_CATALOG_PATH,
) -> dict[str, Any]:
    """Load the machine-readable analytics catalog."""
    path = Path(catalog_path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Analytics catalog not found:\n{path}")

    with path.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)

    if not isinstance(catalog.get("queries"), dict):
        raise ValueError("Analytics catalog must define a queries object.")

    return catalog


def parse_request(
    payload: str | dict[str, Any],
    catalog: dict[str, Any] | None = None,
) -> AnalyticsRequest:
    """Validate untrusted JSON or dictionary input from a future LLM."""
    active_catalog = catalog or load_catalog()

    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("Request must contain valid JSON.") from error
    else:
        data = payload

    if not isinstance(data, dict):
        raise ValueError("Analytics request must be a JSON object.")

    unexpected_fields = set(data) - ALLOWED_REQUEST_FIELDS
    if unexpected_fields:
        raise ValueError(
            f"Unsupported request fields: {sorted(unexpected_fields)}"
        )

    query_id = data.get("query_id")
    if not isinstance(query_id, str) or not query_id:
        raise ValueError("query_id must be a non-empty string.")

    if query_id not in active_catalog["queries"]:
        raise ValueError(f"Unknown or unapproved query_id: {query_id}")

    query_definition = active_catalog["queries"][query_id]
    allowed_query_fields = set(
        query_definition.get("request_fields", ["limit"])
    )
    provided_query_fields = {
        field
        for field in ALLOWED_REQUEST_FIELDS - {"query_id"}
        if data.get(field) is not None
    }
    unsupported_query_fields = provided_query_fields - allowed_query_fields
    if unsupported_query_fields:
        raise ValueError(
            f"Request fields not supported by {query_id}: "
            f"{sorted(unsupported_query_fields)}"
        )

    for field in query_definition.get("required_request_fields", []):
        if data.get(field) is None:
            raise ValueError(f"{field} is required for {query_id}.")

    limit = data.get("limit", 25)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer.")

    request_schema = active_catalog["request_schema"]
    minimum = request_schema["limit_minimum"]
    maximum = request_schema["limit_maximum"]
    if not minimum <= limit <= maximum:
        raise ValueError(f"limit must be between {minimum} and {maximum}.")

    season_minimum = request_schema["season_minimum"]
    season_maximum = request_schema["season_maximum"]
    season = data.get("season")
    if season is not None:
        if isinstance(season, bool) or not isinstance(season, int):
            raise ValueError("season must be an integer.")
        if not season_minimum <= season <= season_maximum:
            raise ValueError(
                f"season must be between {season_minimum} and "
                f"{season_maximum}."
            )

    team_id = data.get("team_id")
    if team_id is not None:
        if not isinstance(team_id, str) or not team_id:
            raise ValueError("team_id must be a non-empty string.")
        connection = connect_read_only()
        try:
            team_exists = connection.execute(
                "SELECT EXISTS(SELECT 1 FROM teams WHERE team = ?)",
                [team_id],
            ).fetchone()[0]
        finally:
            connection.close()
        if not team_exists:
            raise ValueError("team_id must identify a documented team.")

    month = data.get("month")
    day = data.get("day")
    if month is not None or day is not None:
        if (
            isinstance(month, bool)
            or not isinstance(month, int)
            or isinstance(day, bool)
            or not isinstance(day, int)
        ):
            raise ValueError("month and day must be integers.")
        try:
            date(2000, month, day)
        except ValueError as error:
            raise ValueError("month and day must form a valid date.") from error

    start_season = data.get("start_season")
    if start_season is not None:
        if isinstance(start_season, bool) or not isinstance(start_season, int):
            raise ValueError("start_season must be an integer.")
        if not season_minimum <= start_season <= season_maximum:
            raise ValueError(
                f"start_season must be between {season_minimum} and "
                f"{season_maximum}."
            )

    end_season = data.get("end_season")
    if end_season is not None:
        if isinstance(end_season, bool) or not isinstance(end_season, int):
            raise ValueError("end_season must be an integer.")
        if not season_minimum <= end_season <= season_maximum:
            raise ValueError(
                f"end_season must be between {season_minimum} and "
                f"{season_maximum}."
            )
    if start_season is not None and end_season is not None:
        if start_season > end_season:
            raise ValueError("start_season must not exceed end_season.")

    player_id = data.get("player_id")
    if player_id is not None:
        if not isinstance(player_id, str) or not player_id:
            raise ValueError("player_id must be a non-empty string.")
        connection = connect_read_only()
        try:
            player_exists = connection.execute(
                "SELECT EXISTS(SELECT 1 FROM people WHERE id = ?)",
                [player_id],
            ).fetchone()[0]
        finally:
            connection.close()
        if not player_exists:
            raise ValueError("player_id must identify a documented player.")

    venue = data.get("venue")
    if venue is not None and venue not in {"home", "away"}:
        raise ValueError("venue must be either home or away.")

    opponent_team_id = data.get("opponent_team_id")
    if opponent_team_id is not None:
        if not isinstance(opponent_team_id, str) or not opponent_team_id:
            raise ValueError("opponent_team_id must be a non-empty string.")
        connection = connect_read_only()
        try:
            opponent_exists = connection.execute(
                "SELECT EXISTS(SELECT 1 FROM teams WHERE team = ?)",
                [opponent_team_id],
            ).fetchone()[0]
        finally:
            connection.close()
        if not opponent_exists:
            raise ValueError(
                "opponent_team_id must identify a documented team."
            )
        if opponent_team_id == team_id:
            raise ValueError("team_id and opponent_team_id must differ.")

    metric = data.get("metric")
    secondary_metric = data.get("secondary_metric")
    allowed_metrics = set(query_definition.get("allowed_metrics", []))
    if metric is not None and metric not in allowed_metrics:
        raise ValueError("metric is not approved for this query.")
    if secondary_metric is not None and secondary_metric not in allowed_metrics:
        raise ValueError("secondary_metric is not approved for this query.")
    if metric is not None and metric == secondary_metric:
        raise ValueError("metric and secondary_metric must differ.")

    direction = data.get("direction")
    if direction is not None and direction not in {"ascending", "descending"}:
        raise ValueError("direction must be ascending or descending.")

    min_pa = data.get("min_pa")
    if min_pa is not None:
        if isinstance(min_pa, bool) or not isinstance(min_pa, int) or min_pa < 0:
            raise ValueError("min_pa must be a non-negative integer.")

    min_ip_outs = data.get("min_ip_outs")
    min_starts = data.get("min_starts")
    for field_name, value in (("min_ip_outs", min_ip_outs), ("min_starts", min_starts)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"{field_name} must be a non-negative integer.")

    top_n = data.get("top_n")
    if top_n is not None and (
        isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= 100
    ):
        raise ValueError("top_n must be an integer between 1 and 100.")

    raw_conditions = data.get("conditions", [])
    if not isinstance(raw_conditions, (list, tuple)):
        raise ValueError("conditions must be a list.")
    maximum_conditions = query_definition.get("maximum_conditions", 4)
    if len(raw_conditions) > maximum_conditions:
        raise ValueError(
            f"At most {maximum_conditions} conditions are supported by "
            f"{query_id}."
        )
    allowed_condition_metrics = set(
        query_definition.get("allowed_condition_metrics", [])
    )
    conditions: list[MetricCondition] = []
    for raw_condition in raw_conditions:
        if not isinstance(raw_condition, dict) or set(raw_condition) != {
            "metric", "operator", "value"
        }:
            raise ValueError("Each condition requires metric, operator, and value.")
        metric_name = raw_condition["metric"]
        operator = raw_condition["operator"]
        value = raw_condition["value"]
        if metric_name not in allowed_condition_metrics:
            raise ValueError("Condition metric is not approved for this query.")
        if operator not in {">", ">=", "<", "<=", "="}:
            raise ValueError("Condition operator is not approved.")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Condition value must be numeric.")
        if metric_name in {"plate_appearances", "hits", "home_runs", "stolen_bases"} and float(value) % 1:
            raise ValueError("Counting-stat condition values must be whole numbers.")
        conditions.append(MetricCondition(metric_name, operator, float(value)))
    if "conditions" in query_definition.get("required_request_fields", []) and not conditions:
        raise ValueError("At least one condition is required for this query.")

    return AnalyticsRequest(
        query_id=query_id,
        limit=limit,
        season=season,
        team_id=team_id,
        month=month,
        day=day,
        start_season=start_season,
        end_season=end_season,
        player_id=player_id,
        venue=venue,
        opponent_team_id=opponent_team_id,
        metric=metric,
        secondary_metric=secondary_metric,
        direction=direction,
        min_pa=min_pa,
        min_ip_outs=min_ip_outs,
        min_starts=min_starts,
        top_n=top_n,
        conditions=tuple(conditions),
    )


def resolve_query_path(
    request: AnalyticsRequest,
    catalog: dict[str, Any] | None = None,
) -> Path:
    """Resolve an approved query while preventing arbitrary file access."""
    active_catalog = catalog or load_catalog()
    relative_path = Path(active_catalog["queries"][request.query_id]["path"])
    query_path = (PROJECT_ROOT / relative_path).resolve()
    approved_root = (PROJECT_ROOT / "sql" / "queries").resolve()

    if approved_root not in query_path.parents:
        raise ValueError("Approved query must remain inside sql/queries.")

    if query_path.suffix.lower() != ".sql" or not query_path.is_file():
        raise FileNotFoundError(f"Approved SQL query not found:\n{query_path}")

    return query_path


def execute_request(
    request: AnalyticsRequest,
    catalog: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Execute one approved saved query through a read-only connection."""
    active_catalog = catalog or load_catalog()
    query_path = resolve_query_path(request, active_catalog)
    sql = query_path.read_text(encoding="utf-8")
    query_definition = active_catalog["queries"][request.query_id]
    request_values = {
        "limit": request.limit,
        "season": request.season,
        "team_id": request.team_id,
        "month": request.month,
        "day": request.day,
        "start_season": request.start_season,
        "end_season": request.end_season,
        "player_id": request.player_id,
        "venue": request.venue,
        "opponent_team_id": request.opponent_team_id,
        "metric": request.metric,
        "secondary_metric": request.secondary_metric,
        "direction": request.direction,
        "min_pa": request.min_pa,
        "min_ip_outs": request.min_ip_outs,
        "min_starts": request.min_starts,
        "top_n": request.top_n,
    }
    for index in range(4):
        condition = request.conditions[index] if index < len(request.conditions) else None
        request_values[f"condition_{index + 1}_active"] = condition is not None
        request_values[f"condition_{index + 1}_metric"] = condition.metric if condition else None
        request_values[f"condition_{index + 1}_operator"] = condition.operator if condition else None
        request_values[f"condition_{index + 1}_value"] = condition.value if condition else None
    parameters = {
        field: request_values[field]
        for field in query_definition.get("sql_parameters", [])
    }

    connection = connect_read_only()
    try:
        result = connection.execute(sql, parameters).fetchdf()
    finally:
        connection.close()

    return result.head(request.limit)
