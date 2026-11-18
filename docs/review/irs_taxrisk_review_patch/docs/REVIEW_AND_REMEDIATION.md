# IRS TaxRisk MCP ? Repository review and remediation

Based on the supplied `repo_contents.txt` export and deck v2; this is a review patch, **not** a verified replacement of the live Bob workspace. Do not deploy without local tests.

## P0: before recording
1. Confirm `src/irs_risk/app.py` is the canonical server; remove or clearly archive the legacy root `server.py`. Its 30-point hobby-loss weight and automatic-violation language contradict the current hypothetical-v1 engine (20 points and non-determinative flags). Update Bob's MCP launch config and README; smoke-test `list_tools`.
2. Correct `eval/datasets/golden_dataset.json` TC-12: include all seven fields with `reported_1099_income > gross_income`, and assert the error specifically identifies the intended validation rule. The exported results show an empty input dict and seven missing-field errors, not the intended check.
3. Fix the aggregate pass accounting. TC-13 and TC-14 are **not passed**: agent-level assertions were SKIPPED. Report tool-level pass count separately from agent-level executed/passed/skipped counts. Preserve raw run JSON and git commit hash.
4. Test real Orchestrate agent invocation, not only direct Python calls. Capture prompts, tool names, inputs (synthetic only), outputs, timestamps, and failures.
5. Remove delete-before-import behavior in `deploy/ibm/local-mcp-toolkit/register-toolkit.sh`; implement dry-run, staging validation, versioned toolkit import and rollback, with explicit approval before changes.
6. Verify `httpx2>=2.0.0` in toolkit requirements is an intended dependency; inspect `pyproject.toml` and imports and align exact supported dependencies.

## P1: domain correctness
- Replace 'Modernized DIF' branding with 'experimental evidence-review indicators'; the model is neither DIF nor a validated audit probability.
- The 20% charitable-to-gross threshold is invented and **not** an official IRS statistical threshold or deduction limit. A charitable deduction limit may depend on adjusted gross income, recipient and property type, tax year and other factors.
- IRC §183: loss history is one fact; failure to qualify for the profit presumption does not automatically establish hobby status. Avoid audit-action recommendations based on tiers.
- Reconcile corrected/duplicate information returns before evaluating the income mismatch, and test that the final score uses the reconciled total rather than a contradictory pre-reconciliation value.
- Use `Decimal` for monetary arithmetic or justify/verify cent-level rounding; validate form types, tax years, corrected-record chains, duplicate conflicts, and mismatched payers.
- Guidance is currently curated/static. Do not call it 'real-time verified' unless actual retrieval and source verification were logged. Record URL, title, tax-year applicability, retrieval mode and checked date; check authoritative IRS content for changed tax-year rules.
- Review `TaxProfileInput` validation that 1099 income cannot exceed gross income: these are not necessarily directly comparable tax concepts; document assumptions or remove overly rigid validation.

## P1: evaluation and demo
- Add agent tests for TC-13 and TC-14 and an end-to-end tool selection test with actual Orchestrate trace.
- Include a counterexample where a corrected 1099 removes a false-positive mismatch; demonstrate the score before and after reconciliation as *hypothetical* indicators, with no audit recommendation.
- Add no-tool baseline if feasible, but do not claim MCP improvement without measurements.
- Report latency separately: pure-function microseconds vs full agent request time. Do not call in-process tests MCP transport performance.
- Record a 4?6 minute screen capture in the approved IBM environment, with synthetic data only and credentials/UI secrets hidden. Include visible Orchestrate tool calls and final evidence summary. Review recording before sharing.

## P2: repository hygiene
- Ensure `.bob/mcp.json`, `.env`, tokens, generated staging folders and local recording files are ignored. Check git history as well as staged content.
- Avoid self-inclusion in `convert_repo.py`: exclude `repo_contents.txt`, outputs and reference binaries; never use an export as a substitute for actual runnable source review.
- Fix README statements implying all guidance URLs were live verified, all 14 tests fully passed, or Orchestrate agent execution was measured.
- Keep slide deck and evaluation report consistent with the latest verified run and git commit.
