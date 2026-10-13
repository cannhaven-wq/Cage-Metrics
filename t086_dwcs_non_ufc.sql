-- =============================================================================
-- T-086 — Move the non-UFC card "DWCS 10.3" out of the UFC tables (2026-10-13)
-- =============================================================================
-- NOT APPLIED. L3: it removes rows from events, fights and fight_rounds (after
-- copying them). Plan, checks and approval record:
-- research/data-integrity/T-086_MIGRATION_PLAN_2026-10-13.md.
--
-- WHAT. Event 4259 "DWCS 10.3" (2026-08-25), its 5 bouts (49307-49311) and
-- their 8 round rows (86132-86139) are Dana White's Contender Series, not UFC.
-- They move, UNCHANGED and WITH THE SAME IDS, into three sibling tables:
--   events_non_ufc, fights_non_ufc, fight_rounds_non_ufc.
-- After this, `events` / `fights` / `fight_rounds` hold UFC only, which is what
-- every view, page and script already assumes. Nothing is lost: every column
-- of every row is copied and its fingerprint is checked before the originals
-- are removed.
--
-- WHY THE EVENT MOVES TOO (refinement of the approved Option C, see the plan):
-- about 20 readers choose "the next card" / "recent cards" from `events` with
-- no promotion filter. Leaving the row there would show an empty card, and an
-- upcoming DWCS episode could become the homepage's next card. With the event
-- in events_non_ufc, the existing fights.event_id foreign key makes it
-- impossible for a UFC-table fight to sit on a non-UFC card.
--
-- WHY NOT `CREATE TABLE ... (LIKE ... INCLUDING ALL)`: LIKE does not copy
-- foreign keys, RLS, policies or grants, and copies identity in a way that
-- would give the new table its OWN sequence. Everything is written out below.
--
-- IDS. The new tables draw new ids from the SAME sequences as the UFC tables,
-- so an id is unique across both. A row can always move back (rollback, or a
-- misclassification) without colliding.
--
-- GUARD. events gains a CHECK that a name looks like a UFC event, the same
-- rule as research/data-integrity/reconcile_ufc_records.py::UFC_EVENT_RE. The
-- old scraper can therefore not put a non-UFC card back into `events`, and
-- without an event row its bouts cannot enter `fights` (foreign key). Checked
-- against all 801 production event names on 2026-10-13: exactly one fails,
-- 4259.
--
-- ONE TRANSACTION. Any failed assertion raises and nothing is applied.
-- Refuses to run twice. Rollback: t086_dwcs_non_ufc.rollback.sql.
-- =============================================================================

BEGIN;

SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- 0. Preconditions. Production must still look exactly like what was reviewed.
-- -----------------------------------------------------------------------------
DO $pre$
DECLARE
  n      bigint;
  fk     record;
