"""Tool registry — aggregates all tool modules."""

from __future__ import annotations

from fastmcp import FastMCP

from irs_risk.tools import (
    evaluate_profile,
    generate_briefing,
    get_irs_guidance,
    get_synthetic_record,
    reconcile_income,
)


def register_tools(mcp: FastMCP) -> None:
    """Register all IRS risk tools with the MCP server."""
    evaluate_profile.register(mcp)
    reconcile_income.register(mcp)
    get_irs_guidance.register(mcp)
    get_synthetic_record.register(mcp)
    generate_briefing.register(mcp)
