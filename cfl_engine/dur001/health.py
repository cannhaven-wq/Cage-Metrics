"""DUR-001 capture health — one command, read-only.

    python cfl_engine/dur001/health.py            # next upcoming card
    python cfl_engine/dur001/health.py --event-id 4433
    python cfl_engine/dur001/health.py --json     # machine-readable

Reports GREEN / YELLOW / RED on the five things worth watching each card:
  1. workflow health   latest scheduled "Fetch UFC odds" run on main, quota
  2. lock coverage     every eligible 3-round fight has exactly one PROP-0001
                       lock set, ledger hash unchanged
  3. quote coverage    exact-threshold totals per locked fight, books,
                       capture timestamps, staleness
  4. close-time safety start_basis, live flags, fallback starts
  5. ledger integrity  row counts, append evidence, constraint violations
  6. matchable sample  rows that satisfy every preregistration rule

Never writes. Never computes model performance. Reads the database through the
Supabase Management API (SUPABASE_ACCESS_TOKEN, read-only SELECTs) and GitHub
through the REST API (public run list; GH_TOKEN optional for log-level quota).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

PROJECT_REF = "uftancejftcryfvbggll"
REPO = "cannhaven-wq/Cage-Metrics"
MODEL_VERSION = "PROP-0001@v1"
LOCK_THRESHOLDS = (0.5, 1.5, 2.5)
STALE_HOURS_NEAR = 3          # inside 24h of a start, a quote older than this is stale
PRIMARY_BASES = ("bell_at", "provider_commence")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"


# ------------------------------------------------------------------ io
def sql(query: str):
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        sys.exit("SUPABASE_ACCESS_TOKEN not set (read-only Management API).")
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": query, "read_only": True}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def gh_token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    try:
        out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                             capture_output=True, text=True, timeout=20).stdout
        for line in out.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return None


def gh(path: str, token=None, raw=False):
    req = urllib.request.Request(f"https://api.github.com{path}",
                                 headers={"User-Agent": UA, "Accept": "application/vnd.github+json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        return body.decode(errors="replace") if raw else json.loads(body.decode())


# ------------------------------------------------------------ sections
def workflow_health():
    out = {"ok": None}
    try:
        runs = gh(f"/repos/{REPO}/actions/workflows/odds.yml/runs?branch=main&event=schedule&per_page=1")["workflow_runs"]
    except Exception as e:
        return {"ok": None, "error": f"github api: {e}"}
    if not runs:
        return {"ok": False, "error": "no scheduled runs on main"}
    r = runs[0]
    out.update({"run_id": r["id"], "created_at": r["created_at"], "status": r["status"],
                "conclusion": r["conclusion"], "head_sha": r["head_sha"][:8],
                "url": r["html_url"]})
    out["ok"] = r["conclusion"] == "success"
    tok = gh_token()
    if tok:
        try:
            log = gh(f"/repos/{REPO}/actions/runs/{r['id']}/logs", token=tok, raw=True)
        except urllib.error.HTTPError as e:
            log = ""
            if e.code == 302:
                log = ""
        except Exception:
            log = ""
        # logs endpoint redirects to a zip; fall back to the jobs API text via gh cli if present
        txt = ""
        try:
            txt = subprocess.run(["gh", "run", "view", str(r["id"]), "--log"], capture_output=True, text=True,
                                 timeout=120, env={**os.environ, "GH_TOKEN": tok}).stdout
        except Exception:
            txt = log
        for line in txt.splitlines():
            if "[odds-api] HTTP" in line:
                seg = line.split("[odds-api] ", 1)[1]
                out["api_line"] = seg.strip()
                for part in seg.replace(",", " ").split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k in ("used", "remaining", "last"):
                            out[f"quota_{k}"] = v
            elif "[totals] appended" in line:
                out["totals_appended"] = int(line.split("appended", 1)[1].split()[0])
            elif "[totals] skipping" in line or "[cadence]" in line and "skipping" in line:
                out["skipped_reason"] = line.split("] ", 1)[1].strip()
            elif "[fetch-odds] failed" in line:
                out["error"] = line.split("failed:", 1)[1].strip()
    else:
        out["note"] = "no GitHub token: quota/credit lines unavailable (run list is public)"
    return out


def target_event(event_id):
    if event_id:
        rows = sql(f"select id, name, event_date from events where id={int(event_id)}")
    else:
        rows = sql("select id, name, event_date from events where event_date >= current_date "
                   "and exists (select 1 from fights f where f.event_id=events.id and f.winner_id is null) "
                   "order by event_date limit 1")
    return rows[0] if rows else None


def lock_coverage(eid):
    r = sql(f"""
