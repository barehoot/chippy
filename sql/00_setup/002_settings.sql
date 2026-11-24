-- SR-002 · L1 settings. Every threshold lives here and is read through SR_DB.OPS.CFG('<KEY>').
-- SR-004 replaces the <...> placeholders below with the chosen scope. AS_OF_WEEK_END starts four weeks before
-- the latest real week, so the demo can replay four weeks.
--
-- Rerun safety (docs/decisions.md, B01): a rerun inserts new keys and refreshes descriptions, but it only
-- overwrites a stored value while that value is still a placeholder. Real values set by SR-004, the replay
-- or the admin app are never reset by a redeploy.
USE ROLE SR_DEV;

CREATE TABLE IF NOT EXISTS SR_DB.OPS.SETTINGS (
  SETTING_KEY    VARCHAR(64)   NOT NULL PRIMARY KEY,
  SETTING_VALUE  VARIANT       NOT NULL,
  DESCRIPTION    VARCHAR(500),
  UPDATED_AT     TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

MERGE INTO SR_DB.OPS.SETTINGS t
USING (
  SELECT column1 AS SETTING_KEY, PARSE_JSON(column2) AS SETTING_VALUE, column3 AS DESCRIPTION
  FROM VALUES
    ('AS_OF_WEEK_END',       '"<yyyy-mm-dd>"',      'Replay control: adapter shows weeks up to this date'),
    ('SCOPE_CATEGORY',       '"<category>"',        'Demo category (V_SRC_PRODUCT.CATEGORY)'),
    ('SCOPE_PARENT_MARKET',  '"<market_id>"',       'Parent market whose child retailer markets partition it'),
    ('FOCUS_MANUFACTURER',   '"<manufacturer>"',    'Client whose brands lead the brief'),
    ('COMPARES',             '["L4W_VS_YA","L4W_VS_PP","L12W_VS_YA"]', 'Comparisons evaluated each run'),
    ('MIN_SHARE_PTS',        '0.3',   'Gate: absolute share change, points'),
    ('MIN_VALUE_AT_STAKE',   '50000', 'Gate: |share change| x category sales, local currency'),
    ('MIN_Z',                '2.0',   'Gate: z-score of the change against history'),
    ('TOP_N',                '5',     'Shifts per brief'),
    ('SUPPRESS_RUNS',        '3',     'Look-back runs for repeat suppression'),
    ('SUPPRESS_GROWTH',      '0.2',   'A repeat is shown again if it grew by this fraction'),
    ('ART_STORE_CHG',        '0.05',  'R1: store-count change that marks a coverage change'),
    ('ART_CAT_TDP_JUMP',     '0.15',  'R1 proxy: category TDP log-change'),
    ('ART_CAT_SPPD_FLAT',    '0.03',  'R1 proxy: category velocity log-change treated as flat'),
    ('ART_RESTATE_PCT',      '0.01',  'R3: restated week moving market value by at least this fraction is HIGH'),
    ('ART_RECODE_TOL',       '0.2',   'R4: exit vs entry item sales tolerance'),
    ('ART_RECODE_MIN_SHARE', '0.2',   'R4: exiting and entering sales must each reach this fraction of brand base sales'),
    ('ART_SPIKE_K',          '5',     'R5: std deviations from the trailing 13-week mean'),
    ('EW_DIST_DROP',         '-0.05', 'Early warning: latest-week distribution share vs L4W'),
    ('EW_PRICE_RISE',        '0.03',  'Early warning: latest-week price index vs L4W'),
    ('LLM_MODEL',            '"claude-sonnet-4-5"', 'Confirm availability in the smoke test'),
    ('LLM_FALLBACK_MODEL',   '"mistral-large2"',    'Used after one failure'),
    ('NOTIFY_EMAILS',        '["<analyst>@nielseniq.com"]', 'Verified Snowflake user emails only'),
    ('TEAMS_ENABLED',        'false', 'Stretch: Teams webhook'),
    ('DISPLAY_ALIAS',        'false', 'Mask manufacturer and brand names in UI and briefs'),
    ('MAX_CREDITS_PER_RUN',  '5',     'Above this, ML and TOP_INSIGHTS steps are skipped'),
    ('CURRENCY',             '"INR"', 'Display currency code for briefs and the app')
) s
ON t.SETTING_KEY = s.SETTING_KEY
WHEN MATCHED AND TO_JSON(t.SETTING_VALUE) LIKE '%<%>%' THEN
  UPDATE SET t.SETTING_VALUE = s.SETTING_VALUE, t.DESCRIPTION = s.DESCRIPTION, t.UPDATED_AT = CURRENT_TIMESTAMP()
WHEN MATCHED THEN
  UPDATE SET t.DESCRIPTION = s.DESCRIPTION
WHEN NOT MATCHED THEN
  INSERT (SETTING_KEY, SETTING_VALUE, DESCRIPTION) VALUES (s.SETTING_KEY, s.SETTING_VALUE, s.DESCRIPTION);

-- Read helper for procedures (not used inside dynamic tables, which read OPS.SETTINGS with a scalar subquery)
CREATE OR REPLACE FUNCTION SR_DB.OPS.CFG(K VARCHAR)
RETURNS VARIANT
AS $$ SELECT SETTING_VALUE FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = K $$;

-- Placeholders still to fill (SR-004). Zero rows means the scope is set.
SELECT SETTING_KEY, SETTING_VALUE
FROM SR_DB.OPS.SETTINGS
WHERE TO_JSON(SETTING_VALUE) LIKE '%<%>%'
ORDER BY SETTING_KEY;
