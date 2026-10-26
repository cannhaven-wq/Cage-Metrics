"""DISC-001 — the factor discovery run.

Asks, for each factor fixed in PREREGISTRATION.md: once the closing odds are
known, does this factor make the forecast any better?

    python3 research/experiments/DISC-001/discover.py

Reads data/dev_fights.csv and data/dev_fighters.csv (fights before
2025-01-01 only; every row passes through pred_protocol.dev_only, which raises
on a sealed date). Writes results.json and REPORT.md next to this file.

Everything here implements the preregistration. A change to a factor, a
threshold or a rule is an amendment there first, or a new experiment.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import pathlib
import random
import sys
from collections import defaultdict

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "protocol"))
import pred_protocol as pp  # noqa: E402

DATA = HERE / "data"
TEST_YEARS = list(range(2012, 2025))
EXCLUDED_FIGHTS = {43, 46, 8780}          # rebooked in place (PRED-001 §2)
MAX_AMERICAN = 10000                      # 100-to-1 (PRED-001 §3)
BOOT_B, BOOT_SEED = 10_000, 20261012
AUDIT_N, AUDIT_SEED = 200, 20261021
ALPHA = 0.05
MIN_FIRED = 300
MIN_USEFUL = 0.003
RIDGE_COMBINED = 5.0

KO = "K"                                  # KO/TKO; doctor's stoppage ('T') excluded
FINISH = {"K", "S"}

PRIMARY = [
    ("F01", "KO/TKO losses"),
    ("F02", "KO/TKO loss in the last year"),
    ("F03", "Coming off a KO/TKO loss"),
    ("F04", "Repeat KO/TKO losses (2+)"),
    ("F05", "Knockout damage, fading with time"),
    ("F06", "Knockdowns absorbed"),
    ("F07", "Layoff length"),
    ("F08", "Long layoff (a year or more)"),
    ("F09", "Quick turnaround (90 days or less)"),
    ("F10", "Recent activity (fights in 2 years)"),
    ("F11", "UFC experience"),
    ("F12", "Accumulated cage time"),
    ("F13", "Age"),
    ("F14", "UFC win rate"),
    ("F15", "Opponent quality"),
    ("F16", "Momentum (win streak)"),
    ("F17", "Rematch: who won last time"),
    ("F18", "Common opponents (MMA math)"),
    ("F19", "First five-round fight"),
    ("F20", "First main event"),
]
CONTAMINATED = {"F13", "F14"}
PAIRWISE = {"F17", "F18"}
DEBUT_DEFINED = {"F11", "F19", "F20"}

INTERACTIONS = [
    ("I1", "KO/TKO loss x quick return (180 days)"),
    ("I2", "Rematch x first meeting ended in a finish"),
    ("I3", "First main event x opponent's main-event experience"),
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _int(v):
    return int(v) if v != "" else None


def load():
    with open(DATA / "dev_fights.csv", newline="") as fh:
        cols = ["id", "event_id", "event_date", "a", "b", "res", "method", "end_round",
                "end_secs", "sched_rounds", "title", "main", "a_kd", "b_kd", "bfo_a", "bfo_b"]
        rows = [dict(zip(cols, r)) for r in csv.reader(fh)]
    rows = pp.dev_only(rows)
    fights = []
    for r in rows:
        fights.append({
            "id": int(r["id"]), "event_id": int(r["event_id"]),
            "date": dt.date.fromisoformat(r["event_date"]),
            "a": int(r["a"]), "b": int(r["b"]), "res": r["res"], "method": r["method"],
            "end_round": _int(r["end_round"]), "end_secs": _int(r["end_secs"]),
            "sched5": _int(r["sched_rounds"]) == 5, "main": r["main"] == "1",
            "a_kd": _int(r["a_kd"]) or 0, "b_kd": _int(r["b_kd"]) or 0,
            "bfo_a": _int(r["bfo_a"]), "bfo_b": _int(r["bfo_b"]),
        })
    fights.sort(key=lambda f: (f["date"], f["event_id"], f["id"]))
    dob = {}
    with open(DATA / "dev_fighters.csv", newline="") as fh:
        for fid, d in csv.reader(fh):
            dob[int(fid)] = dt.date.fromisoformat(d) if d else None
    return fights, dob


def minutes(f):
    if f["end_round"] is None or f["end_secs"] is None:
        return 0.0
    return (f["end_round"] - 1) * 5 + f["end_secs"] / 60.0


def outcome_for(f, me):
    """W / L / D / N from one fighter's side."""
    if f["res"] in ("A", "B"):
        winner = f["a"] if f["res"] == "A" else f["b"]
        return "W" if winner == me else "L"
    return f["res"]


