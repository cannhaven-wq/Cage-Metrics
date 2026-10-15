-- =============================================================================
-- replace_fight_rounds — atomic round replacement for the scrapers (2026-10-15)
-- =============================================================================
-- T-091. NOT APPLIED. Needs the owner's approval (CRITICAL_GATES item 5): it
-- adds two database functions. Apply this BEFORE merging the scraper PR that
-- calls it; until then that scraper refuses to write rounds and fails its run.
--
-- WHY. Both scrapers (cage-metrics-event-scrapper) replaced a fight's round
-- rows with two separate REST calls: DELETE, then INSERT. When the connection
-- dropped between them, the fight was left with NO rounds and the run still
-- reported success. That happened on 2026-10-14 to fight 7349 (McSweeney vs
-- Browne, 2010): its fight totals are intact and its round rows are gone. It
-- is the only fight in that state.
--
-- WHAT. One function per round table. Each runs the delete and the insert in
-- ONE transaction (a function call is atomic), so a failure anywhere leaves
-- the old rounds exactly as they were. It also refuses, rather than deletes:
--   * an empty or non-array payload (never wipe a fight's rounds to nothing);
--   * a fight id that does not exist in the matching fights table;
--   * a payload whose rows name a different fight;
--   * duplicate round numbers;
--   * a set that is not exactly rounds 1..end_round of a finished fight (a
--     partial page would otherwise shrink the fight's stored rounds);
-- and it checks that the number of rows written equals the number sent.
-- Returns the number of rows written.
--
-- SECURITY. SECURITY INVOKER (no definer-function finding), search_path pinned.
-- EXECUTE is revoked from PUBLIC, anon and authenticated and granted to
-- service_role only: the browser can never call it.
--
-- Rollback: fight_rounds_replace_rpc.rollback.sql (drops both functions; the
-- scraper then refuses to write rounds rather than falling back to the old
-- delete-then-insert).
-- Safe to re-run.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.replace_fight_rounds(p_fight_id bigint, p_rounds jsonb)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
  n_sent    integer;
  n_written integer;
  n_end     integer;
BEGIN
  IF p_rounds IS NULL OR jsonb_typeof(p_rounds) <> 'array' OR jsonb_array_length(p_rounds) = 0 THEN
    RAISE EXCEPTION 'replace_fight_rounds: refusing an empty or non-array payload for fight %', p_fight_id;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.fights WHERE id = p_fight_id) THEN
    RAISE EXCEPTION 'replace_fight_rounds: fight % is not in fights', p_fight_id;
  END IF;
  n_sent := jsonb_array_length(p_rounds);

  IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rounds) e
              WHERE e ? 'fight_id' AND (e->>'fight_id')::bigint IS DISTINCT FROM p_fight_id) THEN
    RAISE EXCEPTION 'replace_fight_rounds: payload names a different fight than %', p_fight_id;
  END IF;
  IF (SELECT count(DISTINCT (e->>'round_number')) FROM jsonb_array_elements(p_rounds) e) <> n_sent
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_rounds) e WHERE e->>'round_number' IS NULL) THEN
    RAISE EXCEPTION 'replace_fight_rounds: round numbers must be present and distinct for fight %', p_fight_id;
  END IF;

  -- A fight that ended in round N has exactly rounds 1..N (true of all 8,915
  -- fights with rounds on 2026-10-15). A payload that is not exactly that set
  -- is a partial or wrong page, and replacing with it would LOSE rounds.
  SELECT f.end_round INTO n_end FROM public.fights f WHERE f.id = p_fight_id;
  IF n_end IS NOT NULL AND (
       n_sent <> n_end
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_rounds) e
                   WHERE (e->>'round_number')::int NOT BETWEEN 1 AND n_end)) THEN
    RAISE EXCEPTION 'replace_fight_rounds: fight % ended in round %, payload has % round(s); refusing a partial set',
      p_fight_id, n_end, n_sent;
  END IF;

  DELETE FROM public.fight_rounds WHERE fight_id = p_fight_id;

  -- LATERAL, not (jsonb_populate_record(...)).*: the latter evaluates the
  -- record once per column, calling nextval() 37 times for every row.
  INSERT INTO public.fight_rounds
  SELECT r.*
    FROM jsonb_array_elements(p_rounds) e
    CROSS JOIN LATERAL jsonb_populate_record(NULL::public.fight_rounds,
            (e - 'id') || jsonb_build_object('fight_id', p_fight_id,
                                             'id', nextval(pg_get_serial_sequence('public.fight_rounds', 'id')))) r;
  GET DIAGNOSTICS n_written = ROW_COUNT;

  IF n_written <> n_sent THEN
    RAISE EXCEPTION 'replace_fight_rounds: wrote % rows for fight %, expected %', n_written, p_fight_id, n_sent;
  END IF;
  RETURN n_written;
