"""Versioned risk-scoring engine — pure functions, no I/O.

DISCLAIMER
----------
All weights, thresholds, and tier boundaries in this module are HYPOTHETICAL
values chosen for demonstration purposes only. They do not represent, implement,
or approximate the actual IRS Discriminant Index Function (DIF) or any other
official IRS audit-selection methodology. No legal conclusions should be drawn
from scores produced by this engine.

Design principles
-----------------
- Pure functions: no side effects, no I/O, deterministic output for any input.
- Versioned: every output embeds the engine version so downstream records remain
  traceable even after the weights change.
- Non-determinative flags: no single indicator is treated as automatically
  establishing a legal conclusion. Flags are statistical signals that warrant
  further review, not findings.
- Corrected IRC § 183 interpretation: consecutive business losses are ONE of
  nine factors the IRS weighs under Treas. Reg. § 1.183-2(b). They do not
  automatically reclassify an activity as a hobby. The engine flags the
  *pattern* for human review of all nine factors.
"""

from __future__ import annotations

import logging

from irs_risk.models import (
    FlagCode,
    RiskFlag,
    RiskScoreOutput,
    RiskTier,
    TaxProfileInput,
)

log = logging.getLogger(__name__)

# ── Engine version ─────────────────────────────────────────────────────────────
# Bump the version string whenever weights, thresholds, or flag logic change.
# Consumers should store this alongside every persisted score.
ENGINE_VERSION = "hypothetical-v1"

# ── Hypothetical weights ───────────────────────────────────────────────────────
# These are invented for demonstration. They are NOT IRS DIF weights.
_W_INCOME_MISMATCH       = 40
_W_OUTLIER_DEDUCTIONS    = 30
_W_BUSINESS_LOSS_PATTERN = 20   # reduced from 30; reflects non-determinative nature

# ── Thresholds ─────────────────────────────────────────────────────────────────
# Charitable-contribution-to-gross-income ratio that triggers the deduction flag.
# Based on broad public statistical patterns; not an IRS-published threshold.
_CHARITABLE_RATIO_THRESHOLD = 0.20

# Number of loss years within the 5-year window that triggers the loss-pattern
# flag. IRC § 183 safe-harbor looks at profit in 2 of 5 years; we flag when
# fewer than 2 profitable years are implied (i.e. ≥ 4 loss years in window).
# This is deliberately conservative — the flag signals "warrants 9-factor review",
# not "this is a hobby".
_LOSS_YEARS_IN_WINDOW_THRESHOLD = 4

# ── Tier boundaries ────────────────────────────────────────────────────────────
_TIER_HIGH_MIN   = 70
_TIER_MEDIUM_MIN = 40


def _tier_from_score(score: int) -> RiskTier:
    if score >= _TIER_HIGH_MIN:
        return RiskTier.HIGH
    if score >= _TIER_MEDIUM_MIN:
        return RiskTier.MEDIUM
    return RiskTier.LOW


