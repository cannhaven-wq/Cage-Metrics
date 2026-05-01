-- =============================================================================
-- CAGE METRICS — Analytics views for the Stat Finder page
-- =============================================================================
-- Creates Postgres VIEWS that compute bettor-relevant aggregate stats from
-- the fights and fighters tables. The frontend reads these views directly
-- via the Supabase anon key.
--
-- Views are computed on-demand (not materialized) — they're cheap enough at
-- this dataset size and stay always-fresh as fights table updates.
--
-- Safe to re-run.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1) Younger fighter win rate
-- For every decided fight (winner_id IS NOT NULL), check if winner was the
-- younger fighter. Excludes fights where age is unknown for either side.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_younger_fighter_winrate CASCADE;
CREATE VIEW v_younger_fighter_winrate AS
WITH decided AS (
  SELECT
    f.id,
    f.fighter_a_id,
    f.fighter_b_id,
    f.winner_id,
    fa.age AS a_age,
    fb.age AS b_age,
    e.event_date
  FROM fights f
  JOIN events e ON e.id = f.event_id
  JOIN fighters fa ON fa.id = f.fighter_a_id
  JOIN fighters fb ON fb.id = f.fighter_b_id
  WHERE e.is_upcoming = false
    AND f.winner_id IS NOT NULL
    AND fa.age IS NOT NULL
    AND fb.age IS NOT NULL
    AND fa.age <> fb.age  -- exclude same-age fights from this analysis
)
SELECT
  COUNT(*) AS sample_size,
  SUM(CASE
    WHEN (a_age < b_age AND winner_id = fighter_a_id) THEN 1
    WHEN (b_age < a_age AND winner_id = fighter_b_id) THEN 1
    ELSE 0
  END)::float / NULLIF(COUNT(*), 0) AS younger_winrate
FROM decided;

-- ---------------------------------------------------------------------------
-- 2) Stance matchups: southpaw vs orthodox
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_southpaw_vs_orthodox CASCADE;
CREATE VIEW v_southpaw_vs_orthodox AS
WITH stance_fights AS (
  SELECT
    f.winner_id,
    f.fighter_a_id,
    f.fighter_b_id,
    fa.stance AS a_stance,
    fb.stance AS b_stance
  FROM fights f
  JOIN events e ON e.id = f.event_id
  JOIN fighters fa ON fa.id = f.fighter_a_id
  JOIN fighters fb ON fb.id = f.fighter_b_id
  WHERE e.is_upcoming = false
    AND f.winner_id IS NOT NULL
    AND (
      (fa.stance = 'Southpaw' AND fb.stance = 'Orthodox')
      OR (fa.stance = 'Orthodox' AND fb.stance = 'Southpaw')
    )
)
SELECT
  COUNT(*) AS sample_size,
  SUM(CASE
    WHEN (a_stance = 'Southpaw' AND winner_id = fighter_a_id) THEN 1
    WHEN (b_stance = 'Southpaw' AND winner_id = fighter_b_id) THEN 1
    ELSE 0
  END)::float / NULLIF(COUNT(*), 0) AS southpaw_winrate
FROM stance_fights;

-- ---------------------------------------------------------------------------
-- 3) Reach advantage win rate
-- For fights where both fighters have known reach AND the difference is >= 2"
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_reach_advantage_winrate CASCADE;
CREATE VIEW v_reach_advantage_winrate AS
WITH reach_fights AS (
  SELECT
    f.winner_id,
    f.fighter_a_id,
    f.fighter_b_id,
    fa.reach_in AS a_reach,
    fb.reach_in AS b_reach
  FROM fights f
  JOIN events e ON e.id = f.event_id
  JOIN fighters fa ON fa.id = f.fighter_a_id
  JOIN fighters fb ON fb.id = f.fighter_b_id
  WHERE e.is_upcoming = false
    AND f.winner_id IS NOT NULL
    AND fa.reach_in IS NOT NULL
    AND fb.reach_in IS NOT NULL
    AND ABS(fa.reach_in - fb.reach_in) >= 2  -- meaningful reach gap only
)
SELECT
  COUNT(*) AS sample_size,
  SUM(CASE
    WHEN (a_reach > b_reach AND winner_id = fighter_a_id) THEN 1
    WHEN (b_reach > a_reach AND winner_id = fighter_b_id) THEN 1
    ELSE 0
  END)::float / NULLIF(COUNT(*), 0) AS longer_reach_winrate,
  AVG(ABS(a_reach - b_reach))::float AS avg_reach_gap_in
