-- t088_replica_bootstrap.sql — throwaway local replica only (T-088 rehearsal). Mirrors Supabase's role layout, auth.uid() and production's pg_default_acl. NEVER apply to a real database.
-- Throwaway local replica only. Mirrors Supabase's role layout.
CREATE ROLE postgres NOLOGIN;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
CREATE ROLE supabase_auth_admin NOLOGIN;
GRANT anon, authenticated, service_role TO postgres;
CREATE EXTENSION pgcrypto;
GRANT USAGE, CREATE ON SCHEMA public TO postgres;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role, supabase_auth_admin;
CREATE SCHEMA auth;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role, postgres, supabase_auth_admin;
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(coalesce(current_setting('request.jwt.claim.sub', true),
                         (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')), '')::uuid $$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT current_setting('request.jwt.claims', true)::jsonb ->> 'role' $$;
CREATE TABLE auth.users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text);
GRANT INSERT, SELECT ON auth.users TO supabase_auth_admin;
-- production's pg_default_acl for postgres in public
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
