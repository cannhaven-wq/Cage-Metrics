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


class TestPublicationGateAfterFreeze(unittest.TestCase):
    """The gate that matters once the protocol IS frozen.

    Three of the original gate tests skip in the frozen state — they were written
    to police the run-up to a freeze. Without these, freezing would silently
    remove every check on publication at the exact moment publication becomes
    conceivable.

    Reed, approving the freeze: "do not publish the first CLV number immediately
    after freeze." Freezing settled how the number is measured. It did not create
    a number worth showing.
    """

    def _gate(self):
        return doc()["publication_gate"]

    def test_publication_allowed_is_the_and_of_its_conditions(self):
        """The headline boolean must be derivable, not asserted. If it can drift
        from the conditions, it is decoration."""
        g = self._gate()
        conds = g.get("conditions") or {}
        self.assertTrue(conds, "the publication gate records no conditions")
        self.assertEqual(
            g["publication_allowed"], all(conds.values()),
            f"publication_allowed is {g['publication_allowed']} but the conditions "
            f"are {conds}. The flag must be the AND of them.",
        )

    def test_every_unmet_condition_is_listed_in_blocked_by(self):
        g = self._gate()
        unmet = {k for k, v in (g.get("conditions") or {}).items() if not v}
        self.assertEqual(
            unmet, set(g.get("blocked_by") or []),
            "blocked_by must name exactly the conditions that are false, so a "
            "reader is never left to diff two structures by eye",
        )

    def test_publication_is_shut_while_the_sample_floor_is_unmet(self):
        """The check that survives the freeze."""
        g = self._gate()
        floor = g.get("sample_floor") or {}
        obs, ev = floor.get("scored_observations_current"), floor.get("distinct_events_current")
        need_obs, need_ev = floor.get("scored_observations_required"), floor.get("distinct_events_required")
        for name, cur, need in (("observations", obs, need_obs), ("events", ev, need_ev)):
            self.assertIsNotNone(cur, f"the {name} counter is not recorded")
            self.assertIsNotNone(need, f"the {name} requirement is not recorded")
        if obs < need_obs or ev < need_ev:
            self.assertFalse(
                g["publication_allowed"],
                f"\n\nCLV publication is ALLOWED at {obs}/{need_obs} observations and "
                f"{ev}/{need_ev} events.\nThe floor is not advisory — see Q-08 and "
                f"Q-13, both approved 2026-09-16.\n",
            )
            self.assertIs(g["conditions"].get("sample_floor_met"), False)

    def test_the_sample_floor_matches_the_approved_numbers(self):
        """100 and 20 were approved explicitly. Silently lowering either would be
        the cheapest possible way to publish early."""
        floor = self._gate().get("sample_floor") or {}
        self.assertEqual(floor.get("scored_observations_required"), 100)
        self.assertEqual(floor.get("distinct_events_required"), 20)
        self.assertIs(floor.get("applies_to_breakouts"), True,
                      "Q-08: the same thresholds apply to any breakout shown as a finding")

    def test_the_freeze_procedure_states_that_publication_does_not_open(self):
        """The original procedure said publication_allowed becomes true at freeze.
        Following it literally would have published on a sample of zero.

        Asserted positively rather than as a forbidden substring: the procedure
        now *quotes* the old wrong rule in order to retract it, and a negative
        substring check cannot tell an instruction from a correction. Requiring
        the explicit denial is both stricter and not fooled by its own footnote.
        """
        text = " ".join(doc().get("freeze_procedure") or []).lower()
        self.assertIn(
            "publication_allowed does not", text,
            "the freeze procedure must say outright that publication does NOT open "
            "on freeze — it is the step most likely to be followed mechanically",
        )
        self.assertIn("sample floor", text)

    def test_a_frozen_protocol_says_so_where_a_reader_looks(self):
        """Replaces the draft-banner check, which skips once frozen."""
        d = doc()
        if d["status"] != "frozen":
            self.skipTest("protocol is not frozen")
        md = markdown()
        self.assertIn("Status: FROZEN", md)
        self.assertIn("Frozen is not publishable", md,
                      "the banner must say that freezing did not open publication — "
                      "that is the single most misreadable fact about this document")

    def test_every_question_is_resolved_in_a_frozen_protocol(self):
        d = doc()
        if d["status"] != "frozen":
            self.skipTest("protocol is not frozen")
        unresolved = [q["id"] for q in d["open_questions"] if q.get("status") != "resolved"]
        self.assertEqual(unresolved, [],
                         f"the protocol is frozen but {unresolved} are still open")

    def test_every_l3_resolution_names_its_approver(self):
        d = doc()
        if d["status"] != "frozen":
            self.skipTest("protocol is not frozen")
        for q in d["open_questions"]:
            if q["level"] != "L3":
                continue
            with self.subTest(question=q["id"]):
                self.assertTrue((q.get("resolved_by") or "").strip(),
                                f"{q['id']} is L3 and resolved but names no approver")


