-- =============================================================================
-- v_fighter_consistency — v7: real round lengths
-- =============================================================================
-- WHAT CHANGED FROM v6 (Aug 2026): v4 through v6 all hardcoded `5.0 AS
-- round_minutes` — every round was treated as a full five minutes, whether it
-- lasted five minutes or forty seconds. That single line quietly inverted the
-- metric for finishers. A fighter who stops someone at 0:45 of round three had
-- his handful of strikes divided by five minutes and graded out as though he
-- had gassed, while a fighter who coasted through three full rounds scored
-- well. The metric was rewarding the wrong thing.
--
-- v7 uses the real clock. `fights.end_round` and `fights.end_time` were in the
-- database the whole time; a round is five minutes unless it is the round the
-- fight ended in, in which case it is however long it actually lasted.
--
-- Rounds under one minute are dropped entirely. A 40-second round says nothing
-- about whether a fighter can hold a pace — for the loser it is usually the
-- finishing sequence, and for the winner it is a flurry. Including them would
-- swing the score on the noisiest data in the fight.
--
-- SAME-FIGHT COMPARISON (also new in v7): only fights that actually reached
-- round three count, on both sides of the ratio. Previously round-one pace was
-- averaged over every fight a man ever had — including the ones he blew out in
-- ninety seconds — while his late-round pace could only come from the fights
-- that went long. That compared his best explosive nights against his grind-it-
-- out nights and called the difference "cardio". Now both halves of the ratio
-- are drawn from the same fights, so the number answers the question it claims
-- to: when this fighter got to deep water, did he hold the pace he set early?
--
-- EVERY OUTPUT COLUMN, TIER CUT AND THRESHOLD IS UNCHANGED from v6, on purpose:
-- index.html, card-lab.html, cardio.html and fight-insights.js all read this
-- view, and a rename here silently breaks loadFights (see CLAUDE.md). Only the
-- arithmetic behind the numbers is corrected.
--
-- Scoring (unchanged): weighted ratio of rounds-3+ output to round-1 output,
-- across three striking dimensions plus a grappling dimension for grapplers
-- only, each capped by a sample-size-aware ceiling. 100 = holds pace exactly.
--
-- Known limitation, still true: this is a career-recency metric over the last 5
-- fights, so it describes a fighter today. It is NOT point-in-time and must
-- never be used to score historical fights in a backtest — doing so is how the
-- old "cardio picks winners 66.7% of the time" claim came about. That number
-- does not survive an honest test; cardio predicts fight LENGTH, not winners.
--
-- Safe to re-run.
-- =============================================================================

DROP VIEW IF EXISTS v_fighter_consistency;

CREATE VIEW v_fighter_consistency AS
WITH
fighter_round AS (
  SELECT
    fr.fight_id,
    f.fighter_a_id AS fighter_id,
    e.event_date,
    fr.round_number,
    fr.a_sig_str_attempted::float    AS sig_attempted,
    fr.a_sig_str_landed::float       AS sig_landed,
    fr.a_total_str_attempted::float  AS total_attempted,
    fr.a_td_landed::float            AS td_landed,
    fr.a_ctrl_seconds::float         AS ctrl_seconds,
    -- Real length of THIS round. Full five minutes unless the fight ended in
    -- it, then the clock at the stoppage.
    CASE
      WHEN f.end_round IS NULL                THEN 5.0
      WHEN fr.round_number < f.end_round      THEN 5.0
      WHEN fr.round_number = f.end_round
           AND f.end_time ~ '^[0-9]+:[0-9]{1,2}$'
        THEN split_part(f.end_time, ':', 1)::float
           + split_part(f.end_time, ':', 2)::float / 60.0
      ELSE 5.0
    END AS round_minutes,
    CASE
      WHEN f.weight_class IN (
        'Strawweight','Flyweight','Bantamweight','Featherweight','Lightweight',
        'Welterweight','Middleweight','Light Heavyweight','Heavyweight',
        'Women''s Strawweight','Women''s Flyweight','Women''s Bantamweight',
        'Women''s Featherweight'
      ) THEN f.weight_class
      ELSE 'Other'
    END AS weight_class
  FROM fight_rounds fr
  JOIN fights f ON f.id = fr.fight_id
  JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = false
  UNION ALL
  SELECT
    fr.fight_id,
    f.fighter_b_id AS fighter_id,
    e.event_date,
    fr.round_number,
    fr.b_sig_str_attempted::float,
    fr.b_sig_str_landed::float,
    fr.b_total_str_attempted::float,
    fr.b_td_landed::float,
    fr.b_ctrl_seconds::float,
    CASE
      WHEN f.end_round IS NULL                THEN 5.0
      WHEN fr.round_number < f.end_round      THEN 5.0
      WHEN fr.round_number = f.end_round
           AND f.end_time ~ '^[0-9]+:[0-9]{1,2}$'
        THEN split_part(f.end_time, ':', 1)::float
           + split_part(f.end_time, ':', 2)::float / 60.0
      ELSE 5.0
    END,
    CASE
      WHEN f.weight_class IN (
        'Strawweight','Flyweight','Bantamweight','Featherweight','Lightweight',
        'Welterweight','Middleweight','Light Heavyweight','Heavyweight',
        'Women''s Strawweight','Women''s Flyweight','Women''s Bantamweight',
        'Women''s Featherweight'
      ) THEN f.weight_class
      ELSE 'Other'
    END
  FROM fight_rounds fr
  JOIN fights f ON f.id = fr.fight_id
  JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = false
),

