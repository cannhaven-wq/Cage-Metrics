-- card_population.sql — PRED-001: which bouts each card SHOULD have locks for.
--
-- Read-only. Produces the card_population argument of pred_protocol.evaluate /
-- run_look for one experiment: every card from the experiment's first locked
-- card onward, its start, and the bouts that had a two-sided price from a real
-- sportsbook before that start. Its sha256 is folded into the look's
-- fight_ids_sha256, so a third party re-running this recipe gets the same hash
-- or knows the population differs.
--
-- Why it exists: selective locking (forecasting only the fights or cards one
-- likes, or rolling back a savepoint after the results) is the prospective
-- form of cherry-picking. A look is INVALID unless EVERY bout listed here for
-- a card in the scored run has a lock row - a forecast, or an abstention lock
-- (p_a NULL) written before the bell.
--
-- "Priced" means a two-sided sportsbook price captured before the EARLIER of
-- the card's start and the experiment's last lock on that card. A bout first
-- priced after the last lock pass (a late replacement) could not have been
-- locked, so it is not owed one.
--
-- Start of a card: the same rule the lock guard uses - the earliest best-known
-- start of any bout, with an event-date fallback counted from 00:00 UTC.
-- Sportsbooks: v_odds_books_sportsbooks (no consensus rows, no prediction
-- markets). "Two-sided" = both corners quoted by the same book.
--
-- Parameter: replace :experiment_id with the experiment, e.g. 'PRED-002'.

with first_card as (
  select min(e.event_date) as d
    from public.win_model_locks l join public.events e on e.id = l.event_id
   where l.experiment_id = :experiment_id),
cards as (
  select s.event_id,
         min(case when s.start_basis = 'event_date_fallback'
                  then (s.event_date::timestamp at time zone 'UTC') else s.start_at end) as card_start
    from public.v_fight_start_best s, first_card
   where s.event_date >= first_card.d
     and s.event_date < current_date        -- only cards that have happened
   group by s.event_id),
last_lock as (
  select l.event_id, max(l.actual_lock_at) as at
    from public.win_model_locks l
   where l.experiment_id = :experiment_id
   group by l.event_id),
two_sided as (
  select o.fight_id
    from public.fight_odds o
    join public.v_odds_books_sportsbooks b on b.id = o.book_id
    join public.fights f on f.id = o.fight_id
    join cards c on c.event_id = f.event_id
    left join last_lock ll on ll.event_id = c.event_id
   where o.captured_at < least(c.card_start, coalesce(ll.at, c.card_start))
     and o.captured_at > timestamptz '1990-01-01'
   group by o.fight_id, o.book_id
  having count(distinct o.fighter_id) filter (where o.fighter_id in (f.fighter_a_id, f.fighter_b_id)) = 2)
select c.event_id,
       c.card_start as start,
       coalesce(array_agg(distinct f.id order by f.id) filter (where t.fight_id is not null), '{}') as priced
  from cards c
  join public.fights f on f.event_id = c.event_id and f.is_active is distinct from false
  left join (select distinct fight_id from two_sided) t on t.fight_id = f.id
 group by c.event_id, c.card_start
 order by c.card_start, c.event_id;