SCORE = {"W": 1.0, "L": 0.0, "D": 0.5, "N": 0.5}


def rate(w, l):
    return (w + 1) / (w + l + 2)


# ---------------------------------------------------------------------------
# Point-in-time features: incremental (the run) ...
# ---------------------------------------------------------------------------

class State:
    __slots__ = ("n", "last_date", "last_ko_loss", "ko_dates", "kd_abs", "mins", "w", "l",
                 "streak", "had5", "mains", "oppq", "dates", "vs")

    def __init__(self):
        self.n = 0
        self.last_date = None
        self.last_ko_loss = False
        self.ko_dates = []
        self.kd_abs = 0
        self.mins = 0.0
        self.w = self.l = 0
        self.streak = 0
        self.had5 = False
        self.mains = 0
        self.oppq = []
        self.dates = []
        self.vs = defaultdict(list)       # opponent -> [(date, event, id, outcome, method)]


def fighter_values(s: State, t: dt.date, dob, sched5: bool, main: bool, opp_mains: int):
    """Per-fighter g(.) for F01-F16, F19, F20 and the interaction inputs.
    None means undefined for this fighter."""
    v = {}
    has = s.n > 0
    days = (t - s.last_date).days if has else None
    v["F01"] = len(s.ko_dates) if has else None
    v["F02"] = float(any((t - d).days <= 365 for d in s.ko_dates)) if has else None
    v["F03"] = float(s.last_ko_loss) if has else None
    v["F04"] = float(len(s.ko_dates) >= 2) if has else None
    v["F05"] = sum(math.exp(-(t - d).days / 730.0) for d in s.ko_dates) if has else None
    v["F06"] = float(s.kd_abs) if has else None
    v["F07"] = math.log(days) if has else None
    v["F08"] = float(days >= 365) if has else None
    v["F09"] = float(days <= 90) if has else None
    v["F10"] = float(sum(1 for d in s.dates if (t - d).days <= 730)) if has else None
    v["F11"] = math.log1p(s.n)
    v["F12"] = math.log1p(s.mins) if has else None
    v["F13"] = ((t - dob).days / 365.25) if (has and dob) else None
    v["F14"] = rate(s.w, s.l) if has else None
    v["F15"] = (sum(s.oppq) / len(s.oppq)) if has else None
    v["F16"] = float(max(-5, min(5, s.streak))) if has else None
    v["F19"] = float(sched5 and not s.had5)
    v["F20"] = float(main and s.mains == 0)
    # interaction inputs
    v["q180"] = float(days <= 180) if has else None
    v["own_mains"] = math.log1p(s.mains)
    v["opp_mains"] = math.log1p(opp_mains)
    return v


def pairwise(sa: State, sb: State, a: int, b: int):
    """F17, F18 and the I2 finish flag. None = the pair has no such history."""
    f17 = fin = None
    meets = sa.vs.get(b)
    if meets:
        _, _, _, out, method = meets[-1]
        f17 = 1.0 if out == "W" else -1.0 if out == "L" else 0.0
        fin = float(method in FINISH)
    common = (set(sa.vs) - {b}) & (set(sb.vs) - {a})
    f18 = None
    if common:
        diffs = []
        for c in common:
            ma = [SCORE[m[3]] for m in sa.vs[c]]
            mb = [SCORE[m[3]] for m in sb.vs[c]]
            diffs.append(sum(ma) / len(ma) - sum(mb) / len(mb))
        f18 = sum(diffs) / len(diffs)
    return f17, f18, fin


def diff(va, vb):
    if va is None or vb is None:
        return 0.0, False
    return va - vb, True


