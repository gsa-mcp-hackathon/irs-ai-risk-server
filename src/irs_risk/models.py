"""Pydantic models for tool inputs, outputs, and shared types.

Typed parameters give MCP clients (and watsonx Orchestrate) a precise JSON
schema, which the LLM uses to call tools correctly. All monetary values are in
USD. All years are calendar years (not fiscal years).

DISCLAIMER: Risk weights, thresholds, and tiers in this module are
HYPOTHETICAL values used for demonstration purposes only. They do not represent
or implement the actual IRS Discriminant Index Function (DIF) or any other
official IRS audit selection methodology.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class RiskTier(str, Enum):
    LOW    = "Low"
    MEDIUM = "Medium"
    HIGH   = "High"


class RecordStatus(str, Enum):
    """Status of an individual 1099 record after reconciliation."""
    ORIGINAL   = "original"
    CORRECTED  = "corrected"    # superseded by a correction filing
    DUPLICATE  = "duplicate"    # exact duplicate of another record
    MISSING    = "missing"      # referenced in cross-check but absent from set


class FlagCode(str, Enum):
    """Standardised flag identifiers emitted by the risk engine."""
    INCOME_MISMATCH        = "INCOME_MISMATCH"
    OUTLIER_DEDUCTIONS     = "OUTLIER_DEDUCTIONS"
    BUSINESS_LOSS_PATTERN  = "BUSINESS_LOSS_PATTERN"   # renamed from HOBBY_LOSS_RISK
    NO_FLAGS               = "NO_FLAGS"


# ── Shared value types ────────────────────────────────────────────────────────

PositiveDollars = Annotated[float, Field(ge=0.0, description="USD amount ≥ 0.")]
TaxYear = Annotated[
    int,
    Field(ge=1990, le=2030, description="Calendar tax year, e.g. 2023."),
]


# ── Tool input models ─────────────────────────────────────────────────────────

class TaxProfileInput(BaseModel):
    """
    Financial profile of a single taxpayer for one tax year.

    All monetary values are in US dollars (pre-tax, as reported on the return).
    This input does NOT contain PII; use a case reference ID in `case_id`.
    """

    case_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            description=(
                "Opaque case reference identifier (e.g. 'CASE-2024-0042'). "
                "Must not contain taxpayer PII such as SSN or EIN."
            ),
        ),
    ]
    tax_year: TaxYear
    gross_income: Annotated[
        float,
        Field(
            ge=0.0,
            description="Total gross income reported on the return (line 9, Form 1040).",
        ),
    ]
    reported_1099_income: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "1099 income the taxpayer self-reported on the return. "
                "This is the subset of gross_income attributable to 1099 payers."
            ),
        ),
    ]
    third_party_1099_total: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "Total 1099 income found in third-party information returns "
                "(employer/payer filings). Used for income-mismatch comparison."
            ),
        ),
    ]
    charitable_contributions: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "Total charitable contribution deductions claimed on Schedule A."
            ),
        ),
    ]
    business_loss_years_in_window: Annotated[
        int,
        Field(
            ge=0,
            le=10,
            description=(
                "Number of years with a net Schedule C/F business loss "
                "within the most recent 5-year window. Used as one indicator "
                "in the IRC § 183 nine-factor analysis; not determinative alone."
            ),
        ),
    ]

    @field_validator("reported_1099_income")
    @classmethod
    def reported_1099_must_not_exceed_gross(cls, v: float, info: Any) -> float:
        """Validate that self-reported 1099 income does not exceed gross income.

        Assumption: for this prototype, reported_1099_income is modelled as a
        subset of gross_income (1099 income the taxpayer declared as part of
        their total gross income on Form 1040 line 9).

        Limitation: in practice, a taxpayer with a net operating loss carryover
        or certain negative-income items could have more 1099 income than the
        'gross income' figure on a specific line. If this validation is too
        restrictive for a real-world integration, soften it to a warning flag
        rather than a hard reject, or remove it and document the assumption
        explicitly in the calling system.
        """
        gross = (info.data or {}).get("gross_income")
        if gross is not None and v > gross:
            raise ValueError(
                f"reported_1099_income ({v:,.2f}) cannot exceed "
                f"gross_income ({gross:,.2f})."
            )
        return v


class Form1099Record(BaseModel):
    """A single 1099-series information-return record."""

    record_id: Annotated[
        str,
        Field(description="Unique identifier for this record (e.g. payer EIN + sequence)."),
    ]
    payer_name: Annotated[str, Field(description="Name of the payer/issuer.")]
    amount: Annotated[float, Field(ge=0.0, description="Amount reported on the form (USD).")]
    form_type: Annotated[
        str,
        Field(description="Form type, e.g. '1099-NEC', '1099-MISC', '1099-INT'."),
    ]
    tax_year: TaxYear
    status: RecordStatus = RecordStatus.ORIGINAL
    corrects_record_id: Annotated[
        str | None,
        Field(
            default=None,
            description="record_id of the original this record corrects (if applicable).",
        ),
    ]

    @model_validator(mode="after")
    def corrected_needs_target(self) -> "Form1099Record":
        if self.status == RecordStatus.CORRECTED and not self.corrects_record_id:
            raise ValueError(
                "A CORRECTED record must supply corrects_record_id."
            )
        return self


class ReconcileIncomeInput(BaseModel):
    """Input for the income-reconciliation tool."""

    case_id: Annotated[str, Field(min_length=1, max_length=64, description="Case reference ID.")]
    tax_year: TaxYear
    reported_total: Annotated[
        float,
        Field(ge=0.0, description="Total 1099 income the taxpayer self-reported."),
    ]
    records: Annotated[
        list[Form1099Record],
        Field(
            min_length=1,
            description="List of 1099 records to reconcile. Must contain at least one entry.",
        ),
    ]


class GuidanceQueryInput(BaseModel):
    """Input for the IRS guidance retrieval tool."""

    topic: Annotated[
        str,
        Field(
            min_length=2,
            max_length=120,
            description=(
                "Topic to look up, e.g. 'charitable contribution deduction limits', "
                "'IRC 183 hobby loss factors', 'Schedule C net loss'."
            ),
        ),
    ]
    tax_year: Annotated[
        TaxYear | None,
        Field(
            default=None,
            description=(
                "Tax year for which guidance applies. If omitted, returns the most "
                "current available guidance."
            ),
        ),
    ]


class SyntheticRecordInput(BaseModel):
    """Input for the synthetic taxpayer record generator."""

    seed_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            description=(
                "Deterministic seed identifier. The same seed always produces the "
                "same synthetic record. Format: 'SYNTH-<scenario>-<number>', "
                "e.g. 'SYNTH-HIGH-001'."
            ),
        ),
    ]
    tax_year: TaxYear = 2023
    scenario: Annotated[
        str,
        Field(
            default="baseline",
            description=(
                "Scenario type controlling which risk patterns are embedded. "
                "One of: 'baseline', 'income_mismatch', 'outlier_deductions', "
                "'business_loss_pattern', 'multi_flag', 'clean'."
            ),
        ),
    ]


# ── Tool output models ────────────────────────────────────────────────────────

class RiskFlag(BaseModel):
    """A single risk flag emitted by the scoring engine."""

    code: FlagCode
    weight_applied: Annotated[
        int,
        Field(
            description=(
                "Hypothetical score points applied by this flag. "
                "Does not represent actual IRS scoring weights."
            ),
        ),
    ]
    detail: Annotated[str, Field(description="Human-readable explanation of the flag.")]
    is_determinative: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "False for all flags in this model. No single indicator is "
                "treated as automatically determinative of a legal conclusion."
            ),
        ),
    ]


class RiskScoreOutput(BaseModel):
    """Structured output of the risk-scoring engine."""

    case_id: str
    tax_year: int
    engine_version: Annotated[
        str,
        Field(
            description=(
                "Version tag of the scoring engine that produced this result. "
                "Embed in any downstream record for auditability."
            ),
        ),
    ]
    risk_score: Annotated[
        int,
        Field(
            ge=0,
            le=100,
            description=(
                "Hypothetical composite risk score (0–100). "
                "Higher values indicate more statistical indicators present."
            ),
        ),
    ]
    risk_tier: RiskTier
    flags: list[RiskFlag]
    disclaimer: str = (
        "DISCLAIMER: This score is produced by a HYPOTHETICAL risk model for "
        "demonstration purposes only. It does not represent or implement the "
        "actual IRS Discriminant Index Function (DIF) or any official IRS audit "
        "selection methodology. No legal conclusions should be drawn from it."
    )


class ReconciliationRecord(BaseModel):
    """A single record annotated after reconciliation."""
    record_id: str
    payer_name: str
    amount: float
    form_type: str
    status: RecordStatus
    note: str | None = None
    counted_in_total: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "True if this record's amount was included in reconciled_total. "
                "False for voided originals, duplicates, and missing placeholders."
            ),
        ),
    ]


class ReconciliationArithmeticTrace(BaseModel):
    """
    Step-by-step arithmetic trace of the reconciliation calculation.

    Included in ReconcileIncomeOutput so the caller can verify every cent
    without re-implementing the algorithm. All amounts are exact-decimal
    strings to avoid float representation ambiguity.
    """
    reported_total_str: Annotated[
        str,
        Field(description="Self-reported total as exact decimal string (e.g. '48000.00')."),
    ]
    counted_records: Annotated[
        list[dict],
        Field(
            description=(
                "Records included in the reconciled total. Each entry has "
                "record_id, payer_name, amount_str, and form_type."
            ),
        ),
    ]
    excluded_records: Annotated[
        list[dict],
        Field(
            description=(
                "Records excluded from the reconciled total. Each entry has "
                "record_id, status, and reason."
            ),
        ),
    ]
    reconciled_total_str: Annotated[
        str,
        Field(description="Sum of counted_records as exact decimal string."),
    ]
    discrepancy_str: Annotated[
        str,
        Field(
            description=(
                "reconciled_total minus reported_total as exact decimal string. "
                "Positive = potential underreporting. Negative = over-reporting."
            ),
        ),
    ]
    rounding_note: str = (
        "All monetary arithmetic uses Python Decimal with ROUND_HALF_EVEN "
        "(banker's rounding) to two decimal places. Output floats are "
        "converted from Decimal; the trace strings are the authoritative values."
    )


class ReconcileIncomeOutput(BaseModel):
    """Structured output of the income-reconciliation tool."""

    case_id: str
    tax_year: int
    reported_total: float
    reconciled_total: Annotated[
        float,
        Field(description="Sum of all live (non-voided, non-duplicate) record amounts."),
    ]
    discrepancy: Annotated[
        float,
        Field(description="reconciled_total minus reported_total (positive = underreport)."),
    ]
    records: list[ReconciliationRecord]
    arithmetic_trace: Annotated[
        ReconciliationArithmeticTrace,
        Field(
            description=(
                "Step-by-step arithmetic trace showing which records were counted, "
                "which were excluded, and how the final totals were computed. "
                "Use this to verify the arithmetic independently."
            ),
        ),
    ]
    summary: str


class GuidanceRetrievalMetadata(BaseModel):
    """Provenance and verification metadata for a static guidance entry."""
    retrieval_mode: Annotated[
        str,
        Field(
            default="static/offline",
            description=(
                "How this guidance was obtained. 'static/offline' means it was "
                "compiled into the registry at build time — no live network request "
                "is made when this tool runs."
            ),
        ),
    ]
    registry_edition: Annotated[
        str,
        Field(
            default="hypothetical-v1 / compiled 2025",
            description="Version identifier of the guidance registry this entry belongs to.",
        ),
    ]
    verification_status: Annotated[
        str,
        Field(
            description=(
                "Whether the source title, URL, and summary have been manually checked "
                "against the actual IRS publication."
            ),
        ),
    ]
    checked_date: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "ISO 8601 date (YYYY-MM-DD) when this entry was last verified against "
                "the official IRS source. Null if not recorded."
            ),
        ),
    ]
    currency_warning: str = (
        "This entry has NOT been verified against IRS publications after the "
        "checked_date. Tax-year-specific rule changes after that date are not "
        "reflected. Always verify against current official IRS materials at irs.gov."
    )


class GuidanceResult(BaseModel):
    """A single guidance item returned by the IRS guidance tool."""
    source: str
    title: str
    tax_year_applicable: int | None
    summary: str
    url: str | None = None
    retrieval_metadata: Annotated[
        GuidanceRetrievalMetadata | None,
        Field(
            default=None,
            description=(
                "Provenance and verification metadata. Always present for static "
                "registry entries. Consumers should surface retrieval_mode and "
                "checked_date to end users so they can assess currency."
            ),
        ),
    ]


class GuidanceOutput(BaseModel):
    """Structured output of the IRS guidance retrieval tool."""
    topic: str
    tax_year_requested: int | None
    results: list[GuidanceResult]
    disclaimer: str = (
        "Guidance summaries are for informational purposes only and may not "
        "reflect the most recent IRS publications. Always verify against "
        "current official IRS materials at irs.gov."
    )


class BriefingOutput(BaseModel):
    """Structured analyst briefing combining score, reconciliation, and guidance."""
    case_id: str
    tax_year: int
    generated_at_utc: str
    risk_summary: str
    reconciliation_summary: str
    guidance_notes: list[str]
    recommended_actions: list[str]
    disclaimer: str = (
        "This briefing is generated by an AI prototype for demonstration "
        "purposes only. It is not an official IRS document and must not be "
        "used as the basis for any examination, enforcement, or compliance action."
    )
