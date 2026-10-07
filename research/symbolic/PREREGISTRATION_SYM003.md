# SYM-003: do better matchup features add information? (private, exploratory)

**Frozen 2026-10-07, before any SYM-003 feature was built or scored.** The rules
are in [`config_sym003.json`](config_sym003.json). All fights involved have
already been examined, so every result is **exploratory**.

## Plain version

SYM-002 found that a plain weighted average of 23 "who has more of X" gaps was as
good as any fancy formula. This experiment asks a narrower question: **does
knowing how the two styles collide, or how good someone's numbers really were
given who they fought, add anything to that weighted average?** We add three
groups of matchup numbers, one at a time and then all together, and keep a group
only if it beats the plain version by more than luck would allow.

## Audit of the existing 23 inputs

| question | already covered by | what is actually missing |
|---|---|---|
| **Opponent strength** | `elo` (results adjusted for opponent rating at the time), `opp_elo_mean` (mean pre-fight Elo of past opponents) | Strength-adjusted **stats**. Elo adjusts *wins* for opposition; every striking and wrestling rate is raw. Landing 5 a minute on people who usually concede 6 is treated the same as landing 5 on people who concede 3. |
| **Recent performance** | `last3_win_rate`, `fights_24m`, `log_days_since_last`; Elo's sequential updates also weight recent results more | Recency in **stats**. Every rate is a career-cumulative average with equal weight for a bout from eight years ago. |
| **Style interactions** | none. The model sees `td_per15_A − td_per15_B` and `td_def_A − td_def_B` as separate, additive gaps | A **cross term**: whether A's takedown offence meets B's takedown weakness. Note the trap: a multiplicative matchup taken in logs, `log(td_A·tdag_B) − log(td_B·tdag_A)`, splits into `(log td_A − log td_B) − (log tdag_A − log tdag_B)`. That is still just two gaps, so it is mostly already represented. The new features are therefore defined as products on the **natural** scale, which does not decompose. |
| **Takedowns / knockdowns conceded** | only as ratios (`td_def`) or not at all (knockdowns conceded) | Rates of takedowns and knockdowns **conceded per 15 minutes**, added as point-in-time inputs. |

## The three groups (equations in `config_sym003.json`)

- **W, wrestling matchup.** Expected takedowns: my takedown rate × the opponent's
  takedowns-conceded rate, over the league rate. Expected control: my control
  share × the opponent's control-conceded share, over the league share. Takedown
  success: my takedown accuracy × the opponent's takedown-defence failure rate.
  Each is "mine against them minus theirs against me".
- **S, striking matchup.** Expected strikes landed: my output × the opponent's
  absorption. Expected accuracy: my accuracy × the opponent's defensive failure
  rate. Expected knockdowns: my knockdown rate × the opponent's
  knockdowns-conceded rate.
- **O, opponent-adjusted performance.** For each earlier bout, compare what the
  fighter did with what that opponent normally allowed, using the opponent's
  rates **going into that bout**, never their later career. Six residuals:
  striking for and against, takedowns for and against, control for and against.
  These are averaged by minutes, with a two-year half-life, and shrunk toward
  zero with 15 pseudo-minutes so a short record stays near "as expected".

Why these and not others: they are the three pieces of information the audit
found missing. W and S deliberately use the existing career rates, so any gain
comes from the combination, not from recency. O carries the recency weighting
because it is a new measurement.

**A risk declared in advance:** S1 and W1 are close cousins of gaps the baseline
already has. The outcome-free R² diagnostic is reported before anything is
scored. If it shows a group is ≥ 90% represented, that is said plainly rather
than the group being dropped after the fact.

## The test

Baseline (SYM-002's regularised logistic regression on 23 gaps) vs baseline + W,
+ S, + O and + all three. The cohort is identical for every model, λ and scaling
are chosen inside each chronological fold, there are outer folds 2021–2026, and
there is no intercept, so the fighter swap is exact. A group "helps" only if the
95% event-level interval is entirely below zero **and** it wins at least 4 of 5
folds (2021–2025). Another symbolic search is justified only if a group passes.
The archived market is shown on the same fights, labelled as having unverified
timestamps.
