"""Parse and represent conservative season-level metric conditions."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricCondition:
    """One exact metric comparison preserved from the user's question."""

    metric: str
    operator: str
    value: float


METRIC_ALIASES = {
    "avg": r"(?:avg|batting\s+average)",
    "obp": r"(?:obp|on[- ]base\s+percentage)",
    "slg": r"(?:slg|slugging\s+percentage)",
    "ops": r"ops",
    "home_runs": r"(?:hrs?|home[- ]runs?|homers?)",
    "hits": r"(?:hits|hit\s+total)",
    "stolen_bases": r"(?:sb|stolen\s+bases?|steals?)",
    "plate_appearances": r"(?:pas?|plate\s+appearances?)",
}

OPERATOR_WORDS = {
    "greater than or equal to": ">=",
    "at least": ">=",
    "no fewer than": ">=",
    "greater than": ">",
    "more than": ">",
    "over": ">",
    "less than or equal to": "<=",
    "at most": "<=",
    "no more than": "<=",
    "less than": "<",
    "fewer than": "<",
    "under": "<",
    "equal to": "=",
    "exactly": "=",
}

NUMBER_WORDS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}


def _numeric_value(text: str) -> float:
    """Convert one approved numeric token without interpreting free text."""
    lowered = text.casefold()
    if lowered in NUMBER_WORDS:
        return NUMBER_WORDS[lowered]
    return float(text.replace(",", ""))


def parse_metric_conditions(question: str) -> tuple[MetricCondition, ...]:
    """Extract explicit metric/operator/value triples without guessing."""
    found: list[tuple[int, MetricCondition]] = []
    number_words = "|".join(NUMBER_WORDS)
    number = rf"(?:\d[\d,]*(?:\.\d+)?|\.\d+|{number_words})"
    operators = "|".join(
        sorted((re.escape(word) for word in OPERATOR_WORDS), key=len, reverse=True)
    )
    symbols = r">=|<=|>|<|="
    for metric, alias in METRIC_ALIASES.items():
        patterns = (
            rf"\b({alias})\b\s*(?:of\s*)?({symbols}|{operators})\s*({number})",
            rf"\b({operators})\s*(?:an?\s+)?({number})\s*\b({alias})\b",
            rf"\b({alias})\b\s+({operators})\s*({number})",
        )
        for index, pattern in enumerate(patterns):
            for match in re.finditer(pattern, question, flags=re.IGNORECASE):
                groups = match.groups()
                if index == 1:
                    operator_text, value_text = groups[0], groups[1]
                else:
                    operator_text, value_text = groups[1], groups[2]
                operator = OPERATOR_WORDS.get(operator_text.casefold(), operator_text)
                value = _numeric_value(value_text)
                found.append((match.start(), MetricCondition(metric, operator, value)))
    # Baseball shorthand such as "hit over .275 with an OPS over .850" uses
    # "hit" to mean batting average. Limit this inference to a decimal rate
    # below 1.000 so counting requests such as "hit over 30 home runs" cannot
    # be converted into an AVG condition.
    for match in re.finditer(
        rf"\b(?:hit|batted)\s+({symbols}|{operators})\s+(\.\d{{1,3}})\b",
        question,
        flags=re.IGNORECASE,
    ):
        operator_text, value_text = match.groups()
        operator = OPERATOR_WORDS.get(operator_text.casefold(), operator_text)
        value = _numeric_value(value_text)
        if 0 <= value < 1:
            found.append((match.start(), MetricCondition("avg", operator, value)))
    unique: dict[tuple[str, str, float], tuple[int, MetricCondition]] = {}
    for item in found:
        condition = item[1]
        unique[(condition.metric, condition.operator, condition.value)] = item
    # Coordinate wording may share the first operator: "over .275 AVG and
    # .850 OPS" means both thresholds use >. Do not infer without a parsed
    # preceding condition and the explicit conjunction.
    ordered_existing = sorted(unique.values())
    if ordered_existing:
        shared_operator = ordered_existing[-1][1].operator
        for metric, alias in METRIC_ALIASES.items():
            for match in re.finditer(
                rf"\band\s+({number})\s*\b({alias})\b",
                question,
                flags=re.IGNORECASE,
            ):
                value = _numeric_value(match.group(1))
                condition = MetricCondition(metric, shared_operator, value)
                unique[(metric, shared_operator, value)] = (match.start(), condition)
    return tuple(condition for _, condition in sorted(unique.values()))
