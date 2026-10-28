"""Income reconciliation utility — pure function, no I/O.

Handles:
- Duplicate records (same record_id appearing more than once).
- Corrected records (status=CORRECTED; the original is voided and replaced).
- Missing records (a corrected form references an original that is absent).
- Net reconciled total vs. self-reported total → discrepancy calculation.
"""

from __future__ import annotations

import logging

from irs_risk.models import (
    Form1099Record,
    ReconciliationRecord,
    ReconcileIncomeInput,
    ReconcileIncomeOutput,
    RecordStatus,
)

log = logging.getLogger(__name__)


def reconcile_income(inp: ReconcileIncomeInput) -> ReconcileIncomeOutput:
    """
    Reconcile a set of 1099 records against a self-reported total.

    Algorithm
    ---------
    1. Detect duplicate record_ids; keep the first occurrence, mark the rest
       as DUPLICATE.
    2. For every CORRECTED record, locate the original it replaces
       (corrects_record_id) and mark that original as CORRECTED (voided).
       If the original is absent, emit a MISSING placeholder.
    3. Sum amounts from all records that remain ORIGINAL (not voided,
       not duplicate, not missing).
    4. Compute discrepancy = reconciled_total - reported_total.
       Positive → potential underreporting; negative → over-reporting.

    Parameters
    ----------
    inp : Validated ReconcileIncomeInput.

    Returns
    -------
    ReconcileIncomeOutput with per-record annotations and a discrepancy figure.
    """
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
            ))
        else:
            seen_ids[rec.record_id] = len(deduped)
            deduped.append(rec)

    # Pass 2: handle corrections — void originals, detect missing originals.
    # We track voided record_ids in a separate set so we can distinguish:
    #   - voided originals  (record that was superseded → do NOT count)
    #   - live corrections  (the correction form itself → DO count its amount)
    voided_ids: set[str] = set()
    notes_map: dict[str, str] = {}
    original_ids: set[str] = {r.record_id for r in deduped}

    for rec in deduped:
        if rec.status == RecordStatus.CORRECTED and rec.corrects_record_id:
            orig_id = rec.corrects_record_id
            if orig_id in original_ids:
                # Mark the original as voided
                voided_ids.add(orig_id)
                notes_map[orig_id] = (
                    f"Voided: superseded by corrected record '{rec.record_id}'."
                )
                log.debug(
                    "case=%s record=%s voids original=%s",
                    inp.case_id, rec.record_id, orig_id,
                )
            else:
                # Original is missing from the record set
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
                ))

    # Pass 3: build annotated records for the deduped list.
    # Count rule:
    #   - ORIGINAL and not voided → count amount
    #   - CORRECTED (live correction form) and not voided → count amount
    #   - voided original → annotated as CORRECTED, do NOT count
    reconciled_total = 0.0
    for rec in deduped:
        is_voided = rec.record_id in voided_ids
        if is_voided:
            display_status = RecordStatus.CORRECTED  # voided original
        else:
            display_status = rec.status
        note = notes_map.get(rec.record_id)
        annotated.append(ReconciliationRecord(
            record_id=rec.record_id,
            payer_name=rec.payer_name,
            amount=rec.amount,
            form_type=rec.form_type,
            status=display_status,
            note=note,
        ))
        # Count if the record is live (not voided) and not a duplicate
        if not is_voided and display_status in (RecordStatus.ORIGINAL, RecordStatus.CORRECTED):
            reconciled_total += rec.amount

    discrepancy = round(reconciled_total - inp.reported_total, 2)

    if discrepancy > 0:
        direction = f"${discrepancy:,.2f} potential underreporting"
    elif discrepancy < 0:
        direction = f"${abs(discrepancy):,.2f} over-reporting (reported more than reconciled)"
    else:
        direction = "no discrepancy"

    summary = (
        f"Reconciled total: ${reconciled_total:,.2f}. "
        f"Self-reported total: ${inp.reported_total:,.2f}. "
        f"Discrepancy: {direction}."
    )

    log.info(
        "case=%s year=%d reconciled=%.2f reported=%.2f discrepancy=%.2f",
        inp.case_id, inp.tax_year, reconciled_total, inp.reported_total, discrepancy,
    )

    return ReconcileIncomeOutput(
        case_id=inp.case_id,
        tax_year=inp.tax_year,
        reported_total=inp.reported_total,
        reconciled_total=round(reconciled_total, 2),
        discrepancy=discrepancy,
        records=annotated,
        summary=summary,
    )
