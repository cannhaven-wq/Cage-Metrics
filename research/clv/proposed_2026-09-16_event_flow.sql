-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- Event flow: the running order of a card, when each bout ended, and the close
-- reference CLV-001 derives from them. Implements Amendment 3.
--
-- STATUS: draft. Apply AFTER proposed_2026-09-16_fight_odds_capture.sql and
-- BEFORE proposed_2026-09-16_clv001_columns.sql.
--
-- Filed under research/clv/ rather than the repo root so the "apply root *.sql"
-- habit cannot pick it up by accident.
--
-- ADDITIVE ONLY:
--   * no DROP of any kind
--   * no DELETE
--   * no destructive or back-filling UPDATE
--   * no existing trigger created, altered, weakened or removed
--   * no reinterpretation of an existing row or column
--
-- IT DOES NOT TOUCH `v_fight_start_best`. That view is defined in
-- dur001_migration.sql, which is a FROZEN FILE, and DUR-001's totals experiment
-- is running against it right now. CLV-001 gets its own view, with its own
-- rules, and the two experiments stay independent. A `create or replace view`
-- on a frozen experiment's view would be exactly the silent reinterpretation
-- the freeze exists to prevent.
--
-- ---------------------------------------------------------------------------
-- WHY THIS EXISTS
-- ---------------------------------------------------------------------------
-- A UFC card is one published start time and then a queue. Only the first bout
-- begins when the schedule says; every later bout begins when the one before it
-- ends. The database has neither fact:
--
--   * `fights` has no running-order column. It has is_main_event (the LAST
--     fight) and nothing else. Ordering by id would be an inference dressed as
--     a record, and it is wrong whenever a bout is rebooked or a card is
--     reshuffled — which is the exact case where getting it wrong costs most.
--   * nothing anywhere records when a bout ended.
--
-- So both are given append-only ledgers here, in the same shape as
-- fight_start_estimates: observations with a source, never a computed guess
-- overwriting an observation.
--
-- THE TRIGGER IS NOT THE CLOSE. Recording a bout's completion lets the odds job
-- start capturing every 30 minutes for the next fight. It does not define that
-- fight's closing price. The close is the last valid pre-live quote for the
-- upcoming fight, and any quote at or after that fight started is excluded.
-- v_clv_close_reference below supplies the cutoff; the exclusion is enforced in
-- cfl_engine/clv/scoring.py.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- 1. Running order — an observation, not an id sort
-- ---------------------------------------------------------------------------

create table if not exists public.fight_bout_order (
  id          bigserial primary key,
  fight_id    bigint      not null references public.fights(id) on delete cascade,
  event_id    bigint      not null,
  bout_order  integer     not null,          -- 1 = first bout to walk out
  source      text        not null,          -- 'ufcstats_card' | 'manual' | 'provider'
  observed_at timestamptz not null default now(),
  constraint fight_bout_order_positive check (bout_order >= 1)
);

comment on table public.fight_bout_order is
  'Append-only record of where a fight sat in its card''s running order. '
  'bout_order 1 is the first bout to walk out - the only one whose start is the '
  'card''s scheduled start. Append-only: a reshuffled card gets a NEW row and '
  'the latest observation wins, so the order we believed at any past moment '
  'stays recoverable.';

-- One live answer per (fight, source): re-observing the same order is a no-op,
-- a changed order appends.
create unique index if not exists fight_bout_order_unique_idx
  on public.fight_bout_order (fight_id, source, bout_order);

create index if not exists fight_bout_order_event_idx
  on public.fight_bout_order (event_id, bout_order);

-- ---------------------------------------------------------------------------
-- 2. Bout completions — when a fight actually ended
-- ---------------------------------------------------------------------------

create table if not exists public.fight_bout_completions (
  id           bigserial primary key,
  fight_id     bigint      not null references public.fights(id) on delete cascade,
  completed_at timestamptz not null,
  source       text        not null,   -- 'live_feed' | 'manual' | 'broadcast'
  is_exact     boolean     not null default false,
  observed_at  timestamptz not null default now(),
  constraint fight_bout_completions_not_epoch
    check (completed_at >= timestamptz '2026-05-22T00:00:00Z'),
  constraint fight_bout_completions_source_known
    check (source in ('live_feed', 'manual', 'broadcast'))
);

comment on table public.fight_bout_completions is
  'Append-only record of when a bout ended. Feeds the NEXT fight''s close '
  'reference and triggers its 30-minute capture window.';

comment on column public.fight_bout_completions.is_exact is
  'TRUE only for an observed completion instant. FALSE for an upper bound - '
  'e.g. "the result scraper first saw a winner at T", which is completion PLUS '
  'unknown lag. An upper bound must never become a close reference: it would '
  'admit quotes taken after the next fight had already started, which is the '
  'one thing this whole rule exists to prevent. v_clv_close_reference reads '
  'only is_exact rows.';

