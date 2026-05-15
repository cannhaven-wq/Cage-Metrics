-- =============================================================================
-- v_fighter_finish_rate — per-fighter career outcome breakdown
-- =============================================================================
-- For every fighter with at least 3 graded UFC fights, the fraction of those
-- fights that ended in each outcome class. Used by distanceEdges.js to gauge
-- whether a fight is likely to go the distance — fighters with high career
-- decision rates tend to be in fights that go the distance.
--
-- The view aggregates across BOTH sides of every fight (fighter A and fighter
-- B count the fight's method the same way) because we're measuring "does this
-- fighter's fight tend to end in X?" not "does this fighter win by X?".
--
-- Outcomes are bucketed as:
--   - decision: method LIKE 'Decision%' (Unanimous, Split, Majority)
--   - ko_tko:   method contains 'KO' or 'TKO'
--   - submission: method = 'Submission'
--   - dq / doctor: less common; counted in total but not rate
--   - NC / Other / null: excluded from total (ungradeable)
--
-- Safe to re-run.
-- =============================================================================

DROP VIEW IF EXISTS v_fighter_finish_rate;

CREATE VIEW v_fighter_finish_rate AS
WITH both_sides AS (
  SELECT f.fighter_a_id AS fighter_id, f.method
  FROM fights f
  JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = false
    AND f.method IS NOT NULL
    AND f.fighter_a_id IS NOT NULL
  UNION ALL
  SELECT f.fighter_b_id, f.method
  FROM fights f
  JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = false
    AND f.method IS NOT NULL
    AND f.fighter_b_id IS NOT NULL
),
classified AS (
  SELECT
    fighter_id,
    CASE
      WHEN method LIKE 'Decision%'                  THEN 'decision'
      WHEN method LIKE '%KO%' OR method LIKE '%TKO%' THEN 'ko_tko'
      WHEN method = 'Submission'                    THEN 'submission'
      WHEN method = 'DQ'                            THEN 'dq'
      WHEN method = 'Doctor''s Stoppage'            THEN 'doctor'
      ELSE NULL
    END AS outcome
  FROM both_sides
)
SELECT
  fighter_id,
  COUNT(*) AS total_fights,
  ROUND((COUNT(*) FILTER (WHERE outcome = 'decision')::float   / NULLIF(COUNT(*), 0))::numeric, 3) AS decision_rate,
  ROUND((COUNT(*) FILTER (WHERE outcome = 'ko_tko')::float     / NULLIF(COUNT(*), 0))::numeric, 3) AS ko_tko_rate,
  ROUND((COUNT(*) FILTER (WHERE outcome = 'submission')::float / NULLIF(COUNT(*), 0))::numeric, 3) AS sub_rate
FROM classified
WHERE outcome IS NOT NULL
GROUP BY fighter_id
HAVING COUNT(*) >= 3;

-- Anon/authenticated SELECT — required for the frontend (anon) and signed-in
-- users (authenticated) both to read this view. See CLAUDE.md "RLS" notes.
GRANT SELECT ON v_fighter_finish_rate TO anon, authenticated;
