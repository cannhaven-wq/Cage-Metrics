# PRED-002 — Does opponent-adjusted grappling tell us anything the closing line does not?

**Status: DRAFT, not frozen.** Approved as the first PRED-001 experiment by the
owner on 2026-10-13 ([D-024](../../../coordination/DECISIONS.md)). Governed by
[PRED-001](../../protocol/PREDICTION_RESEARCH_PROTOCOL.md). Nothing has been
trained. Development uses fights before 2025-01-01 only. This file is frozen —
its sha256 recorded in `research/registry.json` — before any request to the
auditor; until then every value below may change, and every change is counted
in `variants_tried_on_dev`.

## Plain version

We ask whether knowing how well a fighter wrestles, **measured against how hard
his past opponents were to wrestle**, improves on the betting market's own
probability. If the combination does not beat the market by at least 0.003 log
loss on fights forecast in advance, the answer is no.

**What we expect, said before we look: probably no.** The plain takedown-defence
gap already failed the market test (Factor Lab: 50.2% on market-even fights;
`edges.js`'s version 50.5%). The only new idea here is the opponent adjustment.
A raw takedown average rewards a fighter who met poor wrestlers; adjusting for
the opponent is the one thing the earlier tests did not do.

## Hypothesis

- **H0:** a logistic combination of the de-vigged market probability and the
  grappling features, weights frozen on DEV, has Δ ≤ 0 against the market.
- **H1:** Δ > 0.
- **Target gain δ = 0.006** log loss per fight. That is above the 0.004 floor
  and below the 0.0082 that the sealed H1 window can detect, so **an H1 look
  will most likely come back INCONCLUSIVE even if the effect is real**. The
  prospective test is the one that can decide.

## Challenger

- **Type:** incremental. `logit p = w0·logit(p_market) + Σ wₖ·xₖ`, with no
  intercept, and every xₖ antisymmetric in the corners (A minus B). So
  p(A beats B) = 1 − p(B beats A) holds exactly, which is PRED-001 §3's
  corner symmetry by construction.
- **Fitting:** walk-forward by year inside DEV (fit on years before t, score
  year t, for t = 2015–2024), to choose among the variants below. The final
  weights are then fit once on all DEV fights from 2010 to 2024 and frozen.
- **Artifact:** the frozen weight vector and feature code, sha256 recorded at
  freeze.
- **Variants tried on DEV:** counted from now, starting at 0. Every
  configuration compared is one variant: a feature set, a half-life, a
  shrinkage strength, a regularisation strength.

## Feature manifest (all point-in-time: rows strictly before the fight's `event_date`)

Source: `fight_rounds` per corner — `td_landed`, `td_attempted`,
`ctrl_seconds`, `sub_attempts`, `rev`. Fight time comes from
`fights.end_round`/`end_time`, in 300-second rounds. No `fighters` career
column is used.

For fighter X's prior fight against opponent O, with fight time *m* minutes:

1. **Raw rates per 15 minutes:** takedowns landed, takedowns attempted,
   submission attempts and reversals; plus control share = ctrl_seconds / (60·m).
2. **The opponent's baseline at that date.** For each rate, the average O
   *conceded* in O's own UFC fights before that date, excluding this fight,
   time-weighted, and shrunk toward the division mean with strength k = 3
   fights (empirical Bayes).
3. **Residual:** X's rate minus O's conceded baseline.
4. **Opponent-adjusted offence:** a time-weighted mean of X's residuals over
   X's prior UFC fights, with a 2-year half-life (the engine's choice).
5. **Opponent-adjusted defence:** the same, using what X conceded minus each
   opponent's own offensive baseline.
6. **Matchup features (antisymmetric):**
   - offence_A − defence_B, minus (offence_B − defence_A), for takedowns
     landed and for control share;
   - the A − B difference in submission attempts;
   - the A − B difference in prior UFC fight count (log), which lets the
     model discount thin histories.
7. **Fewer than 2 prior UFC fights** on either side: the grappling features
   are 0, so the model gives the market's probability. This is how the model
   declines to forecast a bout, and it **is not** an abstention lock.

| feature | source | time rule | static? |
|---|---|---|---|
| td_land_adj_diff | fight_rounds.td_landed, fights.end_round/end_time | events strictly before | no |
| ctrl_share_adj_diff | fight_rounds.ctrl_seconds, fights.end_round/end_time | events strictly before | no |
| sub_att_diff | fight_rounds.sub_attempts | events strictly before | no |
| log_ufc_fights_diff | fights (count of prior UFC bouts) | events strictly before | no |
| logit_p_market | BFO close (H1) / consensus at lock (prospective), proportional de-vig | at or before lock | no |

Contamination declared under PRED-001 §2:

- Takedown defence was measured by the Factor Lab over all years, including
  H1, and came out as noise.
- These features were chosen by the owner because that plain version failed,
  not because any all-years result looked good.
- The H1 result is therefore treated as confirmatory. If the auditor
  disagrees, it is recorded as non-confirmatory and nothing else changes.

## Benchmark

- **H1:** the BestFightOdds closing consensus, proportional de-vig. The power
  and Shin de-vigs are reported alongside.
- **Prospective:** the consensus frozen on each lock (`market_p_a_vigfree`) —
  the same-timestamp benchmark, because the model reads the market. The
  close (CLV-001 proxy) is reported alongside.

## Population

Every UFC bout on every card from the experiment's first locked card onward
that has a two-sided sportsbook price before the card starts. Draws and
no-contests are not graded. Bouts rebooked in place are excluded.

## Sample size

- SD: max(0.064, the SD of Δᵢ measured on DEV walk-forward) — to be filled
  in at freeze.
- **n_required = 1,142**, from `required_n(0.064, 0.006, 0.01, 0.8, mue=0.003)`.
  It will be recomputed if the DEV SD exceeds 0.064.
- At about 480 priced fights a year, that is roughly **2.4 years of locks**.
  The plan does not shorten this.

## Stages requested

- [ ] H1 evaluation: spends 1 of 10 slots, on the whole sealed set only.
- [ ] Prospective test: spends 1 of 5 slots. The lock table is live
  (D-024); the lock script is still to be written, and is frozen with the
  artifact.

## Pre-stated interpretation

- **REJECT:** "Opponent-adjusted grappling adds nothing the closing line does
  not already know." Recorded and published as a negative result, with no
  successor experiment on grappling unless a new idea is preregistered.
- **INCONCLUSIVE on H1:** expected at this size. The prospective test decides.
- **PASS_H1:** a reason to keep locking. Nothing more is said in public.
- **PASS_PROSPECTIVE:** "Added information beyond the market on N fights
  forecast in advance." Public use is the owner's call (L3); it is not a
  betting claim (CLV-001 gate).

```pred-registration
{"experiment_id": "PRED-002", "model_artifact_sha256": "TBD-at-freeze", "model_class": "incremental",
 "target_effect": 0.006, "sd_used": 0.064, "n_required": 1142,
 "author_sessions": ["session_01J8Jjgk3pgqKw3xVPHjUbyY"], "code_paths": []}
```

## Amendments

None. The file is not frozen yet.
