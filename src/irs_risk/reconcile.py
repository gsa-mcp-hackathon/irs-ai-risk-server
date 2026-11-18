"""Income reconciliation utility — pure function, no I/O.

Handles:
- Duplicate records (same record_id appearing more than once).
- Corrected records (status=CORRECTED; the original is voided and replaced).
- Missing records (a corrected form references an original that is absent).
- Net reconciled total vs. self-reported total → discrepancy calculation.

Monetary arithmetic
-------------------
All summation uses Python ``Decimal`` with ``ROUND_HALF_EVEN`` (banker's
rounding) to two decimal places. This avoids the float accumulation errors
that can arise when summing many cent-level values. The output ``float``
fields are converted from ``Decimal`` at the end so downstream consumers do
not need to handle ``Decimal`` themselves; the ``arithmetic_trace`` strings
hold the authoritative exact-decimal values.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_EVEN, Decimal

from irs_risk.models import (
    Form1099Record,
    ReconciliationArithmeticTrace,
    ReconciliationRecord,
    ReconcileIncomeInput,
    ReconcileIncomeOutput,
    RecordStatus,
)

log = logging.getLogger(__name__)

_CENTS = Decimal("0.01")


def _to_decimal(value: float) -> Decimal:
    """Convert a float to a Decimal quantized to two decimal places."""
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_EVEN)


def reconcile_income(inp: ReconcileIncomeInput) -> ReconcileIncomeOutput:
    """
    Reconcile a set of 1099 records against a self-reported total.

    Algorithm
    ---------
    1. Detect duplicate record_ids; keep the first occurrence, mark the rest
       as DUPLICATE.
    2. For every CORRECTED record, locate the original it replaces
       (corrects_record_id) and mark that original as voided.
       If the original is absent, emit a MISSING placeholder.
    3. Sum amounts from all records that remain live (not voided, not
       duplicate, not missing) using Decimal arithmetic.
    4. Compute discrepancy = reconciled_total - reported_total.
       Positive → potential underreporting; negative → over-reporting.

    Parameters
    ----------
    inp : Validated ReconcileIncomeInput.

    Returns
    -------
    ReconcileIncomeOutput with per-record annotations, an arithmetic trace,
    and a discrepancy figure. All monetary totals use Decimal internally;
    output fields are float for JSON compatibility, with exact-decimal strings
    in arithmetic_trace for independent verification.
    """
    reported_d = _to_decimal(inp.reported_total)

    seen_ids: dict[str, int] = {}          # record_id → first-seen index
    annotated: list[ReconciliationRecord] = []

    # Pass 1: dedup — first occurrence wins; subsequent are DUPLICATE
    deduped: list[Form1099Record] = []
    for rec in inp.records:
        if rec.record_id in seen_ids:
            log.debug(
                "case=%s DUPLICATE record_id=%s", inp.case_id, rec.record_id
            )
            annotated.append(ReconciliationRecord(
                record_id=rec.record_id,
                payer_name=rec.payer_name,
                amount=rec.amount,
                form_type=rec.form_type,
                status=RecordStatus.DUPLICATE,
                note=f"Duplicate of record already seen at position {seen_ids[rec.record_id]}.",
                counted_in_total=False,
            ))
        else:
            seen_ids[rec.record_id] = len(deduped)
            deduped.append(rec)

    # Pass 2: handle corrections — void originals, detect missing originals.
    voided_ids: set[str] = set()
    notes_map: dict[str, str] = {}
    original_ids: set[str] = {r.record_id for r in deduped}

    for rec in deduped:
        if rec.status == RecordStatus.CORRECTED and rec.corrects_record_id:
            orig_id = rec.corrects_record_id
            if orig_id in original_ids:
                voided_ids.add(orig_id)
                notes_map[orig_id] = (
                    f"Voided: superseded by corrected record '{rec.record_id}'."
                )
                log.debug(
                    "case=%s record=%s voids original=%s",
                    inp.case_id, rec.record_id, orig_id,
                )
            else:
                log.debug(
                    "case=%s MISSING original=%s referenced by corrected=%s",
                    inp.case_id, orig_id, rec.record_id,
                )
                annotated.append(ReconciliationRecord(
                    record_id=orig_id,
                    payer_name="(unknown — missing from record set)",
                    amount=0.0,
                    form_type="unknown",
                    status=RecordStatus.MISSING,
                    note=(
                        f"Referenced as original by corrected record '{rec.record_id}' "
                        f"but not present in the submitted record set."
                    ),
                    counted_in_total=False,
                ))

    # Pass 3: build annotated records; accumulate reconciled total with Decimal.
    reconciled_d = Decimal("0.00")
    counted_entries: list[dict] = []
    excluded_entries: list[dict] = []

    for rec in deduped:
        is_voided = rec.record_id in voided_ids
        display_status = RecordStatus.CORRECTED if is_voided else rec.status
        note = notes_map.get(rec.record_id)

        # A record is counted if it is live (not voided) and its status is
        # ORIGINAL or CORRECTED (the correction form itself, not the voided original).
        counted = (
            not is_voided
            and display_status in (RecordStatus.ORIGINAL, RecordStatus.CORRECTED)
        )

        amount_d = _to_decimal(rec.amount)
        if counted:
            reconciled_d += amount_d
            counted_entries.append({
                "record_id": rec.record_id,
                "payer_name": rec.payer_name,
                "amount_str": str(amount_d),
                "form_type": rec.form_type,
            })
        else:
            reason = (
                "voided original (superseded by corrected form)" if is_voided
                else display_status.value
            )
            excluded_entries.append({
                "record_id": rec.record_id,
                "status": display_status.value,
                "reason": reason,
            })

        annotated.append(ReconciliationRecord(
            record_id=rec.record_id,
            payer_name=rec.payer_name,
            amount=rec.amount,
            form_type=rec.form_type,
            status=display_status,
            note=note,
            counted_in_total=counted,
        ))

    reconciled_d = reconciled_d.quantize(_CENTS, rounding=ROUND_HALF_EVEN)
    discrepancy_d = (reconciled_d - reported_d).quantize(_CENTS, rounding=ROUND_HALF_EVEN)

    if discrepancy_d > 0:
        direction = f"${discrepancy_d:,} potential underreporting"
    elif discrepancy_d < 0:
        direction = f"${abs(discrepancy_d):,} over-reporting (reported more than reconciled)"
    else:
        direction = "no discrepancy"

    summary = (
        f"Reconciled total: ${reconciled_d:,}. "
        f"Self-reported total: ${reported_d:,}. "
        f"Discrepancy: {direction}."
    )

    trace = ReconciliationArithmeticTrace(
        reported_total_str=str(reported_d),
        counted_records=counted_entries,
        excluded_records=excluded_entries,
        reconciled_total_str=str(reconciled_d),
        discrepancy_str=str(discrepancy_d),
    )

    log.info(
        "case=%s year=%d reconciled=%s reported=%s discrepancy=%s engine=decimal",
        inp.case_id, inp.tax_year, reconciled_d, reported_d, discrepancy_d,
    )

    return ReconcileIncomeOutput(
        case_id=inp.case_id,
        tax_year=inp.tax_year,
        reported_total=float(reported_d),
        reconciled_total=float(reconciled_d),
        discrepancy=float(discrepancy_d),
        records=annotated,
        arithmetic_trace=trace,
        summary=summary,
    )
