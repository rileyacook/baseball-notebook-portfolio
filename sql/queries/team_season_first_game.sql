-- First recorded regular-season game, including the first game of a doubleheader.
SELECT team AS team_id, $season AS season, gid AS game_id, date,
       number AS game_number, opp AS opponent_team_id,
       CASE vishome WHEN 'h' THEN 'home' ELSE 'away' END AS venue,
       b_r AS runs_for, p_r AS runs_against,
       CASE WHEN win THEN 'W' WHEN loss THEN 'L' WHEN tie THEN 'T' END AS result
FROM team_stats
WHERE team = $team_id AND YEAR(date) = $season
  AND stattype = 'value' AND LOWER(gametype) = 'regular'
ORDER BY date ASC, number ASC NULLS LAST, gid ASC
LIMIT 1;
