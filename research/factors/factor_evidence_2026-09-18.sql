-- =============================================================================
-- factor_evidence_2026-09-18.sql — FE-001 scoring query (READ ONLY)
-- =============================================================================
-- Companion to FACTOR_EVIDENCE_2026-09-18.md. Re-run this to reproduce every
-- number in that report's results table.
--
-- Run it against the Cage Metrics Supabase project with a role that can read
-- `fight_odds` (the publishable key cannot — see build/factor-rates.js).
--
-- It SELECTs only. It creates nothing, writes nothing and drops nothing.
--
-- It returns one row per (factor, band) with four raw counts:
--   n       fights the factor fired on
--   w       of those, fights the favoured fighter won
--   n_even  the same, restricted to fights the market priced as even
--   w_even  (both sides inside +/-140 at close, median across books)
-- Wilson intervals and verdicts are computed from those four numbers with the
-- same formulas build/factor-rates.js uses (z = 1.96; MIN_SAMPLE = 100;
-- LEAN_PCT = 55).
--
-- Point-in-time discipline: every per-fighter statistic below is a window
-- aggregate over that fighter's STRICTLY PRIOR fights
-- (`rows between unbounded preceding and 1 preceding`), ordered by event date
-- then fight id — the SQL equivalent of the chronological walk in
-- build/factor-rates.js, which snapshots state before folding each result in.
-- Nothing reads a career-aggregate column that contains the fight being scored,
-- with one deliberate, labelled exception: `fighters.td_avg` in the
-- C_td_def_edgesjs_careergate variant, which exists precisely to show what
-- production's capability gate does. Its point-in-time twin is variant B.
-- =============================================================================

