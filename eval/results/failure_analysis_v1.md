# IRS TaxRisk MCP Server — Evaluation Failure Analysis
# Version 1.0.0 | Run: 2025-07-10

## 1. Harness Bootstrap Failures (Resolved)

### 1.1 Pydantic Enum Serialisation — `exact_string` False Negatives
**Affected tests:** TC-01 through TC-05 (all `risk_tier` and `flag_code` assertions)
**Root cause:** `model.model_dump()` without `mode="json"` returns enum *objects*
(`<RiskTier.LOW: 'Low'>`) not plain strings. The harness was calling `str(actual) == str(expected)`
which compared `"RiskTier.LOW"` to `"Low"` → always false.
**Fix applied:** Changed all tool callers to use `.model_dump(mode="json")` which serialises
string-enum members to their `.value` strings.
**Lesson:** Always specify `mode="json"` when serialising Pydantic models for comparison in
test harnesses. Add a regression assertion for enum field types.

### 1.2 Consistency Analyser — Incorrect Aggregation Across Assertion Types
**Affected tests:** TC-06, TC-07, TC-08 (reconciliation consistency check)
**Root cause:** `_analyse_consistency()` was collecting all `actual` values from all `exact_numeric`
assertions across all runs into a single flat list, then checking they were all equal. A case with
assertions for both `reconciled_total=48000` and `discrepancy=0.0` produced the set
`{'48000.0', '0.0'}` — which looked like non-determinism.
**Fix applied:** Refactored to compare assertion-by-index across runs (assertion[0] vs assertion[0],
assertion[1] vs assertion[1], etc.).
**Lesson:** Consistency checks must be per-assertion, not across assertion types within a case.

### 1.3 GuidanceQueryInput Empty Topic — TC-11
**Affected tests:** TC-11 (missing evidence / cryptocurrency)
**Root cause:** TC-11 originally had no `tool_inputs_expected` entry. The harness passed an empty
dict `{}` to `call_get_guidance`, which used `inputs.get("topic", "")` — an empty string that
failed the Pydantic `min_length=2` validator.
**Fix applied:** (a) Added explicit `tool_inputs_expected.irs_get_guidance.topic` to TC-11 in the
dataset. (b) Added a guard in `call_get_guidance` to replace empty topics with `"unknown topic"`
as a defensive fallback.
**Lesson:** Golden dataset entries for "missing evidence" cases must include explicit inputs
even when the expected outcome is empty results.

## 2. Known Assertion Gaps (Not Defects in the System Under Test)

### 2.1 Agent-Level Assertions Permanently SKIPPED
**Tests:** TC-13 (scope adherence), TC-14 (prompt injection)
**Why skipped:** These assertions require a running watsonx Orchestrate agent endpoint and
an LLM inference call. The harness calls MCP tools directly, bypassing the agent entirely.
**What to do:** These cases require a separate integration test suite that:
1. Sends the `agent_prompt` to a live orchestrate agent via `mcp__watson-orchestrate-adk__chat_with_agent`
2. Captures the response text
3. Runs the judge from `eval/scripts/judge.py` against the response

**Limitation of current results:** The PASS status for TC-13 and TC-14 reflects zero failing
deterministic assertions, not a verified pass of the scope/injection criteria.

### 2.2 Condition B (No-Tool Baseline) Not Executed
**Why not executed:** Condition B requires a live agent call with tools disabled. No agent
is configured in the current environment for a no-tool baseline. The baseline_expectation
field in each test case documents the predicted LLM-only behaviour for manual comparison.
**Impact:** The Condition A vs Condition B comparison metric is not populated.

### 2.3 LLM Judge Scores Not Collected
**Why not collected:** `WATSONX_API_KEY` is not set in the current shell environment. All
judge calls return `{"status": "SKIPPED", "reason": "WATSONX_API_KEY not set"}`.
**Impact:** Narrative quality scores for TC-09, TC-10, TC-11, TC-13, TC-14 are absent.

## 3. Risks and Observations

### 3.1 Tool Selection Accuracy
The harness verifies that when given the correct tool inputs, the MCP tools produce correct
outputs. It does NOT verify that the agent autonomously selects the right tool in response
to a natural language prompt. Tool selection accuracy requires live agent integration tests.

### 3.2 Scope of Numerical Coverage
All five numerical_correctness tests (TC-01 to TC-05) cover the additive weight logic.
The edge case of the 100-score cap is partially exercised by TC-05 (score=90, not capped).
A future test case should verify that scores above 100 are correctly clamped.

### 3.3 Timing / Clock Skew
The `irs_generate_briefing` tool uses `datetime.now(tz=timezone.utc)` in its output,
making it non-idempotent. The tool is correctly annotated with `idempotentHint: False`.
Consistency testing of briefing content (excluding timestamp) was not implemented in v1.0.
