-- Count exact-season regular-season team games satisfying every supplied condition.

WITH game_values AS (
    SELECT
        gid,
        date,
        number,
        team AS team_id,
        b_pa AS plate_appearances,
        b_h AS hits,
        b_hr AS home_runs,
        b_sb AS stolen_bases,
        CASE $condition_1_metric WHEN 'plate_appearances' THEN b_pa WHEN 'hits' THEN b_h WHEN 'home_runs' THEN b_hr WHEN 'stolen_bases' THEN b_sb END AS value_1,
        CASE $condition_2_metric WHEN 'plate_appearances' THEN b_pa WHEN 'hits' THEN b_h WHEN 'home_runs' THEN b_hr WHEN 'stolen_bases' THEN b_sb END AS value_2,
        CASE $condition_3_metric WHEN 'plate_appearances' THEN b_pa WHEN 'hits' THEN b_h WHEN 'home_runs' THEN b_hr WHEN 'stolen_bases' THEN b_sb END AS value_3,
        CASE $condition_4_metric WHEN 'plate_appearances' THEN b_pa WHEN 'hits' THEN b_h WHEN 'home_runs' THEN b_hr WHEN 'stolen_bases' THEN b_sb END AS value_4
    FROM team_stats
    WHERE team = $team_id
      AND stattype = 'value'
      AND LOWER(gametype) = 'regular'
      AND YEAR(date) = $season
      AND (
          $venue IS NULL
          OR ($venue = 'home' AND vishome = 'h')
          OR ($venue = 'away' AND vishome = 'v')
      )
), evaluated AS (
    SELECT *,
        (NOT $condition_1_active OR value_1 IS NOT NULL)
        AND (NOT $condition_2_active OR value_2 IS NOT NULL)
        AND (NOT $condition_3_active OR value_3 IS NOT NULL)
        AND (NOT $condition_4_active OR value_4 IS NOT NULL) AS components_complete,
        (NOT $condition_1_active OR CASE $condition_1_operator WHEN '>' THEN value_1 > $condition_1_value WHEN '>=' THEN value_1 >= $condition_1_value WHEN '<' THEN value_1 < $condition_1_value WHEN '<=' THEN value_1 <= $condition_1_value WHEN '=' THEN value_1 = $condition_1_value ELSE FALSE END)
        AND (NOT $condition_2_active OR CASE $condition_2_operator WHEN '>' THEN value_2 > $condition_2_value WHEN '>=' THEN value_2 >= $condition_2_value WHEN '<' THEN value_2 < $condition_2_value WHEN '<=' THEN value_2 <= $condition_2_value WHEN '=' THEN value_2 = $condition_2_value ELSE FALSE END)
        AND (NOT $condition_3_active OR CASE $condition_3_operator WHEN '>' THEN value_3 > $condition_3_value WHEN '>=' THEN value_3 >= $condition_3_value WHEN '<' THEN value_3 < $condition_3_value WHEN '<=' THEN value_3 <= $condition_3_value WHEN '=' THEN value_3 = $condition_3_value ELSE FALSE END)
        AND (NOT $condition_4_active OR CASE $condition_4_operator WHEN '>' THEN value_4 > $condition_4_value WHEN '>=' THEN value_4 >= $condition_4_value WHEN '<' THEN value_4 < $condition_4_value WHEN '<=' THEN value_4 <= $condition_4_value WHEN '=' THEN value_4 = $condition_4_value ELSE FALSE END) AS matches_conditions
    FROM game_values
), summary AS (
    SELECT
        COUNT(*) AS source_team_games,
        COUNT(*) FILTER (WHERE components_complete) AS covered_team_games,
        COUNT(*) FILTER (WHERE components_complete AND matches_conditions)
            AS counted_matching_games,
        MIN(date) FILTER (WHERE components_complete AND matches_conditions)
            AS first_matching_date,
        MAX(date) FILTER (WHERE components_complete AND matches_conditions)
            AS last_matching_date,
        LIST(gid ORDER BY date, number, gid) FILTER (
            WHERE components_complete AND matches_conditions
        ) AS matching_game_ids
    FROM evaluated
)
SELECT
    $team_id::VARCHAR AS team_id,
    $season::INTEGER AS season,
    COALESCE($venue, 'all') AS venue,
    'one regular-season team-game row' AS instance_definition,
    ($condition_1_active::INTEGER + $condition_2_active::INTEGER
        + $condition_3_active::INTEGER + $condition_4_active::INTEGER)
        AS condition_count,
    source_team_games,
    CASE WHEN source_team_games = covered_team_games
        THEN counted_matching_games
    END AS matching_games,
    first_matching_date,
    last_matching_date,
    matching_game_ids,
    ROUND(100.0 * covered_team_games / NULLIF(source_team_games, 0), 1)
        AS condition_component_coverage_percent
FROM summary;
