"""
IRS Modernized Risk Core — FastMCP Server
Hackathon scaffold: AI-native DIF (Discriminant Index Function) risk scoring.
"""

import json
from typing import List
from fastmcp import FastMCP
from fastmcp.prompts import Message

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp = FastMCP("IRS Modernized Risk Core")


# ---------------------------------------------------------------------------
# Scoring logic (pure function — easy to unit-test independently)
# ---------------------------------------------------------------------------

def _compute_risk(
    gross_income: float,
    reported_1099_income: float,
    actual_1099_records: float,
    charitable_contributions: float,
    consecutive_business_losses_years: int,
) -> dict:
    """
    Calculate a Modernized DIF Score (0–100) and return a structured payload.

    Scoring model
    -------------
    Each triggered flag contributes a weighted penalty:
      - Income Mismatch          → 40 pts  (hard discrepancy; highest audit priority)
      - Outlier Deductions        → 30 pts  (statistically uncommon; mid-tier risk)
      - Hobby Loss / Safe Harbor  → 30 pts  (consecutive losses violate IRS § 183 safe harbor)

    Risk tiers
    ----------
      0–39   → Low
      40–69  → Medium
      70–100 → High
    """

    score = 0
    flags: List[str] = []

    # ── Flag 1: Income Mismatch ────────────────────────────────────────────
    # Third-party 1099 records exceed what the taxpayer self-reported.
    if actual_1099_records > reported_1099_income:
        delta = actual_1099_records - reported_1099_income
        score += 40
        flags.append(
            f"INCOME_MISMATCH: Third-party 1099 records report ${delta:,.2f} more income "
            f"than the taxpayer disclosed (reported ${reported_1099_income:,.2f} vs. "
            f"IRS records ${actual_1099_records:,.2f}). Potential underreporting."
        )

    # ── Flag 2: Outlier Deductions ─────────────────────────────────────────
    # Charitable contributions exceed 20 % of gross income — a statistical outlier
    # that the IRS flags as a Schedule A anomaly.
    if gross_income > 0:
        contribution_ratio = charitable_contributions / gross_income
        if contribution_ratio > 0.20:
            score += 30
            flags.append(
                f"OUTLIER_DEDUCTIONS: Charitable contributions (${charitable_contributions:,.2f}) "
                f"represent {contribution_ratio:.1%} of gross income (${gross_income:,.2f}), "
                f"exceeding the 20% statistical threshold. Schedule A scrutiny recommended."
            )

    # ── Flag 3: Hobby Loss / Safe Harbor Violation ─────────────────────────
    # Under IRC § 183, a business with fewer than 3 profitable years in the last 5
    # is presumed a hobby. >= 3 consecutive loss years breaches the safe harbor.
    if consecutive_business_losses_years >= 3:
        score += 30
        flags.append(
            f"HOBBY_LOSS_RISK: {consecutive_business_losses_years} consecutive years of "
            f"business losses exceeds the IRS § 183 'Safe Harbor' profit rule (2 of 5 years). "
            f"Activity may be reclassified as a hobby, disallowing loss deductions."
        )

    # ── Clamp and tier ────────────────────────────────────────────────────
    score = min(score, 100)

    if score >= 70:
        tier = "High"
    elif score >= 40:
        tier = "Medium"
    else:
        tier = "Low"

    if not flags:
        flags.append(
            "NO_FLAGS: No anomalies detected across income reporting, deduction ratios, "
            "or business loss history. Profile appears within normal statistical ranges."
        )

    return {
        "risk_score": score,
        "risk_tier": tier,
        "agent_briefing_flags": flags,
    }


# ---------------------------------------------------------------------------
# MCP Tool
# ---------------------------------------------------------------------------

@mcp.tool()
def evaluate_tax_profile(
    gross_income: float,
    reported_1099_income: float,
    actual_1099_records: float,
    charitable_contributions: float,
    consecutive_business_losses_years: int,
) -> str:
    """
    Evaluate a taxpayer's financial profile and return a Modernized DIF Risk Score.

    Parameters
    ----------
    gross_income                    : Total gross income reported on the return.
    reported_1099_income            : 1099 income the taxpayer self-reported.
    actual_1099_records             : 1099 income found in IRS third-party database (mock).
    charitable_contributions        : Total charitable contribution deductions claimed.
    consecutive_business_losses_years : Number of consecutive years with a net business loss.

    Returns
    -------
    JSON string with keys: risk_score (int 0–100), risk_tier (str), agent_briefing_flags (list[str]).
    """
    result = _compute_risk(
        gross_income=gross_income,
        reported_1099_income=reported_1099_income,
        actual_1099_records=actual_1099_records,
        charitable_contributions=charitable_contributions,
        consecutive_business_losses_years=consecutive_business_losses_years,
    )
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
# A Prompt is a reusable message template that the AI agent (or user) can
# invoke by name.  FastMCP passes your return value straight into the
# conversation as pre-formed messages — think of it as a guided question
# sequence that steers the model's next reply.
#
# Declare one with @mcp.prompt().
# Return a single Message or a list of Messages.
# Each Message has a role ("user" or "assistant") and a text body.
#
# How to invoke from Bob / the agent:
#   → Ask: "Use the audit_intake_interview prompt for taxpayer John Doe"
#   → The model receives the rendered messages and responds in that context.
# ---------------------------------------------------------------------------

