-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- Event flow: the running order of a card, when each bout ended, and the close
-- reference CLV-001 derives from them. Implements Amendments 3, 4.1 and 5.
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
-- A BOUT'S COMPLETION HAS TWO ROLES under Amendment 5, and both are real: it is
-- the next fight's scoring cutoff, and it triggers aggressive card-night
-- capture for that fight. The exclusion of quotes at or after the cutoff is
-- enforced in cfl_engine/clv/scoring.py.
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
  'Append-only record of when a bout ended. Two roles under Amendment 5: it is '
  'the NEXT fight''s scoring cutoff, and it triggers aggressive card-night '
  'capture for that fight. The cutoff precedes that fight''s bell by the walkout '
  'interval, which is accepted for this protocol version and marked per row by '
  'v_clv_close_reference.reference_is_lower_bound.';

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
-- 2b. Append-only enforcement
--
-- Same shape as fight_start_estimates, prop_odds, prop_model_locks and
-- pre_fight_snapshots: a BEFORE UPDATE / BEFORE DELETE trigger that raises for
-- EVERY role, service_role included. RLS alone is not enough — service_role
-- bypasses policies, and the scripts that write these ledgers hold it.
--
-- These are observation ledgers. A running order that turned out wrong, or a
-- completion time that was mis-entered, is corrected by APPENDING a newer
-- observation; the view takes the latest. Editing history in place would mean a
-- CLV figure computed last week could not be reproduced today, which is the
-- whole thing these ledgers exist to prevent.
-- ---------------------------------------------------------------------------

create or replace function public.fight_bout_order_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'fight_bout_order is append-only: % rejected. A card''s running order is an '
    'observation - append a newer one and the latest wins.', tg_op;
end;
$$;
drop trigger if exists fight_bout_order_block_update on public.fight_bout_order;
create trigger fight_bout_order_block_update
  before update on public.fight_bout_order
  for each row execute function public.fight_bout_order_no_rewrite();
drop trigger if exists fight_bout_order_block_delete on public.fight_bout_order;
create trigger fight_bout_order_block_delete
  before delete on public.fight_bout_order
  for each row execute function public.fight_bout_order_no_rewrite();

alter table public.fight_bout_order enable row level security;
revoke all on public.fight_bout_order from anon, authenticated;

create or replace function public.fight_bout_completions_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'fight_bout_completions is append-only: % rejected. A bout ended when it '
    'ended; append a better observation instead of revising one.', tg_op;
end;
$$;
drop trigger if exists fight_bout_completions_block_update on public.fight_bout_completions;
create trigger fight_bout_completions_block_update
  before update on public.fight_bout_completions
  for each row execute function public.fight_bout_completions_no_rewrite();
drop trigger if exists fight_bout_completions_block_delete on public.fight_bout_completions;
create trigger fight_bout_completions_block_delete
  before delete on public.fight_bout_completions
  for each row execute function public.fight_bout_completions_no_rewrite();

alter table public.fight_bout_completions enable row level security;
revoke all on public.fight_bout_completions from anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Odds API credit ledger — the hard usage ceiling (Amendment 4)
-- ---------------------------------------------------------------------------
-- Five-minute capture through a live card is what makes the late pre-fight proxy
-- worth having, and it is also enough to break a 500-credit free tier if it runs
-- unchecked: measured, 3.7 UFC events a month on average and 6 in the busiest,
-- at roughly 93 h2h credits a card.
--
-- Each GitHub Actions run is a separate process with no memory of the last one,
-- so the provider's x-requests-remaining header is written here and read by the
-- next run to gate BEFORE spending. An empty or unreadable ledger reads as
-- "budget unknown", which build/fetch-odds.js treats as tight, not unlimited.

create table if not exists public.odds_api_usage (
  id                 bigserial primary key,
  requests_used      integer,
  requests_remaining integer,
  -- What THIS call cost: 1 for h2h alone, 2 when totals rode along. Summing this
  -- over the month is the authoritative spend, because nothing upstream can
  -- reset it. The provider's remaining-balance header is a cross-check and is
  -- believed only when it is SMALLER.
  credits_charged    integer not null default 1,
  observed_at        timestamptz not null default now(),
  constraint odds_api_usage_remaining_sane
    check (requests_remaining is null or requests_remaining >= 0),
  constraint odds_api_usage_charge_sane
    check (credits_charged between 1 and 10)
);

comment on table public.odds_api_usage is
  'Append-only. One row per Odds API call, with what that call cost. The SUM of '
  'credits_charged for the current month is the authoritative month-to-date '
  'spend - it cannot be reset by anything upstream, which a clamped provider '
  'balance can. requests_remaining is the provider''s own header, kept as a '
  'cross-check and believed only when it is smaller than our own count.';

