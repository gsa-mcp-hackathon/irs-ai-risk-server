# Toolkit Update Procedure, Rollback Plan & Exact Commands

**Server:** IRS AI Risk MCP Server (`src/irs_risk/`)  
**Toolkit:** `mdc-irs-risk-toolkit` (watsonx Orchestrate SaaS, `gsa-hackathon` env)  
**Canonical entry point:** `src/irs_risk/app.py` (5 tools)  
**Legacy file:** `server.py` — kept for reference, NOT deployed  
**Git commit at time of writing:** `98ff36c2b4528e9b9cdaeaad8fbbbdbcc5f3246c`

---

## 1. Prerequisites (one-time setup)

```bash
# Confirm venv exists and has fastmcp ≥ 4.0.0
.venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"
# Expected: 4.1.4 (or later)

# Confirm orchestrate ADK is on PATH
orchestrate --version

# Confirm git status is clean (no uncommitted secrets)
git status
git diff --stat
```

---

## 2. Pre-deployment checks (run before every update)

```bash
# 2a. Run the full eval harness — must be 15/15 PASS with 0 FAIL
.venv/bin/python eval/scripts/harness.py --condition A
# Accept only: Pass rate: 100.0%

# 2b. Run unit tests
.venv/bin/python -m pytest tests/ -v --tb=short

# 2c. Toolkit staging validation (5 tools discoverable)
WXO_ENV_NAME=gsa-hackathon \
WXO_INSTANCE_URL=https://api.<region>.watson-orchestrate.cloud.ibm.com/instances/<instance-id-redacted> \
TOOLKIT_NAME=mdc-irs-risk-toolkit \
  bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh --dry-run
# NOTE: register-toolkit.sh --dry-run uses bare python3 (3.9 on this machine).
# If it fails with "No module named 'fastmcp'", run the manual validation instead:
#
#   STAGE_DIR=deploy/ibm/local-mcp-toolkit/_stage
#   .venv/bin/python -c "
#     import sys, asyncio; sys.path.insert(0, '${STAGE_DIR}')
#     from irs_risk.app import mcp
#     async def c():
#         tools = await mcp.list_tools()
#         print([t.name for t in tools])
#     asyncio.run(c())
#   "
# Expected: 5 tools listed.

# 2d. Confirm Orchestrate environment is active and authenticated
orchestrate env list
orchestrate env activate gsa-hackathon --api-key "${WXO_API_KEY}"
orchestrate toolkits list    # note the current toolkit name and version
orchestrate agents list      # note which agents reference mdc-irs-risk-toolkit
```

---

## 3. Supported update procedure

**Rule: DO NOT remove the working toolkit before the new one is verified.**  
The script already enforces an interactive confirmation prompt before any removal.

### Step 1 — Export current toolkit registration (snapshot before change)

```bash
orchestrate toolkits export \
  --name mdc-irs-risk-toolkit \
  --output-file eval/results/toolkit_backup_$(date -u +%Y%m%dT%H%M%SZ).zip
```

### Step 2 — Tag the current Git state

```bash
git tag -a "pre-update-$(date -u +%Y%m%d)" -m "Snapshot before toolkit update"
git push origin --tags
```

### Step 3 — Make and test code changes locally

```bash
# Edit files in src/irs_risk/ as needed
# Run full validation (Step 2a–2c above)
# Commit only when tests pass:
git add src/irs_risk/ tests/ eval/
git commit -m "fix: <description>"
```

### Step 4 — Live registration (requires explicit approval)

```bash
# Source env config (no API key — will prompt if WXO_API_KEY not set)
set -a; source deploy/ibm/local-mcp-toolkit/.env; set +a

# Run the registration script (live)
# The script will:
#   1. Activate the Orchestrate environment
#   2. Stage the irs_risk package
#   3. Validate 5 tools are importable
#   4. CHECK if mdc-irs-risk-toolkit already exists
#   5. PROMPT you to confirm removal before importing new version
#   6. Import and clean up
bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh
```

> **Gate:** Only proceed through the interactive [y/N] prompt if you have:
> - Passing eval harness (Step 2a)
> - Passing unit tests (Step 2b)
> - 5 tools confirmed in staging (Step 2c)
> - A Git tag and toolkit backup (Steps 1–2)

