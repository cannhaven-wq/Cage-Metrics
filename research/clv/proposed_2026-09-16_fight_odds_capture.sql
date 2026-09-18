-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- Capture columns on `fight_odds`, so the moneyline market records what the
-- totals market already records.
--
-- STATUS: draft. Apply this one FIRST — before
-- proposed_2026-09-16_clv001_columns.sql — and only once the capture path has
-- been verified against it. It changes what gets STORED; the other migration
-- changes where a computed RESULT is stored, and there is nothing to compute
-- until this one has been collecting.
--
-- Filed under research/clv/ rather than the repo root so the "apply root *.sql"
-- habit cannot pick it up by accident.
--
-- ADDITIVE ONLY. This migration contains, and must always contain:
--   * no DROP of any kind
--   * no DELETE
--   * no destructive or back-filling UPDATE
--   * no trigger created, altered, weakened or removed
--   * no reinterpretation of an existing row or column
--
-- Every statement is ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, or a
-- DO block that checks pg_constraint before adding a named constraint, so the
-- whole file is genuinely idempotent and re-runnable. (A bare ADD CONSTRAINT is
-- not: it errors on the second run.) Every new column is NULLable with no
-- default, so all 110,032 existing rows are untouched and read exactly as they
-- did before: NULL means "this row predates the column", which is true, and is
-- the only honest thing it could mean.
--
-- WHY THIS SHAPE
-- --------------
-- These are not new ideas. `prop_odds` — the totals ledger DUR-001 shipped in
-- dur001_migration.sql — already carries source_event_id, source_commence_at,
-- is_live and raw, and has been populating them since 2026-09-14. The moneyline
-- table is the one that does not, which is why CLV-001's capture requirements
-- read as missing when the mechanism was sitting in the next table over.
--
-- So the column names here are COPIED, not invented. A reader who understands
-- prop_odds understands this, and a query that joins the two does not have to
-- translate. Where a name differs from prop_odds it is because the concept is
-- genuinely new (retrieved_at, provider_last_update, opponent_fighter_id).
--
-- Mapping to CLV-001 §4, the capture requirements that cannot be backfilled:
--   item  9  provider market IDs                -> source_event_id
--   item  7  scheduled AND actual bout timing   -> source_commence_at (card),
--                                                  bout_started_at (confirmed bell),
--                                                  proxy_cutoff_at (frozen cutoff)
--   item 11  provider AND retrieval timestamps  -> provider_last_update + retrieved_at
--   item 10  opponent identity at quote time    -> opponent_fighter_id
--   item  8  market suspension / takedown       -> market_status
--   item  6  provider and feed version          -> feed_version
--   item 12  immutable link to the source quote -> raw
--
-- The actual-bell audit field stays where it is: `fights.bell_at`, reserved for
-- a confirmed bell and never written by the odds job. bout_started_at is the
-- capture-time BELIEF about when this fight began; bell_at is the record of when
-- it did. They are kept apart so a later correction to one never silently
-- rewrites the other, and so the close a quote was judged against at capture
-- stays recoverable.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- 1. Provider identity — §4 items 9 and 6
-- ---------------------------------------------------------------------------

-- The provider's own id for the market this quote came from (Odds API event id).
-- Q-10 resolves reschedules and opponent changes by matching on fighter identity
-- AND provider market id. Without this, only half of that match is enforceable:
-- a rematch between the same two fighters is indistinguishable from the original
-- booking, and a reposted market cannot be told from the market it replaced.
alter table public.fight_odds
  add column if not exists source_event_id text;

-- Which feed and which shape produced the row. A provider changing its response
-- format can shift timings without changing any price, and that has to be
-- detectable after the fact rather than inferred from a gap in the data.
alter table public.fight_odds
  add column if not exists feed_version text;

-- ---------------------------------------------------------------------------
-- 2. Time — §4 items 7 and 11
-- ---------------------------------------------------------------------------

-- The provider's scheduled start for this fight AS SEEN AT CAPTURE. Immutable
-- per row, exactly like prop_odds.source_commence_at: it is what we believed the
-- schedule to be at that instant, which is the only version of the schedule that
-- can explain a capture decision made then.
--
-- NOT a cutoff. From v1.0.8 onward there are exactly two cutoff bases — the
-- card's scheduled start for bout 1 and the previous bout's exact completion for
-- bouts 2..N — and they
-- are resolved by v_clv_close_reference, not from this column. A confirmed bell
-- is audit-only and supplies neither (Amendment 5.1). The card's scheduled start
-- applied to a LATER bout is hours early and is reported, never scored
-- (Amendment 4.1).
--
-- CLV-001 reads this column as provenance: what the schedule looked like when
-- the quote was taken. The cutoff the quote was judged against is
-- proxy_cutoff_at, below, under its own name.
alter table public.fight_odds
  add column if not exists source_commence_at timestamptz;