BEGIN
  IF to_regclass('public.fights_non_ufc') IS NOT NULL
     OR to_regclass('public.fight_rounds_non_ufc') IS NOT NULL
     OR to_regclass('public.events_non_ufc') IS NOT NULL THEN
    RAISE EXCEPTION 'T-086: a *_non_ufc table already exists; this migration has run before';
  END IF;

  SELECT count(*) INTO n FROM public.events WHERE id = 4259 AND name = 'DWCS 10.3';
  IF n <> 1 THEN RAISE EXCEPTION 'T-086: event 4259 "DWCS 10.3" not found (got %)', n; END IF;

  SELECT count(*) INTO n FROM public.fights WHERE event_id = 4259;
  IF n <> 5 THEN RAISE EXCEPTION 'T-086: expected 5 fights on event 4259, found %', n; END IF;

  SELECT count(*) INTO n FROM public.fights
   WHERE event_id = 4259 AND id NOT IN (49307, 49308, 49309, 49310, 49311);
  IF n <> 0 THEN RAISE EXCEPTION 'T-086: event 4259 holds a fight outside 49307-49311'; END IF;

  SELECT count(*) INTO n FROM public.fight_rounds
   WHERE fight_id IN (SELECT id FROM public.fights WHERE event_id = 4259);
  IF n <> 8 THEN RAISE EXCEPTION 'T-086: expected 8 round rows, found %', n; END IF;

  -- Every OTHER table that references fights or events must hold nothing for
  -- these rows: deleting them would otherwise cascade (8 FKs to fights are ON
  -- DELETE CASCADE), null out, or be refused. Generic over pg_constraint, so a
  -- table added after this file was written is still checked.
  FOR fk IN
    SELECT c.conrelid::regclass AS tbl, a.attname AS col, c.confrelid::regclass AS ref
      FROM pg_constraint c
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
     WHERE c.contype = 'f'
       AND c.confrelid IN ('public.fights'::regclass, 'public.events'::regclass)
       AND array_length(c.conkey, 1) = 1
  LOOP
    IF fk.ref = 'public.events'::regclass THEN
      CONTINUE WHEN fk.tbl = 'public.fights'::regclass;      -- the 5 being moved
      EXECUTE format('SELECT count(*) FROM %s WHERE %I = 4259', fk.tbl, fk.col) INTO n;
    ELSE
      CONTINUE WHEN fk.tbl = 'public.fight_rounds'::regclass; -- the 8 being moved
      EXECUTE format('SELECT count(*) FROM %s WHERE %I IN (49307,49308,49309,49310,49311)',
                     fk.tbl, fk.col) INTO n;
    END IF;
    IF n <> 0 THEN
      RAISE EXCEPTION 'T-086: %.% still references the DWCS card (% rows)', fk.tbl, fk.col, n;
    END IF;
  END LOOP;

  -- Tables that hold a fight_id WITHOUT a foreign key (append-only evidence).
  IF to_regclass('public.pre_fight_snapshots') IS NOT NULL THEN
    SELECT count(*) INTO n FROM public.pre_fight_snapshots
     WHERE fight_id IN (49307,49308,49309,49310,49311);
    IF n <> 0 THEN RAISE EXCEPTION 'T-086: pre_fight_snapshots references the DWCS card'; END IF;
  END IF;

  -- The name guard must pass for every event that stays.
  SELECT count(*) INTO n FROM public.events
   WHERE id <> 4259
     AND NOT (name ~ '\mUFC\M|^The Ultimate Fighter\M|^Ortiz vs\.? Shamrock 3\M'
              AND name !~* '^\s*road to ufc');
  IF n <> 0 THEN RAISE EXCEPTION 'T-086: % other events fail the UFC name rule', n; END IF;
END
$pre$;

-- -----------------------------------------------------------------------------
-- 1. The three sibling tables. Same columns, same order, same types and
--    defaults as their UFC counterparts (events_non_ufc adds `promotion` and
--    `moved_at` at the end).
-- -----------------------------------------------------------------------------
CREATE TABLE public.events_non_ufc (
  id            bigint      NOT NULL,
  ufc_event_id  text        NOT NULL,
  name          text        NOT NULL,
  event_date    date,
  location      text,
  is_upcoming   boolean     DEFAULT false,
  ufc_url       text,
  updated_at    timestamptz DEFAULT now(),
  promotion     text        NOT NULL,
  moved_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT events_non_ufc_pkey PRIMARY KEY (id),
  CONSTRAINT events_non_ufc_ufc_event_id_key UNIQUE (ufc_event_id),
  CONSTRAINT events_non_ufc_promotion_check CHECK (promotion IN ('DWCS', 'RTU', 'OTHER'))
);

