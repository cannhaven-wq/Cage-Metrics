-- =============================================================================
-- Beta premium access
-- =============================================================================
-- During beta (until paid launches), every account holder gets the premium
-- experience automatically. This is implemented as a separate boolean column
-- on profiles rather than flipping the `tier` enum to 'premium' for everyone,
-- so that:
--   - We preserve the canonical `tier` field for post-launch billing logic
--   - We can flip beta_premium off later without losing any user's actual
--     paid tier state
--   - The auth layer can OR the two: effective_premium = (tier='premium' OR beta_premium=true)
--
-- Re-run safe.
-- =============================================================================

-- 1. Add the column. Defaults to true so any new rows automatically get it,
--    even if the trigger somehow doesn't fire. Cheap insurance.
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS beta_premium boolean NOT NULL DEFAULT true;

-- 2. Backfill: every existing profile gets beta_premium = true.
--    Safe to run repeatedly — already-true rows stay true.
UPDATE profiles
SET beta_premium = true
WHERE beta_premium = false OR beta_premium IS NULL;

-- 3. Update the new-user trigger so future signups get it set.
--    The default already covers this, but being explicit in the trigger means
--    if you ever change the default to false, signups still work as expected.
--
--    NOTE: Replace the function body to match your existing trigger. The exact
--    function name in your project may differ — confirm with:
--      SELECT trigger_name, event_object_table, action_statement
--      FROM information_schema.triggers
--      WHERE event_object_table = 'users' AND trigger_schema = 'auth';
--    Common name is `handle_new_user`. Adjust below if yours is different.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, display_name, tier, beta_premium)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'display_name', NULL),
    'free',
    true   -- beta access for everyone during the beta window
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

-- The trigger itself doesn't need to be re-created if it already exists —
-- replacing the function above is enough. But include this for fresh installs:
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- 4. Sanity check — verify no rows are left at false
DO $$
DECLARE
  remaining int;
BEGIN
  SELECT COUNT(*) INTO remaining FROM profiles WHERE beta_premium = false;
  IF remaining > 0 THEN
    RAISE WARNING 'After backfill, % profiles still have beta_premium = false', remaining;
  ELSE
    RAISE NOTICE 'Backfill complete — all profiles have beta_premium = true';
  END IF;
END $$;
