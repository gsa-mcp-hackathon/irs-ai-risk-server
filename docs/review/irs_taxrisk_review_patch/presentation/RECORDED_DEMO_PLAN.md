# Recorded demo plan ? IRS TaxRisk MCP (5 minutes)

**Prerequisite:** Capture the actual watsonx Orchestrate agent in the IBM sandbox, not a simulated transcript. Use only synthetic records. Do not expose API keys, user identifiers or internal system information.

| Time | Show | Evidence to capture |
|---|---|---|
| 0:00?0:35 | Title, problem, disclaimer | Synthetic-only; experimental indicators, not official DIF or audit decisions |
| 0:35?1:15 | Orchestrate agent and MCP toolkit | Registered toolkit and five discoverable tool names |
| 1:15?2:30 | Synthetic case and corrected 1099 | Agent invokes record and reconciliation tools; show corrected form supersedes original |
| 2:30?3:20 | Reconciled score and evidence | Show source IDs, arithmetic, hypothetical version and non-determinative flags |
| 3:20?4:10 | Public guidance and briefing | Static vs live retrieval explicitly labeled; cite verified source and tax year; show human-review disclaimer |
| 4:10?5:00 | Evaluation, limitations, close | Tool-only results separately from actual agent tests; show run ID and commit hash |

## Recording checklist
- Confirm all five tools work from the same deployed version.
- Rehearse the scenario and record actual tool traces.
- Use a short, clean run with readable text and no secret-bearing terminals.
- If an agent test is pending, label it pending rather than showing a fabricated success.
- Save the final video outside the Git repository until sharing approval and file-size limits are known.
- Add an approved recording link and SHA-256 checksum to the submission README.

## Suggested prompt for Orchestrate
"Using synthetic case CASE-2024-HIGHRISE, retrieve the sample records and reconcile the information returns, including the corrected form. Calculate experimental indicators from the **reconciled** amounts, retrieve relevant public IRS guidance from the available registry, and produce a preliminary evidence-review briefing. Distinguish verified facts, missing evidence, hypothetical rules, and human-review questions. Do not recommend an audit or make a legal finding."