def compute_risk(profile: TaxProfileInput, engine_version: str = ENGINE_VERSION) -> RiskScoreOutput:
    """
    Score a taxpayer profile and return a structured, versioned result.

    Parameters
    ----------
    profile        : Validated TaxProfileInput from the caller.
    engine_version : Version tag to embed in the output (default: ENGINE_VERSION).

    Returns
    -------
    RiskScoreOutput with risk_score, risk_tier, flags, and engine_version.

    Notes
    -----
    - All weights are hypothetical. See module docstring.
    - IRC § 183 interpretation: business_loss_years_in_window is treated as
      ONE statistical indicator that warrants human review of all nine factors
      in Treas. Reg. § 1.183-2(b). It does NOT automatically establish hobby status.
    - Charitable contributions above the threshold are flagged as a statistical
      anomaly for Schedule A review, NOT as a legal violation of IRC § 170.
    """
    score = 0
    flags: list[RiskFlag] = []

    # ── Flag 1: Income Mismatch ──────────────────────────────────────────────
    # Third-party 1099 filings exceed taxpayer self-reported 1099 income.
    # Potential indicator of underreported income; requires document matching
    # to rule out timing differences, corrected forms, or employer errors.
    if profile.third_party_1099_total > profile.reported_1099_income:
        delta = profile.third_party_1099_total - profile.reported_1099_income
        score += _W_INCOME_MISMATCH
        log.debug(
            "case=%s year=%d INCOME_MISMATCH delta=%.2f",
            profile.case_id, profile.tax_year, delta,
        )
        flags.append(RiskFlag(
            code=FlagCode.INCOME_MISMATCH,
            weight_applied=_W_INCOME_MISMATCH,
            detail=(
                f"Third-party 1099 filings (${profile.third_party_1099_total:,.2f}) "
                f"exceed taxpayer-reported 1099 income (${profile.reported_1099_income:,.2f}) "
                f"by ${delta:,.2f}. Warrants document-matching review to determine whether "
                f"the gap reflects unreported income, timing differences, or corrected forms."
            ),
        ))

    # ── Flag 2: Outlier Deductions ───────────────────────────────────────────
    # Charitable contributions are statistically high relative to gross income.
    # This is a Schedule A anomaly indicator, NOT a determination of IRC § 170
    # non-compliance. High ratios occur legitimately (e.g. a one-time large gift,
    # qualified conservation easements, donor-advised fund contributions).
    if profile.gross_income > 0:
        ratio = profile.charitable_contributions / profile.gross_income
        if ratio > _CHARITABLE_RATIO_THRESHOLD:
            score += _W_OUTLIER_DEDUCTIONS
            log.debug(
                "case=%s year=%d OUTLIER_DEDUCTIONS ratio=%.3f",
                profile.case_id, profile.tax_year, ratio,
            )
            flags.append(RiskFlag(
                code=FlagCode.OUTLIER_DEDUCTIONS,
                weight_applied=_W_OUTLIER_DEDUCTIONS,
                detail=(
                    f"Charitable contributions (${profile.charitable_contributions:,.2f}) "
                    f"represent {ratio:.1%} of gross income (${profile.gross_income:,.2f}), "
                    f"exceeding the {_CHARITABLE_RATIO_THRESHOLD:.0%} statistical reference "
                    f"threshold. This is a Schedule A anomaly indicator. High ratios can arise "
                    f"legitimately (e.g. one-time large gifts, conservation easements). "
                    f"Documentation review is warranted."
                ),
            ))

    # ── Flag 3: Business Loss Pattern ────────────────────────────────────────
    # Multiple loss years within the 5-year window are ONE of nine factors the
    # IRS considers under Treas. Reg. § 1.183-2(b) when evaluating whether an
    # activity has a genuine profit motive (IRC § 183). The other eight factors
    # (manner of operation, expertise, time/effort, asset appreciation, prior
    # success, history of income/losses, occasional profits, financial status,
    # and elements of personal pleasure) must be weighed together. A pattern of
    # losses does NOT automatically establish hobby status.
    if profile.business_loss_years_in_window >= _LOSS_YEARS_IN_WINDOW_THRESHOLD:
        score += _W_BUSINESS_LOSS_PATTERN
        log.debug(
            "case=%s year=%d BUSINESS_LOSS_PATTERN loss_years=%d",
            profile.case_id, profile.tax_year, profile.business_loss_years_in_window,
        )
        flags.append(RiskFlag(
            code=FlagCode.BUSINESS_LOSS_PATTERN,
            weight_applied=_W_BUSINESS_LOSS_PATTERN,
            detail=(
                f"{profile.business_loss_years_in_window} of the last 5 years show a net "
                f"Schedule C/F business loss. Under IRC § 183, the IRS weighs this as ONE "
                f"of nine factors (Treas. Reg. § 1.183-2(b)) when evaluating profit motive. "
                f"A full nine-factor analysis by an examiner is recommended before drawing "
                f"any conclusion about hobby classification. A loss pattern alone is NOT "
                f"determinative of hobby status."
            ),
        ))

    # ── Clamp, tier, and no-flag case ────────────────────────────────────────
    score = min(score, 100)

    if not flags:
        flags.append(RiskFlag(
            code=FlagCode.NO_FLAGS,
            weight_applied=0,
            detail=(
                "No statistical anomalies detected across income reporting, "
                "deduction ratios, or business loss patterns. Profile appears "
                "within reference ranges for these three indicators."
            ),
        ))

    log.info(
        "case=%s year=%d score=%d tier=%s engine=%s",
        profile.case_id, profile.tax_year, score,
        _tier_from_score(score).value, engine_version,
    )

    return RiskScoreOutput(
        case_id=profile.case_id,
        tax_year=profile.tax_year,
        engine_version=engine_version,
        risk_score=score,
        risk_tier=_tier_from_score(score),
        flags=flags,
    )
