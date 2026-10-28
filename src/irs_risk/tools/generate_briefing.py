"""Tool: irs_generate_briefing

Assembles a preliminary analyst briefing from a risk score, reconciliation
result, and applicable guidance summaries.

The briefing is AI-generated and for demonstration use only. It is NOT an
official IRS document and must not be used for any enforcement action.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastmcp import FastMCP

from irs_risk.models import BriefingOutput, FlagCode, RiskTier

log = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:
    """Register the irs_generate_briefing tool."""

    @mcp.tool(
        name="irs_generate_briefing",
        annotations={
            "title": "Generate Analyst Briefing",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,   # timestamp changes each call
            "openWorldHint": False,
        },
    )
    async def irs_generate_briefing(
        case_id: Annotated[str, "Case reference ID. No PII."],
        tax_year: Annotated[int, "Tax year under review."],
        risk_score: Annotated[
            int,
            "Composite risk score (0–100) from irs_evaluate_tax_profile.",
        ],
        risk_tier: Annotated[
            str,
            "Risk tier from irs_evaluate_tax_profile: 'Low', 'Medium', or 'High'.",
        ],
        flag_codes: Annotated[
            list[str],
            (
                "List of flag codes from irs_evaluate_tax_profile, e.g. "
                "['INCOME_MISMATCH', 'OUTLIER_DEDUCTIONS']. "
                "Use ['NO_FLAGS'] when the profile is clean."
            ),
        ],
        reconciliation_summary: Annotated[
            str,
            "The 'summary' field from irs_reconcile_income output.",
        ],
        discrepancy: Annotated[
            float,
            "The 'discrepancy' field from irs_reconcile_income (USD).",
        ],
        guidance_topics_found: Annotated[
            list[str],
            (
                "List of guidance titles returned by irs_get_guidance, "
                "e.g. ['IRC § 183 — Hobby Loss Rules', 'IRC § 170 — Charitable Contributions']. "
                "Pass an empty list if guidance was not retrieved."
            ),
        ],
    ) -> dict:
        """
        Assemble a preliminary analyst briefing from scoring, reconciliation,
        and guidance results.

        The briefing summarises the risk tier, explains each flag in examiner-
        friendly language, translates the income discrepancy, and lists
        recommended review actions.

        IMPORTANT: This briefing is produced by an AI prototype for
        demonstration purposes only. It is NOT an official IRS document and
        must not be used as the basis for any examination, enforcement, or
        compliance action.
        """
        # ── Validate and normalise inputs ─────────────────────────────────────
        try:
            tier = RiskTier(risk_tier)
        except ValueError:
            tier = RiskTier.LOW

        valid_codes = {fc.value for fc in FlagCode}
        flags = [c for c in flag_codes if c in valid_codes]

        # ── Risk summary ──────────────────────────────────────────────────────
        tier_descriptions = {
            RiskTier.LOW: (
                f"Case {case_id} (TY {tax_year}) received a hypothetical risk score of "
                f"{risk_score}/100 (Low tier). No significant statistical anomalies were "
                f"detected across the three indicators reviewed. No immediate escalation "
                f"is indicated by this model."
            ),
            RiskTier.MEDIUM: (
                f"Case {case_id} (TY {tax_year}) received a hypothetical risk score of "
                f"{risk_score}/100 (Medium tier). One or more statistical indicators were "
                f"triggered. A correspondence inquiry or document request may be appropriate "
                f"pending examiner review of the flagged items."
            ),
            RiskTier.HIGH: (
                f"Case {case_id} (TY {tax_year}) received a hypothetical risk score of "
                f"{risk_score}/100 (High tier). Multiple statistical indicators were triggered. "
                f"Examiner review of all flagged items is recommended before determining "
                f"the appropriate next step."
            ),
        }
        risk_summary = tier_descriptions[tier]

        # ── Flag explanations ─────────────────────────────────────────────────
        flag_notes: dict[str, str] = {
            FlagCode.INCOME_MISMATCH.value: (
                "Income Mismatch: Third-party 1099 filings exceed taxpayer-reported income. "
                "Recommend document matching against W-2/1099 forms received by the taxpayer. "
                "Common benign causes include corrected forms, timing differences, and "
                "duplicate payer filings."
            ),
            FlagCode.OUTLIER_DEDUCTIONS.value: (
                "Outlier Deductions: Charitable contributions are statistically high relative "
                "to gross income. Recommend substantiation review (IRC § 170 written "
                "acknowledgment, qualified appraisal if applicable). High ratios can arise "
                "legitimately from one-time large gifts or conservation easements."
            ),
            FlagCode.BUSINESS_LOSS_PATTERN.value: (
                "Business Loss Pattern: Multiple loss years detected within the 5-year window. "
                "Under IRC § 183, this is ONE of nine factors in the profit-motive analysis "
                "(Treas. Reg. § 1.183-2(b)). A full nine-factor review by the examiner is "
                "required before any hobby-loss reclassification. Loss patterns alone do NOT "
                "establish hobby status."
            ),
        }
        guidance_notes = [flag_notes[c] for c in flags if c in flag_notes]
        if guidance_topics_found:
            guidance_notes.append(
                f"Applicable guidance retrieved: {'; '.join(guidance_topics_found)}."
            )

        # ── Reconciliation summary ────────────────────────────────────────────
        if discrepancy > 0:
            recon = (
                f"{reconciliation_summary} "
                f"A ${discrepancy:,.2f} potential income underreporting gap was identified. "
                f"This warrants income-matching verification before any compliance action."
            )
        elif discrepancy < 0:
            recon = (
                f"{reconciliation_summary} "
                f"The taxpayer appears to have reported ${abs(discrepancy):,.2f} more than "
                f"the reconciled third-party total. This may indicate estimated income was "
                f"included on the return or that some 1099 forms were not provided."
            )
        else:
            recon = f"{reconciliation_summary} No income discrepancy detected."

        # ── Recommended actions ───────────────────────────────────────────────
        actions: list[str] = []
        if FlagCode.INCOME_MISMATCH.value in flags:
            actions.append(
                "Request copies of all 1099 forms received by the taxpayer and "
                "reconcile against third-party records."
            )
        if FlagCode.OUTLIER_DEDUCTIONS.value in flags:
            actions.append(
                "Request substantiation for charitable contribution deductions "
                "(IRC § 170 written acknowledgments; qualified appraisals for "
                "non-cash contributions > $5,000)."
            )
        if FlagCode.BUSINESS_LOSS_PATTERN.value in flags:
            actions.append(
                "Conduct a nine-factor IRC § 183 profit-motive analysis per "
                "Treas. Reg. § 1.183-2(b) before making any hobby-loss determination."
            )
        if not actions:
            actions.append(
                "No immediate documentation requests indicated by this model. "
                "Examiner discretion applies."
            )
        actions.append(
            "REMINDER: This briefing is produced by a hypothetical AI prototype. "
            "All conclusions must be independently verified by a qualified examiner "
            "before any official action is taken."
        )

        log.info(
            "briefing generated case=%s year=%d tier=%s flags=%s",
            case_id, tax_year, tier.value, flags,
        )

        output = BriefingOutput(
            case_id=case_id,
            tax_year=tax_year,
            generated_at_utc=datetime.now(tz=timezone.utc).isoformat(),
            risk_summary=risk_summary,
            reconciliation_summary=recon,
            guidance_notes=guidance_notes,
            recommended_actions=actions,
        )
        return output.model_dump()
