// Regression test — the build scripts cannot page by OFFSET again. T-027.
//
// THE DEFECT THIS PINS
//
// build/factor-rates.js paged every read with:
//
//     build().range(from, from + 999)      // LIMIT 1000 OFFSET n
//
// and no .order(). Those are N separate statements, so the code was correct
// only if Postgres returned the same row order for each one. It makes no such
// promise. For a large filtered scan — fight_odds, 110k rows filtered to ~16k,
// sixteen requests — a parallel sequential scan can hand back a different order
// per execution, and then page n+1 is a window into a differently ordered
// result: rows near every boundary are dropped, others duplicated.
//
// What made it survive review is that the row COUNT still looks right. You get
// about 16,000 rows either way. They are just not the same 16,000, and the
// duplicates quietly corrupt the median-across-books as well.
//
// The observable consequence was factor-rates.json publishing
// market_even_cohort = 869 where a direct query counts 1,220, on an identical
// 8,739-fight denominator.
//
//   node tests/factor-rates-paging.test.js

'use strict';

const fs = require('fs');
const path = require('path');
const { fetchAllKeyset } = require('../build/paginate.js');

let passed = 0;
const failures = [];
const pending = [];
function t(name, fn) {
  const done = (err) => { if (err) failures.push(`${name}\n      ${err.message}`); else passed += 1; };
  const p = (async () => fn())().then(() => done(), done);
  pending.push(p);
  return p;
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }
function eq(a, b, what) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${what || 'value'}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
  }
}
async function throwsAsync(fn, what) {
  let threw = false;
  try { await fn(); } catch (e) { threw = true; }
  if (!threw) throw new Error(`${what || 'call'} should have thrown but did not`);
}

// --------------------------------------------------------------- the fake DB
//
// A minimal PostgREST-shaped query builder over an in-memory table. `scramble`
// decides the order rows come back in for each STATEMENT, which is the whole
// point: it is how the real planner is allowed to behave when no ORDER BY is
// given.

function makeTable(rows, opts) {
  const o = opts || {};
  let statements = 0;
  const api = {
    get statements() { return statements; },
    rows,
    from() {
      statements += 1;
      const n = statements;
      let working = rows.slice();
      if (o.scramble) working = o.scramble(working, n);
      const q = {
        _order: null, _limit: null, _gt: null, _from: null, _to: null,
        order(col, x) { q._order = { col, asc: !x || x.ascending !== false }; return q; },
        limit(k) { q._limit = k; return q; },
        gt(col, v) { q._gt = { col, v }; return q; },
        range(from, to) { q._from = from; q._to = to; return q; },
        then(resolve, reject) { return Promise.resolve(q._run()).then(resolve, reject); },
        _run() {
          let out = working;
          if (q._gt) out = out.filter((r) => r[q._gt.col] > q._gt.v);
          if (q._order) {
            const { col, asc } = q._order;
            out = out.slice().sort((a, b) => (a[col] < b[col] ? -1 : a[col] > b[col] ? 1 : 0));
            if (!asc) out.reverse();
          }
          if (q._from != null) out = out.slice(q._from, q._to + 1);
          else if (q._limit != null) out = out.slice(0, q._limit);
          return { data: out, error: null };
        },
      };
      return q;
    },
  };
  return api;
}

// The algorithm as it was, reproduced here so the reason for the change is
// pinned rather than described. If this ever stops losing rows the test below
// is no longer demonstrating anything and should be re-read, not deleted.
async function fetchAllOffset(build, page) {
  const out = [];
  const p = page || 1000;
  for (let from = 0; ; from += p) {
    const { data, error } = await build().range(from, from + p - 1);
    if (error) throw new Error(error.message);
    out.push(...data);
    if (data.length < p) break;
  }
  return out;
}

const makeRows = (n) => Array.from({ length: n }, (_, i) => ({ id: i + 1, v: `r${i + 1}` }));

// A planner that returns a different order on every statement. Rotating by the
// statement number is deterministic (so this test cannot flake) while still
// being a genuinely different order each time, which is exactly the property
// Postgres declines to rule out.
const rotate = (arr, n) => arr.slice(n % arr.length).concat(arr.slice(0, n % arr.length));

// ------------------------------------------------------- the defect is real

t('OFFSET paging loses and duplicates rows when the scan order moves', async () => {
  const rows = makeRows(5000);
  const db = makeTable(rows, { scramble: rotate });
  const got = await fetchAllOffset(() => db.from(), 1000);

  const ids = new Set(got.map((r) => r.id));
  ok(ids.size < rows.length, 'expected rows to go missing, but every id survived');
  ok(got.length > ids.size, 'expected duplicates alongside the losses');

  // The signature that hid this in production: the count looks about right.
  ok(got.length >= rows.length - 1000, `count looked plausible: ${got.length} of ${rows.length}`);
});

