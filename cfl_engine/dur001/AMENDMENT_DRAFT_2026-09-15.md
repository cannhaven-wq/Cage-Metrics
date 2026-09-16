# DUR-001 — amendment draft, 2026-09-15

**Status of this file: DRAFT. Nothing here is in force.**

Every item below is marked **PROPOSED — needs Reed's approval before UFC 331
outcomes are inspected.** None of them has been implemented. `PREREGISTRATION.md`
is unchanged and remains binding exactly as written.

This draft was written before any UFC 331 fight result was read. No result,
settled or partial, informed any item in it. That ordering is the whole point:
the preregistration says amendments "may never be motivated by observed
results", so the only safe time to write them is now.

Quotes below are from `cfl_engine/dur001/PREREGISTRATION.md` at commit
`1bc3fdd` (line numbers as of that file).

---

## (a) Primary consensus requires ≥ 2 books

**Current — §5, lines 62, 66–67:**

> One analysis row is one (fight, threshold). It enters only if all hold:
>
> 2. at least one non-synthetic, non-live quote (`is_live = false`,
>    `source <> 'synthetic'`) captured strictly before the fight's start;

**and §6, lines 81–82:**

> - **Closing consensus** = median of per-book vig-free `p_over` across eligible
>   books at the identical threshold (`v_prop_odds_closing_consensus`).

**Proposed:**

> 2. quotes from **at least two distinct books** (`is_live = false`,
>    `source <> 'synthetic'`) captured strictly before the fight's start, each
>    at the identical threshold;
>
> - **Closing consensus** = median of per-book vig-free `p_over` across eligible
>   books at the identical threshold, requiring **≥ 2 books** for the primary
>   analysis (`v_prop_odds_closing_consensus`).
>
> Sensitivities, reported alongside and never as the primary: the same analysis
> at **≥ 1 book** and at **≥ 3 books**.

**Why:** a one-book "consensus" is not a consensus; it is one trader's number
plus that book's margin, and its de-vig is the least reliable.

**Code:** `dur001_analysis.py` — add a book-count filter on the closing
consensus join and loop the primary computation over a `MIN_BOOKS ∈ {1, 2, 3}`
list, tagging 2 as primary.

---

## (b) One line per fight, chosen deterministically

**Current — §5, lines 62, 64–65:**

> One analysis row is one (fight, threshold). It enters only if all hold:
>
> 1. the sportsbook threshold **exactly equals** a locked PROP-0001 threshold
>    (0.5, 1.5, 2.5). No interpolation, extrapolation, or nearest-line mapping;

**Proposed:**

> One analysis row is one **fight**. Where a fight has quotes at more than one
> locked threshold, exactly one threshold is selected, by this deterministic
> rule applied in order until one line remains:
>
> 1. the threshold quoted by the **most distinct books**;
> 2. tie → the threshold with the **lowest median overround** across its books;
> 3. tie → the **lower numerical threshold**.
>
> The rule uses only pre-fight information and is applied before any outcome is
> read. The threshold must still exactly equal a locked PROP-0001 threshold
> (0.5, 1.5, 2.5); no interpolation, extrapolation, or nearest-line mapping.
>
> Sensitivity: all exact lines retained, with each fight's rows weighted to sum
> to 1.

**Why:** at present one fight can contribute up to three highly correlated rows,
which inflates the effective sample and understates the cluster bootstrap's
width. Selecting one line per fight makes the observation unit and the cluster
unit the same object.

**Code:** `dur001_analysis.py` — a line-selection step between the eligibility
filter and the walk-forward fit, plus a `--weighting {single,weighted}` switch
for the sensitivity.

---

## (c) Two questions, labeled separately

**Current — §7, lines 87–94:**

> Walk-forward by event, chronological. For each scored event, coefficients are
> fit on prior events only (minimum 8 prior events and 40 prior rows):
>
> ```
> baseline:   logit(P) = α + β·logit(P_close)
> challenger: logit(P) = α + β·logit(P_close) + γ·[logit(P_CFL) − logit(P_close)]
> ```

**Proposed — replace §7's opening with two explicitly separated questions:**