FROM reach_fights;

-- ---------------------------------------------------------------------------
-- 4) Title fight finish rate
-- Are title fights more or less likely to go the distance?
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_title_finish_rate CASCADE;
CREATE VIEW v_title_finish_rate AS
SELECT
  COUNT(*) FILTER (WHERE is_title_fight = true) AS title_fights,
  COUNT(*) FILTER (WHERE is_title_fight = true 
                   AND method NOT LIKE 'Decision%' 
                   AND method NOT IN ('Overturned', 'Other'))::float
    / NULLIF(COUNT(*) FILTER (WHERE is_title_fight = true), 0) AS title_finish_rate,
  COUNT(*) FILTER (WHERE is_title_fight = false) AS non_title_fights,
  COUNT(*) FILTER (WHERE is_title_fight = false 
                   AND method NOT LIKE 'Decision%' 
                   AND method NOT IN ('Overturned', 'Other'))::float
    / NULLIF(COUNT(*) FILTER (WHERE is_title_fight = false), 0) AS non_title_finish_rate
FROM fights f
JOIN events e ON e.id = f.event_id
WHERE e.is_upcoming = false
  AND f.method IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5) Finish rate by division
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_finish_rate_by_division CASCADE;
CREATE VIEW v_finish_rate_by_division AS
SELECT
  weight_class AS division,
  COUNT(*) AS fights,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE method NOT LIKE 'Decision%' 
                              AND method NOT IN ('Overturned', 'Other'))
    / NULLIF(COUNT(*), 0), 1
  ) AS finish_rate_pct,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE method LIKE '%KO%' OR method LIKE '%TKO%')
    / NULLIF(COUNT(*), 0), 1
  ) AS ko_rate_pct,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE method = 'Submission')
    / NULLIF(COUNT(*), 0), 1
  ) AS sub_rate_pct
FROM fights f
JOIN events e ON e.id = f.event_id
WHERE e.is_upcoming = false
  AND weight_class IN (
    'Flyweight','Bantamweight','Featherweight','Lightweight',
    'Welterweight','Middleweight','Light Heavyweight','Heavyweight','Strawweight'
  )
GROUP BY weight_class
HAVING COUNT(*) >= 50  -- exclude small samples
ORDER BY finish_rate_pct DESC;

-- ---------------------------------------------------------------------------
-- 6) Main event vs prelim finish rate
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_main_event_finish_rate CASCADE;
CREATE VIEW v_main_event_finish_rate AS
SELECT
  COUNT(*) FILTER (WHERE is_main_event = true) AS main_events,
  ROUND(100.0 * 
    COUNT(*) FILTER (WHERE is_main_event = true 
                     AND method NOT LIKE 'Decision%'
                     AND method NOT IN ('Overturned', 'Other'))
    / NULLIF(COUNT(*) FILTER (WHERE is_main_event = true), 0)
  , 1) AS main_event_finish_rate_pct,
  COUNT(*) FILTER (WHERE is_main_event = false) AS non_main_events,
  ROUND(100.0 *
    COUNT(*) FILTER (WHERE is_main_event = false
                     AND method NOT LIKE 'Decision%'
                     AND method NOT IN ('Overturned', 'Other'))
    / NULLIF(COUNT(*) FILTER (WHERE is_main_event = false), 0)
  , 1) AS non_main_finish_rate_pct
FROM fights f
JOIN events e ON e.id = f.event_id
WHERE e.is_upcoming = false
  AND f.method IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Grant SELECT to the anon role on all views
-- ---------------------------------------------------------------------------
GRANT SELECT ON v_younger_fighter_winrate TO anon;
GRANT SELECT ON v_southpaw_vs_orthodox TO anon;
GRANT SELECT ON v_reach_advantage_winrate TO anon;
GRANT SELECT ON v_title_finish_rate TO anon;
GRANT SELECT ON v_finish_rate_by_division TO anon;
GRANT SELECT ON v_main_event_finish_rate TO anon;
