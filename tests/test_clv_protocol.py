"""Tripwire: the CLV protocol's gates must hold, and its two copies must agree.

    python -m unittest tests/test_clv_protocol.py -v

CLV is the number that separates a real model from a good-looking replay of
history, which makes it the number most worth publishing early and least safe to
publish early. Reed's rule is that raw quotes capture immediately but no CLV
figure reaches a surface until the protocol is frozen.

That rule is only worth anything if something enforces it, so:

  * while the protocol is not frozen, the publication gate must be shut, and the
    protocol must not claim a freeze it has not had;
  * capture must stay open — a protocol that accidentally blocks collection
    loses data that cannot be recovered;
  * `results_computed_before_freeze` must be false, the same discipline as
    `motivated_by_observed_results` in the research registry;
  * the markdown and the JSON mirror must not drift, because the drifting copy
    would be the one nobody reads.

What this cannot check is whether a human looked at the data and then chose a
definition. That is what the §9 disclosure is for.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
CLV = REPO / "research" / "clv"
PROTOCOL_MD = CLV / "CLV_MEASUREMENT_PROTOCOL.md"
PROTOCOL_JSON = CLV / "protocol.json"

STATUSES = ("draft", "under-review", "frozen")
LEVELS = {"L0", "L1", "L2", "L3"}

# | Q-01 | what "closing line" means | L2 |   (level may be bolded)
# The §8 row is `| Q-nn | question | level |`, optionally followed by one more
# cell carrying review status. The trailing cell is tolerated but NOT captured:
# the level group stays anchored to the third column, so a row that loses its
# level or gains a column in the wrong place still fails to parse rather than
# being silently skipped — a skipped row is invisible to the agreement check.
Q_ROW = re.compile(
    r"^\|\s*(Q-\d{2})\s*\|\s*(.+?)\s*\|\s*\*{0,2}(L[0-3])\*{0,2}\s*\|(?:[^|]*\|)?\s*$")
# ### R-01 — Raw capture is immediate...
R_HEAD = re.compile(r"^###\s+(R-\d{2})\s")


def doc() -> dict:
    return json.loads(PROTOCOL_JSON.read_text(encoding="utf-8"))


def markdown() -> str:
    return PROTOCOL_MD.read_text(encoding="utf-8")


def md_questions() -> dict[str, str]:
    """{Q-id: level} from the §8 summary table."""
    return {m.group(1): m.group(3)
            for line in markdown().splitlines() if (m := Q_ROW.match(line))}


class TestFilesExist(unittest.TestCase):
    def test_protocol_markdown_exists(self):
        self.assertTrue(PROTOCOL_MD.is_file(), f"missing {PROTOCOL_MD}")

    def test_protocol_json_exists_and_parses(self):
        self.assertTrue(PROTOCOL_JSON.is_file(), f"missing {PROTOCOL_JSON}")
        self.assertEqual(doc()["protocol_id"], "CLV-001")


class TestGates(unittest.TestCase):
    """The load-bearing checks."""

    def test_status_is_known(self):
        self.assertIn(doc()["status"], STATUSES)

    def test_publication_is_blocked_until_frozen(self):
        d = doc()
        if d["status"] == "frozen":
            self.skipTest("protocol is frozen; publication gate legitimately open")
        self.assertIs(
            d["publication_gate"]["publication_allowed"], False,
            "\n\nThe CLV protocol is not frozen but its publication gate is open.\n"
            "No CLV figure may reach a page, post, email or digest until the "
            "protocol is frozen — see research/clv/CLV_MEASUREMENT_PROTOCOL.md "
            "R-10 and coordination/DECISIONS.md D-003.\n",
        )

    def test_capture_is_never_blocked(self):
        """The one gate that must stay open. A quote not captured today cannot be
        captured later, and several definitions in §3 depend on fields that can
        only be collected prospectively."""
        self.assertIs(
            doc()["capture_gate"]["capture_allowed"], True,
            "raw quote capture must remain allowed — unlike publication, "
            "collection cannot be caught up afterwards",
        )

    def test_an_unfrozen_protocol_claims_no_freeze(self):
        d = doc()
        if d["status"] == "frozen":
            self.skipTest("protocol is frozen")
        for field in ("frozen_at", "frozen_by", "protocol_sha256"):
            with self.subTest(field=field):
                self.assertIsNone(
                    d[field],
                    f"status is {d['status']!r} but {field} is set — a draft that "
                    f"records a freeze reads as binding when it is not",
                )

    def test_a_frozen_protocol_records_its_freeze_and_matches_disk(self):
        d = doc()
        if d["status"] != "frozen":
            self.skipTest("protocol is not frozen yet")
        self.assertIsNotNone(d["frozen_at"])
        self.assertIsNotNone(d["frozen_by"])
        actual = hashlib.sha256(PROTOCOL_MD.read_bytes()).hexdigest()
        self.assertEqual(
            d["protocol_sha256"], actual,
            "\n\nThe frozen CLV protocol no longer matches its recorded hash.\n"
            "Do not update the hash to make this pass. Either a dated amendment "
            "or a new protocol version — see §5.\n",
        )

    def test_no_results_were_computed_before_freeze(self):
        """Mirrors motivated_by_observed_results in the research registry: recorded
        false, and required to actually be false."""
        self.assertIs(doc()["results_computed_before_freeze"], False)

    def test_markdown_status_banner_agrees_with_json(self):
        d = doc()
        if d["status"] != "draft":
            self.skipTest("banner check is written for the draft state")
        self.assertIn(
            "Status: DRAFT", markdown(),
            "protocol.json says draft but the markdown does not say so at the top, "
            "where a reader would see it",
        )


class TestOpenQuestions(unittest.TestCase):
    def test_there_are_open_questions_to_check(self):
        self.assertGreater(len(doc()["open_questions"]), 0)

    def test_every_question_is_well_formed(self):
        for q in doc()["open_questions"]:
            with self.subTest(question=q.get("id")):
                self.assertRegex(q["id"], r"^Q-\d{2}$")
                self.assertIn(q["level"], LEVELS)
                self.assertTrue(q["question"].strip())
                self.assertGreaterEqual(
                    len(q.get("options") or []), 2,
                    "an 'open question' with fewer than two options is a decided "
                    "rule wearing the wrong label",
                )
                self.assertTrue(q.get("recommendation", "").strip())

    def test_no_question_was_chosen_by_historical_comparison(self):
        """Reed: do not calculate historical 'best' definitions to choose among
        alternatives. Recorded per question, and required to be false."""
        for q in doc()["open_questions"]:
            with self.subTest(question=q["id"]):
                self.assertIs(
                    q["chosen_by_historical_comparison"], False,
                    f"{q['id']} records being chosen by historical comparison. "
                    f"A definition picked because it scored better is not a "
                    f"preregistered definition.",
                )

    def test_question_ids_are_unique(self):
        ids = [q["id"] for q in doc()["open_questions"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate question ids in {ids}")

    def test_json_and_markdown_list_the_same_questions(self):
        """The registry-agreement pattern: two hand-maintained copies drift, and
        the drifting one is always the copy nobody reads."""
        js = {q["id"]: q["level"] for q in doc()["open_questions"]}
        md = md_questions()
        self.assertEqual(
            set(js), set(md),
            f"§8 summary table and protocol.json disagree on which questions "
            f"exist: only in JSON {sorted(set(js) - set(md))}, only in markdown "
            f"{sorted(set(md) - set(js))}",
        )
        for qid in sorted(js):
            with self.subTest(question=qid):
                self.assertEqual(
                    js[qid], md[qid],
                    f"{qid} is {js[qid]} in protocol.json but {md[qid]} in the "
                    f"markdown summary table",
                )

    def test_an_l3_question_says_why(self):
        """L3 is escalation to Reed. If a question claims it without a reason, it
        is either mislabelled or padding the owner's queue."""
        for q in doc()["open_questions"]:
            if q["level"] != "L3":
                continue
            with self.subTest(question=q["id"]):
                self.assertTrue(
                    (q.get("why_l3") or "").strip(),
                    f"{q['id']} is L3 but records no why_l3",
                )


