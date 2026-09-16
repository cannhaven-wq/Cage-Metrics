-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- CLV-001 storage for model_edges.
-- See research/clv/CLV_MEASUREMENT_PROTOCOL.md (frozen 2026-09-16T10:30:00Z).
--
-- STATUS: draft. Reed approves application, and only after the dry-run report
-- has been reviewed. Filed under research/clv/ rather than the repo root so the
-- "apply root *.sql" habit cannot pick it up by accident.
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
-- not: it errors on the second run. That was claimed here before it was true.)
--
-- THE LEGACY COLUMNS ARE NOT TOUCHED. closing_odds / clv_pp / clv_beat and their
-- _pm siblings were computed under the pre-CLV-001 convention (raw single-side
-- implied-probability movement, vigged both ends). They stay exactly as they
-- are, keep their meaning, and stay historically identifiable. CLV-001 lands in
-- NEW columns beside them. Nothing is migrated, recomputed or reinterpreted.
--
-- RLS NOTE (per CLAUDE.md): model_edges is not read by the frontend and no
-- grant is added. If that ever changes, grant SELECT TO anon, authenticated —
-- an anon-only policy makes signed-in users see empty results with HTTP 200.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- 1. The frozen measure and its inputs
-- ---------------------------------------------------------------------------

-- CLV_return = closing_fair_probability * decimal_odds_at_publish - 1
-- Expected return per unit staked at the posted price, against the de-vigged
-- close. Null means UNSCORED, never zero — see clv_unscored_reason.
alter table public.model_edges
  add column if not exists clv_return numeric;

-- The de-vigged closing fair probability of the BET SIDE. Power method
-- (DUR-001 Amendment 1.1 as corrected by Amendment 2), de-vigged per book and
-- then median-ed across books — that order, which is not interchangeable.
alter table public.model_edges
  add column if not exists closing_fair_probability numeric;

-- How many eligible two-sided books survived de-vig and entered the median.
-- The frozen minimum is 3 (Q-02). Stored so a later reader can see how thin the
-- consensus was without re-deriving it.
alter table public.model_edges
  add column if not exists closing_book_count integer;

-- Exact protocol version that produced the row, e.g. 'CLV-001@1.0.6'. A row
-- whose version does not match the currently frozen protocol is not comparable
-- with one that does, and the writer refuses to mix them.
alter table public.model_edges
  add column if not exists clv_protocol_version text;

-- When the CLV-001 measure was computed. Distinct from settled_at, which marks
-- the legacy settlement.
alter table public.model_edges
  add column if not exists clv_scored_at timestamptz;

-- Why this row has no CLV_return. NULL iff clv_return is not null.
-- Vocabulary is closed and enforced below.
alter table public.model_edges
  add column if not exists clv_unscored_reason text;

-- ---------------------------------------------------------------------------
-- 1b. How late the proxy actually was — Amendments 4 and 5
--
-- The benchmark is the CFL CLOSING-PRICE PROXY, never the exact sportsbook
-- closing line. These columns are what make that claim checkable per row rather
-- than asserted once in a document — and under Amendment 5 they are also what
-- records, honestly, that a bout-2..N cutoff precedes the bell.
-- ---------------------------------------------------------------------------

-- Which instant was the CUTOFF for this fight: 'scheduled_first_bout' (bout 1),
-- 'previous_bout_completion' (bouts 2..N), or 'bell_at' where a confirmed bell
-- exists. Amendment 5.
alter table public.model_edges
  add column if not exists clv_close_basis text;

-- When the bout before this one ended. For bouts 2..N under Amendment 5 this is
-- the same instant as the cutoff; it is stored separately so a future protocol
-- version with real bell times can still see where the window opened, and so a
-- confirmed bell can be checked against it.
alter table public.model_edges
  add column if not exists clv_window_opened_at timestamptz;

-- Minutes from the selected quote to the CUTOFF. Exact, always. Under a
-- five-minute capture cadence this should read in single digits; a large value
-- is a coverage problem that must be visible rather than averaged away.
alter table public.model_edges
  add column if not exists clv_lead_time_minutes numeric;

-- TRUE when the CUTOFF precedes the bell — the 'previous_bout_completion' case
-- under Amendment 5. The lead time above is then the exact gap to the cutoff and
-- a LOWER BOUND on the gap to the fight actually starting. FALSE when the cutoff
-- is the start itself. NULL when the basis is unknown; never FALSE by default,
-- because FALSE asserts the cutoff was the start.
alter table public.model_edges
  add column if not exists clv_lead_time_is_lower_bound boolean;

