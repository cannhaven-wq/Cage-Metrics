-- =============================================================================
-- T-086 ROLLBACK — put "DWCS 10.3" back exactly as it was before the migration
-- =============================================================================
-- Undoes t086_dwcs_non_ufc.sql in one transaction:
--   1. drops the events name guard (otherwise "DWCS 10.3" cannot re-enter);
--   2. copies event 4259, its 5 bouts and 8 round rows back, same ids;
--   3. proves the restored rows are byte-for-byte the originals, using the
--      fingerprints the migration stored on fights_non_ufc.id and
--      fight_rounds_non_ufc.id;
--   4. drops the three *_non_ufc tables.
--
-- REFUSES if the *_non_ufc tables hold anything besides the original card.
-- That means the updated scraper has since stored another non-UFC card there,
-- and dropping the tables would lose it. Decide what happens to those rows
-- first; this file never discards data.
-- =============================================================================

BEGIN;

SET LOCAL lock_timeout = '10s';

DO $pre$
DECLARE n bigint;
BEGIN
  IF to_regclass('public.fights_non_ufc') IS NULL THEN
    RAISE EXCEPTION 'T-086 rollback: fights_non_ufc does not exist; nothing to roll back';
  END IF;
  SELECT count(*) INTO n FROM public.events_non_ufc WHERE id <> 4259;
  IF n <> 0 THEN RAISE EXCEPTION 'T-086 rollback: events_non_ufc holds % other card(s); refusing to drop them', n; END IF;
  SELECT count(*) INTO n FROM public.fights_non_ufc WHERE id NOT IN (49307,49308,49309,49310,49311);
  IF n <> 0 THEN RAISE EXCEPTION 'T-086 rollback: fights_non_ufc holds % other bout(s); refusing to drop them', n; END IF;
  SELECT count(*) INTO n FROM public.fight_rounds_non_ufc
   WHERE fight_id NOT IN (49307,49308,49309,49310,49311);
  IF n <> 0 THEN RAISE EXCEPTION 'T-086 rollback: fight_rounds_non_ufc holds other rows; refusing to drop them'; END IF;

  SELECT count(*) INTO n FROM public.fights_non_ufc;
  IF n <> 5 THEN RAISE EXCEPTION 'T-086 rollback: fights_non_ufc holds %, expected 5', n; END IF;
  SELECT count(*) INTO n FROM public.fight_rounds_non_ufc;
  IF n <> 8 THEN RAISE EXCEPTION 'T-086 rollback: fight_rounds_non_ufc holds %, expected 8', n; END IF;

  SELECT count(*) INTO n FROM public.events WHERE id = 4259 OR ufc_event_id = '2015c944226ad2df';
  IF n <> 0 THEN RAISE EXCEPTION 'T-086 rollback: events already holds the DWCS card'; END IF;
  SELECT count(*) INTO n FROM public.fights
   WHERE id IN (49307,49308,49309,49310,49311)
      OR ufc_fight_id IN (SELECT ufc_fight_id FROM public.fights_non_ufc);
  IF n <> 0 THEN RAISE EXCEPTION 'T-086 rollback: fights already holds a DWCS bout'; END IF;
END
$pre$;

ALTER TABLE public.events DROP CONSTRAINT IF EXISTS events_ufc_name_only;

INSERT INTO public.events
  (id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at)
SELECT id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at
  FROM public.events_non_ufc WHERE id = 4259;

INSERT INTO public.fights
SELECT f.* FROM public.fights_non_ufc f ORDER BY f.id;

INSERT INTO public.fight_rounds
SELECT r.* FROM public.fight_rounds_non_ufc r ORDER BY r.id;

DO $verify$
DECLARE
  want text; got text;
BEGIN
  want := substring(col_description('public.fights_non_ufc'::regclass, 1) from '= ([0-9a-f]{32})$');
  SELECT md5(string_agg(f::text, '|' ORDER BY f.id)) INTO got
    FROM public.fights f WHERE f.id IN (49307,49308,49309,49310,49311);
  IF want IS NULL OR got IS DISTINCT FROM want THEN
    RAISE EXCEPTION 'T-086 rollback: restored fights differ from the originals (% vs %)', got, want;
  END IF;

  want := substring(col_description('public.fight_rounds_non_ufc'::regclass, 1) from '= ([0-9a-f]{32})$');
  SELECT md5(string_agg(r::text, '|' ORDER BY r.id)) INTO got
    FROM public.fight_rounds r WHERE r.fight_id IN (49307,49308,49309,49310,49311);
  IF want IS NULL OR got IS DISTINCT FROM want THEN
    RAISE EXCEPTION 'T-086 rollback: restored rounds differ from the originals (% vs %)', got, want;
  END IF;

  SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) INTO want FROM (
    SELECT id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at
      FROM public.events_non_ufc WHERE id = 4259) t;
  SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) INTO got FROM (
    SELECT id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at
      FROM public.events WHERE id = 4259) t;
  IF got IS DISTINCT FROM want THEN
    RAISE EXCEPTION 'T-086 rollback: restored event differs (% vs %)', got, want;
  END IF;
END
$verify$;

-- Children first. fight_rounds_non_ufc goes with its tables.
DROP TABLE public.fight_rounds_non_ufc;
DROP TABLE public.fights_non_ufc;
DROP TABLE public.events_non_ufc;

COMMIT;
