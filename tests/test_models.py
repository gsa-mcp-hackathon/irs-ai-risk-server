"""Tests for the Pydantic models — validation, constraints, and custom validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from irs_risk.models import (
    Form1099Record,
    RecordStatus,
    TaxProfileInput,
)


# ── TaxProfileInput ───────────────────────────────────────────────────────────

class TestTaxProfileInput:
    def _valid(self, **overrides) -> dict:
        base = dict(
            case_id="CASE-2023-001",
            tax_year=2023,
            gross_income=100_000.0,
            reported_1099_income=60_000.0,
            third_party_1099_total=60_000.0,
            charitable_contributions=5_000.0,
            business_loss_years_in_window=1,
        )
        base.update(overrides)
        return base

    def test_valid_profile_parses(self):
        p = TaxProfileInput(**self._valid())
        assert p.case_id == "CASE-2023-001"
        assert p.gross_income == 100_000.0

    def test_reported_1099_cannot_exceed_gross(self):
        with pytest.raises(ValidationError, match="reported_1099_income"):
            TaxProfileInput(**self._valid(
                gross_income=50_000.0,
                reported_1099_income=60_000.0,
            ))

    def test_negative_gross_income_rejected(self):
        with pytest.raises(ValidationError):
            TaxProfileInput(**self._valid(gross_income=-1.0))

    def test_tax_year_too_early_rejected(self):
        with pytest.raises(ValidationError):
            TaxProfileInput(**self._valid(tax_year=1985))

    def test_tax_year_too_late_rejected(self):
        with pytest.raises(ValidationError):
            TaxProfileInput(**self._valid(tax_year=2031))

    def test_business_loss_years_upper_bound(self):
        with pytest.raises(ValidationError):
            TaxProfileInput(**self._valid(business_loss_years_in_window=11))

    def test_empty_case_id_rejected(self):
        with pytest.raises(ValidationError):
            TaxProfileInput(**self._valid(case_id=""))


# ── Form1099Record ────────────────────────────────────────────────────────────

class TestForm1099Record:
    def test_original_record_valid(self):
        r = Form1099Record(
            record_id="R-001",
            payer_name="Acme Corp",
            amount=10_000.0,
            form_type="1099-NEC",
            tax_year=2023,
        )
        assert r.status == RecordStatus.ORIGINAL

    def test_corrected_record_requires_target(self):
        with pytest.raises(ValidationError, match="corrects_record_id"):
            Form1099Record(
                record_id="R-002",
                payer_name="Acme Corp",
                amount=10_000.0,
                form_type="1099-NEC",
                tax_year=2023,
                status=RecordStatus.CORRECTED,
                # corrects_record_id intentionally omitted
            )

    def test_corrected_record_with_target_valid(self):
        r = Form1099Record(
            record_id="R-002",
            payer_name="Acme Corp",
            amount=11_000.0,
            form_type="1099-NEC",
            tax_year=2023,
            status=RecordStatus.CORRECTED,
            corrects_record_id="R-001",
        )
        assert r.corrects_record_id == "R-001"

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            Form1099Record(
                record_id="R-003",
                payer_name="Bad Corp",
                amount=-100.0,
                form_type="1099-INT",
                tax_year=2023,
            )
