# Discovery Engine Phase 1 — what it found

**Dated 2026-10-21. Research artifact, DEV data only (every fight before
2025-01-01). Nothing in production changed. Exploratory under PRED-001 §9: it
supports no statement outside the research folder.**

> **Dated correction, 2026-10-21 (consolidation audit, D-034).** Read this
> report with three corrections; the text below is otherwise left as written.
> (1) **E4:** the configuration and catalog code were committed 33 seconds
> after this run started, so it is not demonstrably preregistered before
> execution; its config and code hashes do match the committed files.
> (2) The "market under-confident in 2019-24" context result (§3, §4.1)
> depends on the de-vig: +0.0023 proportional, +0.0002 power, +0.0008 Shin
> (`research/consolidation/AUDIT_2026-10-21.md` §4.1). It is mostly an
> artefact of the proportional method, not a property of the market.
> (3) Engine defects E1-E3 did not affect any result here (no candidate
> reached the code where they live) and are fixed in engine 1.1.0.
> (4) The DEV export is no longer committed: where §1-§2 say the data is in
> `data/dev/`, it is now obtained as `research/discovery/WITHHELD.json` says,
> and checked against the same hashes.

Run of record: [`runs/20261021T200151Z-phase1/`](runs/20261021T200151Z-phase1/SUMMARY.md),
ledger entry 1. Synthetic demonstration: [`runs/20261021T202341Z-demo-synthetic/`](runs/20261021T202341Z-demo-synthetic/SUMMARY.md), ledger entry 2 (see §6).

---

## Plain verdict

**Nothing we tried tells you more about who wins than the closing betting price
already does.** We tested 660 ideas — 44 fight factors and 616
"factor in this situation" combinations — on 6,824 priced UFC fights from 2007
to 2024. None passed the first screen once we allowed for how many we tried.
The best real idea scored *below* what the best of 660 random coin-flip
factors typically scores. The factors that looked a little useful in
2010–2018 were, as a group, slightly *worse* than useless in 2019–2024.

That is a finding, not a failure of the tool. The same machinery, run on a
labelled synthetic world with one hidden real effect, finds that effect,
finds nothing in a world without one, and refuses an effect that is too good
to be true (§6).

---

## 1. What was asked and what changed

