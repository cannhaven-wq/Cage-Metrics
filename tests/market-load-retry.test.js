// T-092: a failed read of v_fight_market_movement is retried once, and if it
// still fails the page is TOLD, so it can say "prices didn't load" instead of
// "no sportsbook price captured" — a dash must carry its true reason.
//
//   node tests/market-load-retry.test.js
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'market.js'), 'utf8');

function load(responses) {
  const calls = [];
  const sb = {
    from(view) {
      const q = {
        select() { return q; }, eq() { return q; }, limit() { return q; },
        then(res, rej) {
          calls.push(view);
          const r = responses.shift();
          return Promise.resolve(r instanceof Error ? Promise.reject(r) : r).then(res, rej);
        },
      };
      return q;
    },
  };
  const window = { cflSupabase: sb, cfl: { escapeHtml: s => s } };
  const ctx = { window, console: { warn() {}, log() {} }, setTimeout, Promise, Date, Math };
  vm.runInNewContext(SRC, ctx);
  window.cflMarket.MOVEMENT_RETRY_MS = 1;
  return { M: window.cflMarket, calls };
}

const ROW = { fight_id: 7, event_id: 1 };
const TIMEOUT = { data: null, error: { message: 'canceling statement due to statement timeout' } };

(async () => {
  {
    const { M, calls } = load([TIMEOUT, { data: [ROW], error: null }]);
    const out = await M.loadCardMovement(1);
    assert.deepStrictEqual(Object.keys(out), ['7'], 'a retry that succeeds returns the rows');
    assert.strictEqual(out.loadFailed, false);
    assert.strictEqual(calls.length, 2, 'exactly one retry');
  }
  {
    const { M, calls } = load([TIMEOUT, TIMEOUT]);
    const out = await M.loadCardMovement(1);
    assert.strictEqual(out.loadFailed, true, 'two failures are reported, not hidden');
    assert.deepStrictEqual(Object.keys(out), [], 'loadFailed is not enumerable');
    assert.strictEqual(calls.length, 2, 'no third attempt');
  }
  {
    const { M } = load([{ data: [], error: null }]);
    const out = await M.loadCardMovement(1);
    assert.strictEqual(out.loadFailed, false, 'an empty card is "no prices yet", not a failure');
  }
  {
    let failed = false;
    const { M } = load([new Error('network'), TIMEOUT]);
    const row = await M.loadFightMovement(7, { onFailed: () => { failed = true; } });
    assert.strictEqual(row, null);
    assert.strictEqual(failed, true, 'Fight Lab is told the read failed');
  }
  {
    let failed = false;
    const { M } = load([{ data: [], error: null }]);
    const row = await M.loadFightMovement(7, { onFailed: () => { failed = true; } });
    assert.strictEqual(row, null);
    assert.strictEqual(failed, false, 'a fight with no price is not a failure');
  }
  {
    const { M } = load([{ data: [ROW], error: null }]);
    assert.deepStrictEqual(await M.loadFightMovement(7), ROW, 'no opts still works');
  }
  console.log('market-load-retry: all checks passed');
})().catch(e => { console.error(e); process.exit(1); });
