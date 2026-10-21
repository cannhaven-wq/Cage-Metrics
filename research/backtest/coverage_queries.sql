-- BT-001 — the statements behind RESULTS_2026-10-21.md. SELECT only.
-- Run read-only on Supabase project uftancejftcryfvbggll, 2026-10-21, through
-- the Supabase MCP execute_sql tool (the sandbox cannot reach the database
-- host directly). None of them reads fights.winner_id or any outcome, and none
-- reads win_model_locks. Q1-Q3 count rows and times across sealed months; they
-- return no price values. Q4 reads prices only for cards on or after
-- 2026-10-12 (after the PRED-001 RESERVE window). Q5 reads BFO consensus
-- prices before 2025-01-01 (DEV), prices only.

-- Q1. Rows by capture month, book and writer fingerprint -------------------
select to_char(date_trunc('month', o.captured_at),'YYYY-MM') cap_month, b.name,
  (s.id is not null) sportsbook, count(*) n,
  count(*) filter (where o.feed_version is not null) fv,
  string_agg(distinct coalesce(o.feed_version,'-'), '|') fvs,
  count(*) filter (where o.retrieved_at is not null) ret,
  count(*) filter (where o.source_url is not null) url,
  count(*) filter (where o.raw is not null) raw,
  count(*) filter (where o.source_commence_at is not null) commence,
  count(*) filter (where o.is_live) live,
  count(*) filter (where o.market_status is not null) ms,
  count(*) filter (where o.bout_started_at is not null) bout_start,
  count(*) filter (where o.proxy_cutoff_at is not null) cutoff,
  left(min(o.source_url),40) url_eg
from fight_odds o join odds_books b on b.id=o.book_id
left join v_odds_books_sportsbooks s on s.id=o.book_id
where o.book_id <> 6
group by 1,2,3 order by 1,2;

-- Q1b. Book-level span (all books, including BFO consensus id 6) -----------
select b.id, b.name, (s.id is not null) as sportsbook, count(o.id) n_rows,
  min(e.event_date) min_ev, max(e.event_date) max_ev,
  count(*) filter (where e.event_date < '2025-01-01') n_dev,
  count(*) filter (where o.is_closer) n_closer, count(*) filter (where o.is_opener) n_opener,
  min(o.captured_at) min_cap, max(o.captured_at) max_cap
from odds_books b left join v_odds_books_sportsbooks s on s.id=b.id
left join fight_odds o on o.book_id=b.id left join fights f on f.id=o.fight_id
left join events e on e.id=f.event_id
group by 1,2,3 order by n_rows desc;

-- Q2. Executable two-sided pre-bell coverage, per card (-> data/actionable_coverage_by_card.csv)
-- "Executable": a real sportsbook, not live, both sides quoted by the same book
-- at the same capture instant, captured strictly before the fight's best-known
-- start. When no provider commence time exists, v_fight_start_best falls back to
-- 00:00 UTC on the event date, so a quote is only counted if it was captured
-- before the card's day began - the conservative reading.
with fx as (
  select f.id fight_id, e.id event_id, e.event_date, sb.start_at, sb.start_basis
  from fights f join events e on e.id=f.event_id left join v_fight_start_best sb on sb.fight_id=f.id
  where f.is_active is distinct from false and e.event_date >= '2026-05-01'
),
q as (
  select o.fight_id, o.book_id, o.captured_at, bool_or(o.feed_version is not null) w3, count(distinct o.side) sides
  from fight_odds o join v_odds_books_sportsbooks s on s.id=o.book_id
  where o.is_live is not true group by 1,2,3
),
anyq as (select distinct fight_id from q),
two as (select q.*, fx.start_at from q join fx using (fight_id)
        where q.sides=2 and fx.start_at is not null and q.captured_at < fx.start_at),
pf as (select fight_id, max(captured_at) last_cap, count(distinct book_id) books, bool_or(w3) w3 from two group by 1)
select fx.event_date, fx.event_id, count(*) fights_on_card, count(anyq.fight_id) any_sb_quote,
  string_agg(distinct coalesce(fx.start_basis,'none'), ',') basis,
  count(pf.fight_id) two_sided_prebell, count(*) filter (where pf.w3) w3_two_sided,
  round(percentile_cont(0.5) within group (order by extract(epoch from fx.start_at-pf.last_cap)/60)::numeric,0) med_min_before,
  count(*) filter (where extract(epoch from fx.start_at-pf.last_cap)/60 <= 60) within_60,
  count(*) filter (where extract(epoch from fx.start_at-pf.last_cap)/60 <= 180) within_180,
  round(avg(pf.books),1) avg_books
