-- SR-043 · L10 the Ask-Why agent. It answers from the same tables the brief was written from and never computes a
-- number: every figure comes from a tool result. Routing rules are in the orchestration instructions.
-- After any change: rerun 505_cowork.sql grants, then python3 eval/run_eval.py --tools-only, then the full golden set.
-- Some accounts want "name" instead of "search_service" for the search resource; keep whichever the account accepts.
USE ROLE SR_DEV;
CREATE OR REPLACE AGENT SR_DB.SEM.SHARE_RADAR_AGENT
  COMMENT = 'Ask-Why agent for competitive share shifts'
  PROFILE = '{"display_name": "Share Radar", "color": "blue"}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto
  orchestration:
    budget:
      seconds: 60
      tokens: 16000
  instructions:
    orchestration: >
      You explain competitive market share changes for NIQ client-service analysts.
      For any question about why share changed, call get_share_bridge first, then check_artefact.
      For who gained or lost the share, call share_flow. For lever scenarios, call what_if and repeat its assumption.
      For what changed this week, call latest_brief.
      For any other number use share_analyst. For definitions or method use method_search.
      Never calculate, round or estimate numbers yourself; quote them exactly as tools return them.
      If a tool returns an error or nothing, say so. Never fill the gap. If it returns AMBIGUOUS, ask which of the candidates the user means.
      If no tool can answer (for example a forecast, or an average of shares across markets), say you cannot answer that and suggest a supported question.
    response: >
      Lead with the answer in one sentence and name the period comparison.
      If check_artefact returns POSSIBLE_DATA_EFFECT, say so in the first sentence.
      Then at most four bullets: drivers in share points, where it happened, who gained, data status.
      Say "share points" for share changes, never "percent".
    sample_questions:
      - question: "Why did <brand> lose share in <market> in the last 4 weeks vs year ago?"
      - question: "Who took the share <brand> lost in <market>?"
      - question: "Is the <brand> drop real or a data effect?"
      - question: "What if <brand> restored distribution to last year's level?"
  tools:
    - tool_spec:
        type: "cortex_analyst_text_to_sql"
        name: "share_analyst"
        description: "Governed share, sales, distribution and share-change numbers by brand, market and period"
    - tool_spec:
        type: "cortex_search"
        name: "method_search"
        description: "Definitions and method: ACV, TDP, velocity, the share bridge, artefact rules, period codes"
    - tool_spec:
        type: "generic"
        name: "get_share_bridge"
        description: "Exact share-change bridge (distribution, velocity, price, promo, in share points) and top retailer contributions for one brand, market and comparison"
        input_schema:
          type: "object"
          properties:
            p_brand: {type: "string", description: "Brand name as the user wrote it"}
            p_market: {type: "string", description: "Market or retailer name"}
            p_cmp_code: {type: "string", description: "L4W_VS_YA, L4W_VS_PP, L12W_VS_YA or L52W_VS_YA; default L4W_VS_YA"}
          required: ["p_brand", "p_market", "p_cmp_code"]
    - tool_spec:
        type: "generic"
        name: "check_artefact"
        description: "Whether a share change could be a data effect (coverage, feed, restatement, recode, spike, gap), with evidence"
        input_schema:
          type: "object"
          properties:
            p_market: {type: "string", description: "Market or retailer name"}
            p_cmp_code: {type: "string", description: "Comparison code"}
            p_brand: {type: "string", description: "Brand name, or empty for market-level rules only"}
          required: ["p_market", "p_cmp_code", "p_brand"]
    - tool_spec:
        type: "generic"
        name: "share_flow"
        description: "Which brands gained the share a brand lost, or lost the share it gained, in share points (proportional allocation)"
        input_schema:
          type: "object"
          properties:
            p_brand: {type: "string", description: "Brand name"}
            p_market: {type: "string", description: "Market or retailer name"}
            p_cmp_code: {type: "string", description: "Comparison code"}
          required: ["p_brand", "p_market", "p_cmp_code"]
    - tool_spec:
        type: "generic"
        name: "what_if"
        description: "Mechanical share impact of restoring or changing distribution or promo for a brand"
        input_schema:
          type: "object"
          properties:
            p_brand: {type: "string", description: "Brand name"}
            p_market: {type: "string", description: "Market or retailer name"}
            p_lever: {type: "string", description: "DISTRIBUTION or PROMO"}
            p_target: {type: "string", description: "BASE to restore the year-ago level, or a signed percentage such as +10%"}
          required: ["p_brand", "p_market", "p_lever", "p_target"]
    - tool_spec:
        type: "generic"
        name: "latest_brief"
        description: "Headline and top shifts of the latest published brief"
        input_schema:
          type: "object"
          properties:
            p_scope: {type: "string", description: "Scope key, or empty for the default scope"}
          required: ["p_scope"]
  tool_resources:
    share_analyst:
      semantic_view: "SR_DB.SEM.SV_SHARE"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    method_search:
      search_service: "SR_DB.SEM.CSS_METHOD"
      max_results: 4
    get_share_bridge:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_GET_SHARE_BRIDGE"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    check_artefact:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_CHECK_ARTEFACT"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    share_flow:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_SHARE_FLOW"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    what_if:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_WHAT_IF"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    latest_brief:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_LATEST_BRIEF"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
  $$;

-- Sample check (SR-043): ask the four sample questions and list the tools each answer called, e.g.
-- SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN('SR_DB.SEM.SHARE_RADAR_AGENT',
--   '{"messages": [{"role": "user", "content": [{"type": "text", "text": "Why did <brand> lose share in <market> in the last 4 weeks vs year ago?"}]}]}');
-- python3 eval/run_eval.py --connection sr --only G01,G09,G14,G18 does the same and scores the answers.

-- Stretch SR-045 (one skill, two agents): attach the share-methodology skill that builds this repo to the agent.
-- 1) PUT the skill:   snow stage copy .cortex/skills/share-methodology/SKILL.md @SR_DB.SEM.SKILLS/share-methodology/ -c sr
-- 2) Re-specify the live version with a skills entry (the specification above as JSON, plus):
--    "skills": [{"name": "share-methodology", "source": {"type": "STAGE", "path": "@SR_DB.SEM.SKILLS/share-methodology"}}]
--    ALTER AGENT SR_DB.SEM.SHARE_RADAR_AGENT MODIFY LIVE VERSION SET SPECIFICATION = '<that JSON>';
-- 3) Rerun the golden set and record both scores in docs/decisions.md.
CREATE STAGE IF NOT EXISTS SR_DB.SEM.SKILLS COMMENT = 'Agent skills (stretch SR-045)';
