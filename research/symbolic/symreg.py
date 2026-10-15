"""Bounded symbolic regression for corner-antisymmetric fight models (SYM-002).

A model is a list of expression trees h_1..h_K. Each tree reads two vectors of
standardised per-fighter features, `a` (this corner) and `b` (the opponent), and
contributes the term

    T_k(A, B) = h_k(a, b) - h_k(b, a)

so T_k(B, A) = -T_k(A, B) exactly. With no intercept,

    P(A wins) = sigmoid( offset + sum_k w_k * T_k / s_k )

and swapping corners maps P to 1 - P (offset = logit of the market for
Experiment B, which is antisymmetric too, or 0 for Experiment A).

Numerical safety: protected division x / (1 + |y|) (denominator >= 1), every
node clipped to +/- NODE_CLIP, NaN/inf mapped to 0, terms that are identically
zero after antisymmetrisation are rejected, and weights are fitted with an L2
penalty by a damped Newton solver.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

NODE_CLIP = 20.0
CONSTS = (0.5, 1.0, 2.0)
BINARY = ("add", "sub", "mul", "pdiv")
UNARY = ("tanh", "sq", "abs", "slog")


# ------------------------------------------------------------------ trees
# ("x", side, i)  side 0 = own corner, 1 = opponent
# ("c", value)
# ("u", op, child)
# ("b", op, left, right)

def depth(t) -> int:
    if t[0] in ("x", "c"):
        return 0
    if t[0] == "u":
        return 1 + depth(t[2])
    return 1 + max(depth(t[2]), depth(t[3]))


def size(t) -> int:
    if t[0] in ("x", "c"):
        return 1
    if t[0] == "u":
        return 1 + size(t[2])
    return 1 + size(t[2]) + size(t[3])


def to_str(t, names) -> str:
    if t[0] == "x":
        return f"{'a' if t[1] == 0 else 'b'}.{names[t[2]]}"
    if t[0] == "c":
        return f"{t[1]:g}"
    if t[0] == "u":
        return f"{t[1]}({to_str(t[2], names)})"
    sym = {"add": "+", "sub": "-", "mul": "*"}.get(t[1])
    if sym:
        return f"({to_str(t[2], names)} {sym} {to_str(t[3], names)})"
    return f"pdiv({to_str(t[2], names)}, {to_str(t[3], names)})"


def _clean(v):
    v = np.nan_to_num(v, nan=0.0, posinf=NODE_CLIP, neginf=-NODE_CLIP)
    return np.clip(v, -NODE_CLIP, NODE_CLIP)


def evaluate(t, A, B):
    """h(a, b) on matrices A (own) and B (opponent), rows = fights."""
    k = t[0]
    if k == "x":
        return (A if t[1] == 0 else B)[:, t[2]]
    if k == "c":
        return np.full(A.shape[0], t[1])
    if k == "u":
        x = evaluate(t[2], A, B)
        op = t[1]
        with np.errstate(all="ignore"):
            if op == "tanh":
                v = np.tanh(x)
            elif op == "sq":
                v = x * x
            elif op == "abs":
                v = np.abs(x)
            else:
                v = np.sign(x) * np.log1p(np.abs(x))
        return _clean(v)
    l, r = evaluate(t[2], A, B), evaluate(t[3], A, B)
    with np.errstate(all="ignore"):
        if t[1] == "add":
            v = l + r
        elif t[1] == "sub":
            v = l - r
        elif t[1] == "mul":
            v = l * r
        else:
            v = l / (1.0 + np.abs(r))
    return _clean(v)


def term(t, A, B):
    """Antisymmetric term T = h(a,b) - h(b,a)."""
    return evaluate(t, A, B) - evaluate(t, B, A)


def is_linear(t) -> bool:
    """True if h is an affine combination of leaves (only add/sub, constants
    multiplying nothing nonlinear). Used to label a structure honestly."""
    if t[0] in ("x", "c"):
        return True
    if t[0] == "u":
        return False
    if t[1] in ("add", "sub"):
        return is_linear(t[2]) and is_linear(t[3])
    if t[1] == "mul":
        return (t[2][0] == "c" and is_linear(t[3])) or (t[3][0] == "c" and is_linear(t[2]))
    return False


# ------------------------------------------------------------------ fitting
def fit_logistic(X, y, offset=None, lam=1.0, iters=30):
    """L2-penalised logistic regression, no intercept, optional fixed offset.
    Minimises sum(logloss) + lam/2 * ||w||^2 by damped Newton."""
    n, k = X.shape
    w = np.zeros(k)
    off = np.zeros(n) if offset is None else offset
    if k == 0:
        return w
    for _ in range(iters):
        z = np.clip(off + X @ w, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        g = X.T @ (p - y) + lam * w
        H = (X * (p * (1 - p))[:, None]).T @ X + lam * np.eye(k)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, g, rcond=None)[0]
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def logloss(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


# ------------------------------------------------------------------ search
@dataclass
class SearchData:
    """Inner-train / inner-validation matrices for one fold, already scaled."""
    A_tr: np.ndarray
    B_tr: np.ndarray
    y_tr: np.ndarray
    A_va: np.ndarray
    B_va: np.ndarray
    y_va: np.ndarray
    off_tr: np.ndarray | None = None
    off_va: np.ndarray | None = None
    cache: dict = field(default_factory=dict)

    def term_cols(self, t, key):
        if key not in self.cache:
            tr, va = term(t, self.A_tr, self.B_tr), term(t, self.A_va, self.B_va)
            s = float(np.std(tr))
            self.cache[key] = None if (not np.isfinite(s) or s < 1e-8) else (tr / s, va / s)
        return self.cache[key]


class Search:
    def __init__(self, data: SearchData, names, max_depth, max_terms, seed,
                 population, generations, tournament, elitism, hof_size,
                 penalty, lam=1.0, log=None, run_label=""):
        self.d, self.names = data, names
        self.nf = len(names)
        self.max_depth, self.max_terms = max_depth, max_terms
        self.rng = np.random.default_rng(seed)
        self.P, self.G, self.T, self.E = population, generations, tournament, elitism
        self.hof_size, self.penalty, self.lam = hof_size, penalty, lam
        self.log = log if log is not None else []
        self.label = run_label
        self.seen = {}

    # --- random construction
    def rand_leaf(self):
        if self.rng.random() < 0.08:
            return ("c", float(self.rng.choice(CONSTS)))
        return ("x", int(self.rng.integers(2)), int(self.rng.integers(self.nf)))

    def rand_tree(self, d):
        if d == 0 or self.rng.random() < 0.3:
            return self.rand_leaf()
        if self.rng.random() < 0.3:
            return ("u", str(self.rng.choice(UNARY)), self.rand_tree(d - 1))
        return ("b", str(self.rng.choice(BINARY)), self.rand_tree(d - 1), self.rand_tree(d - 1))

    def rand_term(self):
        # a third of new terms start as a plain own-feature leaf (=> linear difference)
        if self.rng.random() < 0.33:
            return ("x", 0, int(self.rng.integers(self.nf)))
        return self.rand_tree(self.max_depth)

    # --- subtree utilities
    def _paths(self, t, p=()):
        yield p
        if t[0] == "u":
            yield from self._paths(t[2], p + (2,))
        elif t[0] == "b":
            yield from self._paths(t[2], p + (2,))
            yield from self._paths(t[3], p + (3,))

    def _get(self, t, p):
        for i in p:
            t = t[i]
        return t

    def _set(self, t, p, new):
        if not p:
            return new
        lst = list(t)
        lst[p[0]] = self._set(t[p[0]], p[1:], new)
        return tuple(lst)

    def _rand_path(self, t):
        ps = list(self._paths(t))
        return ps[int(self.rng.integers(len(ps)))]

    # --- variation
    def mutate(self, ind, other):
        ind = list(ind)
        for _ in range(10):
            r = self.rng.random()
            new = list(ind)
            k = int(self.rng.integers(len(new)))
            if r < 0.30:                                         # subtree mutation
                p = self._rand_path(new[k])
                new[k] = self._set(new[k], p, self.rand_tree(max(0, self.max_depth - len(p))))
            elif r < 0.45 and len(new) < self.max_terms:         # add a term
                new.append(self.rand_term())
            elif r < 0.55 and len(new) > 1:                      # drop a term
                new.pop(k)
            elif r < 0.70:                                       # leaf point mutation
                p = self._rand_path(new[k])
                node = self._get(new[k], p)
                if node[0] == "x":
                    node = (node[0], int(self.rng.integers(2)), int(self.rng.integers(self.nf))) \
                        if self.rng.random() < 0.5 else (node[0], 1 - node[1], node[2])
                elif node[0] in ("u", "b"):
                    ops = UNARY if node[0] == "u" else BINARY
                    node = (node[0], str(self.rng.choice(ops))) + tuple(node[2:])
                else:
                    node = ("c", float(self.rng.choice(CONSTS)))
                new[k] = self._set(new[k], p, node)
            elif r < 0.85:                                       # subtree crossover
                o = other[int(self.rng.integers(len(other)))]
                donor = self._get(o, self._rand_path(o))
                new[k] = self._set(new[k], self._rand_path(new[k]), donor)
            else:                                                # term crossover
                o = other[int(self.rng.integers(len(other)))]
                if len(new) < self.max_terms and self.rng.random() < 0.5:
                    new.append(o)
                else:
                    new[k] = o
            if all(depth(t) <= self.max_depth for t in new):
                return self.canon(new)
        return self.canon(ind)

    def canon(self, ind):
        # deduplicate terms; order-free identity
        out, keys = [], set()
        for t in ind:
            s = to_str(t, self.names)
            if s not in keys:
                keys.add(s)
                out.append(t)
        return tuple(sorted(out, key=lambda t: to_str(t, self.names)))

    # --- fitness
    def score(self, ind):
        key = " || ".join(to_str(t, self.names) for t in ind)
        if key in self.seen:
            return self.seen[key]
        cols_tr, cols_va, kept = [], [], []
        for t in ind:
            c = self.d.term_cols(t, to_str(t, self.names))
            if c is not None:
                cols_tr.append(c[0]); cols_va.append(c[1]); kept.append(t)
        if not kept:
            res = (math.inf, math.inf, 0, key)
        else:
            Xtr, Xva = np.column_stack(cols_tr), np.column_stack(cols_va)
            w = fit_logistic(Xtr, self.d.y_tr, self.d.off_tr, self.lam)
            ova = 0 if self.d.off_va is None else self.d.off_va
            ll = logloss(sigmoid(ova + Xva @ w), self.d.y_va)
            nodes = sum(size(t) for t in kept)
            res = (ll + self.penalty * nodes, ll, nodes, key)
            self.log.append((self.label, key, len(kept), nodes, round(ll, 6), round(res[0], 6)))
        self.seen[key] = res
        return res

    def run(self):
        pop = []
        for i in range(self.P):
            n = 1 + int(self.rng.integers(min(3, self.max_terms)))
            pop.append(self.canon([self.rand_term() for _ in range(n)]))
        hof = {}
        for g in range(self.G + 1):
            scored = sorted(((self.score(ind), ind) for ind in pop), key=lambda x: x[0][0])
            for s, ind in scored[: self.hof_size]:
                if np.isfinite(s[0]):
                    hof[s[3]] = (s, ind)
            if g == self.G:
                break
            nxt = [ind for _, ind in scored[: self.E]]
            while len(nxt) < self.P:
                a = self._tournament(scored)
                b = self._tournament(scored)
                nxt.append(self.mutate(a, b))
            pop = nxt
        best = sorted(hof.values(), key=lambda x: x[0][0])[: self.hof_size]
        return best

    def _tournament(self, scored):
        idx = self.rng.integers(len(scored), size=self.T)
        return scored[int(min(idx))][1]          # scored is sorted, so min index = fittest
