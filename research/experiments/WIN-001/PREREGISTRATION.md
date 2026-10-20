# WIN-001 — Does a stats-plus-rating formula know anything the closing line does not?

Governed by PRED-001 (`research/protocol/PREDICTION_RESEARCH_PROTOCOL.md`).
**Status: DRAFT, awaiting the owner's approval of the plain version.** Nothing
in this file is frozen until `research/registry.json` records its sha256 with
`status: "frozen"`; until then no look may be requested and no slot is spent.

## Plain version

We built a formula that takes the betting market's closing price and nudges it
using sixteen things we can measure about both fighters before the bell: their
opponent-adjusted rating, UFC win-loss gap, experience, layoff, age, reach,
height, striking pace, strikes absorbed, takedowns landed and allowed,
knockdowns, submission attempts, how often they finish, how often they get
finished, and their win rate. On fights through 2024 it beat the market by a
hair: about 0.0046 log-loss points per fight, roughly half of which comes from
correcting a known bias in how prices are turned into probabilities, not from
the stats. If, on fights that have not happened yet, the formula is not better
than the market by at least 0.003 per fight with the lower end of its range
above zero, the answer is "no" and it stays off the site.

## Hypothesis

- H0: the challenger adds no information to the vig-free BFO closing consensus
  (prospectively: the eligible-book consensus at lock). Δ ≤ 0.
- H1: Δ > 0 on priced, decided UFC fights.
- Target gain δ (≥ 0.004): **0.005**. The DEV walk-forward estimate is 0.0046
  (95% event-bootstrap range 0.0000 to 0.0093, `DEV_RESULTS.md`). 0.005 is the
  smallest permitted round figure at or above that estimate; a larger target
  would be sizing for a gain DEV gave no reason to expect.

## Challenger

- Type: **incremental** (market + model, weights frozen on DEV)
- Form: `logit p = 1.105 × logit(p_market) + Σ wᵢ dᵢ/sᵢ`, no intercept, where
  `dᵢ` are A − B differences and `sᵢ` their DEV standard deviations. All
  weights are in `artifact.json`.
- Model artifact sha256: `3f07179193c3a8ffb9237f81b2a35256c7bb2f43fe352d6af8af9e12e970120c`
  (`artifact.json`, produced by `freeze_artifact.py`; re-running reproduces the
  bytes). Code commit: the commit that freezes this file, recorded in the
  registry entry.
- Training window: DEV only, 1994-03-11 → 2024-12-14, 6,824 priced decided
  fights across 623 events. The DEV export's id and outcome fingerprints equal
  the manifest's `partitions.DEV` hashes (`DATA.md`).
- Variants tried on DEV (an honest count of configurations compared): **7** —
  six blends (`market_only`, `elo`, `elo_age_record`, `full_c1`, `full_c01`,
  `full_c001`, see `model.py::VARIANTS`) and one standalone reading of the full
  set. `full_c1` was chosen for the highest walk-forward Δ.
- Features chosen using any all-years result (Factor Lab, a published
  benchmark)? **Yes.** Age and the UFC win-loss gap were included because the
  Factor Lab, which scores all years including H1, reports them as surviving
  market control. **Per PRED-001 §2 any H1 result for this experiment is
  non-confirmatory.** The remaining fourteen features are standard matchup
  measurements chosen before any result was seen.

## Feature manifest

All computed by `features.py::build_rows` from fights dated strictly before
`event_date`, state advanced once per event date (same-night bouts never
feed each other). Rates are exponentially decayed (half-life three years)
with one fight's worth (15 minutes) of league-average pace as a prior.

| feature | source table.column | time rule | static? |
|---|---|---|---|
| elo | fights.winner_id, method (K = 32, start 1500) | before date | no |
| ufc_gap | fights.winner_id (wins − losses in the fights table) | before date | no |
| n_fights | fights (count) | before date | no |
| log_layoff | events.event_date (days since last fight, log1p) | before date | no |
| age | fighters.dob, events.event_date | computed at fight date | dob static (declared caveat) |
| reach | fighters.reach_in | present-day profile value | yes (declared caveat) |
| height | fighters.height_in | present-day profile value | yes (declared caveat) |
| sl_pm | fights.a/b_sig_str_landed ÷ fight minutes | before date, decayed | no |
| sa_pm | opponent's sig_str_landed ÷ minutes | before date, decayed | no |
| td_p15 | fights.a/b_td_landed per 15 min | before date, decayed | no |
| tdd_p15 | opponent's td_landed per 15 min | before date, decayed | no |
| kd_p15 | fights.a/b_kd per 15 min | before date, decayed | no |
| sub_p15 | fights.a/b_sub_attempts per 15 min | before date, decayed | no |
| finish_rate | wins not by decision ÷ fights, Laplace (1, 2) | before date | no |
| finished_rate | losses not by decision ÷ fights, Laplace | before date | no |
| win_rate | wins ÷ fights, Laplace | before date | no |
| logit_market | fight_odds BFO closer, proportional de-vig | the price the model reads | — |

