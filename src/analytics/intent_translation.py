"""Propose approved operations from shared intent, without embedded answers."""
from __future__ import annotations
import re
from .question_intent import QuestionIntent, named_metrics, named_rates, requested_fields, requests_relationship_scope
from .entity_resolution import find_player_mentions, find_team_mentions, resolve_player_mentions_for_context, _player_aliases, normalize_entity_text, player_display_name
from .conditions import parse_metric_conditions, ambiguous_numeric_metric


def _clarify(message, reason='ambiguous_metric'):
    return 'needs_clarification', reason, message


def _one_edit(a, b):
    if abs(len(a)-len(b)) > 1 or a == b:
        return False
    if len(a) == len(b):
        different = [i for i in range(len(a)) if a[i] != b[i]]
        return len(different) == 1 or (len(different) == 2 and different[1] == different[0]+1
               and a[different[0]] == b[different[1]] and a[different[1]] == b[different[0]])
    if len(a) > len(b):
        a, b = b, a
    return any(a == b[:i]+b[i+1:] for i in range(len(b)))


def intent_clarification(question, catalog):
    intent = QuestionIntent.read(question)
    if intent.role in {'ambiguous_relief', 'ambiguous_starter'}:
        return _clarify('How should the pitching role be defined? For relief, specify relief appearances only, or pitchers with zero starts in the period. Starting-pitcher classification is not yet supported.', 'ambiguous_population')
    for condition in parse_metric_conditions(question):
        if condition.metric in {'avg','obp','slg','ops'} and condition.value >= 10:
            return _clarify('Please specify the rate threshold as a decimal. The value will not be silently rescaled.', 'ambiguous_rate_definition')
    if 'intentional_walks' in intent.metrics:
        return 'unsupported','unsupported_metric','Intentional walks are not exposed by the current approved queries; ordinary walks will not be substituted.'
    if re.search(r'\bwalks? rate\b', question, re.I) and not set(intent.rates)&{'walks_per_nine','walk_percentage'}:
        return _clarify('Should walk rate mean BB/9 (per nine innings) or BB% (per batter faced)? Please specify the denominator; the other requested statistic will be retained.', 'ambiguous_rate_definition')
    years = re.findall(r'\b(?:18|19|20)\d{2}\b',question)
    if re.search(r'\blast\s+\d+\s+years\b',question,re.I) and len(set(years)) != 2:
        return _clarify('Which start and end seasons should be included? Please give an explicit year range within the recorded data.', 'ambiguous_time_scope')
    if ambiguous_numeric_metric(question):
        return _clarify('Should the numeric statistic mean exactly, at least, over, under, or at most that value? Please state the comparison explicitly; all other conditions will be retained.', 'ambiguous_threshold')
    # Only offer a unique close documented identity. Never execute a correction.
    if not find_player_mentions(question):
        words=normalize_entity_text(question).split(); options=set()
        for pid, alias, _ in _player_aliases():
            bits=alias.split()
            if len(bits)!=2:
                continue
            for a,b in zip(words,words[1:]):
                if a==bits[0] and len(b)>=4 and _one_edit(b,bits[1]):
                    options.add(pid)
        if len(options)==1:
            return _clarify('Did you mean '+player_display_name(next(iter(options)))+'? Please ask again using that documented full name.', 'ambiguous_entity')
    # A one-edit metric suggestion is vocabulary based, never a silent rewrite.
    vocabulary={key for key in catalog['metric_definitions'] if key.isalpha() and len(key)>=5}
    entity_words={w for m in find_team_mentions(question) for w in normalize_entity_text(m.matched_alias).split()}
    entity_words |= {w for m in find_player_mentions(question) for w in normalize_entity_text(m.matched_alias).split()}
    for word in normalize_entity_text(question).split():
        if len(word)>=5 and word not in vocabulary and word+'s' not in vocabulary and word not in entity_words and not named_metrics(word):
            matches={v for v in vocabulary if '_' not in v and _one_edit(word,v)}
            if len(matches)==1 and word not in {'seasons','players','hitting','pitching','recorded','during','across','career','highest','lowest','before','between'}:
                return _clarify('Did you mean '+next(iter(matches))+'? Please restate the requested statistic to confirm.', 'ambiguous_metric')
    return None