-- WHEN THIS FIGHT ACTUALLY BEGAN — a fact, or NULL. Only a confirmed bell fills
-- it. NULL means "we do not know", which is not the same as "it had not
-- started".
--
-- Amendment 5.1. It briefly fell back to the previous bout's completion, which
-- asserted that fight N+1 began the instant fight N ended. It did not — the
-- walkout sits between them — and this column's only job is to hold facts. The
-- operational cutoff lives in proxy_cutoff_at below, under its own name.
alter table public.fight_odds
  add column if not exists bout_started_at timestamptz;

-- THE FROZEN OPERATIONAL CUTOFF for this fight, as it stood at capture:
--   bout 1     the card's scheduled start
--   bout 2..N  the exact completion of the immediately previous bout
--
-- A cutoff, not a start. For later bouts it precedes the bell by the walkout
-- interval, which is precisely why it is not stored as bout_started_at. CLV
-- scoring excludes quotes at or after it directly; nothing infers a start from
-- it. See CLV-001 Amendment 5 as corrected by 5.1.
alter table public.fight_odds
  add column if not exists proxy_cutoff_at timestamptz;

-- True when the quote was captured at or after THIS FIGHT actually started — an
-- in-play price. NULL means we do not know, and that is a third state, not a
-- synonym for false.
--
-- Keyed to bout_started_at, which only a confirmed bell fills, so this is a
-- claim about what happened and never an inference from the cutoff. CLV scoring
-- does not read it: it excludes quotes at or after proxy_cutoff_at directly,
-- rather than manufacturing a liveness fact to achieve the same exclusion.
alter table public.fight_odds
  add column if not exists is_live boolean;

-- The book's own last-update instant, as the provider reports it. Distinct from
-- captured_at, which is when WE looked. Collapsing the two hides feed lag, and
-- feed lag is precisely what a staleness limit measures — a price we retrieved
-- 5 minutes before the bell that the book last moved 4 hours earlier is a stale
-- price wearing a fresh timestamp.
alter table public.fight_odds
  add column if not exists provider_last_update timestamptz;

-- When our capture process retrieved the payload. captured_at is retained
-- unchanged as the row's canonical instant and every existing consumer keeps
-- reading it; this records the retrieval separately so the two can diverge
-- legibly (a batch written from a payload fetched minutes earlier, say).
alter table public.fight_odds
  add column if not exists retrieved_at timestamptz;

-- ---------------------------------------------------------------------------
-- 3. What the quote referred to — §4 items 10 and 8
-- ---------------------------------------------------------------------------

-- The other corner, as the market named it at quote time. A late opponent change
-- silently redefines what a price meant, and after the fact the row looks
-- identical either way. Q-10 excludes a fight whose corners changed after the
-- forecast lock; this is what makes that mechanical instead of a guess.
alter table public.fight_odds
  add column if not exists opponent_fighter_id bigint;

-- 'open' | 'suspended' | 'taken_down', as the provider reported it. A market
-- removed before the bell is a different object from one still quoting, and the
-- difference is invisible afterwards: both leave a last-quote row and nothing
-- else. NULL means the provider said nothing, which is not the same as 'open'.
alter table public.fight_odds
  add column if not exists market_status text;

-- ---------------------------------------------------------------------------
-- 4. Provenance — §4 item 12
-- ---------------------------------------------------------------------------

-- The provider metadata for this quote as received: bookmaker key, the market's
-- and bookmaker's last_update, the provider's own team labels. Mirrors
-- prop_odds.raw. This is the immutable link from a stored price back to the
-- exact thing the provider said, which is what makes the publish side of
-- CLV_return a record rather than an assertion.
alter table public.fight_odds
  add column if not exists raw jsonb;

-- ---------------------------------------------------------------------------
-- 5. Constraints and indexes — additive, and they fail closed
--
-- NOT VALID so the 110,032 existing rows are never touched or re-validated.
-- New and updated rows are checked; history stays exactly as it is.
-- ---------------------------------------------------------------------------

-- Closed vocabulary. An open status column becomes free-form and stops
-- aggregating, the same argument as the CLV unscored-reason vocabulary.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'fight_odds_market_status_known'
                    and conrelid = 'public.fight_odds'::regclass) then
    alter table public.fight_odds add constraint fight_odds_market_status_known
      check (market_status is null or market_status in
             ('open', 'suspended', 'taken_down')) not valid;
  end if;
