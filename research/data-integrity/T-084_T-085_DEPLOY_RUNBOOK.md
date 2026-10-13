# T-084 and T-085 — deployment runbook (2026-10-13)

Conditionally approved by the owner, pending:
- code review of this PR;
- a verified deployment order;
- security checks;
- rollback testing.

This is the order, the checks and the way back. **Nothing in it has been run
against production.**

## Files

| change | apply | roll back | tested by |
|---|---|---|---|
| T-085 chart series | `chart_series_t085.sql` | `chart_series_t085.rollback.sql` | `tests/test_chart_series_t085_sql.py` |
| T-084 UFC record view | `fighter_ufc_record_view.sql` | `fighter_ufc_record_view.rollback.sql` | `tests/test_fighter_ufc_record_sql.py` |
| T-084 pages | merging this PR (GitHub Pages deploy) | reverting the merge commit | `tests/ufc-record.test.js` |

## Rollback testing (done, throwaway Postgres)

**T-085.**
- **Setup:** the five views it depends on are loaded from their production
  definitions (`tests/fixtures/t085_live_dependencies.sql`).
- **The cycle:** pre-change definition → migration → rollback → migration twice.
  The chart output is identical at every step.
- **Fixture coverage:** a 4-book series, a book that joins late (excluded), a
  live quote (ignored), a consensus pseudo-book (excluded) and a fight that
  never reaches 3 books (refused).
- **The rollback file is the production definition exactly.** After applying it
  locally, the normalised `pg_get_viewdef` md5 is `7c88e1a4…`. That is the same
  md5 production returns today, on Postgres 16 locally and 17 in production.

**T-084.**
- **Rollback:** it drops the view only. `fights` and `events` row counts are
  unchanged.
- **Re-apply:** the rollback is re-runnable, and re-applying the view
  afterwards restores the same records.

## Security checks

- **Supabase security advisor baseline,** taken 2026-10-13 before any change:
  - 39 `security_definer_view`;
  - 10 `rls_enabled_no_policy`;
  - 2 `rls_disabled_in_public` (`odds_aliases`, `unmatched_odds`);
  - 8 + 8 definer functions executable by `anon` / `authenticated`;
  - 9 mutable `search_path` functions;
  - leaked-password protection off.

  **None of these comes from T-084 or T-085.** They are listed here so the
  after-check can be compared against them.
- **T-084 view.**
  - It is `security_invoker = on`, so it adds **no** `security_definer_view`
    finding.
  - It reads only `fights` and `events`, which are public-read for both browser
    roles.
  - Tests: browser roles hold SELECT only; a role without access to `fights`
    cannot read through the view.
- **T-085 view.**
  - It stays SECURITY DEFINER, which is required: `fight_odds` is admin-only and
    the market views are the sanctioned path to it.
  - **Its grants are tightened.** Production gives `anon` and `authenticated`
    every privilege on it (`arwdDxtm`). The migration resets that to SELECT
    only, and a test proves it.
  - The same over-broad grants exist on the other definer views. That is outside
    this change and is recorded below.
- **After applying,** re-run the advisor and confirm there are **no new
  findings**.

## Deployment order

T-085 is independent of T-084, so it can go first.

### 1. T-085 (database only; no page change)

1. Snapshot the current output for three fights: 26712 (busiest), 46774 and
   53620 (refused).

   ```sql
   select fight_id, count(*), md5(string_agg(s::text,'|' order by at))
   from v_fight_chart_series s where fight_id = <id> group by 1;
   ```

2. Apply `chart_series_t085.sql`.
3. Re-run step 1. The hashes must match.
   `EXPLAIN ANALYZE` for 46774 must be under 1 s (it was 5.8 s).
4. Grants: `has_table_privilege` returns SELECT only for `anon` and
   `authenticated`.
5. Run `verify-live.yml` with `fight_ids = 46774,53620`. The Fight Lab job
   reports `chartMsAfterPage`, which should drop from about 2,200 ms.
6. **If any check fails:** apply `chart_series_t085.rollback.sql` and re-run
   step 1.

### 2. T-084 view (database), BEFORE the page deploy

1. Apply `fighter_ufc_record_view.sql`.
2. As `anon`, check `select * from v_fighter_ufc_record where fighter_id in
   (3839, 4117, 1106, 2802, 1999)`. Expected:

   | fighter | id | record |
   |---|---|---|
   | Jon Jones | 3839 | 22-1, 1 NC |
   | Islam Makhachev | 4117 | 18-1 |
   | Alexander Volkanovski | 1106 | 15-3 |
   | Katlyn Cerminara | 2802 | 11-6 |
   | Michael Bisping | 1999 | 20-9 |

   All of these were checked against UFCStats.
3. Grants: SELECT only, and `reloptions` contains `security_invoker=on`.
4. Re-run the security advisor: no new findings.

**Why the view goes first.** The pages read the view. If they deploy first,
every record shows "—" (pages fall back to the labelled career record) until
the view exists. That is ugly, but it is never wrong.

### 3. T-084 pages

1. Merge this PR. GitHub Pages deploys it.
2. Run `verify-live.yml`. The served-bytes job must match; the Fight Lab job
   still passes, because records agree with chips and tape.
3. Spot-check by hand, in a browser:
   - the `fighters.html` card for Jon Jones reads UFC 22-1-0;
   - the `h2h.html` "UFC wins" row;
   - an `event.html` card row.
4. The next prerender run (6-hourly) rewrites the `/f/` stubs from the view.
   If the view were missing, the prerender would fail loudly rather than
   publish stubs without a record.

### Rolling back T-084

1. Revert the merge commit first, which restores the old pages.
2. Then apply `fighter_ufc_record_view.rollback.sql`.

In the other order, the pages still deployed would show "—", which is safe but
needless.

## Known, not in scope here

- **Galanti still reads UFC 1-0** after T-084. The view counts what `fights`
  holds, and `fights` still holds the DWCS card. That is T-086's job; see its
  plan.
- **Other definer views grant browser roles more than SELECT.**
  - CORRECTED 2026-10-13. An earlier draft said none of them could be written
    through. That was wrong. `v_odds_books_sportsbooks` could be, so a browser
    could delete a sportsbook and, by cascade, its odds history.
  - It was fixed on production the same day ([D-025](../../coordination/DECISIONS.md),
    cannhaven-wq/Cage-Metrics#67).
  - `v_prop_projections_current` can also be written through, but it is
    `security_invoker` over a table whose RLS is read-only, so it is safe.
  - The rest cannot be written through. A grant hygiene pass is still worth
    doing, as a separate task.
- **The advisor's two `rls_disabled_in_public` findings** (`odds_aliases`,
  `unmatched_odds`) predate this work. They should be looked at separately.
