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

  // --------------------------------------------------------------- headline
  // The engine's headline accuracy, for a surface that shows ONE number.
  //
  // This exists because index.html was computing that number itself, from
  // cfl.fetchEnginePicks() with no `source` filter at all — so the homepage
  // headline, the graded-fight count, the Lock-tier rate and the "Why trust
  // it?" tiles were averages over the live feed and the history replay pooled
  // together. That is precisely the operation assertOneRecord exists to refuse,
  // running on the most prominent statistic on the site.
  //
  // The fix is not a filter bolted onto the page. A page that computes its own
  // headline can always drift back; a page that asks this module for it cannot,
  // because the assertion sits on this side of the call. So the rule and the
  // arithmetic live here together, and the page renders what it is handed.
  //
  // `expected` is required, not optional. "Which record is this?" is the whole
  // question, and a caller that has not answered it has no business publishing
  // a number.
  function headlineFromPicks(rows, expected, opts) {
    if (!expected) {
      throw new Error('proof-gates: headlineFromPicks needs the record it is summarising');
    }
    const o = opts || {};
    const minPicks = o.minPicks == null ? 100 : o.minPicks;
    const minLocks = o.minLocks == null ? 50 : o.minLocks;

    const graded = (rows || []).filter(function (r) {
      return r && (r.hit === true || r.hit === false);
    });

    // Throws rather than returning a blended figure. A mixed set arriving here
    // is a bug upstream, and the one thing that must not happen is it reaching
    // a reader instead.
    assertOneRecord(graded, expected);

    const hits = graded.filter(function (r) { return r.hit === true; }).length;
    const locks = graded.filter(function (r) { return r.tier === 'Lock'; });
    const lockHits = locks.filter(function (r) { return r.hit === true; }).length;
    const pct = function (w, n) { return n ? +((100 * w) / n).toFixed(1) : null; };

    return {
      record: expected,
      n: graded.length,
      hits: hits,
      accuracy: pct(hits, graded.length),
      lockN: locks.length,
      lockHits: lockHits,
      lockAccuracy: pct(lockHits, locks.length),
      // Small samples do not get to be a headline. Same floors the page used.
      publishable: graded.length >= minPicks,
      locksPublishable: locks.length >= minLocks,
    };
  }

  // ------------------------------------------------------------------ status
  // What a number on screen is allowed to say about itself. Every figure the
  // Proof Center renders carries exactly one of these.
  const STATUS = {
    LIVE:        'live',         // measured only on the prospective feed; per-row timing graded separately
    REPLAY:      'replay',       // simulated — the engine re-run through history
    PROVISIONAL: 'provisional',  // real live rows, but under the sample floor: read it as noise
    COLLECTING:  'collecting',   // gate not passed — there is no number to show yet
    APPROVED:    'approved',     // a named publication rule has passed
  };

  // Plain-English label + one-line meaning. No stats vocabulary — a 24-year-old
  // who has never read a stats textbook has to get these in one pass.
  const STATUS_COPY = {
    live:        { label: 'Live',            blurb: 'Measured only on the prospective feed — the calls we published as the card approached. How well each one\u2019s timing can be proved is graded separately, row by row.' },
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
    // The market-price test. NOT OURS TO EVALUATE.
    //
    // The publication rule for CLV belongs to the CLV-001 research protocol, and
    // that protocol is not in this repository yet. Its conditions — how many
    // scored observations, across how many distinct events, under what
    // uncertainty condition, and whatever else the freeze names — are a frozen
    // methodology. Proof Center must never reproduce, approximate or simplify
    // them, and must never substitute a proxy it happens to be able to count.
    //
    // In particular: the legacy `closing_odds` / `odds_at_publish` pairs on
    // model_edges are NOT CLV-001 observations and counting them is NOT progress
    // toward this gate. An earlier cut of this file did exactly that and showed
    // "46 of 100". That was wrong and the count has been removed outright rather
    // than left available to be re-wired by accident.
    //
    // Until Proof Center can read authoritative CLV-001 publication state, this
    // gate is DEFERRED: it has no local threshold, no progress, and no path to
    // opening from anything measured here.
    clv: {
      id: 'clv',
      title: 'Did we get a better price than the market ended up at?',
      deferred: true,
      authority: 'CLV-001',
      record: RECORD.LIVE,
      source: 'The CLV publication rule is owned by the CLV-001 research protocol, which is not integrated here. Proof Center holds no CLV threshold of its own and computes no CLV figure.',
      // Narrow on purpose. UFC outcomes and the legacy price fields predate
      // CLV-001, so "frozen before any result could be seen" claims more than
      // is true. What the freeze actually establishes is about its own results.
      freezeNote: 'frozen before any CLV-001 result was computed or reviewed',
      pending: 'Prospective market-price validation is collecting. No CLV figure is publication-approved yet.',
    },

    // The live straight-up record. Ours, and a plain count of what happened —
    // shown below its floor but labelled as too early to read.
    liveRecord: {
      id: 'liveRecord',
      title: 'How often the live calls were right',
      minObservations: 100,
      record: RECORD.LIVE,
      unit: 'settled live calls',
      source: 'track-record.html honesty box: "Anything under ~100 picks in a bucket is noise."',
      showBelowFloor: true,
      pending: 'Shown as it stands, but there are too few settled calls to read anything into it.',
    },

    // Flat-stake money. Same floor, same treatment: the running total is a fact
    // about the record, so it is shown; it is never phrased as a rate to expect.
    liveMoney: {
      id: 'liveMoney',
      title: 'What $100 a bet came to',
      minObservations: 100,
      record: RECORD.LIVE,
      unit: 'settled live bets',
      source: 'track-record.html honesty box: "Anything under ~100 picks in a bucket is noise."',
      showBelowFloor: true,
      pending: 'A running total of what is on record — not a rate to expect going forward.',
    },
  };

  // Decide what a surface may show. `have` is the count of verified observations
  // of the gate's own unit; anything non-finite is treated as zero.
  //
  // `authority` is the ONLY thing that can open a deferred gate: an object from
  // the protocol that owns it, whose `publication_approved` is exactly true and
  // whose `authority` names the owning protocol. `have` is ignored entirely for
  // a deferred gate — no local count, however large, can open it.
  //
  // Returns { status, publishable, showValue, have, need, ... }. `publishable`
  // means the gate has passed. `showValue` means the page may render the figure
  // at all — true below the floor only for gates that explicitly opt in, and
  // then always alongside the 'provisional' status.
  function evaluateGate(gateId, have, authority) {
    const gate = GATES[gateId];
    if (!gate) {
      // Unknown gate: fail closed, and say so rather than rendering nothing.
      return {
        id: String(gateId), title: '', status: STATUS.COLLECTING, publishable: false,
        showValue: false, deferred: false, have: 0, need: null, remaining: null, pct: null,
        unit: '', source: 'no gate defined', message: 'No publication rule is defined for this number, so it is not shown.',
      };
    }

    if (gate.deferred) {
      const approved = !!(authority &&
        authority.publication_approved === true &&
        authority.authority === gate.authority);
      return {
        id: gate.id,
        title: gate.title,
        status: approved ? STATUS.APPROVED : STATUS.COLLECTING,
        publishable: approved,
        // Even when the owning protocol says approved, this file renders no
        // figure — surfacing one is a separate, reviewed integration.
        showValue: false,
        deferred: true,
        authority: gate.authority,
        have: null, need: null, remaining: null, pct: null,
        unit: '',
        record: gate.record,
        source: gate.source,
        message: approved
          ? gate.authority + ' reports this measurement as publication-approved. Displaying it is a separate change.'
          : gate.pending,
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
      deferred: false,
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

  // --------------------------------------------------------- timing evidence
  // What we can actually prove about WHEN a call was made, graded honestly.
  //
  // The mistake this replaces: treating "published_at falls on or before the
  // card's date" as proof the call preceded the fight. It is not. A card runs
  // for hours, and a row written at 9pm on fight night carries the same date as
  // one written at dawn. Same-day is a timestamp, not a proof.
  //
  // A sealed snapshot is not automatically timing evidence either. Immutability
  // and timing are separate claims: the snapshot table proves the row has not
  // been revised, and its own snapshot_at says when it was taken. A snapshot
  // taken on the card's own day inherits the same-day problem.
  //
  // Four levels, strongest first. Every live row lands in exactly one:
  //
  //   sealed      a sealed pre-fight copy exists, still matches this row, AND
  //               was taken on an earlier calendar day than the card
  //   dated       posted on an earlier calendar day than the card
  //   sameDay     a timestamp exists but falls on the card's own day — the date
  //               alone cannot place it before the first bell
  //   unverified  posted after the card's date, or missing a timestamp entirely
  //
  // If an authoritative per-fight cutoff ever becomes available, sameDay rows
  // can be upgraded by comparing against it. Nothing here invents one.
  function timingEvidence(rows, snapshots) {
    const byFight = {};
    (snapshots || []).forEach(function (s) {
      if (s && s.fight_id != null) byFight[s.fight_id] = s;
    });

    const out = {
      total: 0,
      // Timing grades — these partition the rows.
      sealed: 0, dated: 0, sameDay: 0, unverified: 0,
      // Snapshot facts — THREE SEPARATE THINGS, deliberately not one counter.
      // A snapshot can exist and no longer match; that is a mismatch to report,
      // not an absence to quietly fold into "uncovered". And a snapshot that
      // both exists and matches still says nothing about the clock.
      snapshotPresent: 0,      // a sealed copy exists for this fight
      snapshotMatched: 0,      // …and it still matches the current row
      snapshotMismatched: 0,   // …and it does not
      snapshotAbsent: 0,       // no sealed copy at all
      unverifiedRows: [],
    };

    splitByRecord(rows).live.forEach(function (r) {
      out.total++;
      const card = r.event_date ? String(r.event_date).slice(0, 10) : null;
      const posted = r.published_at ? String(r.published_at).slice(0, 10) : null;
      const snap = byFight[r.fight_id];

      let matched = false;
      if (snap) {
        out.snapshotPresent++;
        const samePick = String(snap.engine_pick_fighter_id) === String(r.pick_fighter_id);
        const sameProb = snap.engine_p_cal != null && r.p_cal != null &&
          Math.abs(Number(snap.engine_p_cal) - Number(r.p_cal)) < 1e-6;
        matched = samePick && sameProb;
        if (matched) out.snapshotMatched++; else out.snapshotMismatched++;
      } else {
        out.snapshotAbsent++;
      }

      // The sealed TIMING grade needs all three: a copy exists, it still
      // matches, and it was taken on an earlier calendar day than the card.
      if (matched && card) {
        const snapDay = snap.snapshot_at ? String(snap.snapshot_at).slice(0, 10) : null;
        if (snapDay && snapDay < card) { out.sealed++; return; }
      }

      if (!posted || !card) { out.unverified++; out.unverifiedRows.push(r); return; }
      if (posted < card) { out.dated++; return; }
      if (posted === card) { out.sameDay++; return; }
      out.unverified++; out.unverifiedRows.push(r);   // posted after the card
    });

    return out;
  }

  // The level a single row sits at, for per-row display in the archive. Same
  // rules as timingEvidence, one row at a time.
  function timingLevel(row, snapshot) {
    const e = timingEvidence([row], snapshot ? [snapshot] : []);
    if (e.sealed) return 'sealed';
    if (e.dated) return 'dated';
    if (e.sameDay) return 'sameDay';
    return 'unverified';
  }

  const TIMING_COPY = {
    sealed:     { label: 'Sealed before the card', blurb: 'A copy of this call was frozen into a record nobody can edit, on a day earlier than the card.' },
    dated:      { label: 'Dated before the card',  blurb: 'Posted on an earlier day than the card. Strong, but it rests on our own timestamp.' },
    sameDay:    { label: 'Same-day timestamp',     blurb: 'Timestamped on the card\u2019s own day. That cannot prove it landed before the fight started.' },
    unverified: { label: 'Timing unverified',      blurb: 'No usable timestamp, or one dated after the card. Not counted as evidence of anything.' },
  };

  function timingCopy(level) {
    return TIMING_COPY[level] || TIMING_COPY.unverified;   // fail closed
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
    headlineFromPicks: headlineFromPicks,
    statusCopy: statusCopy,
    evaluateGate: evaluateGate,
    winProfit: winProfit,
    flatStakeLedger: flatStakeLedger,
    straightRecord: straightRecord,
    timingEvidence: timingEvidence,
    timingLevel: timingLevel,
    timingCopy: timingCopy,
    TIMING_COPY: TIMING_COPY,
    crossCheckSnapshots: crossCheckSnapshots,
  };
}));
