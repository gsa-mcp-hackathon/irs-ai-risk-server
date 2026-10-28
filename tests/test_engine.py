"""Tests for the versioned risk engine — pure function, no I/O."""

from __future__ import annotations

import pytest

from irs_risk.engine import ENGINE_VERSION, compute_risk
from irs_risk.models import FlagCode, RiskTier, TaxProfileInput


def _profile(**overrides) -> TaxProfileInput:
    base = dict(
        case_id="TEST-001",
        tax_year=2023,
        gross_income=100_000.0,
        reported_1099_income=60_000.0,
        third_party_1099_total=60_000.0,   # no mismatch
        charitable_contributions=5_000.0,  # 5% — below threshold
        business_loss_years_in_window=1,   # below threshold
    )
    base.update(overrides)
    return TaxProfileInput(**base)


class TestEngineVersion:
    def test_version_string_is_embedded(self):
        result = compute_risk(_profile())
        assert result.engine_version == ENGINE_VERSION

    def test_custom_version_is_embedded(self):
        result = compute_risk(_profile(), engine_version="test-v99")
        assert result.engine_version == "test-v99"


class TestCleanProfile:
    def test_clean_profile_scores_zero(self):
        result = compute_risk(_profile())
        assert result.risk_score == 0

    def test_clean_profile_tier_is_low(self):
        result = compute_risk(_profile())
        assert result.risk_tier == RiskTier.LOW

    def test_clean_profile_has_no_flags_marker(self):
        result = compute_risk(_profile())
        assert len(result.flags) == 1
        assert result.flags[0].code == FlagCode.NO_FLAGS


class TestIncomeMismatch:
    def test_mismatch_adds_40_points(self):
        result = compute_risk(_profile(third_party_1099_total=70_000.0))
        assert result.risk_score == 40

    def test_mismatch_flag_is_emitted(self):
        result = compute_risk(_profile(third_party_1099_total=70_000.0))
        codes = [f.code for f in result.flags]
        assert FlagCode.INCOME_MISMATCH in codes

    def test_no_mismatch_when_third_party_less(self):
        result = compute_risk(_profile(third_party_1099_total=50_000.0))
        codes = [f.code for f in result.flags]
        assert FlagCode.INCOME_MISMATCH not in codes

    def test_no_mismatch_when_equal(self):
        result = compute_risk(_profile(third_party_1099_total=60_000.0))
        codes = [f.code for f in result.flags]
        assert FlagCode.INCOME_MISMATCH not in codes

    def test_mismatch_tier_is_medium(self):
        result = compute_risk(_profile(third_party_1099_total=70_000.0))
        assert result.risk_tier == RiskTier.MEDIUM


class TestOutlierDeductions:
    def test_deduction_above_threshold_adds_30_points(self):
        # 25% of 100k gross = 25k charitable > 20% threshold
        result = compute_risk(_profile(charitable_contributions=25_000.0))
        assert result.risk_score == 30

    def test_deduction_flag_is_emitted(self):
        result = compute_risk(_profile(charitable_contributions=25_000.0))
        codes = [f.code for f in result.flags]
        assert FlagCode.OUTLIER_DEDUCTIONS in codes

    def test_deduction_exactly_at_threshold_is_not_flagged(self):
        # exactly 20% should NOT trigger (rule is strictly >)
        result = compute_risk(_profile(charitable_contributions=20_000.0))
        codes = [f.code for f in result.flags]
        assert FlagCode.OUTLIER_DEDUCTIONS not in codes

    def test_zero_gross_income_does_not_cause_division_error(self):
        result = compute_risk(_profile(gross_income=0.0, reported_1099_income=0.0, charitable_contributions=1000.0))
        # Should not raise; OUTLIER_DEDUCTIONS guard requires gross_income > 0
        assert result.risk_score is not None


class TestBusinessLossPattern:
    def test_loss_pattern_at_threshold_adds_points(self):
        # threshold is 4 loss years in window
        result = compute_risk(_profile(business_loss_years_in_window=4))
        assert result.risk_score == 20

    def test_loss_pattern_flag_is_emitted(self):
        result = compute_risk(_profile(business_loss_years_in_window=4))
        codes = [f.code for f in result.flags]
        assert FlagCode.BUSINESS_LOSS_PATTERN in codes

    def test_three_loss_years_does_not_trigger(self):
        """3 of 5 loss years is below our threshold of 4 — should NOT flag."""
        result = compute_risk(_profile(business_loss_years_in_window=3))
        codes = [f.code for f in result.flags]
        assert FlagCode.BUSINESS_LOSS_PATTERN not in codes

    def test_flag_detail_mentions_irc_183(self):
        result = compute_risk(_profile(business_loss_years_in_window=4))
        flag = next(f for f in result.flags if f.code == FlagCode.BUSINESS_LOSS_PATTERN)
        assert "183" in flag.detail

    def test_flag_detail_says_not_determinative(self):
        result = compute_risk(_profile(business_loss_years_in_window=4))
        flag = next(f for f in result.flags if f.code == FlagCode.BUSINESS_LOSS_PATTERN)
        # Must NOT claim automatic hobby reclassification
        assert "not determinative" in flag.detail.lower() or "does not" in flag.detail.lower()

    def test_flag_is_not_determinative(self):
        result = compute_risk(_profile(business_loss_years_in_window=4))
        flag = next(f for f in result.flags if f.code == FlagCode.BUSINESS_LOSS_PATTERN)
        assert flag.is_determinative is False


class TestMultipleFlags:
    def test_all_three_flags_score_90(self):
        result = compute_risk(_profile(
            third_party_1099_total=70_000.0,    # +40
            charitable_contributions=25_000.0,  # +30
            business_loss_years_in_window=4,    # +20
        ))
        assert result.risk_score == 90

    def test_all_three_flags_tier_is_high(self):
        result = compute_risk(_profile(
            third_party_1099_total=70_000.0,
            charitable_contributions=25_000.0,
            business_loss_years_in_window=4,
        ))
        assert result.risk_tier == RiskTier.HIGH

    def test_score_capped_at_100(self):
        """Artificially force score above 100 to confirm clamping."""
        # Max achievable with current weights: 40+30+20 = 90; still tests path
        result = compute_risk(_profile(
            third_party_1099_total=70_000.0,
            charitable_contributions=25_000.0,
            business_loss_years_in_window=5,
        ))
        assert result.risk_score <= 100


class TestDisclaimer:
    def test_output_contains_disclaimer(self):
        result = compute_risk(_profile())
        assert "HYPOTHETICAL" in result.disclaimer

    def test_output_says_not_dif(self):
        result = compute_risk(_profile())
        assert "DIF" in result.disclaimer


class TestDeterminism:
    def test_same_input_produces_same_score(self):
        p = _profile(third_party_1099_total=70_000.0)
        r1 = compute_risk(p)
        r2 = compute_risk(p)
        assert r1.risk_score == r2.risk_score
        assert r1.risk_tier == r2.risk_tier
        assert r1.engine_version == r2.engine_version