def fight_features(f, va, vb, pw):
    """Antisymmetric matchup values d (A minus B) for every factor and interaction
    term, and whether each one is defined."""
    x, ok = {}, {}
    for fid, _ in PRIMARY:
        if fid in PAIRWISE:
            continue
        x[fid], ok[fid] = diff(va[fid], vb[fid])
    f17, f18, fin = pw
    x["F17"], ok["F17"] = (f17, True) if f17 is not None else (0.0, False)
    x["F18"], ok["F18"] = (f18, True) if f18 is not None else (0.0, False)
    # I1: x = F03, y = returned within 180 days
    x["I1_y"], ok["I1_y"] = diff(va["q180"], vb["q180"])
    pa = va["F03"] * va["q180"] if va["F03"] is not None else None
    pb = vb["F03"] * vb["q180"] if vb["F03"] is not None else None
    x["I1"], ok["I1"] = diff(pa, pb)
    # I2: F17 x previous meeting ended in a finish
    x["I2"], ok["I2"] = ((f17 * fin), True) if f17 is not None else (0.0, False)
    # I3: first main event x the opponent's prior main events
    x["I3_own"], ok["I3_own"] = va["own_mains"] - vb["own_mains"], True
    x["I3"], ok["I3"] = va["F20"] * va["opp_mains"] - vb["F20"] * vb["opp_mains"], True
    return x, ok


def build(fights, dob):
    """One pass in date order. All fights on a date are featurised from the state
    as it stood before that date, then folded in together: same-card (and
    same-day) results never reach a feature."""
    st = defaultdict(State)
    out = {}
    i = 0
    while i < len(fights):
        j = i
        while j < len(fights) and fights[j]["date"] == fights[i]["date"]:
            j += 1
        day = fights[i:j]
        snap = {}
        for f in day:
            sa, sb = st[f["a"]], st[f["b"]]
            va = fighter_values(sa, f["date"], dob.get(f["a"]), f["sched5"], f["main"], sb.mains)
            vb = fighter_values(sb, f["date"], dob.get(f["b"]), f["sched5"], f["main"], sa.mains)
            out[f["id"]] = fight_features(f, va, vb, pairwise(sa, sb, f["a"], f["b"]))
            snap[f["id"]] = (rate(sa.w, sa.l), rate(sb.w, sb.l))
        for f in day:
            qa, qb = snap[f["id"]]
            for me, opp, kd_abs, oq in ((f["a"], f["b"], f["b_kd"], qb), (f["b"], f["a"], f["a_kd"], qa)):
                s = st[me]
                o = outcome_for(f, me)
                s.n += 1
                s.last_date = f["date"]
                s.dates.append(f["date"])
                s.last_ko_loss = o == "L" and f["method"] == KO
                if s.last_ko_loss:
                    s.ko_dates.append(f["date"])
                s.kd_abs += kd_abs
                s.mins += minutes(f)
                if o == "W":
                    s.w += 1
                    s.streak = s.streak + 1 if s.streak > 0 else 1
                elif o == "L":
                    s.l += 1
                    s.streak = s.streak - 1 if s.streak < 0 else -1
                else:
                    s.streak = 0
                s.had5 = s.had5 or f["sched5"]
                s.mains += int(f["main"])
                s.oppq.append(oq)
                s.vs[opp].append((f["date"], f["event_id"], f["id"], o, f["method"]))
        i = j
    return out


# ---------------------------------------------------------------------------
# ... and naive (the point-in-time audit). Written separately on purpose: it
# rescans a history physically cut off before the fight's date.
# ---------------------------------------------------------------------------

def naive_values(hist, me, opp, t, dob, sched5, main):
    mine = [f for f in hist if me in (f["a"], f["b"])]
    if not mine:
        g = {k: None for k, _ in PRIMARY}
        g.update({"F11": 0.0, "F19": float(sched5), "F20": float(main), "q180": None, "own_mains": 0.0})
    else:
        last = mine[-1]
        outs = [outcome_for(f, me) for f in mine]
        kos = [f["date"] for f, o in zip(mine, outs) if o == "L" and f["method"] == KO]
        days = (t - last["date"]).days
        w = outs.count("W")
        l = outs.count("L")
        streak = 0
        for o in reversed(outs):
            if o == "W" and streak >= 0:
                streak += 1
            elif o == "L" and streak <= 0:
                streak -= 1
            else:
                break
        oppq = []
        for f in mine:
            other = f["b"] if f["a"] == me else f["a"]
            before = [h for h in hist if h["date"] < f["date"] and other in (h["a"], h["b"])]
            ow = sum(1 for h in before if outcome_for(h, other) == "W")
            ol = sum(1 for h in before if outcome_for(h, other) == "L")
            oppq.append(rate(ow, ol))
        mains = sum(1 for f in mine if f["main"])
        g = {
            "F01": len(kos), "F02": float(any((t - d).days <= 365 for d in kos)),
            "F03": float(outs[-1] == "L" and last["method"] == KO), "F04": float(len(kos) >= 2),
            "F05": sum(math.exp(-(t - d).days / 730.0) for d in kos),
            "F06": float(sum(f["b_kd"] if f["a"] == me else f["a_kd"] for f in mine)),
            "F07": math.log(days), "F08": float(days >= 365), "F09": float(days <= 90),
            "F10": float(sum(1 for f in mine if (t - f["date"]).days <= 730)),
            "F11": math.log1p(len(mine)), "F12": math.log1p(sum(minutes(f) for f in mine)),
            "F13": ((t - dob).days / 365.25) if dob else None, "F14": rate(w, l),
            "F15": sum(oppq) / len(oppq), "F16": float(max(-5, min(5, streak))),
            "F19": float(sched5 and not any(f["sched5"] for f in mine)),
            "F20": float(main and mains == 0), "q180": float(days <= 180),
            "own_mains": math.log1p(mains),
        }
    om = sum(1 for f in hist if opp in (f["a"], f["b"]) and f["main"])
    g["opp_mains"] = math.log1p(om)
    return g


