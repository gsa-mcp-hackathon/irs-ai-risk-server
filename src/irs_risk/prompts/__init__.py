"""Prompts module — preserves existing prompts from the prototype."""

from __future__ import annotations

from typing import List

from fastmcp import FastMCP
from fastmcp.prompts import Message


def register_prompts(mcp: FastMCP) -> None:
    """Register all IRS risk prompts."""

    @mcp.prompt()
    def audit_intake_interview(taxpayer_name: str, tax_year: int) -> List[Message]:
        """
        Guided intake interview prompt for a new audit case.

        Produces a structured multi-turn message sequence that directs the AI to
        walk an IRS examiner through collecting the data points required by
        irs_evaluate_tax_profile, one question at a time.

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
                    f"for case reference **{taxpayer_name}** for tax year **{tax_year}**.\n\n"
                    f"Ask the examiner for each of the following values, one at a time, "
                    f"confirming each answer before moving to the next:\n"
                    f"1. Total gross income reported on the return\n"
                    f"2. 1099 income the taxpayer self-reported\n"
                    f"3. Total 1099 income in third-party information returns\n"
                    f"4. Total charitable contribution deductions claimed on Schedule A\n"
                    f"5. Number of years with a net business loss in the last 5 years\n\n"
                    f"Once all five values are collected, call the `irs_evaluate_tax_profile` "
                    f"tool automatically and present the resulting risk score and flags. "
                    f"Remind the examiner that the score is produced by a HYPOTHETICAL model "
                    f"and does not represent official IRS methodology."
                ),
            ),
            Message(
                role="assistant",
                content=(
                    f"Understood. Opening intake session for **{taxpayer_name}** "
                    f"(TY {tax_year}).\n\n"
                    f"**Question 1 of 5:** What is the total gross income reported on the return?"
                ),
            ),
        ]

    @mcp.prompt()
    def explain_risk_score(risk_score: int, risk_tier: str) -> Message:
        """
        Ask the AI to explain a previously computed risk score in plain English.

        Parameters
        ----------
        risk_score : The numeric score (0–100) returned by irs_evaluate_tax_profile.
        risk_tier  : The tier label ("Low", "Medium", or "High").
        """
        return Message(
            role="user",
            content=(
                f"A taxpayer profile received a hypothetical risk score of "
                f"**{risk_score}/100** ({risk_tier} tier) from the IRS AI risk prototype.\n\n"
                f"Explain in plain, non-technical language:\n"
                f"1. What the score means in the context of statistical anomaly detection.\n"
                f"2. What types of examiner actions are typically associated with this tier.\n"
                f"3. What a taxpayer might do to address the flagged items.\n\n"
                f"Remind the reader that this score is produced by a HYPOTHETICAL model, "
                f"does not implement the actual IRS DIF methodology, and that no legal "
                f"conclusions should be drawn from it without independent examiner review."
            ),
        )