end $$;

-- is_live must agree with the bout start it summarises. A row claiming to be
-- pre-start while carrying a capture instant at or after that fight began is not
-- a disagreement to resolve later — it is a bug, and it would present an in-play
-- price as a close.
--
-- Against bout_started_at (a confirmed bell), never against source_commence_at
-- and never against proxy_cutoff_at.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'fight_odds_is_live_agrees_with_bout_start'
                    and conrelid = 'public.fight_odds'::regclass) then
    alter table public.fight_odds add constraint fight_odds_is_live_agrees_with_bout_start
      check (is_live is null or bout_started_at is null
             or (is_live = (captured_at >= bout_started_at))) not valid;
  end if;
end $$;

-- is_live is only knowable when a bout start is. A row asserting liveness with
-- no bout start on it is asserting something it cannot know.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'fight_odds_is_live_needs_a_bout_start'
                    and conrelid = 'public.fight_odds'::regclass) then
    alter table public.fight_odds add constraint fight_odds_is_live_needs_a_bout_start
      check (is_live is null or bout_started_at is not null) not valid;
  end if;
end $$;

-- The opponent is the other corner, never the same fighter.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'fight_odds_opponent_is_not_self'
                    and conrelid = 'public.fight_odds'::regclass) then
    alter table public.fight_odds add constraint fight_odds_opponent_is_not_self
      check (opponent_fighter_id is null or opponent_fighter_id <> fighter_id)
      not valid;
  end if;
end $$;

-- Q-10's mechanical match: (fight, provider market) lookups, newest first.
create index if not exists fight_odds_source_event_idx
  on public.fight_odds (fight_id, source_event_id, captured_at desc)
  where source_event_id is not null;

-- The scheduled-close proxy scan: pre-start quotes for a fight, newest first.
create index if not exists fight_odds_pre_start_idx
  on public.fight_odds (fight_id, captured_at desc)
  where is_live is not true;

comment on column public.fight_odds.source_event_id is
  'Provider market id (Odds API event id) as seen at capture. The stable key '
  'across a repost or a rematch, and the second half of Q-10''s mechanical match.';

comment on column public.fight_odds.source_commence_at is
  'Provider scheduled start AS SEEN AT CAPTURE. Immutable per row, and NOT a '
  'cutoff. CLV-001 from v1.0.8 onward has exactly two cutoff bases - the card''s scheduled '
  'start for bout 1, the previous bout''s exact completion for bouts 2..N - '
  'resolved by v_clv_close_reference. A confirmed bell supplies neither '
  '(Amendment 5.1). The cutoff a quote was judged against is proxy_cutoff_at.';

comment on column public.fight_odds.retrieved_at is
  'When we retrieved the payload, as distinct from captured_at (the row''s '
  'canonical instant) and provider_last_update (when the book last moved). '
  'Kept separate because collapsing them hides feed lag.';

comment on column public.fight_odds.provider_last_update is
  'When the BOOK last moved this price, as the provider reports it. Required '
  'provenance (CLV-001 §4 item 11) and deliberately NOT the staleness clock: '
  'the frozen 45-minute limit was derived from CFL''s own observation cadence '
  'and is measured from captured_at. Re-pointing it here would silently '
  'redefine the rule, and is a methodological amendment rather than an '
  'implementation choice.';

comment on column public.fight_odds.captured_at is
  'The row''s canonical observation instant - when WE looked. CLV-001 measures '
  'its frozen 45-minute staleness limit from this column, orders quotes by it, '
  'and applies R-13 to it (a pre-2026-05-22 or epoch value is not a credible '
  'capture instant). Immutable once written.';

commit;

-- ============================================================================
-- AFTER APPLYING — what must still be true
--
--   * every one of the 110,032 pre-existing rows is byte-identical, with NULL
--     in each new column. Nothing was backfilled, and nothing should be: a
--     commence time reconstructed today is not what we believed at capture.
--   * captured_at still means what it always meant, and every existing consumer
--     (v_fight_odds_consensus, the parlay/event/index pages, export_data.py,
--     factor-rates.js) reads unchanged.
--   * no CLV result is computable yet. This migration makes the INPUTS
--     recordable. proposed_2026-09-16_clv001_columns.sql, which stores the
--     output, still waits — and behind it the publication gate, at 0 of 100
--     observations and 0 of 20 events.
--   * the first card captured after this lands is the first that can ever be
--     scored. Everything before it stays permanently unscorable, which is a
--     coverage fact to report under R-05, not a gap to backfill.
-- ============================================================================
