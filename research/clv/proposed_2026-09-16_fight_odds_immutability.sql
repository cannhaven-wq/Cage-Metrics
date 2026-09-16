-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- Make the raw quote evidence actually durable (CLV-001 R-01, Amendment 6 (g)).
--
-- STATUS: draft. Apply AFTER proposed_2026-09-16_fight_odds_capture.sql — this
-- protects those columns, and protecting a column that does not exist yet is a
-- no-op that then silently fails to cover it when it appears. (It does not, in
-- fact, fail: the guard below is written over to_jsonb(row), so it covers every
-- column the table has at the moment of the UPDATE, including ones added later.
-- Apply it second anyway, so the ordering matches the reasoning.)
--
-- Filed under research/clv/ rather than the repo root so the "apply root *.sql"
-- habit cannot pick it up by accident.
--
-- THIS ONE IS NOT ADDITIVE-ONLY, AND SAYS SO
-- ------------------------------------------
-- The other three CLV-001 migrations add columns, indexes and NOT VALID checks
-- and change no behaviour. This one adds TRIGGERS to a table that is already
-- being written to, which changes what an existing writer is allowed to do. It
-- is filed separately for exactly that reason: it must be read, and approved, on
-- its own terms rather than inside a list of additive changes.
--
-- What it still does NOT do: no DROP of a column, no DELETE of a row, no
-- backfill, no reinterpretation of an existing value. Every row in the table is
-- byte-identical after applying it. And no EXISTING trigger is altered or
-- removed — `fight_odds` has none today; these are new.
--
-- WHY
-- ---
-- R-01: "Every quote is stored as captured. The raw quote store rejects UPDATE
-- and DELETE by trigger for every role including service_role... A store that
-- can be edited afterwards is not evidence, which is the same argument the
-- pre-fight snapshot table rests on."
--
-- `fight_odds` does not do that. It is an ordinary table and it is UPDATEd in
-- production today — build/fetch-odds.js promotes and demotes `is_closer` after
-- every card. So `clv_source_quote_ids`, which is CLV-001's deterministic
-- reference to the exact rows a scored number came from, currently points at
-- rows whose price, timestamp, book, fighter or provenance could be rewritten
-- afterwards with nothing left to show for it. The consensus hash would still
-- match, because the hash covers the artifact we stored, not the rows it names.
--
-- The honest options were: a separate immutable CLV quote ledger (a second copy
-- of every quote, and a second thing to keep correct), or make the observation
-- fields of this table immutable while leaving the derived flags maintainable.
-- The second is taken, because the evidence then stays in one place and the
-- legacy behaviour keeps working unchanged.
--
-- WHITELIST, NOT BLACKLIST
-- ------------------------
-- The guard compares to_jsonb(old) and to_jsonb(new) with the mutable keys
-- removed, so everything is protected by default and only the named derived
-- flags can move. A column added later is covered the moment it exists, with no
-- edit here — which is the opposite of a blacklist, where a new column is
-- unprotected until somebody remembers it.
--
-- `is_opener` and `is_closer` are DERIVED flags: recomputable at any time from
-- (fight, book, fighter, captured_at) and the fight's start, carrying no
-- observation of their own. Rewriting one loses nothing, which is exactly why
-- they are safe to leave mutable and why CLV-001 does not read either of them.
-- ============================================================================

begin;

create or replace function public.fight_odds_protect_observation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  -- The ONLY fields an UPDATE may move. Everything else — price, implied
  -- probability, book, fighter, capture instant, and every §4 provenance column
  -- (source_event_id, feed_version, opponent_fighter_id, provider_last_update,
  -- retrieved_at, market_status, raw, source_commence_at, bout_started_at,
  -- proxy_cutoff_at, is_live) — is the observation itself and is frozen.
  mutable_keys constant text[] := array['is_opener', 'is_closer'];
  before_j jsonb;
  after_j  jsonb;
  changed  text;
begin
  if tg_op = 'DELETE' then
    raise exception
      'fight_odds is append-only for CLV-001 (R-01): DELETE on id % rejected. '
      'A quote that turns out to be garbage is excluded at scoring time by a '
      'written rule, never deleted.', old.id;
  end if;

  if tg_op = 'TRUNCATE' then
    raise exception
      'fight_odds is append-only for CLV-001 (R-01): TRUNCATE rejected.';
  end if;

  before_j := to_jsonb(old) - mutable_keys;
  after_j  := to_jsonb(new) - mutable_keys;

  if before_j is distinct from after_j then
    select string_agg(k, ', ' order by k) into changed
      from jsonb_object_keys(before_j) k
     where before_j -> k is distinct from after_j -> k;
    raise exception
      'fight_odds observation fields are immutable (CLV-001 R-01): UPDATE on '
      'id % would change %. Only % may be maintained. clv_source_quote_ids '
      'points at these rows as evidence; evidence that can be rewritten '
      'afterwards is not evidence.',
      old.id, changed, array_to_string(mutable_keys, ', ');
  end if;

  return new;
end $$;

comment on function public.fight_odds_protect_observation() is
  'CLV-001 R-01. Rejects DELETE and TRUNCATE outright, and rejects any UPDATE '
  'that changes a field other than the derived flags is_opener / is_closer. '
  'Whitelist by construction: a column added later is protected as soon as it '
  'exists, because the comparison is over to_jsonb(row) minus the mutable keys.';

-- drop-then-create is the idempotent recreate idiom, not a weakening: the
-- function above is already replaced in place, and these two statements only
-- ensure the triggers point at it exactly once. Re-running the file is a no-op.
drop trigger if exists fight_odds_block_delete on public.fight_odds;
create trigger fight_odds_block_delete
  before delete on public.fight_odds
  for each row execute function public.fight_odds_protect_observation();

drop trigger if exists fight_odds_protect_update on public.fight_odds;
create trigger fight_odds_protect_update
  before update on public.fight_odds
  for each row execute function public.fight_odds_protect_observation();

drop trigger if exists fight_odds_block_truncate on public.fight_odds;
create trigger fight_odds_block_truncate
  before truncate on public.fight_odds
  for each statement execute function public.fight_odds_protect_observation();

commit;

-- ============================================================================
-- AFTER APPLYING — what must still be true
--
--   * every one of the 110,032 existing rows is byte-identical. This migration
--     reads nothing and writes nothing; it only constrains what happens next.
--   * build/fetch-odds.js's closer promotion still works unchanged. It sets and
--     clears `is_closer` and touches nothing else — verified by reading it, and
--     pinned by a test in build/test-fetch-odds.js so a future edit that starts
--     writing another column fails the suite rather than the cron.
--   * export_data.py, factor-rates.js, v_fight_odds_consensus and the frontend
--     pages read unchanged. Nothing here affects SELECT.
--   * an attempt to correct a captured price now FAILS LOUDLY instead of
--     succeeding quietly. That is the point. If a price is genuinely wrong, the
--     remedy is a written exclusion rule at scoring time (R-01), or a new
--     observation row — never an edit to the old one.
--
-- WHAT TO CHECK BEFORE APPLYING
--
--   Any other writer to fight_odds must be inventoried first. As of this file
--   the repo contains exactly one UPDATE path (build/fetch-odds.js, is_closer)
--   and the scrapers INSERT only. A writer outside this repo that updates a
--   protected column will start erroring the moment this lands — which is the
--   intended behaviour, and is still worth knowing about in advance rather than
--   at 23:00 UTC on a card night.
-- ============================================================================
