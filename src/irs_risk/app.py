"""IRS AI Risk MCP Server — thin entry point.

Keeps this file minimal:
  1. Create the FastMCP instance.
  2. Register tools / prompts / resources / routes from submodules.
  3. Decide which transport to run (stdio locally, HTTP when deployed).

All real logic lives in:
  tools/       one file per tool
  prompts/     reusable conversation starters
  resources/   static reference data
  engine.py    versioned risk-scoring pure function
  reconcile.py income-reconciliation pure function
  models.py    Pydantic input/output models
  config.py    settings from env vars / .env
  utils.py     shared HTTP helpers
"""

from __future__ import annotations

import logging
import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from irs_risk import __version__
from irs_risk.config import settings
from irs_risk.prompts import register_prompts
from irs_risk.resources import register_resources
from irs_risk.tools import register_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# ── Server ────────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="IRS AI Risk Core",
    instructions=(
        "IRS AI Risk Scoring MCP server — GSA hackathon prototype. "
        "Provides hypothetical tax-profile risk scoring, income reconciliation, "
        "IRS guidance lookup, synthetic record generation, and analyst briefing. "
        "DISCLAIMER: Risk scores do not implement the actual IRS DIF methodology. "
        "No legal conclusions should be drawn from any output."
    ),
)

# Wire up all submodules
register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)


# ── HTTP-only routes ──────────────────────────────────────────────────────────

@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Health check used by cloud platforms (Code Engine, cloud.gov)."""
    return JSONResponse({
        "status": "healthy",
        "service": "irs-ai-risk-server",
        "version": __version__,
    })


@mcp.custom_route("/version", methods=["GET"])
async def version(request: Request) -> JSONResponse:
    return JSONResponse({"version": __version__})


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """
    Start the server, selecting transport based on the environment.

    Precedence:
      1. Platform-injected PORT (IBM Code Engine, cloud.gov, Databricks)
         → HTTP on that port.
      2. MCP_TRANSPORT=streamable-http in the environment
         → HTTP on MCP_HOST:MCP_PORT.
      3. Otherwise → stdio (local clients: Bob, Claude Desktop, Claude Code).
    """
    platform_port = os.getenv("PORT") or os.getenv("DATABRICKS_APP_PORT")

    if platform_port:
        log.info("Platform port detected (%s) — starting HTTP transport.", platform_port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        log.info(
            "MCP_TRANSPORT=streamable-http — starting on %s:%d.",
            settings.mcp_host, settings.mcp_port,
        )
        mcp.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    else:
        log.info("Starting stdio transport (local mode).")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
