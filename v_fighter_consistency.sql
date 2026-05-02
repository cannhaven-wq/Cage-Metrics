-- =============================================================================
-- v_fighter_consistency  —  v5: per-weight-class with CAREER fallback
-- =============================================================================
-- Same scoring logic as v4 (R3+ to R1 ratio, volume-weighted, sample-aware
-- cap, wrestler-only takedowns), but now grouped by (fighter, weight_class)
-- with an additional 'CAREER' row per fighter that aggregates everything.
--
-- Frontend usage pattern:
--   1. For each upcoming fight, look up cardio for both fighters at the
--      fight's weight_class.
--   2. If a fighter has no row at that weight_class (or row is too sparse),
--      fall back to the CAREER row.
--   3. If neither exists, render "no data" callout.
--
-- The 'recent 5' window is now per-weight-class — Pereira's last 5 LHW
-- fights inform his LHW score, his last 5 MW fights inform his MW score,
-- and the union of his last 5 fights overall informs his CAREER score.
-- =============================================================================

DROP VIEW IF EXISTS v_fighter_consistency;

CREATE OR REPLACE VIEW v_fighter_consistency AS
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
    fr.a_td_attempted::float         AS td_attempted,
    5.0 AS round_minutes,
    -- Normalize weight class. Anything outside the standard divisions becomes 'Other'.
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
    fr.b_td_attempted::float,
    5.0,
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

-- Per-weight-class ranking (last 5 fights AT this weight class)
ranked_per_wc AS (
  SELECT
    fight_id, fighter_id, weight_class, event_date,
    MAX(round_number) AS rounds_completed,
    ROW_NUMBER() OVER (PARTITION BY fighter_id, weight_class ORDER BY MAX(event_date) DESC, fight_id DESC) AS recency_rank
  FROM fighter_round
  GROUP BY fight_id, fighter_id, weight_class, event_date
),

-- Career ranking (last 5 fights regardless of weight class)
ranked_career AS (
  SELECT
    fight_id, fighter_id, event_date,
    ROW_NUMBER() OVER (PARTITION BY fighter_id ORDER BY MAX(event_date) DESC, fight_id DESC) AS recency_rank
  FROM fighter_round
  GROUP BY fight_id, fighter_id, event_date
),

-- Pull the rows for the per-weight-class window
recent_per_wc AS (
  SELECT fr.*
  FROM fighter_round fr
  JOIN ranked_per_wc r
    ON r.fight_id = fr.fight_id
   AND r.fighter_id = fr.fighter_id
   AND r.weight_class = fr.weight_class
  WHERE r.recency_rank <= 5
),

-- Pull the rows for the career window
recent_career AS (
  SELECT fr.*
  FROM fighter_round fr
  JOIN ranked_career r
    ON r.fight_id = fr.fight_id
   AND r.fighter_id = fr.fighter_id
  WHERE r.recency_rank <= 5
),

-- Aggregate window totals: per weight class
wc_totals AS (
  SELECT
    fighter_id, weight_class,
    SUM(CASE WHEN round_number = 1 THEN sig_attempted ELSE 0 END)   AS r1_sig_attempted,
    SUM(CASE WHEN round_number = 1 THEN sig_landed    ELSE 0 END)   AS r1_sig_landed,
    SUM(CASE WHEN round_number = 1 THEN total_attempted ELSE 0 END) AS r1_tot_attempted,
    SUM(CASE WHEN round_number = 1 THEN td_attempted ELSE 0 END)    AS r1_td,
    SUM(CASE WHEN round_number = 1 THEN round_minutes ELSE 0 END)   AS r1_minutes,
    SUM(CASE WHEN round_number >= 3 THEN sig_attempted ELSE 0 END)   AS r3p_sig_attempted,
    SUM(CASE WHEN round_number >= 3 THEN sig_landed    ELSE 0 END)   AS r3p_sig_landed,
    SUM(CASE WHEN round_number >= 3 THEN total_attempted ELSE 0 END) AS r3p_tot_attempted,
    SUM(CASE WHEN round_number >= 3 THEN td_attempted ELSE 0 END)    AS r3p_td,
    SUM(CASE WHEN round_number >= 3 THEN round_minutes ELSE 0 END)   AS r3p_minutes,
    COUNT(DISTINCT fight_id) AS fight_count
  FROM recent_per_wc
  GROUP BY fighter_id, weight_class
),

-- Career totals (across all weight classes)
career_totals AS (
  SELECT
    fighter_id,
    'CAREER' AS weight_class,
    SUM(CASE WHEN round_number = 1 THEN sig_attempted ELSE 0 END)   AS r1_sig_attempted,
    SUM(CASE WHEN round_number = 1 THEN sig_landed    ELSE 0 END)   AS r1_sig_landed,
    SUM(CASE WHEN round_number = 1 THEN total_attempted ELSE 0 END) AS r1_tot_attempted,
    SUM(CASE WHEN round_number = 1 THEN td_attempted ELSE 0 END)    AS r1_td,
    SUM(CASE WHEN round_number = 1 THEN round_minutes ELSE 0 END)   AS r1_minutes,
    SUM(CASE WHEN round_number >= 3 THEN sig_attempted ELSE 0 END)   AS r3p_sig_attempted,
    SUM(CASE WHEN round_number >= 3 THEN sig_landed    ELSE 0 END)   AS r3p_sig_landed,
    SUM(CASE WHEN round_number >= 3 THEN total_attempted ELSE 0 END) AS r3p_tot_attempted,
    SUM(CASE WHEN round_number >= 3 THEN td_attempted ELSE 0 END)    AS r3p_td,
    SUM(CASE WHEN round_number >= 3 THEN round_minutes ELSE 0 END)   AS r3p_minutes,
    COUNT(DISTINCT fight_id) AS fight_count
  FROM recent_career
  GROUP BY fighter_id
),