with fx as (
  select fg.id, e.event_date, fg.fighter_a_id a_id, fg.fighter_b_id b_id, fg.winner_id,
         fg.method, fg.end_round, fg.end_time,
         fg.a_sig_str_landed, fg.b_sig_str_landed,
         fg.a_td_landed, fg.b_td_landed, fg.a_td_attempted, fg.b_td_attempted
  from fights fg join events e on e.id = fg.event_id
  where e.event_date is not null
),
fxm as (
  -- Real elapsed minutes, from end_round + end_time. A round is not five
  -- minutes just because it is a round (v7 cardio learned this the hard way).
  select *,
    case when end_round is null then null
         else ((end_round-1)*300 + case when end_time ~ '^[0-9]+:[0-9]+$'
              then split_part(end_time,':',1)::int*60 + split_part(end_time,':',2)::int
              else 300 end)::numeric / 60.0 end as mins
  from fx
),
sides as (
  -- One row per fighter per fight. td_faced / td_conceded are the OPPONENT's
  -- takedown attempts and landings, which is what takedown defence measures.
  select id fight_id, event_date, a_id fid, winner_id, mins,
         a_sig_str_landed sig_landed, b_td_attempted td_faced, b_td_landed td_conceded,
         a_td_attempted td_att_self
  from fxm
  union all
  select id, event_date, b_id, winner_id, mins,
         b_sig_str_landed, a_td_attempted, a_td_landed, b_td_attempted
  from fxm
),
st as (
  select fight_id, fid,
    coalesce(count(*) over w, 0) prior_fights,
    coalesce(sum(case when winner_id = fid then 1 else 0 end) over w, 0) prior_wins,
    coalesce(sum(case when winner_id is not null and winner_id <> fid then 1 else 0 end) over w, 0) prior_losses,
    coalesce(sum(case when sig_landed is not null and mins is not null and mins > 0 then mins else 0 end) over w, 0)::numeric prior_mins,
    coalesce(sum(coalesce(td_faced,0)) over w, 0)::numeric prior_td_faced,
    coalesce(sum(coalesce(td_conceded,0)) over w, 0)::numeric prior_td_conceded,
    coalesce(sum(coalesce(td_att_self,0)) over w, 0)::numeric prior_td_att
  from sides
  window w as (partition by fid order by event_date, fight_id
               rows between unbounded preceding and 1 preceding)
),
tot as (
  select fid,
    sum(case when winner_id = fid then 1 else 0 end) db_wins,
    sum(case when winner_id is not null and winner_id <> fid then 1 else 0 end) db_losses
  from sides group by fid
),
close_px as (
  -- Median closing price per fighter per fight. Matches the JS `median` helper:
  -- upper median on an even count. In practice 99.6% of sides carry one book.
  select fight_id, fighter_id,
         (array_agg(american_odds order by american_odds))[floor(count(*)/2)::int + 1] px
  from fight_odds where is_closer and american_odds is not null
  group by fight_id, fighter_id
),
m as (
  select f.id, f.event_date, f.a_id, f.b_id, f.winner_id,
    sa.prior_fights a_pf, sa.prior_wins a_pw, sa.prior_losses a_pl,
    sb.prior_fights b_pf, sb.prior_wins b_pw, sb.prior_losses b_pl,
    sa.prior_td_faced a_tdf, sa.prior_td_conceded a_tdc, sa.prior_td_att a_tda, sa.prior_mins a_min,
    sb.prior_td_faced b_tdf, sb.prior_td_conceded b_tdc, sb.prior_td_att b_tda, sb.prior_mins b_min,
    -- Point-in-time PROFESSIONAL record, which is what edges.js recordEdge
    -- reads (fighters.wins / fighters.losses, not the UFC-only columns).
    -- Reconstruction: the career total as scraped today, minus the UFC results
    -- that came AFTER this fight. At a fighter's UFC debut this leaves their
    -- pre-UFC regional record, which is correct. See the report's mismatch
    -- section for what this reconstruction cannot see.
    greatest(fa.wins   - (ta.db_wins   - sa.prior_wins),   0)::numeric a_prow,
    greatest(fa.losses - (ta.db_losses - sa.prior_losses), 0)::numeric a_prol,
    greatest(fb.wins   - (tb.db_wins   - sb.prior_wins),   0)::numeric b_prow,
    greatest(fb.losses - (tb.db_losses - sb.prior_losses), 0)::numeric b_prol,
    fa.td_avg a_tdavg_c, fb.td_avg b_tdavg_c,
    case when fa.dob is not null then (f.event_date - fa.dob)/365.25 end a_age,
    case when fb.dob is not null then (f.event_date - fb.dob)/365.25 end b_age,
    (pa.px is not null and pb.px is not null
      and pa.px between -140 and 140 and pb.px between -140 and 140) even
  from fxm f
  join fighters fa on fa.id = f.a_id
  join fighters fb on fb.id = f.b_id
  join st sa on sa.fight_id = f.id and sa.fid = f.a_id
  join st sb on sb.fight_id = f.id and sb.fid = f.b_id
  join tot ta on ta.fid = f.a_id
  join tot tb on tb.fid = f.b_id
  left join close_px pa on pa.fight_id = f.id and pa.fighter_id = f.a_id
  left join close_px pb on pb.fight_id = f.id and pb.fighter_id = f.b_id
  where f.winner_id is not null
),
h as (
  select m.*,
    -- edges.js recordEdge: Laplace-smoothed (w+2)/(w+l+4), pro record.
    (a_prow+2.0)/(a_prow+a_prol+4.0) a_sm, (b_prow+2.0)/(b_prow+b_prol+4.0) b_sm,
    -- Takedown defence, point-in-time. MIN_TD_ATTEMPTS = 5 is the Factor Lab
    -- floor; production has NO floor (see the report).
    case when a_tdf >= 5 then 100*(1 - a_tdc/a_tdf) end a_tddef,
    case when b_tdf >= 5 then 100*(1 - b_tdc/b_tdf) end b_tddef,
    -- Point-in-time takedown attempts per 15 minutes — the PIT twin of the
    -- career td_avg that edges.js willHaveWrestling() gates on.
    case when a_min > 0 then 15*a_tda/a_min end a_tdavg_p,
    case when b_min > 0 then 15*b_tda/b_min end b_tdavg_p,
    case when a_age > 15 and a_age < 60 then a_age end aa,
    case when b_age > 15 and b_age < 60 then b_age end ba,
    -- UFC-only point-in-time win rate, for the Factor Lab replication rows.
    case when a_pf >= 5 then a_pw::numeric/a_pf end a_ufcr,
    case when b_pf >= 5 then b_pw::numeric/b_pf end b_ufcr
  from m
),
r as (
  -- === A: edges.js recordEdge, exact trigger and exact bands ================
  select 'A_record_edgesjs_proPIT' factor,
    case when gap >= 0.40 then 'd. gap>=0.40 (claims 72.0%)'
         when gap >= 0.25 then 'c. gap 0.25-0.40 (claims 70.0%)'
         when gap >= 0.15 then 'b. gap 0.15-0.25 (claims 65.0%)'
         else 'a. gap 0.08-0.15 (claims 60.0%)' end band,
    even, (winner_id = case when a_sm > b_sm then a_id else b_id end) hit
  from (select h.*, abs(a_sm-b_sm) gap from h) z
  where (a_prow+a_prol)+(b_prow+b_prol) >= 3 and gap >= 0.08
union all
  -- === B: edges.js tdDefEdge, point-in-time wrestling gate =================
  select 'B_td_def_edgesjs_PITgate',
    case when gap >= 30 then 'c. gap>=30 (claims 56.0%)'
         when gap >= 20 then 'b. gap 20-30 (claims 54.0%)'
         else 'a. gap 10-20 (claims 52.5%)' end,
    even, (winner_id = case when a_tddef > b_tddef then a_id else b_id end)
  from (select h.*, abs(a_tddef-b_tddef) gap from h where a_tddef is not null and b_tddef is not null) z
  where gap >= 10 and (coalesce(a_tdavg_p,0) >= 1.0 or coalesce(b_tdavg_p,0) >= 1.0)
union all
  -- === C: same, but gated on the CAREER td_avg production actually reads ===
  select 'C_td_def_edgesjs_careergate',
    case when gap >= 30 then 'c. gap>=30 (claims 56.0%)'
         when gap >= 20 then 'b. gap 20-30 (claims 54.0%)'
         else 'a. gap 10-20 (claims 52.5%)' end,
    even, (winner_id = case when a_tddef > b_tddef then a_id else b_id end)
  from (select h.*, abs(a_tddef-b_tddef) gap from h where a_tddef is not null and b_tddef is not null) z
  where gap >= 10 and (coalesce(a_tdavg_c,0) >= 1.0 or coalesce(b_tdavg_c,0) >= 1.0)
union all
  -- === D: same, no gate at all — isolates what the gate is worth ===========
  select 'D_td_def_edgesjs_nogate',
    case when gap >= 30 then 'c. gap>=30 (claims 56.0%)'
         when gap >= 20 then 'b. gap 20-30 (claims 54.0%)'
         else 'a. gap 10-20 (claims 52.5%)' end,
    even, (winner_id = case when a_tddef > b_tddef then a_id else b_id end)
  from (select h.*, abs(a_tddef-b_tddef) gap from h where a_tddef is not null and b_tddef is not null) z
  where gap >= 10
union all
  -- === E/F/G: the retired age heuristic's bands, whole + both cohorts ======
  select 'E_age_all',
    case when gap >= 12 then 'f. 12+ yrs' when gap >= 10 then 'e. 10-11 yrs'
         when gap >= 7 then 'd. 7-9 yrs' when gap >= 5 then 'c. 5-6 yrs'
         when gap >= 3 then 'b. 3-4 yrs' else 'a. 1-2 yrs' end,
    even, (winner_id = case when aa < ba then a_id else b_id end)
  from (select h.*, abs(aa-ba) gap from h where aa is not null and ba is not null) z
  where gap >= 1
union all
  select 'F_age_veteran_5plus_both',
    case when gap >= 12 then 'f. 12+ yrs' when gap >= 10 then 'e. 10-11 yrs'
         when gap >= 7 then 'd. 7-9 yrs' when gap >= 5 then 'c. 5-6 yrs'
         when gap >= 3 then 'b. 3-4 yrs' else 'a. 1-2 yrs' end,
    even, (winner_id = case when aa < ba then a_id else b_id end)
  from (select h.*, abs(aa-ba) gap from h where aa is not null and ba is not null) z
  where gap >= 1 and a_pf >= 5 and b_pf >= 5
union all
  select 'G_age_newcomer_cohort',
    case when gap >= 12 then 'f. 12+ yrs' when gap >= 10 then 'e. 10-11 yrs'
         when gap >= 7 then 'd. 7-9 yrs' when gap >= 5 then 'c. 5-6 yrs'
         when gap >= 3 then 'b. 3-4 yrs' else 'a. 1-2 yrs' end,
    even, (winner_id = case when aa < ba then a_id else b_id end)
  from (select h.*, abs(aa-ba) gap from h where aa is not null and ba is not null) z
  where gap >= 1 and (a_pf < 5 or b_pf < 5)
union all
  -- === V/W/X: replications of the three published Factor Lab factors =======
  -- These exist to prove the harness above reproduces build/factor-rates.js
  -- before any of its results are believed. Note the band convention differs:
  -- the Factor Lab uses (lo, hi], edges.js uses [lo, hi).
  select 'V_ufc_record_factorlab_replica',
    case when gap > 0.30 then 'd. 30+ pts' when gap > 0.22 then 'c. 22-30 pts'
         when gap > 0.15 then 'b. 15-22 pts' else 'a. 10-15 pts' end,
    even, (winner_id = case when a_ufcr > b_ufcr then a_id else b_id end)
  from (select h.*, abs(a_ufcr-b_ufcr) gap from h where a_ufcr is not null and b_ufcr is not null) z
  where gap > 0.10
union all
  select 'W_td_def_factorlab_replica',
    case when gap > 30 then 'c. 30+ pts' when gap > 20 then 'b. 20-30 pts' else 'a. 10-20 pts' end,
    even, (winner_id = case when a_tddef > b_tddef then a_id else b_id end)
  from (select h.*, abs(a_tddef-b_tddef) gap from h where a_tddef is not null and b_tddef is not null) z
  where gap > 10
union all
  select 'X_age_factorlab_replica',
    case when gap > 9 then 'e. 10+ yrs' when gap > 6 then 'd. 7-9 yrs'
         when gap > 4 then 'c. 5-6 yrs' when gap > 2 then 'b. 3-4 yrs' else 'a. 1-2 yrs' end,
    even, (winner_id = case when aa < ba then a_id else b_id end)
  from (select h.*, abs(aa-ba) gap from h where aa is not null and ba is not null) z
  where gap > 0
)
select factor, band, count(*) n, sum(hit::int) w,
  count(*) filter (where even) n_even, sum(hit::int) filter (where even) w_even
from r group by factor, band
union all
select factor, 'zz. ANY (headline)', count(*), sum(hit::int),
  count(*) filter (where even), sum(hit::int) filter (where even)
from r group by factor
order by 1, 2;
