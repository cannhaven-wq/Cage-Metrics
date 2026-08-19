-- =============================================================================
-- v_fighter_finisher — how a fighter ends fights, and how they get ended
-- =============================================================================
-- Replaces the guesswork in v_fighter_finish_rate, which counted a fight's
-- method without asking WHO won it — so "knocks people out" and "gets knocked
-- out" produced the same number. Here the two are separated, because to anyone
-- reading a matchup they mean opposite things.
--
-- Per fighter (3+ decided UFC fights):
--   finish_rate     - share of their fights they ended by KO/TKO or submission
--   ko_rate/sub_rate- what kind of finisher they are
--   finished_rate   - share of their fights where THEY got stopped
--   avg_fight_min   - how long their fights actually last
--   threat_per_15   - finishes per 15 minutes of cage time (a full 3-round fight)
--   finish_style    - ko_artist / submission_hunter / mixed_finisher / grinder
--   durability      - granite / solid / vulnerable / fragile
--
-- Research note (Aug 2026): a combined threat+fragility score for the two
-- corners separates fights that end early (59%) from fights that go long (28%)
-- across 3,848 fights, and it holds inside every division — average 22-point
-- spread — so it is not just re-reading the weight class. It does NOT predict
-- who wins (49.6% on market-even fights, i.e. nothing). Use it for fight
-- length, never as a pick factor.
--
-- CAREER-TO-DATE, NOT POINT-IN-TIME. Safe for display, since describing a
-- fighter's record today is a fact, not a forecast. **Never backtest with this
-- view** — scoring a 2019 fight with a career total that includes 2019-2026
-- results is the hindsight bug that faked the old "record predicts 75.5%"
-- claim. Modeling needs the point-in-time build in cfl_engine.
--
-- Idempotent. Safe to re-run.
-- =============================================================================

DROP VIEW IF EXISTS v_fighter_finisher;

CREATE VIEW v_fighter_finisher AS
WITH decided AS (
  SELECT
    f.id,
    f.fighter_a_id,
    f.fighter_b_id,
    f.winner_id,
    f.method,
    -- true fight length in seconds: full rounds before the last, plus the clock
    -- in the round it ended. end_time is text like '4:42'.
    ((COALESCE(f.end_round, 1) - 1) * 300)
      + CASE
          WHEN f.end_time ~ '^[0-9]+:[0-9]{1,2}$'
            THEN split_part(f.end_time, ':', 1)::int * 60
               + split_part(f.end_time, ':', 2)::int
          ELSE 300
        END AS fight_seconds
  FROM fights f
  JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = false
    AND f.method IS NOT NULL
    AND f.winner_id IS NOT NULL
),
both_sides AS (
  SELECT id, fighter_a_id AS fighter_id, winner_id, method, fight_seconds FROM decided
  WHERE fighter_a_id IS NOT NULL
  UNION ALL
  SELECT id, fighter_b_id, winner_id, method, fight_seconds FROM decided
  WHERE fighter_b_id IS NOT NULL
),
classified AS (
  SELECT
    fighter_id,
    fight_seconds,
    (fighter_id = winner_id) AS won,
    CASE
      WHEN method ILIKE '%submission%'                  THEN 'sub'
      WHEN method ILIKE '%ko%' OR method ILIKE '%tko%'  THEN 'ko'
      WHEN method ILIKE 'decision%'                     THEN 'dec'
      ELSE NULL                                          -- DQ, NC: not a finish
    END AS kind
  FROM both_sides
),
agg AS (
  SELECT
    fighter_id,
    COUNT(*)                                                       AS total_fights,
    SUM(fight_seconds) / 60.0                                      AS total_minutes,
    COUNT(*) FILTER (WHERE won AND kind = 'ko')                    AS ko_wins,
    COUNT(*) FILTER (WHERE won AND kind = 'sub')                   AS sub_wins,
    COUNT(*) FILTER (WHERE won AND kind = 'dec')                   AS dec_wins,
    COUNT(*) FILTER (WHERE NOT won AND kind = 'ko')                AS ko_losses,
    COUNT(*) FILTER (WHERE NOT won AND kind = 'sub')               AS sub_losses,
    COUNT(*) FILTER (WHERE NOT won AND kind = 'dec')               AS dec_losses
  FROM classified
  WHERE kind IS NOT NULL
  GROUP BY fighter_id
  HAVING COUNT(*) >= 3
)
SELECT
  fighter_id,
  total_fights,
  ko_wins, sub_wins, dec_wins,
  ko_losses, sub_losses, dec_losses,
  (ko_wins + sub_wins)                                             AS finishes,
  (ko_losses + sub_losses)                                         AS times_finished,
  ROUND(((ko_wins + sub_wins)::numeric / total_fights), 3)         AS finish_rate,
  ROUND((ko_wins::numeric  / total_fights), 3)                     AS ko_rate,
  ROUND((sub_wins::numeric / total_fights), 3)                     AS sub_rate,
  ROUND(((ko_losses + sub_losses)::numeric / total_fights), 3)     AS finished_rate,
  ROUND((total_minutes / total_fights)::numeric, 1)                AS avg_fight_min,
  ROUND(((ko_wins + sub_wins)::numeric
         / NULLIF(total_minutes / 15.0, 0)), 3)                    AS threat_per_15,
  ROUND(((ko_losses + sub_losses)::numeric
         / NULLIF(total_minutes / 15.0, 0)), 3)                    AS fragility_per_15,
  -- "Artist" language is gated on actually finishing a lot. A fighter who wins
  -- 28% by KO and the rest on the cards is not a KO artist, he's a decision
  -- fighter with a punch — the middle bucket exists to say exactly that.
  CASE
    WHEN (ko_wins + sub_wins)::numeric / total_fights < 0.25 THEN 'grinder'
    WHEN (ko_wins + sub_wins)::numeric / total_fights < 0.40 THEN 'occasional_finisher'
    WHEN ko_wins  > 2 * sub_wins                             THEN 'ko_artist'
    WHEN sub_wins > 2 * ko_wins                              THEN 'submission_hunter'
    ELSE                                                          'mixed_finisher'
  END                                                              AS finish_style,
  CASE
    WHEN (ko_losses + sub_losses) = 0 AND total_fights >= 5        THEN 'granite'
    WHEN (ko_losses + sub_losses)::numeric / total_fights < 0.15   THEN 'solid'
    WHEN (ko_losses + sub_losses)::numeric / total_fights < 0.35   THEN 'vulnerable'
    ELSE                                                                'fragile'
  END                                                              AS durability
FROM agg;

-- Frontend reads this as anon and as a signed-in user. Both roles need SELECT
-- or signed-in visitors silently get zero rows. See CLAUDE.md "RLS" notes.
GRANT SELECT ON v_fighter_finisher TO anon, authenticated;
