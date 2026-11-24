"""Run the repository's own SQL on DuckDB against synthetic data (local verification, no Snowflake needed).

What runs is the SQL text in sql/ and tests/sql/, transpiled from Snowflake to DuckDB with sqlglot, after three
mechanical substitutions: settings reads become literals, procedure bind variables (:P_RUN_ID, :parent ...)
become literals, and the dynamic tables become plain tables built in dependency order. Snowflake-only parts
(scripting control flow, ML classes, HASH_AGG, tasks, the agent) are out of scope here and are covered on the
account by the T-* tests. The point: the set-based logic the brief depends on (share grid, gates, bridge, retailer
split, flow, ranking, early warning, artefact rules R1/R2/R4/R5/R6) executes and passes its own SQL tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp

import synthetic as syn

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "local-001"
SETTINGS = {
    "AS_OF_WEEK_END": syn.AS_OF.isoformat(), "SCOPE_CATEGORY": syn.CATEGORY, "SCOPE_PARENT_MARKET": syn.PARENT,
    "FOCUS_MANUFACTURER": "Acme Foods", "COMPARES": ["L4W_VS_YA", "L4W_VS_PP", "L12W_VS_YA"],
    "MIN_SHARE_PTS": 0.3, "MIN_VALUE_AT_STAKE": 50000, "MIN_Z": 2.0, "TOP_N": 5, "SUPPRESS_RUNS": 3,
    "SUPPRESS_GROWTH": 0.2, "ART_STORE_CHG": 0.05, "ART_CAT_TDP_JUMP": 0.15, "ART_CAT_SPPD_FLAT": 0.03,
    "ART_RESTATE_PCT": 0.01, "ART_RECODE_TOL": 0.2, "ART_RECODE_MIN_SHARE": 0.2, "ART_SPIKE_K": 5,
    "EW_DIST_DROP": -0.05, "EW_PRICE_RISE": 0.03, "CURRENCY": "INR", "MAX_CREDITS_PER_RUN": 5,
    "DISPLAY_ALIAS": False, "LLM_MODEL": "claude-sonnet-4-5", "LLM_FALLBACK_MODEL": "mistral-large2",
}
BINDS = {"P_RUN_ID": RUN_ID, "parent": syn.PARENT, "category": syn.CATEGORY}


# ---- splitting and rewriting -------------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    i = line.find("--")
    while i >= 0:
        if line[:i].count("'") % 2 == 0:
            return line[:i]
        i = line.find("--", i + 2)
    return line


def statements(text: str) -> list[str]:
    """Top-level statements; a $$ ... $$ body stays inside its statement."""
    out, cur, in_body = [], [], False
    for raw in text.splitlines():
        line = raw if in_body else _strip_comment(raw)
        if line.count("$$") % 2 == 1:
            in_body = not in_body
        cur.append(line)
        if not in_body and line.rstrip().endswith(";"):
            stmt = "\n".join(cur).strip().rstrip(";").strip()
            if stmt:
                out.append(stmt)
            cur = []
    return out


def body_statements(stmt: str) -> list[str]:
    """INSERT/UPDATE statements inside a procedure's $$ body, comments removed."""
    m = re.search(r"\$\$(.*)\$\$", stmt, re.S)
    if not m:
        return []
    out, cur = [], []
    for raw in m.group(1).splitlines():
        line = _strip_comment(raw)
        if not cur and not re.match(r"\s*(INSERT INTO|WITH)\b", line):
            continue
        cur.append(line)
        if line.rstrip().endswith(";"):
            out.append("\n".join(cur).strip().rstrip(";"))
            cur = []
    # statements inside an EXECUTE IMMEDIATE string (R1's universe branch) are dynamic SQL: out of scope here
    return [s for s in out if s.lstrip().startswith("INSERT INTO") and "USING (" not in s]


def _literal(value, casts: list[str]) -> str:
    if isinstance(value, list):
        return "ARRAY_CONSTRUCT(" + ", ".join(f"'{v}'" for v in value) + ")"
    if isinstance(value, bool):
        lit = "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        lit = repr(value)
    else:
        lit = "'" + str(value).replace("'", "''") + "'"
    for c in casts:
        if c.upper() not in ("VARCHAR", "ARRAY", "BOOLEAN"):
            lit = f"CAST({lit} AS {c})"
    return lit