class TestDecidedRules(unittest.TestCase):
    def test_every_decided_rule_is_well_formed(self):
        for r in doc()["decided_rules"]:
            with self.subTest(rule=r.get("id")):
                self.assertRegex(r["id"], r"^R-\d{2}$")
                self.assertTrue(r["title"].strip())
                self.assertTrue(
                    r.get("basis", "").strip(),
                    "a decided rule with no basis is an undocumented choice",
                )

    def test_rule_ids_are_unique(self):
        ids = [r["id"] for r in doc()["decided_rules"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate rule ids in {ids}")

    def test_every_json_rule_appears_in_the_markdown(self):
        body = markdown()
        headed = {m.group(1) for line in body.splitlines() if (m := R_HEAD.match(line))}
        for r in doc()["decided_rules"]:
            with self.subTest(rule=r["id"]):
                self.assertIn(
                    r["id"], headed,
                    f"{r['id']} is in protocol.json but has no §2 section in the "
                    f"markdown",
                )

    def test_the_publication_and_firewall_rules_are_present(self):
        """These two are the ones Reed's instruction rests on. Losing either to a
        tidy-up would remove the gate without removing the appearance of one."""
        ids = {r["id"] for r in doc()["decided_rules"]}
        for rid in ("R-09", "R-10"):
            with self.subTest(rule=rid):
                self.assertIn(rid, ids)


class TestCaptureRequirements(unittest.TestCase):
    def test_backfill_impossible_requirements_are_listed(self):
        """§4's whole point: an omission here is the only error in the document
        that cannot be fixed later."""
        reqs = doc()["capture_requirements_that_cannot_be_backfilled"]
        self.assertGreater(len(reqs), 0)
        joined = " ".join(reqs).lower()
        self.assertIn(
            "both sides", joined,
            "two-sided capture at the publish instant is what makes the de-vigged "
            "variant in Q-05 possible at all; it cannot be backfilled and must "
            "stay on this list",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestReviewCoverage(unittest.TestCase):
    """The audit of what the external review actually answered.

    A review that comes back short is normal. A review recorded as if it had
    answered everything is not, and the failure mode is silent: a question with
    no resolution and no flag reads exactly like a question nobody has got to
    yet. These tests keep the audit honest against the questions themselves.
    """

    def _audit(self):
        return doc().get("review_coverage_audit") or {}

    def test_audit_exists(self):
        self.assertTrue(self._audit(), "protocol.json records no review_coverage_audit")

    def test_outstanding_questions_are_still_open(self):
        """Anything the audit lists as unaddressed must not be marked resolved."""
        audit = self._audit()
        outstanding = set(audit.get("l2_outstanding", []) + audit.get("l3_outstanding", []))
        for q in doc()["open_questions"]:
            if q["id"] not in outstanding:
                continue
            with self.subTest(question=q["id"]):
                self.assertEqual(
                    q.get("status"), "open",
                    f"{q['id']} is listed as unaddressed by the review but is marked "
                    f"{q.get('status')!r}",
                )

    def test_outstanding_questions_say_so_on_themselves(self):
        """The flag lives on the question too, not only in the summary — whoever
        reads a single question must see that silence was not agreement."""
        audit = self._audit()
        for qid in audit.get("l2_outstanding", []) + audit.get("l3_outstanding", []):
            q = next(x for x in doc()["open_questions"] if x["id"] == qid)
            with self.subTest(question=qid):
                self.assertIn(
                    "NOT ADDRESSED", (q.get("review_coverage") or "").upper(),
                    f"{qid} is outstanding in the audit but carries no "
                    f"review_coverage note",
                )

    def test_audit_counts_match_the_questions(self):
        audit = self._audit()
        levels = {}
        for q in doc()["open_questions"]:
            levels.setdefault(q["level"], []).append(q["id"])
        # questions raised BY the revision were never part of the review's remit
        raised_later = {q["id"] for q in doc()["open_questions"] if q.get("raised_by")}
        for lvl, asked_key, out_key in (("L2", "l2_asked", "l2_outstanding"),
                                        ("L3", "l3_asked", "l3_outstanding")):
            with self.subTest(level=lvl):
                in_remit = [i for i in levels.get(lvl, []) if i not in raised_later]
                self.assertEqual(
                    audit.get(asked_key), len(in_remit),
                    f"audit says {audit.get(asked_key)} {lvl} questions were asked, "
                    f"but {len(in_remit)} were in the review's remit: {in_remit}",
                )
                self.assertTrue(set(audit.get(out_key, [])) <= set(in_remit))

    def test_a_resolved_question_names_who_resolved_it(self):
        for q in doc()["open_questions"]:
            if q.get("status") != "resolved":
                continue
            with self.subTest(question=q["id"]):
                self.assertTrue((q.get("resolution") or "").strip(),
                                f"{q['id']} is resolved but records no resolution")
                self.assertTrue((q.get("resolved_by") or "").strip(),
                                f"{q['id']} is resolved but records no resolver")


class TestPrimaryDefinition(unittest.TestCase):
    """The headline measure. A protocol whose primary number is implicit is a
    protocol that will acquire one by accident."""

    def _pd(self):
        return doc().get("primary_definition") or {}

    def test_primary_definition_exists_and_is_not_frozen(self):
        pd = self._pd()
        self.assertTrue(pd.get("formula", "").strip())
        self.assertIn("proposed", pd.get("status", ""),
                      "the primary definition must not claim frozen status while the "
                      "protocol is a draft")

    def test_the_two_sides_are_treated_differently_and_say_so(self):
        """Vigged at publish, de-vigged at close. If this ever collapses into one
        treatment the measure silently changes meaning."""
        pd = self._pd()
        self.assertIn("posted", pd.get("publish_side", "").lower())
        self.assertIn("de-vig", pd.get("closing_side", "").lower())

    def test_the_conservative_asymmetry_is_recorded(self):
        self.assertTrue((self._pd().get("conservative_by_construction") or "").strip(),
                        "the vigged-publish asymmetry must be stated, or the figure "
                        "will eventually be described as fair-versus-fair")

    def test_blocking_dependency_is_named(self):
        self.assertIn("close", (self._pd().get("blocking_dependency") or "").lower())


class TestStalenessRule(unittest.TestCase):
    """Q-01's limit is a number or it is nothing.

    "Subject to a staleness limit set from capture cadence" is not a rule — it is
    a promise to write one. The number has to exist, and it has to be on record
    as fixed before any CLV result was looked at.
    """

    def _q01(self):
        return next(q for q in doc()["open_questions"] if q["id"] == "Q-01")

    def test_the_limit_is_numeric(self):
        sr = self._q01().get("staleness_rule") or {}
        self.assertIsInstance(sr.get("limit_minutes"), (int, float),
                              "Q-01 resolves to a scheduled-close proxy 'subject to a "
                              "staleness limit'; the limit must be a number")
        self.assertGreater(sr["limit_minutes"], 0)

    def test_the_limit_records_its_derivation_and_its_measurement(self):
        sr = self._q01().get("staleness_rule") or {}
        self.assertTrue((sr.get("derivation") or "").strip())
        self.assertTrue((sr.get("measured_from") or "").strip(),
                        "a limit derived from cadence must say which stream it was "
                        "measured on")

    def test_the_limit_was_fixed_before_results(self):
        self.assertIs(self._q01().get("staleness_rule", {}).get("fixed_before_results"),
                      True)

    def test_the_bimodal_caveat_is_recorded(self):
        """The measured gap distribution is bimodal — ~30 min near a card, ~24 h
        between them. A limit taken from the overall distribution would be ~24
        hours and useless, so the caveat has to travel with the number."""
        self.assertTrue(
            (self._q01().get("staleness_rule", {}).get("caveat_bimodal") or "").strip(),
            "the cadence is bimodal; without that recorded, the next person to "
            "re-derive this limit gets a number an order of magnitude too large",
        )


class TestBlockingRelationships(unittest.TestCase):
    """A question that cannot be decided before another must say so, on both ends."""

    def test_a_blocker_points_at_a_real_question(self):
        ids = {q["id"] for q in doc()["open_questions"]}
        for q in doc()["open_questions"]:
            target = q.get("blocks")
            if not target or not target.startswith("Q-"):
                continue
            with self.subTest(question=q["id"]):
                self.assertIn(target.split()[0], ids,
                              f"{q['id']} blocks {target!r}, which does not exist")

    def test_a_blocked_question_names_its_blocker(self):
        blocks = {q["blocks"].split()[0]: q["id"] for q in doc()["open_questions"]
                  if (q.get("blocks") or "").startswith("Q-")}
        for blocked, blocker in blocks.items():
            q = next(x for x in doc()["open_questions"] if x["id"] == blocked)
            with self.subTest(question=blocked):
                self.assertIn(
                    blocker, (q.get("blocked_by") or ""),
                    f"{blocker} blocks {blocked} but {blocked} does not record it. "
                    f"A one-way blocking relationship is invisible from the side "
                    f"that has to wait.",
                )

    def test_a_blocked_question_is_not_marked_resolved(self):
        for q in doc()["open_questions"]:
            if not (q.get("blocked_by") or ""):
                continue
            with self.subTest(question=q["id"]):
                self.assertEqual(q.get("status"), "open",
                                 f"{q['id']} is blocked by {q['blocked_by']} but is "
                                 f"marked {q.get('status')!r}")


class TestSentinelTimestampRule(unittest.TestCase):
    """R-13. R-02 excludes a MISSING timestamp; a populated fake one passes it."""

    def _r13(self):
        return next((r for r in doc()["decided_rules"] if r["id"] == "R-13"), None)

    def test_r13_exists(self):
        self.assertIsNotNone(self._r13(),
                             "R-13 is what stops an epoch-dated quote from being "
                             "treated as a real pre-fight observation")

    def test_r13_records_the_measurement_behind_it(self):
        basis = (self._r13() or {}).get("basis", "")
        self.assertIn("1970", basis,
                      "R-13 exists because of a measured sentinel population; the "
                      "measurement belongs in the rule, not in a commit message")

    def test_r13_excludes_rather_than_deletes(self):
        """R-01 makes the store append-only. A cleanup rule that deletes would
        contradict it."""
        text = json.dumps(self._r13() or {}).lower()
        self.assertIn("never deleted", text)