CREATE TABLE public.fights_non_ufc (
  id                    bigint      NOT NULL,
  ufc_fight_id          text        NOT NULL,
  event_id              bigint,
  fighter_a_id          bigint,
  fighter_b_id          bigint,
  fighter_a_name        text,
  fighter_b_name        text,
  winner_id             bigint,
  method                text,
  method_detail         text,
  end_round             integer,
  end_time              text,
  scheduled_rounds      integer     DEFAULT 3,
  weight_class          text,
  is_title_fight        boolean     DEFAULT false,
  is_main_event         boolean     DEFAULT false,
  bonus                 text,
  a_kd integer, b_kd integer,
  a_sig_str_landed integer, b_sig_str_landed integer,
  a_sig_str_attempted integer, b_sig_str_attempted integer,
  a_total_str_landed integer, b_total_str_landed integer,
  a_total_str_attempted integer, b_total_str_attempted integer,
  a_td_landed integer, b_td_landed integer,
  a_td_attempted integer, b_td_attempted integer,
  a_sub_attempts integer, b_sub_attempts integer,
  a_rev integer, b_rev integer,
  a_ctrl_seconds integer, b_ctrl_seconds integer,
  a_head_landed integer, b_head_landed integer,
  a_body_landed integer, b_body_landed integer,
  a_leg_landed integer, b_leg_landed integer,
  a_distance_landed integer, b_distance_landed integer,
  a_clinch_landed integer, b_clinch_landed integer,
  a_ground_landed integer, b_ground_landed integer,
  ufc_url               text,
  updated_at            timestamptz DEFAULT now(),
  bell_at               timestamptz,
  bout_order            integer,
  is_active             boolean     NOT NULL DEFAULT true,
  CONSTRAINT fights_non_ufc_pkey PRIMARY KEY (id),
  CONSTRAINT fights_non_ufc_ufc_fight_id_key UNIQUE (ufc_fight_id),
  -- RESTRICT, not CASCADE as on fights: removing a non-UFC event must never
  -- silently erase its results.
  CONSTRAINT fights_non_ufc_event_id_fkey FOREIGN KEY (event_id)
    REFERENCES public.events_non_ufc(id) ON DELETE RESTRICT,
  CONSTRAINT fights_non_ufc_fighter_a_id_fkey FOREIGN KEY (fighter_a_id) REFERENCES public.fighters(id),
  CONSTRAINT fights_non_ufc_fighter_b_id_fkey FOREIGN KEY (fighter_b_id) REFERENCES public.fighters(id),
  CONSTRAINT fights_non_ufc_winner_id_fkey   FOREIGN KEY (winner_id)    REFERENCES public.fighters(id)
);

CREATE TABLE public.fight_rounds_non_ufc (
  id            bigint  NOT NULL,
  fight_id      bigint  NOT NULL,
  round_number  integer NOT NULL,
  fighter_a_id  bigint,
  fighter_b_id  bigint,
  a_kd integer, b_kd integer,
  a_sig_str_landed integer, b_sig_str_landed integer,
  a_sig_str_attempted integer, b_sig_str_attempted integer,
  a_total_str_landed integer, b_total_str_landed integer,
  a_total_str_attempted integer, b_total_str_attempted integer,
  a_td_landed integer, b_td_landed integer,
  a_td_attempted integer, b_td_attempted integer,
  a_sub_attempts integer, b_sub_attempts integer,
  a_rev integer, b_rev integer,
  a_ctrl_seconds integer, b_ctrl_seconds integer,
  a_head_landed integer, b_head_landed integer,
  a_body_landed integer, b_body_landed integer,
  a_leg_landed integer, b_leg_landed integer,
  a_distance_landed integer, b_distance_landed integer,
  a_clinch_landed integer, b_clinch_landed integer,
  a_ground_landed integer, b_ground_landed integer,
  CONSTRAINT fight_rounds_non_ufc_pkey PRIMARY KEY (id),
  CONSTRAINT fight_rounds_non_ufc_fight_id_round_number_key UNIQUE (fight_id, round_number),
  -- Same as fight_rounds: a round row belongs to its bout. The scraper
  -- replaces a bout's rounds by delete-then-insert, as it does for UFC.
  CONSTRAINT fight_rounds_non_ufc_fight_id_fkey FOREIGN KEY (fight_id)
    REFERENCES public.fights_non_ufc(id) ON DELETE CASCADE,
  CONSTRAINT fight_rounds_non_ufc_fighter_a_id_fkey FOREIGN KEY (fighter_a_id) REFERENCES public.fighters(id),
  CONSTRAINT fight_rounds_non_ufc_fighter_b_id_fkey FOREIGN KEY (fighter_b_id) REFERENCES public.fighters(id)
);

