# PRED-002 — prior exploration to disclose before it is frozen

**2026-10-21. For whoever freezes PRED-002** (draft PR #62,
`claude/nice-bell-ussmhp-pred002`, author `session_01J8Jjgk3pgqKw3xVPHjUbyY`).
PRED-002 stays an approved research direction (D-024, retained by D-034).
This file lists every earlier look at the same ideas, so its
`variants_tried_on_dev`, its contamination section and its expectations can
be written honestly. Nothing in PRED-002 is changed here.

## Plain version

PRED-002 asks whether wrestling, measured against how hard each past
opponent was to wrestle, adds anything to the betting odds. Three earlier
pieces of CFL work already looked at close relatives of that idea, and one of
them — SYM-003, in October — looked at **almost exactly that idea on the
sealed 2025–26 fights**, with results that were never recorded. PRED-002 must
say so before it is frozen, and its draft's claim that a sealed-set result
would be "confirmatory" probably does not survive that.

## 1. Looks at the same idea

| when | work | what was looked at | data | result |
|---|---|---|---|---|
| all-years, ongoing | **Factor Lab** `td_def` (`factor-rates.json`) and `edges.js` `td_def` (FE-001) | plain takedown-defence gap | **all years including H1** | noise on market-even fights (PRED-002's draft already declares this) |
| 2026-10-07 | **SYM-003, group O** (draft PR #53) | six **opponent-adjusted residuals** — takedowns for and against, control for and against, striking for and against — each bout compared with what that opponent normally allowed going into it, two-year half-life, shrunk with 15 pseudo-minutes; plus a wrestling matchup group W (takedown rate × opponent's takedowns conceded, control × control conceded, accuracy × defence failure) | outer folds **2021–2026, including all of H1**; fitted before PRED-002 was drafted | **unknown**: results stayed in a git-ignored folder; the session's commit message says only that SYM-002's plain baseline was "as good as any fancy formula". See [`SYM-002_SYM-003_HISTORY.md`](SYM-002_SYM-003_HISTORY.md) |
| 2026-10-07 | **SYM-002** | raw `td_per15`, `td_acc`, `td_def`, `ctrl_share`, `ctrl_against`, `sub_per15` among 23 inputs | 2021–2026 including H1 | unknown (same reason) |
| 2026-10-21 | **Discovery Engine Phase 1** (ledger entry 1) | raw takedown rate, takedown accuracy, takedown defence, control share, submission attempts, submission losses, and `mu_grapple` (takedown rate × opponent's takedown-defence failure), each alone and in 14 situations: **105 grappling ideas** | DEV only, screen 2010–18, confirm 2019–24 | all 105 rejected at the screen. Best: control share × longer layoff, z 1.73 (also the engine's best idea overall); takedown defence alone was *worse* than the market in 2019–24 (−0.0009, range below zero) |
| 2026-10-21 | DISC-001 | no grappling factor | DEV | — |

Engine numbers for the single factors (gain over the re-weighted market, per
fight; screen 2010–18 / confirm 2019–24): takedown rate +0.0004 / +0.0003;
takedown accuracy −0.0008 / −0.0002; takedown defence +0.0002 / −0.0009;
control share −0.0002 / +0.0006; submission attempts +0.0001 / −0.0005;
`mu_grapple` +0.0001 / −0.0006. None was opponent-adjusted the way PRED-002
proposes.

## 2. What PRED-002 needs to say before freezing

1. **`variants_tried_on_dev`.** The engine's 105 grappling ideas are DEV
   comparisons of grappling measures against the same market, made by CFL
   before PRED-002's configuration is fixed. Whether they count toward
   PRED-002's own count is the freezing session's call; they must at least
   be listed in its disclosure section.
2. **Contamination (PRED-001 §2).** The draft says the features were chosen
   because the plain version failed, "not because any all-years result
   looked good", and so treats an H1 result as confirmatory. That reasoning
   predates knowledge of SYM-003: a CFL session evaluated opponent-adjusted
   takedown and control residuals on every H1 fight on 2026-10-07, and its
   results cannot be shown. Whether that makes PRED-002's H1 result
   non-confirmatory is a judgement for the Independent Auditor (and, if
   disputed, the owner, L3 item 10). **This file recommends recording it as
   non-confirmatory**: the protocol already makes the prospective test the one
   that decides, so this costs nothing but a label.
3. **The de-vig head start.** Against the proportional-de-vig BFO close, a
   blend that only re-weights the market gains about +0.001 (2012–24) to
   +0.002 (2019–24) by itself (consolidation audit §4.1). PRED-002's target
   is 0.006. Its DEV report should show the "re-weighted market only" model
   beside its own, so a reader can see how much of any gain is the de-vig.
4. **Author independence.** PRED-002's author session is not one of the
   SYM, engine or DISC-001 sessions, so the auditor eligibility rule is
   unaffected; record which of these reports its author had read.