with elig as (
  select id from fights where event_id={eid} and not coalesce(is_main_event,false)
    and not coalesce(is_title_fight,false) and coalesce(scheduled_rounds,3)=3
    and winner_id is null and method is null),
locks as (
  select fight_id, count(*) n, count(distinct (market_type, coalesce(threshold,-1), side)) keys
  from prop_model_locks where model_version='{MODEL_VERSION}' group by fight_id)
select
  (select count(*) from elig) eligible,
  (select array_agg(id order by id) from elig) eligible_ids,
  (select count(*) from elig e join locks l on l.fight_id=e.id where l.n=4 and l.keys=4) fully_locked,
  (select array_agg(e.id) from elig e where not exists (select 1 from locks l where l.fight_id=e.id)) missing,
  (select array_agg(fight_id) from locks where n<>keys or n>4) duplicated,
  (select array_agg(fight_id) from locks l where l.fight_id in (select id from fights where event_id={eid}) and l.fight_id not in (select id from elig)) locks_on_ineligible,
  (select count(*) from prop_model_locks) total_locks,
  (select md5(string_agg(row_to_json(l)::text,'|' order by id)) from prop_model_locks l) ledger_hash,
  (select min(actual_lock_at) from prop_model_locks where fight_id in (select id from elig)) first_lock_at,
  (select max(actual_lock_at) from prop_model_locks where fight_id in (select id from elig)) last_lock_at
""")[0]
    r["ok"] = (r["eligible"] > 0 and r["fully_locked"] == r["eligible"]
               and not r["missing"] and not r["duplicated"])
    return r


def quote_coverage(eid):
    rows = sql(f"""
with elig as (
  select f.id fight_id, f.fighter_a_name||' vs '||f.fighter_b_name fight
  from fights f where f.event_id={eid} and not coalesce(is_main_event,false)
    and not coalesce(is_title_fight,false) and coalesce(scheduled_rounds,3)=3
    and f.winner_id is null and f.method is null
    and exists (select 1 from prop_model_locks l where l.fight_id=f.id and l.model_version='{MODEL_VERSION}')),
q as (
  select p.fight_id, p.line, p.book_id, p.captured_at, p.is_live, p.source
  from prop_odds p where p.market_type='total_rounds' and p.source<>'synthetic')
select e.fight_id, e.fight, s.start_at, s.start_basis,
  (select count(distinct line) from q where q.fight_id=e.fight_id and q.line in (0.5,1.5,2.5)) exact_thresholds,
  (select array_agg(distinct line order by line) from q where q.fight_id=e.fight_id and q.line in (0.5,1.5,2.5)) thresholds_exact,
  (select array_agg(distinct line order by line) from q where q.fight_id=e.fight_id and q.line not in (0.5,1.5,2.5)) thresholds_unusable,
  (select count(distinct book_id) from q where q.fight_id=e.fight_id and q.line in (0.5,1.5,2.5)) books,
  (select count(distinct captured_at) from q where q.fight_id=e.fight_id and q.line in (0.5,1.5,2.5) and not is_live) prefight_timestamps,
  (select min(captured_at) from q where q.fight_id=e.fight_id) first_captured,
  (select max(captured_at) from q where q.fight_id=e.fight_id) last_captured,
  (select count(*) from q where q.fight_id=e.fight_id and is_live) live_quotes
from elig e left join v_fight_start_best s on s.fight_id=e.fight_id
order by e.fight_id""")
    now = dt.datetime.now(dt.timezone.utc)
    for r in rows:
        r["has_exact_total"] = (r["exact_thresholds"] or 0) > 0
        r["stale"] = False
        if r["last_captured"] and r["start_at"]:
            last = dt.datetime.fromisoformat(r["last_captured"].replace("Z", "+00:00"))
            start = dt.datetime.fromisoformat(r["start_at"].replace("Z", "+00:00"))
            if start - now < dt.timedelta(hours=24) and now < start:
                r["stale"] = (now - last) > dt.timedelta(hours=STALE_HOURS_NEAR)
    return rows


def close_safety(eid):
    r = sql(f"""
