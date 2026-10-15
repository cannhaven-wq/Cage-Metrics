-- =============================================================================
-- T-093 — retire three duplicate bookings on UFC Fight Night: Song vs.
-- Figueiredo (event 113, 2026-05-30). NOT APPLIED: owner's decision (L3).
-- =============================================================================
-- UFCStats re-issued three bouts' ids. The scraper inserted new rows and the old
-- ones stayed, so each bout is in `fights` twice and six public UFC records
-- count it twice (Vera 2-0, Zhu 0-2, Matthews 17-8, Harris 4-5, Tsuruya 4-1,
-- Gurule 1-5 -> 1-0, 0-1, 16-8, 4-4, 3-1, 1-4).
--
--   stale (retired here)                       canonical (kept)
--   43   b007aa53eadea847 Harris v Matthews    27872 c1c9dfd0c0952f18
--   46   a3d176f12b1f0b86 Tsuruya v Gurule     27877 224dce2c0b03e7eb
--   8780 b6829142f42a75dc Zhu v Vera           27879 34d5ec676fb5bce3
--
-- HOW: is_active = false — the dead-booking mechanism D-024 used for four
-- bookings, which v_fighter_ufc_record, Fight Lab and the shared fight-history
-- helper already honour. NOTHING IS DELETED OR MOVED:
--   * the 10,514 fight_odds rows, 3 predictions rows, 28 model_predictions rows
--     and 1 consensus snapshot that hang off the stale ids stay exactly where
--     they are. Moving the odds onto the canonical fights (what the unapplied
--     dead_booking_cleanup.sql does) is ruled out: PRED-001's frozen H1
--     manifest excludes 43/46/8780 because "their stored prices may belong to
--     a different matchup", and attaching them to the canonical fights would
--     put suspect prices on rows H1's eligibility can see;
--   * every FK to fights cascades on delete, so a DELETE would destroy that
--     history. This file never deletes.
-- H1 is unaffected: none of the six ids is in research/protocol/h1_fight_ids.txt,
-- and the manifest already excludes the three stale ids by id and by is_active.
--
-- Rehearsed on production 2026-10-15 in a rolled-back transaction: 3 rows
-- updated, the six records changed exactly as above, odds rows untouched.
-- Rollback: dead_bookings_t093.rollback.sql (one UPDATE back to true).
-- =============================================================================

BEGIN;
SET LOCAL lock_timeout = '3s';

DO $guard$
DECLARE n int;
BEGIN
  -- The rows must still be what was audited: stale ids with their old UFCStats
  -- ids, each with a canonical twin on the same card, same two fighters, same
  -- winner, that carries round stats.
  SELECT count(*) INTO n
    FROM (VALUES (43::bigint, 'b007aa53eadea847', 27872::bigint),
                 (46, 'a3d176f12b1f0b86', 27877),
                 (8780, 'b6829142f42a75dc', 27879)) m(stale, ufc, canon)
    JOIN public.fights s ON s.id = m.stale AND s.ufc_fight_id = m.ufc
    JOIN public.fights c ON c.id = m.canon
   WHERE c.event_id = s.event_id
     AND least(c.fighter_a_id, c.fighter_b_id) = least(s.fighter_a_id, s.fighter_b_id)
     AND greatest(c.fighter_a_id, c.fighter_b_id) = greatest(s.fighter_a_id, s.fighter_b_id)
     AND c.winner_id IS NOT DISTINCT FROM s.winner_id
     AND c.is_active IS NOT FALSE
     AND EXISTS (SELECT 1 FROM public.fight_rounds r WHERE r.fight_id = c.id)
     AND NOT EXISTS (SELECT 1 FROM public.fight_rounds r WHERE r.fight_id = s.id);
  IF n <> 3 THEN
    RAISE EXCEPTION 'T-093 aborted: expected 3 audited stale/canonical pairs, found %', n;
  END IF;
END
$guard$;

UPDATE public.fights SET is_active = false
 WHERE id IN (43, 46, 8780) AND is_active IS DISTINCT FROM false;

DO $check$
BEGIN
  IF (SELECT count(*) FROM public.fights WHERE id IN (43, 46, 8780) AND is_active = false) <> 3 THEN
    RAISE EXCEPTION 'T-093 aborted: the three bookings are not all retired';
  END IF;
  IF (SELECT count(*) FROM public.fight_odds WHERE fight_id IN (43, 46, 8780)) <> 10514 THEN
    RAISE EXCEPTION 'T-093 aborted: odds rows on the stale ids changed';
  END IF;
END
$check$;

COMMIT;
