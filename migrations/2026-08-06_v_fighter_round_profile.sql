-- =============================================================================
-- v_fighter_round_profile  —  model-facing per-round output profile
-- =============================================================================
-- Grain: one row per (fighter_id, weight_class) PLUS one 'CAREER' row per
-- fighter that aggregates every weight class. Mirrors the per-WC + CAREER shape
-- of v_fighter_consistency and v_fighter_cardio_curve so consumers can look up
-- a fighter at the fight's weight class and fall back to CAREER.
--
-- ADDITIVE: this view does NOT touch v_fighter_consistency, v_fighter_style,
-- v_fighter_cardio_curve, edges.js, or any frontend. It is a new surface.
--
-- WINDOW: every COMPLETED fight (is_upcoming = false) on an event dated
-- 2010-01-01 or later. Career-wide, NOT the last-5 window v_fighter_consistency
-- uses — a per-round output profile wants the fighter's whole body of evidence.
-- Rounds 1-5 only. Each round is treated as a flat 5.0 minutes, the same
-- convention every other CFL cardio view uses (fights that end mid-round are
-- not pro-rated; keeping the convention keeps this view comparable to the rest
-- of the site).
--
-- SAMPLE FLOOR: a row is emitted only when the group has >= 10 R1 minutes
-- (i.e. the fighter contested R1 in at least 2 qualifying fights in that group).
-- Same 10-R1-minute floor as v_fighter_style.
--
-- ---------------------------------------------------------------------------
-- COLUMNS
-- ---------------------------------------------------------------------------
--  r1_sig_rate  / r2_sig_rate  / r3p_sig_rate   accuracy-weighted sig output/min
--  r1_grapp_rate/ r2_grapp_rate/ r3p_grapp_rate grappling output per minute
--  sig_decay_slope  / grapp_decay_slope         linear (OLS) slope R1->R2->R3+
--  rounds_sampled / minutes_sampled             confidence inputs
--
-- STRIKING-EFFECTIVENESS REWRITE (accuracy-weighted sig rate)
-- ---------------------------------------------------------------------------
-- Raw "landed per minute" rewards a fighter who throws a huge volume of missed
-- strikes as if they were elite output. We fix that by scaling the volume rate
-- by the group's landing accuracy, so a busy-but-inaccurate striker is
-- discounted toward their genuinely-landed workload:
--
--     volume_rate = sig_landed / minutes                (strikes landed / min)
--     accuracy    = sig_landed / sig_attempted          (share of attempts that land, 0..1)
--     sig_rate    = volume_rate * accuracy
--                 = sig_landed^2 / (minutes * sig_attempted)   <-- exact closed form
--
-- Guard: NULL when sig_attempted = 0 (no striking base -> no striking profile).
-- Grappling rate is NOT accuracy-weighted (per spec) — it is the canonical CFL
-- blend, raw per minute:
--
--     grapp_rate  = (td_landed * 60 + ctrl_seconds) / minutes
--
-- DECAY SLOPES (dim_cap-guarded, v6 convention)
-- ---------------------------------------------------------------------------
-- A linear least-squares slope over the three per-round rates at x = (1, 2, 3):
--
--     slope = Σ(xi - x̄)·yi / Σ(xi - x̄)²   with x̄ = 2, Σ(xi - x̄)² = 2
--           = (-1·y1 + 0·y2 + 1·y3) / 2
--           = (y3 - y1) / 2
--
-- With three evenly-spaced points the OLS slope depends only on the R1 and R3+
-- endpoints; R2 informs the fit's curvature (residual) but has zero weight on
-- the slope itself. Units are "rate change per round-step": negative = fades in
-- later rounds, positive = climbs.
--
-- The EMITTED per-round rate columns are uncapped (true output). The SLOPES
-- apply the v_fighter_consistency v6 `dim_cap` convention to the R3+/R1 RATIO
-- so a sparse, fluky deep-round sample cannot manufacture a steep phantom climb:
--
--     dim_cap = 1.50 if r3p_minutes >= 60
--               1.40 if r3p_minutes >= 30
--               1.30 if r3p_minutes >= 15
--               1.15 otherwise
--
-- The R3+ endpoint feeding the slope is capped at dim_cap × R1 rate — but only
-- when the R1 base clears a small activity floor (SIG_FLOOR = 0.25 acc-wtd
-- strikes/min, GRAPP_FLOOR = 2.0 grapp-units/min). Below the floor there is no
-- meaningful ratio to cap (near-zero denominator), so the raw R3+ rate is used,
-- exactly as v_fighter_cardio_curve's R1_FLOOR guards its pct denominator. The
-- cap only ever binds on the UP side (a real fader's downside is bounded in
-- [0,1] and passes through untouched).
--
-- RLS: public-surface adjacent — SELECT granted to BOTH anon AND authenticated
-- (the standard CFL public-view rule; an anon-only grant makes signed-in users
-- silently receive empty 200s).
-- =============================================================================