> Two distinct questions are reported, always labeled, never merged:
>
> **(i) Residual-signal test.** Using the frozen model form, α, β and γ are fit
> on the evaluated fights themselves. The question is whether γ > 0 — that is,
> whether PROP-0001 contains information not already in the closing benchmark.
> This is an in-sample test of *existence of signal*. It cannot support a
> deployment claim and its log-loss gain is never reported as out-of-sample.
>
> **(ii) Deployable-combiner test.** α, β and γ are fit on prior events only
> (minimum 8 prior events and 40 prior rows) and frozen before the evaluated
> fights are scored. This is the walk-forward procedure already specified, and
> it is the only one that can support PROMOTE.
>
> ```
> baseline:   logit(P) = α + β·logit(P_close)
> challenger: logit(P) = α + β·logit(P_close) + γ·[logit(P_CFL) − logit(P_close)]
> ```
>
> **UFC 331 counts as (i) only**, unless a combiner was frozen before its
> outcomes were inspected. It was not, so it is (i).

**Why:** the current §7 describes only the walk-forward form, but with one card
there are no prior events, so the minimum-8-events rule means the card produces
nothing at all under (ii). Without this split, the tempting move is to fit on
the card and quietly call the result out-of-sample. Naming both tests and
pinning UFC 331 to (i) removes that temptation in advance.

**Code:** `dur001_analysis.py` — add the in-sample fit path, and tag every
emitted metric with `question: "residual_signal" | "deployable_combiner"`.

---

## (d) Verdict rule

**Current — §11, lines 128–138:**

> PROMOTE the duration branch only if **all** of:
>
> 1. G_LL > 0 out of sample;
> 2. the 95% event-bootstrap interval for G_LL has lower bound > 0;
> 3. G_LL ≥ 0.003 per fight-threshold row;
> 4. challenger Brier − baseline Brier ≤ 0.001;
> 5. challenger calibration slope in [0.8, 1.2] and |intercept| ≤ 0.10.
>
> REJECT if the interval's upper bound is below 0.003. Otherwise HOLD and keep
> collecting.

**Proposed:**

> The verdict is one of four values, evaluated on question (ii) only:
>
> - **PROMOTE** — point estimate ΔLL ≥ 0.003 per observation **and**
>   cluster-bootstrap 95% CI lower bound > 0. Calibration guards 4 and 5 above
>   remain necessary conditions.
> - **REJECT FOR PRACTICAL VALUE** — CI upper bound < 0.003. The effect may be
>   real and is too small to act on.
> - **HOLD** — anything else. Keep collecting.
> - **NO VERDICT — DATA FAILURE** — declared instead of any of the above when
>   the integrity or coverage checks fail (see §14). A data failure is never
>   reported as HOLD; the distinction between "no signal" and "no usable data"
>   must survive into the writeup.

**Why:** the current wording mixes the effect-size floor and the interval into
one PROMOTE list, and has no way to say "the pipeline was broken". "REJECT"
without "for practical value" also reads as "the model is worthless", which is
not what an upper bound below 0.003 means.

**Code:** `dur001_analysis.py` — replace the boolean PROMOTE check with a
four-valued verdict function; add the `NO VERDICT` short-circuit ahead of it.

---

## (e) Cluster CIs are descriptive until 20 cards

**Current — §8, lines 108–111:**

> Event-cluster bootstrap: resample whole UFC events with replacement, 10,000
> draws, on the fixed out-of-sample predictions (no refitting inside the
> bootstrap). Report 95% percentile intervals for G_LL, ΔBrier, and calibration
> slope. Individual fights are never resampled.

**Proposed — append:**

> Until **20 completed eligible cards** are in the sample, these intervals are
> **descriptive only**. They are reported, and they may not trigger PROMOTE or
> REJECT FOR PRACTICAL VALUE. An event-cluster bootstrap over a handful of
> clusters has coverage well below its nominal 95%, and its width is itself
> mostly noise. Below the threshold the verdict is HOLD regardless of where the
> interval falls.

**Why:** with one card there is one cluster and the bootstrap is degenerate —
every resample is the same event. The interval would be a number that looks
like evidence and is not.

**Code:** `dur001_analysis.py` — gate the verdict function on
`n_events >= 20`; emit `ci_status: "descriptive" | "decision_grade"`.

---

## (f) Kill / checkpoint rule

**Current:** none. §11–§12 specify HOLD indefinitely; nothing ever stops.

**Proposed — new §15:**

> **Checkpoint.** DUR-001 reaches a mandatory checkpoint at the earlier of
> **2027-09-15** or **500 valid prospective observations** (question (ii),
> primary line selection, ≥ 2 books).
>
> At the checkpoint, if the verdict is not PROMOTE, DUR-001 moves to
> **HOLD-PASSIVE**: locks continue to be written and graded, and no further
> analyst time is committed until either the sample doubles or the model
> version changes. HOLD-PASSIVE is recorded in the registry with its date.

