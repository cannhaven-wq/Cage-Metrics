-- =============================================================================
-- fight_odds — consensus moneyline odds per fight
-- =============================================================================
-- One row per fight. Written exclusively by the build/fetch-odds.js GitHub
-- Action using the SUPABASE_SERVICE_ROLE_KEY (bypasses RLS). Read by anon +
-- authenticated for the frontend market-line display.
--
-- The fetcher averages implied probability across every US bookmaker the
-- Odds API returns for a given fight, removes the vig (normalizes the two
-- sides to sum to 1.0), and stores both the averaged implied probability
-- and a back-derived "consensus" American odds for display.
--
-- We keep one row per fight (PRIMARY KEY on fight_id) and UPSERT on every
-- fetch, so the row always reflects the most recent market snapshot — not
-- a historical line trajectory. Closing-line history would be a follow-up
-- (insert into a separate fight_odds_history table on each fetch).
--
-- Safe to re-run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS fight_odds (
  fight_id          BIGINT PRIMARY KEY,
  event_id          BIGINT,
  fighter_a_id      BIGINT,
  fighter_b_id      BIGINT,
  fighter_a_name    TEXT,
  fighter_b_name    TEXT,
  american_odds_a   INTEGER,   -- back-derived from averaged vig-removed implied
  american_odds_b   INTEGER,
  implied_prob_a    REAL,      -- vig-removed, averaged across bookmakers (0..1)
  implied_prob_b    REAL,
  bookmaker_count   INTEGER,   -- how many books contributed to the average
  fetched_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fight_odds_event_id_idx ON fight_odds (event_id);
CREATE INDEX IF NOT EXISTS fight_odds_fetched_at_idx ON fight_odds (fetched_at DESC);

ALTER TABLE fight_odds ENABLE ROW LEVEL SECURITY;

-- Read-only for public roles. Writes happen via service-role key, which
-- bypasses RLS and doesn't need a policy.
DROP POLICY IF EXISTS fight_odds_read_all ON fight_odds;
CREATE POLICY fight_odds_read_all ON fight_odds
  FOR SELECT
  TO anon, authenticated
  USING (true);

GRANT SELECT ON fight_odds TO anon, authenticated;
