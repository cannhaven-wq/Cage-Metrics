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
-- One-time cleanup of damage already in the table, scoped to UPCOMING events
-- (past events graded fine; their order is cosmetic and the scraper will
-- backfill bout_order on its recent-events pass anyway).
-- ---------------------------------------------------------------------------

-- 1) A fighter can only fight once per card: where the same fighter appears in
--    two fights of one upcoming event, retire the older booking.
WITH upcoming_fights AS (
  SELECT f.id, f.event_id, f.fighter_a_id, f.fighter_b_id
  FROM fights f JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = true
),
sides AS (
  SELECT id, event_id, fighter_a_id AS fighter_id FROM upcoming_fights WHERE fighter_a_id IS NOT NULL
  UNION ALL
  SELECT id, event_id, fighter_b_id FROM upcoming_fights WHERE fighter_b_id IS NOT NULL
),
stale AS (
  SELECT id FROM (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY event_id, fighter_id ORDER BY id DESC) AS rn
    FROM sides
  ) ranked WHERE rn > 1
)
UPDATE fights SET is_active = false WHERE id IN (SELECT id FROM stale);

-- 2) One main event per upcoming card: clear the flag everywhere except the
--    newest row still claiming it. (The scraper re-asserts the correct flag
--    and bout_order on its next pass; the site independently resolves the
--    main event from the event name.)
WITH claims AS (
  SELECT f.id, ROW_NUMBER() OVER (PARTITION BY f.event_id ORDER BY f.id DESC) AS rn
  FROM fights f JOIN events e ON e.id = f.event_id
  WHERE e.is_upcoming = true AND f.is_main_event = true AND f.is_active = true
)
UPDATE fights SET is_main_event = false
WHERE id IN (SELECT id FROM claims WHERE rn > 1);

-- Sanity check: upcoming events with their active fights and flags.
SELECT e.name, f.id, f.bout_order, f.is_main_event, f.is_active,
       f.fighter_a_name || ' vs ' || f.fighter_b_name AS bout
FROM fights f JOIN events e ON e.id = f.event_id
WHERE e.is_upcoming = true
ORDER BY e.event_date, f.is_main_event DESC, f.id;
