"""Walk-forward evaluation, uncertainty, multiple testing and stability.

Two stages, both inside PRED-001's DEV partition (every fight before
2025-01-01; nothing sealed is read):

  SCREEN   walk-forward test years cfg["screen_years"] (default 2010-2018).
           Every candidate in the catalog is scored. The tested family
           (singles + interactions) is corrected for multiple testing
           (Benjamini-Hochberg, Holm, and a permutation max-statistic null).
           Survivors form the SHORTLIST, which is fixed and hashed before the
           next stage is computed.
  CONFIRM  walk-forward test years cfg["confirm_years"] (default 2019-2024).
           Only shortlisted candidates can be confirmed; Holm over the
           shortlist size. Every other candidate's confirmation-era numbers
           are still computed and kept - descriptive only, never a rescue.

Each test year's model is fitted only on scorable fights from earlier years
(an expanding window). Every number is out-of-sample in time.

Signs follow PRED-001: delta = LL(reference) - LL(candidate); positive means the
candidate forecast better. Uncertainty resamples whole events (cards).
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

import pred_protocol as pp
from . import model as M
from .candidates import Candidate

_N = NormalDist()


# ----------------------------------------------------------------------------- statistics
def cluster_z(delta: np.ndarray, clusters: np.ndarray) -> tuple[float, float]:
    """Mean and cluster-robust (by event) standard error of a per-fight delta."""
    d = np.asarray(delta, dtype=float)
    n = len(d)
    if n == 0:
        return float("nan"), float("nan")
    m = d.mean()
    _, inv = np.unique(clusters, return_inverse=True)
    s = np.bincount(inv, weights=d - m)
    G = len(s)
    if G < 2:
        return float(m), float("nan")
    se = math.sqrt(float(np.sum(s ** 2)) * G / (G - 1)) / n
    return float(m), se


def one_sided_p(mean: float, se: float) -> float:
    if not np.isfinite(se) or se <= 0:
        return float("nan")
    return 1.0 - _N.cdf(mean / se)


def bootstrap_ci(delta, clusters, B: int, seed: int, level: float = 0.95) -> tuple[float, float]:
    if len(delta) == 0:
        return float("nan"), float("nan")
    boots = pp.cluster_bootstrap(delta, clusters, B=B, seed=seed)
    lo, hi = np.quantile(boots, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def benjamini_hochberg(p: np.ndarray, q: float) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), dtype=bool)
    m = int(ok.sum())
    if m == 0:
        return out
    idx = np.where(ok)[0][np.argsort(p[ok])]
    thresh = q * np.arange(1, m + 1) / m
    passed = p[idx] <= thresh
    if passed.any():
        k = np.max(np.where(passed)[0])
        out[idx[: k + 1]] = True
    return out


def bh_adjusted(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return out
    idx = np.where(ok)[0][np.argsort(p[ok])]
    adj = p[idx] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[idx] = np.minimum(adj, 1.0)
    return out


def holm(p: np.ndarray, alpha: float) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.zeros(len(p), dtype=bool)
    ok = np.isfinite(p)
    m = int(ok.sum())
    idx = np.where(ok)[0][np.argsort(p[ok])]
    for rank, i in enumerate(idx):
        if p[i] <= alpha / (m - rank):
            out[i] = True
        else:
            break
    return out


# ----------------------------------------------------------------------------- walk-forward
class WalkForward:
    """Scorable DEV fights, sorted by date, with fold definitions."""

    def __init__(self, table: pd.DataFrame, cfg: dict, q_col: str = "q_close"):
        S = table[table.is_scorable].sort_values(["event_date", "fight_id"]).reset_index(drop=True)
        self.S = S
        self.cfg = cfg
        self.q_col = q_col
        self.y = S.y.to_numpy(float)
        self.year = S.event_date.dt.year.to_numpy()
        self.event = S.event_id.astype(str).to_numpy()
        self.off = M.logit(S[q_col].to_numpy(float))
        self.q = S[q_col].to_numpy(float)
        self.stages = {"screen": list(cfg["screen_years"]), "confirm": list(cfg["confirm_years"])}
        start = cfg["train_start_year"]
        self.folds = {}
        for st, years in self.stages.items():
            fl = []
            for yr in years:
                tr = np.where((self.year < yr) & (self.year >= start))[0]
                te = np.where(self.year == yr)[0]
                if len(tr) and len(te):
                    fl.append((yr, tr, te))
            self.folds[st] = fl
        self.test_idx = {st: np.concatenate([te for _, _, te in fl]) if fl else np.array([], int)
                         for st, fl in self.folds.items()}

    def with_q(self, q_col: str) -> "WalkForward":
        """Same fights and folds, a different de-vig for the market input."""
        w = WalkForward.__new__(WalkForward)
        w.__dict__.update(self.__dict__)
        w.q_col = q_col
        w.q = self.S[q_col].to_numpy(float)
        w.off = M.logit(w.q)
        return w

    @staticmethod
    def transformer(cand: Candidate, train, cache: dict | None = None, key=None):
        """Fit the candidate's scaling on training rows only; return a function
        mapping any rows to the design matrix. Rows are a DataFrame or a dict
        of column arrays holding the RAW feature values. `cache`/`key` reuse a
        column's scaler for the same training rows (it is deterministic)."""
        def col(R, n):
            return np.asarray(R[n], dtype=float)

        def scaler(n, kind):
            ck = (key, n, kind)
            if cache is not None and key is not None and ck in cache:
                return cache[ck]
            sc = (M.Scaler().fit(col(train, n)[:, None]) if kind == "anti"
                  else M.CtxScaler().fit(col(train, n)))
            if cache is not None and key is not None:
                cache[ck] = sc
            return sc

        parts = []
        for t in cand.terms:
            parts.append(lambda R, t=t, sc=scaler(t, "anti"): sc.transform(col(R, t)[:, None]))
        for a, c in cand.interact:
            parts.append(lambda R, a=a, c=c, sa=scaler(a, "anti"), scx=scaler(c, "ctx"):
                         (sa.transform(col(R, a)[:, None])[:, 0] * scx.transform(col(R, c)))[:, None])
        if not parts:
            raise ValueError(f"{cand.cid} has no terms")
        return lambda R: np.hstack([p(R) for p in parts])

    def columns(self, cand: Candidate, S: pd.DataFrame | None = None) -> dict:
        S = self.S if S is None else S
        names = set(cand.terms) | {x for p in cand.interact for x in p}
        return {n: S[n].to_numpy(float) for n in names}

    def design(self, cand: Candidate, tr: np.ndarray, te: np.ndarray, S: pd.DataFrame | None = None,
               cols: dict | None = None, cache: dict | None = None, key=None):
        cols = self.columns(cand, S) if cols is None else cols
        tf = self.transformer(cand, {n: v[tr] for n, v in cols.items()}, cache, key)
        return tf({n: v[tr] for n, v in cols.items()}), tf({n: v[te] for n, v in cols.items()})

    def oos(self, cand: Candidate | None, stage: str, S: pd.DataFrame | None = None,
            scache: dict | None = None) -> dict:
        """Out-of-sample probabilities over a stage's test rows. cand=None is
        the recalibrated market (market slope only)."""
        cfg = self.cfg
        standalone = cand is not None and cand.kind == "standalone"
        multi = cand is not None and cand.kind in ("multi", "standalone")
        ridge = cfg["ridge_multi"] if multi else cfg["ridge_single"]
        ps, coefs = [], []
        cols = self.columns(cand, S) if cand is not None else None
        for yr, tr, te in self.folds[stage]:
            if cand is None:
                Xtr, Xte = np.zeros((len(tr), 0)), np.zeros((len(te), 0))
            else:
                Xtr, Xte = self.design(cand, tr, te, cols=cols, cache=scache, key=(stage, yr))
            off_tr = np.zeros(len(tr)) if standalone else self.off[tr]
            off_te = np.zeros(len(te)) if standalone else self.off[te]
            th = M.fit_offset_logistic(Xtr, off_tr, self.y[tr], ridge, market_slope=not standalone)
            ps.append(M.predict_offset_logistic(th, Xte, off_te, market_slope=not standalone))
            coefs.append(th.tolist())
        return {"p": np.concatenate(ps) if ps else np.array([]), "coefs": coefs}


