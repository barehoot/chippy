-- SR-022 · L6 share bridge (LMDI, modes A-D) and the L10 refactor: APP.V_BRIDGE_ALL covers every
-- DT_SHARE_COMPARE row, so the agent can explain any brand; SP_BRIDGE stores the run's gated shifts from it.
-- python/sr_lib/bridge.py mirrors this view line for line (T-BR-02).
--
-- share = distribution share x velocity index x price index x promo index (each relative to the category)
-- term pts = 100 x L(SH1, SH0) x LN(F1 / F0); L(a, b) = (a - b) / (LN a - LN b), L(a, a) = a
-- The terms add up to 100 x D_SHARE exactly. RESIDUAL_PTS is NULL when no decomposition was made (B03).
USE ROLE SR_DEV;

CREATE OR REPLACE VIEW SR_DB.APP.V_BRIDGE_ALL
COMMENT = 'Exact share-change bridge for every brand, market and comparison (LMDI, modes A-D)'
AS
-- cap: the newest capability row caps every row's mode ('D' before the first check)
WITH cap AS (
  SELECT COALESCE((SELECT MAX_BRIDGE_MODE FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1), 'D') AS M
),
-- x: each row's status and the best mode its data supports
x AS (
  SELECT c.CMP_CODE, c.MARKET_ID, c.CATEGORY, c.MANUFACTURER, c.BRAND, c.AS_OF_WEEK,
         c.S1, c.S0, c.CS1, c.CS0, c.TDP1, c.TDP0, c.CTDP1, c.CTDP0, c.U1, c.U0, c.CU1, c.CU0,
         c.B1, c.B0, c.CB1, c.CB0, c.BU1, c.BU0, c.CBU1, c.CBU0, c.SH1, c.SH0, c.D_SHARE,
         CASE WHEN NOT (COALESCE(c.CS1, 0) > 0 AND COALESCE(c.CS0, 0) > 0) THEN 'NO_DATA'
              WHEN c.S0 <= 0 AND c.S1 > 0 THEN 'NEW'
              WHEN c.S1 <= 0 AND c.S0 > 0 THEN 'EXIT'
              WHEN c.S1 <= 0 AND c.S0 <= 0 THEN 'NO_DATA'
              ELSE 'OK' END AS STATUS,
         CASE WHEN cap.M = 'A'
                   AND LEAST(c.TDP1, c.TDP0, c.CTDP1, c.CTDP0, c.BU1, c.BU0, c.CBU1, c.CBU0, c.B1, c.B0, c.CB1, c.CB0) > 0 THEN 'A'
              WHEN cap.M IN ('A', 'B') AND LEAST(c.TDP1, c.TDP0, c.CTDP1, c.CTDP0, c.U1, c.U0, c.CU1, c.CU0) > 0 THEN 'B'
              WHEN cap.M IN ('A', 'B', 'C') AND LEAST(c.TDP1, c.TDP0, c.CTDP1, c.CTDP0) > 0 THEN 'C'
              ELSE 'D' END AS MODE
  FROM SR_DB.CORE.DT_SHARE_COMPARE c
  CROSS JOIN cap
),
-- f: the factor indices per period (only where the row is OK) and the LMDI weight
f AS (
  SELECT x.*,
    IFF(MODE <> 'D', TDP1 / NULLIF(CTDP1, 0), NULL) AS DS1,
    IFF(MODE <> 'D', TDP0 / NULLIF(CTDP0, 0), NULL) AS DS0,
    CASE WHEN STATUS = 'OK' THEN
      CASE MODE WHEN 'A' THEN (BU1 / NULLIF(TDP1, 0)) / NULLIF(CBU1 / NULLIF(CTDP1, 0), 0)
                WHEN 'B' THEN (U1  / NULLIF(TDP1, 0)) / NULLIF(CU1  / NULLIF(CTDP1, 0), 0)
                WHEN 'C' THEN (S1  / NULLIF(TDP1, 0)) / NULLIF(CS1  / NULLIF(CTDP1, 0), 0) END END AS V1,
    CASE WHEN STATUS = 'OK' THEN
      CASE MODE WHEN 'A' THEN (BU0 / NULLIF(TDP0, 0)) / NULLIF(CBU0 / NULLIF(CTDP0, 0), 0)
                WHEN 'B' THEN (U0  / NULLIF(TDP0, 0)) / NULLIF(CU0  / NULLIF(CTDP0, 0), 0)
                WHEN 'C' THEN (S0  / NULLIF(TDP0, 0)) / NULLIF(CS0  / NULLIF(CTDP0, 0), 0) END END AS V0,
    CASE WHEN STATUS = 'OK' THEN
      CASE MODE WHEN 'A' THEN (B1 / NULLIF(BU1, 0)) / NULLIF(CB1 / NULLIF(CBU1, 0), 0)
                WHEN 'B' THEN (S1 / NULLIF(U1, 0))  / NULLIF(CS1 / NULLIF(CU1, 0), 0) END END AS PI1,
    CASE WHEN STATUS = 'OK' THEN
      CASE MODE WHEN 'A' THEN (B0 / NULLIF(BU0, 0)) / NULLIF(CB0 / NULLIF(CBU0, 0), 0)
                WHEN 'B' THEN (S0 / NULLIF(U0, 0))  / NULLIF(CS0 / NULLIF(CU0, 0), 0) END END AS PI0,
    IFF(STATUS = 'OK' AND MODE = 'A', (S1 / NULLIF(B1, 0)) / NULLIF(CS1 / NULLIF(CB1, 0), 0), NULL) AS PRI1,
    IFF(STATUS = 'OK' AND MODE = 'A', (S0 / NULLIF(B0, 0)) / NULLIF(CS0 / NULLIF(CB0, 0), 0), NULL) AS PRI0,
    IFF(STATUS = 'OK' AND MODE <> 'D',
        IFF(ABS(SH1 - SH0) < 1e-12, SH1, (SH1 - SH0) / (LN(SH1) - LN(SH0))), NULL) AS L
  FROM x
)
SELECT CMP_CODE, MARKET_ID, CATEGORY, MANUFACTURER, BRAND, AS_OF_WEEK, MODE, STATUS, SH1, SH0, D_SHARE,
       L                         AS LMDI_WEIGHT,
       100 * L * LN(DS1 / DS0)   AS DIST_PTS,
       100 * L * LN(V1 / V0)     AS VELOCITY_PTS,
       100 * L * LN(PI1 / PI0)   AS PRICE_PTS,
       100 * L * LN(PRI1 / PRI0) AS PROMO_PTS,
       IFF(L IS NULL, NULL,
           100 * D_SHARE - COALESCE(DIST_PTS, 0) - COALESCE(VELOCITY_PTS, 0)
                         - COALESCE(PRICE_PTS, 0) - COALESCE(PROMO_PTS, 0)) AS RESIDUAL_PTS,
       DS1, DS0, PI1, PI0, PRI1, PRI0,
       CASE STATUS WHEN 'NEW'     THEN 'New listing: no sales in the base period'
                   WHEN 'EXIT'    THEN 'Delisted: no sales in the current period'
                   WHEN 'NO_DATA' THEN 'Category total missing in one period'
                   ELSE IFF(MODE = 'D', 'No distribution data: share change only', NULL) END AS NOTE