def substitute(sql: str, binds: dict | None = None) -> str:
    """Settings reads -> literals; :binds -> literals."""
    sql = re.sub(r"\(\s*SELECT\s+SETTING_VALUE((?:::\w+)*)\s+FROM\s+SR_DB\.OPS\.SETTINGS\s+WHERE\s+SETTING_KEY\s*=\s*'(\w+)'\s*\)",
                 lambda m: _literal(SETTINGS[m.group(2)], m.group(1).split("::")[1:]), sql)
    sql = re.sub(r"SELECT\s+SETTING_VALUE((?:::\w+)*)\s+AS\s+(\w+)\s+FROM\s+SR_DB\.OPS\.SETTINGS\s+WHERE\s+SETTING_KEY\s*=\s*'(\w+)'",
                 lambda m: f"SELECT {_literal(SETTINGS[m.group(3)], m.group(1).split('::')[1:])} AS {m.group(2)}", sql)
    sql = re.sub(r"SR_DB\.OPS\.CFG\('(\w+)'\)((?:::\w+)*)",
                 lambda m: _literal(SETTINGS[m.group(1)], m.group(2).split("::")[1:]), sql)
    sql = sql.replace("::VARIANT", "")
    for k, v in (binds or {}).items():
        sql = re.sub(rf":{k}\b", "'" + str(v).replace("'", "''") + "'", sql)
    return sql


def _name_values(tree: exp.Expression) -> exp.Expression:
    """Snowflake names VALUES columns column1, column2 ...; DuckDB needs them spelled out."""
    for v in tree.find_all(exp.Values):
        first = v.expressions[0] if v.expressions else None
        n = len(first.expressions) if isinstance(first, exp.Tuple) else 1
        alias = v.args.get("alias")
        if alias is None or not alias.columns:
            v.set("alias", exp.TableAlias(this=exp.to_identifier(alias.name if alias else "_v"),
                                          columns=[exp.to_identifier(f"column{i + 1}") for i in range(n)]))
    return tree


# DuckDB-only typing differences, applied after transpiling (the Snowflake SQL is correct as written)
DUCKDB_FIXES = [
    (re.compile(r"CHR\(64 \+ N\)"), "CHR(CAST(64 + N AS INTEGER))"),
    # Snowflake's v:key::VARCHAR yields the bare string; DuckDB's -> keeps the JSON quotes, ->> does not
    (re.compile(r"CAST\(([\w.]+) -> '(\$\.\w+)' AS TEXT\)"), r"(\1 ->> '\2')"),
]


def _structs_to_json(tree: exp.Expression) -> exp.Expression:
    """OBJECT_CONSTRUCT becomes a DuckDB struct; VARIANT columns are JSON, so serialise the outermost structs."""
    def wrap(node):
        if isinstance(node, exp.Struct) and not isinstance(node.parent, (exp.Struct, exp.Anonymous)):
            return exp.func("TO_JSON", node.copy())
        return node
    return tree.transform(wrap, copy=False)


def to_duckdb(sql: str) -> str:
    tree = sqlglot.parse_one(sql, read="snowflake")
    out = _structs_to_json(_name_values(tree)).sql(dialect="duckdb")
    for pattern, repl in DUCKDB_FIXES:
        out = pattern.sub(repl, out)
    return out


# ---- the pipeline ------------------------------------------------------------------------------------------

@dataclass
class Local:
    con: duckdb.DuckDBPyConnection
    log: list[tuple[str, str, str]] = field(default_factory=list)       # (object, status, message)

    def run(self, label: str, sql: str, binds: dict | None = None, must: bool = True) -> None:
        try:
            self.con.execute(to_duckdb(substitute(sql, binds)))
            self.log.append((label, "OK", ""))
        except Exception as e:                                          # noqa: BLE001
            self.log.append((label, "FAILED", str(e).splitlines()[0][:300]))
            if must:
                raise RuntimeError(f"{label}: {e}") from e

    def df(self, sql: str, binds: dict | None = None):
        return self.con.execute(to_duckdb(substitute(sql, binds))).fetchdf()


