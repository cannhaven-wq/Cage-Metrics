# WIN-001 data: the DEV export

Pulled 2026-10-20 from the production database through the read-only SQL
tool, into three CSV files. Every row is dated **before 2025-01-01**: the
statements below carry that predicate, and `dev_walkforward.py` passes every
row through `pred_protocol.dev_only()`, which raises on a sealed date. No
sealed row was read, requested or displayed.

| file | rows | sha256 |
|---|---|---|
| `data/fights_dev.csv` | 7,974 fights, 1994-03-11 → 2024-12-14 | `891ec74d7bd09b951172de8d7a217e1fecf19c44636ecd0ec3ba06dd4082d9be` |
| `data/fighters_dev.csv` | 2,550 fighters (dob, height_in, reach_in, stance) | `de6ba769a9140e465dc1c33dc1daec8054f0b1cafbd181e6cbb79df168c8c6ad` |
| `data/closing_dev.csv` | 6,953 fights with a BFO closer on both corners (American odds, ints) | `64405e9279687d706e0e0f20f209324ede97c3b04233b1f0df0711d0d6d3762d` |

**Fingerprint check against the frozen manifest.** Applying the manifest's
eligibility (decided winner in the corners, both corners priced by BFO, not
43/46/8780; no DEV fight is `is_active = false`) to this export gives 6,824
fights across 623 events, and

- ids sha256 `25b2e735595274bd3089b9968ed79fb9899215247cbed7bd6f8b8b7148fcbff7`
- outcomes sha256 `f1b1141dd03578b3aee895b2c4d7276da0b6aa2a01e49a2c4e4e8bb41b728e5d`

both equal to `research/protocol/holdout_manifest.json → partitions.DEV`. The
data the model was fitted on is the data the protocol sealed as DEV.

## Statements used

Fights (paged `limit 1000 offset k`, k = 0 … 7000, ordered by id):

```sql
with r as (
  select fight_id, fighter_a_id, fighter_b_id,
    sum(a_sig_str_landed) a_sl, sum(b_sig_str_landed) b_sl,
    sum(a_sig_str_attempted) a_sa, sum(b_sig_str_attempted) b_sa,
    sum(a_td_landed) a_tl, sum(b_td_landed) b_tl,
    sum(a_td_attempted) a_ta, sum(b_td_attempted) b_ta,
    sum(a_sub_attempts) a_sub, sum(b_sub_attempts) b_sub,
    sum(a_kd) a_kd, sum(b_kd) b_kd,
    sum(a_ctrl_seconds) a_ctrl, sum(b_ctrl_seconds) b_ctrl
  from fight_rounds group by 1,2,3)
select f.id, f.event_id, e.event_date, f.fighter_a_id a, f.fighter_b_id b,
  f.winner_id w, f.method m, f.weight_class wc, f.scheduled_rounds sr,
  f.end_round er, f.end_time et, f.is_title_fight t,
  coalesce(f.a_sig_str_landed, r.a_sl) a_sl, coalesce(f.b_sig_str_landed, r.b_sl) b_sl,
  coalesce(f.a_sig_str_attempted, r.a_sa) a_sa, coalesce(f.b_sig_str_attempted, r.b_sa) b_sa,
  coalesce(f.a_td_landed, r.a_tl) a_tl, coalesce(f.b_td_landed, r.b_tl) b_tl,
  coalesce(f.a_td_attempted, r.a_ta) a_ta, coalesce(f.b_td_attempted, r.b_ta) b_ta,
  coalesce(f.a_sub_attempts, r.a_sub) a_sub, coalesce(f.b_sub_attempts, r.b_sub) b_sub,
  coalesce(f.a_kd, r.a_kd) a_kd, coalesce(f.b_kd, r.b_kd) b_kd,
  coalesce(f.a_ctrl_seconds, r.a_ctrl) a_ctrl, coalesce(f.b_ctrl_seconds, r.b_ctrl) b_ctrl
from fights f join events e on e.id = f.event_id
left join r on r.fight_id = f.id and r.fighter_a_id = f.fighter_a_id and r.fighter_b_id = f.fighter_b_id
where not e.is_upcoming and e.event_date < '2025-01-01'
order by f.id limit 1000 offset :k;
```

Fighters:

```sql
select fi.id, fi.dob, fi.height_in h, fi.reach_in r, fi.stance s
from fighters fi
where fi.id in (select f.fighter_a_id from fights f join events e on e.id = f.event_id
                 where not e.is_upcoming and e.event_date < '2025-01-01'
                union
                select f.fighter_b_id from fights f join events e on e.id = f.event_id
                 where not e.is_upcoming and e.event_date < '2025-01-01')
order by fi.id;
```

Closing prices (BestFightOdds closing consensus only, the manifest's
benchmark; keyed by fighter id, never by the capture's side label), then
pivoted locally to one row per fight with `american_a` / `american_b`:

```sql
with bfo as (select id from odds_books where name ilike 'BFO%')
select o.fight_id f, o.fighter_id p, max(o.american_odds) am
from fight_odds o join fights fi on fi.id = o.fight_id join events e on e.id = fi.event_id
where o.book_id in (select id from bfo) and o.is_closer
  and not e.is_upcoming and e.event_date < '2025-01-01'
  and o.fighter_id in (fi.fighter_a_id, fi.fighter_b_id)
group by 1, 2 order by 1, 2;
```

A check that no DEV fight is a dead booking (`is_active = false` with
`event_date < '2025-01-01'`) returned zero rows, so the export carries no
`is_active` column.

## For the auditor

The same three statements with the date predicate removed give the whole
history; `features.py::build_rows` on that table yields the H1 features
point-in-time (fights from 2025 that precede an H1 bout feed its features,
as they should). `model.predict(artifact, rows, p_market)` then gives
`p_model` per fight. No H1 look is requested by this preregistration.