**Why:** an experiment with no stopping rule is not an experiment, it is a
standing invitation to keep looking until something clears. The checkpoint is
set now, before any result is visible, so the date cannot be chosen to suit the
data. HOLD-PASSIVE rather than kill because the locks are cheap to keep writing
and the record has value even if the effect does not.

**Code:** `dur001_analysis.py` — emit `checkpoint_reached` and
`observations_to_checkpoint` in the report header.

---

## (g) Terminology: this is not a closing line

**Current — §6, line 80 and §5, line 68:**

> - **Close** per book = last non-live quote strictly before `v_fight_start_best.start_at`.

> 3. the fight's start basis is `bell_at` or `provider_commence`.

**Proposed:**

> The phrase **"closing line" is not used** for anything DUR-001 currently
> measures, and no CFL surface may use it for these numbers. Two named
> benchmarks replace it:
>
> - **Provider pre-fight closing benchmark** (live capture) — per book, the last
>   non-live quote strictly before `v_fight_start_best.start_at`, where
>   `start_at` rests on `provider_commence`. This is the last price *we
>   observed*, which is not the last price the book *posted*.
> - **T-10 historical pre-fight benchmark** (historical backfill) — per book,
>   the quote selected by the historical timing rule in item (i).
>
> "Closing line" becomes available only once `fights.bell_at` is populated and
> the start basis is `bell_at`. **As of 2026-09-15, `bell_at` is populated on
> 0 of 8,992 fights**, so no fight in the database currently qualifies.

**Why:** we are capturing on a cron against a provider feed. Calling that a
closing line overstates it, and the overstatement would leak into user-facing
copy, where `COPY_STYLE.md` forbids market language anyway.

**Code:** rename in `dur001_analysis.py` output keys and
`v_prop_odds_closing_consensus` comments; grep `edges.html`, `methodology.html`
and `predictor.html` for "closing line" before shipping.

---

## (h) De-vig method

**Current — §6, line 79:**

> - Two-way de-vig per book: `p_over = q_over / (q_over + q_under)`.

**Proposed:**

> - **Primary:** proportional (normalisation) de-vig per book,
>   `p_over = q_over / (q_over + q_under)`. Unchanged.
> - **Sensitivity:** exactly **one** frozen alternative, chosen now and named in
>   this amendment — **[Reed picks: Shin (1993) | power/odds-ratio]** — reported
>   beside the primary. No further de-vig methods are added later; a method not
>   named here cannot be introduced once results are visible.

**Why:** proportional de-vig is known to under-price favourites and over-price
longshots, so it is worth one robustness check. One alternative, frozen now,
rather than an open family — otherwise the choice of de-vig becomes a free
parameter searched after the fact.

**Code:** `dur001_analysis.py` — a `devig(method)` helper and a second pass; the
view `v_prop_odds_devig` gains one column.

---

## (i) Historical timing rule — two candidates, Reed picks one

**Current — §13, lines 149–152:**

> A historical backfill, if ever attempted, must be walk-forward with
> `training_cutoff < fight_start`, carry a distinct `model_version`, and never
> be written to `prop_model_locks`.

The preregistration says a backfill must be walk-forward but does not say
*which historical quote* is the benchmark. Both candidates below are
pre-registrable. **Reed picks one; the unpicked one is not kept as a
sensitivity.**

### Candidate 1 — current tool: T-10 before earliest observed start

> For each fight, the benchmark is the last snapshot at or before
> **T−10 minutes**, where T is the **earliest provider start time ever observed**
> for that fight across all snapshots. Fights whose provider start moved after
> capture are **flagged** in the output but retained.

- **Credits:** **0 extra Odds API calls.** Uses snapshots already stored.
- **Weakness:** if a fight's start was moved later, "earliest observed start"
  picks a benchmark from well before the real pre-fight window — potentially
  hours early, and systematically so for delayed cards.

### Candidate 2 — Chat's: self-consistent snapshot walk-back

> For each fight, the benchmark is the **latest snapshot whose own reported
> commence time, minus 10 minutes, is after that snapshot's capture time** —
> i.e. the last snapshot that still believed the fight had not started. Walk
> back through 5-minute snapshots up to **60 minutes**. A fight with no
> qualifying snapshot is **excluded**, not flagged.

