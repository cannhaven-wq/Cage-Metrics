-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- DUR-001 amendment draft item (j), 2026-09-15.
-- See cfl_engine/dur001/AMENDMENT_DRAFT_2026-09-15.md.
--
-- STATUS: draft. Needs Reed's approval before it is applied, and it must not be
-- applied before the DUR-001 amendment covering item (j) is accepted. This file
-- deliberately lives under cfl_engine/dur001/ rather than the repo root so that
-- the "apply *.sql in repo root" habit does not pick it up by accident.
--
-- WHAT IT DOES
--   1. Exposes market_last_update as a derived column on v_prop_odds_lifecycle.
--      The Odds API already returns it and build/fetch-odds.js already stores it
--      inside prop_odds.raw; nothing reads it today.
--   2. Tightens the "closer" definition so a quote only counts as a pre-fight
--      close when the BOOK's own last-update timestamp is also strictly before
--      the fight's start — not merely our capture time.
--
-- WHY IT MATTERS
--   captured_at answers "when did we write this row". market_last_update
--   answers "when did the book last move this price". Only the second one tells
--   you the price was pre-fight. Without this, a row captured at T-2min can
--   carry a price the book stamped after the bell and still be graded a closer.
--
-- READ-ONLY IMPACT: this migration creates/replaces views only. It writes no
-- rows, drops no tables, and touches neither prop_model_locks nor prop_odds.
--
-- ROLLBACK: re-run the previous definitions of the two views from
-- dur001_migration.sql.
--
-- RLS NOTE (per CLAUDE.md): both views must grant SELECT TO anon, authenticated
-- if they are ever read from the frontend. They are research surfaces and are
-- not read by the site today, so no grant is added here. If that changes, add
-- the grant to BOTH roles — an anon-only policy makes signed-in users see empty
-- results with HTTP 200 and no error.
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. v_prop_odds_lifecycle — add market_last_update + a pre-fight flag
--
-- Unchanged from the current definition except for the three new columns at the
-- end and the tightened is_closer_calc. Everything else is carried over
-- verbatim so a diff against the live definition shows only the intended delta.
-- ----------------------------------------------------------------------------
create or replace view public.v_prop_odds_lifecycle as
select
  d.id,
  d.fight_id,
  d.event_id,
  d.event_date,
  d.market_type,
  d.fighter_id,
  d.line,
  d.over_odds,
  d.under_odds,
  d.book_id,
  d.source,
  d.source_event_id,
  d.captured_at,
  d.is_opener,
  d.is_closer,
  d.over_prob_raw,
  d.under_prob_raw,
  d.overround,
  d.over_prob_vigfree,
  d.under_prob_vigfree,
  f.bell_at,

  -- NEW: the book's own last-update stamp, lifted out of the raw payload.
  -- nullif guards the empty string; the ::timestamptz cast is safe because the
  -- Odds API emits RFC3339 ("2026-09-15T02:04:06Z").
  nullif(p.raw ->> 'market_last_update', '')::timestamptz as market_last_update,

  -- NEW: same, for the bookmaker-level stamp. Kept separate because the two can
  -- differ when a book updates one market and not another.
  nullif(p.raw ->> 'bookmaker_last_update', '')::timestamptz as bookmaker_last_update,

  -- NEW: is this quote pre-fight by the BOOK's clock, not just ours?
  -- null (unknown market_last_update) is treated as NOT pre-fight, so a missing
  -- stamp can never silently qualify a row as a closer.
  (
    s.start_at is not null
    and nullif(p.raw ->> 'market_last_update', '')::timestamptz is not null
    and nullif(p.raw ->> 'market_last_update', '')::timestamptz < s.start_at
  ) as market_is_prefight,

  d.captured_at = min(d.captured_at) over (
    partition by d.fight_id, d.market_type,
                 (coalesce(d.fighter_id, 0::bigint)),
                 (coalesce(d.line, '-1'::numeric)), d.book_id
  ) as is_opener_calc,

  -- TIGHTENED: a closer must now satisfy BOTH clocks.
  -- Previously: not live AND captured_at < start_at AND captured_at is the max
  -- such capture. Now the same, plus market_last_update < start_at, with the
  -- max taken over only the rows that pass the new filter.
  (
    s.start_at is not null
    and not p.is_live
    and d.captured_at < s.start_at
    and nullif(p.raw ->> 'market_last_update', '')::timestamptz is not null
    and nullif(p.raw ->> 'market_last_update', '')::timestamptz < s.start_at
    and d.captured_at = max(d.captured_at) filter (
          where not p.is_live
            and d.captured_at < s.start_at
            and nullif(p.raw ->> 'market_last_update', '')::timestamptz is not null
            and nullif(p.raw ->> 'market_last_update', '')::timestamptz < s.start_at
        ) over (
          partition by d.fight_id, d.market_type,
                       (coalesce(d.fighter_id, 0::bigint)),
                       (coalesce(d.line, '-1'::numeric)), d.book_id
        )
  ) as is_closer_calc,

  s.start_at,
  s.start_basis,
  p.source_commence_at,
  p.is_live,
  s.start_at - d.captured_at as lead_time,

  -- NEW: how stale was the price when we captured it? Positive = the book had
  -- not moved it since before our capture. Useful for spotting a dead feed that
  -- keeps returning the same quote.
  d.captured_at - nullif(p.raw ->> 'market_last_update', '')::timestamptz
    as capture_lag

from v_prop_odds_devig d
  join prop_odds p on p.id = d.id
  join fights    f on f.id = d.fight_id
  left join v_fight_start_best s on s.fight_id = d.fight_id;

comment on view public.v_prop_odds_lifecycle is
  'Per-quote lifecycle for prop odds. market_last_update is the book''s own '
  'last-move stamp, derived from prop_odds.raw. is_closer_calc requires the '
  'quote to be pre-fight on BOTH our capture clock and the book''s clock '
  '(DUR-001 amendment item (j), 2026-09-15).';

-- ----------------------------------------------------------------------------
-- 2. Coverage check — run BEFORE deciding to apply this.
--
-- If market_last_update is missing on a large share of rows, this migration
-- would silently shrink the eligible closing sample rather than clean it. Run
-- this first and look at the numbers. Do not apply if n_missing_mlu is a
-- meaningful fraction of n_total without understanding why.
--
--   select
--     count(*)                                                as n_total,
--     count(*) filter (where raw ->> 'market_last_update' is null)
--                                                             as n_missing_mlu,
--     min(nullif(raw ->> 'market_last_update','')::timestamptz) as earliest_mlu,
--     max(nullif(raw ->> 'market_last_update','')::timestamptz) as latest_mlu
--   from prop_odds;
--
-- And the before/after closer count:
--
--   select count(*) filter (where is_closer_calc) as closers_after
--   from v_prop_odds_lifecycle;
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- 3. v_prop_odds_closing_consensus is NOT redefined here.
--
-- It consumes is_closer_calc from the view above, so it inherits the tightened
-- rule automatically. Amendment item (a) (>= 2 books) would change it, and that
-- belongs in its own migration once (a) is approved — keeping one amendment
-- item per migration so either can be reverted alone.
-- ----------------------------------------------------------------------------

commit;