# ----------------------------------------------------------------------------- one candidate, one stage
def informative_mask(wf: WalkForward, cand: Candidate, idx: np.ndarray,
                     S: pd.DataFrame | None = None) -> np.ndarray:
    cols = list(cand.terms) + [a for a, _ in cand.interact]
    if not cols:
        return np.ones(len(idx), bool)
    V = (wf.S if S is None else S)[cols].to_numpy(float)[idx]
    return np.any(np.isfinite(V) & (V != 0), axis=1)


def stage_record(wf: WalkForward, cand: Candidate, stage: str, p: np.ndarray, coefs: list,
                 p_ref: np.ndarray, ref_name: str, p_recal: np.ndarray, cfg: dict,
                 boot: int, seed: int, S: pd.DataFrame | None = None) -> dict:
    idx = wf.test_idx[stage]
    y, q, ev, yr = wf.y[idx], wf.q[idx], wf.event[idx], wf.year[idx]
    ll_c = pp.log_loss_each(y, p)
    ll_m = pp.log_loss_each(y, q)
    ll_r = pp.log_loss_each(y, p_recal)
    ll_ref = pp.log_loss_each(y, p_ref)
    d_mkt, d_ref, d_rec = ll_m - ll_c, ll_ref - ll_c, ll_r - ll_c
    m_ref, se_ref = cluster_z(d_ref, ev)
    m_mkt, se_mkt = cluster_z(d_mkt, ev)
    acc_c = float(np.mean((p > 0.5) == (y == 1)))
    acc_m = float(np.mean((q > 0.5) == (y == 1)))
    per_year = {}
    for Y in np.unique(yr):
        k = yr == Y
        per_year[int(Y)] = round(float(d_ref[k].mean()), 6)
    vals = list(per_year.values())
    # the coefficient of the term that defines the candidate: the last one
    key = [c[-1] for c in coefs if len(c) > 1] if cand is not None and cand.kind != "standalone" else \
          [c[-1] for c in coefs if len(c)]
    med = float(np.median(key)) if key else float("nan")
    agree = float(np.mean(np.sign(key) == np.sign(med))) if key and med != 0 else float("nan")
    inf = informative_mask(wf, cand, idx, S) if cand is not None else np.ones(len(idx), bool)
    half = len(idx) // 2
    rec = {
        "n": int(len(idx)), "n_events": int(len(np.unique(ev))), "n_informative": int(inf.sum()),
        "coverage": round(float(inf.mean()), 4) if len(idx) else 0.0,
        "ll_candidate": round(float(ll_c.mean()), 6), "ll_market": round(float(ll_m.mean()), 6),
        "ll_recalibrated_market": round(float(ll_r.mean()), 6),
        "delta_vs_market": round(m_mkt, 6), "se_vs_market": round(se_mkt, 6),
        "delta_vs_recalibrated": round(float(d_rec.mean()), 6),
        "screen_reference": ref_name,
        "delta_vs_reference": round(m_ref, 6), "se_vs_reference": round(se_ref, 6),
        "z_vs_reference": round(m_ref / se_ref, 4) if se_ref and np.isfinite(se_ref) and se_ref > 0 else None,
        "p_one_sided": one_sided_p(m_ref, se_ref),
        "sd_delta_vs_market": round(float(np.std(d_mkt, ddof=1)), 6) if len(idx) > 1 else None,
        "accuracy_candidate": round(acc_c, 4), "accuracy_market": round(acc_m, 4),
        "brier_candidate": round(float(np.mean(pp.brier_each(y, p))), 6),
        "brier_market": round(float(np.mean(pp.brier_each(y, q))), 6),
        "per_year_delta_vs_reference": per_year,
        "frac_years_positive": round(float(np.mean(np.array(vals) > 0)), 4) if vals else None,
        "first_half_delta": round(float(d_ref[:half].mean()), 6) if half else None,
        "second_half_delta": round(float(d_ref[half:].mean()), 6) if half else None,
        "key_coef_median": round(med, 6) if np.isfinite(med) else None,
        "key_coef_sign_agreement": round(agree, 4) if np.isfinite(agree) else None,
        "market_slope_median": round(float(np.median([c[0] for c in coefs])), 6)
        if coefs and cand is not None and cand.kind != "standalone" and len(coefs[0]) else None,
    }
    if boot:
        rec["ci95_vs_reference"] = [round(x, 6) for x in bootstrap_ci(d_ref, ev, boot, seed)]
        rec["ci95_vs_market"] = [round(x, 6) for x in bootstrap_ci(d_mkt, ev, boot, seed)]
    trip = []
    if m_mkt > cfg["leak_delta"]:
        trip.append(f"delta vs market {m_mkt:.4f} > {cfg['leak_delta']}")
    if acc_c - acc_m > cfg["leak_accuracy_lift"]:
        trip.append(f"accuracy lift {acc_c - acc_m:.3f} > {cfg['leak_accuracy_lift']}")
    rec["tripwires"] = trip
    return rec


