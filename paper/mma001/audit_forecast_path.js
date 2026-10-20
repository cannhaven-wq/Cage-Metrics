"use strict";
/* Consistency audit of the prospective forecast path against the Doc's own feature path.
 *
 *   node audit_forecast_path.js <history.json> [n=200] [seed=20261012]
 *
 * For n randomly drawn decided bouts dated 2015-01-01 or later, the features
 * model.js::buildExamples computes (history strictly before the bout's date,
 * same-date results excluded) are compared with what forecast.js computes
 * when it is given ONLY the bouts dated before that one and asked to forecast
 * the bout as a target. Any difference above 1e-12 is a failure.
 *
 * This is a same-author check that the two code paths agree. It is not the
 * independent point-in-time audit PRED-001 §3 requires, which an auditor who
 * wrote neither path performs from the source tables.
 */
const fs = require("node:fs");
const m = require("./model.js");
const F = require("./forecast.js");

const [historyPath, nArg, seedArg] = process.argv.slice(2);
if (!historyPath) throw Error("Usage: node audit_forecast_path.js history.json [n] [seed]");
const history = JSON.parse(fs.readFileSync(historyPath, "utf8")).fights;
const n = Number(nArg || 200);
let seed = Number(seedArg || 20261012);
const random = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed >>> 0) / 4294967296; };

// The Doc's path, restricted to DEV rows (buildExamples refuses sealed dates)
const dev = history.filter(r => r[2] < m.CUTOFF);
const prices = dev.filter(r => r[5] === 0 || r[5] === 1).map(r => [r[0], -110, -110, 1, 1]);
const docExamples = new Map(m.buildExamples(dev, prices).map(e => [e.id, e]));
const candidates = dev.filter(r => (r[5] === 0 || r[5] === 1) && r[2] >= "2015-01-01");
const picked = [];
while (picked.length < Math.min(n, candidates.length)) {
  const r = candidates[Math.floor(random() * candidates.length)];
  if (!picked.includes(r)) picked.push(r);
}
let maxDiff = 0, checked = 0;
for (const r of picked) {
  const before = history.filter(h => h[2] < r[2]);           // strictly before the bout's date
  const states = F.replayHistory(before);
  const { x } = F.targetFeatures(states, { fight_id: r[0], event_date: r[2], a_id: r[3], b_id: r[4], a_dob: r[19], b_dob: r[20], a_reach: r[21], b_reach: r[22] });
  const ref = docExamples.get(r[0]).x;
  for (let j = 0; j < x.length; j++) maxDiff = Math.max(maxDiff, Math.abs(x[j] - ref[j]));
  checked++;
}
const ok = maxDiff <= 1e-12;
process.stdout.write(JSON.stringify({ checked, max_abs_feature_difference: maxDiff, pass: ok, seed: Number(seedArg || 20261012),
  note: "same-author consistency of forecast.js against model.js::buildExamples; not the independent PRED-001 point-in-time audit" }) + "\n");
process.exit(ok ? 0 : 1);