DROP VIEW IF EXISTS v_fighter_round_profile;

CREATE VIEW v_fighter_round_profile AS
WITH per_corner AS (
  -- Corner A: this fighter's own output in each round of each completed fight.
  SELECT
    f.fighter_a_id AS fighter_id,
    fr.fight_id,
    fr.round_number,
    fr.a_sig_str_landed::float                                AS sig_landed,
    fr.a_sig_str_attempted::float                             AS sig_attempted,
    (fr.a_td_landed::float * 60.0 + fr.a_ctrl_seconds::float) AS grapp_output,
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
    AND e.event_date >= DATE '2010-01-01'
    AND fr.round_number BETWEEN 1 AND 5

  UNION ALL

  -- Corner B.
  SELECT
    f.fighter_b_id AS fighter_id,
    fr.fight_id,
    fr.round_number,
    fr.b_sig_str_landed::float,
    fr.b_sig_str_attempted::float,
    (fr.b_td_landed::float * 60.0 + fr.b_ctrl_seconds::float),
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
    AND e.event_date >= DATE '2010-01-01'
    AND fr.round_number BETWEEN 1 AND 5
),

-- Label every round-row twice: once under its real weight class, once as CAREER.
labeled AS (
  SELECT fighter_id, weight_class,   round_number, sig_landed, sig_attempted, grapp_output FROM per_corner
  UNION ALL
  SELECT fighter_id, 'CAREER'::text, round_number, sig_landed, sig_attempted, grapp_output FROM per_corner
),

-- Aggregate to R1 / R2 / R3+ buckets per (fighter, weight_class).
grouped AS (
  SELECT
    fighter_id,
    weight_class,
    -- Round 1
    SUM(CASE WHEN round_number = 1 THEN sig_landed    ELSE 0 END) AS r1_sig_landed,
    SUM(CASE WHEN round_number = 1 THEN sig_attempted ELSE 0 END) AS r1_sig_attempted,
    SUM(CASE WHEN round_number = 1 THEN grapp_output  ELSE 0 END) AS r1_grapp,
    SUM(CASE WHEN round_number = 1 THEN 5.0           ELSE 0 END) AS r1_minutes,
    -- Round 2
    SUM(CASE WHEN round_number = 2 THEN sig_landed    ELSE 0 END) AS r2_sig_landed,
    SUM(CASE WHEN round_number = 2 THEN sig_attempted ELSE 0 END) AS r2_sig_attempted,
    SUM(CASE WHEN round_number = 2 THEN grapp_output  ELSE 0 END) AS r2_grapp,
    SUM(CASE WHEN round_number = 2 THEN 5.0           ELSE 0 END) AS r2_minutes,
    -- Rounds 3+ (3, 4, 5 pooled)
    SUM(CASE WHEN round_number >= 3 THEN sig_landed    ELSE 0 END) AS r3p_sig_landed,
    SUM(CASE WHEN round_number >= 3 THEN sig_attempted ELSE 0 END) AS r3p_sig_attempted,
    SUM(CASE WHEN round_number >= 3 THEN grapp_output  ELSE 0 END) AS r3p_grapp,
    SUM(CASE WHEN round_number >= 3 THEN 5.0           ELSE 0 END) AS r3p_minutes,
    COUNT(*)                                                       AS rounds_sampled
  FROM labeled
  GROUP BY fighter_id, weight_class
),

