-- Fighter analysis layer (Sep 2026): the reads behind fighter.html.
-- 1) v_fighter_division_read — where a fighter sits inside his division on
--    each stat, as a percentile, plus the division median to anchor to.
--    Pool = fighters with 3+ UFC fights who fought in the last 5 years, so a
--    percentile means "against the people he actually fights", not UFC 1.
-- 2) v_fighter_model_record — the engine's graded history on each fighter:
--    how many wins the model expected vs how many he got.
create or replace view v_fighter_division_read as
with base as (
  select id as fighter_id, division, slpm, sapm, str_acc, str_def, td_avg, td_acc, td_def, sub_avg,
         reach_in, height_in, age,
         coalesce(ufc_wins,0)+coalesce(ufc_losses,0)+coalesce(ufc_draws,0) as ufc_fights,
         last_fight_date
  from fighters
  where division is not null
),
pool as (
  select * from base
  where ufc_fights >= 3
    and last_fight_date is not null
    and last_fight_date >= (current_date - interval '5 years')
),
core as (
  select fighter_id,
    percent_rank() over (partition by division order by slpm)    as slpm_pct,
    percent_rank() over (partition by division order by sapm)    as sapm_pct,
    percent_rank() over (partition by division order by str_acc) as str_acc_pct,
    percent_rank() over (partition by division order by str_def) as str_def_pct,
    percent_rank() over (partition by division order by td_avg)  as td_avg_pct,
    percent_rank() over (partition by division order by td_def)  as td_def_pct,
    percent_rank() over (partition by division order by sub_avg) as sub_avg_pct
  from pool
  where slpm is not null and sapm is not null and str_acc is not null and str_def is not null
    and td_avg is not null and td_def is not null and sub_avg is not null
),
tdacc as (
  select fighter_id, percent_rank() over (partition by division order by td_acc) as td_acc_pct
  from pool where td_acc is not null and td_avg > 0
),
phys as (
  select fighter_id,
    percent_rank() over (partition by division order by reach_in)  as reach_pct,
    percent_rank() over (partition by division order by height_in) as height_pct
  from pool where reach_in is not null and height_in is not null
),
agep as (
  select fighter_id, percent_rank() over (partition by division order by age) as age_pct
  from pool where age is not null
),
meds as (
  select division, count(*) as pool_n,
    percentile_cont(0.5) within group (order by slpm)    as slpm_med,
    percentile_cont(0.5) within group (order by sapm)    as sapm_med,
    percentile_cont(0.5) within group (order by str_acc) as str_acc_med,
    percentile_cont(0.5) within group (order by str_def) as str_def_med,
    percentile_cont(0.5) within group (order by td_avg)  as td_avg_med,
    percentile_cont(0.5) within group (order by td_acc) filter (where td_avg > 0) as td_acc_med,
    percentile_cont(0.5) within group (order by td_def)  as td_def_med,
    percentile_cont(0.5) within group (order by sub_avg) as sub_avg_med,
    percentile_cont(0.5) within group (order by reach_in) as reach_med,
    percentile_cont(0.5) within group (order by height_in) as height_med,
    percentile_cont(0.5) within group (order by age)     as age_med
  from pool group by division
)
select b.fighter_id, b.division, b.ufc_fights,
       (p.fighter_id is not null) as in_pool,
       c.slpm_pct, c.sapm_pct, c.str_acc_pct, c.str_def_pct, c.td_avg_pct, t.td_acc_pct, c.td_def_pct, c.sub_avg_pct,
       ph.reach_pct, ph.height_pct, ag.age_pct,
       m.pool_n, m.slpm_med, m.sapm_med, m.str_acc_med, m.str_def_med, m.td_avg_med, m.td_acc_med, m.td_def_med, m.sub_avg_med,
       m.reach_med, m.height_med, m.age_med
from base b
left join pool  p  on p.fighter_id = b.fighter_id
left join core  c  on c.fighter_id = b.fighter_id
left join tdacc t  on t.fighter_id = b.fighter_id
left join phys  ph on ph.fighter_id = b.fighter_id
left join agep  ag on ag.fighter_id = b.fighter_id
left join meds  m  on m.division = b.division;

create or replace view v_fighter_model_record as
with g as (
  select fight_id, event_date, p_cal, pick_fighter_id, fighter_a_id, fighter_b_id, winner_id, source
  from v_model_picks_graded
  where hit is not null and winner_id is not null
),
one as (
  select distinct on (fight_id) * from g order by fight_id, (source = 'live') desc
),
sides as (
  select fight_id, event_date, fighter_a_id as fighter_id,
         case when pick_fighter_id = fighter_a_id then p_cal else 1 - p_cal end as p_win,
         (winner_id = fighter_a_id) as won
  from one
  union all
  select fight_id, event_date, fighter_b_id,
         case when pick_fighter_id = fighter_b_id then p_cal else 1 - p_cal end,
         (winner_id = fighter_b_id)
  from one
)
select fighter_id,
       count(*)                                   as n_scored,
       sum(won::int)                              as wins,
       round(sum(p_win)::numeric, 2)              as expected_wins,
       sum(case when (p_win >= 0.5) = won then 1 else 0 end) as model_correct,
       sum(case when p_win >= 0.5 and not won then 1 else 0 end) as lost_as_pick,
       sum(case when p_win <  0.5 and won     then 1 else 0 end) as won_as_underdog,
       max(event_date)                            as last_scored
from sides
group by fighter_id;

grant select on v_fighter_division_read to anon, authenticated;
grant select on v_fighter_model_record  to anon, authenticated;
