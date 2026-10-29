"""Deterministic refusals for data grains without an approved contract."""

from __future__ import annotations

import re


def unsupported_frontier_reason(question: str) -> str | None:
    """Return a precise refusal reason for streak or inning-state requests."""
    lowered = question.casefold()
    if re.search(r"\b(?:postseason|playoffs?|world series)\b", lowered):
        return "unsupported_postseason_scope"
    if re.search(
        r"\b(?:streak|streaks|consecutive\s+(?:games|seasons|years|wins|losses|hits))\b",
        lowered,
    ):
        return "unsupported_streak_definition"
    if re.search(
        r"\b(?:after|through|at the end of|following)\s+(?:the\s+)?"
        r"(?:one|two|three|four|five|six|seven|eight|nine|"
        r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
        r"\d+(?:st|nd|rd|th)?)\s+innings?\b|"
        r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
        r"\d+(?:st|nd|rd|th)?)[- ]inning\s+(?:score|lead|deficit|state)\b|"
        r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
        r"\d+(?:st|nd|rd|th))\s+innings?\b",
        lowered,
    ):
        return "unsupported_inning_state"
    return None