| deliverable | where |
|---|---|
| Offline discovery on permitted DEV data | `cfl_discovery/run.py`; data in `data/dev/` (SQL-filtered to before 2025, then re-checked by PRED-001's own `dev_only()`) |
| Candidate features and interactions | 44 antisymmetric features (engine history, extra history, physical, style, matchup, market) × 14 situations; `features.py`, `candidates.py` |
| Walk-forward, train/test separation | fitted only on earlier years; screen 2010–2018, confirm 2019–2024; `evaluate.py` |
| Against the de-vigged market by log loss | PRED-001's incremental form: `logit p = (1+g)·logit(q_close) + b·x`; proportional de-vig primary, power and Shin as sensitivities |
| Leakage, sample floors, card-level uncertainty, stability, multiple testing | `leakage.py` (4 audits + tripwires + self-check), sample floors in `config/phase1.json`, card-clustered errors and bootstrap, split Benjamini–Hochberg + Holm + 100-shuffle permutation null, year/fold/de-vig stability |
| Machine-readable report + readable summary | `runs/<id>/results.json`, `runs/<id>/SUMMARY.md` |
| Every hypothesis, config and failure kept | `catalog.json` hashed before scoring, `shortlist.json` hashed before confirmation, hash-chained `ledger.jsonl`, tests that fail if a run or file disappears |
| Tests, commands, demonstration | `tests/test_discovery.py` (32 tests), `README.md`, this report |

**Reused, not rebuilt:** `research/protocol/pred_protocol.py` (DEV guard, de-vig,
log loss, card bootstrap, calibration, sample size, symmetry checker),
`cfl_engine/engine.py` (point-in-time career features and Elo),
`cfl_engine/clv/devig.py` (power and Shin). None of them was edited.

**Not touched:** any database, scraper, page, workflow, frozen protocol file,
registered experiment, the registry, the holdout ledger, or the H1/RESERVE
fights. No paid service.

## 2. The data, and how we know it is the right data

The export (`export_dev.sql`, read-only) holds all 7,974 DEV fights (history
needs the unpriced ones too). Its 6,824 priced, decided fights reproduce
PRED-001's frozen DEV fingerprints exactly — the id hash
`25b2e735…cbff7` and the outcome hash `f1b1141d…8e5d` in
`holdout_manifest.json`. The loader recomputes both on every load and refuses a
file that drifted; a test flips one outcome and checks it is refused. The last
event in the file is 2024-12-14.

## 3. Results

### The market

| period | fights | cards | market log loss | market after re-weighting its own number | market picks right |
|---|---|---|---|---|---|
| 2010–2018 (screen) | 3,509 | 321 | 0.6117 | 0.6115 | 65.7% |
| 2019–2024 (confirm) | 2,826 | 253 | 0.6061 | 0.6038 | 67.0% |

### The 660 tested ideas

| outcome | count |
|---|---|
| research lead | 0 |
| held up but too small to matter | 0 |
| unstable | 0 |
| failed confirmation | 0 |
| rejected at the screen | 585 |
| too few informative fights to judge | 75 (5 features × their 15 forms: switch stance, KO loss last time, lost last time, weight-class move, debut-vs-veteran) |
| leak suspect | 0 |

How thin the evidence is, in four numbers:

- **1 of 585** judgeable ideas reached p < 0.05 before any correction. Pure
  chance would give about 29. Out-of-sample testing charges an idea for the
  noise it fits, so useless ideas tend to *lose* a little.
- Only **16%** of ideas improved on the market at all in 2010–2018, and
  **26%** in 2019–2024.
- The **correlation between an idea's 2010–2018 gain and its 2019–2024 gain
  is −0.19**. What looked better earlier looked worse later: no persistence.
- **Best real z = 1.73.** Under 100 shuffles that destroy every real
  relationship, the best of 660 ideas reaches z = 2.26 at the median and
  3.06 at the 95th percentile.

### Factors earlier CFL work called real

| factor | gain over the re-weighted market, 2010–18 | 2019–24 (95% range by card) | reading |
|---|---|---|---|
| Age gap | +0.0003 (p 0.41) | +0.0001 (−0.0020 to +0.0023) | the coefficient leans "younger fighter" in both periods, but the forecast is no better |
| UFC record, raw win rate | +0.0004 (p 0.08) | +0.0001 (−0.0009 to +0.0011) | nearest single-factor miss; does not hold up |
| UFC record, wins minus losses | −0.0004 | −0.0000 | nothing |
| Recency-weighted win rate | +0.0005 (p 0.12) | −0.0002 | gone in 2019–24 |
| Elo | −0.0003 | +0.0000 | nothing |
| Reach | +0.0001 | +0.0002 | nothing |
| Takedown defence | +0.0002 | **−0.0009 (−0.0015 to −0.0003)** | made forecasts worse in 2019–24 |

This does **not** contradict FE-001 or the Factor Lab. Those count how often
the younger, or better-recorded, fighter wins among fights the market priced
near even. This run asks a stricter question: does knowing the factor make a
better *probability* than the price, across every priced fight? A factor can
tilt a win rate in one band and still add nothing measurable to the price as a
whole. The two results answer different questions; neither should be quoted
as the other.

### Near-misses, and what became of them

The twelve ideas closest to passing the 2010–2018 screen are listed in the
run's `SUMMARY.md`. Their 2019–2024 numbers were computed and kept; **none was
positive with a range clear of zero, and 10 of 12 went negative**. They were
never shortlisted, so this is description, not a second chance.

### Context models (not tested; shown so the whole picture is visible)

| model | gain vs market 2019–24 | 95% range | gain vs re-weighted market |
|---|---|---|---|
| all 22 engine features at once | +0.0007 | −0.0043 to +0.0054 | −0.0016 |
| all 44 features at once | −0.0007 | −0.0060 to +0.0045 | −0.0030 |
| market-shape only (line move + favourite/long-shot bend) | +0.0022 | +0.0008 to +0.0035 | −0.0000 |
| stats only, **no market input** | **−0.0537** | −0.0634 to −0.0437 | — |

Two things worth saying:

1. **The stats-only model is 0.054 log loss worse than the market**, the same
   size as the engine's measured deficit in PRED-001 §0 (0.054 on 3,068
   fights). An independent pipeline landing on the same number is a useful
   check that this one is not broken.
2. **The only clearly positive context number is the market correcting
   itself.** In 2019–2024 the closing consensus was slightly under-confident:
   the calibration slope was 1.23, meaning favourites won a little more often
   than priced. Re-weighting the market's own number gained +0.0023. In
   2010–2018 the slope was 1.05 and the gain +0.0002. This is not a fight
   factor. It is below PRED-001's 0.003 bar. And it appeared in one period
   only.