-- Drop rounds too short to say anything about pace (see header).
long_enough AS (
  SELECT * FROM fighter_round WHERE round_minutes >= 1.0
),

-- Keep only (fighter, fight) pairs that actually reached round three, so the
-- early and late halves of every ratio come from the same fights.
deep_fights AS (
  SELECT fight_id, fighter_id
  FROM long_enough
  GROUP BY fight_id, fighter_id
  HAVING MAX(round_number) >= 3
),

usable_round AS (
  SELECT le.*
  FROM long_enough le
  JOIN deep_fights df
    ON df.fight_id = le.fight_id
   AND df.fighter_id = le.fighter_id
),

ranked_per_wc AS (
  SELECT
    fight_id, fighter_id, weight_class, event_date,
    ROW_NUMBER() OVER (PARTITION BY fighter_id, weight_class
                       ORDER BY MAX(event_date) DESC, fight_id DESC) AS recency_rank
  FROM usable_round
  GROUP BY fight_id, fighter_id, weight_class, event_date
),

ranked_career AS (
  SELECT
    fight_id, fighter_id, event_date,
    ROW_NUMBER() OVER (PARTITION BY fighter_id
                       ORDER BY MAX(event_date) DESC, fight_id DESC) AS recency_rank
  FROM usable_round
  GROUP BY fight_id, fighter_id, event_date
),

recent_per_wc AS (
  SELECT ur.*
  FROM usable_round ur
  JOIN ranked_per_wc r
    ON r.fight_id = ur.fight_id
   AND r.fighter_id = ur.fighter_id
   AND r.weight_class = ur.weight_class
  WHERE r.recency_rank <= 5
),

recent_career AS (
  SELECT ur.*
  FROM usable_round ur
  JOIN ranked_career r
    ON r.fight_id = ur.fight_id
   AND r.fighter_id = ur.fighter_id
  WHERE r.recency_rank <= 5
),

wc_totals AS (
  SELECT
    fighter_id, weight_class,
    SUM(CASE WHEN round_number = 1 THEN sig_attempted   ELSE 0 END) AS r1_sig_attempted,
    SUM(CASE WHEN round_number = 1 THEN sig_landed      ELSE 0 END) AS r1_sig_landed,
    SUM(CASE WHEN round_number = 1 THEN total_attempted ELSE 0 END) AS r1_tot_attempted,
    SUM(CASE WHEN round_number = 1 THEN td_landed       ELSE 0 END) AS r1_td_landed,
    SUM(CASE WHEN round_number = 1 THEN ctrl_seconds    ELSE 0 END) AS r1_ctrl_seconds,
    SUM(CASE WHEN round_number = 1 THEN round_minutes   ELSE 0 END) AS r1_minutes,
    SUM(CASE WHEN round_number >= 3 THEN sig_attempted   ELSE 0 END) AS r3p_sig_attempted,
    SUM(CASE WHEN round_number >= 3 THEN sig_landed      ELSE 0 END) AS r3p_sig_landed,
    SUM(CASE WHEN round_number >= 3 THEN total_attempted ELSE 0 END) AS r3p_tot_attempted,
    SUM(CASE WHEN round_number >= 3 THEN td_landed       ELSE 0 END) AS r3p_td_landed,
    SUM(CASE WHEN round_number >= 3 THEN ctrl_seconds    ELSE 0 END) AS r3p_ctrl_seconds,
    SUM(CASE WHEN round_number >= 3 THEN round_minutes   ELSE 0 END) AS r3p_minutes,
    COUNT(DISTINCT fight_id) AS fight_count
  FROM recent_per_wc
  GROUP BY fighter_id, weight_class
),

