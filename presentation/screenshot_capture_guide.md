# Screenshot and Log Capture Guide
## IRS TaxRisk MCP — GSA Hackathon Presentation

Use this guide to capture evidence screenshots and logs before the presentation.
All captures should use synthetic data only.

---

## Section A — IBM Bob / MCP Server

### A1. Bob MCP Connection — Tool List
**What to capture:** The tool list shown when Bob connects to the MCP server.
**How:**
1. Open Bob in the project workspace (`irs-ai-risk-server`)
2. The MCP server should auto-connect via `.bob/mcp.json`
3. Ask Bob: *"What tools do you have available?"* or look in the MCP panel
4. **Screenshot:** The list showing `irs_evaluate_tax_profile`, `irs_reconcile_income`,
   `irs_get_guidance`, `irs_generate_briefing`, `irs_get_synthetic_record`
5. **Label:** "Slide 3 / Slide 4 — Five MCP tools registered"

### A2. Bob — Single Tool Call Response
**What to capture:** A clean JSON response from `irs_evaluate_tax_profile`.
**How:** Ask Bob:
```
Evaluate CASE-DEMO-HIGH. Gross $150k, reported 1099 $90k, 3P 1099 $110k, charitable $45k, loss years 5.
```
**Screenshot:** The full JSON response including `engine_version: hypothetical-v1`
**Label:** "Slide 4 — Tool response with engine_version embedded"

### A3. Bob — Resource Read
**How:** Ask Bob: *"Read the IRS risk scoring guide"*
**Screenshot:** The guide content showing flag weights and tiers
**Label:** "Slide 3 — MCP resource: irs://risk-scoring/guide"

### A4. Bob — Validation Error
**How:** Ask Bob: *"Score CASE-INVALID. Gross $100k. Reported 1099 $120k. Third-party $115k. Charitable $5k. Loss years 0."*
**Screenshot:** The validation error showing reported_1099 > gross_income rejected
**Label:** "Slide 7 — Pydantic v2 input validation in action"

---

## Section B — IBM watsonx Orchestrate

### B1. Orchestrate Agent Chat — High-Risk Profile (Step 1)
**What to capture:** The complete Step 1 demo response.
**Screenshot content must show:**
- User prompt (the CASE-DEMO-HIGH evaluate request)
- Agent response with `risk_score: 90`, `risk_tier: High`
- All three flags visible: INCOME_MISMATCH, OUTLIER_DEDUCTIONS, BUSINESS_LOSS_PATTERN
- `is_determinative: false` on at least one flag
- `engine_version: hypothetical-v1`
**Label:** "Slide 5 / Slide 6 — Step 1: High-risk profile, score=90"

### B2. Orchestrate Agent Chat — 1099 Reconciliation (Step 2)
**Screenshot must show:**
- User prompt (reconcile request with corrected record R001-C)
- `reconciled_total: 90000`
- `discrepancy: 0.0`
- R001 status `corrected` (voided)
**Label:** "Slide 5 — Step 2: Corrected-record voiding"

### B3. Orchestrate Agent Chat — Guidance Citation (Step 3)
**Screenshot must show:**
- `source: "IRC § 183 / Treas. Reg. § 1.183-2"`
- `url: "https://www.irs.gov/publications/p535"`
- The nine-factor text in the summary
**Label:** "Slide 5 / Slide 7 — Step 3: Citable guidance, real irs.gov URL"

### B4. Orchestrate Agent Chat — Clean Profile (Step 5)
**Screenshot must show:**
- User prompt (CASE-DEMO-CLEAN)
- `risk_score: 0`, `risk_tier: Low`, `NO_FLAGS`
**Label:** "Slide 5 / Slide 6 — Step 5: Clean profile, no false positives"

### B5. Orchestrate Agent Definition (optional)
**What to capture:** The agent YAML/configuration page in Orchestrate UI
**Where:** Orchestrate → Agents → IRS TaxRisk Agent
**Screenshot:** Agent name, model, tool list, instructions summary
**Label:** "Slide 3 — Agent configuration in Orchestrate"

---

## Section C — Evaluation Framework

### C1. pytest Run — Full Pass
**How:**
```bash
cd /home/itzuser/irs-ai-risk-server
EVAL_REPEAT=3 uv run pytest eval/scripts/test_eval_deterministic.py -v
```
**Screenshot:** Terminal showing `12 passed, 2 skipped in X.XXs`
**Label:** "Slide 6 — 12 deterministic tests passing, 2 skipped (agent-level)"

### C2. Harness Run — Summary Output
**How:**
```bash
uv run python eval/scripts/harness.py --repeat 3
```
**Screenshot:** The summary table at the bottom showing 14/14 PASS, latency stats
**Label:** "Slide 6 — Harness: 14/14 passing, 3 repeats, all consistent"

### C3. Single Case — Detailed Output
**How:**
```bash
uv run python eval/scripts/harness.py --case TC-05
```
**Screenshot:** The detailed assertion results for TC-05 (all three flags, score=90)
**Label:** "Slide 6 — TC-05: All three flags, deterministic score=90"

### C4. Results JSON (optional, for technical audience)
**How:** Open `eval/results/run_<latest timestamp>.json` in VS Code
**Screenshot:** The aggregate section showing `pass_rate: 1.0`, `latency_p50_sec`
**Label:** "Slide 6 — Machine-readable results JSON"

---

## Section D — Architecture Evidence

### D1. File Tree
**How:**
```bash
cd /home/itzuser/irs-ai-risk-server
find . -not -path './.git/*' -not -path './.venv/*' -not -path './__pycache__/*' \
  -not -path '*/__pycache__/*' -not -name '*.pyc' | sort | head -60
```
**Screenshot:** Tree showing `src/irs_risk/tools/`, `eval/`, `deploy/ibm/`, `presentation/`
**Label:** "Slide 3 / Slide 4 — Repository structure"

### D2. server.py Tool Registration
**How:** Open `src/irs_risk/tools/evaluate_profile.py` in editor
**Screenshot:** The `@mcp.tool(name="irs_evaluate_tax_profile", annotations={...})` block
showing `readOnlyHint: True`, `destructiveHint: False`
**Label:** "Slide 4 — MCP tool annotations"

### D3. Deploy Config
**How:** Open `deploy/ibm/mdc_irs_risk_agent.yaml`
**Screenshot:** The agent YAML file
**Label:** "Slide 3 — IBM Orchestrate agent definition"

---

## Capture checklist

- [ ] A1 — Bob tool list
- [ ] A2 — Bob single tool call (high-risk profile)
- [ ] A3 — Bob resource read
- [ ] A4 — Bob validation error
- [ ] B1 — Orchestrate: high-risk profile response (Step 1)
- [ ] B2 — Orchestrate: reconciliation with corrected record (Step 2)
- [ ] B3 — Orchestrate: guidance citation with URL (Step 3)
- [ ] B4 — Orchestrate: clean profile (Step 5)
- [ ] C1 — pytest 12 passed / 2 skipped
- [ ] C2 — harness 14/14 summary
- [ ] C3 — TC-05 detailed assertions
- [ ] D1 — file tree

---

## Naming convention for saved screenshots

```
screenshot_<section>_<description>_<YYYYMMDD>.png

Examples:
  screenshot_B1_orchestrate_high_risk_profile_20250710.png
  screenshot_C1_pytest_12passed_2skipped_20250710.png
  screenshot_A4_bob_validation_error_20250710.png
```

Save all screenshots in `presentation/screenshots/` (create the folder if it doesn't exist).
