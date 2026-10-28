#!/usr/bin/env python
"""Local MCP toolkit entrypoint for watsonx Orchestrate (stdio transport).

watsonx Orchestrate runs a LOCAL MCP toolkit by executing this script with
`python server.py` inside its own runtime, communicating over stdio.

The register script stages this file NEXT TO the `irs_risk` package
(flattened out of the repo's src/ layout), so `irs_risk` is importable
directly from this script's directory. We add that directory to sys.path
defensively in case Orchestrate changes CWD.
"""

import os
import sys

# Ensure the directory containing this file (which also contains the
# `irs_risk` package after staging) is on sys.path regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from irs_risk.app import mcp  # noqa: E402

if __name__ == "__main__":
    # stdio is the transport watsonx Orchestrate uses for local MCP toolkits.
    mcp.run(transport="stdio")
