# DISC-001 — Which fight factors add anything the betting odds don't already know?

**Internal research. Development data only (fights before 2025-01-01).**
Nothing here goes on a public page (CLAUDE.md, D-011). Any public use of a
result is a published claim, L3 item 8, owner only.

Written and committed **before** any data was exported or any result
computed. The factor list, the transforms, the thresholds and the verdict
rules below are fixed by that commit. A factor added later is a new
experiment (DISC-002), not a row slipped into this one.

## Plain version

For each factor on a fixed list (knockout losses, layoffs, activity, opponent
quality, rematches, common opponents and so on), we ask one question: if you
already know the closing odds, does knowing this factor make the forecast any
better? Every factor gets a verdict, including the ones that add nothing, and
"adds nothing" is the expected answer for most of them.

## What this is and is not

- **Exploratory, DEV only.** It ranks hypotheses. It confirms nothing. A
  factor that survives here is a *candidate* for a future PRED-001 experiment
  with its own preregistration, sealed-set look and prospective test.
- **Not a betting test.** The benchmark is BFO's historical closing
  consensus, which nobody could bet at a known time (BT-001,
  `research/backtest/RESULTS_2026-10-21.md`). A gain here is information,
  never a return.
- **No sealed outcome is read.** The export is filtered to
  `event_date < 2025-01-01` at the source, and the loader passes every row
  through `pred_protocol.dev_only()`, which raises on a sealed date.

## Data

- **Export:** `research/factors/disc001_dev_export.sql` (outside this folder,
  because experiment code may not name a database route), run once, read-only.
  Output committed as `data/dev_fights.csv` and `data/dev_fighters.csv`.
- **History:** every UFC fight in `fights` dated before 2025-01-01 with both
  fighter ids and `is_active` not false. Draws, no-contests and overturned
  results count as fights for activity and layoff, never as wins or losses.
- **Only UFC fights are visible.** A fighter's pre-UFC record is not in the
  table. "Prior fights" below means prior UFC fights. That is a known limit,
  stated beside every result.
- **dob** from `fighters.dob` (allowed with caveat, PRED-001 §3).
- **Market:** BFO closing consensus (`odds_books.name ILIKE 'BFO%'`,
  `is_closer`), one price per corner, corners assigned by `fighter_id`,
  exactly as `research/protocol/holdout_manifest.sql` does.

## Scored set

A fight is scored when all of these hold:

1. decided: `winner_id` is one of the two fighters;
2. both BFO closers present, each within 100-to-1 (|American| ≤ 10000);
3. not fight 43, 46 or 8780 (rebooked in place);
4. its event year is a walk-forward test year: **2012 through 2024**.

## Point-in-time rule

Every feature for a fight is computed only from fights on **events dated
strictly before** that fight's event date. Same-card results never count.
A self-check recomputes every feature for 200 randomly drawn scored fights
(seed 20261021) from a history physically truncated at that date, with a
separate, naive implementation, and the run fails on any difference.

## Model

For fight i, with m = proportional vig-free market probability for corner A:

- **Baseline B0 (recalibrated market):** p = σ(a · logit m).
- **Single-factor model M_k:** p = σ(a · logit m + β · d_k), where
  d_k = g_k(A) − g_k(B) (or an antisymmetric pairwise value for the
  matchup factors), standardised by its training-window SD.

There is no intercept and every feature is antisymmetric, so
p(A beats B) = 1 − p(B beats A) exactly: the corner label carries no
information. `pred_protocol.symmetry_violations` is run on every fitted model
and any violation fails the run.

When a factor is undefined for either fighter (for example a UFC debut), d_k = 0
for that fight: the model falls back to the baseline and the fight adds zero.
Abstaining cannot help.

**Why the primary benchmark is the *recalibrated* market and not the raw
one.** BFO closing prices are known to be slightly miscalibrated (the
favourite-longshot bias). A factor fitted with a free market slope would
otherwise be credited with fixing that bias. Gains over the raw market are
reported beside, never decisive.

**Fitting:** maximum likelihood, Newton-Raphson, on every scored-eligible fight
(rules 1–3) in years before the test year; predict the test year; step forward
one year. Expanding window. Coefficients are refitted each year.

## Primary endpoint

G_k = mean over scored fights of [LL(B0) − LL(M_k)], out of sample, in nats per
fight. Positive means the factor helped.

**Uncertainty:** whole cards resampled, 10,000 times, seed 20261012
(`pred_protocol.cluster_bootstrap`). One-sided p = (number of resampled means
≤ 0, plus 1) / 10,001.

## Primary family — 20 factors

All "prior" counts are prior UFC fights, point in time. Unless noted, a factor
is undefined for a fighter with no prior UFC fight.

