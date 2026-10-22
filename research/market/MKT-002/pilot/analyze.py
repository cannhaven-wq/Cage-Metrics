"""MKT-002 pilot: quote quality, coverage and spread. Reads prices only; tests no hypothesis.

    python3 -I research/market/MKT-002/pilot/analyze.py <export.json> > pilot_results.json

Input: the rows returned by export_quotes.sql, saved locally as JSON (never
committed, D-034). Output: aggregates only.

What it computes (PILOT_PLAN.md): coverage per card, how often each quality
rule drops a quote, how many books are fresh at each anchor, the spread of
book-versus-consensus gaps (to fix the outlier threshold), and the spread of
CLV_return over ALL anchor quotes pooled (to fix the sample size).
What it never computes: CLV_return split by gap size or outlier status, by
book, or its mean — that is the hypothesis, and it waits for the freeze and
for new cards.
"""
from __future__ import annotations

import datetime as dt
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

ANCHORS_H = {"T-24h": 24.0, "T-3h": 3.0}
FRESH_ANCHOR_MIN = 120          # actionable-price staleness (alerts.js)
FRESH_CLOSE_MIN = 45            # CLV-001 frozen limit
W3_PREFIX = "odds-api-v4"
MAX_AMERICAN = 10000
GAP_STEPS = (0.02, 0.03, 0.04, 0.05)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def q(values, ps=(0.5, 0.75, 0.9, 0.95, 0.99)):
    v = sorted(values)
    if not v:
        return None
    return {str(p): round(v[min(len(v) - 1, int(p * len(v)))], 5) for p in ps}


def decimal(american):
    return 1 + (american / 100.0 if american > 0 else 100.0 / -american)


def from_csv(text):
    """export_quotes_compact.sql's CSV, typed like the JSON form."""
    import csv
    def b(v):
        return None if v == "" else v in ("true", "t", "True")
    def i(v):
        return None if v == "" else int(float(v))
    rows = []
    for r in csv.DictReader(text.splitlines()):
        rows.append(dict(r, fight_id=int(r["fight_id"]), event_id=int(r["event_id"]), book_id=int(r["book_id"]),
                         is_active=b(r["is_active"]), is_live=b(r["is_live"]),
                         market_status=r["market_status"] or None, am_a=i(r["am_a"]), am_b=i(r["am_b"]),
                         n_rows=int(r["n_rows"])))
    return rows


