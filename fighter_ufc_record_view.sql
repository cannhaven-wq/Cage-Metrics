-- =============================================================================
-- v_fighter_ufc_record — T-084 (2026-10-13)
-- =============================================================================
-- Each fighter's UFC record, COUNTED from the completed fights in `fights`.
--
-- WHY THIS EXISTS. `fighters.ufc_wins / ufc_losses / ufc_draws` is wrong for
-- about two fighters in three, and not only because it is stale: in 1,232 of
-- 1,835 disagreements the total number of fights matches and the win/loss
-- split does not (Jon Jones read 12-11; he is 22-1). It was checked against
-- UFCStats for 74 fighters. `fights` agreed on every UFC bout. The one
-- exception is a Contender Series card stored as a UFC event, which is T-086's
-- job, not this view's. Write-up:
-- research/data-integrity/T-083_UFC_RECORDS_2026-10-13.md.
--
-- `fighters.ufc_*` is deliberately left in place, unread (owner instruction,
-- 2026-10-13). Dropping it is a separate L3 decision.
--
-- WHAT COUNTS. The same rule as fight-lab.js::isCompleted, so Fight Lab and
-- every other page agree:
--   * an active booking: `is_active IS NOT FALSE` (D-024 retired bookings are
--     excluded, and a NULL never hides a real fight);
--   * on a card dated before today (UTC), not flagged upcoming;
--   * with a recorded, non-blank method.
-- Result: winner = this fighter -> win; another winner -> loss; no winner and
-- a "Decision ..." method -> draw; no winner otherwise -> no contest.
--
-- A fighter with no completed UFC fight has NO ROW. Readers treat a missing
-- row as 0-0. That is how ufc-record.js does it.
--
-- NO HISTORICAL RESULT IS READ FROM ANYWHERE BUT `fights`, AND NOTHING IS
-- WRITTEN. This file only defines a view.
--
-- Performance: both halves of the UNION ALL hit fights_fighter_{a,b}_id_idx
-- when filtered by fighter_id. The whole view (every fighter) is one
-- aggregate over about 9k bouts. Measured figures are in the PR that adds it.
--
-- Security: security_invoker, so it reads `fights` and `events` with the
-- caller's own rights. Both are public-read for anon AND authenticated. REVOKE
-- from BOTH roles first, then GRANT SELECT. A view inherits broad default
-- grants (see CLAUDE.md, funnel_events).
--
-- Safe to re-run.
-- =============================================================================

CREATE OR REPLACE VIEW public.v_fighter_ufc_record
WITH (security_invoker = on) AS
WITH bouts AS (
  SELECT f.fighter_a_id AS fighter_id, f.winner_id, f.method, e.event_date
  FROM public.fights f
  JOIN public.events e ON e.id = f.event_id
  WHERE f.fighter_a_id IS NOT NULL
    AND f.is_active IS NOT FALSE
    AND f.method IS NOT NULL AND btrim(f.method) <> ''
    AND e.event_date < CURRENT_DATE
    AND e.is_upcoming IS NOT TRUE
  UNION ALL
  SELECT f.fighter_b_id AS fighter_id, f.winner_id, f.method, e.event_date
  FROM public.fights f
  JOIN public.events e ON e.id = f.event_id
  WHERE f.fighter_b_id IS NOT NULL
    AND f.is_active IS NOT FALSE
    AND f.method IS NOT NULL AND btrim(f.method) <> ''
    AND e.event_date < CURRENT_DATE
    AND e.is_upcoming IS NOT TRUE
)
SELECT
  fighter_id,
  COUNT(*) FILTER (WHERE winner_id = fighter_id)::integer                              AS ufc_wins,
  COUNT(*) FILTER (WHERE winner_id IS NOT NULL AND winner_id <> fighter_id)::integer   AS ufc_losses,
  COUNT(*) FILTER (WHERE winner_id IS NULL AND method ILIKE 'decision%')::integer      AS ufc_draws,
  COUNT(*) FILTER (WHERE winner_id IS NULL AND method NOT ILIKE 'decision%')::integer  AS ufc_no_contests,
  COUNT(*)::integer                                                                    AS ufc_fights,
  MAX(event_date)                                                                      AS last_ufc_fight_date
FROM bouts
GROUP BY fighter_id;

COMMENT ON VIEW public.v_fighter_ufc_record IS
  'UFC record counted from completed active bookings in fights (T-084). '
  'Replaces fighters.ufc_wins/losses/draws for display; those columns are '
  'wrong for most fighters and are kept only until an L3 decision drops them. '
  'No row = no completed UFC fight.';

REVOKE ALL ON public.v_fighter_ufc_record FROM anon, authenticated;
GRANT SELECT ON public.v_fighter_ufc_record TO anon, authenticated;
