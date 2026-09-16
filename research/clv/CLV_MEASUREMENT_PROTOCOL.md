# CLV measurement protocol

**Status: FROZEN — 2026-09-16, approved by Reed Cannon.**

**Frozen is not publishable.** The measurement rules are settled; the publication
gate is still **shut**. The sample floor is 100 scored observations across 20
distinct events and it currently stands at **0**. Freezing settled *how* the
number is measured — it did not create a number worth showing.

| field | value |
|---|---|
| protocol id | `CLV-001` |
| version | `1.0.9` |
| revised | 2026-09-16, against [ChatGPT's review](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md) |
| created | 2026-09-16 |
| author | Claude, for ChatGPT methodological review |
| next action | reconcile `settle_clv.py` with the frozen rules. **No publication** |
| frozen at | **2026-09-16T10:30:00Z** (v1.0.0; Amendments 1–6 same day) |
| frozen by | **Reed Cannon** |
| machine mirror | [`protocol.json`](protocol.json) |

---

## Plain version

When CFL posts a pick, it also posts the price. Later the fight starts and the
market stops moving. If the price moved toward our side after we posted, we got
a better price than the people who bet at the close — that is closing line
value, and it is the one measurement that separates a model that knows
something from a model that had a good weekend.

This document fixes exactly how that gets measured, **before** any number is
calculated for publication. The order matters. If you measure first and define
afterwards, you end up defining it whichever way makes the number look best, and
nobody — including you — can tell whether you did that on purpose.

Two things are separately gated, and the distinction is the whole design:

| | allowed now? |
|---|---|
| capturing raw market quotes | **yes** — starts immediately, keeps running |
| computing a CLV statistic | **yes**, as of the freeze |
| putting a CLV number on a surface | **no** — the sample floor is unmet, 0 of 100 |

Freezing opened the second row and **not** the third. They were never the same
gate, and an earlier draft of the freeze procedure wrongly said publication opens
on freeze — corrected, because that would have published on a sample of zero.

Collecting early costs nothing and loses nothing. Deciding early is the part
that has to be disciplined.

---

## 0. Scope and standing

CLV is **not** a predictive-model experiment. It has no hypothesis, no
challenger model and no verdict, so it does not go in the DUR register and does
not get a `model_version`. It is a **measurement protocol**: the rules by which
an already-published number is scored against the market.

What it borrows from DUR-001 and DUR-002 is the only part that transfers — the
rules are fixed before any result is computed, and a rule may not be swapped
after a result is visible.

### Relationship to what already ships

`cfl_engine/settle_clv.py` already computes CLV daily into
`model_edges.closing_odds` / `clv_pp` / `clv_beat`, under
`.github/workflows/settle-clv.yml`. It is a working implementation with
conventions already chosen — and several of them are good enough that this
protocol adopts them outright (§2). Nothing on a user-facing surface renders
those values today; `track-record.html` carries a placeholder that says the
sample is too small.

**This protocol governs that script.** Where the two disagree once frozen, the
script changes. Until then the script keeps running and keeps writing — it is
capture and computation into a private column, not publication.

### The pre-freeze firewall

Reed's instruction is to capture raw quotes immediately and freeze the protocol
before publishing. That is right, and it has one exposure worth naming: **data
that exists can be looked at, and a definition chosen after looking is not a
preregistered definition.**

So, binding for the draft period:

1. No CLV summary statistic is computed from captured quotes before freeze. Row-level
   settlement into `model_edges` continues — that is bookkeeping under the
   already-shipped convention, not a result.
2. No alternative definition in §3 is evaluated against captured data to decide
   between options. This draft was written without running any such comparison,
   and says so in §9.
3. If anyone does compute one, it is **disclosed** in this document the way
   DUR-002's preregistration §2 discloses its prior comparison — recorded, and
   explicitly not usable as evidence for the choice.

---

## 1. What is being measured

> **FROZEN 2026-09-16, approved by Reed Cannon (Q-05, Q-06).** The primary
> measure below replaces raw implied-probability movement. The `clv_pp`
> construction that follows it is retained because it is what `settle_clv.py`
> ships today and what the stored rows mean — it is a secondary descriptive
> figure, never the headline, and it is never called CLV on a surface.

### 1.1 Primary measure — `CLV_return` **(frozen)**

```
CLV_return = closing_fair_probability × decimal_odds_at_publish − 1
```

Read it as: **the expected return per unit staked at the price CFL actually
posted, evaluated against the market's de-vigged closing fair probability.** It
answers the economically meaningful question — was the price CFL posted better
than the later fair closing market?

| side | treatment |
|---|---|
| **publish** | the **actual posted price**, vigged, exactly as a bettor would take it. Never de-vigged. |
| **close** | **de-vigged fair probability**, which requires both sides at close |

**It is conservative by construction, and that must be said out loud.** Because
the publish side keeps the book's margin, the bar is *fair closing probability >
**vigged** implied probability at publish*. So `CLV_return = 0` does not mean
"no edge either way" — it means CFL obtained exactly fair closing value *after
paying the posted price*. This figure may never be described as though it were a
fair-versus-fair comparison.

**Blocking dependency.** Two-sided capture **at close** — the closing side is
de-vigged and cannot be backfilled. Not at *publish*: the publish side is used as
posted and is never de-vigged. An earlier draft recorded the blocker on the wrong
side; §4 item 2 is the live requirement.

The de-vig method for the closing side is the **power** method, matching
DUR-001 Amendment 1.1 **as corrected by DUR-001 Amendment 2** — Q-12, resolved.
Proportional and Shin are frozen sensitivities only.

> **v1.0.1, 2026-09-16.** DUR-001 Amendment 1.1 stated that the bisection sum is
> "strictly decreasing in `k`". For the formula it specifies, `q^(1/k)`, the sum
> is strictly **increasing**. DUR-001 Amendment 2 corrects it. The two
> conventions are exact reparametrisations, so **no de-vigged probability
> changes** — CLV-001's own rules are untouched and this version records an
> inherited clarification, not a change of its own. The original v1.0.0 bytes
> and freeze record are preserved in `protocol.json`.

### 1.2 Secondary measure — `clv_pp`, the shipped construction

For a published pick on a fighter, at a price we could have taken:

```
p_publish = implied probability of the bet side at the price CFL posted
p_close   = implied probability of the bet side at the close
clv_pp    = p_close - p_publish
beat      = clv_pp > 0
```

American odds convert to implied probability as

```
odds < 0 :  p = |odds| / (|odds| + 100)      e.g. -200 -> 0.6667
odds > 0 :  p = 100    / (odds  + 100)       e.g. +150 -> 0.4000
```

**Sign convention, which is easy to get backwards.** You beat the close when the
market's closing implied probability of your fighter is *higher* than the
implied probability at the price you locked — the line moved toward you and you
hold the longer price.

| | at publish | at close | clv_pp | reading |
|---|---|---|---|---|
| dog | +150 → 0.4000 | +120 → 0.4545 | **+0.0545** | beat the close |
| favourite | −200 → 0.6667 | −300 → 0.7500 | **+0.0833** | beat the close |

Positive `clv_pp` always means beat. Reported in probability points; a
price/cents presentation is a display choice, never the stored unit.

---

## 2. Decided rules

These are settled: each has one defensible answer, or a binding precedent in the
repo. They are not open for review unless the reviewer thinks one is *wrong*, in
which case say so.

### R-01 — Raw capture is immediate, immutable and append-only

Every quote is stored as captured. The raw quote store rejects `UPDATE` and
`DELETE` by trigger for every role including `service_role`, matching
`prop_model_locks` and `pre_fight_snapshots`. A quote that turns out to be
garbage is **excluded at scoring time by a written rule**, never deleted.

Rationale: the whole value of a closing line is that it was observed before the
bell. A store that can be edited afterwards is not evidence, which is the same
argument the pre-fight snapshot table rests on.

### R-02 — A quote without a timestamp is not eligible

Every captured quote carries the book, the fighter, the price, and the UTC
instant of capture. A quote missing any of those cannot be placed relative to
the forecast or the close, and is excluded from scoring — retained in raw, never
scored.

### R-03 — Non-market price guard

A capture whose implied probability falls outside **[0.03, 0.97]** is not a
bettable price and is excluded from scoring.

This is not a theoretical precaution. The feed emits sentinels near ±199900
(implied ≈0.9995 / 0.0005) when a book pulls a fight or the capture lands after
settlement. One such row was, on its own, responsible for the entire positive
mean CLV across the first batch of settleable edges — the sign of the headline
metric flipped when it was removed. The guard was added 2026-08-19 after that
near-miss and is recorded here so it cannot be quietly relaxed.

### R-04 — No substitution, no imputation

If no usable closing price is on file, the observation is left **unscored**. It
stays eligible for a later run if a real price arrives. A stale snapshot, a
de-vigged reconstruction or a modelled price is never substituted for an
observed close.

### R-05 — One-sided or missing markets

An observation is scored only if the bet side has an observed, in-band closing
quote from an eligible book. A market quoted on one side only is scored if that
side is the bet side and the definition chosen in Q-05 does not require the
opposite side; otherwise unscored. Unscored observations are **counted and
reported** — the count of unscored observations appears beside any summary, so
a coverage problem cannot hide inside a favourable average.

### R-06 — Duplicate and reposted markets

Deduplicate on `(book, fight_id, fighter_id, quoted_at)`. Where a book reposts a
market — takes it down and puts it back, or reopens after a fighter change —
each posting is retained in raw and distinguished by capture time. Scoring uses
the latest eligible quote satisfying the closing-line definition (Q-01). A
repost after the scheduled start is subject to R-03 and generally excluded.

### R-07 — The forecast precedes the market quote, always

A scored observation requires `forecast_locked_at < close_quoted_at`, strictly,
in UTC. A forecast whose timestamp cannot be established from an immutable
record is not eligible.

This is the no-lookahead rule, and it is the one an implementation is most
likely to violate by accident — for instance by re-reading a "current" forecast
at settlement time instead of the one on record when the price was posted.
`pre_fight_snapshots` exists precisely to make the publish-time forecast
recoverable.

### R-08 — Outcome independence: void and no-contest

CLV measures **price, not result**. A fight that ends in a no-contest, or whose
result is overturned, still had a closing line, so the observation is
**retained and scored**. Whether the bet would have been refunded is a
bankroll question and belongs in My Book, not here.

A fight **cancelled before a close exists** has no closing line and is
**excluded** — not scored zero. Scoring it zero would silently pull every
summary toward the middle.

### R-09 — No CLV statistic before freeze

Per §0. Row-level settlement continues; summaries do not.

### R-10 — Publication gate

No CLV figure appears on any user-facing surface — page, post, email, digest —
until this protocol is frozen. `protocol.json` carries
`publication_gate.publication_allowed`, which is `false` while status is not
`frozen`, and `tests/test_clv_protocol.py` asserts it.

### R-11 — Provenance

Inherits the research register's standing rule: a number does not appear on a
CFL surface unless it traces to a named artifact. For CLV that means the
published figure names the protocol version it was computed under and the query
or script that produced it.

### R-12 — Copy governance

Any CLV wording follows [`COPY_STYLE.md`](../../COPY_STYLE.md) — plain English,
anti-tout, losses at equal prominence. Q-11 fixes what may and may not be
claimed; `COPY_STYLE.md` governs how it is said.

---

### R-13 — A sentinel timestamp is not a timestamp

R-02 makes a quote without a timestamp ineligible. That is not enough: a
**populated but fake** timestamp passes it.

Measured 2026-09-16, read-only: **30,724 of 110,032 `fight_odds` rows — 27.9%,
across 7,681 fights — carry `captured_at = 1970-01-01`**, the Unix epoch. Live
capture begins 2026-05-22; everything before it is a historical import whose
capture instant was never recorded and defaulted to epoch.

**Rule.** A quote whose `captured_at` is not a credible capture instant is
ineligible, exactly as a missing one is. Credible means at or after the
live-capture era began (2026-05-22) and not in the future. Such rows are
**retained raw** under R-01 and excluded at scoring time — never deleted.

**Consequence, which is a coverage fact and not a gap to paper over.** CLV can
only ever be computed on fights from the live-capture era. Those 7,681 historical
fights have prices but no usable capture timing, and can never enter the measure.
That number gets reported under R-05, not quietly dropped.

An epoch timestamp is also the worst possible failure mode for this protocol
specifically: it is always "before the fight", so a sentinel row is not merely
noise — it is a row that looks *eligible* to every ordering rule in §3, and would
be selected as the opener every time. This is the same family of defect as the
R-03 sentinel that once flipped the sign of mean CLV.

---

## 3. Open questions

Each has more than one defensible answer. **None was chosen by computing which
performs better historically** — no such comparison was run (§9).

Levels are proposed, per D-003: **L1/L2** goes to ChatGPT for methodological
review; **L3** escalates to Reed because the choice materially changes what a
published number means.

---

### Q-01 — What "closing line" means · proposed **L2**

> **RESOLVED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** Last quote before **scheduled** start, named a
> **scheduled-close proxy** and never "the closing line". Staleness limit
> still set from capture cadence.
>
> Independently corroborated: `fights.bell_at` is populated on **0 of 8,992**
> fights, so no row in the database currently supports a literal closing
> line. The proxy naming is forced by the data, not merely prudent.

> ## AMENDMENT 6, v1.0.9, 2026-09-16 — provenance, enforced per row
>
> **Approved by Reed Cannon (L3).** The measurement is unchanged: same cutoffs,
> same de-vig, same 45-minute limit, same book list, same publication gate. What
> changes is that the rules already written here are now enforced where they
> apply — on the ROW — instead of being assumed from the shape of the table.
>
> Nothing is retroactively reinterpreted, because nothing has been scored: the
> gate stands at 0 of 100 observations and 0 of 20 events.
>
> ### (a) Eligibility is a property of the row, not of the schema
>
> §4 says these fields "cannot be backfilled" and that anything captured without
> them "simply cannot be used for the definitions that need them". The settler
> checked that the CLV-001 **columns existed** and then scored on whatever
> `fight_odds` held. Those are not the same test, and the gap between them opens
> the day the capture migration lands: a May or June quote with a perfectly
> credible `captured_at` and NULL in every new column becomes scorable, and the
> measurement silently includes rows that cannot support it.
>
> A quote is now eligible only if **that quote** carries `source_event_id`,
> `feed_version`, `opponent_fighter_id`, `provider_last_update`, `retrieved_at`,
> `market_status` and `raw` — §4 items 9, 6, 10, 11, 11, 8 and 12. Present means
> populated: an empty string and an empty jsonb object record nothing and do not
> count. Rows captured before the migration stay permanently unscorable, which
> is a coverage fact reported under R-05.
>
> New reason: `incomplete_quote_provenance`.
>
> ### (b) R-07 is applied per quote, as written
>
> R-07 is `forecast_locked_at < close_quoted_at`, strictly. The implementation
> checked `published_at < cutoff`, which is a different and much weaker claim.
>
> **A forecast locked at 9:28 could be scored against a book quote from 9:20,
> because the cutoff was 9:30.** That quote was on the screen before the forecast
> existed — it is a price the forecast could have been read off, and calling the
> difference between them closing-line value is the no-lookahead violation R-07
> names as the one an implementation is most likely to make by accident.
>
> Every quote entering the consensus must now be strictly after the lock and
> strictly before the cutoff. `closing_pairs` takes the lock as a required
> argument with no default, because a default of None would be a silent bypass
> of exactly this rule.
>
> ### (c) The lock comes from an immutable record
>
> R-07's second sentence: "A forecast whose timestamp cannot be established from
> an immutable record is not eligible." `model_edges` is a working table with no
> append-only trigger, so `published_at` is a claim about what we published, not
> a record of it.
>
> `pre_fight_snapshots` is the immutable record — unique on `fight_id`, rejecting
> UPDATE and DELETE by trigger for every role including `service_role` — and it
> carries `edge_side`, `edge_bet_fighter_id` and `edge_odds_at_publish`, so it can
> be matched to **this edge** rather than merely to its fight. All three must
> agree. A dedicated publish-lock ledger is therefore not needed; the record
> already exists and predates CLV-001, which is what makes it good evidence.
>
> The effective lock is the **later** of the immutable instant and `published_at`.
> Later is strictly harder to satisfy, so an edited `published_at` can only ever
> cost observations — never admit a quote the immutable record would have
> excluded. That asymmetry is why the two are combined rather than one trusted.
>
> New reason: `no_immutable_forecast_lock`.
>
> ### (d) The publish price must name its source quote
>
> §4 item 12. `model_edges.clv_publish_quote_id` records the exact `fight_odds`
> row `odds_at_publish` came from, and the scorer **verifies** it rather than
> trusting it: the referenced row must itself carry the same American price, the
> bet fighter, the opponent (Q-10), the provider market id (R-06), a credible
> capture instant (R-13) and full §4 provenance.
>
> Historical edges have no such link and are not given one. Searching for "the
> row whose price matches" manufactures the record the rule exists to require,
> and afterwards would be indistinguishable from one the publisher recorded.
>
> The closing quotes must also name the **same provider market** as the publish
> quote, and the **same opponent** — a repost or a rematch is a different market,
> not a later quote on the same one (R-06, Q-10).
>
> New reasons: `no_publish_quote_link`, `market_identity_changed`.
>
> ### (e) The cutoff is stored, and hashed
>
> Every scored observation is defined as "the latest eligible quote strictly
> before X", and X was not stored. For bouts 2..N it coincides with
> `clv_window_opened_at` so it looked recoverable; for **bout 1** — the only bout
> this version can currently score — the cutoff is the card's scheduled start and
> no column held it.
>
> `clv_cutoff_at` is added and required on every scored row. The cutoff also goes
> **inside the hashed artifact**, with the forecast lock and the publish quote id:
> a consensus is a set of prices *selected by* a cutoff, and hashing the prices
> alone leaves the selection rule outside the integrity check — the same books at
> the same median hash identically whether they were chosen against a 22:00
> cutoff or a 23:00 one.
>
> ### (f) Bout 1's cutoff comes from bout 1's own schedule
>
> `v_clv_close_reference` resolved the card's scheduled start from the latest
> `odds_api_commence` observation belonging to **any** fight on the event. The
> provider publishes a commence time per market and the later bouts' estimates
> drift as the night is rebuilt, so on a twelve-bout card the newest observation
> almost always belongs to another fight — and bout 1's cutoff was being set from
> bout 12's schedule. Amendment 3 exists because those are different instants.
>
> It now resolves the latest observation **for the bout-1 fight itself**, within
> the latest complete card snapshot. No running order means no identified first
> bout and therefore no scheduled start, which is correct: "the card's scheduled
> start" is a claim about a specific fight.
>
> ### (g) The raw quote evidence is made durable
>
> R-01 requires the raw quote store to reject UPDATE and DELETE by trigger for
> every role including `service_role`. `fight_odds` did not — it is UPDATEd in
> production today by the legacy `is_closer` promotion — so `clv_source_quote_ids`
> pointed at rows whose price, timestamp, identity or provenance could be
> rewritten afterwards, with the consensus hash still matching because it covers
> the artifact rather than the rows.
>
> `proposed_2026-09-16_fight_odds_immutability.sql` rejects DELETE and TRUNCATE
> outright and rejects any UPDATE that changes anything other than the derived
> flags `is_opener` / `is_closer`, which are recomputable, carry no observation,
> and are not read by CLV-001. Whitelist by construction — the guard compares
> `to_jsonb(old)` and `to_jsonb(new)` minus those keys, so a column added later is
> protected the moment it exists.
>
> That migration is **not additive-only** and is filed separately for that reason.
>
> ### (h) The staleness clock is named, and left alone
>
> The frozen 45 minutes was derived from CFL's own observation cadence, so it is
> measured from `captured_at` and nothing else. `provider_last_update` is
> required provenance (§4 item 11) and is **not** the clock: re-pointing the limit
> at it would change which rows score under the same version number. Recorded as
> `STALENESS_MEASURED_FROM`, and moving it is a methodological amendment.
>
> ### (i) §5 no longer says freezing opens the gate
>
> §5 listed "`publication_gate.publication_allowed` becomes `true`" among the
> things that happen at freeze. That was wrong, and it was the one sentence here
> that could be read as authorising a number to appear. Removed and replaced with
> the actual rule: the flag is the AND of protocol-frozen, the sample floor, and
> an interval excluding zero. It is `false` today.
>
> ### What did NOT change
>
> The cutoff bases, the de-vig method and its order, the 45-minute limit, the
> three-book minimum, the ten named books, the benchmark's name, the credit
> ceiling, and the publication gate and its floor. No rule was changed because a
> result looked better; there are no results.
>
> ---
>
> ## AMENDMENT 5.1, v1.0.8, 2026-09-16 — consistency fixes to Amendment 5
>
> **Approved by Reed Cannon (L3).** The v1.0.7 methodology stands; these make the
> code, schema, tests and documents agree with it.
>
> ### (a) No bell override inside this version
>
> Amendment 5 admitted a confirmed bell as a cutoff "wherever one exists". That
> is withdrawn. **This version's cutoff is exactly two cases, always:**
>
> | | cutoff |
> |---|---|
> | bout 1 | the card's scheduled start |
> | bouts 2..N | the exact completion of the immediately previous bout |
>
> A bell override would silently make one version behave as two — fights with a
> bell scored one way, fights without scored another, inside the same summary
> statistic. A rule that depends on which optional field happens to be populated
> is not frozen.
>
> `fights.bell_at` is **retained as an audit field**, carried on the row and in
> `v_clv_close_reference.actual_bell_at`, and never substituted for the cutoff.
> **Scoring against real bells is a NEW protocol version**, not a per-row upgrade
> inside this one.
>
> ### (b) The cutoff is not a claim about when the fight started
>
> Previous-bout completion is an **operational proxy cutoff**. It is not an
> assertion that the next fight began the instant the last one ended — the
> walkout sits between them.
>
> So the fields that state facts now only hold facts:
>
> | field | filled by |
> |---|---|
> | `fight_odds.bout_started_at` | a **confirmed bell**, and nothing else |
> | `fight_odds.is_live` | keyed to `bout_started_at`; `NULL` when unknown |
> | `fight_odds.proxy_cutoff_at` | **new** — the frozen cutoff, under its own name |
>
> CLV scoring **excludes quotes at or after the frozen cutoff directly**, against
> `proxy_cutoff_at`. It never reads `is_live`, and it never manufactures a
> liveness fact to achieve an exclusion it can perform honestly.
>
> ### (c) Corrections resolve by observation, not by clock
>
> `fight_bout_completions` is append-only, so a correction is a **new row**. A
> correction typically moves the instant **earlier** — 9:31 misheard, 9:30
> confirmed — and `max(completed_at)` would keep returning the superseded 9:31
> forever, leaving a minute of in-window quotes wrongly eligible.
>
> `v_clv_close_reference` therefore resolves the latest applicable completion by
> **`observed_at DESC, id DESC`**. A correction from 9:31 to 9:30 resolves to
> 9:30. The capture job uses the same ordering.
>
> ### (d) Exact bout completions are REQUIRED, not an improvement
>
> All remaining Tier-4-era language is removed. Under Amendment 5 the previous
> bout's exact completion **is the scoring cutoff** for bouts 2..N, so without it
> those fights cannot be scored at all. It is a requirement.
>
> | input | state | required for |
> |---|---|---|
> | running order | absent; **free** to obtain | everything — bout 1 identification and "the previous bout" |
> | exact bout completions | absent; **no free source** | bouts 2..N, entirely |
>
> ---
>
> ## AMENDMENT 5, v1.0.7, 2026-09-16 — the operational cutoff, frozen
>
> *The bell-override clause below is withdrawn by Amendment 5.1. The rest stands.*
>
> **Approved by Reed Cannon (L3). Supersedes Amendment 4.2.**
>
> ### The rule
>
> | | cutoff |
> |---|---|
> | **bout 1** | the card's **scheduled start time** |
> | **bouts 2..N** | the **exact completion time of the immediately previous bout** |
> | ~~any bout with a confirmed bell~~ | ~~the bell, which outranks both~~ — **withdrawn by Amendment 5.1** |
>
> **The scored price is the latest eligible sportsbook snapshot strictly before
> that cutoff.**
>
> ### What this is, said plainly
>
> This is a **CFL closing-price proxy**, not the literal sportsbook closing line,
> and it may never be described as the exact closing line anywhere.
>
> For bouts after the first the cutoff is the previous bout's completion, so the
> proxy can sit **several minutes earlier than the actual bell**. That is
> accepted for this protocol version — not because the gap is thought to be zero,
> but because this is the most consistent, observable and reproducible cutoff
> implementable with the tools currently available, and because every such
> observation shares the same rule.
>
> **Amendment 4.2 is superseded.** It refused this cutoff on the grounds that it
> precedes the bell, and in doing so refused to score anything at all. A
> consistently-early cutoff, named as a proxy and with its lead time recorded, is
> a better measurement than no measurement. **CFL does not wait for a confirmed
> bell in order to score later fights under this version.**
>
> ### Previous-bout completion has two roles, and both are real
>
> 1. it is **this protocol version's scoring cutoff** for the upcoming fight;
> 2. it **triggers aggressive card-night capture** for that fight.
>
> Any remaining language calling it "only an opener, never a cutoff" is stale and
> has been removed.
>
> ### Preserved on every scored observation
>
> | | |
> |---|---|
> | cutoff timestamp | the instant the window closed |
> | cutoff basis | `scheduled_first_bout` or `previous_bout_completion` |
> | selected quote timestamp | `clv_proxy_quoted_at` |
> | lead time | selected quote → cutoff, **exact**, plus a flag saying whether the cutoff itself precedes the bell |
> | source quote IDs and provenance | `clv_source_quote_ids`, `clv_closing_consensus`, `clv_consensus_sha256` |
> | protocol version | `clv_protocol_version`, per row |
>
> The storage constraint requires all of them on a scored row: a figure without
> its cutoff basis and lead time is not writable.
>
> ### If reliable bell timestamps arrive
>
> That is a **NEW PROTOCOL VERSION**, not a revision of this one. Observations
> scored under this version are **never retroactively reinterpreted or
> overwritten**, which is why every row carries its own `clv_protocol_version`.
>
> ### Still excluded
>
> `card_scheduled_start` applied to a later bout remains a non-scoring basis
> (Amendment 4.1): hours early, so it would make the proxy mean something
> different on every fight of the card. It is reported, never scored.
>
> ---
>
> ## AMENDMENT 4.2, v1.0.6, 2026-09-16 — an opener is not a cutoff
>
> **SUPERSEDED BY AMENDMENT 5.** Its scoring restriction is withdrawn: the
> previous bout's completion is this version's cutoff for bouts 2..N. Retained
> below as filed — the reasoning it records is sound about the *gap* and was
> overruled on what to do about it.
>
> **Approved by Reed Cannon (L3).** Removes `previous_bout_completion` from the
> scoring references. Everything else stands.
>
> ### The bug
>
> A pre-fight window has two ends and only one of them is the close.
>
> - It **OPENS** when the previous bout finishes. From that instant the market is
>   pricing the next fight in earnest, and that is when capture goes aggressive.
> - It **CLOSES** when *this* fight starts. That is the cutoff, and the close is
>   the last eligible quote strictly before it.
>
> Amendment 3 used the opener as the cutoff. **If bout 4 ends at 9:30 and bout 5
> walks out at 9:38, taking 9:30 as bout 5's cutoff selects the last quote before
> 9:30 — a price quoted while bout 4 was still being fought — and discards every
> quote from the eight minutes that actually priced bout 5.**
>
> It also made the five-minute capture self-defeating: the job would have
> collected exactly the snapshots the scorer then threw away. The documentation
> already said *the trigger is not the close*; the rule did not.
>
> ### The rule
>
> | | |
> |---|---|
> | scoring cutoffs | **`bell_at`** (any bout) and **`scheduled_first_bout`** (bout 1 only, where the card's start *is* this fight's start) |
> | window openers | **`previous_bout_completion`** and **`card_scheduled_start`** — capture triggers, reported, never cutoffs |
>
> An opener is a **lower** bound on this fight's start. It is safe to capture
> from and can never be scored against. Only an instant that marks *this* fight's
> start may close its window.
>
> `window_opens_at` is stored beside the cutoff, so the snapshots taken inside
> the window are identifiable and become scorable **retrospectively** the moment
> a confirmed bell for that fight arrives — including on cards already captured.
>
> ### The three unscorable states are told apart
>
> | reason | meaning | distance from scorable |
> |---|---|---|
> | `fight_start_unverified` | the window opened, the snapshots exist, nothing says where it closed | **one confirmed bell** |
> | `only_pre_card_price` | only the card's scheduled start is on file; hours early on a late bout | needs order *and* a bell |
> | `no_scheduled_start` | nothing at all | furthest |
>
> ### What is not done
>
> **No end-of-window marker is manufactured to raise coverage.** Until there is a
> defensible way to identify when a fight actually started, bouts 2..N stay
> unscored. The snapshots keep accumulating; the scoring rule stays strict.
>
> ### Spending
>
> Tightened in the same pass: the approved free allowance is a hard constant in
> code. An environment variable may **lower** the cap and never raise it, may
> **raise** the reserve and never lower it, and a provider quota reading above
> the ceiling is clamped and flagged rather than spent. A larger quota upstream
> is not authorisation for this job to spend; any increase above the approved
> free-credit ceiling is **L3**.
>
> ---
>
> ## AMENDMENT 4.1, v1.0.5, 2026-09-16 — a pre-card price is not a late one
>
> **Approved by Reed Cannon (L3).** Withdraws tier 4 from scoring. Everything
> else in Amendment 4 stands — the naming, the lead-time reporting, the
> five-minute capture and the credit ceiling.
>
> **Amendment 4 overreached.** Its argument was sound: a fight cannot begin
> before its own card begins, so a quote strictly before the card's scheduled
> start is verifiably pre-fight for every fight on the card. The conclusion did
> not follow. Such a quote is safely pre-fight and it is **not late** — on the
> twelfth bout it sits hours before the bell.
>
> Scoring it would have made the benchmark mean **different things on different
> fights of the same card**: five minutes before the bell for bout one, four
> hours before it for bout twelve, both labelled the same. A benchmark that moves
> like that is not consistently measured, and the name would have been doing work
> the number could not support.
>
> ### What changes
>
> | | |
> |---|---|
> | scoring bases | **three**: actual bell, previous bout's exact completion, and the card's scheduled start **for the first bout only** |
> | `card_scheduled_start` | **recognised, never scored**. A fight in that state reports `only_pre_card_price` |
> | every scored row's lead time | **exact**. `LOWER_BOUND_REFERENCE_BASES` is empty and a test asserts it |
>
> `only_pre_card_price` is a distinct unscored reason on purpose. "We hold a
> verifiably pre-fight price that is not late enough" and "we hold nothing" are
> different problems with different fixes, and collapsing them would hide which
> one is in front of you.
>
> ### What this costs, stated plainly
>
> Scoring coverage returns to roughly **one observation per card** — the first
> bout — until a running order and exact bout completions exist. At that rate 100
> observations is on the order of 100 cards, not the ~8 Amendment 4 projected.
>
> That is the price of a consistently measured benchmark, and it is the right
> price. An hours-early pre-card price and a five-minute-old price cannot both be
> called the same thing.
>
> ### What is NOT given up
>
> **Capture coverage is unchanged.** Five-minute snapshots run through the whole
> card and **every one is stored**. Nothing is discarded. The dense snapshots are
> precisely what makes a genuinely late proxy available the moment a fight's
> start becomes verifiable — including retrospectively, for cards already
> captured. The stored history is the asset; the scoring rule is what stays
> strict.
>
> ---
>
> ## AMENDMENT 4, v1.0.4, 2026-09-16 — the late pre-fight price proxy
>
> *Tier 4 below is **withdrawn from scoring** by Amendment 4.1 above. The naming,
> the lead-time reporting, the five-minute capture and the credit ceiling all
> stand.*
>
> **Approved by Reed Cannon (L3).** Extends Amendment 3 by adding a fourth tier.
> Nothing in Amendment 3 is withdrawn.
>
> **Exact-to-the-second start detection stops being a blocker.** It was one: under
> Amendment 3 every tier needed a running order, and the tier that covered later
> bouts needed exact completion times with no free source. The result was one
> scorable fight per card and a two-year road to a hundred observations.
>
> ### What the benchmark is called
>
> It is **not the closing line** and may never be described as one on any
> surface, in any artifact, or in any summary. It is the **late pre-fight price
> proxy** — long form, the *scheduled/late closing-price proxy*: the latest quote
> that can be **verified** to have been taken before the fight started.
>
> ### Tier 4 — the card's scheduled start as a bound
>
> | tier | basis | lead time |
> |---|---|---|
> | 1 | actual confirmed bell | exact |
> | 2 | the previous bout's exact completion | exact |
> | 3 | the card's scheduled start, **first bout only** | exact |
> | 4 | **the card's scheduled start, as a lower bound on any fight's start** | **lower bound** |
>
> **A fight cannot begin before its own card begins.** So a quote strictly before
> the card's scheduled start is verifiably pre-fight for *every* fight on that
> card — whether or not the running order is known, and whether or not any bout
> completion was ever recorded.
>
> **Tier 4 bounds; it does not guess.** That distinction is the whole reason it
> is admissible where the event-date fallback is not. The fallback invents an
> instant (18:00 UTC) that has no relationship to anything. Tier 4 uses a real
> published time and makes only the claim that time actually supports.
>
> **What it gives up is lead time, not correctness.** On the twelfth bout the
> proxy sits before the card started, which may be hours before that fight's
> bell. Every tier-4 row is marked `lead_time_is_lower_bound = true`, and the
> lead time is **retained and reported** beside any figure computed from it.
> A reader must be able to see, from the row, how late the price actually was.
>
> ### Capture: five minutes, under a hard ceiling
>
> h2h moneyline is captured **every five minutes** through a live card, for all
> remaining fights, and **every snapshot is stored with its exact timestamp**.
> That is what makes "late" true: the last quote before a card's scheduled start
> is then five minutes old rather than thirty.
>
> **Subject to a hard usage ceiling that keeps CFL inside the existing free API
> allowance.** Measured 2025-01 to 2026-08: 3.7 UFC events a month on average,
> 6 in the busiest month, 12.5 fights a card. At five-minute cadence one card
> costs roughly 93 credits, and six cards would exceed a 500-credit allowance on
> their own. So five minutes is a **target** and the ceiling is a **governor**:
> before each call the job reads the provider's own remaining-credit header,
> counts the cards still to come this month, and takes the finest cadence on the
> ladder 5 → 10 → 15 → 30 that fits. Below a hard floor it stops rather than
> spending a credit it does not have.
>
> Degrading to 30 minutes still clears the frozen 45-minute staleness limit, so
> the governor costs lead time and never correctness. **No paid tier, ever,
> without an L3.**
>
> ### What previous-bout completion is now for
>
> It still improves the answer — it upgrades a later bout from a lower bound to
> an exact lead time — and it still helps identify event flow. It is **no longer
> a prerequisite** for collecting or scoring. The open L3 on where completions
> come from stays open, as an improvement rather than a blocker.
>
> ### What this changes about the timeline
>
> From roughly **1 scorable observation per card** to roughly **12.5**. The floor
> of 100 scored observations across 20 distinct events stops being bound by the
> observation count and becomes bound by the event count: about **20 cards**
> instead of about 100.
>
> The publication gate itself is untouched. It is still 100 and 20 and an
> interval excluding zero, still fail-closed, still at 0.
>
> ---
>
> ## AMENDMENT 3, v1.0.3, 2026-09-16 — the event-flow rule
>
> **Approved by Reed Cannon (L3).** Supersedes Amendment 2 (b) below, by
> narrowing it.
>
> A UFC card is **one scheduled start and then a queue.** Only the first bout
> begins at a time anybody published. Every later bout begins when the one before
> it ends, and the gap between the card's advertised start and the twelfth fight
> walking out is hours.
>
> Amendment 2 (b) admitted `provider_commence` — the card-level commence time —
> as the reference for *every* fight on the card. That is right for one fight out
> of thirteen and wrong for the rest, and wrong in the expensive direction: it
> would mark every quote taken after the first bell as in-play for all thirteen,
> discarding exactly the quotes the later fights close on.
>
> ### The close reference, per fight
>
> | tier | basis | applies to |
> |---|---|---|
> | 1 | **actual confirmed bell** (`fights.bell_at`) | any bout |
> | 2 | **the previous bout's exact completion** | any bout after the first |
> | 3 | **the card's scheduled start** (`scheduled_first_bout`) | **the first bout only** |
> | — | anything else, including the event-date fallback | nothing — the fight is unscored |
>
> A fight whose running order is unknown has no admissible reference at all:
> without an order there is no "previous bout" to reason from, and no fight can
> be identified as the card's first. Unknown is unscored.
>
> ### The trigger is not the close
>
> This is the distinction the amendment turns on, and it is easy to collapse by
> accident. Stated so it cannot be:
>
> - **The previous bout ending is a CAPTURE TRIGGER.** It tells the odds job to
>   begin taking quotes every 30 minutes for the next fight. It governs how much
>   data exists and nothing else. Capture cadence is **not frozen** — it cannot
>   change what a number means, only how many numbers there are.
> - **The CLOSE is the last valid pre-live quote for the upcoming fight.** Any
>   quote captured at or after that fight actually started is excluded, strictly.
>   That is frozen, and `closing_pairs` in `cfl_engine/clv/scoring.py` enforces
>   it.
>
> Getting these the wrong way round would let a quote taken *during* a fight
> score as that fight's closing price. There are four tests named for this in
> `test_scoring.py`.
>
> ### The audit field stays separate
>
> `fights.bell_at` remains the record of when a fight **actually** began,
> reserved for a confirmed bell and never written by the odds job.
> `fight_odds.bout_started_at` is a different thing: the capture-time **belief**
> about when this bout began, stamped on each quote so the close a quote was
> judged against stays recoverable even if a better account arrives later. A
> correction to one never silently rewrites the other.
>
> ### What this costs, and it is the biggest fact about the CLV timeline
>
> Both tier-2 inputs are missing from the database today:
>
> - **Running order.** `fights` has no order column — only `is_main_event`, which
>   names the last bout. Sorting by id would be an inference dressed as a record,
>   and it breaks exactly when a card is reshuffled. Obtainable free: ufcstats
>   lists a card in order.
> - **Exact bout completions.** Nothing records when a bout ended. The result
>   scraper yields an *upper bound* — completion plus unknown lag — which is
>   explicitly refused, because using it would place a bout's start too late and
>   admit in-play quotes as its close.
>
> Until exact completions exist, **only the first bout of each card can be
> scored**: roughly one observation per event, against a floor of 100 across 20
> distinct events. Acquiring them needs a paid live-data feed or a person
> entering times during the card. Both are new standing commitments and are
> escalated, not assumed.
>
> ---
>
> **AMENDMENT 2 (b), v1.0.2, 2026-09-16 — which start bases count.** *Superseded
> in part by Amendment 3 above: `provider_commence` is no longer admissible for
> every fight, only for the card's first bout. The rest stands — the event-date
> fallback was not a schedule then and is not one now.* The
> reference instant is read from `v_fight_start_best` (`dur001_migration.sql`),
> which resolves `bell_at` → latest provider commence → an event-date fallback.
> **Only the first two are admissible here.**
>
> | `start_basis` | admissible as a scheduled start? |
> |---|---|
> | `bell_at` | yes — an actual confirmed bell |
> | `provider_commence` | yes — the provider's scheduled start, which is what Q-01 asks for |
> | `event_date_fallback` | **no** |
>
> The fallback is the event date at 18:00 UTC. It is a placeholder, not a
> schedule, and it is wrong by hours in both directions. Accepting it would put a
> fabricated instant at the centre of the measure and would make a quote look
> fresh or stale according to a constant nobody chose for this purpose. A fight
> whose only basis is the fallback is **unscored** (`no_scheduled_start`), which
> is the same treatment a missing instant gets, because that is what it is.
>
> Recorded because the 2026-09-16 dry-run report first stated that no scheduled
> start instant existed at all. That was wrong: the ledger exists and works, and
> had simply not been collecting long enough to cover any settled card. See the
> correction in [`DRY_RUN_2026-09-16.md`](DRY_RUN_2026-09-16.md).

| option | definition | cost |
|---|---|---|
| **A** | last eligible quote strictly before the **scheduled** card/bout start | scheduled times slip; a delayed card closes early |
| **B** | last eligible quote strictly before the **actual** walkout | needs a reliable walkout timestamp we do not currently store |
| **C** | last eligible quote before the book **takes the market down** | per-book, so different books close at different instants |
| **D** | consensus at a fixed offset (e.g. T−5 min from scheduled start) | uniform and reproducible; discards genuine late movement |

**Recommendation on principle: A**, with the quote required to be within the
staleness limit of Q-01b. It is reproducible from data we already hold, it does
not depend on a field we do not capture, and "before the fight was scheduled to
start" is a sentence a bettor understands. B is the most faithful and should be
revisited if walkout timestamps ever become reliable.

**Q-01b — staleness limit.** A "last quote before start" that was captured
eleven hours earlier is not a closing line. Proposed: a maximum age, measured
from the quote to the reference instant, beyond which the observation is
unscored rather than scored on a stale price. The **value** of that limit is
open; it should be set from capture cadence, not from what it does to the
result.

---

### Q-02 — Eligible books and exclusion rules · proposed **L2**

> **RESOLVED** — named list, ≥3 books, de-vig per book *then* median (ChatGPT
> second-pass review, 2026-09-16).
>
> **THE LIST ITSELF IS FROZEN BY AMENDMENT 2 (v1.0.2), 2026-09-16, approved by
> Reed Cannon.** The 2026-09-16 dry run found that the *rule* had been frozen
> and the *list* had never been written down, which left the discretion sitting
> exactly where a named list exists to remove it.

#### The frozen list

Ten sportsbooks, by name. Names and not ids: an id is a database detail that can
be renumbered, and what is frozen here is which businesses' prices count.

| | | |
|---|---|---|
| FanDuel | DraftKings | BetMGM |
| Caesars | BetRivers | BetWay |
| Unibet | BetOnline.ag | Bovada |
| BetUS | | |

**Where the list came from, which matters more than its contents.** It is the
membership of `v_odds_books_sportsbooks`, a view shipped in `dur001_migration.sql`
**before CLV-001 existed**, defined as *every row of `odds_books` whose name does
not contain "consensus" and is not Polymarket or Kalshi*. It was written to keep
aggregates and prediction markets out of the **totals** market's de-vig, and it
selects the same ten businesses here for the same structural reason. The list was
therefore not assembled by looking at which books would suit a CLV number — it
was already in the repo, for another purpose, under a rule anyone can read.

Two further facts make that checkable rather than merely asserted: **no CLV
figure has ever been computed**, and the same dry run establishes that none is
computable on the present record at all. A list frozen in that state cannot have
been chosen for its effect on a result, because there is no result.

**Coverage was deliberately not a criterion.** Caesars, BetWay and Unibet have
not appeared in the feed since 2026-05-31; they are on the list anyway. Dropping
a book for thin coverage is a judgement made now about which prices count, and
it is the exact judgement freezing is meant to foreclose. A book that never
quotes simply never enters a consensus, which costs nothing. Adding or removing
a name requires its own dated amendment.

Excluded by kind, and not by this list: **aggregates** (`BFO Consensus`,
`CFL Consensus (Odds API)`) — a consensus row is already a blend of other books'
margins, so de-vigging it is a different operation and counting it toward the
three-book floor would double-count its constituents; and **prediction markets**
(Polymarket, Kalshi) under Q-03. `is_eligible_book` in
`cfl_engine/clv/scoring.py` enforces both by name, so neither can re-enter
through a renumbering.

#### The options, as they stood

Options: a **fixed named list** frozen now; a **rule-based** list (any book
meeting stated coverage and cadence criteria); or **all books the feed returns**,
filtered only by R-03.

**Recommendation on principle: a fixed named list, frozen at protocol freeze**,
with additions requiring a dated amendment. DUR-001 already forbids selecting
sportsbooks after results are visible; a fixed list makes that unbreakable
rather than merely prohibited. A rule-based list sounds cleaner but moves the
discretion into the thresholds.

Also to fix: the **minimum number of eligible books** for an observation to
score, and whether that minimum applies per-side.

---

### Q-03 — Exchanges and prediction markets · proposed **L2** (**L3** if admitted as primary)

> **RESOLVED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** Exchanges and prediction markets are **excluded from
> the primary metric**.

Betfair, Polymarket and Kalshi price differently from sportsbooks: commission
rather than vig, and depth that varies with stake. Including them changes what
"the market" denotes.

Options: **exclude entirely**; **include as a frozen sensitivity** reported
beside the primary; **include in the primary consensus**.

**Recommendation on principle: exclude from the primary, admit as a frozen
sensitivity if included at all.** Mixing a commission-based exchange price into
a vig-based consensus produces a number that is not cleanly either. Admitting
them to the primary changes what a published claim refers to, which is why that
branch is L3.

---

### Q-04 — How multiple books become one probability · proposed **L2**

> **RESOLVED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** **Median** across eligible sportsbooks stays the
> primary aggregation. The review was asked to attack the rejection of
> "best available price" rather than agree with it, and rejected it on the
> same grounds.

Options: **median across eligible books** (what ships today); **mean**;
**best available price** (the most favourable to the bet side); **liquidity- or
coverage-weighted**.

**Recommendation on principle: median.** It is what the current implementation
uses, it is robust to a single mispriced book in a way the mean is not, and
`settle_clv.py` already takes the median book's *own booked price* rather than
reconstructing an American price from an aggregate — which matters, because a
reconstructed price may be one no book ever offered.

**Best available price is the option to argue about.** It is arguably the more
honest benchmark for a bettor who shops lines, and it is also the option that
most flatters CLV. That asymmetry is exactly why it should be settled now, by
argument, and not later.

---

### Q-05 — Vigged or de-vigged · proposed **L3**

> **RECOMMENDATION REPLACED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** **Vigged at publish, de-vigged at
> close.** This is a **fourth option**, not one of the three below: the
> posted price is used exactly as posted and only the closing side is
> de-vigged.
>
> The prior recommendation — raw primary, de-vigged sensitivity — is
> superseded. The review's judgement is that it **deferred** the
> contradiction rather than resolving it, which is what the handoff asked
> to be checked.
>
> Which de-vig method applies at close is **still unchosen** — see Q-12.

The sharpest methodological question here, and the one where the shipped
implementation and the rest of the repo point in different directions.

`settle_clv.py` deliberately compares **raw single-side implied probabilities at
both ends**. Its reasoning is sound: `odds_at_publish` is a single-side American
price, and de-vigging it after the fact would require the opposite side at the
same instant, which was not captured. Comparing raw-to-raw is at least
unit-consistent.

But DUR-001 Amendment 1 froze the **power method** as the primary de-vig for
this project, with proportional and Shin as frozen sensitivities. And a raw
single-side implied probability is not a probability — it is a price with the
book's margin inside it. Describing a raw-to-raw difference as a probability
gain would be a mislabelled claim.

| option | what it measures | requires |
|---|---|---|
| **A** | price CLV, vigged both ends — what ships today | nothing new |
| **B** | probability CLV, power de-vig both ends, per DUR-001 | **both sides captured at the publish instant** |
| **C** | A as primary, B as a frozen sensitivity once two-sided publish capture exists | two-sided capture going forward |

**Recommendation on principle: C.** A is what a bettor actually experiences and
is computable on the existing record. B is what a probability claim requires and
is only honestly computable prospectively, from the date two-sided capture at
publish is guaranteed. Reporting both, with the primary named in advance and
never swapped after a result is visible, is the same discipline DUR-001 applies
to its de-vig sensitivities.

**Implication if C is adopted:** two-sided capture at publish time becomes a
capture requirement immediately, because B can never be backfilled. That is a
reason to settle this question early even though publication is far off.

---

### Q-06 — Published probability, or hypothetical wager price · proposed **L3**

> **RECOMMENDATION REPLACED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** The bettor's CLV on the **posted
> price** is the primary and **sole headline** number. Market anticipation
> of the published probability may still be reported separately and may
> **never** carry the CLV label.
>
> The prior recommendation — "both, reported separately" — is superseded:
> the review makes the price measure primary rather than co-equal.

Reed's question, and it needs a distinction stated plainly first.

CFL publishes a **probability**. A bettor takes a **price**. These support two
different statistics, and only one of them is CLV:

- **A — bettor's CLV.** Score the price CFL posted against the close, per §1.
  This is the standard quantity, comparable to what everyone else calls CLV. It
  requires a defensible answer to "what price could a reader actually have
  taken?" — which book, at what moment, at what stake.
- **B — market anticipation.** Ask whether the market moved *toward* CFL's
  published probability between posting and the close. This is honest about what
  CFL actually publishes, but **it is not CLV** and must never carry that label.
  It is a statement about agreement with subsequent market movement.

**Recommendation on principle: C — compute both, report them separately, and
reserve the term "CLV" strictly for A.** B is the more defensible description of
what CFL does; A is the number readers will compare against other sources.
Publishing B under the name CLV would be the single easiest way to make a claim
that is technically computed and substantively misleading.

This is L3 because it decides what the headline number *is*.

---

### Q-07 — Aggregation and weighting · proposed **L3**

> **RECOMMENDATION CONFIRMED AND TIGHTENED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** **Equal weight per
> scored fight.** No Kelly or stake weighting **without a separately frozen
> staking system** — the weighting may not be invented as part of the
> scoring.

How per-fight observations become a card number and a lifetime number.

| option | reading |
|---|---|
| **equal weight per fight** | "our average pick beats the close by X" |
| **weight by stake or Kelly fraction** | "a bettor following us would have beaten the close by X" |
| **weight by market liquidity** | "we beat the close where it mattered" |

These are **different public claims**, not different estimators of one thing.
The stake-weighted version in particular implies a betting strategy CFL does not
publish, and would need one defined before it could be honest.

**Recommendation on principle: equal weight per fight as primary**, because it
matches what CFL actually publishes — a set of picks, not a staking plan — and
because introducing a stake weighting invents a strategy in order to score it.

**Clustering, not weighting, but decided alongside:** the observation unit is one
scored pick; the cluster unit is the **event**. Picks on the same card share
line-movement drivers and are not independent. DUR-001 already uses the UFC
event as its cluster unit; using the same unit here keeps the two comparable.

---

### Q-08 — Minimum sample before any summary is displayed · proposed **L3**

> **RECOMMENDATION EXTENDED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** Keep the **100 scored-observation
> floor** and **add a minimum number of distinct events**, so one or two
> cards cannot dominate the published figure.
>
> The event minimum is **not numerically specified** by the review — see
> Q-13, where the number is the whole content of the rule.

`track-record.html` already promises, in shipped copy: *"these numbers go up
here once 100+ locked picks have both a posted price and a closing price on
record."* That is a published commitment, so the protocol either adopts 100 or
the copy changes with it.

Open: whether 100 is the right floor; whether it counts **scored** observations
or **eligible** ones; whether it applies per-breakout (favourites vs dogs) as
well as overall. The Factor Lab precedent is `MIN_SAMPLE = 100` on market-even
fights, with an explicit `unproven` verdict below it — a good pattern to reuse,
including the part where the surface says "not enough data yet" rather than
going quiet.

**Recommendation on principle: adopt 100 scored observations overall, and apply
the same floor to any breakout**, so a 12-fight dog subset cannot be presented
as a finding.

---

### Q-09 — Uncertainty · proposed **L2**

> **RESOLVED — [ChatGPT review, 2026-09-16](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md).** The **event-cluster bootstrap is primary**; the Wilson
> interval on the beat rate is demoted to a secondary descriptive figure.
>
> Reason: fights on the same card are correlated, so an interval treating
> them as independent overstates precision. This matches DUR-001 §8, which
> already resamples whole events and never individual fights. DUR-001
> amendment (e) would further gate cluster intervals as descriptive-only
> below 20 cards — (e) is still **HELD**, so it is a precedent to weigh, not
> a rule to inherit. See Q-13.

A mean CLV with no interval invites reading noise as edge.

Options: **cluster-robust interval** with the event as cluster (consistent with
Q-07 and DUR-001); **cluster bootstrap over events**; **Wilson interval** on the
beat rate — which is well-behaved at small n and is the interval Factor Lab
already uses.

**Recommendation on principle: report both** — a cluster-robust interval on mean
`clv_pp`, and a Wilson interval on the beat rate — since they answer different
questions ("by how much" and "how often") and the pair is harder to
cherry-pick than either alone.

---

### Q-10 — Cancellation, rescheduling and line movement after the fact · proposed **L2**

R-08 settles the simple cases. The residue is genuinely open:

- A fight **rescheduled to a later card**: is the original market's close scored,
  the new one, or neither? Proposed: **neither** — the original close priced a
  fight that did not happen, and the new market is a different market. The
  forecast is re-locked for the new date if the pick is re-published.
- A fight surviving a **late opponent change**: proposed **exclude** — the
  market after the change prices a different fight from the one the forecast
  was made on, which violates the spirit of R-07 even where the timestamps pass.
- **Post-start quotes**: excluded by Q-01 and R-03.

Needs a reviewer because "different fight" is a judgement the protocol should
make mechanical — probably keyed on whether either fighter id changed after the
forecast lock.

---

### Q-11 — How positive CLV may and may not be described · proposed **L3**

The claim rules, not the computation. Proposed, for review:

**May be said**, once frozen and past the Q-08 floor:

- what was measured, over how many picks, with the interval;
- that CLV is about price, not about winning — a pick can beat the close and
  lose;
- the count of unscored observations alongside (R-05).

**May never be said**, at any sample size:

- any projection of profit, ROI or bankroll growth from a CLV figure;
- "beats the market", "proven edge", or any phrasing that converts a price
  measurement into a claim about winning money;
- a positive CLV figure without its interval and its n;
- a favourable subset (one card, one weight class, favourites only) presented
  without the overall number beside it;
- anything at all while the interval crosses zero — that is reported as
  *"we can't tell yet"*, in those words, matching how Factor Lab reports `lean`.

`COPY_STYLE.md` governs the wording; this fixes the substance.

---

### Q-12 — Which de-vig method applies at close · proposed **L2**

*Raised by the revision, not by the review.*

`CLV_return` needs a **de-vigged closing fair probability**, and the review says
"de-vigged" without naming a method. The repo already has a frozen precedent:
DUR-001 Amendment 1.1 froze the **power** method as this project's primary
de-vig, with proportional and Shin as frozen sensitivities.

| option | note |
|---|---|
| power, matching DUR-001 Amendment 1.1 | consistent with the house method |
| proportional | under-prices favourites, over-prices longshots |
| Shin | leans on an insider-trading interpretation CFL has no evidence for |
| a CLV-specific method with a stated reason | permitted, but the reason has to exist |

**Recommendation: power**, for consistency, with proportional and Shin as frozen
sensitivities on the same pattern.

Diverging from the frozen house method needs a reason. Adopting it silently is
*also* a choice, and one that would be invisible later — which is why this is a
question rather than an assumption.

---

### Q-13 — Minimum distinct events before a summary displays · proposed **L3**

*Raised by the revision, not by the review.*

**Why L3:** the floor is the number itself. It decides when a public CLV figure
may appear at all.

The review requires a distinct-event minimum but gives no number. It is also not
independent of Q-09: an event-cluster bootstrap over very few clusters has
coverage well below nominal, so the floor and the interval method are **one
decision, not two**. DUR-001 hit exactly this and proposed 20 completed cards in
amendment (e), which is still held.

| option | note |
|---|---|
| set from the cluster bootstrap's coverage requirement | derived rather than chosen |
| 20 completed events, matching DUR-001 amendment (e) | consistent, but (e) is not in force |
| a fixed small floor such as 8 or 10 | a round number with nothing behind it |

**Recommendation:** set it from the bootstrap's coverage rather than picking a
round number, and report the figure as **descriptive-only** below the floor
rather than withholding it entirely — withholding invites the question of what
is being hidden, whereas a labelled descriptive number invites none.

---

### Q-14 — May CLV appear in the user interface at all · proposed **L3**

*Raised by the revision. No reviewer recommendation — see below.*

**Why L3:** two documents Reed owns give opposite answers, and Q-11 presupposes
one of them.

> `CLAUDE.md`, line 3 — the top-line product rule:
> "**No closing line value**, no edge percentages, and no market language
> **anywhere in the user interface**."

> `COPY_STYLE.md`, rule 3:
> "**CLV is the north star**, not win rate. When we talk about whether we're
> good, the honest answer is closing-line value — did we get a better price than
> the market closed at — not a hot streak. **Say so.**"

These cannot both hold. Q-11 spends its effort on *how* a positive CLV figure may
be phrased on a surface; `CLAUDE.md` says no such figure may be on a surface in
the first place.

| option | consequence |
|---|---|
| `CLAUDE.md` governs | CLV stays an internal measure, never on a surface. **Q-11 becomes moot** and the publication gate stays shut permanently for the UI |
| `COPY_STYLE.md` governs | CLV may be shown under Q-11's constraints, and `CLAUDE.md` line 3 is amended |
| a middle rule | CLV appears only on a named methodology surface, never on product pages |

**No recommendation is offered.** This is a product-voice decision, not a
methodological one, and a reviewer cannot resolve a conflict between two rules
the owner wrote. Whichever way it goes, **one of the two documents has to be
amended** so they stop contradicting — that is true under every option.

It is worth noting which way the *measurement* work has been pointing: the
protocol has been built on the assumption that a CLV figure eventually reaches a
surface, because that is what the publication gate in R-10 exists to hold shut.
If `CLAUDE.md` governs, the gate is not a gate but a permanent wall, and R-10
should say so plainly instead.

---

## 4. Raw capture requirements

Binding on the capture path **now**, because these cannot be backfilled:

> **Extended 2026-09-16.** Items 7–12 come from the
> [ChatGPT review](../../coordination/reviews/2026-09-16-chatgpt-clv-review.md),
> which was asked what the list was missing. Item 2 is promoted by the
> `CLV_return` definition in §1.1 and **replaces** the previous blocker.

| # | requirement | why it cannot wait |
|---|---|---|
| 1 | book, fighter, American price, UTC capture instant on every quote | R-02; a quote without them is permanently unscorable |
| 2 | **both sides captured AT CLOSE** | the primary measure de-vigs the closing side; one-sided closes are unscorable under it |
| 3 | both sides captured at the publish instant | retained — enables a fair-to-fair sensitivity. **No longer the blocker**: `CLV_return` uses the publish price as posted |
| 4 | every quote retained raw, append-only | R-01 |
| 5 | capture cadence recorded, including gaps | Q-01's staleness limit must be set from real cadence |
| 6 | provider and feed version stored per quote | provenance; a feed change that shifts timing must be detectable |
| 7 | **scheduled and actual bout-start timing**, wherever available | Q-01 resolved to a *scheduled*-close proxy; only actual start times can ever upgrade it, and `bell_at` is populated on 0 of 8,992 fights today |
| 8 | **market suspension / takedown status** | a market removed before the bell is a different object from one still quoting; indistinguishable after the fact |
| 9 | **provider market IDs** | the only stable key when a market is reposted or a fight is rematched |
| 10 | **opponent identity at quote time** | a late opponent change silently redefines what the quote referred to — Q-10 |
| 11 | **provider timestamp AND retrieval timestamp, separately** | collapsing them hides feed lag, and feed lag is exactly what a staleness limit is measuring |
| 12 | **an immutable link from CFL's posted price to the exact source quote** | without it the publish side of `CLV_return` is an assertion rather than a record |

Anything captured without these is not lost — it simply cannot be used for the
definitions that need them.

Item 12 is the direct analogue of the lesson from the PROP-0001 provenance
audit: every v1 lock recorded `code_version` as `…-dirty` with no record of what
dirty was, and the fix was to make each row carry the exact identity of what
produced it. A posted price with no link to its source quote has the same defect.

---

## 5. What freezing means

At freeze:

1. status becomes `frozen`, with the UTC instant and Reed as approver;
2. the sha256 of this file is recorded in `protocol.json` and in the frozen-file
   tripwire, the same mechanism `CFL_RESEARCH_STATE.md` uses;
3. every open question in §3 is resolved to a single rule, in place, with the
   rejected options retained as rejected — not deleted;
4. `settle_clv.py` is reconciled with the frozen rules.

**Freezing does not open the publication gate.** Corrected by Amendment 6 (i);
this list previously said `publication_gate.publication_allowed` becomes `true`
at freeze, which was wrong and was the one sentence in this document that could
be read as authorising a number to appear. Freezing settles **how** the number
is measured. It does not create a number worth showing, and it does not create
one at all — at freeze there were zero scored observations.

`publication_allowed` is the AND of every condition in
`publication_gate.conditions`, and `protocol_frozen` is only the first of them.
The others are the sample floor (**100 scored observations across 20 distinct
events**, counted by `event_id`) and an event-cluster interval excluding zero.
It is `false` today and stays `false` until all three hold — R-10 states the
prohibition, Q-08 and Q-13 set the floor, and `tests/test_clv_protocol.py`
asserts the flag rather than trusting it.

After freeze, changes follow the register's two routes and nothing else: a
**dated amendment** recorded with both hashes and a reason, or a **new protocol
version**. A rule may not be changed because a result looks better, and an
amendment records `motivated_by_observed_results: false` — and it must be true.

---

## 6. What this protocol does not cover

- **Bet sizing, staking or bankroll.** My Book's territory.
- **Whether CFL's picks win.** That is the graded record on `track-record.html`.
  CLV and accuracy are separate claims and are never combined into one headline.
- **Prop and duration markets.** DUR-001 and DUR-002 own those, under their own
  frozen preregistrations. If CLV is ever extended to props it needs its own
  version of this document — the market structure is different.

---

## 7. Review checklist for ChatGPT

1. Are the twelve decided rules in §2 actually settled, or is one of them a
   disguised choice?
2. Q-05 and Q-06 are the two that determine what the published number *means*.
   Is the reasoning right, and is the price/probability distinction in Q-06
   drawn correctly?
3. Q-04's "best available price" and Q-07's stake weighting are the two options
   that would most flatter the result. Are they rejected for the right reasons,
   or merely rejected?
4. Is anything in §3 missing an option that a statistician would insist on?
5. Does §4 capture everything that cannot be backfilled? An omission there is
   the only error in this document that cannot be fixed later.

---

## 8. Open questions summary

| id | question | level | status after the 2026-09-16 review |
|---|---|---|---|
| Q-01 | what "closing line" means (+ staleness limit) | L2 | **resolved** — scheduled-close *proxy*, never "the closing line" |
| Q-02 | eligible books and exclusion rules | L2 | **resolved** — named list, ≥3 books, de-vig per book *then* median |
| Q-03 | exchanges and prediction markets | L2 | **resolved** — excluded from the primary |
| Q-04 | how multiple books become one probability | L2 | **resolved** — median across eligible sportsbooks |
| Q-05 | vigged or de-vigged | **L3** | **APPROVED** — vigged at publish, power-de-vigged at close |
| Q-06 | published probability or hypothetical wager price | **L3** | **APPROVED** — posted price is the sole headline CLV |
| Q-07 | aggregation and weighting | **L3** | **APPROVED** — equal weight; no stake/Kelly without a frozen staking protocol |
| Q-08 | minimum sample before display | **L3** | **APPROVED** — 100 scored observations, breakouts included |
| Q-09 | uncertainty | L2 | **resolved** — event-cluster bootstrap primary, Wilson demoted |
| Q-10 | cancellation, rescheduling, opponent change | L2 | **resolved** — unscored unless re-locked; match on fighter + provider market ID |
| Q-11 | how positive CLV may be described | **L3** | **APPROVED** — stricter wording; n, events, interval and unscored count always |
| Q-12 | which de-vig method applies at close | L2 | **resolved** — power, matching DUR-001 Amendment 1.1 |
| Q-13 | minimum distinct events before a summary displays | **L3** | **APPROVED** — 20 distinct completed UFC events |
| Q-14 | may CLV appear in the user interface at all | **L3** | **APPROVED — YES**, under the frozen protocol and its thresholds |

### Review coverage — complete

**All six L2 resolved; all five L3 have a recommendation.** The first pass
returned four of each; the second pass closed Q-02, Q-10 and Q-11, resolved
Q-12 and recommended on Q-13.

**Q-14 has no reviewer recommendation, by design.** It was raised after the
review and is a product-voice decision that belongs to Reed — and the two
documents he owns give opposite answers, so it cannot be resolved by a reviewer
at all.

### What now goes to Reed

| | |
|---|---|
| **Q-14** | **take this first** — it decides whether Q-11 has a subject |
| Q-11 | how positive CLV may be described, if it may be shown at all |
| Q-05, Q-06 | what the headline number is |
| Q-07, Q-08, Q-13 | how it is aggregated and when it may appear |

---

## 9. Disclosure

**No historical CLV comparison was run in the course of writing this draft.** No
alternative definition in §3 was evaluated against captured data, and no CLV
summary statistic was computed. Every recommendation above rests on an argument
from principle, precedent in this repository, or a stated property of the
data — never on which option produced a better number.

If that ever stops being true, it gets recorded here, and the affected choice
becomes unusable as a preregistered decision.
