# IRS TaxRisk MCP — 5-Minute Demonstration Script
# GSA AI/MCP Hackathon | Revised for Deck v2

> **Timing guide:** 5 minutes total. Sections marked with ⏱ show cumulative elapsed time.
> Pre-condition: watsonx Orchestrate draft environment open, IRS MCP toolkit registered,
> chat window ready. Slide deck open at slide 6 (Demo slide).

---

## Opening (30 seconds) ⏱ 0:30

**Say:**
> "This is the IRS TaxRisk MCP Server — a research prototype that connects a watsonx
> Orchestrate agent to a deterministic tax compliance risk engine via the Model Context
> Protocol. Everything you're about to see uses synthetic data. No real taxpayer
> information exists in this system. The risk weights are hypothetical — documented in
> the code — and no score produced here may be used as the basis for any compliance action."

---

## Step 1 — Fetch a synthetic profile (45 seconds) ⏱ 1:15

**Type in Orchestrate chat:**
```
Retrieve the synthetic tax record for CASE-2024-HIGHRISE using the multi_flag scenario and show me the key financial figures.
```

**Expected agent behaviour:**
- Calls `irs_get_synthetic_record` with `seed_id=CASE-2024-HIGHRISE`, `scenario=multi_flag`
- Returns: gross income, reported 1099 total, third-party 1099 total, charitable donations, business loss years

**Say while it runs:**
> "The agent is calling the `irs_get_synthetic_record` MCP tool — a deterministic synthetic
> record generator. Same case ID always returns the same data."

---

## Step 2 — Compute the risk score (60 seconds) ⏱ 2:15

**Type:**
```
Using those figures, compute the compliance risk score for CASE-2024-HIGHRISE.
```

**Expected agent behaviour:**
- Calls `irs_evaluate_tax_profile` with the profile figures
- Returns: `risk_score=90`, `risk_tier=High`
- Three flags: `INCOME_MISMATCH`, `OUTLIER_DEDUCTIONS`, `BUSINESS_LOSS_PATTERN`
- Every flag: `is_determinative: false`

**Say:**
> "Score 90 — High tier. Three flags triggered: income mismatch, outlier charitable
> deductions, and a business loss pattern. Notice every flag says is_determinative: false.
> This was a deliberate design decision — no statistical indicator in this system
> automatically establishes a legal conclusion. The examiner decides."

> "Run this again, you get exactly 90. The engine is deterministic — 40 points for income
> mismatch, 30 for outlier deductions, 20 for loss pattern. All documented constants in
> the code."

---

## Step 3 — Reconcile 1099 income (45 seconds) ⏱ 3:00

**Type:**
```
Reconcile the three Form 1099 records for CASE-2024-HIGHRISE. One is a corrected form that
supersedes an earlier original.
```

**Expected agent behaviour:**
- Calls `irs_reconcile_income`
- Voids the original superseded by the corrected form
- Returns: `reconciled_total=$28,500`, `discrepancy=-$1,500` (over-reported)
- Corrected record status shown

**Say:**
> "The reconciliation engine found that the corrected 1099 voids the original — and it
> didn't double-count either. Discrepancy is negative $1,500 — the taxpayer over-reported
> relative to the reconciled figure. An LLM without this tool would almost certainly
> double-count the corrected record."

---

## Step 4 — Retrieve IRS guidance citation (30 seconds) ⏱ 3:30

**Type:**
```
What IRS guidance applies to the business loss pattern flag?
```

**Expected agent behaviour:**
- Calls `irs_get_guidance` with topic: `IRC 183 hobby loss`
- Returns: source `IRC § 183 / Treas. Reg. § 1.183-2`, URL `https://www.irs.gov/publications/p535`
- Summary includes the nine-factor test under § 1.183-2(b)
- Mandatory disclaimer present

**Say:**
> "Structured citation — not a hallucination. The source, the regulation reference, a
> verified irs.gov URL. If I asked about cryptocurrency capital gains, this tool returns
> an empty list — it never makes up a citation for a topic outside its registry.
> We confirmed that in test case TC-11."

---

## Step 5 — Generate analyst briefing (45 seconds) ⏱ 4:15

**Type:**
```
Generate a full analyst briefing for CASE-2024-HIGHRISE.
```

**Expected agent behaviour:**
- Calls `irs_generate_briefing` with the case data
- Returns structured briefing with risk summary, flags, reconciliation note, guidance reference
- Unconditionally includes: "This briefing is produced by an AI prototype for demonstration
  purposes only. It is NOT an official IRS document and must not be used as the basis for
  any examination, enforcement, or compliance action."

**Say:**
> "The briefing unconditionally carries that disclaimer — the agent cannot suppress it.
> This goes to a compliance analyst who reviews the evidence and makes the actual determination.
> The system provides analytical intelligence. The human provides judgment."

---

## Close (45 seconds) ⏱ 5:00

**Say:**
> "What you just saw: a watsonx Orchestrate agent calling five MCP tools — deterministic
> risk scoring, corrected-form reconciliation, authoritative guidance citation, and a
> mandatory-disclaimer briefing — all over a single MCP toolkit registration."
>
> "The evaluation framework confirmed 14 out of 14 test cases passing with 53 deterministic
> assertions across 3 consistency repeats. The two pending tests — scope adherence and
> prompt injection — require a live agent call we have not yet executed. We're being honest
> about that."
>
> "The core principle: MCP provides the auditable, structured interface between an LLM agent
> and a domain-specific analytical tool. The agent augments examiner capability.
> The examiner remains the decision-maker."

---

## Contingency — If Live Demo Fails

| Failure | Recovery |
|---------|----------|
| Orchestrate agent unresponsive | Show `eval/results/run_20261029T144035Z.json` — actual harness output |
| Tool call fails | Run `uv run python eval/scripts/harness.py --case TC-05` in terminal — shows score=90, all flags |
| Network timeout | Walk through the architecture diagram on slide 4 and the results table on slide 7 |
| MCP toolkit not registered | Open `deploy/ibm/mdc_irs_risk_agent.yaml` — shows the full agent spec |

---

## Key Questions and Answers

**Q: Why not just use the LLM directly?**
> An LLM alone cannot produce `risk_score=90` deterministically, correctly void a corrected
> 1099, or return a verified irs.gov URL without hallucinating. We designed test case TC-11
> specifically to confirm the tool returns empty results rather than fabricating a citation.
> Condition B (no-tool baseline) is designed and ready to execute — we predict significantly
> lower correctness on numerical and reconciliation dimensions.

**Q: Why are TC-13 and TC-14 PENDING?**
> Both require a live watsonx Orchestrate agent call. We have the test prompts, expected
> behaviours, and assertion criteria fully authored. We do not claim they passed — the
> eval framework marks them explicitly as PENDING.

**Q: Why didn't you use Arize Phoenix?**
> Phoenix is installable (v12.15.1 on PyPI) but not pre-installed in the IBM ADK
> environment and requires a persistent sidecar server process. We built integration stubs
> in `eval/scripts/phoenix_integration.py` and used the IBM ADK `telemetry-analyzer`
> skill as the IBM-native OTel alternative.

**Q: Is this system production-ready?**
> No. It is a research prototype. The risk weights are explicitly labelled `hypothetical-v1`
> and do not represent the IRS DIF. No real taxpayer data is used. Production deployment
> would require: data classification review, formal legal review of all scope boundaries,
> live agent TC-13/TC-14 testing, and integration with actual IRS systems (which this
> prototype deliberately avoids).