Fight minutes come from `fights.end_round` / `end_time` of the **past** fight
(its own result, used only after it is over), falling back to the scheduled
length for decisions. Per-fight totals are the `fights` wide columns, with
`fight_rounds` sums filling a null corner. No `fighters` career column is read
except `dob`, `height_in`, `reach_in`.

## Benchmark

- Primary: BFO close (H1); the eligible-book consensus at lock (prospective),
  with CLV-001's closing proxy reported beside it.
- De-vig: proportional (primary); power and Shin reported.
- **Declared decomposition, reported never decisive:** the `market_only`
  variant (the market logit re-scaled, no stats) is scored beside the
  challenger at every look. On DEV it carries 0.0022 of the 0.0046. The gain
  attributable to the stats is the challenger's Δ minus `market_only`'s Δ, and
  the write-up states it.

## Population and eligibility

PRED-001's: UFC fights with both fighters set, a decided winner (draws and
no-contests excluded), `is_active IS DISTINCT FROM false`, both corners priced
by the benchmark, not fights 43, 46, 8780. No division, round or title
restriction. Nothing else is excluded.

## Sample size

- SD used: max(0.064, DEV-measured SD = 0.1187) = **0.119**. The blend's
  fitted market weight lets it disagree with the market more than the fixed
  80/20 blend the floor was measured on, so its per-fight spread is nearly
  twice the floor.
- n_required (prospective): **5685** = `required_n(0.119, 0.005, 0.01, 0.8, mue=0.003)`.
  At about 480 priced fights a year that is roughly **twelve years**. This is
  stated here so nobody is surprised later: a gain this small, with this
  spread, is not confirmable in a product timescale, and PRED-001 §6 says that
  is a finding.
- Analysis trigger: the first n_required eligible locks, in lock order, taken
  whole cards at a time.
- H1 can detect about 0.015 at this SD on 710 fights — exactly the leak
  tripwire — so an H1 look would almost certainly return INCONCLUSIVE and, per
  the declaration above, would be non-confirmatory anyway. **This
  preregistration does not request an H1 slot.**

## Registry entry (research/registry.json)

```pred-registration
{
  "experiment_id": "WIN-001",
  "protocol": "PRED-001",
  "model_class": "incremental",
  "model_artifact_sha256": "3f07179193c3a8ffb9237f81b2a35256c7bb2f43fe352d6af8af9e12e970120c",
  "target_effect": 0.005,
  "sd_used": 0.119,
  "n_required": 5685,
  "author_sessions": ["session_017sMsVkbvovsKrTqJSLafJi"],
  "code_paths": ["research/experiments/WIN-001/features.py", "research/experiments/WIN-001/model.py"]
}
```

## Stages requested

- [ ] H1 evaluation — **not requested** (non-confirmatory by declaration, and
  underpowered by a factor of three at this SD).
- [ ] Prospective test (spends 1 of 5 slots; needs locks in `win_model_locks`
  before every priced bout on every card from the first locked card, L3).
  Requested **only on the owner's approval of this draft**.

## Pre-stated interpretation

- REJECT: the formula does not carry usable information beyond the closing
  line. It stays off every public surface; D-011 stands. The result is written
  up in the open, losses at equal prominence.
- INCONCLUSIVE / UNDERPOWERED: nothing is claimed. The lock schedule continues
  only if the owner renews it; no public number.
- PASS_H1: not applicable (no H1 look requested).
- PASS_PROSPECTIVE: "added information beyond the market on N fights forecast
  in advance". Public use still needs the owner (L3 item 8), does not lift
  D-011 by itself, and the `market_only` decomposition is published beside it
  so a gain that is only a de-vig correction is named as one.

## Amendments

None.
