"""Read-only data-integrity checks and the runner that reports them.

`checks.py` is the catalogue: one entry per defect, each with the SQL that
counts it, a plain-English reason it matters, and who gets to decide what to do
about it. `run_audit.py` runs them and compares against a baseline.

Nothing in here writes to the database. That is asserted by a test, not by
intent.
"""
