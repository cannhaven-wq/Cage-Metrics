/* ==========================================================================
   proof-gates.js — the rules the Proof Center is not allowed to break.

   Single source of truth for three things, and nothing else:

     1. RECORD SEPARATION. A live row (posted before the bell) and a replay row
        (the engine re-run through history) may never be counted together. Every
        function here either takes one kind or refuses.
     2. PUBLICATION GATES. A number is publishable only when a named rule says
        so. Until then the surface shows the gate, not an estimate, not a
        placeholder, not a greyed-out guess.
     3. FLAT-STAKE MONEY MATH. One definition of "what $100 a bet came to", used
        everywhere, so two panels can't disagree.

   It computes nothing about the model and reinterprets no research artifact.
   It reads what is already on record and decides whether it may be shown.

   FAILS CLOSED. An unknown gate, a missing count, a NaN, a row set it can't
   verify as one kind — all resolve to "not publishable". The default answer to
   "can we show this?" is no.

   Loaded with <script src="proof-gates.js"> in the browser (exports
   window.cflProof) and require('./proof-gates') in Node, same as edges.js.
   ========================================================================== */

(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.cflProof = api;
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ------------------------------------------------------------------ record
  // The two kinds of row, and the DB `source` value each maps to. These are the
  // only two. A row whose source is neither is UNKNOWN and is never counted.
  const RECORD = {
    LIVE:    'live',      // source='live'     — written before the fight, timestamped
    REPLAY:  'replay',    // source='backtest' — the engine re-run through history
    UNKNOWN: 'unknown',
  };

  const SOURCE_TO_RECORD = { live: RECORD.LIVE, backtest: RECORD.REPLAY };

  function recordKind(row) {
    if (!row || typeof row.source !== 'string') return RECORD.UNKNOWN;
    return SOURCE_TO_RECORD[row.source] || RECORD.UNKNOWN;
  }

  // Split a mixed result set into its two records. Anything unrecognised lands
  // in `unknown` and is deliberately not folded into either — a row we can't
  // classify is not quietly treated as live.
  function splitByRecord(rows) {
    const out = { live: [], replay: [], unknown: [] };
    (rows || []).forEach(function (r) {
      const k = recordKind(r);
      if (k === RECORD.LIVE) out.live.push(r);
      else if (k === RECORD.REPLAY) out.replay.push(r);
      else out.unknown.push(r);
    });
    return out;
  }

  // The invariant, as an assertion. Call it before any aggregate: if a set that
  // is about to be summarised as one record contains another, throw rather than
  // publish a blended number. Loud beats subtly wrong.
  function assertOneRecord(rows, expected) {
    const kinds = {};
    (rows || []).forEach(function (r) { kinds[recordKind(r)] = true; });
    delete kinds[RECORD.UNKNOWN];               // an empty set is fine
    const present = Object.keys(kinds);
    if (present.length > 1) {
      throw new Error('proof-gates: refusing to summarise a mixed record — found ' + present.sort().join(' + '));
    }
    if (expected && present.length === 1 && present[0] !== expected) {
      throw new Error('proof-gates: expected the ' + expected + ' record, got ' + present[0]);
    }
    return true;
  }

  // ------------------------------------------------------------------ status
  // What a number on screen is allowed to say about itself. Every figure the
  // Proof Center renders carries exactly one of these.
  const STATUS = {
    LIVE:        'live',         // measured only on rows posted before the fight
    REPLAY:      'replay',       // simulated — the engine re-run through history
    PROVISIONAL: 'provisional',  // real live rows, but under the sample floor: read it as noise
    COLLECTING:  'collecting',   // gate not passed — there is no number to show yet
    APPROVED:    'approved',     // a named publication rule has passed
  };

  // Plain-English label + one-line meaning. No stats vocabulary — a 24-year-old
  // who has never read a stats textbook has to get these in one pass.
  const STATUS_COPY = {
    live:        { label: 'Live',            blurb: 'Measured only on picks posted before the fight, with a timestamp on record.' },
    replay:      { label: 'Simulated',       blurb: 'The engine re-run through old fights. Useful for a sanity check, never proof.' },
    provisional: { label: 'Too early',       blurb: 'These are real live picks, but there are too few to mean anything yet. Read it as noise.' },
    collecting:  { label: 'Still collecting', blurb: 'We are not showing a number until enough of them are on record. No estimate, no placeholder.' },
    approved:    { label: 'Cleared',         blurb: 'Enough verified picks are on record for this number to be worth reading.' },
  };

  function statusCopy(status) {
    return STATUS_COPY[status] || STATUS_COPY.collecting;   // fail closed
  }

  // ------------------------------------------------------------------- gates
  // A gate is a named, written-down rule that says when a number may be shown.
  // `source` is the audit trail: where the rule came from. A gate is never
  // invented at render time, and a gate is never relaxed because the number
  // underneath it happens to look good.
  //
  // NOTE ON CHANGING THESE. Raising or lowering a floor after seeing the data
  // it gates is the exact move this file exists to prevent. Change a gate in a
  // commit of its own, before the number is visible, and say why.
  const GATES = {
    // The market test. Already the site's published stance, shipped on
    // track-record.html: "these numbers go up here once 100+ locked picks have
    // both a posted price and a closing price on record."
    clv: {
      id: 'clv',
      title: 'Did we get a better price than the market closed at?',
      minObservations: 100,
      record: RECORD.LIVE,           // replay rows can never satisfy this gate
      unit: 'picks with both a posted price and a closing price',
      source: 'track-record.html, shipped stance: "100+ locked picks have both a posted price and a closing price on record"',
      // What the surface says while the gate is shut. It does not hint at the
      // direction of the unpublished number.
      pending: 'Prospective data collecting. We are not putting a number here until enough picks have both prices on record.',
    },

    // The live straight-up record. Shown below the floor — it is the record
    // itself, not a claim about the future — but labelled as too early to read.
    liveRecord: {
      id: 'liveRecord',
      title: 'How often the live picks won',
      minObservations: 100,
      record: RECORD.LIVE,
      unit: 'settled live picks',
      source: 'track-record.html honesty box: "Anything under ~100 picks in a bucket is noise."',
      showBelowFloor: true,
      pending: 'Shown as it stands, but there are too few settled picks to read anything into it.',
    },

    // Flat-stake money. Same floor, same treatment: the running total is a fact
    // about the record, so it is shown; it is never phrased as a rate to expect.
    liveMoney: {
      id: 'liveMoney',
      title: 'What $100 a bet came to',
      minObservations: 100,
      record: RECORD.LIVE,
      unit: 'settled live value picks',
      source: 'track-record.html honesty box: "Anything under ~100 picks in a bucket is noise."',
      showBelowFloor: true,
      pending: 'A running total of what is on record — not a rate to expect going forward.',
    },
  };

  // Decide what a surface may show. `have` is the count of verified observations
  // of the gate's own unit; anything non-finite is treated as zero.
  //
  // Returns { status, publishable, showValue, have, need, remaining, pct, ... }.
  // `publishable` means the gate has passed. `showValue` means the page may
  // render the figure at all — true below the floor only for gates that
  // explicitly opt in, and then always alongside the 'provisional' status.
  function evaluateGate(gateId, have) {
    const gate = GATES[gateId];
    if (!gate) {
      // Unknown gate: fail closed, and say so rather than rendering nothing.
      return {
        id: String(gateId), title: '', status: STATUS.COLLECTING, publishable: false,
        showValue: false, have: 0, need: Infinity, remaining: Infinity, pct: 0,
        unit: '', source: 'no gate defined', message: 'No publication rule is defined for this number, so it is not shown.',
      };
    }
    const n = (typeof have === 'number' && isFinite(have) && have > 0) ? Math.floor(have) : 0;
    const need = gate.minObservations;
    const passed = n >= need;
    const status = passed ? STATUS.APPROVED : (gate.showBelowFloor ? STATUS.PROVISIONAL : STATUS.COLLECTING);
    return {
      id: gate.id,
      title: gate.title,
      status: status,
      publishable: passed,
      showValue: passed || gate.showBelowFloor === true,
      have: n,
      need: need,
      remaining: Math.max(0, need - n),
      pct: need > 0 ? Math.min(1, n / need) : 0,
      unit: gate.unit,
      record: gate.record,
      source: gate.source,
      message: passed
        ? n.toLocaleString() + ' ' + gate.unit + ' on record — enough to be worth reading.'
        : gate.pending,
    };
  }

  // ------------------------------------------------------------------- money
  // Profit on a winning $100 bet at American odds. -150 → $66.67, +180 → $180.
  function winProfit(americanOdds, stake) {
    const o = Number(americanOdds), s = (stake == null ? 100 : Number(stake));
    if (!isFinite(o) || o === 0 || !isFinite(s)) return null;
    return o > 0 ? s * (o / 100) : s * (100 / Math.abs(o));
  }

  // Flat-stake ledger over one record. `priceOf(row)` returns the American price
  // the bet is graded at; `wonOf(row)` returns true / false / null (unsettled).
  // A row with no price or no result is counted as unpriced/pending, never as a
  // loss and never silently dropped from the denominator without being reported.
  function flatStakeLedger(rows, opts) {
    const o = opts || {};
    const stake = o.stake == null ? 100 : Number(o.stake);
    const priceOf = o.priceOf || function (r) { return r.odds_at_publish; };
    const wonOf = o.wonOf || function (r) { return r.won; };
    if (o.expectRecord) assertOneRecord(rows, o.expectRecord);

    let wins = 0, losses = 0, pending = 0, unpriced = 0, pnl = 0;
    (rows || []).forEach(function (r) {
      const won = wonOf(r);
      if (won == null) { pending++; return; }
      const profit = winProfit(priceOf(r), stake);
      if (profit == null) { unpriced++; return; }
      if (won === true) { wins++; pnl += profit; }
      else { losses++; pnl -= stake; }
    });
    const settled = wins + losses;
    return {
      stake: stake,
      wins: wins,
      losses: losses,
      settled: settled,
      pending: pending,
      unpriced: unpriced,
      pnl: settled ? pnl : 0,
      perBet: settled ? pnl / settled : null,   // dollars per $100 risked — never annualised, never projected
      hitRate: settled ? wins / settled : null,
    };
  }

  // Straight-up record over one kind of row (no price involved).
  function straightRecord(rows, opts) {
    const o = opts || {};
    const hitOf = o.hitOf || function (r) { return r.hit; };
    if (o.expectRecord) assertOneRecord(rows, o.expectRecord);
    let hits = 0, misses = 0, pending = 0;
    (rows || []).forEach(function (r) {
      const h = hitOf(r);
      if (h == null) pending++;
      else if (h === true) hits++;
      else misses++;
    });
    const settled = hits + misses;
    return { hits: hits, misses: misses, settled: settled, pending: pending,
             hitRate: settled ? hits / settled : null };
  }

  // ------------------------------------------------------------- clv counting
  // The gate's unit: a live row carrying BOTH a posted price and a closing
  // price. Counting only — the CLV value itself is never computed here, and
  // this file has no opinion on how CLV is scored. That definition lives in
  // cfl_engine/settle_clv.py and is not ours to restate.
  function clvPairCount(rows) {
    const live = splitByRecord(rows).live;
    return live.filter(function (r) {
      return r.odds_at_publish != null && r.closing_odds != null;
    }).length;
  }

  // ---------------------------------------------------------- timestamp audit
  // The claim the whole page rests on: every live pick was on record before its
  // card. This checks it against the rows themselves rather than asserting it,
  // and reports failures so the page can print them.
  //
  // A row is IN ORDER when published_at falls on or before the card's date. It
  // is counted as UNDATED when either timestamp is missing — undated is not
  // treated as in order.
  //
  // SAME-DAY rows are counted separately and are a subset of inOrder. The card
  // date alone does not prove a pick landed before the first bell, so the page
  // states the day-of count rather than folding it into a stronger claim.
  function timestampAudit(rows) {
    const live = splitByRecord(rows).live;
    let inOrder = 0, undated = 0, sameDay = 0;
    const late = [];
    live.forEach(function (r) {
      if (!r.published_at || !r.event_date) { undated++; return; }
      const posted = String(r.published_at).slice(0, 10);
      const card = String(r.event_date).slice(0, 10);
      if (posted < card) inOrder++;
      else if (posted === card) { inOrder++; sameDay++; }
      else late.push(r);
    });
    return {
      total: live.length,
      inOrder: inOrder,
      sameDay: sameDay,
      dayBefore: inOrder - sameDay,
      undated: undated,
      late: late.length,
      lateRows: late,
      clean: live.length > 0 && late.length === 0 && undated === 0,
    };
  }

  // ------------------------------------------------------- immutable crosscheck
  // The stronger audit line, and the honest one.
  //
  // `model_picks` and `model_edges` are NOT trigger-protected — the publisher
  // only inserts into them by convention, and `model_edges` is deliberately
  // updated after a card to fill in the closing price. `pre_fight_snapshots` IS
  // append-only, enforced by database triggers that reject UPDATE and DELETE for
  // every role including service_role. So the claim worth making is not "the
  // picks table cannot be edited" — it is that every pick covered by a snapshot
  // still matches the frozen copy, which anyone can recheck.
  //
  // Matches on fighter and probability. Probability is compared at 1e-6 because
  // both sides are numerics rendered through JSON, not exact binary equality.
  function crossCheckSnapshots(livePicks, snapshots) {
    const byFight = {};
    (snapshots || []).forEach(function (s) {
      if (s && s.fight_id != null) byFight[s.fight_id] = s;
    });
    let covered = 0, matched = 0;
    const mismatches = [];
    splitByRecord(livePicks).live.forEach(function (p) {
      const s = byFight[p.fight_id];
      if (!s) return;                       // no snapshot for this fight — not a mismatch
      covered++;
      const samePick = String(s.engine_pick_fighter_id) === String(p.pick_fighter_id);
      const sameProb = s.engine_p_cal != null && p.p_cal != null &&
        Math.abs(Number(s.engine_p_cal) - Number(p.p_cal)) < 1e-6;
      if (samePick && sameProb) matched++;
      else mismatches.push(p);
    });
    return {
      snapshots: (snapshots || []).length,
      covered: covered,
      matched: matched,
      mismatched: mismatches.length,
      mismatchRows: mismatches,
      clean: covered > 0 && mismatches.length === 0,
    };
  }

  return {
    RECORD: RECORD, STATUS: STATUS, GATES: GATES,
    recordKind: recordKind,
    splitByRecord: splitByRecord,
    assertOneRecord: assertOneRecord,
    statusCopy: statusCopy,
    evaluateGate: evaluateGate,
    winProfit: winProfit,
    flatStakeLedger: flatStakeLedger,
    straightRecord: straightRecord,
    clvPairCount: clvPairCount,
    timestampAudit: timestampAudit,
    crossCheckSnapshots: crossCheckSnapshots,
  };
}));
