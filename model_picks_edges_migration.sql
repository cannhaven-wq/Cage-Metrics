-- =============================================================================
-- model_picks_edges_migration.sql — publishing tables for the CFL engine
-- =============================================================================
-- Paste into the Supabase SQL Editor and run once (direct DB is IPv6-only from
-- this machine, so DDL goes through the editor; REST handles the row inserts).
--
-- Two tables, one per product face of cfl_engine (see cfl_engine/faces.py):
--   model_picks — Face 1. One locked pick per fight: the calibrated winner +
--                 confidence tier (Lock / Pick / Lean). Sold on accuracy.
--   model_edges — Face 2. One flagged +EV bet per fight vs the vig-free close,
--                 with fractional-Kelly stake and CLV instrumentation. Sold on
--                 ROI / CLV.
--
-- source column: 'backtest' rows are the point-in-time walk-forward replay
-- (published by cfl_engine/publish_backtest.py); 'live' rows are locked at
-- first write the week of a real card and NEVER re-priced. The unique
-- (fight_id, source) constraint keeps exactly one row per fight per source, so
-- a backtest re-publish can DELETE+reinsert its own rows without ever touching
-- a locked 'live' pick.
--
-- Corner convention: pick_side / side are the DB fights-table corner ('a'/'b'),
-- NOT the engine's randomized inference corner. The loader maps back to the DB
-- corner before writing (see publish_backtest.py). pick_fighter_id /
-- bet_fighter_id are the unambiguous source of truth; the side char is a
-- convenience for the frontend.
--
-- RLS: SELECT open to anon AND authenticated (CLAUDE.md rule — an anon-only
-- policy makes signed-in users see empty results with HTTP 200 and no error).
-- No INSERT/UPDATE/DELETE policies: the publisher uses the service_role key,
-- which bypasses RLS. Public writes are impossible by construction.
--
-- Idempotent — safe to re-run.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- model_picks — Face 1: one calibrated pick per fight.
-- ----------------------------------------------------------------------------
-- p_cal is the calibrated probability OF THE PICKED FIGHTER (always >= 0.5).
-- tier is derived from that confidence: Lock >= 0.65, Pick >= 0.57, else Lean.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_picks (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fight_id         BIGINT  NOT NULL REFERENCES fights(id),
    event_date       DATE    NOT NULL,
    p_cal            NUMERIC NOT NULL,                       -- calibrated prob of the picked fighter
    pick_fighter_id  BIGINT  NOT NULL REFERENCES fighters(id),
    pick_side        CHAR(1) NOT NULL CHECK (pick_side IN ('a','b')),  -- DB fights corner of the pick
    tier             TEXT    NOT NULL CHECK (tier IN ('Lock','Pick','Lean')),
    source           TEXT    NOT NULL DEFAULT 'live' CHECK (source IN ('backtest','live')),
    model_version    TEXT    NOT NULL DEFAULT 'engine_v1',
    published_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fight_id, source)
);

CREATE INDEX IF NOT EXISTS idx_model_picks_event_date
    ON model_picks(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_model_picks_source
    ON model_picks(source);

ALTER TABLE model_picks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read model_picks" ON model_picks;
CREATE POLICY "public read model_picks" ON model_picks
    FOR SELECT TO anon, authenticated USING (true);

GRANT SELECT ON model_picks TO anon, authenticated;

-- ----------------------------------------------------------------------------
-- model_edges — Face 2: one flagged +EV bet per fight.
-- ----------------------------------------------------------------------------
-- All probabilities/odds are oriented to the BET side:
--   p_blend  — model blend probability of the bet side
--   q_mkt    — vig-free market probability of the bet side
--   edge     — p_blend - q_mkt (>= edge_min, i.e. 0.04, by construction)
--   stake_frac — fractional-Kelly stake (quarter-Kelly, capped at 0.02)
-- odds_at_publish is the American price of the bet side captured when the row
-- is written; closing_odds is the American price of the bet side at close.
-- clv_pp is the vig-free implied-prob move (close minus publish) on the bet
-- side — positive means we beat the close; clv_beat mirrors its sign.
-- For 'backtest' rows the only price on file is the close, so
-- odds_at_publish == closing_odds and clv is left NULL (no bet-time line).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_edges (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fight_id         BIGINT  NOT NULL REFERENCES fights(id),
    event_date       DATE    NOT NULL,
    side             CHAR(1) NOT NULL CHECK (side IN ('a','b')),  -- DB fights corner of the bet
    bet_fighter_id   BIGINT  NOT NULL REFERENCES fighters(id),
    p_blend          NUMERIC NOT NULL,                       -- blend prob of the bet side
    q_mkt            NUMERIC NOT NULL,                       -- vig-free market prob of the bet side
    edge             NUMERIC NOT NULL,                       -- p_blend - q_mkt
    stake_frac       NUMERIC NOT NULL,                       -- fractional-Kelly stake fraction
    odds_at_publish  INTEGER,                                -- American, bet side, at publish
    closing_odds     INTEGER,                                -- American, bet side, at close
    clv_pp           NUMERIC,                                -- vig-free implied-prob move, bet side (+ = beat close)
    clv_beat         BOOLEAN,                                -- clv_pp > 0
    source           TEXT    NOT NULL DEFAULT 'live' CHECK (source IN ('backtest','live')),
    model_version    TEXT    NOT NULL DEFAULT 'engine_v1',
    published_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at       TIMESTAMPTZ,
    UNIQUE (fight_id, source)
);

CREATE INDEX IF NOT EXISTS idx_model_edges_event_date
    ON model_edges(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_model_edges_source
    ON model_edges(source);

ALTER TABLE model_edges ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read model_edges" ON model_edges;
CREATE POLICY "public read model_edges" ON model_edges
    FOR SELECT TO anon, authenticated USING (true);

GRANT SELECT ON model_edges TO anon, authenticated;
