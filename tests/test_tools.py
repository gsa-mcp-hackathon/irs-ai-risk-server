"""Tests for the guidance tool — matching, no-match, tax-year filtering,
retrieval metadata, and corrected-1099 synthetic record trace."""

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


class TestGuidanceRetrievalMetadata:
    def test_all_results_have_retrieval_metadata(self):
        results = _match_guidance("IRC 183 hobby loss", None)
        for r in results:
            assert r.retrieval_metadata is not None

    def test_retrieval_mode_is_static_offline(self):
        results = _match_guidance("IRC 183 hobby loss", None)
        for r in results:
            assert r.retrieval_metadata.retrieval_mode == "static/offline"

    def test_registry_edition_is_set(self):
        results = _match_guidance("charitable contribution", None)
        for r in results:
            assert r.retrieval_metadata.registry_edition != ""

    def test_verification_status_is_set_for_all_entries(self):
        for topic in ["183 hobby", "charitable", "1099", "schedule c", "audit"]:
            results = _match_guidance(topic, None)
            for r in results:
                assert r.retrieval_metadata.verification_status not in (None, "", "not recorded"), (
                    f"Entry '{r.source}' has no verification_status"
                )

    def test_checked_date_is_iso8601(self):
        import re
        results = _match_guidance("1099 income mismatch", None)
        for r in results:
            assert r.retrieval_metadata.checked_date is not None
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", r.retrieval_metadata.checked_date), (
                f"checked_date '{r.retrieval_metadata.checked_date}' is not YYYY-MM-DD"
            )

    def test_currency_warning_mentions_irs_gov(self):
        results = _match_guidance("IRC 183 hobby loss", None)
        for r in results:
            assert "irs.gov" in r.retrieval_metadata.currency_warning.lower()

    def test_guidance_summary_does_not_assert_automatic_audit_selection(self):
        """No guidance summary should claim an indicator automatically triggers an audit."""
        for topic in ["183 hobby", "charitable", "1099", "audit dif"]:
            results = _match_guidance(topic, None)
            for r in results:
                lower = r.summary.lower()
                # Must not assert automatic audit triggering
                assert "automatically trigger" not in lower or "does not" in lower, (
                    f"Entry '{r.source}' may assert automatic audit: ...{lower[:200]}..."
                )

    def test_guidance_summary_does_not_assert_legal_violation(self):
        """High charitable ratio is a statistical anomaly, not a per-se legal violation."""
        results = _match_guidance("charitable contribution", None)
        for r in results:
            lower = r.summary.lower()
            assert "per-se violation" not in lower or "not a per-se violation" in lower

    def test_dif_entry_says_does_not_implement_dif(self):
        results = _match_guidance("audit dif discriminant", None)
        joined = " ".join(r.summary for r in results).lower()
        assert "does not implement" in joined or "not implement" in joined


class TestCorrected1099SyntheticTrace:
    def _get_trace(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        return generate_synthetic_record("TRACE-TEST-001", 2023, "corrected_1099")

    def test_corrected_1099_trace_key_present(self):
        r = self._get_trace()
        assert "corrected_1099_trace" in r

    def test_trace_pre_reconciliation_shows_false_positive(self):
        r = self._get_trace()
        pre = r["corrected_1099_trace"]["pre_reconciliation"]
        assert pre["apparent_discrepancy"] > 0, "Pre-reconciliation should show a positive gap"
        assert "false positive" in pre["flag_without_reconciliation"].lower()

    def test_trace_post_reconciliation_shows_zero_discrepancy(self):
        r = self._get_trace()
        post = r["corrected_1099_trace"]["post_reconciliation"]
        assert post["discrepancy_after_reconciliation"] == 0.0

    def test_trace_post_reconciliation_no_flags(self):
        r = self._get_trace()
        post = r["corrected_1099_trace"]["post_reconciliation"]
        assert "NO_FLAGS" in post["flag_after_reconciliation"]

    def test_trace_instruction_mentions_reconcile_before_evaluate(self):
        r = self._get_trace()
        instr = r["corrected_1099_trace"]["instruction"].lower()
        assert "reconcile" in instr
        assert "before" in instr

    def test_trace_corrected_amount_plus_others_equals_reported(self):
        """Verify the arithmetic in the trace is internally consistent."""
        r = self._get_trace()
        post = r["corrected_1099_trace"]["post_reconciliation"]
        computed = round(post["corrected_amount_used"] + post["other_records_sum"], 2)
        assert computed == post["reconciled_total"]
        assert round(computed - r["profile"]["reported_1099_income"], 2) == 0.0

    def test_non_corrected_scenario_has_no_trace_key(self):
        from irs_risk.tools.get_synthetic_record import generate_synthetic_record
        r = generate_synthetic_record("SEED-X", 2023, "baseline")
        assert "corrected_1099_trace" not in r
