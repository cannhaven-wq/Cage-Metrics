// ---------------------------------------------------------------------------
// Keyset pagination for PostgREST / Supabase reads.
//
// WHY THIS EXISTS (T-027)
//
// The build scripts used to page with `.range(from, from + 999)` and no
// `.order()`. That is `LIMIT 1000 OFFSET n` issued as N *separate* statements,
// and it is only correct if Postgres returns the same row order every time.
// Postgres does not promise that. Without ORDER BY the order is whatever the
// plan produces, and for a large filtered scan — where a parallel sequential
// scan hands blocks to workers as they ask for them — it can differ between
// two executions of the identical query.
//
// When it does differ, OFFSET paging is not "slightly out of order". Page n+1
// is a window into a *differently ordered* result, so rows near every page
// boundary are silently skipped and others silently duplicated. The row count
// still looks about right, which is what makes it hard to see: you get ~16,000
// rows either way, but they are not the same ~16,000.
//
// THE FIX
//
// Page by a key instead of by offset: order by a unique ascending column and
// ask for rows strictly greater than the last one seen. Each page is then
// defined by data rather than by position, so it does not matter what order
// the planner chose or whether rows were inserted while we were reading.
//
// REQUIREMENT: `key` must be UNIQUE and selected by the query.
// `.gt(key, last)` is strictly greater, so duplicate key values would skip
// every row sharing the last page's final key. A primary key satisfies this;
// anything else has to be checked before it is used here.
// ---------------------------------------------------------------------------

const DEFAULT_PAGE = 1000;

async function fetchAllKeyset(build, opts) {
  const o = opts || {};
  const key = o.key || 'id';
  const page = o.page || DEFAULT_PAGE;
  const out = [];
  let after = o.after === undefined ? null : o.after;

  for (;;) {
    let q = build().order(key, { ascending: true }).limit(page);
    if (after !== null) q = q.gt(key, after);

    const { data, error } = await q;
    if (error) throw new Error(error.message);
    if (!data || data.length === 0) break;

    out.push(...data);
    if (data.length < page) break;

    const last = data[data.length - 1];
    const next = last == null ? undefined : last[key];
    // Without the cursor value there is no way to advance, and the loop would
    // either repeat the same page forever or silently stop. Say so instead:
    // the usual cause is a select list that forgot to include the key.
    if (next === undefined || next === null) {
      throw new Error(
        `paginate: rows do not carry the key "${key}" — add it to the select `
        + 'list, or pass { key } naming a unique column that is selected.',
      );
    }
    // Non-uniqueness has to be caught HERE, on the page that reveals it, not by
    // noticing later that the cursor failed to move. `.gt()` is strictly
    // greater, so if anything else on this page carries the last row's key, the
    // next request skips those rows — and if the WHOLE page carries it, the
    // next request returns nothing and the read ends early, quietly short.
    // That silent truncation is the same class of bug as the one this module
    // exists to remove, so it throws.
    let ties = 0;
    for (const r of data) if (r && r[key] === next) ties += 1;
    if (ties > 1) {
      throw new Error(
        `paginate: ${ties} rows share the key ${String(next)} on "${key}" — keyset `
        + 'paging needs a unique key, or those rows would be skipped. Page by a '
        + 'primary key, or add a tiebreak column.',
      );
    }
    after = next;
  }

  return out;
}

module.exports = { fetchAllKeyset, DEFAULT_PAGE };
