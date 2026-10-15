-- t088_guard_probe.sql — does TRUNCATE on pre_fight_snapshots get through? Always rolls back (ends in an exception). For the local replica and an approved rehearsal only.
DO $g$
DECLARE out text := '';
BEGIN
  BEGIN
    SET LOCAL ROLE service_role;
    INSERT INTO public.pre_fight_snapshots (event_id, event_date, fight_id) VALUES (1, current_date, 990001);
    RAISE EXCEPTION USING ERRCODE = 'ZT004', MESSAGE = 'ok';
  EXCEPTION WHEN OTHERS THEN out := out || ' service_insert=' || CASE WHEN SQLSTATE = 'ZT004' THEN 'allowed' ELSE 'err:' || SQLSTATE END;
  END;
  BEGIN
    SET LOCAL ROLE service_role;
    TRUNCATE public.pre_fight_snapshots;
    RAISE EXCEPTION USING ERRCODE = 'ZT004', MESSAGE = 'ok';
  EXCEPTION WHEN OTHERS THEN out := out || ' service_truncate=' || CASE WHEN SQLSTATE = 'ZT004' THEN 'allowed' ELSE 'blocked(' || SQLERRM || ')' END;
  END;
  BEGIN
    SET LOCAL ROLE postgres;
    TRUNCATE public.pre_fight_snapshots;
    RAISE EXCEPTION USING ERRCODE = 'ZT004', MESSAGE = 'ok';
  EXCEPTION WHEN OTHERS THEN out := out || ' owner_truncate=' || CASE WHEN SQLSTATE = 'ZT004' THEN 'allowed' ELSE 'blocked' END;
  END;
  RAISE EXCEPTION 'GUARD_RESULT%', out;
END $g$;