END
$fn$;

CREATE OR REPLACE FUNCTION public.replace_fight_rounds_non_ufc(p_fight_id bigint, p_rounds jsonb)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
  n_sent    integer;
  n_written integer;
  n_end     integer;
BEGIN
  IF p_rounds IS NULL OR jsonb_typeof(p_rounds) <> 'array' OR jsonb_array_length(p_rounds) = 0 THEN
    RAISE EXCEPTION 'replace_fight_rounds_non_ufc: refusing an empty or non-array payload for fight %', p_fight_id;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.fights_non_ufc WHERE id = p_fight_id) THEN
    RAISE EXCEPTION 'replace_fight_rounds_non_ufc: fight % is not in fights_non_ufc', p_fight_id;
  END IF;
  n_sent := jsonb_array_length(p_rounds);

  IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rounds) e
              WHERE e ? 'fight_id' AND (e->>'fight_id')::bigint IS DISTINCT FROM p_fight_id) THEN
    RAISE EXCEPTION 'replace_fight_rounds_non_ufc: payload names a different fight than %', p_fight_id;
  END IF;
  IF (SELECT count(DISTINCT (e->>'round_number')) FROM jsonb_array_elements(p_rounds) e) <> n_sent
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_rounds) e WHERE e->>'round_number' IS NULL) THEN
    RAISE EXCEPTION 'replace_fight_rounds_non_ufc: round numbers must be present and distinct for fight %', p_fight_id;
  END IF;

  -- A fight that ended in round N has exactly rounds 1..N (true of all 8,915
  -- fights with rounds on 2026-10-15). A payload that is not exactly that set
  -- is a partial or wrong page, and replacing with it would LOSE rounds.
  SELECT f.end_round INTO n_end FROM public.fights_non_ufc f WHERE f.id = p_fight_id;
  IF n_end IS NOT NULL AND (
       n_sent <> n_end
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_rounds) e
                   WHERE (e->>'round_number')::int NOT BETWEEN 1 AND n_end)) THEN
    RAISE EXCEPTION 'replace_fight_rounds_non_ufc: fight % ended in round %, payload has % round(s); refusing a partial set',
      p_fight_id, n_end, n_sent;
  END IF;

  DELETE FROM public.fight_rounds_non_ufc WHERE fight_id = p_fight_id;

  -- LATERAL, not (jsonb_populate_record(...)).*: the latter evaluates the
  -- record once per column, calling nextval() 37 times for every row.
  INSERT INTO public.fight_rounds_non_ufc
  SELECT r.*
    FROM jsonb_array_elements(p_rounds) e
    CROSS JOIN LATERAL jsonb_populate_record(NULL::public.fight_rounds_non_ufc,
            (e - 'id') || jsonb_build_object('fight_id', p_fight_id,
                                             'id', nextval(pg_get_serial_sequence('public.fight_rounds', 'id')))) r;
  GET DIAGNOSTICS n_written = ROW_COUNT;

  IF n_written <> n_sent THEN
    RAISE EXCEPTION 'replace_fight_rounds_non_ufc: wrote % rows for fight %, expected %', n_written, p_fight_id, n_sent;
  END IF;
  RETURN n_written;
END
$fn$;

COMMENT ON FUNCTION public.replace_fight_rounds(bigint, jsonb) IS
  'Atomically replaces a UFC fight''s round rows (delete + insert in one transaction). '
  'Refuses empty payloads, unknown fights, mismatched fight ids and duplicate rounds. service_role only.';
COMMENT ON FUNCTION public.replace_fight_rounds_non_ufc(bigint, jsonb) IS
  'As replace_fight_rounds, for fight_rounds_non_ufc (T-086). service_role only.';

REVOKE ALL ON FUNCTION public.replace_fight_rounds(bigint, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.replace_fight_rounds_non_ufc(bigint, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.replace_fight_rounds(bigint, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.replace_fight_rounds_non_ufc(bigint, jsonb) TO service_role;
