-- SR-056 · L12 app usage, run after both Streamlit apps are deployed (scripts/deploy_all.sh does).
USE ROLE SR_ADMIN;
GRANT USAGE ON STREAMLIT SR_DB.APP.SHARE_RADAR       TO ROLE SR_ANALYST;   -- judges inherit it
GRANT USAGE ON STREAMLIT SR_DB.APP.SHARE_RADAR_ADMIN TO ROLE SR_DEV;       -- only the team opens the admin app

-- Judge accounts: the organizers create the users; then, as SECURITYADMIN, for each judge:
--   GRANT ROLE SR_JUDGE TO USER <judge_user>;
--   ALTER USER <judge_user> SET DEFAULT_ROLE = SR_JUDGE, DEFAULT_SECONDARY_ROLES = ();
-- No secondary roles means a judge's session holds only SR_JUDGE, so what a judge sees matches T-SEC-01.
