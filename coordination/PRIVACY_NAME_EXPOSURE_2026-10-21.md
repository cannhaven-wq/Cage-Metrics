# Owner name exposure in the public repository — report (decision E2)

**Rule from 2026-10-21:** the owner's personal name may appear only in
genuinely private records. Public pages, decision logs, GitHub documentation,
commit messages and PR text say **"CFL Owner"**. Historical records are not
silently rewritten; this report lists them so the owner can decide on
remediation separately.

## Fixed

- **`about.html`**: the public website said the site was "built and
  maintained by" the owner by name. The name is removed (PR #116).
  `git grep` finds no other HTML page naming the owner. The `f/` stubs that
  match "Reed" are fighters who share the name.

## Still present — needs a separate owner decision

The full name appears in these tracked files (counted 2026-10-21, excluding
`f/` and `e/`):

| area | files | nature |
|---|---|---|
| `coordination/` | 4 | decision log and records. **D-031 and D-032, written on 2026-10-21 before this rule existed, name the owner in their "decided by" field.** Earlier entries do too |
| `research/` | 6 | protocol, approval and amendment records |
| `cfl_engine/` | 4 | preregistration and amendment records |
| `CLAUDE.md` | 1 | the project instructions name the owner |
| `CFL_RESEARCH_STATE.md` | 1 | research state summary |

A second spelling of the owner's name appears in 7 files (part of T-009).

Commit messages and PR text checked in the recent history contain no name.

## Why nothing else was edited

The decision log is append-only by rule: entries are never rewritten. Frozen
research files are checked by sha256 in `tests/test_research_state.py`, so
editing them would invalidate the experiments that rest on them. And because
the repository is public, removing a name from today's files does not remove
it from git history.

## Options for the owner

1. **Do nothing to history; use "CFL Owner" from now on.** Already in
   effect. Free and reversible.
2. **Redact the current files only.** Leave frozen research files alone;
   add a dated note to the decision log rather than editing entries. Removes
   the name from the default view, but it stays in git history.
3. **Rewrite git history.** Removes the name everywhere, but it is
   destructive, breaks every clone and fork, invalidates the frozen-file
   hashes, and is not undoable.
4. **Make the repository private.** The site keeps deploying only on a
   GitHub plan that supports Pages for private repositories.