-- The exact capture instant of the latest quote that entered the consensus —
-- the "late" in late pre-fight closing-price proxy. Stored so the lead time can
-- be recomputed under a future protocol version without reinterpreting this one.
alter table public.model_edges
  add column if not exists clv_proxy_quoted_at timestamptz;

-- ---------------------------------------------------------------------------
-- 2. Provenance — enough to reconstruct the calculation from the raw quotes
--
-- Reed: "store enough provenance to reconstruct the calculation — ideally the
-- closing consensus/source artifact or a deterministic reference to the raw
-- quotes used."
--
-- Both are stored. The id array is the deterministic reference; the jsonb
-- artifact is the consensus as computed, so a reconstruction can be checked
-- without re-querying rows that may since have been added to the same fight.
-- ---------------------------------------------------------------------------

-- Every fight_odds.id that entered the closing consensus, both sides, ordered.
-- This is the deterministic reference: re-reading exactly these rows must
-- reproduce closing_fair_probability bit for bit.
alter table public.model_edges
  add column if not exists clv_source_quote_ids bigint[];

-- The consensus as computed: per book, the two raw implied probabilities, the
-- de-vigged fair probability and the solved exponent k, plus the resulting
-- median. Shape:
--   {"books":[{"book_id":1,"q_bet":0.55,"q_opp":0.52,
--              "fair_bet":0.5155,"k":0.9023,
--              "quote_ids":[123,124]}, ...],
--    "median_fair_bet":0.5155,"n_books":3,
--    "devig":"power","protocol":"CLV-001@<version>"}
alter table public.model_edges
  add column if not exists clv_closing_consensus jsonb;

-- sha256 of the canonical serialisation of clv_closing_consensus, so a stored
-- artifact that is later edited is detectable. The table has no append-only
-- trigger — adding one would not be additive, so integrity is by hash instead.
alter table public.model_edges
  add column if not exists clv_consensus_sha256 text;

-- ---------------------------------------------------------------------------
-- 3. Constraints — additive, and they fail closed
--
-- NOT VALID so existing rows are never touched or re-validated. New and updated
-- rows are checked; the historical rows stay exactly as they are. Validating
-- them later is a separate, deliberate decision.
-- ---------------------------------------------------------------------------

-- A row is either scored or it names why not. Never both, never neither.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_scored_xor_reason'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_scored_xor_reason
      check (
        (clv_return is not null and clv_unscored_reason is null)
        or (clv_return is null)
      ) not valid;
  end if;
end $$;

-- A scored row carries its whole provenance. Partial provenance is worse than
-- none: it looks reconstructible and is not.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_scored_is_complete'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_scored_is_complete
      check (
        clv_return is null
        or (closing_fair_probability is not null
            and closing_book_count is not null
            and clv_protocol_version is not null
            and clv_scored_at is not null
            and clv_source_quote_ids is not null
            and clv_closing_consensus is not null
            and clv_consensus_sha256 is not null
            -- Amendment 4: a scored row states how late its proxy was and whether
            -- that is exact. A figure without them cannot be read honestly.
            and clv_close_basis is not null
            and clv_lead_time_minutes is not null
            and clv_lead_time_is_lower_bound is not null
            and clv_proxy_quoted_at is not null)
      ) not valid;
  end if;
end $$;

-- The close basis vocabulary for a SCORED row, matching CLOSE_REFERENCE_BASES
-- in cfl_engine/clv/scoring.py (Amendment 5).
--
-- 'card_scheduled_start' is deliberately absent: applied to a later bout it sits
-- hours early, so the proxy would mean something different on every fight of the
-- card (Amendment 4.1). It remains reportable as a reference_basis in
-- v_clv_close_reference and can never reach a scored row.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_close_basis_known'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_close_basis_known
      check (clv_close_basis is null or clv_close_basis in (
        'bell_at',
        'scheduled_first_bout',
        'previous_bout_completion'
      )) not valid;
  end if;
end $$;

-- The lower-bound flag must agree with the basis: TRUE exactly when the cutoff
-- was the previous bout's completion, which precedes the bell. If these ever
-- disagree, one of them is lying about how late the price was.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_lower_bound_matches_basis'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_lower_bound_matches_basis
      check (clv_close_basis is null or clv_lead_time_is_lower_bound is null
             or (clv_lead_time_is_lower_bound
                 = (clv_close_basis = 'previous_bout_completion'))) not valid;
  end if;
end $$;

-- The proxy quote is strictly before the fight; a negative lead time would mean
-- an in-play price scored as a close.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_lead_time_positive'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_lead_time_positive
      check (clv_lead_time_minutes is null or clv_lead_time_minutes > 0) not valid;
  end if;
