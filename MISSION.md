# Mission

> **Draft wording, 2026-10-22.** The CFL Owner adopted this mission and asked
> for it to be the shared north star ([D-035](coordination/DECISIONS.md)). The
> owner's own text did not reach the session that wrote this file, so the
> explanation below was drafted from the owner's north star line. **The north
> star line is the owner's, word for word.** When the owner supplies the
> adopted text, it replaces the body of this file and this note is removed.

## North star

**Find a real edge. Prove it exists. Make it actionable. Build a business around what we learn.**

Four steps, in that order. Each one depends on the one before it.

## What each step means in this repository

1. **Find a real edge.** An edge is something about a fight that the betting
   market prices wrongly, often enough and by enough to matter after the
   sportsbook's margin. A stat that only repeats what the betting line already
   says is not an edge. That is why Factor Lab tests every factor on fights the
   market priced as even. Finding a candidate is research, and a candidate is
   not a result.

2. **Prove it exists.** Proof is **prospective**: the method is written down and
   frozen before the outcomes are known, the forecast is locked before the
   bell, and the result is scored in the open under the protocols in
   [`research/`](research/). Backtests, in-sample fits, exploration and data
   exports produce leads, not proof. A failed result is recorded as plainly as
   a passing one and is never deleted.

3. **Make it actionable.** Only after step 2, and only through the existing
   gates. A proven edge reaches a public page only when its publication
   thresholds are met and the evidence is published before the number
   ([D-011](coordination/DECISIONS.md), the CLV protocol, `CRITICAL_GATES.md`
   item 8). "Actionable" also means a UFC bettor with no stats background can
   understand it in one sentence.

4. **Build a business around what we learn.** What CFL sells is the research:
   the capture schedule, the provenance, the vig-free consensus, the movement
   history, the matchup comparisons and the factor testing (D-011). Third-party
   data is an input, never the product. Every decision about pricing, payments
   or spending stays with the owner (L3).

## Using it to stay on track

Before starting a piece of work, name the step it serves. Keeping the odds
capture, the pre-fight record and the monitoring running serves step 2: those
are the instruments that make proof possible. Fixing something the owner asked
for serves the product the business is built on. If a task serves none of the
four steps, it is a detour: say so in the handoff instead of quietly doing it.

When there is a choice of what to do next, prefer the work that moves the
earliest unfinished step forward. A business cannot be built on an edge that
has not been proven, and an edge cannot be proven if it has not been found.

## What this mission does not do

- **It authorises nothing.** It is not a decision level and not a gate.
  [`coordination/CRITICAL_GATES.md`](coordination/CRITICAL_GATES.md) still
  decides who may do what. "It serves the mission" is never a reason to skip a
  gate, change a frozen specification, widen a test window, or publish a number
  early.
- **It does not reverse D-011.** No public page shows a CFL win probability, a
  pick, a confidence tier, a predicted winner, an edge percentage, or a
  difference between CFL's number and the market's. Looking for an edge is the
  research; claiming one in public is a separate step that needs proof first.
- **It does not override a recorded decision.** If the mission and a decision
  in [`coordination/DECISIONS.md`](coordination/DECISIONS.md) seem to
  disagree, the decision stands and the conflict goes to the owner as a
  question.
