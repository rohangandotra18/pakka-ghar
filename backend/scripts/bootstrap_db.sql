-- Run once as a superuser. Creates the two roles the backend uses and the database.
--   pakka         logs in for the web process and owns the tables. Row-level security is FORCEd on every
--                 business table, so even the owner is filtered by app.current_org / app.current_party.
--   pakka_system  cannot log in; BYPASSRLS. The web process switches to it with SET LOCAL ROLE only for
--                 webhooks, scheduled jobs, public listing aggregates and seeding (apps.core.rls.system).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pakka') THEN
    CREATE ROLE pakka LOGIN CREATEDB PASSWORD 'pakka' NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pakka_system') THEN
    CREATE ROLE pakka_system NOLOGIN BYPASSRLS;
  END IF;
END $$;
GRANT pakka_system TO pakka;
SELECT 'CREATE DATABASE pakka OWNER pakka' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'pakka')\gexec