end $$;

-- No ordering constraint between clv_window_opened_at and clv_proxy_quoted_at.
-- Under Amendment 5 the window's opening instant IS the cutoff for bouts 2..N,
-- and the selected quote is strictly BEFORE the cutoff — so the quote precedes
-- the "opening", and an ordering check either way would be wrong for one of the
-- two bases. `model_edges_clv_lead_time_positive` already encodes the only
-- ordering that matters: the quote came before the cutoff.

-- The frozen minimum book count (Q-02). A scored row below it is impossible.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_min_books'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_min_books
      check (clv_return is null or closing_book_count >= 3) not valid;
  end if;
end $$;

-- A probability is a probability.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_fair_prob_range'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_fair_prob_range
      check (closing_fair_probability is null
             or (closing_fair_probability > 0 and closing_fair_probability < 1)) not valid;
  end if;
end $$;

-- Closed vocabulary for the unscored reason. An open text field becomes a
-- free-form excuse column, and the counts stop aggregating.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'model_edges_clv_unscored_reason_known'
                    and conrelid = 'public.model_edges'::regclass) then
    alter table public.model_edges add constraint model_edges_clv_unscored_reason_known
      check (clv_unscored_reason is null or clv_unscored_reason in (
        -- global preconditions: these disqualify every row at once
        'schema_incomplete',            -- CLV-001 columns absent; nothing written
        'protocol_version_mismatch',    -- row written under a different frozen version
        'eligible_book_list_not_frozen', -- Q-02's named list is absent from protocol.json
        -- per-row
        'no_publish_price',             -- odds_at_publish missing
        'bet_fighter_not_in_fight',     -- Q-10; opponent change, rematch or reschedule
        'no_scheduled_start',           -- Q-01 has no reference instant to measure to
        'no_closing_quotes',            -- nothing on file from an eligible book
        'implausible_timestamp',        -- R-13; epoch-era import, permanently unscorable
        'stale_close',                  -- outside the 45-minute staleness limit
        'one_sided_close',              -- only one corner quoted at close
        'non_market_price',             -- R-03 band violation on every book
        'devig_failed',                 -- no root in the frozen bracket
        'insufficient_books',           -- fewer than 3 eligible two-sided books
        'forecast_not_before_close',    -- R-07; no-lookahead violated
        -- Amendment 4.1: we hold a verifiably pre-fight price, but the only cutoff
        -- we can verify is the card's scheduled start, which on a later bout is
        -- hours early. Safely pre-fight is not LATE. Distinct from
        -- no_scheduled_start, which means we hold nothing at all — two different
        -- problems with two different fixes.
        'only_pre_card_price',
        -- Amendment 5: this is not the card's first bout, so the cutoff is the
        -- exact completion of the bout before it — and no such completion is
        -- recorded. Recording one makes the already-captured snapshots scorable,
        -- which is why bout completions are the highest-leverage open item.
        'no_previous_bout_completion'
      )) not valid;
  end if;
end $$;

-- This list and UNSCORED_REASONS in cfl_engine/clv/scoring.py must stay
-- identical. tests/../test_scoring.py asserts it against this file, so a reason
-- added on one side and not the other fails the suite rather than the INSERT.

-- ---------------------------------------------------------------------------
-- 4. Indexes for the eligibility counters the publication gate reads
-- ---------------------------------------------------------------------------

create index if not exists model_edges_clv_scored_idx
  on public.model_edges (clv_scored_at) where clv_return is not null;

create index if not exists model_edges_clv_unscored_idx
  on public.model_edges (clv_unscored_reason) where clv_unscored_reason is not null;

comment on column public.model_edges.clv_return is
  'CLV-001 primary measure: closing_fair_probability * decimal_odds_at_publish - 1. '
  'NULL means unscored (see clv_unscored_reason), never zero. Zero means exactly '
  'fair closing value after paying the posted price.';

comment on column public.model_edges.clv_pp is
  'LEGACY, pre-CLV-001: raw single-side implied-probability movement, vigged both '
  'ends. Retained unchanged and historically identifiable. Not the headline '
  'measure and never labelled CLV on a surface.';

commit;

-- ============================================================================
-- AFTER APPLYING — what must still be true
--
--   * publication remains blocked. This migration stores a number; it does not
--     publish one. The gate is 100 scored observations across 20 distinct
--     events with the cluster interval excluding zero, and it is at 0.
--   * legacy clv_pp / clv_beat values are byte-identical to before.
--   * no row acquired a clv_return as a side effect of the migration itself —
--     every new column starts NULL and only settle_clv.py in write mode fills it.
-- ============================================================================