def screen_family(wf: WalkForward, cands: list[Candidate], stage: str, S: pd.DataFrame | None = None,
                  cache: dict | None = None) -> dict:
    """OOS probabilities for every candidate in one stage (optionally on a
    permuted copy of the data). Returns cid -> {"p", "coefs"}."""
    out = {} if cache is None else cache
    scache: dict = {}   # one scaler per (fold, column) for THIS dataset only
    out["__recal__"] = wf.oos(None, stage, S)
    for c in cands:
        if c.cid not in out:
            out[c.cid] = wf.oos(c, stage, S, scache)
    return out


def family_z(wf: WalkForward, cands: list[Candidate], preds: dict, stage: str) -> np.ndarray:
    """Cluster z of each family candidate against its screening reference."""
    idx = wf.test_idx[stage]
    y, ev = wf.y[idx], wf.event[idx]
    ll_recal = pp.log_loss_each(y, preds["__recal__"]["p"])
    zs = []
    for c in cands:
        ll_ref = pp.log_loss_each(y, preds[c.parent]["p"]) if c.parent else ll_recal
        d = ll_ref - pp.log_loss_each(y, preds[c.cid]["p"])
        m, se = cluster_z(d, ev)
        zs.append(m / se if se and np.isfinite(se) and se > 0 else 0.0)
    return np.array(zs)


def permute_within_year(wf: WalkForward, cols: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """A copy of the scorable table where each feature column is shuffled
    among fights of the same year, independently per column. Breaks every
    feature-outcome link while keeping each year's feature distribution, so
    each fold's scaling is unchanged."""
    S = wf.S.copy()
    for Y in np.unique(wf.year):
        rows = np.where(wf.year == Y)[0]
        for c in cols:
            S.loc[rows, c] = S[c].to_numpy()[rng.permutation(rows)]
    return S
