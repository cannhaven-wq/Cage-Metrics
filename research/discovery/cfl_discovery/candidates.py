"""The hypothesis catalog: every candidate the engine will test, fixed BEFORE
any candidate is scored.

Kinds
  single       one antisymmetric feature, added to the market.
               Screened against the recalibrated market (is the feature itself
               informative, not just the market's own bias?).
  interaction  feature x context, added on top of that feature's own single
               model. Screened against the PARENT single, so an interaction
               cannot borrow credit from its main effect.
  multi        several features at once, heavier ridge. Descriptive context
               for "how much is there in all of it together"; never screened.
  standalone   no market input at all. Context only: shows the gap a
               stats-only model starts from.
  control      noise features run through exactly the same machinery.
               They are never in the tested family; they measure how often
               the pipeline 'discovers' something that is not there.

The catalog is hashed; the hash goes into the run ledger before results exist.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict

from .features import FeatureSpec


@dataclass
class Candidate:
    cid: str
    kind: str                       # single / interaction / multi / standalone / control
    terms: list                     # antisymmetric feature names entering the model
    interact: list = field(default_factory=list)   # [(anti, ctx)] product terms
    parent: str | None = None       # screening reference for interactions
    family_member: bool = True      # counted in the multiple-testing family
    hypothesis: str = ""            # plain English
    families: list = field(default_factory=list)
    h1_contaminated: bool = False   # uses a feature flagged in features.H1_CONTAMINATED

    def as_dict(self):
        d = asdict(self)
        d["interact"] = [list(p) for p in self.interact]
        return d


def build_catalog(specs: list[FeatureSpec], cfg: dict) -> list[Candidate]:
    by = {s.name: s for s in specs}
    anti = [s.name for s in specs if s.kind == "anti" and s.family != "control"]
    ctrl = [s.name for s in specs if s.kind == "anti" and s.family == "control"]
    ctx = [s.name for s in specs if s.kind == "ctx"]
    out: list[Candidate] = []

    for a in anti:
        out.append(Candidate(f"S:{a}", "single", [a], hypothesis=f"Beyond the closing price, {by[a].plain} "
                             f"helps say who wins.", families=[by[a].family]))
    if cfg.get("interactions", True):
        for a in anti:
            for c in ctx:
                if c in cfg.get("skip_interactions_with", []):
                    continue
                out.append(Candidate(
                    f"I:{a}*{c}", "interaction", [a], interact=[(a, c)], parent=f"S:{a}",
                    hypothesis=f"The effect of {by[a].plain} is different when the bout is "
                               f"{by[c].plain} (beyond the feature's own effect).",
                    families=[by[a].family, by[c].family]))

    groups = {
        "M:engine_all": [a for a in anti if by[a].sources and "(cfl_engine.build_features)" in by[a].sources
                         or a in ("d_age", "d_height_in", "d_reach_in", "d_is_southpaw", "d_is_switch")],
        "M:history_all": [a for a in anti if by[a].family == "history"],
        "M:style_matchup_all": [a for a in anti if by[a].family in ("style", "matchup")],
        "M:physical_all": [a for a in anti if by[a].family == "physical"],
        "M:market_all": [a for a in anti if by[a].family == "market"],
        "M:all_base": list(anti),
    }
    for cid, terms in groups.items():
        if terms:
            out.append(Candidate(cid, "multi", terms, family_member=False,
                                 hypothesis=f"Together, {len(terms)} features add to the closing price.",
                                 families=sorted({by[t].family for t in terms})))
    eng = groups["M:engine_all"]
    out.append(Candidate("X:standalone_engine_features", "standalone", eng, family_member=False,
                         hypothesis="A stats-only model, with no market input, compared with the market "
                                    "(context: the gap any standalone model starts from).",
                         families=["standalone"]))

    for i, n in enumerate(ctrl):
        out.append(Candidate(f"C:{n}", "control", [n], family_member=False,
                             hypothesis="Negative control: random noise. Any 'discovery' here is a false one.",
                             families=["control"]))
        if ctx and cfg.get("interactions", True):
            c = ctx[i % len(ctx)]
            out.append(Candidate(f"CI:{n}*{c}", "control", [n], interact=[(n, c)], parent=f"C:{n}",
                                 family_member=False,
                                 hypothesis="Negative control interaction: noise times a real context.",
                                 families=["control"]))
    return flag_contamination(out, specs)


def flag_contamination(cands: list[Candidate], specs: list[FeatureSpec]) -> list[Candidate]:
    bad = {s.name for s in specs if s.h1_contaminated}
    for c in cands:
        names = set(c.terms) | {x for p in c.interact for x in p}
        c.h1_contaminated = bool(names & bad)
    return cands


def catalog_sha256(cands: list[Candidate]) -> str:
    blob = json.dumps([c.as_dict() for c in cands], sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()