def main(path):
    raw = pathlib.Path(path).read_bytes()
    rows = json.loads(raw) if path.endswith(".json") else from_csv(raw.decode())
    out = {"export_sha256": hashlib.sha256(raw).hexdigest(), "rows_read": len(rows)}

    # ---- quality rules, counted in order; a quote is dropped by the first it fails
    drops = Counter()
    status_values = Counter(r.get("market_status") for r in rows)
    feed_values = Counter((r.get("feed_version") or "")[:24] for r in rows)
    good = []
    for r in rows:
        if r["is_active"] is False:
            drops["fight_not_active"] += 1
        elif not (r.get("feed_version") or "").startswith(W3_PREFIX):
            drops["not_w3_feed"] += 1
        elif not r.get("retrieved_at"):
            drops["no_retrieved_at"] += 1
        elif r.get("is_live"):
            drops["live"] += 1
        elif r.get("market_status") not in (None, "open"):
            drops[f"status_{r.get('market_status')}"] += 1
        elif r["am_a"] is None or r["am_b"] is None:
            drops["one_sided"] += 1
        elif not all(100 <= abs(x) <= MAX_AMERICAN for x in (r["am_a"], r["am_b"])):
            drops["beyond_100_to_1"] += 1
        elif ts(r["retrieved_at"]) >= ts(r["start_at"]):
            drops["after_start"] += 1
        else:
            good.append(r)
    out["quality"] = {"kept": len(good), "dropped": dict(drops), "market_status_values": dict(status_values),
                      "feed_version_prefixes": dict(feed_values)}

    # ---- coverage per card
    by_card = defaultdict(lambda: {"fights": set(), "books": set(), "captures": 0, "basis": Counter()})
    starts = {}
    for r in good:
        c = by_card[(r["event_id"], r["event_date"])]
        c["fights"].add(r["fight_id"]); c["books"].add(r["book_id"]); c["captures"] += 1
        starts[r["fight_id"]] = (ts(r["start_at"]), r["start_basis"], r["event_id"])
    for fid, (_, basis, ev) in starts.items():
        by_card[next(k for k in by_card if k[0] == ev)]["basis"][basis] += 1
    out["cards"] = [{"event_id": k[0], "event_date": k[1], "fights_with_quotes": len(v["fights"]),
                     "books": len(v["books"]), "clean_quote_rows": v["captures"], "start_basis": dict(v["basis"])}
                    for k, v in sorted(by_card.items(), key=lambda kv: kv[0][1])]

    # ---- per fight, per book: clean two-sided captures in time order
    series = defaultdict(lambda: defaultdict(list))
    for r in good:
        series[r["fight_id"]][r["book_id"]].append((ts(r["retrieved_at"]), r["am_a"], r["am_b"]))
    for f in series.values():
        for b in f.values():
            b.sort()

    def at(fid, when, max_age_min):
        """Each book's latest capture at or before `when`, no older than max_age_min."""
        got = {}
        for book, caps in series[fid].items():
            prior = [c for c in caps if c[0] <= when]
            if prior and (when - prior[-1][0]).total_seconds() / 60 <= max_age_min:
                got[book] = prior[-1]
        return got

    def fair_a(am_a, am_b):
        try:
            return power_devig(pp.american_to_implied(am_a), pp.american_to_implied(am_b))[0]
        except ValueError:
            return None

    books_at = defaultdict(list)
    gaps = defaultdict(list)
    outlier_counts = defaultdict(Counter)
    clv_pooled = defaultdict(list)          # (anchor) -> [(card, clv)], all quotes, both corners
    band_drops = Counter()
    cadence = []
    for fid, books in series.items():
        start, _, ev = starts[fid]
        for caps in books.values():
            last = [c[0] for c in caps if (start - c[0]).total_seconds() <= 24 * 3600]
            cadence += [(b - a).total_seconds() / 60 for a, b in zip(last, last[1:])]
        close = at(fid, start - dt.timedelta(seconds=1), FRESH_CLOSE_MIN)
        books_at["close"].append(len(close))
        close_fair = [x for x in (fair_a(c[1], c[2]) for c in close.values()) if x is not None]
        close_p = statistics.median(close_fair) if len(close_fair) >= 3 else None
        for name, hrs in ANCHORS_H.items():
            snap = at(fid, start - dt.timedelta(hours=hrs), FRESH_ANCHOR_MIN)
            books_at[name].append(len(snap))
            fair = {}
            for book, c in snap.items():
                p = fair_a(c[1], c[2])
                if p is None:
                    band_drops[name] += 1
                else:
                    fair[book] = (p, c)
            if len(fair) < 4:
                continue
            for book, (p, c) in fair.items():
                others = [v[0] for k, v in fair.items() if k != book]
                g = abs(p - statistics.median(others))
                gaps[name].append(g)
                for step in GAP_STEPS:
                    if g >= step:
                        outlier_counts[name][f">={int(step * 100)}pts"] += 1
                if close_p is not None:          # pooled over every quote; never split by g
                    clv_pooled[name].append((ev, close_p * decimal(c[1]) - 1))
                    clv_pooled[name].append((ev, (1 - close_p) * decimal(c[2]) - 1))

    def books_summary(v):
        return {"fight_count": len(v), "distribution": dict(sorted(Counter(v).items())),
                "share_with_4_plus": round(sum(x >= 4 for x in v) / len(v), 4) if v else None,
                "share_with_3_plus": round(sum(x >= 3 for x in v) / len(v), 4) if v else None}

    out["fresh_books"] = {k: books_summary(v) for k, v in books_at.items()}
    out["band_excluded_quotes"] = dict(band_drops)
    out["capture_gap_minutes_last_24h"] = q(cadence)
    out["abs_gap_vs_leave_one_out_median"] = {k: {"quotes": len(v), "quantiles": q(v),
                                                  "count_at_or_above": dict(outlier_counts[k])}
                                              for k, v in gaps.items()}

    # spread of CLV_return over ALL quotes, and its within-card correlation (one-way ANOVA ICC)
    spread = {}
    for name, pairs in clv_pooled.items():
        vals = [v for _, v in pairs]
        groups = defaultdict(list)
        for ev, v in pairs:
            groups[ev].append(v)
        k = len(groups); n = len(vals)
        grand = sum(vals) / n
        ssb = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups.values())
        ssw = sum((x - sum(g) / len(g)) ** 2 for g in groups.values() for x in g)
        n0 = (n - sum(len(g) ** 2 for g in groups.values()) / n) / (k - 1) if k > 1 else float("nan")
        msb, msw = ssb / (k - 1) if k > 1 else float("nan"), ssw / (n - k) if n > k else float("nan")
        icc = (msb - msw) / (msb + (n0 - 1) * msw) if k > 1 and n > k else None
        spread[name] = {"quote_sides": n, "cards": k, "sd": round(statistics.stdev(vals), 5) if n > 1 else None,
                        "icc_by_card": round(icc, 4) if icc is not None else None}
    out["clv_return_spread_all_quotes"] = spread
    out["not_computed"] = ("mean CLV_return; CLV_return by gap, outlier status or book "
                           "(the hypothesis: waits for the freeze and for new cards)")
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=1, default=str))
