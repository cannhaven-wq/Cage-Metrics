# Fight 8566 (UFC 17) — conflicting result, documented, not corrected

**Verdict: no change.** The sources still conflict, and no third source could
be reached, so under the CFL Owner's E4 condition the record stays as it is.

## The fight

- **Fight id:** 8566
- **Event:** UFC 17: Redemption, 1998-05-15
- **Division:** heavyweight
- **Bout:** Andre Roberts (fighter 4625) vs. Harry Moskowitz (fighter 2165)

Both sources agree on who fought and who won (Roberts). They disagree only on
how the fight ended.

| source | method | round / time |
|---|---|---|
| CFL database (scraped from UFCStats, last updated 2026-04-27) | Decision, unanimous | round 2, 3:00 |
| Wikipedia, *UFC 17* results table (MediaWiki API, 2026-10-21) | KO (elbow) | 3:15 |

The fight has no round-by-round records in our database (it is one of the
21 in T-093).

## Why it isn't settled

- **UFCStats**, the source our record came from, serves GitHub's runners a
  "Checking your browser" page, so it can't be re-read automatically.
- **Sherdog and Tapology** would be independent third sources. Reading them
  needs a new automated fetch, and the CFL Owner ruled out new
  infrastructure on 2026-10-21.
- A record from memory or recollection is not evidence.

## What would settle it

A person opens the UFCStats fight page and the Sherdog fight page in a
browser and notes what each says. If both say KO/TKO (elbow), the owner has
already authorized correcting fight 8566's method, round and time in one
statement. Nothing else gets touched.