def _file(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _create(stmt: str) -> tuple[str, str] | None:
    """(name, CREATE TABLE/VIEW statement) for a dynamic table, view or table DDL."""
    m = re.match(r"CREATE OR REPLACE DYNAMIC TABLE (\S+).*?\nAS\n(.*)", stmt, re.S)
    if m:
        return m.group(1), f"CREATE OR REPLACE TABLE {m.group(1)} AS\n{m.group(2)}"
    m = re.match(r"CREATE OR REPLACE VIEW (\S+)\s*(?:\([^)]*\))?\s*(?:COMMENT = '(?:[^']|'')*')?\s*AS\s*\n(.*)", stmt, re.S)
    if m:
        return m.group(1), f"CREATE OR REPLACE VIEW {m.group(1)} AS\n{m.group(2)}"
    m = re.match(r"CREATE TABLE IF NOT EXISTS (\S+)", stmt)
    if m:
        return m.group(1), stmt
    return None


def build() -> Local:
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS SR_DB")
    for s in ("SRC", "CORE", "ML", "APP", "SEM", "OPS", "KB", "TEST"):
        con.execute(f"CREATE SCHEMA SR_DB.{s}")
    loc = Local(con)

    # source contract (the adapter's NIQ mapping is replaced by synthetic tables)
    con.execute("""CREATE TABLE SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL (WEEK_END_DATE DATE, MARKET_ID VARCHAR, PRODUCT_ID VARCHAR,
                   VALUE_SALES DECIMAL(18,2), VOLUME_SALES DECIMAL(18,3), UNIT_SALES DECIMAL(18,3), ACV_DIST_PCT DECIMAL(9,4),
                   BASE_VALUE_SALES DECIMAL(18,2), BASE_UNIT_SALES DECIMAL(18,3), STORES_SELLING INTEGER, DATA_VERSION VARCHAR)""")
    con.executemany("INSERT INTO SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL VALUES (?,?,?,?,?,?,?,?,?,?,?)", syn.facts())
    con.execute("CREATE TABLE SR_DB.SRC.V_SRC_PRODUCT (PRODUCT_ID VARCHAR, ITEM_DESC VARCHAR, BRAND VARCHAR, "
                "MANUFACTURER VARCHAR, CATEGORY VARCHAR, SEGMENT VARCHAR, PACK_SIZE VARCHAR, IS_PRIVATE_LABEL BOOLEAN)")
    con.executemany("INSERT INTO SR_DB.SRC.V_SRC_PRODUCT VALUES (?,?,?,?,?,?,?,?)", syn.products())
    con.execute("CREATE TABLE SR_DB.SRC.V_SRC_MARKET (MARKET_ID VARCHAR, MARKET_NAME VARCHAR, MARKET_LEVEL VARCHAR, "
                "PARENT_MARKET_ID VARCHAR, RETAILER VARCHAR, CHANNEL VARCHAR, REGION VARCHAR)")
    con.executemany("INSERT INTO SR_DB.SRC.V_SRC_MARKET VALUES (?,?,?,?,?,?,?)", syn.markets())

    # the replay view: the second statement of 101 (the first names NIQ objects)
    replay = [s for s in statements(_file("sql/10_src/101_adapter_views.sql")) if "V_SRC_FACT_WEEKLY\n" in s][0]
    name, ddl = _create(replay)
    loc.run(name, ddl)

    # ops and result tables
    for rel in ("sql/00_setup/003_ops_tables.sql", "sql/10_src/102_capability.sql", "sql/40_app/401_result_tables.sql",
                "tests/sql/000_fixtures.sql"):
        for stmt in statements(_file(rel)):
            if stmt.startswith("CREATE TABLE"):
                loc.run(_create(stmt)[0], re.sub(r"\bVARIANT\b", "JSON", stmt))   # DuckDB's own VARIANT differs

    # core dynamic tables and the grid view, in file order (= dependency order)
    for rel in sorted((ROOT / "sql/20_core").glob("*.sql")):
        for stmt in statements(rel.read_text()):
            c = _create(stmt)
            if c:
                loc.run(*c)

    # capability: the procedure's INSERT, with the information-schema probe for the optional view answered here
    cap = body_statements([s for s in statements(_file("sql/10_src/102_capability.sql")) if "PROCEDURE" in s][0])[0]
    cap = re.sub(r"\(SELECT COUNT\(\*\) > 0 FROM SR_DB\.INFORMATION_SCHEMA\.VIEWS.*?'V_SRC_MARKET_UNIVERSE'\)", "FALSE", cap, flags=re.S)
    loc.run("SP_CAPABILITY_CHECK", cap)

    # the run under test, as SP_RUN_WEEK's OPEN step writes it
    con.execute(f"""INSERT INTO SR_DB.OPS.RUN_LOG (RUN_ID, TRIGGER_TYPE, AS_OF_WEEK, SCOPE_KEY, STATUS, STARTED_AT)
                    VALUES ('{RUN_ID}', 'MANUAL', DATE '{syn.AS_OF}', 'Biscuits|M0|Acme Foods', 'SUCCEEDED', now())""")

    # V_BRIDGE_ALL, then the step procedures' set-based bodies in run order
    for stmt in statements(_file("sql/40_app/404_sp_bridge.sql")):
        c = _create(stmt)
        if c:
            loc.run(*c)
    steps = [("SP_DETECT_SHIFTS", "sql/40_app/403_sp_detect_shifts.sql", None),
             ("SP_BRIDGE", "sql/40_app/404_sp_bridge.sql", None),
             ("SP_ARTEFACT", "sql/40_app/405_sp_artefact.sql", "R3"),       # R3 needs HASH_AGG snapshots
             ("SP_RANK", "sql/40_app/406_sp_rank.sql", None),
             ("SP_WHERE", "sql/40_app/407_sp_where.sql", None),
             ("SP_FLOW", "sql/40_app/408_sp_flow.sql", None),
             ("SP_EARLY_WARNING", "sql/40_app/409_sp_early_warning.sql", None)]
    for label, rel, skip in steps:
        proc = [s for s in statements(_file(rel)) if "CREATE OR REPLACE PROCEDURE" in s][0]
        for i, body in enumerate(body_statements(proc)):
            if skip and "R3_RESTATE" in body:
                continue
            loc.run(f"{label}#{i + 1}", body, BINDS)

    # UI and semantic-layer views compile and read
    for rel in ("sql/40_app/415_ui_objects.sql", "sql/50_sem/501_v_sem_views.sql"):
        for stmt in statements(_file(rel)):
            c = _create(stmt)
            if c:
                loc.run(*c)
    return loc


SQL_TESTS = ["T-CORE-01", "T-CORE-02", "T-CORE-04", "T-DET-01", "T-DET-02", "T-BR-01", "T-BR-03", "T-BR-04",
             "T-ART-01", "T-ART-02", "T-ART-04", "T-RANK-01", "T-WH-01", "T-FLOW-01", "T-FLOW-02", "T-EW-01"]


def run_sql_test(loc: Local, test_id: str) -> tuple[bool, int, str]:
    """Run tests/sql/<id>.sql's INSERT ... SELECT with the session variables as literals; read its result row."""
    text = _file(f"tests/sql/{test_id}.sql")
    stmt = [s for s in statements(text) if s.startswith("INSERT INTO SR_DB.OPS.TEST_RESULT")][0]
    for var, val in (("TEST_RUN_ID", "local-test"), ("TEST_ID", test_id), ("RUN_UNDER_TEST", RUN_ID)):
        stmt = stmt.replace(f"${var}", f"'{val}'")
    stmt = re.sub(r"\(SELECT ARRAY_AGG\(OBJECT_CONSTRUCT\(\*\)\) FROM \(SELECT \* FROM failures LIMIT 20\)\)",
                  "(SELECT TO_JSON(ARRAY_AGG(f)) FROM (SELECT * FROM failures LIMIT 20) f)", stmt)
    loc.run(test_id, stmt)
    row = loc.con.execute("SELECT PASSED, FAILURES, CAST(DETAIL AS VARCHAR) FROM SR_DB.OPS.TEST_RESULT "
                          f"WHERE TEST_ID = '{test_id}' ORDER BY RAN_AT DESC LIMIT 1").fetchone()
    return bool(row[0]), int(row[1]), (row[2] or "")[:500]