from fx left join anyq on anyq.fight_id=fx.fight_id left join pf on pf.fight_id=fx.fight_id
group by 1,2 order by 1;

-- Q3. Legacy writers (no feed_version): when were their two-sided quotes taken?
with q as (
  select o.fight_id, o.book_id, o.captured_at, count(distinct o.side) sides
  from fight_odds o join v_odds_books_sportsbooks s on s.id=o.book_id
  where o.is_live is not true and o.feed_version is null group by 1,2,3)
select e.event_date, count(distinct q.fight_id) fights_two_sided_any_time,
  count(distinct q.fight_id) filter (where q.captured_at::date = e.event_date) fights_two_sided_on_event_day,
  max(q.captured_at) last_cap
from q join fights f on f.id=q.fight_id join events e on e.id=f.event_id
where q.sides=2 and e.event_date < '2026-10-12' group by 1 order by 1;

-- Q4. Cost of a bet: overround and line-shopping value (cards >= 2026-10-12, no outcomes)
-- Last two-sided W3 snapshot per (fight, sportsbook) before the provider's
-- commence time; fights with at least 3 such books. Re-run with
-- `and o.captured_at >= fx.start_at - interval '180 minutes'` for the
-- "within three hours" variant reported for 2026-10-17.
with fx as (
  select f.id fight_id, e.event_date, sb.start_at from fights f join events e on e.id=f.event_id
  join v_fight_start_best sb on sb.fight_id=f.id
  where f.is_active is distinct from false and e.event_date >= '2026-10-12' and sb.start_basis='provider_commence'
),
snap as (
  select o.fight_id, o.book_id, o.captured_at,
    max(o.american_odds) filter (where o.side='A') am_a, max(o.american_odds) filter (where o.side='B') am_b,
    count(distinct o.side) sides
  from fight_odds o join v_odds_books_sportsbooks s on s.id=o.book_id join fx using (fight_id)
  where o.is_live is not true and o.feed_version is not null and o.captured_at < fx.start_at
  group by 1,2,3
),
last as (
  select distinct on (fight_id, book_id) s.*,
    case when am_a>0 then 1+am_a/100.0 else 1+100.0/abs(am_a) end da,
    case when am_b>0 then 1+am_b/100.0 else 1+100.0/abs(am_b) end db
  from snap s where sides=2 order by fight_id, book_id, captured_at desc
),
pf as (
  select l.fight_id, fx.event_date, count(*) books,
    percentile_cont(0.5) within group (order by da) med_da, max(da) best_da,
    percentile_cont(0.5) within group (order by db) med_db, max(db) best_db,
    percentile_cont(0.5) within group (order by 1/da+1/db) med_book_overround,
    max(extract(epoch from fx.start_at - l.captured_at)/60) max_age_min,
    min(extract(epoch from fx.start_at - l.captured_at)/60) min_age_min
  from last l join fx using (fight_id) group by 1,2 having count(*)>=3
)
select event_date, count(*) fights, round(avg(books),1) avg_books,
  round(percentile_cont(0.5) within group (order by med_book_overround)::numeric,4) med_single_book_overround,
  round(percentile_cont(0.5) within group (order by 1/best_da+1/best_db)::numeric,4) med_best_of_books_overround,
  round(min(1/best_da+1/best_db)::numeric,4) min_best_overround,
  round(percentile_cont(0.5) within group (order by (best_da/med_da + best_db/med_db)/2)::numeric,4) med_best_over_median_decimal,
  round(percentile_cont(0.5) within group (order by min_age_min)::numeric,0) med_min_before_start_freshest_book,
  round(percentile_cont(0.5) within group (order by max_age_min)::numeric,0) med_min_before_start_stalest_book
from pf group by 1 order by 1;

-- Q5. BFO consensus overround before 2025 (prices only) --------------------
with p as (
 select o.fight_id, extract(year from e.event_date) yr, o.is_closer,
  sum(case when o.american_odds>0 then 100.0/(o.american_odds+100)
           else abs(o.american_odds)/(abs(o.american_odds)+100.0) end) ovr, count(*) n
 from fight_odds o join fights f on f.id=o.fight_id join events e on e.id=f.event_id
 where o.book_id=6 and e.event_date < '2025-01-01' group by 1,2,3 having count(*)=2)
select case when yr<2015 then '2007-2014' when yr<2020 then '2015-2019' else '2020-2024' end era, is_closer,
 count(*), round(percentile_cont(0.5) within group (order by ovr)::numeric,4) med_overround,
 round(percentile_cont(0.1) within group (order by ovr)::numeric,4) p10,
 round(percentile_cont(0.9) within group (order by ovr)::numeric,4) p90
from p group by 1,2 order by 1,2;
