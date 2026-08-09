-- prop_projections — public prop-model output for props.html (Prop Board).
-- One row per (fight, corner). Written by cfl_engine/predict_props_upcoming.py
-- --execute (service_role). PUBLIC read (this is site-facing data), unlike the
-- PRIVATE cfl-prop-model.prop_lines table. Idempotent — safe to re-run.

create table if not exists public.prop_projections (
  id            bigint generated always as identity primary key,
  generated_at  timestamptz not null default now(),
  event_id      integer     not null,
  event_name    text,
  event_date    date,
  fight_id      integer     not null,
  weight_class  text,
  main_event    boolean     not null default false,
  side          text        not null check (side in ('a','b')),
  fighter_id    integer,
  fighter_name  text,
  opponent_name text,
  p_distance    numeric,      -- P(fight goes the full scheduled rounds)
  sig_proj      numeric,      -- distance-conditional mean significant strikes
  sig_lo        numeric,      -- 20th percentile (distance-conditional)
  sig_hi        numeric,      -- 80th percentile (distance-conditional)
  sig_med       numeric,      -- median (for the range-bar marker)
  td_proj       numeric,      -- distance-conditional expected takedowns
  p_td_1plus    numeric,      -- P(>=1 takedown), integrates finish risk
  p_td_2plus    numeric,      -- P(>=2 takedowns), integrates finish risk
  thin_tape     boolean       not null default false,
  model_version text,
  unique (fight_id, side)     -- one current projection per corner; re-publish upserts
);

create index if not exists prop_projections_event_idx
  on public.prop_projections (event_date desc, event_id);

-- Public read (matches every other public CFL table: anon AND authenticated).
alter table public.prop_projections enable row level security;
drop policy if exists prop_projections_public_read on public.prop_projections;
create policy prop_projections_public_read
  on public.prop_projections for select
  to anon, authenticated
  using (true);
grant select on public.prop_projections to anon, authenticated;

-- Convenience view: just the most recent card's rows, ordered for the page
-- (main event first, then by fight, corner a before b). security_invoker so the
-- table's public-read RLS governs access.
create or replace view public.v_prop_projections_current
  with (security_invoker = true) as
  select *
  from public.prop_projections
  where event_id = (
    select event_id from public.prop_projections
    order by event_date desc nulls last, generated_at desc
    limit 1
  )
  order by main_event desc, fight_id, side;
grant select on public.v_prop_projections_current to anon, authenticated;
