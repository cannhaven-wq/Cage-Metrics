-- =============================================================================
-- fighter_cardio_migration.sql — cardio fade-slope ratings (v1)
-- =============================================================================
-- Populated by cfl_engine/cardio/fit_model.py. One row per fighter.
--
-- fade_slope is the change in significant strikes ATTEMPTED per minute, for
-- every additional minute of cumulative fight time. Negative = output falls
-- away as the fight wears on. It is the per-fighter random slope from a
-- mixed-effects model fitted across every measurable UFC round:
--
--     output_rate ~ cumulative_min_midpoint + opponent_output_rate
--                   + C(weight_class),  random slope per fighter
--
-- fade_slope_dev is the fighter's deviation from the population fade;
-- fade_slope is that deviation plus population_slope, i.e. their own absolute
-- trajectory. Store both so the UI never has to re-derive one from the other.
--
-- WHY THE EXPOSURE COLUMNS SHIP WITH THE RATING: partial pooling shrinks a
-- fighter with little late-round film hard toward the population mean, so a
-- slope off two eligible fights is not the same claim as one off fifteen even
-- when the numbers look alike. Anything rendering fade_slope must render the
-- exposure alongside it. min_past_10 (minutes fought beyond the 10:00 mark) is
-- the honest one to lead with — it is literally how much deep-water evidence
-- exists. Its correlation with slope_se is -0.96.
--
-- NOT DERIVED FROM FINISHES. Finishing changes how much late-round data a
-- fighter has; that is censoring, not signal. It is corrected for by pooling,
-- never by a finish-related feature. Do not add one.
--
-- KNOWN LIMITATION, documented rather than fixed in v1: this measures STRIKING
-- output fade. A grappling-heavy fighter who spends round three holding
-- position is under-measured — the weight-class and opponent-pace covariates
-- absorb only part of it. A control-time-inclusive composite is a later
-- version. Surface this caveat wherever the rating is shown.
--
-- Idempotent. Safe to re-run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS fighter_cardio (
  fighter_id            integer PRIMARY KEY REFERENCES fighters(id) ON DELETE CASCADE,

  -- the rating
  fade_slope            double precision NOT NULL,
  fade_slope_dev        double precision NOT NULL,
  population_slope      double precision NOT NULL,
  slope_se              double precision,

  -- how much evidence backs it (Step 4 exposure metrics)
  total_min_fought      double precision NOT NULL,
  min_past_10           double precision NOT NULL,
  n_fights              integer NOT NULL,
  n_fights_reaching_r3  integer NOT NULL,
  n_round_obs           integer NOT NULL,

  computed_at           timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE fighter_cardio IS
  'Cardio fade-slope ratings from a mixed-effects model on round-level output. Negative fade_slope = output declines with cumulative fight time. Always display alongside min_past_10 / n_fights_reaching_r3 — low-exposure slopes are heavily shrunk toward the population mean.';
COMMENT ON COLUMN fighter_cardio.fade_slope IS
  'Change in sig strikes attempted per minute, per additional minute of cumulative fight time. Absolute (population_slope + fade_slope_dev).';
COMMENT ON COLUMN fighter_cardio.fade_slope_dev IS
  'This fighter''s deviation from the population fade — the raw random slope.';
COMMENT ON COLUMN fighter_cardio.min_past_10 IS
  'Minutes fought beyond the 10:00 mark. The honest measure of deep-water evidence; correlates -0.96 with slope_se.';

CREATE INDEX IF NOT EXISTS fighter_cardio_slope_idx ON fighter_cardio (fade_slope);
CREATE INDEX IF NOT EXISTS fighter_cardio_exposure_idx ON fighter_cardio (n_fights_reaching_r3);

-- Public read: the frontend queries this as anon AND as a signed-in user.
-- Granting only anon makes signed-in users silently see zero rows (CLAUDE.md).
ALTER TABLE fighter_cardio ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS fighter_cardio_public_read ON fighter_cardio;
CREATE POLICY fighter_cardio_public_read
  ON fighter_cardio FOR SELECT
  TO anon, authenticated
  USING (true);

GRANT SELECT ON fighter_cardio TO anon, authenticated;
