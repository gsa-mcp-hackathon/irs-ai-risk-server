"""Tool: irs_get_synthetic_record

Generates deterministic synthetic taxpayer records for testing and
demonstration purposes. Records contain traceable source IDs so every
generated value can be reproduced and audited.

NO real taxpayer data is used. All values are algorithmically generated
from the seed_id. The seed always produces the same record.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastmcp import FastMCP

log = logging.getLogger(__name__)

# ── Scenario definitions ──────────────────────────────────────────────────────
# Each scenario specifies the pattern of risk indicators to embed.
# Values are expressed as multipliers / absolute counts applied on top of a
# seed-derived base income.

_SCENARIOS: dict[str, dict] = {
    "baseline": {
        "description": "Moderate income, no anomalies.",
        "income_multiplier": 1.0,
        "third_party_ratio": 1.0,     # 3P exactly matches reported
        "charitable_ratio": 0.05,     # 5% of gross — well under threshold
        "loss_years_in_window": 1,
    },
    "income_mismatch": {
        "description": "Third-party 1099 total exceeds self-reported by ~15%.",
        "income_multiplier": 1.0,
        "third_party_ratio": 1.15,    # 15% gap
        "charitable_ratio": 0.04,
        "loss_years_in_window": 0,
    },
    "outlier_deductions": {
        "description": "Charitable contributions at ~35% of gross income.",
        "income_multiplier": 1.0,
        "third_party_ratio": 1.0,
        "charitable_ratio": 0.35,     # above 20% threshold
        "loss_years_in_window": 0,
    },
    "business_loss_pattern": {
        "description": "4 of last 5 years show a net Schedule C loss.",
        "income_multiplier": 1.0,
        "third_party_ratio": 1.0,
        "charitable_ratio": 0.04,
        "loss_years_in_window": 4,    # >= threshold of 4
    },
    "multi_flag": {
        "description": "Income mismatch + outlier deductions + loss pattern.",
        "income_multiplier": 1.0,
        "third_party_ratio": 1.20,
        "charitable_ratio": 0.30,
        "loss_years_in_window": 4,
    },
    "clean": {
        "description": "All indicators within normal ranges. Expected score: 0.",
        "income_multiplier": 1.2,
        "third_party_ratio": 0.98,    # slightly below reported — no flag
        "charitable_ratio": 0.03,
        "loss_years_in_window": 0,
    },
    "corrected_1099": {
        "description": (
            "One original 1099 record is superseded by a corrected form with a lower amount. "
            "Before reconciliation the raw third-party total appears to exceed reported income "
            "(false-positive mismatch). After reconciliation the corrected total matches and "
            "no INCOME_MISMATCH flag should fire. Demonstrates that scoring must use the "
            "reconciled total, not the pre-reconciliation sum."
        ),
        "income_multiplier": 1.0,
        "third_party_ratio": 1.0,     # post-reconciliation: no mismatch
        "charitable_ratio": 0.04,
        "loss_years_in_window": 0,
    },
}

_DEFAULT_SCENARIO = "baseline"


def _seed_to_base_income(seed_id: str) -> float:
    """Deterministically derive a base gross income from the seed string."""
    digest = int(hashlib.sha256(seed_id.encode()).hexdigest(), 16)
    # Map to a realistic income range: $30,000 – $330,000
    return 30_000.0 + (digest % 300_000)


def generate_synthetic_record(seed_id: str, tax_year: int, scenario: str) -> dict:
    """
    Generate a deterministic synthetic taxpayer record.

    Returns a dict that can be passed directly to irs_evaluate_tax_profile
    and irs_reconcile_income. The record is fully traceable via seed_id.
    """
    scenario_key = scenario if scenario in _SCENARIOS else _DEFAULT_SCENARIO
    config = _SCENARIOS[scenario_key]

    gross = round(_seed_to_base_income(seed_id), 2)
    reported_1099 = round(gross * 0.60, 2)   # 60% of income comes from 1099 payers
    third_party = round(reported_1099 * config["third_party_ratio"], 2)
    charitable = round(gross * config["charitable_ratio"], 2)
    loss_years = config["loss_years_in_window"]

    # Generate three synthetic 1099 sub-records with traceable IDs.
    # For the corrected_1099 scenario the first record is an original that is
    # superseded by a corrected form with a lower amount, so the raw sum of
    # all records exceeds the reported total (false-positive before reconciliation)
    # but the reconciled total equals the reported total.
    payer_base = int(hashlib.md5(seed_id.encode()).hexdigest(), 16) % 900000 + 100000
    records_1099 = []

    if scenario_key == "corrected_1099":
        # Original record (inflated — will be voided by the correction)
        original_amount = round(reported_1099 * 0.60, 2)
        corrected_amount = round(reported_1099 * 0.50, 2)   # lower corrected amount
        records_1099 = [
            {
                "record_id": f"{seed_id}-1099-01-ORIG",
                "payer_name": f"Synthetic Payer {payer_base}",
                "amount": original_amount,
                "form_type": "1099-NEC",
                "tax_year": tax_year,
                "status": "original",
                "corrects_record_id": None,
            },
            {
                # Corrected form — supersedes the original; amount is lower
                "record_id": f"{seed_id}-1099-01-CORR",
                "payer_name": f"Synthetic Payer {payer_base}",
                "amount": corrected_amount,
                "form_type": "1099-NEC",
                "tax_year": tax_year,
                "status": "corrected",
                "corrects_record_id": f"{seed_id}-1099-01-ORIG",
            },
            {
                "record_id": f"{seed_id}-1099-02",
                "payer_name": f"Synthetic Payer {payer_base + 1}",
                "amount": round(reported_1099 * 0.30, 2),
                "form_type": "1099-MISC",
                "tax_year": tax_year,
                "status": "original",
                "corrects_record_id": None,
            },
            {
                "record_id": f"{seed_id}-1099-03",
                "payer_name": f"Synthetic Payer {payer_base + 2}",
                "amount": round(reported_1099 * 0.20, 2),
                "form_type": "1099-MISC",
                "tax_year": tax_year,
                "status": "original",
                "corrects_record_id": None,
            },
        ]
        # The raw (pre-reconciliation) third_party total includes the original amount —
        # a false-positive mismatch. The reconciled total uses the corrected amount.
        # corrected_amount + 0.30 + 0.20 = 1.00 × reported_1099 → no discrepancy
        third_party = round(original_amount + reported_1099 * 0.30 + reported_1099 * 0.20, 2)
    else:
        splits = [0.50, 0.30, 0.20]
        for i, split in enumerate(splits):
            records_1099.append({
                "record_id": f"{seed_id}-1099-{i+1:02d}",
                "payer_name": f"Synthetic Payer {payer_base + i}",
                "amount": round(reported_1099 * split, 2),
                "form_type": "1099-NEC" if i == 0 else "1099-MISC",
                "tax_year": tax_year,
                "status": "original",
                "corrects_record_id": None,
            })

    log.info(
        "synthetic record generated seed=%s year=%d scenario=%s gross=%.2f",
        seed_id, tax_year, scenario_key, gross,
    )

    result: dict = {
        "source_id": seed_id,
        "tax_year": tax_year,
        "scenario": scenario_key,
        "scenario_description": config["description"],
        "profile": {
            "case_id": f"SYNTH-{seed_id}",
            "tax_year": tax_year,
            "gross_income": gross,
            "reported_1099_income": reported_1099,
            "third_party_1099_total": third_party,
            "charitable_contributions": charitable,
            "business_loss_years_in_window": loss_years,
        },
        "records_1099": records_1099,
        "note": (
            "SYNTHETIC DATA — generated algorithmically for testing and "
            "demonstration only. Not derived from any real taxpayer information."
        ),
    }

    # For the corrected_1099 scenario, include an explicit before/after arithmetic
    # trace so callers can see exactly why pre-reconciliation scoring is misleading.
    if scenario_key == "corrected_1099":
        orig_rec = next(r for r in records_1099 if r["record_id"].endswith("-ORIG"))
        corr_rec = next(r for r in records_1099 if r["record_id"].endswith("-CORR"))
        other_recs = [r for r in records_1099 if r not in (orig_rec, corr_rec)]
        other_sum = round(sum(r["amount"] for r in other_recs), 2)

        result["corrected_1099_trace"] = {
            "description": (
                "This trace shows why the raw (pre-reconciliation) third_party_1099_total "
                "in profile would trigger a false-positive INCOME_MISMATCH flag. "
                "After reconciliation the corrected amount replaces the original and "
                "the discrepancy disappears. Scoring MUST use the reconciled total."
            ),
            "pre_reconciliation": {
                "note": (
                    "If scored directly from profile.third_party_1099_total without "
                    "first reconciling, the engine sees a mismatch and sets INCOME_MISMATCH."
                ),
                "original_record": {
                    "record_id": orig_rec["record_id"],
                    "amount": orig_rec["amount"],
                    "status": "original (will be voided by corrected form)",
                },
                "corrected_record": {
                    "record_id": corr_rec["record_id"],
                    "amount": corr_rec["amount"],
                    "status": "corrected (supersedes original)",
                    "corrects_record_id": corr_rec["corrects_record_id"],
                },
                "raw_third_party_total": third_party,
                "reported_1099_income": reported_1099,
                "apparent_discrepancy": round(third_party - reported_1099, 2),
                "flag_without_reconciliation": "INCOME_MISMATCH (false positive)",
            },
            "post_reconciliation": {
                "note": (
                    "After running irs_reconcile_income, the original is voided. "
                    "The reconciled total uses the corrected amount only."
                ),
                "voided_original_amount": orig_rec["amount"],
                "corrected_amount_used": corr_rec["amount"],
                "other_records_sum": other_sum,
                "reconciled_total": round(corr_rec["amount"] + other_sum, 2),
                "reported_1099_income": reported_1099,
                "discrepancy_after_reconciliation": round(
                    corr_rec["amount"] + other_sum - reported_1099, 2
                ),
                "flag_after_reconciliation": "NO_FLAGS (mismatch resolved)",
            },
            "instruction": (
                "Always call irs_reconcile_income before irs_evaluate_tax_profile "
                "when corrected or duplicate 1099 records may be present. Pass "
                "reconciled_total (not the raw third_party_1099_total from profile) "
                "as the third_party_1099_total input to irs_evaluate_tax_profile."
            ),
        }

    return result


def register(mcp: FastMCP) -> None:
    """Register the irs_get_synthetic_record tool."""

    @mcp.tool(
        name="irs_get_synthetic_record",
        annotations={
            "title": "Get Synthetic Taxpayer Record",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def irs_get_synthetic_record(
        seed_id: Annotated[
            str,
            (
                "Deterministic seed string. The same seed always produces the same "
                "record. Suggested format: 'SYNTH-<scenario>-<number>', "
                "e.g. 'SYNTH-HIGH-001'. The scenario name in the seed is for "
                "human readability only; use the 'scenario' parameter to control "
                "which risk pattern is embedded."
            ),
        ],
        tax_year: Annotated[int, "Tax year for the record, e.g. 2023."] = 2023,
        scenario: Annotated[
            str,
            (
                "Risk scenario to embed. One of: "
                "'baseline' (no anomalies), "
                "'income_mismatch' (3P > reported by ~15%), "
                "'outlier_deductions' (charitable ~35% of gross), "
                "'business_loss_pattern' (4 of 5 loss years), "
                "'multi_flag' (all three flags), "
                "'clean' (all indicators within normal ranges), "
                "'corrected_1099' (one original superseded by corrected form; "
                "includes corrected_1099_trace showing pre/post reconciliation). "
                "Invalid values fall back to 'baseline'."
            ),
        ] = "baseline",
    ) -> dict:
        """
        Generate a deterministic synthetic taxpayer record for testing.

        The record is derived exclusively from the seed_id — no real taxpayer
        data is used. The same seed always produces the same values, making
        it suitable for reproducible test cases and demo scenarios.

        Returns a dict containing:
        - profile: inputs ready to pass to irs_evaluate_tax_profile
        - records_1099: a list of synthetic Form 1099 records ready for
          irs_reconcile_income
        - scenario metadata and a SYNTHETIC DATA disclaimer
        """
        return generate_synthetic_record(seed_id, tax_year, scenario)
