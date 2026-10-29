"""Stable UI-facing result contract for validated analytics only."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from time import perf_counter
from typing import Any

import pandas as pd

from .answer_summary import build_plain_english_answer
from .cli_formatting import primary_display_fields
from .entity_resolution import player_display_name, team_display_name
from .ollama_client import translate_question
from .query_registry import execute_request, load_catalog


def _records(
    frame: pd.DataFrame,
    request: Any | None = None,
) -> list[dict[str, Any]]:
    records = [
        {key: _native_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    for record in records:
        if record.get("player_id"):
            record["player_name"] = player_display_name(record["player_id"])
        if record.get("team_id") and "team_name" in record:
            season = None
            if request is not None:
                season = request.season
                if season is None and request.start_season == request.end_season:
                    season = request.start_season
            record["team_name"] = team_display_name(record["team_id"], season)
    return records


def _native_value(value: Any) -> Any:
    """Convert a dataframe scalar to a JSON-friendly Python value."""
    if isinstance(value, (list, tuple)):
        return [_native_value(item) for item in value]
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        converted = value.tolist()
        if isinstance(converted, list):
            return [_native_value(item) for item in converted]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def _first_value(frame: pd.DataFrame, column: str) -> Any:
    """Return one displayed semantic value when the column is available."""
    if frame.empty or column not in frame.columns:
        return None
    return _native_value(frame.iloc[0][column])


def _coverage_values(frame: pd.DataFrame) -> dict[str, Any]:
    """Expose displayed coverage fields without hiding row variation."""
    coverage: dict[str, Any] = {}
    for column in frame.columns:
        if "coverage" not in column:
            continue
        values = [
            _native_value(value)
            for value in frame[column].drop_duplicates().tolist()
            if not pd.isna(value)
        ]
        coverage[column] = values[0] if len(values) == 1 else values
    return coverage


def answer_question(question: str, **translation_options: Any) -> dict[str, Any]:
    """Translate, validate, execute, and package one auditable answer."""
    started = perf_counter()
    catalog = load_catalog()
    translation = translate_question(question, catalog=catalog, **translation_options)
    return answer_translation(question, translation, catalog, started=started)


def answer_translation(
    question: str,
    translation: Any,
    catalog: dict[str, Any] | None = None,
    *,
    started: float | None = None,
) -> dict[str, Any]:
    """Package a validated translation after a caller's continuity checks."""
    started = perf_counter() if started is None else started
    catalog = load_catalog() if catalog is None else catalog
    result: dict[str, Any] = {
        "question": question,
        "status": translation.status,
        "reason_code": translation.reason_code,
        "plain_english_answer": None,
        "display": None,
        "clarification_message": translation.message if translation.status == "needs_clarification" else None,
        "clarification_options": [
            dict(option) for option in translation.clarification_options
        ],
        "unsupported_reason": translation.message if translation.status == "unsupported" else None,
        "query_id": None,
        "validated_request": None,
        "entities": {},
        "metrics": [],
        "time_scope": None,
        "filters": {},
        "conditions": [],
        "rate_definition": None,
        "average_method": None,
        "population": None,
        "aggregation_grain": None,
        "tie_policy": None,
        "qualification": None,
        "coverage": {"database_seasons": [catalog["request_schema"]["season_minimum"], catalog["request_schema"]["season_maximum"]]},
        "data_source": "Retrosheet-derived local DuckDB; regular season",
        "result_columns": [],
        "result_rows": [],
        "displayed_row_count": 0,
        "latency": None,
    }
    if translation.request is not None:
        request = translation.request
        definition = catalog["queries"][request.query_id]
        semantics = definition.get("semantics", {})
        frame = execute_request(request, catalog)
        request_data = asdict(request)
        result.update({
            "plain_english_answer": build_plain_english_answer(question, request, frame),
            "display": {
                "format": "stat_cards" if len(frame) == 1 else "leaderboard",
                "primary_columns": primary_display_fields(frame, request),
                "show_rank": len(frame) > 1,
                "tie_expanded": bool(
                    request.top_n is not None and len(frame) > request.top_n
                ),
            },
            "query_id": request.query_id,
            "validated_request": request_data,
            "entities": {key: request_data[key] for key in ("player_id", "team_id", "opponent_team_id") if request_data[key] is not None},
            "metrics": definition.get("output_metrics", []),
            "time_scope": semantics.get("time_scope"),
            "filters": {key: request_data[key] for key in ("season", "start_season", "end_season", "month", "day", "venue") if request_data[key] is not None},
            "conditions": [
                *list(request_data.get("conditions", ())),
                *[
                {"field": key, "operator": ">=", "value": request_data[key]}
                for key in ("min_pa", "min_ip_outs", "min_starts")
                if request_data.get(key) is not None
                ],
            ],
            "qualification": semantics.get("qualification"),
            "rate_definition": _first_value(frame, "rate_definition"),
            "average_method": _first_value(frame, "average_method")
                or semantics.get("average_method"),
            "population": _first_value(frame, "population")
                or _first_value(frame, "ranking_population")
                or semantics.get("ranking_population"),
            "aggregation_grain": semantics.get("aggregation_grain"),
            "tie_policy": _first_value(frame, "tie_policy")
                or semantics.get("tie_policy"),
            "coverage": {
                "database_seasons": [catalog["request_schema"]["season_minimum"], catalog["request_schema"]["season_maximum"]],
                **_coverage_values(frame),
            },
            "result_columns": list(frame.columns),
            "result_rows": _records(frame, request),
            "displayed_row_count": len(frame),
        })
    result["latency"] = {"seconds": round(perf_counter() - started, 3)}
    return result