- **Credits:** up to **12 extra calls per moved fight** (60 min ÷ 5 min). Only
  moved fights incur the walk-back; unmoved fights resolve on the first probe.
- **Weakness:** excludes fights rather than flagging them, so the historical
  sample is selected on a capture property. Costs credits.

**Credit difference:** Candidate 1 is free. Candidate 2 costs up to 12 calls per
*moved* fight and 0 for the rest, so the bill scales with schedule churn, not
with sample size. On a clean historical window the two cost nearly the same; on
a churny one Candidate 2 could be materially more expensive.

**Recommendation for Reed to accept or overrule:** Candidate 1, on the grounds
that flagging beats excluding — an excluded-fight rule silently conditions the
sample on a property correlated with card chaos, which is exactly the kind of
selection this preregistration exists to prevent. The flag can be used as a
sensitivity split at zero credit cost.

**Code:** new `cfl_engine/dur001/historical_benchmark.py`; neither candidate
touches `prop_model_locks`.

---

## (j) Expose `market_last_update`, and require it for a closer

**Current — §6, line 80:**

> - **Close** per book = last non-live quote strictly before `v_fight_start_best.start_at`.

**Proposed:**

> - **Close** per book = the last non-live quote strictly before
>   `v_fight_start_best.start_at` **whose `market_last_update` is also strictly
>   before `start_at`**. A quote whose underlying market timestamp is at or
>   after the fight's start is not a pre-fight price regardless of when we
>   captured it, and is excluded from the primary analysis.

**Why:** `captured_at` is when *we* wrote the row; `market_last_update` is when
the *book* last moved the price. The Odds API already returns it and
`fetch-odds.js` already stores it inside `prop_odds.raw`, but nothing reads it.
Without this check a row captured at T−2min can carry a price the book stamped
after the bell, and it would count as a closer.

`market_last_update` is present in `prop_odds.raw` on the live data
(`raw->>'market_last_update'`, e.g. `2026-09-15T02:04:06Z`) but is not exposed
as a column anywhere.

**Migration written, not applied:**
[`proposed_2026-09-15_market_last_update.sql`](proposed_2026-09-15_market_last_update.sql)

**Code:** `dur001_analysis.py` reads the new column; `v_prop_odds_lifecycle` and
`v_prop_odds_closing_consensus` are replaced by the migration above.

---

## (k) No `-dirty` locks *(added by the provenance audit, not in Reed's list)*

Flagged here because the audit in `research/provenance/` found every one of the
48 live locks carries `code_version = 322a5b09e739-dirty`, and the uncommitted
code included the lock script itself.

**Current — §3, lines 33–34:**

> | lock script | `cfl_engine/dur001/lock_prop0001.py` |
> | freeze commit (model + features + lock script) | `6be7198ebe4d56b27366268318b757e99e3074c5` |

**Proposed — append to §3:**

> A lock is never written from a dirty working tree. The lock script refuses to
> insert when `git status --porcelain` is non-empty, unless `--allow-dirty` is
> passed, in which case the full working-tree diff is hashed and its sha256 is
> written to `notes`, and the diff itself is committed under
> `research/provenance/` before the card starts.
>
> Any hash cited in this preregistration must name the expression that computes
> it, or point at the function in the repository that does. The ledger hash
> `df3ab0cc…` in §3 is amended to read:
>
> > ledger hash `df3ab0cca0757eb9c452e9bfb0cede38` —
> > `md5(string_agg(row_to_json(l)::text, '|' order by id))` over the whole
> > `prop_model_locks` table, as computed by `cfl_engine/dur001/health.py`

**Note on the audit:** the hash **verified**. The 48 rows are byte-for-byte what
was hashed at freeze time. The only defect found was that §3's one-line
description ("md5 of row_to_json ordered by id") omits the pipe separator and
the table scope, so it cannot be re-derived from the preregistration alone.
Item (k) is therefore a wording fix plus the dirty-tree guard, not a
supersession — nothing about the existing evidence is withdrawn.

**Code:** `lock_prop0001.py` — a dirty-tree guard and an `--allow-dirty` escape
that records the diff hash. No change to `health.py`.

---

## Decisions needed from Reed

| item | decision |
|---|---|
| a–g, j, k | approve / reject / amend |
| h | approve, **and pick**: Shin or power de-vig |
| i | **pick Candidate 1 or Candidate 2** (recommendation above: 1) |

Until these are approved, `PREREGISTRATION.md` stands as written and UFC 331
outcomes stay uninspected.