select
  (select count(*) from v_prop_odds_lifecycle where event_id={eid} and start_basis='event_date_fallback') fallback_rows,
  (select count(*) from v_prop_odds_lifecycle where event_id={eid} and is_closer_calc and is_live) live_closers,
  (select bool_and(is_live = (captured_at >= source_commence_at)) from prop_odds where event_id={eid}) live_flag_consistent,
  (select count(*) from prop_odds where event_id={eid} and source_commence_at is null) null_commence,
  (select json_agg(t) from (select start_basis, count(distinct fight_id) fights from v_prop_odds_lifecycle where event_id={eid} group by 1) t) basis_breakdown,
  (select json_agg(t) from (select fight_id, source, start_at, observed_at from fight_start_estimates where fight_id in (select id from fights where event_id={eid}) order by fight_id, observed_at) t) start_estimates
""")[0]
    r["ok"] = (r["fallback_rows"] == 0 and r["live_closers"] == 0
               and r["live_flag_consistent"] in (True, None) and r["null_commence"] == 0)
    return r


def ledger_integrity(latest_run_created):
    since = latest_run_created or "1970-01-01T00:00:00Z"
    r = sql(f"""
select
  (select count(*) from prop_odds) total_rows,
  (select count(distinct captured_at) from prop_odds) capture_batches,
  (select max(captured_at) from prop_odds) latest_capture,
  (select count(*) from prop_odds where captured_at >= '{since}'::timestamptz) rows_since_latest_run,
  (select count(*) from (select fight_id, book_id, line from prop_odds group by 1,2,3 having count(distinct captured_at) > 1) x) keys_with_repeat_captures,
  (select count(*) from v_prop_odds_integrity_issues) integrity_issues,
  (select count(*) from prop_odds where over_odds between -99 and 99 or under_odds between -99 and 99) bad_prices,
  (select count(*) from prop_odds where source='synthetic') synthetic_rows,
  (select count(*) from pg_trigger where tgrelid='public.prop_odds'::regclass and not tgisinternal) prop_odds_triggers,
  (select count(*) from pg_trigger where tgrelid='public.prop_model_locks'::regclass and not tgisinternal) lock_triggers
""")[0]
    r["append_evidence"] = r["keys_with_repeat_captures"] > 0
    r["ok"] = (r["integrity_issues"] == 0 and r["bad_prices"] == 0 and r["synthetic_rows"] == 0
               and r["prop_odds_triggers"] >= 3 and r["lock_triggers"] >= 4)
    return r


def matchable_sample():
    return sql(f"""
with c as (
  select fight_id, event_id, line, book_ids, start_basis
  from v_prop_odds_closing_consensus
  where market_type='total_rounds' and start_basis in ('bell_at','provider_commence')),
m as (
  select c.*, l.actual_lock_at
  from c join prop_model_locks l on l.fight_id=c.fight_id and l.threshold=c.line
    and l.market_type='total_rounds' and l.side='over' and l.model_version='{MODEL_VERSION}')
select
  count(distinct fight_id) fights,
  count(*) fight_threshold_pairs,
  count(distinct event_id) events,
  (select count(distinct b) from m, unnest(m.book_ids) b) books,
  (select count(distinct p.captured_at) from prop_odds p join m on m.fight_id=p.fight_id and m.line=p.line
     where not p.is_live and p.source<>'synthetic') capture_timestamps,
  (select json_agg(t) from (select line, count(*) n from m group by line order by line) t) by_threshold