-- Indexes: every index the UFC tables have, under matching names.
CREATE INDEX events_non_ufc_event_date_idx  ON public.events_non_ufc USING btree (event_date DESC);
CREATE INDEX events_non_ufc_is_upcoming_idx ON public.events_non_ufc USING btree (is_upcoming);
CREATE INDEX fights_non_ufc_bell_at_idx      ON public.fights_non_ufc USING btree (bell_at) WHERE (bell_at IS NOT NULL);
CREATE INDEX fights_non_ufc_event_id_idx     ON public.fights_non_ufc USING btree (event_id);
CREATE INDEX fights_non_ufc_fighter_a_id_idx ON public.fights_non_ufc USING btree (fighter_a_id);
CREATE INDEX fights_non_ufc_fighter_b_id_idx ON public.fights_non_ufc USING btree (fighter_b_id);
CREATE INDEX fights_non_ufc_method_idx       ON public.fights_non_ufc USING btree (method);
CREATE INDEX fights_non_ufc_weight_class_idx ON public.fights_non_ufc USING btree (weight_class);
CREATE INDEX fights_non_ufc_winner_id_idx    ON public.fights_non_ufc USING btree (winner_id);
CREATE INDEX fight_rounds_non_ufc_fight_id_idx ON public.fight_rounds_non_ufc USING btree (fight_id);

-- Ids come from the UFC tables' own sequences (see header).
DO $seq$
BEGIN
  EXECUTE format('ALTER TABLE public.events_non_ufc ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
                 pg_get_serial_sequence('public.events', 'id'));
  EXECUTE format('ALTER TABLE public.fights_non_ufc ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
                 pg_get_serial_sequence('public.fights', 'id'));
  EXECUTE format('ALTER TABLE public.fight_rounds_non_ufc ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
                 pg_get_serial_sequence('public.fight_rounds', 'id'));
END
$seq$;

-- Security. Public results, like fights: read for both browser roles, write
-- for service_role only. REVOKE from both roles (and PUBLIC) first: a new
-- table inherits Supabase's broad default grants (CLAUDE.md, funnel_events).
ALTER TABLE public.events_non_ufc       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fights_non_ufc       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fight_rounds_non_ufc ENABLE ROW LEVEL SECURITY;

CREATE POLICY events_non_ufc_public_read       ON public.events_non_ufc       FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY fights_non_ufc_public_read       ON public.fights_non_ufc       FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY fight_rounds_non_ufc_public_read ON public.fight_rounds_non_ufc FOR SELECT TO anon, authenticated USING (true);

REVOKE ALL ON public.events_non_ufc, public.fights_non_ufc, public.fight_rounds_non_ufc
  FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.events_non_ufc, public.fights_non_ufc, public.fight_rounds_non_ufc
  TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.events_non_ufc, public.fights_non_ufc, public.fight_rounds_non_ufc
  TO service_role;

COMMENT ON TABLE public.events_non_ufc IS
  'T-086: cards that are not UFC events (Contender Series, Road to UFC, other). '
  'Kept verbatim with their original ids; excluded from every UFC record by living here.';
COMMENT ON TABLE public.fights_non_ufc IS
  'T-086: bouts on non-UFC cards. Same columns and ids as fights. Not a UFC fight.';
COMMENT ON TABLE public.fight_rounds_non_ufc IS
  'T-086: round stats for fights_non_ufc. Same columns and ids as fight_rounds.';

-- -----------------------------------------------------------------------------
-- 2. Copy, then prove the copy is exact.
-- -----------------------------------------------------------------------------
INSERT INTO public.events_non_ufc
  (id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at, promotion)
SELECT id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at, 'DWCS'
  FROM public.events WHERE id = 4259;

INSERT INTO public.fights_non_ufc
SELECT f.* FROM public.fights f WHERE f.event_id = 4259 ORDER BY f.id;

INSERT INTO public.fight_rounds_non_ufc
SELECT r.* FROM public.fight_rounds r
 WHERE r.fight_id IN (SELECT id FROM public.fights WHERE event_id = 4259) ORDER BY r.id;

DO $verify$
DECLARE
  src text; dst text;