def naive_pairwise(hist, a, b):
    meet = [f for f in hist if {f["a"], f["b"]} == {a, b}]
    f17 = fin = None
    if meet:
        o = outcome_for(meet[-1], a)
        f17 = 1.0 if o == "W" else -1.0 if o == "L" else 0.0
        fin = float(meet[-1]["method"] in FINISH)

    def opps(me, other):
        d = defaultdict(list)
        for f in hist:
            if me in (f["a"], f["b"]):
                c = f["b"] if f["a"] == me else f["a"]
                if c != other:
                    d[c].append(SCORE[outcome_for(f, me)])
        return d
    oa, ob = opps(a, b), opps(b, a)
    common = set(oa) & set(ob)
    f18 = (sum(sum(oa[c]) / len(oa[c]) - sum(ob[c]) / len(ob[c]) for c in common) / len(common)
           if common else None)
    return f17, f18, fin


def naive_features(fights, dob, f, swap=False):
    hist = [h for h in fights if h["date"] < f["date"]]
    a, b = (f["b"], f["a"]) if swap else (f["a"], f["b"])
    va = naive_values(hist, a, b, f["date"], dob.get(a), f["sched5"], f["main"])
    vb = naive_values(hist, b, a, f["date"], dob.get(b), f["sched5"], f["main"])
    return fight_features(f, va, vb, naive_pairwise(hist, a, b))


def audit(fights, dob, feats, scored):
    """Fails the run on any difference: point-in-time, and corner swap."""
    rnd = random.Random(AUDIT_SEED)
    sample = rnd.sample(scored, AUDIT_N)
    problems = []
    for f in sample:
        x, ok = feats[f["id"]]
        nx, nok = naive_features(fights, dob, f)
        sx, sok = naive_features(fights, dob, f, swap=True)
        for k in x:
            if ok[k] != nok[k] or abs(x[k] - nx[k]) > 1e-9:
                problems.append(f"fight {f['id']} {k}: run {x[k]!r}/{ok[k]} vs cut-off {nx[k]!r}/{nok[k]}")
            if sok[k] != ok[k] or abs(sx[k] + x[k]) > 1e-9:
                problems.append(f"fight {f['id']} {k}: not antisymmetric ({x[k]!r} vs swapped {sx[k]!r})")
    if problems:
        raise SystemExit("point-in-time audit FAILED:\n" + "\n".join(problems[:40]))
    return [f["id"] for f in sample]


# ---------------------------------------------------------------------------
# Model: p = sigmoid(a * logit(m) + X beta). No intercept, antisymmetric X.
# ---------------------------------------------------------------------------

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def fit(L, X, y, ridge=0.0, iters=100):
    """Newton-Raphson. Column 0 is the market slope (unpenalised); the rest are
    standardised factor columns, penalised by 0.5 * ridge * ||beta||^2."""
    Z = np.column_stack([L, X]) if X.size else L[:, None]
    k = Z.shape[1]
    pen = np.full(k, ridge + 1e-6)
    pen[0] = 1e-9
    w = np.zeros(k)
    w[0] = 1.0
    for _ in range(iters):
        mu = sigmoid(Z @ w)
        g = Z.T @ (y - mu) - pen * w
        H = (Z * (mu * (1 - mu))[:, None]).T @ Z + np.diag(pen)
        step = np.linalg.solve(H, g)
        w += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return w