create index if not exists odds_api_usage_observed_idx
  on public.odds_api_usage (observed_at desc);

-- Append-only, same as the other ledgers. This one guards spending: a quota
-- reading that can be edited after the fact is a budget that can be talked into
-- allowing one more call, and "one more call" past a free tier is paid usage.
create or replace function public.odds_api_usage_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'odds_api_usage is append-only: % rejected. A quota reading is what the '
    'provider said at that instant; append the next one.', tg_op;
end;
$$;
drop trigger if exists odds_api_usage_block_update on public.odds_api_usage;
create trigger odds_api_usage_block_update
  before update on public.odds_api_usage
  for each row execute function public.odds_api_usage_no_rewrite();
drop trigger if exists odds_api_usage_block_delete on public.odds_api_usage;
create trigger odds_api_usage_block_delete
  before delete on public.odds_api_usage
  for each row execute function public.odds_api_usage_no_rewrite();

alter table public.odds_api_usage enable row level security;
revoke all on public.odds_api_usage from anon, authenticated;

-- ---------------------------------------------------------------------------
-- 4. The close reference — Amendments 3 and 4, in one view
-- ---------------------------------------------------------------------------
-- AMENDMENT 5 - the operational cutoff, frozen for this protocol version:
--
--   bout 1      cutoff = the card's SCHEDULED START
--   bout 2..N   cutoff = the EXACT COMPLETION of the immediately previous bout
--   plus        a confirmed bell wherever one exists, which outranks both
--
-- and the scored price is the latest eligible sportsbook snapshot strictly
-- before that cutoff.
--
-- For bouts after the first the cutoff precedes the bell by the walkout
-- interval, so the proxy can sit several minutes early. That is accepted and
-- declared rather than hidden: it is the most consistent, observable and
-- reproducible cutoff implementable with the tools currently available, it is
-- the same rule for every such observation, and reference_is_lower_bound marks
-- each affected row.
--
-- This is a CFL closing-price proxy. It is never the exact sportsbook closing
-- line and must not be described as one.
--
-- If reliable bell timestamps ever arrive, that is a NEW PROTOCOL VERSION. Rows
-- scored under this one are never retroactively reinterpreted, which is why
-- every scored row carries its own clv_protocol_version.
--
-- AMENDMENT 4.1 separately withdrew a fourth tier. Amendment 4 had admitted the card's
-- scheduled start as a LOWER BOUND for every fight on the card, reasoning that a
-- fight cannot begin before its card does. The reasoning is sound; the
-- conclusion overreached. Such a quote is safely pre-fight but not LATE - on the
-- twelfth bout it sits hours before the bell - and calling it a late pre-fight
-- closing-price proxy would make the benchmark mean different things on
-- different fights of the same card.
--
-- So 'card_scheduled_start' is still REPORTED as a reference_basis and is never
-- used as reference_at for a later bout. A fight in that state has a verifiably
-- pre-fight price that is simply not late enough to score, which is a different
-- situation from having no price at all, and the report should say which.
--
-- The snapshots are kept. Five-minute capture runs through the whole card
-- precisely so a genuinely late snapshot is already on file for whenever a
-- fight's start becomes verifiable.
--
-- Deliberately absent: the event-date fallback, a placeholder rather than a
-- schedule.

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
  -- already maintains.
  --
  -- LATEST OBSERVATION, not max(start_at). A reschedule can move a card
  -- EARLIER, and max() would keep returning the superseded later time — so a
  -- quote taken after the new start would still look pre-fight. DISTINCT ON
  -- ordered by observed_at takes what the provider most recently said, which is
  -- the only reading that survives a reschedule in either direction.
  select distinct on (f.event_id)
         f.event_id, e.start_at as card_start_at, e.observed_at
  from public.fight_start_estimates e
  join public.fights f on f.id = e.fight_id
  where e.source = 'odds_api_commence'
  order by f.event_id, e.observed_at desc, e.id desc
)
select f.id                                   as fight_id,
       f.event_id,
       o.bout_order,
       (o.bout_order = 1)                     as is_first_bout,
       -- THE CUTOFF (Amendment 5).
       --   bout 1    -> the card's scheduled start
       --   bout 2..N -> the exact completion of the immediately previous bout
       --   plus      -> a confirmed bell wherever one exists, which outranks both
       --
       -- For bouts after the first the cutoff PRECEDES the bell by the walkout
       -- interval. That is accepted and declared: it is the most consistent,
       -- observable and reproducible cutoff available, it is the same rule for
       -- every such observation, and reference_is_lower_bound marks it.
       coalesce(f.bell_at,
                case when o.bout_order = 1 then s.card_start_at
                     else pd.prev_completed_at end)
                                              as reference_at,
       case
         when f.bell_at is not null            then 'bell_at'
         when o.bout_order = 1
          and s.card_start_at is not null      then 'scheduled_first_bout'
         when o.bout_order > 1
          and pd.prev_completed_at is not null then 'previous_bout_completion'
         -- Reported, never scored: the card's scheduled start applied to a later
         -- bout is hours early, so it would mean something different on every
         -- fight of the card (Amendment 4.1).
         when s.card_start_at is not null      then 'card_scheduled_start'
         else null
       end                                    as reference_basis,
       -- The bout BEFORE this one finishing. Under Amendment 5 this is the same
       -- instant as reference_at for bouts 2..N - it is both the cutoff and the
       -- capture trigger, which is the point. Carried separately so a future
       -- protocol version with real bell times can still see where the window
       -- opened without re-deriving it.
       pd.prev_completed_at                   as prev_bout_completed_at,
       -- TRUE when the cutoff PRECEDES the bell, so the recorded lead time is a
       -- lower bound on the true gap to the fight starting. Exactly the
       -- previous-bout-completion case.
       (f.bell_at is null and o.bout_order > 1
        and pd.prev_completed_at is not null)  as reference_is_lower_bound,
       f.bell_at                              as actual_bell_at,
       s.card_start_at                        as card_scheduled_start_at,
       s.observed_at                          as card_start_observed_at