-- Per-round rates. Sig rates are accuracy-weighted (see header); grapp rates
-- are the raw canonical blend per minute.
rates AS (
  SELECT
    fighter_id,
    weight_class,
    rounds_sampled,
    (r1_minutes + r2_minutes + r3p_minutes)                     AS minutes_sampled,
    r1_minutes,
    r3p_minutes,
    -- accuracy-weighted sig output/min = landed^2 / (minutes * attempted)
    CASE WHEN r1_minutes  > 0 AND r1_sig_attempted  > 0
         THEN (r1_sig_landed  * r1_sig_landed)  / (r1_minutes  * r1_sig_attempted)  END AS r1_sig_rate,
    CASE WHEN r2_minutes  > 0 AND r2_sig_attempted  > 0
         THEN (r2_sig_landed  * r2_sig_landed)  / (r2_minutes  * r2_sig_attempted)  END AS r2_sig_rate,
    CASE WHEN r3p_minutes > 0 AND r3p_sig_attempted > 0
         THEN (r3p_sig_landed * r3p_sig_landed) / (r3p_minutes * r3p_sig_attempted) END AS r3p_sig_rate,
    -- grapp output/min = (td_landed*60 + ctrl_seconds) / minutes  (raw)
    CASE WHEN r1_minutes  > 0 THEN r1_grapp  / r1_minutes  END AS r1_grapp_rate,
    CASE WHEN r2_minutes  > 0 THEN r2_grapp  / r2_minutes  END AS r2_grapp_rate,
    CASE WHEN r3p_minutes > 0 THEN r3p_grapp / r3p_minutes END AS r3p_grapp_rate,
    -- dim_cap keyed on deep-round sample size (v_fighter_consistency v6 convention)
    CASE
      WHEN r3p_minutes >= 60 THEN 1.5
      WHEN r3p_minutes >= 30 THEN 1.4
      WHEN r3p_minutes >= 15 THEN 1.3
      ELSE                        1.15
    END AS dim_cap
  FROM grouped
),

-- Cap the R3+ endpoint at dim_cap × R1 (upside only) before taking the slope,
-- guarded by an R1 activity floor so a near-zero base can't collapse the cap.
capped AS (
  SELECT
    r.*,
    CASE
      WHEN r3p_sig_rate IS NULL OR r1_sig_rate IS NULL THEN NULL
      WHEN r1_sig_rate >= 0.25 THEN LEAST(r3p_sig_rate, dim_cap * r1_sig_rate)
      ELSE r3p_sig_rate
    END AS r3p_sig_rate_capped,
    CASE
      WHEN r3p_grapp_rate IS NULL OR r1_grapp_rate IS NULL THEN NULL
      WHEN r1_grapp_rate >= 2.0 THEN LEAST(r3p_grapp_rate, dim_cap * r1_grapp_rate)
      ELSE r3p_grapp_rate
    END AS r3p_grapp_rate_capped
  FROM rates r
)

SELECT
  fighter_id,
  weight_class,
  ROUND(r1_sig_rate::numeric,   3) AS r1_sig_rate,
  ROUND(r2_sig_rate::numeric,   3) AS r2_sig_rate,
  ROUND(r3p_sig_rate::numeric,  3) AS r3p_sig_rate,
  ROUND(r1_grapp_rate::numeric,  3) AS r1_grapp_rate,
  ROUND(r2_grapp_rate::numeric,  3) AS r2_grapp_rate,
  ROUND(r3p_grapp_rate::numeric, 3) AS r3p_grapp_rate,
  -- OLS slope over x=(1,2,3); with symmetric spacing = (capped_R3+ − R1) / 2.
  ROUND(((r3p_sig_rate_capped  - r1_sig_rate)  / 2.0)::numeric, 4) AS sig_decay_slope,
  ROUND(((r3p_grapp_rate_capped - r1_grapp_rate) / 2.0)::numeric, 4) AS grapp_decay_slope,
  rounds_sampled,
  ROUND(minutes_sampled::numeric, 1) AS minutes_sampled
FROM capped
WHERE r1_minutes >= 10          -- minimum 10 R1 minutes (>= 2 qualifying fights in the group)
ORDER BY fighter_id, weight_class;

-- Public-surface adjacent: grant to BOTH roles (CFL public-view rule).
GRANT SELECT ON v_fighter_round_profile TO anon, authenticated;
