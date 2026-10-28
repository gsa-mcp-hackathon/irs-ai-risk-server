"""Tests for the income reconciliation utility."""

from __future__ import annotations

import pytest

from irs_risk.models import Form1099Record, ReconcileIncomeInput, RecordStatus
from irs_risk.reconcile import reconcile_income


def _inp(records: list[dict], reported_total: float = 0.0, case_id: str = "TEST-R-001") -> ReconcileIncomeInput:
    return ReconcileIncomeInput(
        case_id=case_id,
        tax_year=2023,
        reported_total=reported_total,
        records=[Form1099Record(**r) for r in records],
    )


def _rec(record_id: str, amount: float, status: str = "original", corrects: str | None = None) -> dict:
    return {
        "record_id": record_id,
        "payer_name": f"Payer-{record_id}",
        "amount": amount,
        "form_type": "1099-NEC",
        "tax_year": 2023,
        "status": status,
        "corrects_record_id": corrects,
    }


class TestNoAnomalies:
    def test_simple_total_matches_reported(self):
        result = reconcile_income(_inp(
            [_rec("R1", 10_000), _rec("R2", 5_000)],
            reported_total=15_000.0,
        ))
        assert result.reconciled_total == 15_000.0
        assert result.discrepancy == 0.0

    def test_reconciled_total_sums_only_originals(self):
        result = reconcile_income(_inp([_rec("R1", 10_000), _rec("R2", 5_000)]))
        assert result.reconciled_total == 15_000.0


class TestDuplicateDetection:
    def test_duplicate_record_id_is_flagged(self):
        result = reconcile_income(_inp([
            _rec("R1", 10_000),
            _rec("R1", 10_000),  # duplicate
        ]))
        statuses = {r.record_id: r.status for r in result.records}
        duplicate_entries = [r for r in result.records if r.status == RecordStatus.DUPLICATE]
        assert len(duplicate_entries) == 1

    def test_duplicate_not_counted_in_reconciled_total(self):
        result = reconcile_income(_inp([
            _rec("R1", 10_000),
            _rec("R1", 10_000),  # duplicate — should not be counted
        ]))
        assert result.reconciled_total == 10_000.0

    def test_first_occurrence_wins(self):
        result = reconcile_income(_inp([
            _rec("R1", 10_000),
            _rec("R1", 99_999),  # second occurrence: should be duplicate
        ]))
        original = next(r for r in result.records if r.status == RecordStatus.ORIGINAL)
        assert original.amount == 10_000.0


class TestCorrectedRecords:
    def test_corrected_record_voids_original(self):
        result = reconcile_income(_inp([
            _rec("R1", 10_000),
            _rec("R2", 11_000, status="corrected", corrects="R1"),
        ]))
        r1 = next(r for r in result.records if r.record_id == "R1")
        assert r1.status == RecordStatus.CORRECTED

    def test_corrected_amount_is_counted_original_is_not(self):
        result = reconcile_income(_inp([
            _rec("R1", 10_000),
            _rec("R2", 11_000, status="corrected", corrects="R1"),
        ]))
        # R2 has status=CORRECTED (the correction form itself); R1 is voided
        # Only records whose effective status is ORIGINAL count
        assert result.reconciled_total == 11_000.0

    def test_correction_referencing_absent_original_creates_missing_placeholder(self):
        result = reconcile_income(_inp([
            _rec("R2", 11_000, status="corrected", corrects="MISSING-ORIGINAL"),
        ]))
        missing = [r for r in result.records if r.status == RecordStatus.MISSING]
        assert len(missing) == 1
        assert missing[0].record_id == "MISSING-ORIGINAL"


class TestDiscrepancy:
    def test_underreporting_gives_positive_discrepancy(self):
        result = reconcile_income(_inp(
            [_rec("R1", 15_000)],
            reported_total=10_000.0,
        ))
        assert result.discrepancy == 5_000.0

    def test_over_reporting_gives_negative_discrepancy(self):
        result = reconcile_income(_inp(
            [_rec("R1", 8_000)],
            reported_total=10_000.0,
        ))
        assert result.discrepancy == -2_000.0

    def test_exact_match_gives_zero_discrepancy(self):
        result = reconcile_income(_inp(
            [_rec("R1", 10_000)],
            reported_total=10_000.0,
        ))
        assert result.discrepancy == 0.0

    def test_summary_mentions_discrepancy(self):
        result = reconcile_income(_inp(
            [_rec("R1", 15_000)],
            reported_total=10_000.0,
        ))
        assert "5,000" in result.summary or "5000" in result.summary
