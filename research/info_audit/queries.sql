-- INFO-AUDIT-001 — the live-database measurements behind
-- PREDICTIVE_INFORMATION_AUDIT_2026-10-12.md. Read-only. Run 2026-10-12 against
-- project uftancejftcryfvbggll; outputs recorded in live_results_2026-10-12.json.

-- Q1. Historical closing benchmark: BestFightOdds consensus closer
--     (the 1970-01-01 placeholder-timestamp rows), vig removed proportionally.
with h as (
 select o.fight_id, f.winner_id, f.fighter_a_id, f.fighter_b_id, e.event_date,
  max(o.implied_prob) filter (where o.is_closer and o.fighter_id=f.fighter_a_id) pa,
  max(o.implied_prob) filter (where o.is_closer and o.fighter_id=f.fighter_b_id) pb
 from fight_odds o join fights f on f.id=o.fight_id join events e on e.id=f.event_id
 where o.captured_at<'2000-01-01' and f.winner_id in (f.fighter_a_id,f.fighter_b_id)
 group by 1,2,3,4,5)
select count(*) n, min(event_date), max(event_date),
 avg(((pa>pb and winner_id=fighter_a_id) or (pb>pa and winner_id=fighter_b_id))::int) filter (where pa<>pb) fav_acc,
 avg(-( (winner_id=fighter_a_id)::int*ln(pa/(pa+pb)) + (winner_id=fighter_b_id)::int*ln(pb/(pa+pb)))) ll_close
from h where pa>0 and pb>0;

-- Q2. The prospective record: earliest pre_fight_snapshots row per settled
--     fight. Engine pick vs market favourite at the same instant.
with s as (
 select distinct on (s.fight_id) s.*, f.winner_id
 from pre_fight_snapshots s join fights f on f.id=s.fight_id
 where f.winner_id is not null order by s.fight_id, s.snapshot_at)
select count(*) n,
 count(*) filter (where engine_pick_fighter_id = winner_id) pick_right,
 count(*) filter (where implied_prob_a is not null and implied_prob_a<>implied_prob_b) n_mkt,
 count(*) filter (where implied_prob_a is not null and implied_prob_a<>implied_prob_b and ((implied_prob_a>implied_prob_b and winner_id=fighter_a_id) or (implied_prob_b>implied_prob_a and winner_id=fighter_b_id))) mkt_right,
 count(*) filter (where engine_pick_fighter_id is not null and implied_prob_a is not null and implied_prob_a<>implied_prob_b and engine_pick_fighter_id <> case when implied_prob_a>implied_prob_b then fighter_a_id else fighter_b_id end) n_disagree,
 count(*) filter (where engine_pick_fighter_id is not null and implied_prob_a is not null and implied_prob_a<>implied_prob_b and engine_pick_fighter_id <> case when implied_prob_a>implied_prob_b then fighter_a_id else fighter_b_id end and engine_pick_fighter_id=winner_id) disagree_engine_right,
 min(event_date) first, max(event_date) last, count(distinct event_id) events
from s;

-- Q3. Same prospective set, scored as probabilities (log loss), engine vs
--     market vs a coin, with a plain (non-clustered) standard error.
with s as (
 select distinct on (s.fight_id) s.*, f.winner_id
 from pre_fight_snapshots s join fights f on f.id=s.fight_id
 where f.winner_id is not null and s.implied_prob_a is not null and s.engine_p_cal is not null
 order by s.fight_id, s.snapshot_at),
t as (select (winner_id=fighter_a_id)::int y,
  case when engine_pick_fighter_id=fighter_a_id then engine_p_cal else 1-engine_p_cal end pe,
  implied_prob_a/(implied_prob_a+implied_prob_b) pm from s),
d as (select -(y*ln(pe)+(1-y)*ln(1-pe)) lle, -(y*ln(pm)+(1-y)*ln(1-pm)) llm from t)
select count(*) n, avg(lle) ll_engine, avg(llm) ll_market, ln(2) ll_coin,
 avg(lle-llm) eng_minus_mkt, stddev(lle-llm)/sqrt(count(*)) se_mkt,
 avg(lle-ln(2)) eng_minus_coin, stddev(lle-ln(2))/sqrt(count(*)) se_coin
from d;

-- Q4. model_picks written before the card, live engine versions, since 2026-07-18.
select source, model_version, count(*) n, count(*) filter (where f.winner_id is not null) settled,
 count(*) filter (where f.winner_id = m.pick_fighter_id) right_
from model_picks m join fights f on f.id=m.fight_id
where m.event_date >= '2026-07-18' and m.source='live'
group by 1,2 order by 1,2;

-- Q5. What is held: coverage of the per-round position / target splits.
select count(*) rows_, count(a_head_landed) head, count(a_distance_landed) dist,
 count(a_clinch_landed) clinch, count(a_ground_landed) ground, count(a_rev) rev,
 count(distinct fight_id) fights
from fight_rounds;

-- Q6. Odds depth: placeholder-timestamp history vs real captures.
select (captured_at < '2000-01-01') placeholder_ts, count(*) rows_, count(distinct fight_id) fights,
 min(captured_at), max(captured_at)
from fight_odds group by 1;

-- Q7. Decided fights per year, for the test-duration arithmetic.
select extract(year from e.event_date) yr, count(*) from fights f join events e on e.id=f.event_id
where e.event_date between '2021-01-01' and '2025-12-31' and f.winner_id is not null group by 1 order by 1;
