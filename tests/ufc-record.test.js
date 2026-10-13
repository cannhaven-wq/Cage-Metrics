/* ==========================================================================
   tests/ufc-record.test.js — T-084. Every public UFC record comes from
   v_fighter_ufc_record through ufc-record.js, never from fighters.ufc_*.

   Run:  node tests/ufc-record.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const U = require('../ufc-record.js');

let passed = 0;
const failures = [];
function t(name, fn) {
  return Promise.resolve().then(fn).then(() => { passed += 1; },
    err => failures.push(`${name}\n      ${err.message}`));
}
function eq(a, b, what) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${what || 'not equal'}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);
  }
}
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }
const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');

// A stand-in Supabase client that records what was asked.
function fakeSb(rows, opts) {
  opts = opts || {};
  const calls = [];
  const sb = {
    calls,
    from(name) {
      const q = { name, filters: [], ordered: null, range: null };
      calls.push(q);
      const api = {
        select() { return api; },
        order(col) { q.ordered = col; return api; },
        in(col, vals) { q.filters.push([col, vals]); return api; },
        range(a, b) { q.range = [a, b]; return api; },
        then(res, rej) {
          if (opts.error) return Promise.resolve({ data: null, error: { message: 'boom' } }).then(res, rej);
          let data = rows;
          if (q.filters.length) data = rows.filter(r => q.filters[0][1].includes(r.fighter_id));
          if (q.range) data = data.slice(q.range[0], q.range[1] + 1);
          return Promise.resolve({ data, error: null }).then(res, rej);
        },
      };
      return api;
    },
  };
  return sb;
}

const ROWS = [
  { fighter_id: 3839, ufc_wins: 22, ufc_losses: 1, ufc_draws: 0, ufc_no_contests: 1 },
  { fighter_id: 4289, ufc_wins: 1, ufc_losses: 3, ufc_draws: 0, ufc_no_contests: 0 },
];

(async () => {
  await t('the view overwrites the stored totals (regression: Jones 12-11 vs 22-1)', () => {
    const f = [{ id: 3839, ufc_wins: 12, ufc_losses: 11, ufc_draws: 0 }];
    U.apply(f, ROWS);
    eq([f[0].ufc_wins, f[0].ufc_losses, f[0].ufc_draws, f[0].ufc_no_contests], [22, 1, 0, 1]);
  });

  await t('a fighter with no row has no completed UFC fight: 0-0-0, never the stored total', () => {
    const f = [{ id: 24066, ufc_wins: 3, ufc_losses: 2, ufc_draws: 0 }];
    U.apply(f, ROWS);
    eq([f[0].ufc_wins, f[0].ufc_losses, f[0].ufc_draws], [0, 0, 0]);
  });

  await t('if the view could not be read the fields are emptied, not left stale', () => {
    const f = [{ id: 3839, ufc_wins: 12, ufc_losses: 11, ufc_draws: 0 }];
    U.apply(f, null);
    eq([f[0].ufc_wins, f[0].ufc_losses, f[0].ufc_draws, f[0].ufc_record_unavailable], [null, null, null, true]);
  });

  await t('load by ids asks only for those fighters, in chunks', async () => {
    const sb = fakeSb(ROWS);
    const ids = Array.from({ length: 320 }, (_, i) => i + 1).concat([3839, 3839]);
    const rows = await U.load(sb, ids);
    eq(sb.calls.length, 3, 'expected 3 chunked requests for 321 ids');
    ok(sb.calls.every(c => c.name === 'v_fighter_ufc_record'), 'read something other than the view');
    eq(rows.map(r => r.fighter_id), [3839]);
  });

  await t('load all pages in a stable order (T-027: unordered pages drop rows)', async () => {
    const many = Array.from({ length: 2500 }, (_, i) => ({ fighter_id: i + 1, ufc_wins: 1, ufc_losses: 0, ufc_draws: 0, ufc_no_contests: 0 }));
    const sb = fakeSb(many);
    const rows = await U.load(sb, null, { all: true });
    eq(rows.length, 2500);
    ok(sb.calls.every(c => c.ordered === 'fighter_id'), 'a page was requested without ORDER BY fighter_id');
    eq(sb.calls.length, 3);
  });

  await t('a failed read resolves to null instead of throwing', async () => {
    eq(await U.load(fakeSb(ROWS, { error: true }), [3839]), null);
    eq(await U.load(fakeSb(ROWS, { error: true }), null, { all: true }), null);
  });

  // ------------------------------------------------------------ the surfaces
  // Every page that shows a UFC record, or decides "no UFC fights" from it.
  const PAGES = ['fighters.html', 'event.html', 'h2h.html', 'cardio.html',
                 'index.html', 'fighter.html', 'fight.html'];

  await t('every record-showing page loads ufc-record.js after _auth.js', () => {
    PAGES.forEach(p => {
      const src = read(p);
      ok(/<script src="ufc-record\.js\?v=\d+"><\/script>/.test(src), `${p} does not load ufc-record.js`);
      ok(src.indexOf('ufc-record.js') > src.indexOf('_auth.js'), `${p} loads ufc-record.js before _auth.js`);
      ok(/cflUfcRecord\.(attach|apply)\(/.test(src), `${p} never applies the authoritative record`);
    });
  });

  await t('no record-showing page selects fighters.ufc_* any more', () => {
    PAGES.forEach(p => {
      const src = read(p).replace(/\/\/.*$/gm, '');
      const selects = src.match(/\.select\('[^']*'\)/g) || [];
      selects.forEach(s => ok(!/ufc_(wins|losses|draws)/.test(s), `${p} still selects ${s}`));
      ok(!/fighterColumns = '[^']*ufc_wins/.test(src), `${p} still selects ufc_wins via a column list`);
    });
  });

  await t('the prerendered stubs take the record from the view and refuse to run without it', () => {
    const src = read('build/prerender.js');
    ok(/require\('\.\.\/ufc-record\.js'\)/.test(src), 'prerender does not use ufc-record.js');
    ok(/ufcRows == null\) throw/.test(src), 'prerender would publish stubs without a record');
    const fsel = src.slice(src.indexOf("from('fighters')"), src.indexOf("from('fighters')") + 200);
    ok(!/ufc_wins/.test(fsel), 'prerender still selects fighters.ufc_wins');
  });

  await t('the migration keeps fighters.ufc_* (owner: preserve for now) and writes nothing', () => {
    const sql = read('fighter_ufc_record_view.sql').replace(/--.*$/gm, '');
    ok(!/\b(drop|alter)\s+table\b/i.test(sql), 'the migration alters or drops a table');
    ok(!/\b(insert|update|delete|truncate)\b/i.test(sql), 'the migration writes data');
    ok(/security_invoker\s*=\s*on/i.test(sql), 'the view is not security_invoker');
    ok(/revoke all on public\.v_fighter_ufc_record from anon, authenticated/i.test(sql), 'grants not reset for both roles');
  });

  if (failures.length) {
    console.error(`ufc-record: ${failures.length} failed, ${passed} passed`);
    failures.forEach(f => console.error('  ✗ ' + f));
    process.exit(1);
  }
  console.log(`ufc-record: ${passed} passed`);
})();
