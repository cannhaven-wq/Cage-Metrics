-- ============================================================================
-- PROPOSED — NOT APPLIED
--
-- One read-only function so cfl_engine/integrity/run_audit.py can ask Postgres
-- for a single count. PostgREST cannot run arbitrary SQL, and the alternative —
-- pulling 110,000 odds rows over the wire to count them in Python — is slower,
-- costlier and no safer.
--
-- Filed under cfl_engine/integrity/ rather than the repo root so the
-- "apply root *.sql" habit cannot pick it up by accident.
--
-- It is locked down three ways:
--   * SECURITY INVOKER — it gets the caller's privileges, never the owner's;
--   * the transaction is READ ONLY, so a write raises inside the function
--     regardless of what was passed in;
--   * the query text must begin with `select` and must return exactly one
--     integer, so a statement that does anything else fails.
--
-- Execute is granted to service_role only. anon and authenticated cannot call
-- it at all, which is the point: this exists for an audit script, not for the
-- website.
-- ============================================================================

begin;

create or replace function public.cfl_integrity_count(q text)
returns bigint
language plpgsql
security invoker
as $$
declare
  result bigint;
  trimmed text := btrim(q);
begin
  if lower(left(trimmed, 6)) <> 'select' then
    raise exception 'cfl_integrity_count only runs SELECT, got: %', left(trimmed, 40);
  end if;
  if trimmed like '%;%' then
    raise exception 'cfl_integrity_count takes one statement, no semicolons';
  end if;

  -- Belt and braces: even a SELECT that calls a writing function fails here.
  set local transaction read only = on;

  execute format('select n from (%s) integrity_check_q', trimmed) into result;
  return result;
end;
$$;

comment on function public.cfl_integrity_count(text) is
  'Read-only single-count helper for cfl_engine/integrity/run_audit.py. '
  'SECURITY INVOKER, read-only transaction, SELECT-only, one statement, must '
  'return a column named n. service_role only.';

revoke all on function public.cfl_integrity_count(text) from public, anon, authenticated;
grant execute on function public.cfl_integrity_count(text) to service_role;

commit;
