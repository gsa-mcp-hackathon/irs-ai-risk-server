# Paste into IBM Bob in `/home/itzuser/irs-ai-risk-server`

Review the attached review patch documents and inspect the ACTUAL working repository. Do not assume the text export is complete. Preserve the working Orchestrate agent and its toolkit until a tested replacement is ready.

Phase 1: Audit the canonical MCP entry point, README, agent YAML, toolkit packaging, dependencies and test results. Specifically compare root `server.py` with `src/irs_risk/app.py`; inspect the TC-12 missing-field false-positive, skipped TC-13/14 counting, and delete-before-import toolkit script. Provide a file-by-file change plan before editing.

Phase 2: After my approval, fix correctness and safety issues with small commits. Maintain hypothetical weights unless explicitly approved; do not infer official IRS DIF or audit-selection rules. Reconcile corrected 1099s before scoring; add a synthetic false-positive-correction scenario. Use source-traceable evidence and clearly mark static guidance as static. Add precise validation tests and distinguish passed/failed/skipped results.

Phase 3: Run unit, MCP tool-discovery, toolkit packaging and agent integration tests. Capture actual Orchestrate tool traces and test TC-13/14. Do not claim an agent test passed based on a direct Python function call. Produce updated evaluation report, README and presentation notes from actual evidence only.

Phase 4: Prepare a 5-minute recorded demonstration script, showing tool discovery, a corrected-form case, reconciled scoring, cited guidance, and an analyst briefing. Mark all data synthetic and all scoring experimental. Keep secrets out of recordings and Git.

Phase 5: Review git status, .gitignore and git history for secrets; show staged changes, test evidence, proposed commit and deployment commands. Do not push, delete an existing toolkit, redeploy, or publish without my explicit approval.
