"""Tool: irs_reconcile_income

Reconciles a set of 1099 records against a self-reported total.
Handles duplicates, corrected forms, and missing originals.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from irs_risk.models import Form1099Record, ReconcileIncomeInput, RecordStatus
from irs_risk.reconcile import reconcile_income


def register(mcp: FastMCP) -> None:
    """Register the irs_reconcile_income tool."""

    @mcp.tool(
        name="irs_reconcile_income",
        annotations={
            "title": "Reconcile 1099 Income Records",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def irs_reconcile_income(
        case_id: Annotated[str, "Case reference ID. No PII."],
        tax_year: Annotated[int, "Calendar tax year, e.g. 2023."],
        reported_total: Annotated[
            float,
            "Total 1099 income the taxpayer self-reported on the return, in USD.",
        ],
        records: Annotated[
            list[dict],
            (
                "List of 1099 record objects. Each must have: "
                "record_id (str), payer_name (str), amount (float ≥ 0), "
                "form_type (str, e.g. '1099-NEC'), tax_year (int), "
                "status ('original'|'corrected'|'duplicate'|'missing'), "
                "corrects_record_id (str|null, required when status='corrected')."
            ),
        ],
    ) -> dict:
        """
        Reconcile a list of 1099 records against a self-reported income total.

        The tool detects:
        - Duplicate record_ids (first occurrence wins; rest are flagged).
        - Corrected records (the original they replace is voided).
        - Missing originals (corrected form references a record not in the set).

        Returns a structured object with per-record annotations, a reconciled
        total (sum of all live original amounts), and a discrepancy figure
        (positive = potential underreporting, negative = over-reporting).
        """
        parsed_records = [Form1099Record(**r) for r in records]
        inp = ReconcileIncomeInput(
            case_id=case_id,
            tax_year=tax_year,
            reported_total=reported_total,
            records=parsed_records,
        )
        result = reconcile_income(inp)
        return result.model_dump()
