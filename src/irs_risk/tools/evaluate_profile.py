"""Tool: irs_evaluate_tax_profile

Evaluates a taxpayer financial profile and returns a versioned, structured
risk score. Uses the hypothetical risk engine — not the actual IRS DIF.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from irs_risk.engine import compute_risk
from irs_risk.models import TaxProfileInput


def register(mcp: FastMCP) -> None:
    """Register the irs_evaluate_tax_profile tool."""

    @mcp.tool(
        name="irs_evaluate_tax_profile",
        annotations={
            "title": "Evaluate Tax Profile Risk",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def irs_evaluate_tax_profile(
        case_id: Annotated[
            str,
            "Opaque case reference ID (e.g. 'CASE-2024-0042'). No PII.",
        ],
        tax_year: Annotated[int, "Calendar tax year under review, e.g. 2023."],
        gross_income: Annotated[
            float,
            "Total gross income reported on the return (line 9, Form 1040), in USD.",
        ],
        reported_1099_income: Annotated[
            float,
            "1099 income the taxpayer self-reported on the return, in USD.",
        ],
        third_party_1099_total: Annotated[
            float,
            "Total 1099 income found in third-party information returns, in USD.",
        ],
        charitable_contributions: Annotated[
            float,
            "Total charitable contribution deductions claimed on Schedule A, in USD.",
        ],
        business_loss_years_in_window: Annotated[
            int,
            (
                "Number of years with a net Schedule C/F business loss in the "
                "most recent 5-year window (0–5). Used as ONE of nine IRC § 183 "
                "factors; not determinative of hobby status alone."
            ),
        ],
    ) -> dict:
        """
        Score a taxpayer's financial profile using a hypothetical risk engine.

        Returns a versioned JSON object with a composite risk score (0–100),
        a risk tier (Low / Medium / High), and structured flags explaining
        each statistical indicator that was triggered.

        IMPORTANT: The score is produced by a HYPOTHETICAL model for
        demonstration purposes only. It does not implement the actual IRS
        Discriminant Index Function (DIF). No legal conclusions should be
        drawn from the result.

        The IRC § 183 business-loss flag represents ONE of nine factors the
        IRS considers under Treas. Reg. § 1.183-2(b). A flag alone does NOT
        establish hobby status or disallow deductions.
        """
        profile = TaxProfileInput(
            case_id=case_id,
            tax_year=tax_year,
            gross_income=gross_income,
            reported_1099_income=reported_1099_income,
            third_party_1099_total=third_party_1099_total,
            charitable_contributions=charitable_contributions,
            business_loss_years_in_window=business_loss_years_in_window,
        )
        result = compute_risk(profile)
        return result.model_dump()