from public.fights f
left join ord o        on o.fight_id = f.id
left join prev_done pd on pd.fight_id = f.id
left join sched s      on s.event_id = f.event_id;

comment on view public.v_clv_close_reference is
  'CLV-001 Amendment 5. reference_at is the scoring CUTOFF: the card''s '
  'scheduled start for bout 1, the previous bout''s exact completion for bouts '
  '2..N, or a confirmed bell where one exists. reference_is_lower_bound is TRUE '
  'when the cutoff precedes the bell, which is the previous-bout case. This is a '
  'CFL closing-price proxy, never the exact sportsbook closing line. Separate '
  'from DUR-001''s v_fight_start_best on purpose: that view is defined in a '
  'frozen file and serves a running experiment. actual_bell_at is the audit '
  'field and is never synthesised.';

comment on column public.v_clv_close_reference.reference_is_lower_bound is
  'TRUE when the cutoff precedes the fight''s bell - the previous-bout-completion '
  'case. The recorded lead time is then the exact gap to the CUTOFF and a lower '
  'bound on the gap to the bell. FALSE when the cutoff is the start itself.';

comment on column public.v_clv_close_reference.prev_bout_completed_at is
  'When the bout before this one ended. Under Amendment 5 this is the same '
  'instant as reference_at for bouts 2..N - it is both the cutoff and the '
  'capture trigger. Carried separately so a future protocol version with real '
  'bell times can still see where the window opened.';

-- Note the LEFT JOIN on running order, changed by Amendment 4. Under Amendment 3
-- a fight with no order row could not appear at all, because tiers 1-3 all need
-- one. Tier 4 does not: the card's scheduled start bounds every fight on the
-- card regardless of where in the running order it sits. Order still improves
-- the answer; it is no longer required to get one.

commit;

-- ============================================================================
-- AFTER APPLYING — what must still be true
--
--   * v_fight_start_best is byte-identical and DUR-001 is unaffected.
--   * all three new tables are EMPTY. Nothing backfills the two ledgers: a
--     running order reconstructed today is not what we observed on the night,
--     and a completion time we never recorded cannot be recovered by inference.
--   * v_clv_close_reference resolves a SCORING cutoff for bout 1 of any card
--     whose provider commence time is on file, and for bouts 2..N once the
--     preceding bout has an exact completion recorded. A fight with neither is
--     unscored: 'card_scheduled_start' -> only_pre_card_price, otherwise
--     no_previous_bout_completion or no_scheduled_start.
--   * the publication gate is untouched: 0 of 100 scored observations, 0 of 20
--     distinct events, fail-closed.
--
-- WHAT THIS NEEDS TO PRODUCE OBSERVATIONS
--
--   Running order. Free: ufcstats lists a card in order and the existing event
--   scraper can write fight_bout_order on the same pass. Without it no fight can
--   be identified as bout 1 and no bout has a 'previous' one.
--
--   Exact bout completions. These are now the SCORING CUTOFF for bouts 2..N
--   under Amendment 5, not merely a capture trigger - so they are what turns a
--   card from one scorable observation into roughly twelve. They have no free
--   source: a live feed or someone entering times during the card. That remains
--   the open L3, and it is now the single highest-leverage item on it.
--
--   Everything else is already in place: the 5-minute snapshots are captured and
--   stored, and they are exactly the prices these cutoffs select from.
-- ============================================================================