### Step 5 — Smoke-test after registration

```bash
orchestrate toolkits list   # confirm mdc-irs-risk-toolkit is listed
# Then chat with the agent:
orchestrate agents chat --name mdc-irs-risk-agent
# Suggested prompt: "Score a clean profile: case_id=POST-DEPLOY-SMOKE, tax_year=2023,
#   gross_income=80000, reported_1099_income=40000, third_party_1099_total=40000,
#   charitable_contributions=3000, business_loss_years_in_window=0"
# Expected: score=0, tier=Low, NO_FLAGS
```

---

## 4. Rollback plan

### Case A — Rollback to previous toolkit ZIP (within same session)

```bash
# Remove the newly imported toolkit
orchestrate toolkits remove --name mdc-irs-risk-toolkit

# Re-import from the backup ZIP
orchestrate toolkits import \
  -f eval/results/toolkit_backup_<timestamp>.zip

# Verify
orchestrate toolkits list
```

### Case B — Rollback to previous Git commit

```bash
# Identify the last good commit
git log --oneline -10

# Check out the last known good tag/commit
git checkout pre-update-<date>

# Re-run staging validation, then do a fresh live registration
bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh
```

### Case C — Full reset (agent unavailable, need immediate restore)

```bash
# 1. Remove broken toolkit
orchestrate toolkits remove --name mdc-irs-risk-toolkit

# 2. Import from last known good ZIP backup
orchestrate toolkits import -f eval/results/toolkit_backup_<timestamp>.zip

# 3. Confirm agent can reach tools
orchestrate agents chat --name mdc-irs-risk-agent
```

---

## 5. What NOT to do

| Forbidden action | Why |
|---|---|
| `orchestrate toolkits remove mdc-irs-risk-toolkit` without a backup | Leaves the agent toolless with no fast recovery path |
| Pushing `WXO_API_KEY`, `.env`, or any bearer token to Git | Credentials must stay out of version history |
| Claiming eval tests passed without running them | Per AGENT_EVAL_ACCEPTANCE.md: "Baseline results must be actually run, not predicted" |
| Using `server.py` (repo root) as the toolkit entry point | Legacy file; 30-pt hobby-loss weight, `HOBBY_LOSS_RISK` flag name, no reconciliation |
| Using bare `python3` for staging validation on this machine | System Python is 3.9; fastmcp requires ≥ 3.10. Use `.venv/bin/python` |

---

## 6. Known issues and open items (as of 2026-11-18)

| Issue | Severity | Status |
|---|---|---|
| `register-toolkit.sh --dry-run` uses bare `python3` (3.9); fails staging validation on this machine | Medium | Workaround: run manual staging validation with `.venv/bin/python` (see §2c above) |
| Orchestrate `gsa-hackathon` token expired | Blocker for agent-level tests | Run `orchestrate env activate gsa-hackathon --api-key <key>` |
| Agent-level A-01/A-04/A-05/A-06/A-07 checks NOT_EXECUTED | Medium | Requires live Orchestrate session; direct-function evidence saved in `eval/results/agent_eval_A01_A07_20261118T180800Z.json` |
| TC-13/TC-14 agent assertions SKIPPED | Low | Labelled correctly as SKIPPED in harness output; not counted as PASSED |

---

## 7. Files changed in this codebase (git status at this writing)

```
 M README.md
 M deploy/ibm/local-mcp-toolkit/.env.example
 M deploy/ibm/local-mcp-toolkit/register-toolkit.sh
 M eval/datasets/golden_dataset.json
 M eval/reports/eval_report_v2.md
 M eval/scripts/harness.py
 M requirements.txt
 M server.py
 M src/irs_risk/models.py
 M src/irs_risk/reconcile.py
 M src/irs_risk/tools/get_irs_guidance.py
 M src/irs_risk/tools/get_synthetic_record.py
 M tests/test_tools.py
?? eval/results/run_20261118T145209Z.json
?? tests/test_reconcile_decimal.py
```

**New files added in this session:**
```
?? eval/results/agent_eval_A01_A07_20261118T180800Z.json
?? eval/results/UPDATE_PROCEDURE_AND_ROLLBACK.md
```

**NOT staged, NOT pushed. Await explicit approval before committing or deploying.**
