-- =============================================================================
-- Bet tracking — per-user bankroll + bet log
-- =============================================================================
-- Backs the My Book page (mybook.html). Lets a signed-in user record real
-- bets they placed at any book, track CLV vs the BFO opener the model uses,
-- and watch their bankroll trajectory vs the picks-page backtest.
--
-- Auto-grading: when model_predictions.outcome_known=TRUE for (fight_id,
-- fighter_id) on an open bet, the page settles the row client-side
-- (the user's signed-in JWT satisfies the UPDATE policy below).
--
-- Re-run safe.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- user_bankrolls — one row per user, the current bankroll state.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_bankrolls (
    user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    current_amount   NUMERIC(12,2) NOT NULL DEFAULT 0,
    initial_deposit  NUMERIC(12,2) NOT NULL DEFAULT 0,
    kelly_fraction   NUMERIC(4,3)  NOT NULL DEFAULT 0.5,   -- 0.25/0.5/1.0
    max_bet_fraction NUMERIC(4,3)  NOT NULL DEFAULT 0.05,  -- cap per fight
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE user_bankrolls ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own bankroll"   ON user_bankrolls;
DROP POLICY IF EXISTS "Users insert own bankroll" ON user_bankrolls;
DROP POLICY IF EXISTS "Users update own bankroll" ON user_bankrolls;

CREATE POLICY "Users read own bankroll" ON user_bankrolls
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "Users insert own bankroll" ON user_bankrolls
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own bankroll" ON user_bankrolls
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- user_bets — one row per real bet the user placed.
-- ----------------------------------------------------------------------------
-- status lifecycle:  open → won | lost | push | void
-- pnl_usd is signed: positive for a win, negative for a loss, 0 for push/void.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_bets (
    id                     BIGSERIAL PRIMARY KEY,
    user_id                UUID   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    fight_id               BIGINT NOT NULL REFERENCES fights(id) ON DELETE CASCADE,
    fighter_id             BIGINT NOT NULL REFERENCES fighters(id) ON DELETE CASCADE,
    side                   CHAR(1) NOT NULL CHECK (side IN ('A','B')),
    book                   TEXT NOT NULL,
    placed_price_american  INT  NOT NULL,
    opener_price_american  INT,                 -- BFO opener for CLV math
    stake_usd              NUMERIC(10,2) NOT NULL CHECK (stake_usd >= 0),
    model_p                NUMERIC(7,6),
    edge_at_placement      NUMERIC(7,6),        -- model_p - placed_price_implied
    status                 TEXT NOT NULL DEFAULT 'open'
                              CHECK (status IN ('open','won','lost','push','void')),
    won                    BOOLEAN,             -- mirrors status, set on grading
    pnl_usd                NUMERIC(10,2),
    placed_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at             TIMESTAMPTZ,
    notes                  TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_bets_user
    ON user_bets(user_id, placed_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_bets_user_open
    ON user_bets(user_id, status) WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_user_bets_fight
    ON user_bets(fight_id, fighter_id);

ALTER TABLE user_bets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own bets"   ON user_bets;
DROP POLICY IF EXISTS "Users insert own bets" ON user_bets;
DROP POLICY IF EXISTS "Users update own bets" ON user_bets;
DROP POLICY IF EXISTS "Users delete own bets" ON user_bets;

CREATE POLICY "Users read own bets" ON user_bets
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "Users insert own bets" ON user_bets
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own bets" ON user_bets
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own bets" ON user_bets
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- Touch updated_at on bankroll changes.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.touch_user_bankrolls_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_touch_user_bankrolls ON user_bankrolls;
CREATE TRIGGER trg_touch_user_bankrolls
  BEFORE UPDATE ON user_bankrolls
  FOR EACH ROW EXECUTE FUNCTION public.touch_user_bankrolls_updated_at();