-- R-13's rule, restated for this table: a timestamp that cannot be a real
-- observation is not a timestamp. The epoch floor is the same one fight_odds
-- quotes are held to.

create unique index if not exists fight_bout_completions_unique_idx
  on public.fight_bout_completions (fight_id, source, completed_at);

-- ---------------------------------------------------------------------------
-- 3. The close reference — Amendment 3's hierarchy, in one view
-- ---------------------------------------------------------------------------
--   1. bell_at                   an actual confirmed bell. Audit-grade.
--   2. previous_bout_completion  the bout before this one ended (is_exact only).
--   3. scheduled_first_bout      the card's scheduled start - BOUT 1 ONLY.
--   else NULL, and the fight is unscored.
--
-- Deliberately absent: the event-date fallback, and any tier that guesses a
-- later bout's start from the card's scheduled time. A card's scheduled start
-- is the first fight's start and nobody else's.

create or replace view public.v_clv_close_reference
with (security_invoker = true) as
with ord as (
  select distinct on (o.fight_id)
         o.fight_id, o.event_id, o.bout_order
  from public.fight_bout_order o
  order by o.fight_id, o.observed_at desc, o.id desc   -- latest observation wins
),
prev_done as (
  -- The completion of the bout immediately before this one, same card.
  select o.fight_id,
         (select max(c.completed_at)
            from public.fight_bout_completions c
            join ord p on p.fight_id = c.fight_id
           where p.event_id = o.event_id
             and p.bout_order = o.bout_order - 1
             and c.is_exact) as prev_completed_at
  from ord o
),
sched as (
  -- The card's scheduled start, from the provider commence ledger DUR-001
  -- already maintains. Latest observation wins, so a reschedule supersedes.
  select e.fight_id, max(e.start_at) as start_at
  from public.fight_start_estimates e
  where e.source = 'odds_api_commence'
  group by e.fight_id
)
select f.id                                   as fight_id,
       o.event_id,
       o.bout_order,
       (o.bout_order = 1)                     as is_first_bout,
       coalesce(f.bell_at, pd.prev_completed_at,
                case when o.bout_order = 1 then s.start_at end)
                                              as reference_at,
       case
         when f.bell_at is not null            then 'bell_at'
         when pd.prev_completed_at is not null then 'previous_bout_completion'
         when o.bout_order = 1
          and s.start_at is not null           then 'scheduled_first_bout'
         else null
       end                                    as reference_basis,
       f.bell_at                              as actual_bell_at
from public.fights f
join ord o          on o.fight_id = f.id
left join prev_done pd on pd.fight_id = f.id
left join sched s      on s.fight_id = f.id;

comment on view public.v_clv_close_reference is
  'CLV-001 Amendment 3. Per fight: the instant it began, by the best available '
  'account - actual bell, else the previous bout''s exact completion, else (bout '
  '1 only) the card''s scheduled start. NULL reference_basis means unscorable, '
  'which is the correct answer and not a gap to fill. Separate from DUR-001''s '
  'v_fight_start_best on purpose: that view is defined in a frozen file and '
  'serves a running experiment. actual_bell_at is carried through as the audit '
  'field and is never synthesised.';

-- A fight with no order row cannot appear above at all (inner join), which is
-- deliberate: without a running order there is no "previous bout", so there is
-- nothing to reason from. Unknown is unscored.

commit;

-- ============================================================================
-- AFTER APPLYING — what must still be true
--
--   * v_fight_start_best is byte-identical and DUR-001 is unaffected.
--   * both new tables are EMPTY. Nothing backfills them: a running order
--     reconstructed today is not what we observed on the night, and a
--     completion time we never recorded cannot be recovered by inference.
--   * v_clv_close_reference therefore returns zero rows until fight_bout_order
--     is populated, and settle_clv.py reports every fight as
--     no_scheduled_start. That is the honest state, not a broken one.
--   * the publication gate is untouched: 0 of 100 scored observations, 0 of 20
--     distinct events, fail-closed.
--
-- WHAT STILL HAS NO SOURCE — and why it is an L3 question, not a TODO
--
--   Running order is obtainable free: ufcstats lists a card in order, and the
--   existing event scraper can write fight_bout_order on the same pass.
--
--   Exact bout completions are NOT obtainable free. The result scraper runs
--   after the card and yields an upper bound (completion plus unknown lag),
--   which is_exact=false explicitly refuses. A real completion instant needs
--   either a paid live-data feed or a person entering times during the card.
--   Both are new standing commitments, so both are escalated rather than
--   assumed - see the handoff.
--
--   Until one exists, only bout 1 of each card can be scored. That is roughly
--   one scorable observation per event, against a floor of 100 across 20
--   events, and it is the single biggest fact about the CLV timeline.
-- ============================================================================
