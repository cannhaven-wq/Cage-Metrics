-- Read-only extraction for paper/replay.py and paper/arbitrage.py (2026-10-20).
-- Run each statement; save the JSON payload (not the tool's wrapper) to the named
-- file in a private directory. Never commit the output.
--
-- Sealed partitions (PRED-001): prices only. The ONLY outcome statement is the last
-- one, and it is restricted to event_date >= 2026-10-12 (outside DEV, H1 and RESERVE).

-- quote_rows.json: configured sportsbooks only; one row per fight_odds row
select f.event_id, json_agg(json_build_array(o.id, o.fight_id, o.fighter_id, o.opponent_fighter_id, o.book_id,
       o.american_odds, o.captured_at, o.provider_last_update, o.is_live, o.market_status) order by o.id) rows
from fight_odds o join fights f on f.id = o.fight_id
where f.event_id in (113,114,117,118,2563,2619,2626,4224,4282,4433,4550,4551,4713,4368)
  and o.book_id in (1,3,9,10,11,12,13)
group by 1;

-- quote_rows_ufc333_pm_window.json: the sportsbook capture beside the 2026-10-20 Polymarket capture
select json_agg(json_build_array(o.id, o.fight_id, o.fighter_id, o.opponent_fighter_id, o.book_id, o.american_odds,
       o.captured_at, o.provider_last_update, o.is_live, o.market_status) order by o.id) rows
from fight_odds o join fights f on f.id = o.fight_id
where f.event_id = 4542 and o.book_id in (1,3,9,10,11,12,13)
  and o.captured_at between '2026-10-20 18:00:00+00' and '2026-10-20 19:15:00+00';

-- card_meta.json: cards, bookings (no result columns), provider start estimates with observation times
select json_build_object(
 'events', (select json_agg(json_build_object('event_id', e.id, 'name', e.name, 'event_date', e.event_date) order by e.event_date)
            from events e where e.id in (113,114,117,2563,2619,118,2626,4224,4282,4433,4550,4551,4713,4368,4542)),
 'fights', (select json_agg(json_build_object('id', f.id, 'event_id', f.event_id, 'fighter_a_id', f.fighter_a_id, 'fighter_b_id', f.fighter_b_id,
            'fighter_a_name', f.fighter_a_name, 'fighter_b_name', f.fighter_b_name, 'is_active', f.is_active, 'bout_order', f.bout_order) order by f.id)
            from fights f where f.event_id in (113,114,117,2563,2619,118,2626,4224,4282,4433,4550,4551,4713,4368,4542)),
 'starts', (select json_agg(json_build_object('fight_id', s.fight_id, 'source', s.source, 'start_at', s.start_at, 'observed_at', s.observed_at)
            order by s.fight_id, s.observed_at) from fight_start_estimates s join fights f on f.id = s.fight_id
            where f.event_id in (113,114,117,2563,2619,118,2626,4224,4282,4433,4550,4551,4713,4368,4542))) as meta;

-- outcomes_unsealed.json: results for the one settled card outside every sealed partition
select json_agg(json_build_object('id', f.id, 'fighter_a_id', f.fighter_a_id, 'fighter_b_id', f.fighter_b_id,
       'winner_id', f.winner_id, 'method', f.method, 'is_active', f.is_active) order by f.id)
from fights f join events e on e.id = f.event_id
where f.event_id = 4368 and e.event_date >= date '2026-10-12';
