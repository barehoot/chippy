"""Share Radar library: run orchestration, bridge mirror, fact pack, validator, renderer and fallback (L2).

Packaged as sr_lib.zip and imported by SP_RUN_WEEK, SP_BUILD_FACT_PACK and SP_WRITE_BRIEF from @SR_DB.APP.CODE.
Modules that need Snowpark import it inside functions, so the pure modules run anywhere for unit tests.
"""
