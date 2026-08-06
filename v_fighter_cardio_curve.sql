-- =============================================================================
-- v_fighter_cardio_curve  —  per-fighter, per-round expected output profile
-- =============================================================================
-- Foundation for a future live in-fight "fade tracker" (that live piece is OUT
-- of scope here — this is the historical profile it will compare against).
--
-- Grain: one row per (fighter_id, weight_class, round_number) plus a 'CAREER'
-- weight_class row per fighter, mirroring v_fighter_consistency's per-WC +
-- CAREER shape. Rounds 1-5 only. A round the fighter never reached simply has
-- no row (absent).
--
-- Per-round output uses CFL's canonical striking+grappling blend (same as the
-- style classifier and v_fighter_consistency), so it stays consistent with the
-- rest of the site:
--     strk_norm  = (avg sig_str_landed in that round)              / 16
--     grapp_norm = (avg (td_landed*60 + ctrl_seconds) that round)  / 90
--     raw_output = strk_norm + grapp_norm            <- source of truth
--     pct_of_r1  = raw_output / (that fighter+WC's R1 raw_output)   <- derived
--         RATIO, not 0-100: 1.000 = identical to round 1, 0.800 = 20% below R1.
--         Guarded: NULL when the R1 base is below R1_FLOOR (0.15) to avoid
--         dividing by a near-zero denominator (see note below).
--
-- WINDOW: CAREER-WIDE (every completed fight), NOT the last-5 window that
-- v_fighter_consistency uses. This is deliberate — a cardio profile wants the
-- fighter's whole body of deep-round evidence, not just recent form. As a
-- result these numbers will NOT match the existing cardio tier, and that is
-- expected.
--
-- CONFIDENCE is keyed to r3p_apps = the fighter's CAREER count of DISTINCT
-- fights that reached round 3+ (denormalized onto every row, incl. per-WC rows):
--     >= 7  -> 'high'
--     4-6   -> 'limited'
--     <  4  -> 'insufficient': NO curve. strk_norm/grapp_norm/raw_output/
--              pct_of_r1 are all NULL and descriptor =
--              'finisher_or_low_deep_round_sample'. These fighters finish early;
--              they get a finish-threat flag elsewhere, not a fabricated cardio
--              score. n_fights is still populated so consumers can see the
--              actual (shallow) sample.
--
-- R1_FLOOR (0.15) rationale: across the 972 fighters who qualify for a curve,
-- the 1st-percentile career R1 raw_output is ~0.69 and the minimum ~0.46, so a
-- 0.15 floor never nulls a legitimate fighter's pct — it only catches genuine
-- near-zero R1 anomalies at sparse per-WC slices.
--
-- Additive: does not touch v_fighter_consistency, v_fighter_style, edges.js,
-- fight-insights.js, or any frontend.
--
-- NOTE ON GRANTS: SELECT is granted to BOTH anon AND authenticated. An
-- anon-only grant makes signed-in users get empty 200s (the standard CFL
-- public-data rule).
-- =============================================================================

DROP VIEW IF EXISTS v_fighter_cardio_curve;

CREATE VIEW v_fighter_cardio_curve AS
WITH per_corner AS (
  -- Corner A: this fighter's own output in each round of each completed fight
  SELECT
    f.fighter_a_id AS fighter_id,
    fr.fight_id,
    fr.round_number,
    fr.a_sig_str_landed::float                                   AS sig_landed,
    (fr.a_td_landed::float * 60.0 + fr.a_ctrl_seconds::float)    AS grapp_output,
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
    AND fr.round_number BETWEEN 1 AND 5

  UNION ALL

  -- Corner B
  SELECT
    f.fighter_b_id AS fighter_id,
    fr.fight_id,
    fr.round_number,
    fr.b_sig_str_landed::float,
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
    AND fr.round_number BETWEEN 1 AND 5
),

-- Career-wide round-3+ appearance count per fighter (drives confidence tier).
r3p AS (
  SELECT fighter_id, COUNT(DISTINCT fight_id) AS r3p_apps
  FROM per_corner
  WHERE round_number >= 3
  GROUP BY fighter_id
),

-- Label every round-row twice: once under its real weight class, once as CAREER.
labeled AS (
  SELECT fighter_id, weight_class,      round_number, fight_id, sig_landed, grapp_output FROM per_corner
  UNION ALL
  SELECT fighter_id, 'CAREER'::text,    round_number, fight_id, sig_landed, grapp_output FROM per_corner
),

-- Career aggregates per (fighter, weight_class, round).
per_round AS (
  SELECT
    fighter_id,
    weight_class,
    round_number,
    COUNT(DISTINCT fight_id) AS n_fights,
    AVG(sig_landed)          AS avg_sig,
    AVG(grapp_output)        AS avg_grapp
  FROM labeled
  GROUP BY fighter_id, weight_class, round_number
),

normed AS (
  SELECT
    fighter_id,
    weight_class,
    round_number,
    n_fights,
    (avg_sig   / 16.0)                     AS strk_norm,
    (avg_grapp / 90.0)                     AS grapp_norm,
    (avg_sig / 16.0 + avg_grapp / 90.0)    AS raw_output
  FROM per_round
),

-- Round-1 base per (fighter, weight_class) = the pct denominator.
r1base AS (
  SELECT fighter_id, weight_class, raw_output AS r1_raw
  FROM normed
  WHERE round_number = 1
)

SELECT
  n.fighter_id,
  n.weight_class,
  n.round_number,
  n.n_fights,
  COALESCE(r3p.r3p_apps, 0)                                          AS r3p_apps,
  CASE
    WHEN COALESCE(r3p.r3p_apps, 0) >= 7 THEN 'high'
    WHEN COALESCE(r3p.r3p_apps, 0) >= 4 THEN 'limited'
    ELSE 'insufficient'
  END                                                                AS confidence,
  CASE
    WHEN COALESCE(r3p.r3p_apps, 0) < 4 THEN 'finisher_or_low_deep_round_sample'
    ELSE NULL
  END                                                                AS descriptor,
  -- Curve values are NULL for 'insufficient' fighters (no fabricated cardio score).
  CASE WHEN COALESCE(r3p.r3p_apps, 0) < 4 THEN NULL
       ELSE ROUND(n.strk_norm::numeric, 3)  END                      AS strk_norm,
  CASE WHEN COALESCE(r3p.r3p_apps, 0) < 4 THEN NULL
       ELSE ROUND(n.grapp_norm::numeric, 3) END                      AS grapp_norm,
  CASE WHEN COALESCE(r3p.r3p_apps, 0) < 4 THEN NULL
       ELSE ROUND(n.raw_output::numeric, 3) END                      AS raw_output,
  CASE
    WHEN COALESCE(r3p.r3p_apps, 0) < 4                THEN NULL
    WHEN r1.r1_raw IS NULL OR r1.r1_raw < 0.15       THEN NULL   -- divide-by-tiny guard
    ELSE ROUND((n.raw_output / r1.r1_raw)::numeric, 3)
  END                                                                AS pct_of_r1
FROM normed n
LEFT JOIN r3p    ON r3p.fighter_id = n.fighter_id
LEFT JOIN r1base r1 ON r1.fighter_id = n.fighter_id
                   AND r1.weight_class = n.weight_class;

GRANT SELECT ON v_fighter_cardio_curve TO anon, authenticated;
