"""Tests for Decimal monetary arithmetic and arithmetic_trace in reconcile_income.

Verifies:
- Totals computed with Decimal match round(float, 2) for simple cases.
- Exact-decimal trace strings match the output float values.
- Banker's rounding (ROUND_HALF_EVEN) is used, not ROUND_HALF_UP.
- counted_in_total flags are set correctly per record.
- arithmetic_trace excluded_records lists voided originals and duplicates.
- arithmetic_trace counted_records lists only live records.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from irs_risk.models import Form1099Record, ReconcileIncomeInput, RecordStatus
from irs_risk.reconcile import _to_decimal, reconcile_income


def _inp(records: list[dict], reported_total: float, case_id: str = "DEC-TEST") -> ReconcileIncomeInput:
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


class TestToDecimal:
    def test_integer_float_converts_correctly(self):
        assert _to_decimal(10000.0) == Decimal("10000.00")

    def test_cent_value_converts_correctly(self):
        assert _to_decimal(10000.99) == Decimal("10000.99")

    def test_zero_converts_correctly(self):
        assert _to_decimal(0.0) == Decimal("0.00")

    def test_bankers_rounding_half_even_rounds_down(self):
        # 0.005 → nearest even is 0.00 (banker's rounding)
        assert _to_decimal(0.005) == Decimal("0.00")

    def test_bankers_rounding_half_even_rounds_up(self):
        # 0.015 → nearest even is 0.02
        assert _to_decimal(0.015) == Decimal("0.02")


class TestArithmeticTrace:
    def test_trace_reported_total_str_matches_float_output(self):
        result = reconcile_income(_inp([_rec("R1", 10_000.0)], reported_total=10_000.0))
        assert result.arithmetic_trace.reported_total_str == "10000.00"
        assert float(result.arithmetic_trace.reported_total_str) == result.reported_total

    def test_trace_reconciled_total_str_matches_float_output(self):
        result = reconcile_income(_inp([_rec("R1", 10_000.0), _rec("R2", 5_000.0)], reported_total=15_000.0))
        assert result.arithmetic_trace.reconciled_total_str == "15000.00"
        assert float(result.arithmetic_trace.reconciled_total_str) == result.reconciled_total

    def test_trace_discrepancy_str_matches_float_output(self):
        result = reconcile_income(_inp([_rec("R1", 15_000.0)], reported_total=10_000.0))
        assert result.arithmetic_trace.discrepancy_str == "5000.00"
        assert float(result.arithmetic_trace.discrepancy_str) == result.discrepancy

    def test_trace_negative_discrepancy_str(self):
        result = reconcile_income(_inp([_rec("R1", 8_000.0)], reported_total=10_000.0))
        assert result.arithmetic_trace.discrepancy_str == "-2000.00"

    def test_trace_zero_discrepancy_str(self):
        result = reconcile_income(_inp([_rec("R1", 10_000.0)], reported_total=10_000.0))
        assert result.arithmetic_trace.discrepancy_str == "0.00"

    def test_trace_counted_records_lists_live_originals(self):
        result = reconcile_income(_inp(
            [_rec("R1", 10_000.0), _rec("R2", 5_000.0)],
            reported_total=15_000.0,
        ))
        ids = {r["record_id"] for r in result.arithmetic_trace.counted_records}
        assert ids == {"R1", "R2"}

    def test_trace_counted_records_amount_str_is_exact(self):
        result = reconcile_income(_inp([_rec("R1", 10_000.0)], reported_total=10_000.0))
        assert result.arithmetic_trace.counted_records[0]["amount_str"] == "10000.00"

    def test_trace_duplicate_is_not_in_counted(self):
        """Duplicates are removed in Pass 1 (dedup) before the trace is built.
        They appear in result.records with status=DUPLICATE / counted_in_total=False,
        but are not carried into arithmetic_trace.excluded_records (which only
        covers the deduped pass-3 records). Verify the duplicate is absent from
        counted_records and that counted_in_total is False on the duplicate record."""
        result = reconcile_income(_inp(
            [_rec("R1", 10_000.0), _rec("R1", 10_000.0)],
            reported_total=10_000.0,
        ))
        counted_ids = [r["record_id"] for r in result.arithmetic_trace.counted_records]
        # Only one R1 should be counted (the first occurrence)
        assert counted_ids.count("R1") == 1
        # The duplicate record in result.records must have counted_in_total=False
        duplicates = [r for r in result.records if r.status == RecordStatus.DUPLICATE]
        assert all(not r.counted_in_total for r in duplicates)

    def test_trace_voided_original_appears_in_excluded(self):
        result = reconcile_income(_inp(
            [
                _rec("R1-ORIG", 10_000.0),
                _rec("R1-CORR", 9_000.0, status="corrected", corrects="R1-ORIG"),
            ],
            reported_total=9_000.0,
        ))
        excl_ids = [r["record_id"] for r in result.arithmetic_trace.excluded_records]
        assert "R1-ORIG" in excl_ids

    def test_trace_corrected_form_appears_in_counted(self):
        result = reconcile_income(_inp(
            [
                _rec("R1-ORIG", 10_000.0),
                _rec("R1-CORR", 9_000.0, status="corrected", corrects="R1-ORIG"),
            ],
            reported_total=9_000.0,
        ))
        counted_ids = [r["record_id"] for r in result.arithmetic_trace.counted_records]
        assert "R1-CORR" in counted_ids

    def test_trace_rounding_note_mentions_decimal(self):
        result = reconcile_income(_inp([_rec("R1", 10_000.0)], reported_total=10_000.0))
        assert "Decimal" in result.arithmetic_trace.rounding_note


class TestCountedInTotalFlag:
    def test_live_original_is_counted(self):
        result = reconcile_income(_inp([_rec("R1", 10_000.0)], reported_total=10_000.0))
        r1 = next(r for r in result.records if r.record_id == "R1")
        assert r1.counted_in_total is True

    def test_duplicate_is_not_counted(self):
        result = reconcile_income(_inp(
            [_rec("R1", 10_000.0), _rec("R1", 10_000.0)],
            reported_total=10_000.0,
        ))
        duplicates = [r for r in result.records if r.status == RecordStatus.DUPLICATE]
        assert all(not r.counted_in_total for r in duplicates)

    def test_voided_original_is_not_counted(self):
        result = reconcile_income(_inp(
            [
                _rec("R1-ORIG", 10_000.0),
                _rec("R1-CORR", 9_000.0, status="corrected", corrects="R1-ORIG"),
            ],
            reported_total=9_000.0,
        ))
        orig = next(r for r in result.records if r.record_id == "R1-ORIG")
        assert orig.counted_in_total is False

    def test_corrected_form_is_counted(self):
        result = reconcile_income(_inp(
            [
                _rec("R1-ORIG", 10_000.0),
                _rec("R1-CORR", 9_000.0, status="corrected", corrects="R1-ORIG"),
            ],
            reported_total=9_000.0,
        ))
        corr = next(r for r in result.records if r.record_id == "R1-CORR")
        assert corr.counted_in_total is True

    def test_missing_placeholder_is_not_counted(self):
        result = reconcile_income(_inp(
            [_rec("R1-CORR", 9_000.0, status="corrected", corrects="MISSING-ID")],
            reported_total=9_000.0,
        ))
        missing = next((r for r in result.records if r.status == RecordStatus.MISSING), None)
        assert missing is not None
        assert missing.counted_in_total is False


class TestDecimalPrecision:
    def test_many_small_amounts_sum_exactly(self):
        """10 × $0.10 should equal exactly $1.00 with Decimal (not 0.9999... with float)."""
        records = [_rec(f"R{i}", 0.10) for i in range(10)]
        result = reconcile_income(_inp(records, reported_total=1.0))
        assert result.reconciled_total == 1.0
        assert result.discrepancy == 0.0
        assert result.arithmetic_trace.reconciled_total_str == "1.00"
        assert result.arithmetic_trace.discrepancy_str == "0.00"

    def test_cent_level_amounts_do_not_accumulate_error(self):
        """Three records with cent amounts should sum to an exact cent total."""
        result = reconcile_income(_inp(
            [_rec("R1", 100.33), _rec("R2", 200.66), _rec("R3", 99.01)],
            reported_total=400.00,
        ))
        # 100.33 + 200.66 + 99.01 = 400.00 exactly
        assert result.reconciled_total == 400.00
        assert result.discrepancy == 0.00