career_totals AS (
  SELECT
    fighter_id,
    'CAREER' AS weight_class,
    SUM(CASE WHEN round_number = 1 THEN sig_attempted   ELSE 0 END),
    SUM(CASE WHEN round_number = 1 THEN sig_landed      ELSE 0 END),
    SUM(CASE WHEN round_number = 1 THEN total_attempted ELSE 0 END),
    SUM(CASE WHEN round_number = 1 THEN td_landed       ELSE 0 END),
    SUM(CASE WHEN round_number = 1 THEN ctrl_seconds    ELSE 0 END),
    SUM(CASE WHEN round_number = 1 THEN round_minutes   ELSE 0 END),
    SUM(CASE WHEN round_number >= 3 THEN sig_attempted   ELSE 0 END),
    SUM(CASE WHEN round_number >= 3 THEN sig_landed      ELSE 0 END),
    SUM(CASE WHEN round_number >= 3 THEN total_attempted ELSE 0 END),
    SUM(CASE WHEN round_number >= 3 THEN td_landed       ELSE 0 END),
    SUM(CASE WHEN round_number >= 3 THEN ctrl_seconds    ELSE 0 END),
    SUM(CASE WHEN round_number >= 3 THEN round_minutes   ELSE 0 END),
    COUNT(DISTINCT fight_id)
  FROM recent_career
  GROUP BY fighter_id
),

unioned_totals AS (
  SELECT * FROM wc_totals
  UNION ALL
  SELECT * FROM career_totals
),

fighter_rates AS (
  SELECT
    fighter_id, weight_class, fight_count, r1_minutes, r3p_minutes,
    CASE WHEN r1_minutes > 0 THEN r1_sig_attempted   / r1_minutes END AS r1_sig_apm,
    CASE WHEN r1_minutes > 0 THEN r1_sig_landed      / r1_minutes END AS r1_sig_lpm,
    CASE WHEN r1_minutes > 0 THEN r1_tot_attempted   / r1_minutes END AS r1_tot_apm,
    CASE WHEN r1_minutes > 0 THEN r1_td_landed    / (r1_minutes / 5.0) END AS r1_td_landed_per_round,
    CASE WHEN r1_minutes > 0 THEN r1_ctrl_seconds / (r1_minutes / 5.0) END AS r1_ctrl_per_round,
    CASE WHEN r1_minutes > 0
         THEN (r1_td_landed * 60.0 + r1_ctrl_seconds) / (r1_minutes / 5.0) END AS r1_grapp_output_per_round,
    CASE WHEN r3p_minutes > 0 THEN r3p_sig_attempted / r3p_minutes END AS r3p_sig_apm,
    CASE WHEN r3p_minutes > 0 THEN r3p_sig_landed    / r3p_minutes END AS r3p_sig_lpm,
    CASE WHEN r3p_minutes > 0 THEN r3p_tot_attempted / r3p_minutes END AS r3p_tot_apm,
    CASE WHEN r3p_minutes > 0
         THEN (r3p_td_landed * 60.0 + r3p_ctrl_seconds) / (r3p_minutes / 5.0) END AS r3p_grapp_output_per_round,
    CASE
      WHEN r3p_minutes >= 60 THEN 1.5
      WHEN r3p_minutes >= 30 THEN 1.4
      WHEN r3p_minutes >= 15 THEN 1.3
      ELSE                        1.15
    END AS dim_cap
  FROM unioned_totals
),