BEGIN
  -- events: the original 8 columns.
  SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) INTO src FROM (
    SELECT id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at
      FROM public.events WHERE id = 4259) t;
  SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) INTO dst FROM (
    SELECT id, ufc_event_id, name, event_date, location, is_upcoming, ufc_url, updated_at
      FROM public.events_non_ufc) t;
  IF src IS DISTINCT FROM dst THEN RAISE EXCEPTION 'T-086: events copy differs (% vs %)', src, dst; END IF;

  -- fights / rounds: whole rows. Identical column order makes row text identical.
  SELECT md5(string_agg(f::text, '|' ORDER BY f.id)) INTO src FROM public.fights f WHERE f.event_id = 4259;
  SELECT md5(string_agg(f::text, '|' ORDER BY f.id)) INTO dst FROM public.fights_non_ufc f;
  IF src IS DISTINCT FROM dst THEN RAISE EXCEPTION 'T-086: fights copy differs (% vs %)', src, dst; END IF;
  EXECUTE format('COMMENT ON COLUMN public.fights_non_ufc.id IS %L',
                 'T-086 source fingerprint md5(string_agg(row::text, ''|'' order by id)) = ' || src);

  SELECT md5(string_agg(r::text, '|' ORDER BY r.id)) INTO src FROM public.fight_rounds r
   WHERE r.fight_id IN (SELECT id FROM public.fights WHERE event_id = 4259);
  SELECT md5(string_agg(r::text, '|' ORDER BY r.id)) INTO dst FROM public.fight_rounds_non_ufc r;
  IF src IS DISTINCT FROM dst THEN RAISE EXCEPTION 'T-086: rounds copy differs (% vs %)', src, dst; END IF;
  EXECUTE format('COMMENT ON COLUMN public.fight_rounds_non_ufc.id IS %L',
                 'T-086 source fingerprint md5(string_agg(row::text, ''|'' order by id)) = ' || src);
END
$verify$;

-- -----------------------------------------------------------------------------
-- 3. Remove the originals, children first, with exact row counts.
-- -----------------------------------------------------------------------------
DO $del$
DECLARE n bigint;
BEGIN
  DELETE FROM public.fight_rounds
   WHERE fight_id IN (SELECT id FROM public.fights WHERE event_id = 4259);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 8 THEN RAISE EXCEPTION 'T-086: deleted % round rows, expected 8', n; END IF;

  DELETE FROM public.fights WHERE event_id = 4259;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 5 THEN RAISE EXCEPTION 'T-086: deleted % fights, expected 5', n; END IF;

  DELETE FROM public.events WHERE id = 4259;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'T-086: deleted % events, expected 1', n; END IF;
END
$del$;

-- -----------------------------------------------------------------------------
-- 4. The guard: `events` accepts UFC cards only.
-- -----------------------------------------------------------------------------
ALTER TABLE public.events ADD CONSTRAINT events_ufc_name_only CHECK (
  name ~ '\mUFC\M|^The Ultimate Fighter\M|^Ortiz vs\.? Shamrock 3\M'
  AND name !~* '^\s*road to ufc'
);

-- -----------------------------------------------------------------------------
-- 5. Postconditions.
-- -----------------------------------------------------------------------------
DO $post$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM public.fights WHERE id IN (49307,49308,49309,49310,49311);
  IF n <> 0 THEN RAISE EXCEPTION 'T-086: DWCS bouts still in fights'; END IF;
  SELECT count(*) INTO n FROM public.fights_non_ufc;
  IF n <> 5 THEN RAISE EXCEPTION 'T-086: fights_non_ufc holds %, expected 5', n; END IF;
  SELECT count(*) INTO n FROM public.fight_rounds_non_ufc;
  IF n <> 8 THEN RAISE EXCEPTION 'T-086: fight_rounds_non_ufc holds %, expected 8', n; END IF;
  SELECT count(*) INTO n FROM public.events_non_ufc WHERE id = 4259 AND promotion = 'DWCS';
  IF n <> 1 THEN RAISE EXCEPTION 'T-086: events_non_ufc is missing 4259'; END IF;
END
$post$;

COMMIT;
