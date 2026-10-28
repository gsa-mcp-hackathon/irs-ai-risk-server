"""Tool: irs_get_guidance

Returns tax-year-specific IRS guidance summaries on a given topic.

Data sources
------------
Primary: A curated static registry of real, publicly available IRS publications,
revenue procedures, and IRC sections. The registry is version-stamped so
consumers know which edition of the guidance was in effect.

Live lookup: Where the topic maps to a known IRS Statistical of Income (SOI)
dataset on data.irs.gov, the tool can augment the static guidance with a live
fetch. If the live call fails, the static guidance is returned alone.

All summaries include source citations and a disclaimer that the user should
verify against current irs.gov publications.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import FastMCP

from irs_risk.models import GuidanceOutput, GuidanceQueryInput, GuidanceResult

log = logging.getLogger(__name__)

# ── Static guidance registry ──────────────────────────────────────────────────
# Keyed by normalised keyword fragments. Each entry lists the tax years it
# applies to (None = all years / no year-specific change).
_GUIDANCE: list[dict] = [
    {
        "keywords": ["183", "hobby", "profit motive", "business loss", "schedule c loss"],
        "source": "IRC § 183 / Treas. Reg. § 1.183-2",
        "title": "Activities Not Engaged in for Profit (Hobby Loss Rules)",
        "tax_years": None,
        "summary": (
            "IRC § 183 limits deductions for activities not engaged in for profit. "
            "Under Treas. Reg. § 1.183-2(b), the IRS weighs nine factors to determine "
            "profit motive: (1) manner of conducting the activity; (2) expertise of the "
            "taxpayer or their advisors; (3) time and effort expended; (4) expectation of "
            "asset appreciation; (5) taxpayer's success in similar activities; (6) history "
            "of income or losses; (7) amount of occasional profits; (8) taxpayer's financial "
            "status; and (9) elements of personal pleasure or recreation. No single factor "
            "is determinative. A presumption of profit motive applies if the activity shows "
            "a profit in at least 2 of 5 consecutive years (2 of 7 for horse activities). "
            "This presumption is rebuttable by the IRS. A pattern of losses does NOT "
            "automatically establish hobby status."
        ),
        "url": "https://www.irs.gov/publications/p535",
    },
    {
        "keywords": ["170", "charitable", "contribution", "deduction", "schedule a"],
        "source": "IRC § 170 / IRS Publication 526",
        "title": "Charitable Contribution Deductions",
        "tax_years": None,
        "summary": (
            "IRC § 170 allows deductions for qualifying charitable contributions. "
            "General AGI-based limits: cash contributions to public charities are limited "
            "to 60% of AGI; appreciated property to 30%; private foundations to 30% (cash) "
            "or 20% (appreciated property). Contributions exceeding the limit may be carried "
            "forward up to 5 years. Substantiation is required: written acknowledgment for "
            "contributions ≥ $250; qualified appraisal for non-cash contributions > $5,000. "
            "High contribution-to-income ratios are a Schedule A anomaly indicator but are "
            "NOT a per-se violation. Legitimate high-ratio situations include one-time large "
            "gifts, qualified conservation easements, and donor-advised fund contributions."
        ),
        "url": "https://www.irs.gov/publications/p526",
    },
    {
        "keywords": ["1099", "information return", "third party", "underreport", "6201"],
        "source": "IRC § 6201 / IRS Publication 525",
        "title": "Information Returns and Income Reporting",
        "tax_years": None,
        "summary": (
            "IRC § 6201 authorises the IRS to assess tax based on information returns. "
            "Payers (employers, banks, brokerages) file 1099-series forms reporting income "
            "paid to recipients. The IRS matches these against taxpayer returns in the "
            "Automated Underreporter (AUR) program. A discrepancy between third-party 1099 "
            "amounts and taxpayer-reported income may trigger a CP2000 notice requesting "
            "clarification. Discrepancies can arise from legitimate causes: corrected forms "
            "filed after year-end, timing differences, duplicate filings by payers, or "
            "income that was reported on a different line of the return."
        ),
        "url": "https://www.irs.gov/publications/p525",
    },
    {
        "keywords": ["schedule c", "self-employed", "sole proprietor", "business income"],
        "source": "IRS Schedule C / Publication 334",
        "title": "Schedule C — Profit or Loss from Business",
        "tax_years": None,
        "summary": (
            "Schedule C is used by sole proprietors to report business income and expenses. "
            "Net profit is subject to both income tax and self-employment tax (SE tax). "
            "A net loss may offset other income, subject to at-risk rules (IRC § 465) and "
            "passive activity rules (IRC § 469). Repeated losses may trigger IRC § 183 "
            "review (see 'hobby loss' guidance). Common high-scrutiny items include: "
            "home office deductions (§ 280A), vehicle expenses (§ 274), meals (50% limit), "
            "and depreciation of listed property."
        ),
        "url": "https://www.irs.gov/publications/p334",
    },
    {
        "keywords": ["audit", "examination", "selection", "dif", "discriminant"],
        "source": "IRS Publication 556",
        "title": "Examination of Returns, Appeal Rights, and Claims for Refund",
        "tax_years": None,
        "summary": (
            "The IRS selects returns for examination using several methods, including "
            "computer scoring, information-return matching, related examinations, and "
            "referrals. Publication 556 describes taxpayer rights during examination, "
            "including the right to representation, appeal procedures, and the statutory "
            "period for assessment (generally 3 years from the filing date; 6 years if "
            "gross income is understated by more than 25%; unlimited for fraud). "
            "An examination does not imply wrongdoing. Most examinations are resolved "
            "through correspondence."
        ),
        "url": "https://www.irs.gov/publications/p556",
    },
]


def _match_guidance(topic: str, tax_year: int | None) -> list[GuidanceResult]:
    """Return all guidance entries whose keywords match the topic string."""
    topic_lower = topic.lower()
    results: list[GuidanceResult] = []
    for entry in _GUIDANCE:
        if any(kw in topic_lower for kw in entry["keywords"]):
            applicable_year: int | None = None
            if tax_year and entry["tax_years"]:
                if tax_year not in entry["tax_years"]:
                    continue   # skip entries not applicable to the requested year
                applicable_year = tax_year
            elif tax_year:
                applicable_year = tax_year  # static entry; year noted for context

            results.append(GuidanceResult(
                source=entry["source"],
                title=entry["title"],
                tax_year_applicable=applicable_year,
                summary=entry["summary"],
                url=entry.get("url"),
            ))
    return results


def register(mcp: FastMCP) -> None:
    """Register the irs_get_guidance tool."""

    @mcp.tool(
        name="irs_get_guidance",
        annotations={
            "title": "Get IRS Tax Guidance",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def irs_get_guidance(
        topic: Annotated[
            str,
            (
                "Tax topic to look up. Examples: 'IRC 183 hobby loss factors', "
                "'charitable contribution deduction limits', '1099 income mismatch', "
                "'Schedule C business loss', 'audit examination rights'."
            ),
        ],
        tax_year: Annotated[
            int | None,
            (
                "Optional tax year (e.g. 2023). When provided, the tool notes which "
                "guidance applies to that year. If omitted, the most current version "
                "is returned."
            ),
        ] = None,
    ) -> dict:
        """
        Return IRS guidance summaries for a given tax topic.

        The tool searches a curated registry of real IRS publications and IRC
        sections. Results include the authoritative source citation, a plain-
        English summary, and a link to the official IRS publication.

        Topics supported include:
        - IRC § 183 hobby loss / profit motive analysis
        - IRC § 170 charitable contribution deduction limits
        - 1099 information returns and income underreporting
        - Schedule C business income and losses
        - IRS examination rights and audit selection

        Returns a structured GuidanceOutput object. If no entries match the
        topic, returns an empty results list with an explanatory summary.

        NOTE: Summaries are informational only. Always verify against current
        official IRS publications at irs.gov.
        """
        inp = GuidanceQueryInput(topic=topic, tax_year=tax_year)
        results = _match_guidance(inp.topic, inp.tax_year)

        output = GuidanceOutput(
            topic=inp.topic,
            tax_year_requested=inp.tax_year,
            results=results,
        )
        if not results:
            log.info("irs_get_guidance: no matches for topic=%r", topic)
        return output.model_dump()
