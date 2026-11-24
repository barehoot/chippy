-- SR-029 · L6 what-if: the mechanical share effect of moving one lever, all other levers held.
--   P_LEVER  DISTRIBUTION (modes A-C) or PROMO (mode A only)
--   P_TARGET BASE (restore the base-period level) or a signed percentage such as +10%
--   new share = SH1 x ratio, ratio = DS0 / DS1 (or PRI0 / PRI1), or 1 + pct
-- Returns the L6 object, or an L13 error object (BAD_INPUT, NOT_FOUND, NO_DATA). Not a pipeline step.
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_WHAT_IF(P_SHIFT_ID VARCHAR, P_LEVER VARCHAR, P_TARGET VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  lever  VARCHAR DEFAULT UPPER(TRIM(COALESCE(P_LEVER, '')));
  target VARCHAR DEFAULT UPPER(REPLACE(TRIM(COALESCE(P_TARGET, '')), ' ', ''));
  pct    FLOAT;
  ratio  FLOAT;
  n      NUMBER DEFAULT 0;
  sh1    FLOAT;
  ds1    FLOAT;
  ds0    FLOAT;
  pri1   FLOAT;
  pri0   FLOAT;
  mode   VARCHAR;
  brand  VARCHAR;
  market VARCHAR;
  cmp    VARCHAR;
BEGIN
  IF (lever NOT IN ('DISTRIBUTION', 'PROMO')) THEN
    RETURN OBJECT_CONSTRUCT('error', 'BAD_INPUT', 'detail', 'Lever must be DISTRIBUTION or PROMO');
  END IF;
  IF (target <> 'BASE') THEN
    pct := TRY_TO_DOUBLE(REPLACE(REPLACE(target, '%', ''), '+', '')) / 100;
    IF (pct IS NULL) THEN
      RETURN OBJECT_CONSTRUCT('error', 'BAD_INPUT', 'detail', 'Target must be BASE or a signed percentage such as +10%');
    END IF;
  END IF;

  SELECT COUNT(*) INTO :n FROM SR_DB.APP.SHARE_BRIDGE WHERE SHIFT_ID = :P_SHIFT_ID;
  IF (n = 0) THEN
    RETURN OBJECT_CONSTRUCT('error', 'NOT_FOUND', 'detail', 'No bridge row for this shift');
  END IF;
  SELECT b.SH1, b.DS1, b.DS0, b.PRI1, b.PRI0, b.MODE, b.BRAND, COALESCE(m.MARKET_NAME, b.MARKET_ID), b.CMP_CODE
    INTO :sh1, :ds1, :ds0, :pri1, :pri0, :mode, :brand, :market, :cmp
    FROM SR_DB.APP.SHARE_BRIDGE b
    LEFT JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = b.MARKET_ID
   WHERE b.SHIFT_ID = :P_SHIFT_ID
   LIMIT 1;

  IF (lever = 'DISTRIBUTION') THEN
    IF (ds1 IS NULL OR ds0 IS NULL OR ds1 = 0) THEN
      RETURN OBJECT_CONSTRUCT('error', 'NO_DATA', 'detail', 'No distribution share for this shift (bridge mode ' || mode || ')');
    END IF;
    ratio := IFF(target = 'BASE', ds0 / ds1, 1 + pct);
  ELSE
    IF (mode <> 'A' OR pri1 IS NULL OR pri0 IS NULL OR pri1 = 0) THEN
      RETURN OBJECT_CONSTRUCT('error', 'NO_DATA', 'detail', 'The promo lever needs bridge mode A; this shift is mode ' || mode);
    END IF;
    ratio := IFF(target = 'BASE', pri0 / pri1, 1 + pct);
  END IF;

  RETURN OBJECT_CONSTRUCT('brand', brand, 'market', market, 'cmp_code', cmp, 'lever', lever, 'target', P_TARGET,
                          'share_now_pts', 100 * sh1, 'share_if_pts', 100 * sh1 * ratio,
                          'delta_pts', 100 * sh1 * (ratio - 1),
                          'assumption', 'Other levers held constant; mechanical, not a forecast');
END;
$$;
