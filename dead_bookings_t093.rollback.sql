-- Rollback for dead_bookings_t093.sql: un-retire the three bookings. Nothing
-- else was changed, so this restores the previous state exactly.
BEGIN;
SET LOCAL lock_timeout = '3s';
UPDATE public.fights SET is_active = true WHERE id IN (43, 46, 8780);
COMMIT;