unioned_totals AS (
  SELECT * FROM wc_totals
  UNION ALL
  SELECT * FROM career_totals
),

-- Convert to per-minute / per-round rates
fighter_rates AS (
  SELECT
    fighter_id, weight_class, fight_count, r1_minutes, r3p_minutes,
    CASE WHEN r1_minutes > 0 THEN r1_sig_attempted / r1_minutes ELSE NULL END   AS r1_sig_apm,
    CASE WHEN r1_minutes > 0 THEN r1_sig_landed    / r1_minutes ELSE NULL END   AS r1_sig_lpm,
    CASE WHEN r1_minutes > 0 THEN r1_tot_attempted / r1_minutes ELSE NULL END   AS r1_tot_apm,
    CASE WHEN r1_minutes > 0 THEN r1_td / (r1_minutes / 5.0) ELSE NULL END      AS r1_td_per_round,
    CASE WHEN r3p_minutes > 0 THEN r3p_sig_attempted / r3p_minutes ELSE NULL END AS r3p_sig_apm,
    CASE WHEN r3p_minutes > 0 THEN r3p_sig_landed    / r3p_minutes ELSE NULL END AS r3p_sig_lpm,
    CASE WHEN r3p_minutes > 0 THEN r3p_tot_attempted / r3p_minutes ELSE NULL END AS r3p_tot_apm,
    CASE WHEN r3p_minutes > 0 THEN r3p_td / (r3p_minutes / 5.0) ELSE NULL END    AS r3p_td_per_round,
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
    (r1_sig_apm    >= 1.5) AS sig_apm_active,
    (r1_sig_lpm    >= 1.0) AS sig_lpm_active,
    (r1_tot_apm    >= 2.0) AS tot_apm_active,
    (r1_td_per_round >= 1.5) AS td_active,
    CASE WHEN r1_sig_apm >= 1.5 AND r1_sig_apm > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_sig_apm / r1_sig_apm) ELSE NULL END AS sig_apm_ratio,
    CASE WHEN r1_sig_lpm >= 1.0 AND r1_sig_lpm > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_sig_lpm / r1_sig_lpm) ELSE NULL END AS sig_lpm_ratio,
    CASE WHEN r1_tot_apm >= 2.0 AND r1_tot_apm > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_tot_apm / r1_tot_apm) ELSE NULL END AS tot_apm_ratio,
    CASE WHEN r1_td_per_round >= 1.5 AND r1_td_per_round > 0 AND r3p_minutes >= 10
         THEN LEAST(dim_cap, r3p_td_per_round / r1_td_per_round) ELSE NULL END AS td_ratio,
    r1_sig_apm, r1_sig_lpm, r1_tot_apm, r1_td_per_round
  FROM fighter_rates
),

scored AS (
  SELECT
    fr.*,
    100.0 * (
      COALESCE(fr.sig_apm_ratio, 0)  * COALESCE(fr.r1_sig_apm, 0) +
      COALESCE(fr.sig_lpm_ratio, 0)  * COALESCE(fr.r1_sig_lpm, 0) +
      COALESCE(fr.tot_apm_ratio, 0)  * COALESCE(fr.r1_tot_apm, 0) +
      COALESCE(fr.td_ratio, 0)       * COALESCE(fr.r1_td_per_round / 5.0, 0)
    ) / NULLIF(
      (CASE WHEN fr.sig_apm_ratio IS NOT NULL THEN fr.r1_sig_apm   ELSE 0 END +
       CASE WHEN fr.sig_lpm_ratio IS NOT NULL THEN fr.r1_sig_lpm   ELSE 0 END +
       CASE WHEN fr.tot_apm_ratio IS NOT NULL THEN fr.r1_tot_apm   ELSE 0 END +
       CASE WHEN fr.td_ratio      IS NOT NULL THEN fr.r1_td_per_round / 5.0 ELSE 0 END), 0)
    AS raw_score
  FROM fighter_ratios fr
)

SELECT
  s.fighter_id,
  s.weight_class,
  s.fight_count             AS recent_fights,
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
  ROUND((100 * s.td_ratio)::numeric, 1)      AS td_ratio_pct,
  s.sig_apm_active, s.sig_lpm_active, s.tot_apm_active, s.td_active
FROM scored s
WHERE s.r1_minutes > 0
  AND s.r3p_minutes > 0
  AND (s.sig_apm_active OR s.sig_lpm_active OR s.tot_apm_active OR s.td_active);
