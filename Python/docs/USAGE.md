# Usage metadata and optional estimates

Default log: reports/ai_usage.jsonl. Optional override: VENESSE_AI_USAGE_LOG.
Each record contains UTC time, provider/model, operation, request status, elapsed seconds, reported input/output/total tokens, and an optional estimate. Provider failures may have unknown token usage; do not interpret unknown usage as zero billed tokens.

Optional rate variables:
- VENESSE_AI_PRICE_MODEL: exact model ID
- VENESSE_AI_INPUT_USD_PER_MILLION: your current input price
- VENESSE_AI_OUTPUT_USD_PER_MILLION: your current output price

Rates are user-configured and not automatically retrieved. Estimates use reported tokens and those rates; they may not include discounts, cache pricing, or other provider charges. No spending cap is enforced.

The session cache holds up to 32 successful commentary results. Restarting clears it. Reports are fetched again even on a commentary cache hit.