### Integrity checks on the real run

| check | result |
|---|---|
| sources against PRED-001's forbidden list | clean |
| corner-label readers | none |
| point-in-time rebuild: 25 random cards, 295 fights, 58 features, each card's own results scrambled | 0 mismatches |
| corner-swap rebuild of every feature | exact (market error 2e-16) |
| PRED-001 `symmetry_violations` on fitted models | 0 |
| planted-leak self-check | tripwire fired (+0.2012) |
| noise controls (40) | 0 below p 0.05, 0 would pass the corrected screen |

## 4. What might justify more research

Nothing here earns a PRED-001 preregistration as it stands. Three directions
are worth a *written* hypothesis before anyone looks at more data:

1. **Market calibration drift.** The 2019–24 under-confidence (slope 1.23) is
   the largest effect seen. It is a property of the price, not the fight. A
   preregistration would have to say in advance which window it will be
   judged on, and the honest prior from 2010–18 is "small".
2. **Better inputs, not more combinations of these.** Every feature here is a
   recency-weighted average of UFCStats totals plus four profile values. The
   market already prices all of that. Information the closing price plausibly
   lacks is not in the database (see §5).
3. **Round-level and opponent-adjusted measures.** For example, output
   against opponents of known defensive quality, or late-round fade from
   `fight_rounds`. These were deliberately left out of Phase 1 to keep the
   first family small. Adding them is a *new* family with its own
   correction, not a re-run of this one.

## 5. What additional evidence would be needed, and what is unavailable

- **To confirm a gain of 0.004 prospectively takes about 2,900 fights forecast
  in advance (≈ 6 years at 480 a year).** At 0.006 it takes about 1,140;
  PRED-001 §6 has the table. Nothing in this run is large enough to make that
  wait shorter.
- **Unavailable in the data, so not tested:**
  - opening and closing times (BFO's are 1970 placeholders), so line movement
    is ordered, not timed;
  - an executable historical price;
  - card position (`bout_order` is empty in DEV);
  - pre-UFC records;
  - short-notice replacements, missed weight, injuries, camps;
  - any per-book history before 2026-09-19.
- **Present-day values used as fixed:** height, reach, stance, date of birth
  (PRED-001 §3 caveat). 77 fighters have no stance.
- **The confirmation period is now used.** 2019–2024 has been looked at once,
  by this run. A future discovery run that confirms on the same years has
  fewer independent tries left in it. The ledger records how many times it has
  been used, so the next reader can discount it.

## 6. Demonstration on labelled synthetic data

`python -m cfl_discovery --data synthetic` builds a fake world of 4,752 fights
in the export's exact shape, with:

- a market that prices hidden skill well;
- one planted effect the market does not price: reach;
- the favourite in corner A 64% of the time, as in real UFC data.

| world | what the engine did |
|---|---|
| reach effect planted (0.22) | **reach found as a research lead**, gain over market +0.0105 (2019–24 range +0.0027 to +0.0184), positive in 93% of years. Height also flagged: in this world height is built from reach, so it is a genuine proxy. The engine cannot tell a cause from its stand-in, and the report says so. |
| no effect | nothing passed the screen |
| effect too strong (0.45) | reach quarantined as a leak suspect: above the 0.015 tripwire, never shortlisted |
| 40 noise controls, every world | none passed the corrected screen |

The planted-world run is committed as ledger entry 2 so it can be inspected
next to the real run. The null and too-strong worlds run inside
`tests/test_discovery.py` on every test run.

## 7. Restrictions, checked

| restriction | how it was kept |
|---|---|
| PRED-001 exactly | DEV only; its thresholds are read from `protocol.json` and a config that differs is refused; its metric, de-vig, bootstrap seed and symmetry checker are imported, not copied |
| no sealed outcomes, no holdout look | the export filters in SQL; the loader raises on a sealed row; no `run_look`, no ledger entry, no H1 id read |
| frozen models and experiments untouched | no file under `research/protocol/`, `cfl_engine/` or `research/registry.json` changed; the PRED-001 tests still pass |
| no production, scraper or site change | the only production access was read-only SELECTs (§2) |
| no paid service | none |
| no claim that consensus odds were bettable | no betting return computed; every summary says the price was never bettable |
| no automatic promotion | the highest tier is `RESEARCH_LEAD`, which licenses a written preregistration only |
| report unavailable data | §5 |