| id | factor | per-fighter value g(·) | notes |
|---|---|---|---|
| F01 | KO/TKO losses | count of prior losses by `KO/TKO` | doctor's stoppage excluded (cuts, not knockouts) |
| F02 | KO/TKO loss in the last year | 1 if a KO/TKO loss within 365 days before this fight | |
| F03 | Coming off a KO/TKO loss | 1 if the most recent prior fight was a KO/TKO loss | |
| F04 | Repeat KO/TKO losses | 1 if two or more prior KO/TKO losses | |
| F05 | Knockout damage, fading with time | Σ over prior KO/TKO losses of exp(−days since / 730) | |
| F06 | Knockdowns absorbed | total knockdowns suffered in prior fights (`a_kd`/`b_kd` of the opponent) | |
| F07 | Layoff length | log(days since the most recent prior fight) | |
| F08 | Long layoff | 1 if 365 or more days since the most recent prior fight | |
| F09 | Quick turnaround | 1 if 90 or fewer days since the most recent prior fight | |
| F10 | Recent activity | number of prior fights in the 730 days before this fight | |
| F11 | UFC experience | log(1 + prior fights) | **defined for debuts** (value 0) |
| F12 | Accumulated cage time | log(1 + total minutes fought in prior fights) | full rounds at 5 minutes plus the final round's clock |
| F13 | Age | years between `dob` and the event date | **H1-contaminated** (chosen from an all-years Factor Lab verdict); reference only |
| F14 | UFC win rate | (wins + 1) / (decided prior fights + 2) | **H1-contaminated**; reference only |
| F15 | Opponent quality | mean, over prior fights, of the opponent's UFC win rate (as F14) **as it stood on that earlier fight's date** | |
| F16 | Momentum (win streak) | current streak: +n after n straight wins, −n after n straight losses, capped at ±5; draws and no-contests end a streak at 0 | stand-in for ranking momentum, which has no source table |
| F17 | Rematch | pairwise: +1 if A won their most recent previous meeting, −1 if B won, 0 if no previous meeting or it was not decided | undefined (d = 0) when the pair has never met |
| F18 | Common opponents ("MMA math") | pairwise: over opponents both fought before this date, mean of [A's result score vs C − B's result score vs C], score W = 1, D/NC = 0.5, L = 0, averaged per opponent first | undefined when no common opponent |
| F19 | First five-round fight | 1 if this fight is scheduled for 5 rounds and the fighter has had no prior fight scheduled for 5 rounds | zero for every 3-round fight; **defined for debuts** |
| F20 | First main event | 1 if this fight is the main event and the fighter has had no prior main event | zero for every non-main event; **defined for debuts** |

F13 and F14 stay in the family (they cost a multiple-comparison slot like
everything else) but are reported under "reference — already contaminated" and
cannot be named a candidate for a sealed-set test as historical evidence.

## Interaction family — 3 interactions

Each is judged by the gain over a model that already holds its main effects,
fitted the same way. d_xy = x(A)·y(A) − x(B)·y(B) unless stated.

| id | interaction | x | y | main effects in the comparison model |
|---|---|---|---|---|
| I1 | KO/TKO loss × quick return | F03 | 1 if 180 or fewer days since the most recent prior fight | F03 and that 180-day indicator |
| I2 | Rematch × how the first meeting ended | F17 (pairwise) | 1 if the previous meeting ended by KO/TKO or submission (same for both corners) | F17. Feature is F17 × y |
| I3 | First main event × opponent's main-event experience | F20 | log(1 + the *opponent's* prior main events) | F20 and log(1 + own prior main events) as a difference |

Venue altitude, travel, camp location, time zones, injuries, media attention
and ranking momentum are **not** tested here: the data does not exist in the
database (or, for venue altitude, needs an elevation source this experiment
does not add).

## Combined models — 2, declared now

- **C1:** all 20 primary factors together.
- **C2:** the 18 primary factors excluding F13 and F14 (clean of H1
  contamination).

Ridge penalty on the standardised factor coefficients, λ = 5 (in units of
summed log-likelihood), the market slope unpenalised. Same walk-forward, same
endpoint, same bootstrap. Reported, not part of the Holm family.

No model is built from "the factors that passed": choosing members by their
DEV result and scoring the choice on the same DEV years is selection on the
answer.

## Verdicts

Holm's step-down correction at family-wise α = 0.05, applied separately to the
primary family (20) and the interaction family (3).

| verdict | plain label | rule |
|---|---|---|
| `TOO_FEW` | Not enough fights | fewer than 300 scored fights where d_k ≠ 0 |
| `CANDIDATE` | Adds information — worth a proper test | survives Holm |
| `HINT` | A hint, probably noise | one-sided p < 0.05 but does not survive Holm |
| `NOTHING` | Adds nothing measurable | anything else |

Reported beside every verdict, never changing it: G_k with its 95% card-bootstrap
range; the gain over the raw market; scored fights where the factor fired; the
fitted direction (which fighter it favours) and in how many of the 13 test
years the yearly coefficient had that sign; whether G_k reaches PRED-001's
minimum useful effect of 0.003.

A `CANDIDATE` below 0.003 is labelled "real but probably too small to matter".
PRED-001 §6: the sealed set can only detect about 0.008 for a blend.

## Disclosure

- **Variants tried:** one. This file is the only configuration. If the run
  surfaces a bug, the fix is a dated amendment below with the reason, and the
  report shows results before and after.
- **Features chosen using an all-years result:** F13 and F14, yes. The rest no.
- **Author:** Claude session `session_01UE1DwShsGRDc8szFAaEvpm`. That session
  wrote everything here and is therefore not eligible to audit any successor
  experiment's sealed look.

## Amendments

none
