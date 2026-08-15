-- pre_fight_snapshots — the permanent, tamper-proof pre-fight record.
--
-- THE RULE: before any card starts, every fight on it gets exactly one row here
-- freezing everything CFL was publicly showing at that moment — the engine's
-- pick and confidence, the market price we saw, the flagged value edge, the
-- Prop Board projections, and the legacy model cards. Written once, never
-- revised. This is the table you point at when someone asks "what did you
-- actually say before the fight?"
--
-- Why it has to exist separately from what we already store:
--   * model_picks is insert-only but carries no price and no props, and its
--     model_version drifts across a single card (a fight locked in July keeps
--     engine_v1 while a late addition gets engine_v2).
--   * prop_projections is FULL-TABLE REPLACED on every refresh — it holds only
--     the next card. Every prop number we ever published before today is gone.
--   * v_fight_odds_consensus is overwritten as the line moves.
-- A snapshot row is the only place those three are frozen together, at a
-- timestamp that provably precedes the bell.
--
-- Written by cfl_engine/snapshot_predictions.py --execute (service_role) on the
-- schedule in .github/workflows/snapshot.yml. PUBLIC read — the whole point is
-- that anyone can audit it.
--
-- Idempotent. Safe to re-run.

create table if not exists public.pre_fight_snapshots (
  id             bigint generated always as identity primary key,

  -- When we froze it. snapshot_at must precede the card; snapshot_label says
  -- which run produced it ('cron_pre_event', 'cron_day_of', 'manual').
  snapshot_at    timestamptz not null default now(),
  snapshot_label text        not null default 'cron_pre_event',

  -- Card / bout identity
  event_id       integer not null,
  event_name     text,
  event_date     date    not null,
  fight_id       integer not null,
  weight_class   text,
  main_event     boolean not null default false,
  title_fight    boolean not null default false,
  scheduled_rounds integer,
  fighter_a_id   integer,
  fighter_a_name text,
  fighter_b_id   integer,
  fighter_b_name text,

  -- What the engine said (from model_picks, source='live')
  engine_pick_fighter_id integer,
  engine_pick_side       text check (engine_pick_side in ('a','b')),
  engine_p_cal           numeric,   -- calibrated win probability for the pick
  engine_tier            text,      -- Lock / Pick / Lean
  engine_model_version   text,      -- engine_v1 / engine_v2 — VARIES WITHIN A CARD
  engine_published_at    timestamptz,

  -- The market at snapshot time (from v_fight_odds_consensus)
  odds_american_a   integer,
  odds_american_b   integer,
  implied_prob_a    numeric,        -- vig-free
  implied_prob_b    numeric,
  bookmaker_count   integer,
  odds_fetched_at   timestamptz,

  -- The flagged value edge, if we posted one (from model_edges, source='live')
  edge_side           text check (edge_side in ('a','b')),
  edge_bet_fighter_id integer,
  edge_value          numeric,      -- model prob minus vig-free market prob
  edge_stake_frac     numeric,      -- quarter-Kelly, 2% cap
  edge_odds_at_publish integer,

  -- The Prop Board as shown, both corners, verbatim. JSONB because this is the
  -- only surviving copy — prop_projections is wiped on the next card.
  props           jsonb,

  -- The legacy v1..v6 model cards the site still renders, as
  -- {"v6": {"fighter_id": 4117, "model_p": 0.83}, ...}. Kept because they are
  -- publicly visible; the audit flags on v5/v6 live in benchmark_report.md.
  legacy_models   jsonb,

  -- One snapshot per fight, forever. Re-runs hit this and do nothing.
  unique (fight_id)
);

create index if not exists pre_fight_snapshots_event_idx
  on public.pre_fight_snapshots (event_date desc, event_id);
create index if not exists pre_fight_snapshots_taken_idx
  on public.pre_fight_snapshots (snapshot_at desc);

-- ---------------------------------------------------------------- append-only
-- RLS keeps anon out of writes, but service_role BYPASSES RLS — so a bug in the
-- publisher could still silently rewrite history. These triggers make the table
-- append-only at the storage layer, for every role including service_role.
-- That guarantee is the whole value of the record: if it can be edited after
-- the fact, it is not evidence.
create or replace function public.pre_fight_snapshots_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'pre_fight_snapshots is append-only: % on fight_id % rejected. The pre-fight record must never be revised after the bell.',
    tg_op, coalesce(old.fight_id, new.fight_id);
end;
$$;

drop trigger if exists pre_fight_snapshots_block_update on public.pre_fight_snapshots;
create trigger pre_fight_snapshots_block_update
  before update on public.pre_fight_snapshots
  for each row execute function public.pre_fight_snapshots_no_rewrite();

drop trigger if exists pre_fight_snapshots_block_delete on public.pre_fight_snapshots;
create trigger pre_fight_snapshots_block_delete
  before delete on public.pre_fight_snapshots
  for each row execute function public.pre_fight_snapshots_no_rewrite();

-- ----------------------------------------------------------------------- RLS
-- Public read (matches every other public CFL table: anon AND authenticated).
-- No insert/update/delete policy — only service_role writes, and the triggers
-- above stop even service_role from rewriting.
alter table public.pre_fight_snapshots enable row level security;

drop policy if exists pre_fight_snapshots_public_read on public.pre_fight_snapshots;
create policy pre_fight_snapshots_public_read
  on public.pre_fight_snapshots for select
  to anon, authenticated
  using (true);

-- ---------------------------------------------------------------------- views
-- Graded pre-fight record: every snapshot joined to what actually happened.
-- NULL won_pick = not settled yet. This is the honest scoreboard — it can only
-- ever contain picks that were on record before the fight.
create or replace view public.v_pre_fight_graded as
select
  s.snapshot_at,
  s.snapshot_label,
  s.event_id,
  s.event_name,
  s.event_date,
  s.fight_id,
  s.weight_class,
  s.main_event,
  s.fighter_a_name,
  s.fighter_b_name,
  s.engine_pick_fighter_id,
  s.engine_p_cal,
  s.engine_tier,
  s.engine_model_version,
  case s.engine_pick_side when 'a' then s.odds_american_a else s.odds_american_b end
    as pick_odds_american,
  s.edge_value,
  s.edge_stake_frac,
  f.winner_id,
  f.method,
  case
    when f.winner_id is null then null
    else (f.winner_id = s.engine_pick_fighter_id)
  end as won_pick
from public.pre_fight_snapshots s
join public.fights f on f.id = s.fight_id;

grant select on public.v_pre_fight_graded to anon, authenticated;
