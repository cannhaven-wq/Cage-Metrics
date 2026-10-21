/* ==========================================================================
   tests/subscription-boundary.test.js — the T-061 boundary, drawn but not built.

   entitlements.js::SURFACES says which surfaces are Free and which are Pro.
   entitlements.js::PRO_GATES_DRAFT says where each Pro surface WOULD be
   enforced. research/commercial/t061_pro_gates.DRAFT.sql is that enforcement,
   written and NOT applied (D-019: no paywall before there is a way to pay).

   These three must agree, and the draft must stay a draft:

     - every Pro surface has a drafted gate or is explicitly `not_built`;
     - every drafted gate exists in the SQL and calls current_user_is_pro();
     - no free surface's view is revoked or wrapped by the draft;
     - nothing is enforced yet, and no root .sql file applies a gate;
     - the draft cannot be applied by accident.

   The behaviour of the SQL itself is tested on a throwaway Postgres by
   tests/test_t061_pro_gates_sql.py.

   Run:  node tests/subscription-boundary.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');
const E = require('../entitlements.js');
const DRAFT_RAW = read(E.PRO_GATES_DRAFT_FILE);
const DRAFT = DRAFT_RAW.replace(/--[^\n]*/g, ' ');

let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); } }
function ok(c, m) { if (!c) throw new Error(m); }
function eq(a, b, m) { if (a !== b) throw new Error((m || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }

const pro = E.SURFACES.filter(s => s.tier === 'pro');
const free = E.SURFACES.filter(s => s.tier === 'free');

t('every Pro surface has a drafted gate or is declared not built', () => {
  pro.forEach(s => ok(E.PRO_GATES_DRAFT[s.key], 'Pro surface ' + s.key + ' has no entry in PRO_GATES_DRAFT'));
  Object.keys(E.PRO_GATES_DRAFT).forEach(k =>
    eq(E.tierFor(k), 'pro', 'PRO_GATES_DRAFT names ' + k + ', which is not a Pro surface'));
});

t('no free surface is given a gate', () => {
  free.forEach(s => ok(!E.PRO_GATES_DRAFT[s.key], 'free surface ' + s.key + ' has a Pro gate drafted'));
});

t('every drafted gate exists in the SQL and is decided by current_user_is_pro()', () => {
  Object.keys(E.PRO_GATES_DRAFT).forEach(k => {
    const g = E.PRO_GATES_DRAFT[k];
    if (g.kind === 'not_built') { eq(g.object, null, k + ' is not built but names an object'); return; }
    if (g.kind === 'view') {
      const m = DRAFT.match(new RegExp('CREATE OR REPLACE VIEW public\\.' + g.object + ' AS([\\s\\S]*?);'));
      ok(m, k + ': view ' + g.object + ' is not in the draft');
      ok(/current_user_is_pro\(\)/.test(m[1]), k + ': ' + g.object + ' does not call current_user_is_pro()');
      ok(new RegExp('GRANT SELECT ON public\\.' + g.object + ' TO anon, authenticated').test(DRAFT),
         k + ': ' + g.object + ' is not granted to BOTH browser roles (an anon-only grant reads empty for members)');
      if (g.replaces) {
        ok(new RegExp('REVOKE ALL ON public\\.' + g.replaces + ' FROM PUBLIC, anon, authenticated').test(DRAFT),
           k + ': the ungated ' + g.replaces + ' stays readable, so the wrapper gates nothing');
      }
    } else if (g.kind === 'policy') {
      const m = DRAFT.match(new RegExp('CREATE POLICY "' + g.object.replace(/[()]/g, '\\$&') + '"([\\s\\S]*?);'));
      ok(m, k + ': policy "' + g.object + '" is not in the draft');
      ok(/current_user_is_pro\(\)/.test(m[1]), k + ': the policy does not call current_user_is_pro()');
      ok(new RegExp('DROP POLICY IF EXISTS "' + g.replaces + '"').test(DRAFT),
         k + ': the old permissive policy is not dropped — policies OR together, so it would keep the door open');
    } else if (g.kind === 'function') {
      const m = DRAFT.match(new RegExp('CREATE OR REPLACE FUNCTION public\\.' + g.object + '\\(\\)([\\s\\S]*?)\\$\\$;'));
      ok(m, k + ': function ' + g.object + ' is not in the draft');
      ok(/current_user_is_pro\(\)/.test(m[1]), k + ': ' + g.object + '() does not call current_user_is_pro()');
    } else {
      throw new Error(k + ': unknown gate kind ' + g.kind);
    }
  });
});

t('the alert allowance is split exactly as alerts_migration.sql documents it', () => {
  // One place, one line (D-019 / alerts_migration.sql §0). If the draft and the
  // documented line ever disagree, one of them is wrong.
  const doc = read('alerts_migration.sql').match(/T-061 turns this into:\s*--\s*(SELECT CASE[^;]*;)/);
  ok(doc, 'alerts_migration.sql no longer documents the T-061 line');
  ok(DRAFT.indexOf(doc[1]) !== -1, 'the draft alert_quota() is not the documented line: ' + doc[1]);
});

t('the draft never revokes or wraps a free surface', () => {
  const freeViews = ['v_fight_market_movement', 'v_fight_odds_latest_by_book', 'v_fight_market_vigfree',
    'v_fight_chart_meta', 'v_fight_market_movement_books', 'v_fight_market_horizons',
    'v_fighter_consistency', 'v_fighter_ufc_record', 'v_model_picks_graded', 'v_pre_fight_graded',
    'fighters', 'fights', 'events'];
  freeViews.forEach(v => ok(!new RegExp('REVOKE[^;]*ON (TABLE )?public\\.' + v + '\\b[^;]*;').test(DRAFT),
    'the draft revokes the free surface ' + v));
  ok(!/\bDROP (TABLE|VIEW)\b|\bDELETE FROM\b|\bTRUNCATE\b/i.test(DRAFT), 'the draft is destructive');
});

t('the draft cannot be applied by accident', () => {
  ok(/current_setting\('cfl\.t061_apply', true\) IS DISTINCT FROM 'yes'/.test(DRAFT),
     'the draft has no session-flag guard');
  ok(DRAFT.indexOf('RAISE EXCEPTION') < DRAFT.indexOf('CREATE OR REPLACE VIEW'),
     'the guard runs after the first object is created');
  ok(/DRAFT\. NOT APPLIED/.test(DRAFT_RAW), 'the header no longer says it is a draft');
  ok(!fs.existsSync(root(path.basename(E.PRO_GATES_DRAFT_FILE))), 'a copy of the draft sits at the repo root');
  ok(!/RAISE\s+NOTICE/i.test(DRAFT) && !/DROP\s+TRIGGER\s+IF\s+EXISTS/i.test(DRAFT),
     'the draft carries a statement that hangs the Supabase MCP tool');
});

t('nothing is enforced yet, and no applied SQL carries a Pro gate', () => {
  eq(E.SURFACES.filter(s => s.enforced).length, 0, 'a surface is enforced before T-061');
  fs.readdirSync(root('.')).filter(f => f.endsWith('.sql')).forEach(f => {
    const sql = read(f).replace(/--[^\n]*/g, ' ');
    ok(!/v_pro_fight_chart|watchlist insert own \(pro\)|v_fight_market_movement_lookback/.test(sql),
       f + ' (a root migration) applies a T-061 gate');
    ok(!/THEN 50 ELSE 3/.test(sql), f + ' already splits the alert allowance');
  });
});

t('no page reads a Pro view yet, and none gates a fetch on the client', () => {
  // When T-061 lands the pages switch to the v_pro_* names in the same PR as
  // the SQL. Until then a page reading one would show an empty chart to
  // every reader, with no reason.
  fs.readdirSync(root('.')).filter(f => /\.(html|js)$/.test(f)).forEach(f => {
    const src = read(f);
    ok(!/from\(\s*['"]v_pro_/.test(src) && !/from\(\s*['"]v_fight_market_movement_lookback/.test(src),
       f + ' reads a T-061 view before it exists');
    ok(!/if\s*\(\s*!?\s*(cflAuth|auth)\.isPro\(\)\s*\)\s*\{?[^}]{0,200}\.from\(/.test(src),
       f + ' gates a fetch on the client — the gate belongs in current_user_is_pro()');
  });
});

t('PRODUCT_BOUNDARY.md and entitlements.js still name the same Pro gate', () => {
  const doc = read('PRODUCT_BOUNDARY.md');
  ok(/current_user_is_pro\(\)/.test(doc), 'PRODUCT_BOUNDARY.md no longer names current_user_is_pro()');
  ok(/t061_pro_gates\.DRAFT\.sql/.test(doc), 'PRODUCT_BOUNDARY.md does not point at the drafted gates');
});

if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the boundary is drawn in SQL and gates nothing yet.\n`);