class Design:
    def __init__(self, rows, feats):
        self.y = np.array([1.0 if r["res"] == "A" else 0.0 for r in rows])
        self.m = np.array([r["m"] for r in rows])
        self.L = np.log(self.m / (1 - self.m))
        self.year = np.array([r["date"].year for r in rows])
        self.event = np.array([r["event_id"] for r in rows])
        self.scored = np.array([r["scored"] for r in rows])
        keys = list(feats[rows[0]["id"]][0])
        self.col = {k: i for i, k in enumerate(keys)}
        self.X = np.array([[feats[r["id"]][0][k] for k in keys] for r in rows])
        self.ok = np.array([[feats[r["id"]][1][k] for k in keys] for r in rows])

    def cols(self, names):
        return self.X[:, [self.col[n] for n in names]]


def walk_forward(D: Design, names, ridge=0.0):
    """Out-of-sample p for every scored fight, plus the yearly coefficients
    (in the factor's own units)."""
    p = np.full(len(D.y), np.nan)
    coefs = {}
    X = D.cols(names) if names else np.zeros((len(D.y), 0))
    for Y in TEST_YEARS:
        tr = D.year < Y
        te = (D.year == Y) & D.scored
        if names:
            sd = X[tr].std(axis=0)
            sd[sd == 0] = 1.0
            Xs = X / sd
        else:
            sd, Xs = np.ones(0), X
        w = fit(D.L[tr], Xs[tr], D.y[tr], ridge)
        Zte = np.column_stack([D.L[te], Xs[te]]) if names else D.L[te][:, None]
        p[te] = sigmoid(Zte @ w)
        coefs[Y] = (float(w[0]), [float(b) for b in (w[1:] / sd)])
    return p, coefs


def pooled_direction(D: Design, names):
    tr = D.year <= 2024
    X = D.cols(names)
    sd = X[tr].std(axis=0)
    sd[sd == 0] = 1.0
    w = fit(D.L[tr], (X / sd)[tr], D.y[tr])
    return [float(b) for b in (w[1:] / sd)]


def score(D, p_new, p_ref, mask):
    """Per-fight gain LL(ref) - LL(new) on the scored set, card bootstrap."""
    y = D.y[mask]
    g = pp.log_loss_each(y, p_ref[mask]) - pp.log_loss_each(y, p_new[mask])
    boot = pp.cluster_bootstrap(g, D.event[mask], BOOT_B, BOOT_SEED)
    return {
        "gain": float(g.mean()),
        "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "p_one_sided": float((np.sum(boot <= 0) + 1) / (BOOT_B + 1)),
    }


