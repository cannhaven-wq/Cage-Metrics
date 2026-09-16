-- ============================================================================
-- PROPOSED MIGRATION — NOT APPLIED
--
-- One column: which model_edges row a pre-fight snapshot froze.
-- CLV-001 R-07, Amendment 7 (c).
--
-- STATUS: draft. Order does not matter relative to the other four — nothing
-- else references it — but the sooner it lands the sooner snapshots start
-- carrying an edge identity, and it cannot be backfilled.
--
-- Filed under research/clv/ rather than the repo root so the "apply root *.sql"
-- habit cannot pick it up by accident.
--
-- ADDITIVE ONLY:
--   * no DROP of any kind
--   * no DELETE
--   * no destructive or back-filling UPDATE
--   * no trigger created, altered, weakened or removed
--   * no reinterpretation of an existing row or column
--
-- The append-only triggers on pre_fight_snapshots are untouched and keep
-- rejecting UPDATE and DELETE for every role including service_role. ADD COLUMN
-- is DDL and is not blocked by them; no existing row is read or written.
--
-- WHY
-- ---
-- R-07: "A forecast whose timestamp cannot be established from an immutable
-- record is not eligible." `pre_fight_snapshots` is that record, and CLV-001
-- matches a snapshot to an edge on (edge_side, edge_bet_fighter_id,
-- edge_odds_at_publish).
--
-- That is a good fail-closed cross-check and it is not an identity. The same
-- fight can be republished with the same side, the same fighter and the same
-- price — by coincidence, or simply because the line had not moved between the
-- two publications.
--
-- And several live edges per fight are not hypothetical. snapshot_predictions.py
-- reads every live edge on a fight and keeps the one with the latest
-- published_at:
--
--     cur = edges.get(e["fight_id"])
--     if cur is None or (e["published_at"] or "") > (cur["published_at"] or ""):
--         edges[e["fight_id"]] = e
--
-- So the snapshot is a record of ONE publication, chosen from several, and until
-- it names which one, a later reader is guessing from a tuple two of them can
-- share.
--
-- WHAT CHANGES, AND WHAT DOES NOT
-- -------------------------------
-- Every existing snapshot carries NULL here, permanently and correctly: those
-- snapshots did not record an edge id, and inferring one now by matching prices
-- would manufacture exactly the evidence this column exists to require. CLV-001
-- falls back to the tuple for them, and refuses to score any fight where that
-- tuple matches more than one live edge (`ambiguous_edge_identity`).
--
-- No deploy has to accompany this. snapshot_predictions.py probes for the column
-- and omits it when absent, so it writes the id from the first run after this
-- lands and behaves identically before.
-- ============================================================================

begin;

-- The model_edges row this snapshot froze. NOT a foreign key: model_edges is a
-- working table and a delete there must never cascade into, or be blocked by,
-- the immutable pre-fight record. The id is kept as evidence of what we
-- published, whether or not the working row still exists.
alter table public.pre_fight_snapshots
  add column if not exists edge_model_edge_id bigint;

-- Matching a snapshot back to its edge, which is the only read this serves.
create index if not exists pre_fight_snapshots_edge_idx
  on public.pre_fight_snapshots (edge_model_edge_id)
  where edge_model_edge_id is not null;

-- A snapshot that names an edge must also carry that edge's details, or it is
-- half a record. NOT VALID, so the existing rows — which carry neither an id nor,
-- in some cases, an edge at all — are never touched or re-validated.
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'pre_fight_snapshots_edge_id_needs_an_edge'
                    and conrelid = 'public.pre_fight_snapshots'::regclass) then
    alter table public.pre_fight_snapshots
      add constraint pre_fight_snapshots_edge_id_needs_an_edge
      check (edge_model_edge_id is null
             or (edge_side is not null
                 and edge_bet_fighter_id is not null
                 and edge_odds_at_publish is not null)) not valid;
  end if;
end $$;

comment on column public.pre_fight_snapshots.edge_model_edge_id is
  'Which model_edges row this snapshot froze. CLV-001 R-07 needs to know WHICH '
  'publication was locked, and (edge_side, edge_bet_fighter_id, '
  'edge_odds_at_publish) is a cross-check rather than an identity - two '
  'publications on one fight can share it. Deliberately not a foreign key: '
  'model_edges is a working table and must never cascade into, or be blocked '
  'by, the immutable pre-fight record. NULL on every snapshot taken before this '
  'column existed, and never backfilled - inferring it by matching prices would '
  'manufacture the evidence it exists to require.';

commit;

-- ============================================================================
-- AFTER APPLYING — what must still be true
--
--   * every existing snapshot is byte-identical, with NULL in the new column.
--   * the append-only triggers still reject UPDATE and DELETE for every role.
--   * snapshot_predictions.py starts writing the id on its next run, with no
--     deploy. Before this lands it probes, finds the column missing, and omits
--     it; the probe is what makes applying this safe in either order.
--   * CLV-001 keeps refusing every historical row, for the same reasons as
--     before. This column changes nothing retrospectively - it makes the NEXT
--     snapshot unambiguous.
-- ============================================================================
