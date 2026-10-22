"""MKT-002 pilot: quote quality, coverage and spread. Reads prices only; tests no hypothesis.

    python3 -I research/market/MKT-002/pilot/analyze.py <quality.json> <bouts.csv> <snapshots.csv> <snap_md5> <bouts_md5>

Inputs are the outputs of read1_quality.sql and read2_anchor_snapshots.sql,
saved outside the repository (D-034). The two CSV files must reproduce the md5
the database computed over the same text, so the local copies are provably
exact. Output: aggregates only.

What it computes (PILOT_PLAN.md): how often each quality rule drops a quote,
coverage per card, how many books are fresh at each anchor, the spread of
book-versus-consensus gaps (to fix the outlier threshold), and the spread of
CLV_return over ALL anchor quotes pooled (to fix the sample size).
What it never computes: the mean of CLV_return, or CLV_return split by gap,
outlier status or book. That is the hypothesis; it waits for the freeze and
for new cards.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import statistics
import sys
from collections import Counter, defaultdict

REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "cfl_engine"))
sys.path.insert(0, str(REPO / "research" / "protocol"))
import pred_protocol as pp  # noqa: E402
from clv.devig import power_devig  # noqa: E402  CLV-001's frozen primary

ANCHORS = ("T-24h", "T-3h")
GAP_STEPS = (0.02, 0.03, 0.04, 0.05)


def quantiles(values, ps=(0.5, 0.75, 0.9, 0.95, 0.99)):
    v = sorted(values)
    return {str(p): round(v[min(len(v) - 1, int(p * len(v)))], 5) for p in ps} if v else None


def decimal(american):
    return 1 + (american / 100.0 if american > 0 else 100.0 / -american)


def fair_a(am_a, am_b):
    try:
        return power_devig(pp.american_to_implied(am_a), pp.american_to_implied(am_b))[0]
    except ValueError:
        return None


def icc_by_group(pairs):
    """One-way ANOVA intraclass correlation of values grouped by card."""
    groups = defaultdict(list)
    for g, v in pairs:
        groups[g].append(v)
    k, n = len(groups), len(pairs)
    if k < 2 or n <= k:
        return None
    grand = sum(v for _, v in pairs) / n
    means = {g: sum(v) / len(v) for g, v in groups.items()}
    msb = sum(len(v) * (means[g] - grand) ** 2 for g, v in groups.items()) / (k - 1)
    msw = sum((x - means[g]) ** 2 for g, v in groups.items() for x in v) / (n - k)
    n0 = (n - sum(len(v) ** 2 for v in groups.values()) / n) / (k - 1)
    return (msb - msw) / (msb + (n0 - 1) * msw)


def main(quality_path, bouts_path, snap_path, snap_md5, bouts_md5):
    bouts_txt = pathlib.Path(bouts_path).read_text().rstrip("\n")
    snap_txt = pathlib.Path(snap_path).read_text().rstrip("\n")
    if hashlib.md5(snap_txt.encode()).hexdigest() != snap_md5 or \
            hashlib.md5(bouts_txt.encode()).hexdigest() != bouts_md5:
        raise SystemExit("local copy does not match the database's md5; not analysing it")
    out = {"inputs": {"snapshots_md5": snap_md5, "bouts_md5": bouts_md5,
                      "quality_sha256": hashlib.sha256(pathlib.Path(quality_path).read_bytes()).hexdigest()},
           "quality": json.loads(pathlib.Path(quality_path).read_text())}

    bouts = {}
    for line in bouts_txt.splitlines():
        ev, fid, basis = line.split(",")
        bouts[int(fid)] = (int(ev), basis)
    snap = defaultdict(dict)                 # (fight, anchor) -> book -> (age, am_a, am_b)
    for line in snap_txt.splitlines():
        ev, fid, anchor, book, age, am_a, am_b = line.split(",")
        snap[(int(fid), anchor)][int(book)] = (int(age), int(am_a), int(am_b))
    out["bouts_with_clean_quotes"] = len(bouts)

    fresh = {}
    for anchor in ANCHORS + ("close",):
        counts = [len(snap.get((fid, anchor), {})) for fid in bouts]
        ages = [a for fid in bouts for a, _, _ in snap.get((fid, anchor), {}).values()]
        fresh[anchor] = {"distribution": dict(sorted(Counter(counts).items())),
                         "share_with_4_plus": round(sum(c >= 4 for c in counts) / len(counts), 4),
                         "share_with_3_plus": round(sum(c >= 3 for c in counts) / len(counts), 4),
                         "median_age_min": statistics.median(ages) if ages else None}
    out["fresh_books_per_bout"] = fresh

    gaps, steps, clv, band = defaultdict(list), defaultdict(Counter), defaultdict(list), Counter()
    for fid, (ev, _) in bouts.items():
        close = [fair_a(a, b) for _, a, b in snap.get((fid, "close"), {}).values()]
        close = [p for p in close if p is not None]
        close_p = statistics.median(close) if len(close) >= 3 else None
        for anchor in ANCHORS:
            fair = {}
            for book, (_, a, b) in snap.get((fid, anchor), {}).items():
                p = fair_a(a, b)
                if p is None:
                    band[anchor] += 1
                else:
                    fair[book] = (p, a, b)
            if len(fair) < 4:
                continue
            for book, (p, a, b) in fair.items():
                g = abs(p - statistics.median([v[0] for k, v in fair.items() if k != book]))
                gaps[anchor].append(g)
                for s in GAP_STEPS:
                    if g >= s:
                        steps[anchor][f">={int(round(s * 100))}pts"] += 1
                if close_p is not None:       # pooled over every quote; never split by g
                    clv[anchor].append((ev, close_p * decimal(a) - 1))
                    clv[anchor].append((ev, (1 - close_p) * decimal(b) - 1))
    out["band_excluded_quotes"] = dict(band)
    out["abs_gap_vs_leave_one_out_median"] = {
        a: {"quotes": len(gaps[a]), "quantiles": quantiles(gaps[a]), "count_at_or_above": dict(steps[a])}
        for a in ANCHORS}
    out["clv_return_spread_all_quotes"] = {}
    for a in ANCHORS:
        icc = icc_by_group(clv[a])
        out["clv_return_spread_all_quotes"][a] = {
            "quote_sides": len(clv[a]), "cards": len({e for e, _ in clv[a]}),
            "sd": round(statistics.stdev([v for _, v in clv[a]]), 5) if len(clv[a]) > 1 else None,
            "icc_by_card": round(icc, 4) if icc is not None else None}
    out["not_computed"] = ("mean CLV_return; CLV_return by gap, outlier status or book "
                           "(the hypothesis: waits for the freeze and for new cards)")
    return out


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:6]), indent=1, default=str))
