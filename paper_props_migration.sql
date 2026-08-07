-- =============================================================================
-- paper_props_migration.sql — the props paper-trading layer
-- =============================================================================
-- Stage-1 (paper) of wiring the model to the prop market. NO real money touches
-- this: paper_picks is a private audit ledger of what the pipeline WOULD have
-- bet, graded after the fact for closing-line value (CLV). prop_cards is the
-- public, presentation-only projection the site shows fans.
--
-- Two tables, deliberately opposite visibility:
--   paper_picks  — PRIVATE. service_role only. Holds entry prices, model/market
--                  probabilities, blended edge, and post-event CLV. This is the
--                  research ledger; it must never leak (it reveals the exact
--                  edge and would let anyone reconstruct the book we beat).
--   prop_cards   — PUBLIC. anon + authenticated SELECT (CFL rule). Holds only
--                  the fan-facing verdict (over/under/skip + lean/strong + one
--                  sentence). No prices, no edge percentages beyond the bucketed
--                  strength label.
--
-- Apply via Supabase → SQL Editor (direct DB is IPv6-only from this machine;
-- see reference_cfl_db_access). Idempotent — safe to re-run.
-- =============================================================================


-- ----------------------------------------------------------------------------
-- paper_picks — private ledger. One row per (fight, fighter, stat_type, source)
-- capture decision. Insert-only locking: the first capture cycle that evaluates
-- a prop writes the row and locks the entry price; later cycles DO NOTHING on
-- conflict, so entry_odds / market_p_open / blend_p reflect the OPENING line we
-- would actually have bet into, never a later re-quote. Grading columns
-- (result / clv / close_*) are filled by grading/paper_clv.py after the event.
--
-- `decision` distinguishes a real paper bet ('pick', blended edge >= 4%) from an
-- explicit 'skip' (evaluated but below threshold). Skips are logged too so the
-- ledger records the full opportunity set, not just the bets — you can't audit
-- a strategy from its winners alone.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_picks (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fight_id       INTEGER NOT NULL,
    fighter_id     INTEGER NOT NULL,
    stat_type      TEXT    NOT NULL,
    line           NUMERIC NOT NULL,
    side           TEXT    NOT NULL CHECK (side IN ('over', 'under')),
    source         TEXT    NOT NULL,                 -- book / feed the line came from
    decision       TEXT    NOT NULL DEFAULT 'pick'
                       CHECK (decision IN ('pick', 'skip')),
    entry_odds     INTEGER,                          -- American price of `side` at entry
    model_p        NUMERIC,                          -- simulate.py probability of `side`
    market_p_open  NUMERIC,                          -- de-vigged opener prob of `side`
    blend_p        NUMERIC,                          -- log-odds blend, w<=0.4 on market
    ev_pct         NUMERIC,                          -- blended edge = blend_p - market_p_open

    -- --- filled post-event by grading/paper_clv.py ---
    result         TEXT DEFAULT 'pending'
                       CHECK (result IN ('pending', 'hit', 'miss', 'push')),
    close_odds     INTEGER,                          -- American price of `side` at close
    market_p_close NUMERIC,                          -- de-vigged closing prob of `side`
    clv            NUMERIC,                          -- market_p_close - market_p_open (de-vigged)
    graded_at      TIMESTAMPTZ
);

-- Insert-only lock: one decision row per prop per source. The writer uses
-- ON CONFLICT DO NOTHING so re-running a capture cycle never rewrites a locked
-- entry price. (A prop that a book re-opens at a new line is a new `line` value
-- and therefore a new locked row — intended.)
CREATE UNIQUE INDEX IF NOT EXISTS paper_picks_lock
    ON paper_picks (fight_id, fighter_id, stat_type, source, line, side);

CREATE INDEX IF NOT EXISTS paper_picks_fight ON paper_picks (fight_id);
CREATE INDEX IF NOT EXISTS paper_picks_ungraded
    ON paper_picks (fight_id) WHERE result = 'pending';

-- PRIVATE: RLS on, ZERO policies, and privileges revoked from the public roles.
-- With RLS enabled and no policy, anon/authenticated see no rows even if a grant
-- slipped in; the REVOKE makes that explicit and defence-in-depth. service_role
-- bypasses RLS, so the pipeline still has full access.
ALTER TABLE paper_picks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON paper_picks FROM anon, authenticated;


-- ----------------------------------------------------------------------------
-- prop_cards — PUBLIC fan-facing verdicts. Rebuilt each capture cycle by
-- grading/write_prop_cards.py from the latest sims. Presentation only: the real
-- edge lives in paper_picks. Verdict bands are mechanical (no overrides):
--   blend_p <  0.55            -> skip
--   0.55 <= blend_p < 0.60     -> lean
--   blend_p >= 0.60            -> strong
-- why_text is a single templated sentence driven by the top model covariates.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prop_cards (
    fight_id    INTEGER NOT NULL,
    fighter_id  INTEGER NOT NULL,
    stat_type   TEXT    NOT NULL,
    line        NUMERIC,
    our_number  NUMERIC,                             -- model's projected stat value
    verdict     TEXT CHECK (verdict IN ('over', 'under', 'skip')),
    strength    TEXT CHECK (strength IN ('lean', 'strong')),   -- NULL when skip
    why_text    TEXT,
    model_p     NUMERIC,
    ev_pct      NUMERIC,
    result      TEXT DEFAULT 'pending'
                    CHECK (result IN ('pending', 'hit', 'miss', 'push')),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (fight_id, fighter_id, stat_type)
);

CREATE INDEX IF NOT EXISTS prop_cards_fight ON prop_cards (fight_id);

-- PUBLIC read (CFL rule: public-data tables grant SELECT to BOTH anon AND
-- authenticated, or signed-in users silently get zero rows). Writes are
-- service_role only — no INSERT/UPDATE policy for the public roles.
ALTER TABLE prop_cards ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public read prop_cards" ON prop_cards;
CREATE POLICY "public read prop_cards" ON prop_cards
    FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON prop_cards TO anon, authenticated;