FROM f;

CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_BRIDGE(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n NUMBER DEFAULT 0;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=BRIDGE''';
  DELETE FROM SR_DB.APP.SHARE_BRIDGE WHERE RUN_ID = :P_RUN_ID;
  INSERT INTO SR_DB.APP.SHARE_BRIDGE
    (RUN_ID, SHIFT_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, MODE, STATUS, SH1, SH0, D_SHARE, LMDI_WEIGHT,
     DIST_PTS, VELOCITY_PTS, PRICE_PTS, PROMO_PTS, RESIDUAL_PTS, DS1, DS0, PI1, PI0, PRI1, PRI0, NOTE)
  SELECT :P_RUN_ID, sc.SHIFT_ID, b.CMP_CODE, b.MARKET_ID, b.CATEGORY, b.BRAND, b.MODE, b.STATUS,
         b.SH1, b.SH0, b.D_SHARE, b.LMDI_WEIGHT, b.DIST_PTS, b.VELOCITY_PTS, b.PRICE_PTS, b.PROMO_PTS, b.RESIDUAL_PTS,
         b.DS1, b.DS0, b.PI1, b.PI0, b.PRI1, b.PRI0, b.NOTE
  FROM SR_DB.APP.SHIFT_CANDIDATE sc
  JOIN SR_DB.APP.V_BRIDGE_ALL b
    ON b.CMP_CODE = sc.CMP_CODE AND b.MARKET_ID = sc.MARKET_ID AND b.CATEGORY = sc.CATEGORY AND b.BRAND = sc.BRAND
   AND EQUAL_NULL(b.MANUFACTURER, sc.MANUFACTURER)
  WHERE sc.RUN_ID = :P_RUN_ID AND sc.PASSED_GATES;
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;
