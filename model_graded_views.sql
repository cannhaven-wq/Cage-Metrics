-- =============================================================================
-- model_graded_views.sql — graded read views for the front-end
-- =============================================================================
-- model_picks / model_edges carry no outcome column, and grading the 3,232
-- backtest picks client-side would need a 3,000+-id fights .in() (URL > the ~2KB
-- limit → HTTP 414, plus the 1000-row response cap). So push the fights join
-- server-side. The site reads these views instead of the base tables.
--
--   v_model_picks_graded  — one row per pick + outcome (hit true/false/null)
--   v_model_edges_graded  — one row per edge + outcome (won true/false/null)
--
-- hit/won are NULL while the fight is unresolved (winner_id null). For the live
-- upcoming card that is the normal state; the front-end renders those as pending.
-- Do NOT surface clv_pp yet — backtest rows are NULL and the live edges are not
-- settled; the site's stance is "CLV after 100 locked picks".
--
-- RLS note: SECURITY INVOKER so the view respects the caller's RLS; all three
-- underlying relations (model_picks, model_edges, fights) already grant SELECT to
-- anon + authenticated, so anon reads work. GRANT on the views to both roles.
--
-- Idempotent. Run in the Supabase SQL Editor.
-- =============================================================================

CREATE OR REPLACE VIEW v_model_picks_graded
    WITH (security_invoker = true) AS
SELECT p.id, p.fight_id, p.event_date, p.p_cal, p.pick_fighter_id, p.pick_side,
       p.tier, p.source, p.model_version, p.published_at,
       f.fighter_a_id, f.fighter_b_id, f.fighter_a_name, f.fighter_b_name,
       f.winner_id, f.method,
       CASE WHEN f.winner_id IS NULL THEN NULL
            ELSE (f.winner_id = p.pick_fighter_id) END AS hit
FROM model_picks p
JOIN fights f ON f.id = p.fight_id;

GRANT SELECT ON v_model_picks_graded TO anon, authenticated;

CREATE OR REPLACE VIEW v_model_edges_graded
    WITH (security_invoker = true) AS
SELECT e.id, e.fight_id, e.event_date, e.side, e.bet_fighter_id,
       e.p_blend, e.q_mkt, e.edge, e.stake_frac,
       e.odds_at_publish, e.closing_odds, e.clv_pp, e.clv_beat,
       e.source, e.model_version, e.published_at, e.settled_at,
       f.fighter_a_name, f.fighter_b_name, f.winner_id, f.method,
       CASE WHEN f.winner_id IS NULL THEN NULL
            ELSE (f.winner_id = e.bet_fighter_id) END AS won
FROM model_edges e
JOIN fights f ON f.id = e.fight_id;

GRANT SELECT ON v_model_edges_graded TO anon, authenticated;
