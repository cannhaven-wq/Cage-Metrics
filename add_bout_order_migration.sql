-- =============================================================================
-- add_bout_order_migration.sql — true card order + dead-booking retirement
-- =============================================================================
-- Paste into the Supabase SQL Editor and run once, BEFORE pushing the
-- cage-metrics-event-scrapper changes (the scraper writes these columns and
-- its upserts will fail while they don't exist).
--
-- Why: the fights table had no bout-order column, so "card order" on the site
-- was really insert-id order with an is_main_event tiebreak. Upserts key on
-- ufc_fight_id, so bookings that dropped off the UFCStats event page kept
-- their last-written flags forever (stale "main event") and re-booked
-- matchups left both rows on the card (same fighter in two fights).
-- The site now compensates client-side (cfl.orderCard in _shared.js), but
-- these columns are the real fix.
-- =============================================================================

ALTER TABLE fights ADD COLUMN IF NOT EXISTS bout_order integer;
ALTER TABLE fights ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN fights.bout_order IS
  'Position on the UFCStats event page at last scrape: 1 = main event, counting down the card. Written by the event scraper on every upsert.';
COMMENT ON COLUMN fights.is_active IS
  'False when the booking fell off the UFCStats event page (opponent change / scrapped fight). Rows are never deleted — locked picks reference them.';

-- ---------------------------------------------------------------------------
-- NO DATA CLEANUP IN THIS MIGRATION. Deliberately.
-- ---------------------------------------------------------------------------
-- This file previously carried two one-time UPDATEs: retire a booking when the
-- same fighter appears twice on an upcoming card, and clear every is_main_event
-- flag but the newest. Both were removed on 2026-09-18 and are NOT replaced
-- with another heuristic.
--
-- Why they were removed, measured against production rather than assumed:
--
--   * Both matched ZERO rows. The eight upcoming events carry no
--     double-booked fighter and exactly one main-event claim each. The
--     cleanup was inert, so removing it changes nothing today -- which is
--     precisely why now is the time to remove it, rather than after it has
--     silently retired something.
--
--   * Both ranked by `id DESC` and kept the highest. Insert id is arrival
--     order, not truth. On the next opponent swap it would keep whichever row
--     happened to be written last, which is a guess dressed as a rule.
--
--   * Neither caught the case that motivated all of this. UFC 331 carried a
--     cancelled booking (Moicano vs Ortega, withdrawn injured) that appears
--     exactly ONCE on the card, so a double-booking test cannot see it. The
--     heuristic addresses opponent swaps only, and a straight withdrawal is
--     the more common shape.
--
--   * A booking carries published evidence. That one row has 12 predictions
--     and 40 captured quotes against it. Retiring it is a claim about what is
--     on a card, and a claim like that is made from an observation, not from
--     a row-number tiebreak.
--
-- Retirement belongs to the observation-based signal instead: a booking that
-- was observed on a card and is then absent from successive complete card
-- parses. `plan_append` in cfl_engine/event_flow/bout_order.py already computes
-- exactly that as `stale_fights`. See
-- cfl_engine/event_flow/STALE_BOOKING_LIFECYCLE.md.
--
-- This migration is therefore ADDITIVE ONLY:
--   * no UPDATE, no DELETE, no DROP
--   * no row's meaning is reinterpreted
--   * `is_active` defaults to true, so every existing row -- including all 790
--     past events -- stays active and no historical reporting changes
--
-- ---------------------------------------------------------------------------

-- Sanity check: upcoming events with their active fights and flags.
SELECT e.name, f.id, f.bout_order, f.is_main_event, f.is_active,
       f.fighter_a_name || ' vs ' || f.fighter_b_name AS bout
FROM fights f JOIN events e ON e.id = f.event_id
WHERE e.is_upcoming = true
ORDER BY e.event_date, f.is_main_event DESC, f.id;
