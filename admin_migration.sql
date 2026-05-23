-- Cannon Fight Lab — admin role migration
--
-- Adds an is_admin flag to profiles and grants it to the founder account
-- (cannhaven@gmail.com). Admin access is intentionally minimal: it's the only
-- way to see the prediction_indicators table on predictor.html. Non-admin
-- signed-in users see exactly what they saw before.
--
-- Apply via Supabase SQL editor. Safe to re-run.

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- Grant admin to the founder. If the profile row doesn't exist yet (e.g. the
-- user signed up but the trigger that creates profiles hasn't fired), this
-- update is a no-op — re-run after the row appears.
UPDATE profiles
   SET is_admin = TRUE
 WHERE email = 'cannhaven@gmail.com';

-- Lock down the is_admin column at the SQL grant level. Even if the existing
-- row-level UPDATE policy on profiles allows users to update their own row,
-- this REVOKE prevents them from touching is_admin specifically. Admin
-- elevation can only happen via service_role (Supabase dashboard SQL editor).
REVOKE UPDATE (is_admin) ON profiles FROM authenticated, anon;

-- Verify by signing in as cannhaven@gmail.com and running in the dashboard:
--   SELECT id, email, is_admin FROM profiles WHERE email = 'cannhaven@gmail.com';
--
-- To grant admin to another user later:
--   UPDATE profiles SET is_admin = TRUE WHERE email = '<their email>';
