-- SR-054 · L9 delivery integrations. CREATE INTEGRATION needs account privileges, so the ORGANIZERS may have to run
-- this file. Replace the recipient below with verified Snowflake user emails; keep the same list in NOTIFY_EMAILS.
USE ROLE ACCOUNTADMIN;
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS SR_EMAIL_INT
  TYPE = EMAIL
  ENABLED = TRUE
  ALLOWED_RECIPIENTS = ('<analyst>@nielseniq.com');
GRANT USAGE ON INTEGRATION SR_EMAIL_INT TO ROLE SR_APP;

-- The admin app may not run DESCRIBE INTEGRATION, so the allowed list is mirrored in a setting that
-- data.save_setting checks NOTIFY_EMAILS against (B10). Keep it identical to ALLOWED_RECIPIENTS above.
USE ROLE SR_DEV;
MERGE INTO SR_DB.OPS.SETTINGS t
USING (SELECT 'NOTIFY_ALLOWED' AS SETTING_KEY, PARSE_JSON('["<analyst>@nielseniq.com"]') AS SETTING_VALUE,
              'Mirror of SR_EMAIL_INT ALLOWED_RECIPIENTS, used to validate NOTIFY_EMAILS' AS DESCRIPTION) s
ON t.SETTING_KEY = s.SETTING_KEY
WHEN MATCHED THEN UPDATE SET t.SETTING_VALUE = s.SETTING_VALUE, t.DESCRIPTION = s.DESCRIPTION, t.UPDATED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (SETTING_KEY, SETTING_VALUE, DESCRIPTION) VALUES (s.SETTING_KEY, s.SETTING_VALUE, s.DESCRIPTION);

-- Stretch SR-055: Teams webhook. Per the webhook notification docs, the secret part of the Teams workflow URL
-- goes into a secret object, never into this file. Uncomment, fill in at deploy time (not in Git), run as an
-- organizer, then set TEAMS_ENABLED = true in the admin app.
-- USE ROLE ACCOUNTADMIN;
-- CREATE SECRET IF NOT EXISTS SR_DB.OPS.SR_TEAMS_SECRET
--   TYPE = GENERIC_STRING
--   SECRET_STRING = '<secret part of the Teams workflow URL>';
-- CREATE NOTIFICATION INTEGRATION IF NOT EXISTS SR_TEAMS_INT
--   TYPE = WEBHOOK
--   ENABLED = TRUE
--   WEBHOOK_URL = '<workflow URL with its secret replaced by SNOWFLAKE_WEBHOOK_SECRET>'
--   WEBHOOK_SECRET = SR_DB.OPS.SR_TEAMS_SECRET
--   WEBHOOK_BODY_TEMPLATE = '{"text": "SNOWFLAKE_WEBHOOK_MESSAGE"}'
--   WEBHOOK_HEADERS = ('Content-Type' = 'application/json');
-- GRANT USAGE ON INTEGRATION SR_TEAMS_INT TO ROLE SR_APP;
