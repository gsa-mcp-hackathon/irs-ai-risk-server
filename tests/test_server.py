"""Smoke tests: server import and tool registration."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from irs_risk.app import mcp
from irs_risk.config import settings
from irs_risk.tools import register_tools
from irs_risk.prompts import register_prompts
from irs_risk.resources import register_resources


class TestServerImport:
    def test_mcp_instance_is_importable(self):
        assert mcp is not None

    def test_server_name(self):
        assert mcp.name == "IRS AI Risk Core"

    def test_default_transport_is_stdio(self):
        """Guard against accidentally shipping with a non-stdio default."""
        assert settings.mcp_transport == "stdio"


class TestRegistration:
    def test_tools_register_without_error(self):
        register_tools(FastMCP("test-tools"))

    def test_prompts_register_without_error(self):
        register_prompts(FastMCP("test-prompts"))

    def test_resources_register_without_error(self):
        register_resources(FastMCP("test-resources"))


class TestToolDiscoverability:
    @pytest.mark.asyncio
    async def test_all_five_tools_discoverable(self):
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        expected = {
            "irs_evaluate_tax_profile",
            "irs_reconcile_income",
            "irs_get_guidance",
            "irs_get_synthetic_record",
            "irs_generate_briefing",
        }
        assert expected <= names, f"Missing tools: {expected - names}"

    @pytest.mark.asyncio
    async def test_evaluate_profile_tool_has_annotations(self):
        tools = await mcp.list_tools()
        tool = next(t for t in tools if t.name == "irs_evaluate_tax_profile")
        # Tool should have a description (docstring)
        assert tool.description is not None and len(tool.description) > 10

    @pytest.mark.asyncio
    async def test_evaluate_profile_schema_has_all_parameters(self):
        tools = await mcp.list_tools()
        tool = next(t for t in tools if t.name == "irs_evaluate_tax_profile")
        # FastMCP 4.x exposes the parameter schema via tool.parameters
        schema = tool.parameters if hasattr(tool, "parameters") else {}
        param_names = set(schema.get("properties", {}).keys())
        required_params = {
            "case_id",
            "tax_year",
            "gross_income",
            "reported_1099_income",
            "third_party_1099_total",
            "charitable_contributions",
            "business_loss_years_in_window",
        }
        assert required_params <= param_names, (
            f"Missing parameters in schema: {required_params - param_names}"
        )
