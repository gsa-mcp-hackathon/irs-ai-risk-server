"""Resources module — exposes read-only reference data."""

from __future__ import annotations

import json

from fastmcp import FastMCP

from irs_risk.engine import (
    ENGINE_VERSION,
    _CHARITABLE_RATIO_THRESHOLD,
    _LOSS_YEARS_IN_WINDOW_THRESHOLD,
    _TIER_HIGH_MIN,
    _TIER_MEDIUM_MIN,
    _W_BUSINESS_LOSS_PATTERN,
    _W_INCOME_MISMATCH,
    _W_OUTLIER_DEDUCTIONS,
)


def register_resources(mcp: FastMCP) -> None:
    """Register all IRS risk resources."""

    @mcp.resource("irs://risk-scoring/guide")
    def risk_scoring_guide() -> str:
        """
        Reference guide describing the hypothetical risk flags, their
        thresholds, and the corrected IRC § 183 interpretation.

        The agent reads this resource to answer questions about scoring
        methodology without calling irs_evaluate_tax_profile.
        """
        return json.dumps({
            "title": "IRS AI Risk Scoring Guide",
            "engine_version": ENGINE_VERSION,
            "disclaimer": (
                "All weights, thresholds, and tiers are HYPOTHETICAL values for "
                "demonstration purposes only. They do not represent or implement "
                "the actual IRS Discriminant Index Function (DIF) or any official "
                "IRS audit-selection methodology."
            ),
            "flags": [
                {
                    "id": "INCOME_MISMATCH",
                    "hypothetical_weight": _W_INCOME_MISMATCH,
                    "rule": "third_party_1099_total > reported_1099_income",
                    "interpretation": (
                        "A statistical indicator of potential income underreporting. "
                        "Requires document-matching review before any conclusion. "
                        "Legitimate causes include corrected forms, timing differences, "
                        "and duplicate payer filings (IRC § 6201)."
                    ),
                    "is_determinative": False,
                },
                {
                    "id": "OUTLIER_DEDUCTIONS",
                    "hypothetical_weight": _W_OUTLIER_DEDUCTIONS,
                    "rule": f"charitable_contributions / gross_income > {_CHARITABLE_RATIO_THRESHOLD:.0%}",
                    "interpretation": (
                        "A Schedule A statistical anomaly indicator. High ratios can arise "
                        "legitimately from one-time large gifts, conservation easements, or "
                        "donor-advised fund contributions. NOT a determination of IRC § 170 "
                        "non-compliance. Substantiation review is warranted."
                    ),
                    "is_determinative": False,
                },
                {
                    "id": "BUSINESS_LOSS_PATTERN",
                    "hypothetical_weight": _W_BUSINESS_LOSS_PATTERN,
                    "rule": f"business_loss_years_in_window >= {_LOSS_YEARS_IN_WINDOW_THRESHOLD}",
                    "interpretation": (
                        "ONE of nine factors the IRS weighs under Treas. Reg. § 1.183-2(b) "
                        "for the IRC § 183 profit-motive analysis. A loss pattern does NOT "
                        "automatically establish hobby status or disallow deductions. All nine "
                        "factors must be weighed together by an examiner. The IRC § 183 safe "
                        "harbor presumes profit motive if the activity shows profit in ≥ 2 of "
                        "5 consecutive years (rebuttable presumption)."
                    ),
                    "is_determinative": False,
                    "irc_183_nine_factors": [
                        "1. Manner of conducting the activity",
                        "2. Expertise of taxpayer or advisors",
                        "3. Time and effort expended",
                        "4. Expectation that assets will appreciate",
                        "5. Taxpayer's success in similar activities",
                        "6. History of income or losses",
                        "7. Amount of occasional profits",
                        "8. Taxpayer's financial status",
                        "9. Elements of personal pleasure or recreation",
                    ],
                },
            ],
            "tiers": {
                "Low":    f"0–{_TIER_MEDIUM_MIN - 1}  — No significant indicators. No escalation indicated.",
                "Medium": f"{_TIER_MEDIUM_MIN}–{_TIER_HIGH_MIN - 1} — One or more indicators. Correspondence or document request may be appropriate.",
                "High":   f"{_TIER_HIGH_MIN}–100 — Multiple indicators. Examiner review recommended.",
            },
        }, indent=2)