fighter_ratios AS (
  SELECT
    fighter_id, weight_class, fight_count, r1_minutes, r3p_minutes, dim_cap,
    (r1_sig_apm >= 1.5) AS sig_apm_active,
    (r1_sig_lpm >= 1.0) AS sig_lpm_active,
    (r1_tot_apm >= 2.0) AS tot_apm_active,
    (r1_td_landed_per_round >= 0.5 OR r1_ctrl_per_round >= 45) AS grapp_active,
    CASE WHEN r1_sig_apm >= 1.5 AND r1_sig_apm > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_sig_apm / r1_sig_apm) END AS sig_apm_ratio,
    CASE WHEN r1_sig_lpm >= 1.0 AND r1_sig_lpm > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_sig_lpm / r1_sig_lpm) END AS sig_lpm_ratio,
    CASE WHEN r1_tot_apm >= 2.0 AND r1_tot_apm > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_tot_apm / r1_tot_apm) END AS tot_apm_ratio,
    CASE WHEN (r1_td_landed_per_round >= 0.5 OR r1_ctrl_per_round >= 45)
              AND r1_grapp_output_per_round > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_grapp_output_per_round / r1_grapp_output_per_round) END AS grapp_ratio,
    r1_sig_apm, r1_sig_lpm, r1_tot_apm,
    r1_td_landed_per_round, r1_ctrl_per_round, r1_grapp_output_per_round
  FROM fighter_rates
),

scored AS (
  SELECT
    fr.*,
    100.0 * (
      COALESCE(fr.sig_apm_ratio, 0) * COALESCE(fr.r1_sig_apm, 0) +
      COALESCE(fr.sig_lpm_ratio, 0) * COALESCE(fr.r1_sig_lpm, 0) +
      COALESCE(fr.tot_apm_ratio, 0) * COALESCE(fr.r1_tot_apm, 0) +
      COALESCE(fr.grapp_ratio, 0)   * COALESCE(fr.r1_grapp_output_per_round / 60.0, 0)
    ) / NULLIF(
      (CASE WHEN fr.sig_apm_ratio IS NOT NULL THEN fr.r1_sig_apm ELSE 0 END +
       CASE WHEN fr.sig_lpm_ratio IS NOT NULL THEN fr.r1_sig_lpm ELSE 0 END +
       CASE WHEN fr.tot_apm_ratio IS NOT NULL THEN fr.r1_tot_apm ELSE 0 END +
       CASE WHEN fr.grapp_ratio   IS NOT NULL THEN fr.r1_grapp_output_per_round / 60.0 ELSE 0 END), 0)
    AS raw_score
  FROM fighter_ratios fr
)

SELECT
  s.fighter_id,
  s.weight_class,
  s.fight_count                     AS recent_fights,
  ROUND(s.r1_minutes::numeric, 1)   AS r1_minutes,
  ROUND(s.r3p_minutes::numeric, 1)  AS r3p_minutes,
  ROUND(s.raw_score::numeric, 1)    AS consistency_score,
  CASE
    WHEN s.r1_minutes < 8 OR s.r3p_minutes < 5 THEN 'limited'
    WHEN s.r3p_minutes >= 15 THEN 'high'
    ELSE 'limited'
  END AS confidence_tier,
  CASE
    WHEN s.raw_score IS NULL THEN NULL
    WHEN s.raw_score >= 115 THEN 'tireless'
    WHEN s.raw_score >= 90  THEN 'steady'
    WHEN s.raw_score >= 70  THEN 'tapers'
    WHEN s.raw_score >= 50  THEN 'fades'
    ELSE                         'collapses'
  END AS cardio_tier,
  ROUND((100 * s.sig_apm_ratio)::numeric, 1) AS sig_apm_ratio_pct,
  ROUND((100 * s.sig_lpm_ratio)::numeric, 1) AS sig_lpm_ratio_pct,
  ROUND((100 * s.tot_apm_ratio)::numeric, 1) AS tot_apm_ratio_pct,
  ROUND((100 * s.grapp_ratio)::numeric, 1)   AS grapp_ratio_pct,
  ROUND(s.r1_td_landed_per_round::numeric, 2) AS r1_td_landed_per_round,
  ROUND(s.r1_ctrl_per_round::numeric, 1)      AS r1_ctrl_seconds_per_round,
  -- NEW in v7. The score is a RATIO, so it says whether a fighter held his own
  -- early pace — not whether that pace was worth holding. A famously passive
  -- fighter who is equally passive in round three scores "tireless". Exposing
  -- the round-one volume lets the front end say "holds pace, but a low one"
  -- instead of quietly flattering him.
  ROUND(s.r1_sig_apm::numeric, 1)             AS r1_sig_str_per_min,
  s.sig_apm_active, s.sig_lpm_active, s.tot_apm_active, s.grapp_active
FROM scored s
WHERE s.r1_minutes > 0
  AND s.r3p_minutes > 0
  AND (s.sig_apm_active OR s.sig_lpm_active OR s.tot_apm_active OR s.grapp_active);

GRANT SELECT ON v_fighter_consistency TO anon, authenticated;