from m""")[0]


# ---------------------------------------------------------------- status
def grade(wf, locks, quotes, close, ledger, sample):
    red, yellow = [], []
    if wf.get("ok") is False:
        red.append(f"latest scheduled run {wf.get('run_id')} concluded {wf.get('conclusion')}: {wf.get('error', '')}".strip())
    if not ledger["ok"]:
        red.append("ledger integrity check failed")
    if not close["ok"]:
        red.append("close-time safety violated (live closer / fallback start / commence missing)")
    if not locks["ok"]:
        (red if locks.get("missing") else yellow).append(
            f"lock coverage {locks['fully_locked']}/{locks['eligible']} missing={locks.get('missing')} dup={locks.get('duplicated')}")
    if locks.get("ledger_hash") is None:
        red.append("lock ledger empty")
    uncovered = [q["fight_id"] for q in quotes if not q["has_exact_total"]]
    if uncovered:
        yellow.append(f"{len(uncovered)} locked fight(s) with no exact-threshold total yet: {uncovered}")
    stale = [q["fight_id"] for q in quotes if q["stale"]]
    if stale:
        yellow.append(f"stale quotes (>{STALE_HOURS_NEAR}h old inside 24h of start): {stale}")
    single = [q["fight_id"] for q in quotes if q["has_exact_total"] and (q["prefight_timestamps"] or 0) < 2]
    if single:
        yellow.append(f"only one pre-fight timestamp so far: {single}")
    if wf.get("ok") is None:
        yellow.append(f"workflow status unknown: {wf.get('error')}")
    try:
        if wf.get("quota_remaining") is not None and int(wf["quota_remaining"]) < 60:
            yellow.append(f"Odds API quota low: {wf['quota_remaining']} remaining")
    except ValueError:
        pass
    if red:
        return "RED", red + yellow
    if yellow:
        return "YELLOW", yellow
    return "GREEN", ["collection working as designed"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ev = target_event(args.event_id)
    if not ev:
        print("no upcoming card with pending fights."); return
    eid = ev["id"]
    wf = workflow_health()
    locks = lock_coverage(eid)
    quotes = quote_coverage(eid)
    close = close_safety(eid)
    ledger = ledger_integrity(wf.get("created_at"))
    sample = matchable_sample()
    status, reasons = grade(wf, locks, quotes, close, ledger, sample)
    report = {"checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "event": ev, "status": status,
              "reasons": reasons, "workflow": wf, "locks": locks, "quotes": quotes, "close_safety": close,
              "ledger": ledger, "matchable_sample": sample}
    if args.json:
        print(json.dumps(report, indent=2, default=str)); return

    print(f"\nDUR-001 CAPTURE HEALTH — {ev['name']} ({ev['event_date']})   [{status}]")
    print("=" * 78)
    for r in reasons:
        print(f"  • {r}")
    print("\n1. WORKFLOW (latest scheduled run on main)")
    print(f"   run {wf.get('run_id')}  {wf.get('created_at')}  {wf.get('status')}/{wf.get('conclusion')}  sha {wf.get('head_sha')}")
    print(f"   {wf.get('api_line') or wf.get('note') or wf.get('error') or ''}")
    if "totals_appended" in wf:
        print(f"   totals appended by that run: {wf['totals_appended']}")
    if "skipped_reason" in wf:
        print(f"   {wf['skipped_reason']}")
    print("\n2. PROP-0001 LOCKS")
    print(f"   eligible 3-round fights {locks['eligible']}  fully locked {locks['fully_locked']}  "
          f"missing {locks.get('missing') or '—'}  duplicated {locks.get('duplicated') or '—'}")
    print(f"   ledger rows {locks['total_locks']}  hash {locks['ledger_hash']}  "
          f"(original 48-lock hash df3ab0cca0757eb9c452e9bfb0cede38)")
    print("\n3. SPORTSBOOK TOTALS (exact thresholds only: 0.5 / 1.5 / 2.5)")
    print(f"   {'fight':>6}  {'exact':>5}  {'books':>5}  {'ts':>3}  first → last capture               unusable  stale")
    for q in quotes:
        print(f"   {q['fight_id']:>6}  {q['exact_thresholds'] or 0:>5}  {q['books'] or 0:>5}  {q['prefight_timestamps'] or 0:>3}  "
              f"{(q['first_captured'] or '—')[:16]} → {(q['last_captured'] or '—')[:16]}  "
              f"{q['thresholds_unusable'] or '—'}  {'STALE' if q['stale'] else ''}   {q['fight']}")
    print("\n4. CLOSE-TIME SAFETY")
    print(f"   basis breakdown {close['basis_breakdown']}  fallback rows {close['fallback_rows']}  "
          f"live closers {close['live_closers']}  live flag consistent {close['live_flag_consistent']}")
    print("\n5. LEDGER")
    print(f"   prop_odds rows {ledger['total_rows']}  batches {ledger['capture_batches']}  latest {ledger['latest_capture']}")
    print(f"   rows since latest scheduled run {ledger['rows_since_latest_run']}  keys with repeat captures {ledger['keys_with_repeat_captures']}  "
          f"integrity issues {ledger['integrity_issues']}  synthetic {ledger['synthetic_rows']}  "
          f"triggers prop_odds={ledger['prop_odds_triggers']} locks={ledger['lock_triggers']}")
    print("\n6. MATCHABLE DUR-001 SAMPLE (all preregistration rules, all cards)")
    print(f"   fights {sample['fights']}  fight/threshold pairs {sample['fight_threshold_pairs']}  events {sample['events']}  "
          f"books {sample['books']}  capture timestamps {sample['capture_timestamps']}  by threshold {sample['by_threshold']}")
    print()


if __name__ == "__main__":
    main()