@mcp.prompt()
def audit_intake_interview(taxpayer_name: str, tax_year: int) -> List[Message]:
    """
    Guided intake interview prompt for a new audit case.

    Produces a structured multi-turn message sequence that directs the AI to
    walk an IRS examiner through collecting the five data points required by
    evaluate_tax_profile, one question at a time.

    Parameters
    ----------
    taxpayer_name : Full name or entity name on the return.
    tax_year      : The tax year under review (e.g. 2023).
    """
    return [
        Message(
            role="user",
            content=(
                f"You are an IRS intake assistant opening a risk-screening session "
                f"for taxpayer **{taxpayer_name}** for tax year **{tax_year}**.\n\n"
                f"Ask the examiner for each of the following values, one at a time, "
                f"confirming each answer before moving to the next:\n"
                f"1. Total gross income reported on the return\n"
                f"2. 1099 income the taxpayer self-reported\n"
                f"3. 1099 income found in IRS third-party records (database lookup)\n"
                f"4. Total charitable contribution deductions claimed\n"
                f"5. Number of consecutive years with a net business loss\n\n"
                f"Once all five values are collected, call the `evaluate_tax_profile` "
                f"tool automatically and present the resulting risk score and flags."
            ),
        ),
        Message(
            role="assistant",
            content=(
                f"Understood. Opening intake for **{taxpayer_name}** (TY {tax_year}).\n\n"
                f"**Question 1 of 5:** What is the total gross income reported on the return?"
            ),
        ),
    ]


@mcp.prompt()
def explain_risk_score(risk_score: int, risk_tier: str) -> Message:
    """
    Ask the AI to explain a previously computed DIF risk score in plain English.

    Parameters
    ----------
    risk_score : The numeric score (0–100) returned by evaluate_tax_profile.
    risk_tier  : The tier label ("Low", "Medium", or "High").
    """
    return Message(
        role="user",
        content=(
            f"A taxpayer received a Modernized DIF risk score of **{risk_score}/100** "
            f"({risk_tier} tier). Explain in plain, non-technical language what this "
            f"score means, what IRS examination actions are typically associated with "
            f"this tier, and what the taxpayer should do to respond."
        ),
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------
# A Resource exposes read-only reference data at a stable URI.  The agent
# can fetch it any time it needs context — without calling a tool.
#
# Declare one with @mcp.resource("scheme://path").
# Return a plain string (text/plain) or a JSON-serialisable value.
#
# How to invoke from Bob / the agent:
#   → Ask: "Read the IRS risk scoring guide"
#   → The model fetches the URI and injects the content into its context.
# ---------------------------------------------------------------------------

@mcp.resource("irs://risk-scoring/guide")
def risk_scoring_guide() -> str:
    """
    Reference guide describing the three DIF risk flags and their thresholds.
    The agent reads this resource to answer questions about scoring methodology
    without having to call evaluate_tax_profile.
    """
    return json.dumps({
        "title": "IRS Modernized DIF Scoring Guide",
        "version": "1.0",
        "flags": [
            {
                "id": "INCOME_MISMATCH",
                "weight": 40,
                "rule": "actual_1099_records > reported_1099_income",
                "description": (
                    "Third-party 1099 filings from employers, banks, and brokerages "
                    "exceed what the taxpayer declared. Indicates potential underreporting "
                    "of income (IRC § 6201)."
                ),
            },
            {
                "id": "OUTLIER_DEDUCTIONS",
                "weight": 30,
                "rule": "charitable_contributions / gross_income > 0.20",
                "description": (
                    "Charitable deductions exceed 20% of gross income — a statistical "
                    "outlier on Schedule A. May indicate inflated or fabricated donations "
                    "(IRC § 170)."
                ),
            },
            {
                "id": "HOBBY_LOSS_RISK",
                "weight": 30,
                "rule": "consecutive_business_losses_years >= 3",
                "description": (
                    "Three or more consecutive years of net business losses violates the "
                    "IRC § 183 Safe Harbor presumption (profit in 2 of 5 years). "
                    "Activity may be reclassified as a hobby, disallowing Schedule C losses."
                ),
            },
        ],
        "tiers": {
            "Low":    "0–39  — No immediate examination action required.",
            "Medium": "40–69 — Correspondence audit or document request likely.",
            "High":   "70–100 — Field examination or full audit recommended.",
        },
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