class TestActiveDocumentationIsNotStale(unittest.TestCase):
    """Amendment 6 (i) and the rest of item 9.

    The amendment blocks are HISTORY and stay exactly as filed — a superseded
    rule deleted is a rule you cannot audit. Everything OUTSIDE them is live
    text, and live text that contradicts the current version is worse than no
    text, because a reader reasonably trusts it.

    These tests read the live sections only.
    """

    def _live_text(self) -> str:
        """The markdown with every amendment blockquote removed.

        Amendments are written as `> ` blockquotes under Q-01; stripping every
        quoted line leaves the live rule text. Crude and reliable — and it fails
        loudly if the amendment style ever changes, because the live text would
        suddenly include amendment prose and these assertions would trip.
        """
        return "\n".join(line for line in markdown().splitlines()
                         if not line.lstrip().startswith(">"))

    def test_section_5_does_not_say_freezing_opens_the_gate(self):
        """The one sentence in this document that could be read as authorising
        a number to appear."""
        live = self._live_text()
        section = live[live.index("## 5. What freezing means"):
                       live.index("## 6. What this protocol does not cover")]
        # The numbered list is the rule. The prose below it is the dated
        # correction, which QUOTES the removed sentence in order to record what
        # changed — the repo's convention for an audit narrative (edges.html's
        # "Updated August 2026" note), so it is read past deliberately.
        steps = [ln for ln in section.splitlines()
                 if re.match(r"^\d+\.\s", ln.strip()) or ln.startswith("   ")]
        self.assertTrue(steps, "§5's numbered procedure is gone")
        joined = " ".join(steps)
        self.assertNotIn("publication_allowed", joined,
                         "freezing does not set the publication flag, and §5's "
                         "procedure must not list it among the things it does")
        self.assertIn("Freezing does not open the publication gate", section)
        self.assertIn("100 scored observations", section)
        self.assertIn("Corrected by Amendment 6 (i)", section,
                      "the removal is recorded as a dated correction rather "
                      "than a silent rewrite")

    def test_the_freeze_procedure_in_json_agrees(self):
        steps = " ".join(doc()["freeze_procedure"]).lower()
        self.assertIn("publication_allowed does not", steps)

    def test_no_live_text_says_a_bell_can_supply_the_cutoff(self):
        """v1.0.8 onward has exactly two cutoff bases and a bell is neither.
        Superseded amendment text may still say otherwise; live text may not."""
        live = self._live_text().lower()
        for phrase in ("actual bell, previous bout",
                       "a confirmed bell outranks",
                       "wherever one exists",
                       "bell_at` (any bout)"):
            self.assertNotIn(phrase, live,
                             f"live rule text still admits a bell as a cutoff: "
                             f"{phrase!r}")

    def test_the_machine_mirror_marks_the_bell_audit_only(self):
        self.assertTrue(doc()["close_reference"].get("bell_at_is_audit_only"))
        bases = {t["basis"] for t in doc()["close_reference"]["tiers"]}
        self.assertEqual(bases, {"scheduled_first_bout", "previous_bout_completion"})


class TestScorerTextIsNotStale(unittest.TestCase):
    """Item 9's third bullet. The scorer's own messages are user-facing too —
    they are what a dry run prints and what a reader of an unscored row sees."""

    def _scoring_source(self) -> str:
        return (REPO / "cfl_engine" / "clv" / "scoring.py").read_text(encoding="utf-8")

    def test_no_error_message_offers_a_confirmed_bell_as_a_cutoff(self):
        src = self._scoring_source()
        self.assertNotIn("or a confirmed bell (Amendments 3, 5)", src)
        self.assertIn("A confirmed bell is audit-only and cannot supply one", src)

    def test_the_capture_migration_comments_name_the_two_bases(self):
        sql = (REPO / "research" / "clv" /
               "proposed_2026-09-16_fight_odds_capture.sql").read_text(encoding="utf-8")
        # The Amendment 2 (b) era rule, which admitted bell_at and
        # provider_commence as "start bases", is gone from the live comments.
        self.assertNotIn("Amendment 2 (b) admits", sql)
        self.assertNotIn("bell_at and provider_commence bases", sql)
        self.assertIn("exactly two cutoff bases", sql)
        self.assertIn("proxy_cutoff_at", sql)

    def test_the_staleness_clock_is_documented_where_the_column_lives(self):
        sql = (REPO / "research" / "clv" /
               "proposed_2026-09-16_fight_odds_capture.sql").read_text(encoding="utf-8")
        self.assertIn("NOT the staleness clock", sql)
        self.assertIn("measured from captured_at", sql)