def propose_intent(question, catalog):
    # Imports are local to keep request validation independent of transport.
    from .ollama_client import (explicit_years, requested_qualification, requested_stat_domain,
        requested_row_limit, ambiguous_player_result, requested_venue)
    years=list(dict.fromkeys(explicit_years(question)))
    if len(years)>2:
        return None
    low,high=catalog['request_schema']['season_minimum'],catalog['request_schema']['season_maximum']
    if not years:
        start,end=low,high
    elif len(years)==2:
        start,end=min(years),max(years)
    elif re.search(r'\bsince\b',question,re.I):
        start,end=years[0],high
    elif re.search(r'\bbefore\b',question,re.I):
        start,end=low,years[0]-1
    else:
        start=end=years[0]
    intent=QuestionIntent.read(question); domain=requested_stat_domain(question)
    metrics=list(intent.metrics);conditions=parse_metric_conditions(question)
    team_mentions=find_team_mentions(question,season=start if start==end else None)
    player_mentions=find_player_mentions(question)
    player_aliases={m.matched_alias for m in player_mentions}
    teams=[m.team_id for m in team_mentions if m.matched_alias not in player_aliases]
    teams=list(dict.fromkeys(teams))
    if re.search(r'\b(?:national|american) league\b',question,re.I):
        return None  # Existing population guard issues the explicit refusal.
    if re.search(r'\b(?:contract|salary|salaries|injury|injuries|statcast|exit velocity)\b',question,re.I):
        return 'unsupported','unsupported_query','The requested external context is outside the current recorded-statistics interface.'
    if requests_relationship_scope(question):
        return None  # Relationship contracts retain their existing validation.
    if len(teams)>1 or re.search(r'\b(?:against|versus|vs\.?)\b',question,re.I):
        return None  # Existing opponent-aware contracts own these scopes.
    if intent.both_venues and not player_mentions and len(teams)==1 and len(years)==1 and re.search(r'\b(?:record|win(?:ning)? percentages?)\b',question,re.I):
        return {'query_id':'team_season_venue_records','team_id':teams[0],'season':years[0],'limit':2}
    if intent.role in {'relief_appearances','zero_starts'}:
        if len(years) not in {1,2} or len(metrics)!=1 or player_mentions or teams:
            return None
        d=catalog['queries'][intent.role+'_pitching_metric_leaders']
        if metrics[0] not in d['allowed_metrics']:
            return None
        return {'query_id':intent.role+'_pitching_metric_leaders','start_season':start,'end_season':end,'metric':metrics[0],
                'direction':'ascending' if re.search(r'\b(?:fewest|lowest)\b',question,re.I) else 'descending',
                'min_ip_outs':0,'min_starts':0,'limit':requested_row_limit(question)}
    if len(intent.rates)>1 or (intent.rates and set(requested_fields(question))-set(intent.rates)):
        players=resolve_player_mentions_for_context(question,domain='pitching',season=start if start==end else None,team_id=teams[0] if teams else None)
        if len(players)>1:
            return ambiguous_player_result(question,season=start if start==end else None,domain='pitching',team_id=teams[0] if teams else None)
        if len(players)==1:
            return {'query_id':'player_pitching_rates_summary','player_id':players[0].player_id,'team_id':teams[0] if teams else None,'start_season':start,'end_season':end,'limit':1}
    if player_mentions and re.search(r'\b(?:what|which)\s+(?:season|year)\b',question,re.I) and re.search(r'\b(?:most|fewest|highest|lowest)\b',question,re.I):
        players=resolve_player_mentions_for_context(question,domain='batting')
        if len(players)!=1 or len(metrics)!=1 or teams or conditions or domain=='pitching':
            return None
        qualification=requested_qualification(question)
        if metrics[0] in {'avg','obp','slg','ops'} and qualification is None:
            return _clarify('What minimum plate appearances should qualify a season for this rate-stat comparison?', 'ambiguous_qualification')
        return {'query_id':'player_batting_season_extremum','player_id':players[0].player_id,'start_season':start,'end_season':end,
                'metric':metrics[0],'direction':'ascending' if re.search(r'\b(?:fewest|lowest)\b',question,re.I) else 'descending',
                'min_pa':qualification[1] if qualification else 0,'limit':1}
    if player_mentions and re.search(r'\bgames?\b',question,re.I) and conditions:
        if len(conditions)!=1 or conditions[0].metric not in catalog['queries']['player_game_batting_condition_count']['allowed_condition_metrics']:
            return None
        players=resolve_player_mentions_for_context(question,domain='batting',season=start if start==end else None,team_id=teams[0] if teams else None)
        if len(players)==1:
            return {'query_id':'player_game_batting_condition_count','player_id':players[0].player_id,'team_id':teams[0] if teams else None,'start_season':start,'end_season':end,'conditions':[c.__dict__ for c in conditions],'limit':1}
    if player_mentions and not teams and conditions and re.search(r'\b(?:what|which|list|show)\s+(?:the\s+)?(?:seasons|years)\b',question,re.I):
        players=resolve_player_mentions_for_context(question,domain='batting')
        if len(players)==1 and set(c.metric for c in conditions)<=set(catalog['queries']['player_batting_condition_matches']['allowed_condition_metrics']):
            return {'query_id':'player_batting_condition_matches','player_id':players[0].player_id,'start_season':start,'end_season':end,'conditions':[c.__dict__ for c in conditions],'limit':requested_row_limit(question,100)}
    if not player_mentions and not teams and conditions and re.search(r'\b(?:players|hitters|batters|player.seasons)\b',question,re.I):
        allowed=set(catalog['queries']['batting_condition_player_seasons']['allowed_condition_metrics'])
        if set(c.metric for c in conditions)<=allowed:
            return {'query_id':'batting_condition_player_seasons','start_season':start,'end_season':end,'conditions':[c.__dict__ for c in conditions],'limit':requested_row_limit(question,100)}
    if (not player_mentions and not teams and len(metrics)==1 and not conditions
            and re.search(r'\b(?:mlb|major league baseball)\b',question,re.I)
            and re.search(r'\b(?:how many|total)\b',question,re.I)
            and not re.search(r'\b(?:players|teams|seasons|leaders)\b',question,re.I)):
        if metrics[0] in catalog['queries']['mlb_batting_period_total']['allowed_metrics']:
            return {'query_id':'mlb_batting_period_total','start_season':start,'end_season':end,'metric':metrics[0],'limit':1}
    # Calendar questions belong to the existing date-aware operations.
    if re.search(r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b|\d{4}-\d{1,2}-\d{1,2}',question,re.I):
        return None
    # A complete record question has a deterministic existing contract.
    if not player_mentions and len(teams)==1 and len(years)==1 and re.search(r'\brecord\b',question,re.I) and not intent.both_venues:
        return {'query_id':'team_season_record','team_id':teams[0],'season':years[0],'venue':requested_venue(question),'limit':1}
    return None
