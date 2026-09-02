-- fighter_ratings: the engine's point-in-time Elo, exported per fighter so
-- the site can say "has faced tougher opponents than most of the division"
-- in words. Written by cfl_engine/export_ratings.py; full-table replaced on
-- each run (it is derived data, nothing here is a record).
create table if not exists fighter_ratings (
  fighter_id      bigint primary key,
  elo             numeric(7,1) not null,
  elo_peak        numeric(7,1) not null,
  n_fights        integer      not null,
  opp_elo_avg     numeric(7,1),          -- avg opponent rating going into each fight, all fights
  opp_elo_last5   numeric(7,1),          -- same, last five fights
  wins_vs_rated   integer,               -- wins over opponents rated above 1500 at the time
  last_fight_date date,
  computed_at     timestamptz not null default now()
);
alter table fighter_ratings enable row level security;
drop policy if exists "public read fighter_ratings" on fighter_ratings;
create policy "public read fighter_ratings" on fighter_ratings for select to anon, authenticated using (true);
grant select on fighter_ratings to anon, authenticated;