t('keyset paging returns every row exactly once despite the same scan order', async () => {
  const rows = makeRows(5000);
  const db = makeTable(rows, { scramble: rotate });
  const got = await fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 });

  eq(got.length, rows.length, 'row count');
  eq(new Set(got.map((r) => r.id)).size, rows.length, 'distinct ids');
  eq(got.map((r) => r.id), rows.map((r) => r.id), 'exact ids, in key order');
});

t('keyset paging is unchanged by a hostile order, not merely by a lucky one', async () => {
  // Reverse on every statement — the worst case for OFFSET, no case at all
  // for keyset, because a page is defined by data rather than by position.
  const rows = makeRows(3000);
  const db = makeTable(rows, { scramble: (a) => a.slice().reverse() });
  const got = await fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 });
  eq(got.map((r) => r.id), rows.map((r) => r.id), 'ids');
});

t('rows inserted mid-read cannot shift the window', async () => {
  // fight_odds is append-only and written every 5 minutes by odds.yml, so a
  // read of it genuinely can race an insert. Under OFFSET that shifts every
  // later page; under keyset a higher id is simply picked up or not.
  const rows = makeRows(2000);
  const db = makeTable(rows, {
    scramble: (a, n) => (n === 2 ? a.concat([{ id: 9001, v: 'inserted' }]) : a),
  });
  const got = await fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 });
  const ids = got.map((r) => r.id);
  eq(new Set(ids).size, ids.length, 'no duplicates');
  ok(ids.slice(0, 2000).every((id, i) => id === i + 1), 'the pre-existing 2000 all arrive, in order');
});

t('an exact multiple of the page size terminates and does not repeat', async () => {
  const rows = makeRows(2000);
  const db = makeTable(rows);
  const got = await fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 });
  eq(got.length, 2000, 'row count at an exact page multiple');
  eq(db.statements, 3, 'two full pages plus one empty page to confirm the end');
});

t('an empty table is not an error', async () => {
  const db = makeTable([]);
  eq(await fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 }), [], 'empty');
});

// ------------------------------------------------- it fails loudly, not quietly

t('a select list missing the key throws instead of looping or truncating', async () => {
  const rows = makeRows(2000).map((r) => ({ v: r.v }));   // no id
  const db = makeTable(rows);
  await throwsAsync(() => fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 }),
    'paging on a key the rows do not carry');
});

t('a non-unique key throws rather than silently skipping rows', async () => {
  // .gt() is strictly greater, so a repeated key would skip every row sharing
  // it. That must be an error, not a quiet loss — quiet loss is the bug.
  const rows = Array.from({ length: 2000 }, (_, i) => ({ id: 7, v: `r${i}` }));
  const db = makeTable(rows);
  await throwsAsync(() => fetchAllKeyset(() => db.from(), { key: 'id', page: 1000 }),
    'paging on a non-unique key');
});

// ------------------------------------------------------------- the call sites

t('factor-rates.js pages by keyset and every select carries the key', () => {
  const SRC = fs.readFileSync(path.join(__dirname, '..', 'build', 'factor-rates.js'), 'utf8');

  ok(/fetchAllKeyset/.test(SRC), 'factor-rates.js must use the keyset paginator');
  ok(!/\.range\(/.test(SRC), 'the OFFSET paging is back in factor-rates.js');

  // The fetch that was actually short. Without `id` in the select the
  // paginator throws, so this is belt-and-braces, but it is the one line whose
  // removal would break the build at 6am on a cron.
  ok(/from\('fight_odds'\)\s*\.select\('id,/.test(SRC),
    'the fight_odds select must include id');

  for (const tbl of ['events', 'fights', 'fighters']) {
    const m = new RegExp(`from\\('${tbl}'\\)\\s*\\.select\\(\\s*\\n?\\s*'id[,']`);
    ok(m.test(SRC), `the ${tbl} select must include id`);
  }
});

t('the published artifact is untouched by this change', () => {
  // T-027 fixes the reader. Regenerating the numbers is a separate, owner-gated
  // step, because stats.html verdicts move. If this file changes in the same
  // commit as the fix, that gate was skipped.
  const j = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'factor-rates.json'), 'utf8'));
  eq(j.dataset.market_even_cohort, 869,
    'factor-rates.json was regenerated alongside the paging fix — that publishes new verdicts');
});

// ----------------------------------------------------------------- report
(async () => {
  for (const fn of pending) await fn;
  if (failures.length) {
    console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
    failures.forEach((f) => console.log(`  ✗ ${f}\n`));
    process.exit(1);
  }
  console.log(`\n  ${passed} passed — pagination is keyset, and the artifact is unchanged.\n`);
})();
