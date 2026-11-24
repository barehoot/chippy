-- SR-041 · L10 method knowledge base and Cortex Search service (the agent's method_search tool).
-- scripts/load_kb.py splits kb/*.md at "## " headings into rows and refreshes the service.
USE ROLE SR_DEV;
CREATE TABLE IF NOT EXISTS SR_DB.KB.METHOD_DOCS (
  DOC_ID VARCHAR(64) NOT NULL PRIMARY KEY, TITLE VARCHAR NOT NULL, SECTION VARCHAR NOT NULL,
  BODY VARCHAR NOT NULL, SOURCE_FILE VARCHAR NOT NULL, UPDATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE CORTEX SEARCH SERVICE SR_DB.SEM.CSS_METHOD
  ON BODY
  PRIMARY KEY (DOC_ID)
  ATTRIBUTES TITLE, SECTION
  WAREHOUSE = SR_WH_XS
  TARGET_LAG = '1 day'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  AS (SELECT DOC_ID, TITLE, SECTION, BODY, SOURCE_FILE FROM SR_DB.KB.METHOD_DOCS);

-- Check after loading (SR-041 done-when: the right passage for five definition queries):
-- SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('SR_DB.SEM.CSS_METHOD',
--   '{"query": "what is TDP", "columns": ["DOC_ID", "SECTION"], "limit": 3}')):results;