def holm(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    survive = [False] * len(pvals)
    m = len(pvals)
    for rank, i in enumerate(order):
        if pvals[i] <= ALPHA / (m - rank):
            survive[i] = True
        else:
            break
    return survive


def verdict(fired, p, survives):
    if fired < MIN_FIRED:
        return "TOO_FEW"
    if survives:
        return "CANDIDATE"
    if p < ALPHA:
        return "HINT"
    return "NOTHING"


def even_odds_effect(beta_raw, unit):
    """At even odds, how often the fighter ahead by `unit` of this factor wins."""
    return float(1 / (1 + math.exp(-beta_raw * unit)))


# ---------------------------------------------------------------------------

def main():
    fights, dob = load()
    feats = build(fights, dob)

    rows = []
    for f in fights:
        priced = (f["bfo_a"] is not None and f["bfo_b"] is not None
                  and 100 <= abs(f["bfo_a"]) <= MAX_AMERICAN and 100 <= abs(f["bfo_b"]) <= MAX_AMERICAN)
        if f["res"] not in ("A", "B") or not priced or f["id"] in EXCLUDED_FIGHTS:
            continue
        r = dict(f)
        r["m"] = pp.devig_proportional(f["bfo_a"], f["bfo_b"])
        r["scored"] = f["date"].year in TEST_YEARS
        rows.append(r)
    scored_rows = [r for r in rows if r["scored"]]
    audited = audit(fights, dob, feats, scored_rows)

    D = Design(rows, feats)
    S = D.scored
    p_base, base_coefs = walk_forward(D, [])
    raw = D.m

    def symmetric(names, coefs):
        """pred_protocol's corner check on the final year's fitted model."""
        a, betas = coefs[TEST_YEARS[-1]]
        idx = [D.col[n] for n in names]
        recs = [{"L": float(D.L[i]), "x": [float(D.X[i, j]) for j in idx]} for i in np.where(S)[0][:500]]
        pred = lambda r: float(sigmoid(a * r["L"] + sum(b * v for b, v in zip(betas, r["x"]))))
        swap = lambda r: {"L": -r["L"], "x": [-v for v in r["x"]]}
        bad = pp.symmetry_violations(pred, recs, swap)
        if bad:
            raise SystemExit(f"corner symmetry FAILED for {names}: {len(bad)} rows")

    def one(names, label_id, ref_p, test_name):
        p, coefs = walk_forward(D, names)
        symmetric(names, coefs)
        res = score(D, p, ref_p, S)
        res["gain_vs_raw_market"] = score(D, p, raw, S)["gain"]
        j = D.col[test_name]
        res["fired"] = int(np.sum(S & D.ok[:, j] & (D.X[:, j] != 0)))
        res["defined"] = int(np.sum(S & D.ok[:, j]))
        pooled = pooled_direction(D, names)[names.index(test_name)]
        yearly = [c[1][names.index(test_name)] for c in coefs.values()]
        res["pooled_coef"] = pooled
        res["years_same_sign"] = int(sum(1 for b in yearly if b * pooled > 0))
        nz = D.X[S & D.ok[:, j], j]
        nz = nz[nz != 0]
        unit = 1.0 if set(np.unique(np.abs(nz))) <= {1.0} else float(np.std(nz)) if nz.size else 1.0
        res["unit"] = unit
        res["even_odds_win_pct"] = round(100 * even_odds_effect(pooled, unit), 1)
        return res

    out = {
        "experiment": "DISC-001",
        "data": {"fights_in_history": len(fights), "eligible_priced": len(rows),
                 "scored": int(S.sum()), "scored_events": int(len(set(D.event[S]))),
                 "test_years": [TEST_YEARS[0], TEST_YEARS[-1]],
                 "audit_fights": len(audited)},
        "baseline": {"gain_vs_raw_market": score(D, p_base, raw, S),
                     "market_slope_final_year": base_coefs[TEST_YEARS[-1]][0]},
        "primary": {}, "interactions": {}, "combined": {},
    }

    for fid, label in PRIMARY:
        r = one([fid], fid, p_base, fid)
        r["label"] = label
        r["contaminated"] = fid in CONTAMINATED
        out["primary"][fid] = r

    inter_spec = {
        "I1": (["F03", "I1_y"], "I1"),
        "I2": (["F17"], "I2"),
        "I3": (["F20", "I3_own"], "I3"),
    }
    for iid, label in INTERACTIONS:
        mains, term = inter_spec[iid]
        p_ref, _ = walk_forward(D, mains)
        r = one(mains + [term], iid, p_ref, term)
        r["label"] = label
        r["main_effects"] = mains
        out["interactions"][iid] = r

    for fam in ("primary", "interactions"):
        keys = list(out[fam])
        surv = holm([out[fam][k]["p_one_sided"] for k in keys])
        for k, s_ in zip(keys, surv):
            e = out[fam][k]
            e["holm_survives"] = bool(s_)
            e["verdict"] = verdict(e["fired"], e["p_one_sided"], s_)
            e["reaches_min_useful"] = e["gain"] >= MIN_USEFUL

    for cid, names in (("C1", [k for k, _ in PRIMARY]),
                       ("C2", [k for k, _ in PRIMARY if k not in CONTAMINATED])):
        p, coefs = walk_forward(D, names, RIDGE_COMBINED)
        symmetric(names, coefs)
        r = score(D, p, p_base, S)
        r["gain_vs_raw_market"] = score(D, p, raw, S)["gain"]
        r["factors"] = len(names)
        yearly = {}
        for Y in TEST_YEARS:
            mk = S & (D.year == Y)
            yearly[str(Y)] = float((pp.log_loss_each(D.y[mk], p_base[mk]) - pp.log_loss_each(D.y[mk], p[mk])).mean())
        r["by_year"] = yearly
        out["combined"][cid] = r

    (HERE / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: {i: (v["verdict"], round(v["gain"], 5), v["fired"]) for i, v in out[k].items()}
                      for k in ("primary", "interactions")}, indent=1))
    print(json.dumps({k: (round(v["gain"], 5), [round(c, 5) for c in v["ci95"]]) for k, v in out["combined"].items()}))
    return out


if __name__ == "__main__":
    main()
