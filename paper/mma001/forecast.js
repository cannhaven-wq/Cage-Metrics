"use strict";
/* MMA-001 prospective inference. No fitting, no scoring, no cutoff on history.
 *
 *   node forecast.js <artifact.json> <history.json> <targets.json>
 *
 * history.json  : {"fights": [25-column rows as model.js COLUMNS]} — every settled
 *                 bout on record, any date. Prospective forecasts must know the
 *                 fighters' 2025-26 results; this is the one sanctioned reader
 *                 of post-2024 outcomes and it never evaluates anything.
 * targets.json  : {"targets": [{fight_id, event_id, event_date, a_id, b_id, a_dob,
 *                 b_dob, a_reach, b_reach, q}]} where q is the vig-free market
 *                 p(A) frozen on the lock, or null to abstain.
 *
 * Prints JSON: {artifact_sha256, forecasts: [{fight_id, p_a, features, feature_hash, q}]}.
 * p_a is null (an abstention) when q is missing or a feature is not finite.
 * Corner symmetry is checked on every forecast; a violation aborts.
 */
const fs = require("node:fs");
const crypto = require("node:crypto");
const m = require("./model.js");

const [artifactPath, historyPath, targetsPath] = process.argv.slice(2);
if (!artifactPath || !historyPath || !targetsPath) throw Error("Usage: node forecast.js artifact.json history.json targets.json");
const artifactBytes = fs.readFileSync(artifactPath);
const artifact = JSON.parse(artifactBytes.toString("utf8"));
const history = JSON.parse(fs.readFileSync(historyPath, "utf8")).fights;
const targets = JSON.parse(fs.readFileSync(targetsPath, "utf8")).targets;
if (!Array.isArray(history) || !Array.isArray(targets)) throw Error("Expected fights[] and targets[]");
if (!Array.isArray(artifact.coefficients) || artifact.coefficients.length !== m.FEATURES.length) throw Error("Artifact does not match the model's feature list");

// Replay history exactly as model.js::buildExamples does (date batches, Elo
// deferred to the end of the date), without validateDev's sealed-date refusal
// and without emitting any scored example.
const finite = x => typeof x === "number" && Number.isFinite(x);
const dateMs = s => { const ms = Date.parse(String(s).slice(0, 10) + "T00:00:00Z"); if (!Number.isFinite(ms)) throw Error("Invalid date " + s); return ms; };
const ordered = [...history].sort((a, b) => String(a[2]).localeCompare(String(b[2])) || a[0] - b[0]);
const states = new Map();
const get = id => { if (!states.has(id)) states.set(id, m.emptyState()); return states.get(id); };
const seen = new Set();
for (let start = 0; start < ordered.length;) {
  let end = start + 1; while (end < ordered.length && ordered[end][2] === ordered[start][2]) end++;
  const ms = dateMs(ordered[start][2]), eloChanges = new Map();
  for (let i = start; i < end; i++) {
    const r = ordered[i];
    if (r.length !== m.COLUMNS.length) throw Error("Wrong history columns on fight " + r[0]);
    if (seen.has(r[0])) throw Error("Duplicate history fight " + r[0]);
    seen.add(r[0]);
    if (![0, 0.5, 1].includes(r[5])) throw Error("History fight " + r[0] + " has no decided outcome");
    const a = get(r[3]), b = get(r[4]);
    // decay happens inside the per-date pass in buildExamples via decay(); replicate
    decayState(a, ms); decayState(b, ms);
    const expected = 1 / (1 + Math.pow(10, (b.elo - a.elo) / 400)), delta = 32 * (r[5] - expected);
    eloChanges.set(r[3], (eloChanges.get(r[3]) || 0) + delta);
    eloChanges.set(r[4], (eloChanges.get(r[4]) || 0) - delta);
  }
  for (let i = start; i < end; i++) { const r = ordered[i]; updateStats(get(r[3]), r, 0, ms); updateStats(get(r[4]), r, 1, ms); }
  for (const [id, change] of eloChanges) get(id).elo += change;
  start = end;
}

