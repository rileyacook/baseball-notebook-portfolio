"""Form guidance for existing clarification states; never infer query parameters."""
from __future__ import annotations


def clarification_detail(result: dict) -> dict:
    message = (result.get('clarification_message') or '').casefold()
    options = result.get('clarification_options') or []
    if 'which team do you mean' in message:
        return _detail('identity', 'Which team?', 'Team name', 'Enter the team’s name', 'Atlanta Braves')
    if options:
        team = all(option.get('team_id') for option in options)
        return _detail('identity', 'Which team?' if team else 'Which player?',
                       'Team name or identifying detail' if team else 'Player name or identifying detail',
                       'Choose a name above, or add a team or season.', None)
    if 'denominator' in message:
        return _detail('rate_basis', 'How should I measure the rate?', 'Measure the rate per…',
                       'Plate appearance, batter faced, or inning', 'Per plate appearance')
    if 'comparison population' in message and 'average' in message:
        return _detail('average_method', 'How should I calculate the average?', 'Players to include and averaging method',
                       'All MLB hitters; pooled totals or average of player values',
                       'All MLB hitters, pooled from their totals')
    if 'population is all mlb' in message:
        return _detail('population', 'Which league should I include?', 'League',
                       'MLB, American League, or National League', 'All MLB')
    if 'minimum' in message and 'plate appearances' in message:
        return _detail('qualification', 'Which hitters should qualify?', 'Minimum plate appearances',
                       'Enter a minimum, such as 502 plate appearances', 'At least 502 plate appearances')
    if 'innings-pitched' in message or 'games-started' in message or 'all pitchers' in message:
        return _detail('qualification', 'Which pitchers should qualify?', 'Pitcher eligibility',
                       'All pitchers, or a minimum number of innings or starts', 'At least 162 innings pitched')
    if 'batting or pitching' in message:
        return _detail('stat_domain', 'Batting or pitching?', 'Type of statistic',
                       'Batting or pitching', 'Batting')
    if 'ranking statistic' in message or 'statistic you want to use for the ranking' in message:
        pitching = any(word in (result.get('question') or '').casefold() for word in ('pitcher', 'pitching'))
        return _detail('ranking_statistic', 'Which statistic should determine the ranking?', 'Ranking statistic',
                       'ERA, wins, strikeouts, or another statistic' if pitching else 'Home runs, OPS, or another statistic',
                       'ERA' if pitching else 'Home runs')
    if 'one season' in message or 'which time scope' in message:
        return _detail('time_scope', 'Which time period do you mean?', 'Season or range of seasons',
                       'One season, a year range, or career', '2024, or from 2020 through 2023')
    if 'franchise lineage' in message:
        return _detail('team_scope', 'Which team identities should be included?', 'Team identities and years',
                       'Name the cities or teams and the years to include', None)
    # A failed interpretation is not evidence of a missing season, player, etc.
    # Ask for a complete restatement rather than inventing a missing parameter.
    return _detail('complete_question', 'Restate the question', 'Full question to answer',
                   'Include the player or team and exactly what you want to know.', None)


def _detail(field, title, label, placeholder, example):
    return dict(field=field, title=title, label=label, placeholder=placeholder, example=example)
