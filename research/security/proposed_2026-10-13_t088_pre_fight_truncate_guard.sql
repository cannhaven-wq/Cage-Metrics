-- =============================================================================
-- proposed_2026-10-13_t088_pre_fight_truncate_guard.sql — T-088. PROPOSED. NOT APPLIED.
-- =============================================================================
-- L3: a trigger on an append-only table (coordination/CRITICAL_GATES.md item 5).
--
-- IN PLAIN TERMS
--   The pre-fight record cannot be edited or deleted row by row: two triggers
--   refuse UPDATE and DELETE for every role. But TRUNCATE is not a row
--   operation, so those triggers never see it, and one TRUNCATE would erase
--   every forecast on record. prop_odds, prop_model_locks and win_model_locks
--   already refuse TRUNCATE; pre_fight_snapshots is the one append-only record
--   that does not.
--
--   The least-privilege migration takes TRUNCATE away from the browser roles.
--   This closes it for EVERYONE, service_role and the table owner included,
--   which is what CLAUDE.md already says the table guarantees ("rejects UPDATE
--   and DELETE for every role including service_role").
--
-- WHO IS AFFECTED: nobody who should be. cfl_engine/snapshot_predictions.py only
-- INSERTs, and no file in any repo truncates this table (checked 2026-10-13).
--
-- A new function rather than reusing pre_fight_snapshots_no_rewrite(): that one
-- reads OLD/NEW.fight_id, which a statement-level trigger does not have. Its
-- search_path is pinned, which the advisor asks of every trigger function.
--
-- Idempotent: CREATE OR REPLACE for the function; the trigger is created only
-- if absent, without a `DROP TRIGGER IF EXISTS` (that raises a NOTICE, which
-- hangs the Supabase MCP tool — CLAUDE.md).
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.pre_fight_snapshots_no_truncate()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION
    'pre_fight_snapshots is append-only: TRUNCATE rejected. The pre-fight record must never be erased.';
END;
$$;

REVOKE EXECUTE ON FUNCTION public.pre_fight_snapshots_no_truncate() FROM PUBLIC, anon, authenticated;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid = 'public.pre_fight_snapshots'::regclass
      AND tgname = 'pre_fight_snapshots_block_truncate'
  ) THEN
    CREATE TRIGGER pre_fight_snapshots_block_truncate
      BEFORE TRUNCATE ON public.pre_fight_snapshots
      FOR EACH STATEMENT EXECUTE FUNCTION public.pre_fight_snapshots_no_truncate();
  END IF;
END
$$;

COMMIT;