function decayState(state, ms) {
  // identical to model.js decay(), which is not exported
  const HALF_LIFE_DAYS = 730;
  const FIELDS = ["sigMin","sigNet","tdMin","tdNet","tdOwn","tdConceded","tdOppAttempts","controlMin","controlNet","kdMin","kdNet"];
  if (state.decayAt !== null) {
    if (ms < state.decayAt) throw Error("History out of order");
    const factor = Math.pow(0.5, (ms - state.decayAt) / 86400000 / HALF_LIFE_DAYS);
    for (const k of FIELDS) state[k] *= factor;
  }
  state.decayAt = ms;
}
function updateStats(state, r, side, ms) {
  // identical to model.js updateStats(), which is not exported
  state.n++;
  const win = side === 0 ? r[5] : 1 - r[5];
  if (win === 1) state.w++; else if (win === 0) state.l++;
  state.last = ms;
  const seconds = r[6];
  if (!finite(seconds) || seconds <= 0 || seconds > 3600) return;
  const minutes = seconds / 60, own = i => r[i + side], other = i => r[i + 1 - side];
  if (finite(own(7)) && finite(other(7))) { state.sigMin += minutes; state.sigNet += own(7) - other(7); }
  if ([own(9), other(9), own(11), other(11)].every(finite) && own(9) <= own(11) && other(9) <= other(11)) {
    state.tdMin += minutes; state.tdNet += own(9) - other(9); state.tdOwn += own(9); state.tdConceded += other(9); state.tdOppAttempts += other(11);
  }
  if ([own(13), other(13)].every(finite) && own(13) <= seconds && other(13) <= seconds) { state.controlMin += minutes; state.controlNet += own(13) - other(13); }
  if ([own(15), other(15)].every(finite)) { state.kdMin += minutes; state.kdNet += own(15) - other(15); }
}

const forecasts = [];
for (const t of targets) {
  const ms = dateMs(t.event_date);
  const a = structuredClone(get(t.a_id)), b = structuredClone(get(t.b_id));
  if (a.decayAt !== null && ms < a.decayAt) throw Error("Target " + t.fight_id + " is dated before fighter A's last recorded bout");
  if (b.decayAt !== null && ms < b.decayAt) throw Error("Target " + t.fight_id + " is dated before fighter B's last recorded bout");
  decayState(a, ms); decayState(b, ms);
  const x = m.matchupFeatures(m.profile(a, ms, t.a_dob || null, t.a_reach ?? null), m.profile(b, ms, t.b_dob || null, t.b_reach ?? null));
  const xs = m.matchupFeatures(m.profile(b, ms, t.b_dob || null, t.b_reach ?? null), m.profile(a, ms, t.a_dob || null, t.a_reach ?? null));
  const featureHash = crypto.createHash("sha256").update(JSON.stringify(x)).digest("hex");
  let p = null, reason = null;
  if (!finite(t.q) || t.q <= 0 || t.q >= 1) reason = "no market probability on the lock";
  else if (!x.every(finite)) reason = "non-finite feature";
  else {
    p = m.predict(artifact, x, t.q);
    const ps = m.predict(artifact, xs, 1 - t.q);
    if (Math.abs(p + ps - 1) > 1e-6) throw Error("Corner symmetry violated on fight " + t.fight_id);
  }
  forecasts.push({ fight_id: t.fight_id, p_a: p, abstain_reason: reason, q: finite(t.q) ? t.q : null,
    features: Object.fromEntries(m.FEATURES.map((k, j) => [k, x[j]])), feature_hash: featureHash,
    history_fights_a: a.n, history_fights_b: b.n });
}
process.stdout.write(JSON.stringify({ model_version: artifact.version, artifact_sha256: crypto.createHash("sha256").update(artifactBytes).digest("hex"),
  history_rows: history.length, forecasts }) + "\n");