class TestAmendmentApprovalIsNotClaimed(unittest.TestCase):
    """An amendment that has been WRITTEN is not one that has been APPROVED.

    Recording an approval the owner did not give is the single failure the hash
    chain, the two-route rule and the whole L3 ladder exist to prevent: a
    protocol nobody agreed to, wearing the marks of one they did. It is also the
    easiest mistake to make in good faith, because writing the amendment and
    believing it is correct feel like the same act as it being ratified.
    """

    def amendments(self):
        return doc()["amendments"]

    def test_an_amendment_either_names_an_approver_or_says_it_is_proposed(self):
        for a in self.amendments():
            with self.subTest(amendment=a["number"]):
                if a.get("approved_by"):
                    self.assertIsInstance(a["approved_by"], str)
                    self.assertTrue(a["approved_by"].strip())
                else:
                    self.assertIn("approval_status", a,
                                  "an amendment with no approver must say so "
                                  "explicitly, not leave the field blank")
                    self.assertIn("PROPOSED", a["approval_status"])

    def test_the_version_matches_the_last_amendment_either_way(self):
        """A proposed amendment still chains — what is pending is the approval,
        not the bookkeeping."""
        last = self.amendments()[-1]
        self.assertEqual(last["version_after"], doc()["version"])
        self.assertEqual(last["sha256_after"], doc()["protocol_sha256"])

    def test_a_pending_amendment_is_not_recorded_as_the_ratified_version(self):
        pending = [a for a in self.amendments() if not a.get("approved_by")]
        if not pending:
            return
        self.assertIn("last_ratified_version", doc(),
                      "with an amendment pending, the document must say which "
                      "version actually carries approval")
        ratified = doc()["last_ratified_version"]
        self.assertNotEqual(ratified, doc()["version"])
        self.assertEqual(ratified, pending[0]["version_before"],
                         "the last ratified version is the one before the first "
                         "pending amendment")
        self.assertIn("PROPOSED", doc().get("version_status", ""))

    def test_the_markdown_marks_a_pending_amendment_at_its_top(self):
        pending = [a for a in self.amendments() if not a.get("approved_by")]
        if not pending:
            return
        md = markdown()
        for a in pending:
            head = md.index(f"## AMENDMENT {a['number']}, v{a['version_after']}")
            block = md[head:head + 1200]
            with self.subTest(amendment=a["number"]):
                self.assertIn("PROPOSED", block)
                self.assertIn("NOT APPROVED", block)
                self.assertNotIn("Approved by", block,
                                 "a pending amendment must not carry an "
                                 "approval line anywhere near its heading")

    def test_a_pending_amendment_holds_clv_write_mode_shut(self):
        """Not a note in a handoff — a precondition the writer evaluates.

        Reporting is deliberately unaffected: a dry run against a proposed
        amendment is how the owner sees what they are being asked to approve.
        """
        src = (REPO / "cfl_engine" / "settle_clv.py").read_text(encoding="utf-8")
        self.assertIn('cond["all_amendments_approved"]', src)
        self.assertIn('if not a.get("approved_by")', src)
        # And it is a real blocker: preflight's blockers are every false
        # condition, and blockers force write_allowed false.
        self.assertIn("blockers = [name for name, ok in cond.items() if not ok]",
                      src)
        self.assertIn("write_allowed = write and not blockers", src)

    def test_a_ratified_amendment_records_who_and_when(self):
        """The mirror of the pending case. An approval is only evidence if it
        says who gave it — `approved_by: true` would be a rumour."""
        for a in self.amendments():
            if not a.get("approved_by"):
                continue
            with self.subTest(amendment=a["number"]):
                self.assertRegex(a["date"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(a["approved_by"].strip())
                # `level` arrived with the later amendments; where it is
                # recorded it must say L3, because an amendment is always one.
                if "level" in a:
                    self.assertEqual(a["level"], "L3")
                self.assertIs(a["motivated_by_observed_results"], False)

    def test_amendment_7_records_the_approved_substance_not_just_a_yes(self):
        """The owner approved a RULE, not a commit. What was approved has to be
        recoverable from the record, or a later reader has an approval attached
        to whatever the code happens to do now."""
        a7 = next(a for a in self.amendments() if a["number"] == "7")
        self.assertTrue(a7.get("approved_by"))
        substance = a7.get("approved_substance", "")
        self.assertIn("permanent", substance)
        self.assertIn("never overwrite", substance.replace("overwritten", "overwrite"))
        self.assertIn("superseding", substance)
        self.assertIn("superseding_mechanism", a7,
                      "the deferral of the correction-ledger design is part of "
                      "what was approved and must be on the record")

    def test_the_write_mode_gate_survives_ratification(self):
        """The condition is not deleted once it stops firing. It governs the
        NEXT unratified amendment, and a gate removed the moment it first goes
        green was never a gate."""
        src = (REPO / "cfl_engine" / "settle_clv.py").read_text(encoding="utf-8")
        self.assertIn('cond["all_amendments_approved"]', src)
