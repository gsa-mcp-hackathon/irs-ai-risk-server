"""Tests for the guidance tool — matching, no-match, and tax-year filtering."""

from __future__ import annotations

import pytest

from irs_risk.tools.get_irs_guidance import _match_guidance


class TestGuidanceMatching:
    def test_irc_183_keyword_returns_result(self):
        results = _match_guidance("IRC 183 hobby loss", None)
        assert len(results) >= 1
        assert any("183" in r.source for r in results)

    def test_charitable_keyword_returns_result(self):
        results = _match_guidance("charitable contribution deduction limits", None)
        assert len(results) >= 1
        assert any("170" in r.source for r in results)

    def test_1099_keyword_returns_result(self):
        results = _match_guidance("1099 income mismatch third party", None)
        assert len(results) >= 1

    def test_unknown_topic_returns_empty(self):
        results = _match_guidance("cryptocurrency decentralized exchange exotic derivatives", None)
        assert results == []

    def test_tax_year_is_propagated_to_result(self):
        results = _match_guidance("IRC 183 hobby loss", 2023)
        assert all(r.tax_year_applicable == 2023 for r in results)

    def test_tax_year_none_leaves_year_null_for_undated_entries(self):
        results = _match_guidance("IRC 183 hobby loss", None)
        # Static entries with tax_years=None: applicable year remains None
        assert all(r.tax_year_applicable is None for r in results)

    def test_irc_183_summary_mentions_nine_factors(self):
        results = _match_guidance("183 hobby", None)
        joined = " ".join(r.summary for r in results)
        assert "nine" in joined.lower() or "9" in joined

    def test_irc_183_summary_says_not_automatically(self):
        results = _match_guidance("hobby loss", None)
        joined = " ".join(r.summary for r in results)
        # Must not claim losses automatically establish hobby status
        assert "automatically" not in joined.lower() or "not" in joined.lower()

    def test_all_results_have_source_and_url(self):
        results = _match_guidance("charitable contribution", None)
        for r in results:
            assert r.source
            assert r.url


class TestSyntheticRecord:
    def test_same_seed_produces_same_record(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r1 = generate_synthetic_record("SEED-ABC", 2023, "baseline")
        r2 = generate_synthetic_record("SEED-ABC", 2023, "baseline")
        assert r1["profile"]["gross_income"] == r2["profile"]["gross_income"]

    def test_different_seeds_produce_different_records(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r1 = generate_synthetic_record("SEED-AAA", 2023, "baseline")
        r2 = generate_synthetic_record("SEED-ZZZ", 2023, "baseline")
        assert r1["profile"]["gross_income"] != r2["profile"]["gross_income"]

    def test_multi_flag_scenario_has_nonzero_mismatch(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r = generate_synthetic_record("SEED-X", 2023, "multi_flag")
        assert r["profile"]["third_party_1099_total"] > r["profile"]["reported_1099_income"]

    def test_clean_scenario_has_no_mismatch(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r = generate_synthetic_record("SEED-X", 2023, "clean")
        assert r["profile"]["third_party_1099_total"] <= r["profile"]["reported_1099_income"]

    def test_invalid_scenario_falls_back_to_baseline(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r = generate_synthetic_record("SEED-X", 2023, "nonexistent_scenario")
        assert r["scenario"] == "baseline"

    def test_record_has_disclaimer(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r = generate_synthetic_record("SEED-X", 2023, "baseline")
        assert "SYNTHETIC" in r["note"]

    def test_records_1099_have_traceable_ids(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r = generate_synthetic_record("SEED-X", 2023, "baseline")
        for rec in r["records_1099"]:
            assert "SEED-X" in rec["record_id"]
