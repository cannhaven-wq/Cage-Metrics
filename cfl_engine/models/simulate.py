"""Monte-Carlo fight simulator: the output layer on top of the duration hazard
model (models/duration.py) and the count models (models/counts.py).

For each of N sims we (1) draw the ending round from the duration model's
fight-level distribution [P(end R1), P(end R2), P(end R3), P(decision)], then
(2) within every round actually fought, draw both fighters' significant strikes
(NB2) and takedowns (hurdle) conditioned on the round number and that round's
minutes, and accumulate fight totals. The finishing round gets partial minutes
(Uniform(0,5]); full rounds are 5:00.

The simulator is deliberately agnostic about where the round probabilities come
from -- the harness computes them with the gated DurationHazardModel and passes
them in via the context, so the two stay decoupled and the duration model remains
the single duration authority.

Because a fighter's per-minute rate is constant within a fight
(mu = minutes . exp(X.beta)), the whole thing is vectorised over the N sims with
one parameter bundle per (corner, round) -- no per-draw model calls. The N draws
of every leg share randomness, so the returned matrix supports joint slate-level
P&L across multiple legs of one fight; the seed makes any run reproducible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from _mle import sample_nb2, sample_truncnb2

FEATURE_COLS = ["own_sig_off_pm", "opp_sig_def_pm", "own_td_off_pm",
                "opp_td_def_pm", "own_grapp_pm", "opp_grapp_pm", "own_decay"]


def build_context(fight_id, round_probs, a_feats, b_feats, rounds_sched=3):
    """round_probs = [p_end_r1, p_end_r2, p_end_r3, p_decision] from the duration
    model; a_feats/b_feats = per-corner count-covariate dicts (FEATURE_COLS)."""
    return dict(fight_id=fight_id, rounds_sched=int(rounds_sched),
                round_probs=np.asarray(round_probs, float),
                a_feats=a_feats, b_feats=b_feats)


def context_from_panel(panel, fight_id, round_probs):
    """Pull the per-corner count covariates for a fight already in the panel."""
    p = panel[panel.fight_id == fight_id]
    a = p[p.corner == "a"].iloc[0]; b = p[p.corner == "b"].iloc[0]
    return build_context(fight_id, round_probs,
                         {c: float(a[c]) for c in FEATURE_COLS},
                         {c: float(b[c]) for c in FEATURE_COLS},
                         int(a["rounds_sched"]))


def _corner_frame(feats, R):
    d = {c: np.full(R, feats[c]) for c in FEATURE_COLS}
    d["round_number"] = np.arange(1, R + 1)
    d["round_minutes"] = np.ones(R)
    return pd.DataFrame(d)


class SimResult:
    """Holds N aligned draws for one fight and answers line queries."""

    METRICS = ("a_sig", "b_sig", "a_td", "b_td", "total_sig", "total_td", "end_round")

    def __init__(self, fight_id, draws, seed, rounds_sched):
        self.fight_id = fight_id
        self.draws = draws
        self.seed = seed
        self.rounds_sched = rounds_sched
        self.n = len(draws["end_round"])

    def p_gtd(self):
        return float((self.draws["finished"] == 0).mean())

    def finish_rate(self):
        return float((self.draws["finished"] == 1).mean())

    def round_distribution(self):
        er = self.draws["end_round"]
        return {int(r): float((er == r).mean()) for r in range(1, self.rounds_sched + 1)}

    def summary(self, name):
        a = self.draws[name]
        q = np.percentile(a, [5, 25, 50, 75, 95])
        return dict(mean=float(a.mean()), sd=float(a.std()),
                    p5=q[0], p25=q[1], p50=q[2], p75=q[3], p95=q[4])

    def line(self, name, value):
        """P(over), P(under), P(push) for a posted line on a metric."""
        a = self.draws[name].astype(float)
        return dict(over=float((a > value).mean()),
                    under=float((a < value).mean()),
                    push=float((a == value).mean()))

    def matrix(self, names=None):
        names = names or list(self.METRICS)
        return np.column_stack([self.draws[n] for n in names]), names

    def save(self, path):
        np.savez_compressed(path, seed=self.seed, fight_id=self.fight_id,
                            rounds_sched=self.rounds_sched, **self.draws)


class FightSimulator:
    def __init__(self, sig_model, td_model):
        self.sig = sig_model
        self.td = td_model

    def simulate(self, ctx, n=10000, seed=0):
        rng = np.random.default_rng(seed)
        R = max(1, min(int(ctx["rounds_sched"]), 3))    # duration model is 3-round
        probs = ctx["round_probs"].astype(float)
        probs = probs / probs.sum()

        af, bf = _corner_frame(ctx["a_feats"], R), _corner_frame(ctx["b_feats"], R)
        a_sig_mm, sig_r = self.sig.mu_per_min(af)
        b_sig_mm, _ = self.sig.mu_per_min(bf)
        a_s1a, td_b = self.td.stage1_ab(af)
        b_s1a, _ = self.td.stage1_ab(bf)
        a_td_mm, td_r = self.td.stage2_mu_per_min(af)
        b_td_mm, _ = self.td.stage2_mu_per_min(bf)

        # draw ending round: categories 0,1,2 = finish in R1/R2/R3; 3 = decision
        cat = rng.choice(len(probs), size=n, p=probs)
        finished = cat < R
        end_round = np.where(finished, cat + 1, R)

        tot = {k: np.zeros(n, np.int64) for k in ("a_sig", "b_sig", "a_td", "b_td")}
        for ri in range(1, R + 1):
            fought = end_round >= ri
            is_finish_round = finished & (end_round == ri)
            rmin = np.where(fought, 5.0, 0.0)
            rmin[is_finish_round] = rng.uniform(0.05, 5.0, is_finish_round.sum())
            self._accumulate(rng, tot, "a_sig", "a_td", rmin, fought,
                             a_sig_mm[ri - 1], sig_r, a_s1a[ri - 1], td_b,
                             a_td_mm[ri - 1], td_r)
            self._accumulate(rng, tot, "b_sig", "b_td", rmin, fought,
                             b_sig_mm[ri - 1], sig_r, b_s1a[ri - 1], td_b,
                             b_td_mm[ri - 1], td_r)

        draws = dict(**tot, end_round=end_round, finished=finished.astype(int))
        draws["total_sig"] = draws["a_sig"] + draws["b_sig"]
        draws["total_td"] = draws["a_td"] + draws["b_td"]
        return SimResult(ctx["fight_id"], draws, seed, R)

    @staticmethod
    def _accumulate(rng, tot, sig_key, td_key, rmin, fought,
                    sig_mm, sig_r, s1a, td_b, td_mm, td_r):
        rmin_pos = np.maximum(rmin, 1e-6)
        mu_sig = rmin * sig_mm
        tot[sig_key] += np.where(fought, sample_nb2(rng, mu_sig, sig_r), 0)
        logit = s1a + td_b * np.log(rmin_pos)
        p_any = 1.0 / (1.0 + np.exp(-logit))
        any_td = fought & (rng.random(len(rmin)) < p_any)
        mu_td = rmin * td_mm
        tot[td_key] += np.where(any_td, sample_truncnb2(rng, mu_td, td_r), 0)
