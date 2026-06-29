-- track_record_events_view.sql
-- =============================================================================
-- Backs the homepage "Track Record" grid (loadPastEvents in index.html).
--
-- Previously the grid read v_event_accuracy and required committed_picks > 0 —
-- i.e. a locked RULES-BASED verdict (the cfl-snapshotter writes the
-- `predictions` table the day before each card). When that snapshotter wasn't
-- running, completed events had no rules-based verdict and silently dropped off
-- the Track Record even though the ML models (model_predictions) had locked
-- their picks before the card.
--
-- v_track_record_events surfaces any completed event that has graded picks from
-- EITHER source: a locked rules-based verdict, OR graded ML model picks. The
-- card itself shows the per-model (v1/v2/v3) accuracy, which is honest because
-- those picks were committed before the event.
--
-- Idempotent. Remember: every public v_* view must grant SELECT to anon AND
-- authenticated, or signed-in users get empty 200s (see CLAUDE.md data layer).
-- =============================================================================

create or replace view v_track_record_events as
select e.id          as event_id,
       e.name        as event_name,
       e.event_date,
       coalesce(va.committed_picks, 0) as committed_picks,
       coalesce(va.hits, 0)            as hits,
       coalesce(va.misses, 0)         as misses,
       va.accuracy_pct
from events e
left join v_event_accuracy va on va.event_id = e.id
where e.is_upcoming = false
  and (
        coalesce(va.committed_picks, 0) > 0
        or exists (
          select 1 from model_predictions mp
          where mp.event_date = e.event_date and mp.outcome_known
        )
      )
order by e.event_date desc;

grant select on v_track_record_events to anon, authenticated;
