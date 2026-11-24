-- SR-043 · L10 CoWork registration. Adding an agent to the CoWork object needs ALTER on that object, so the
-- ORGANIZERS may have to run the first statement. Confirm the exact syntax on the account; the Snowsight route is
-- AI & ML > Agents > the CoWork tab. If it fails, the deploy carries on and lists this file for the organizers.
ALTER SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT ADD AGENT SR_DB.SEM.SHARE_RADAR_AGENT;  -- verify syntax

USE ROLE SR_DEV;
GRANT USAGE ON AGENT SR_DB.SEM.SHARE_RADAR_AGENT TO ROLE SR_ANALYST;
GRANT USAGE ON AGENT SR_DB.SEM.SHARE_RADAR_AGENT TO ROLE SR_JUDGE;
