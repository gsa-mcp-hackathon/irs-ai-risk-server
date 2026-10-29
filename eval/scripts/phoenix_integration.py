"""
eval/scripts/phoenix_integration.py
=====================================
Arize Phoenix integration stubs for the IRS TaxRisk evaluation framework.

STATUS: NOT ACTIVATED
---------------------
arize-phoenix (v12.15.1 available on PyPI) is NOT pre-installed in this
IBM watsonx Orchestrate environment. Activating it requires:

1. Install into the project venv:
       source .venv/bin/activate
       pip install arize-phoenix

2. Start the Phoenix server (separate terminal, must remain running):
       python -m phoenix.server.main serve
   → Dashboard will be accessible at http://localhost:6006

3. Set the collector endpoint in your shell:
       export PHOENIX_COLLECTOR_ENDPOINT="http://localhost:6006/v1/traces"

4. In eval/config/eval_config.yaml, set:
       phoenix:
         enabled: true

5. Then import this module in harness.py:
       from eval.scripts.phoenix_integration import setup_phoenix, record_span

WHAT PHOENIX WOULD PROVIDE
---------------------------
- Persistent trace storage for every tool call and LLM inference
- Latency histograms and percentile charts
- Side-by-side comparison of Condition A vs Condition B traces
- Exportable evaluation datasets for offline analysis

LIMITATIONS IN THIS ENVIRONMENT
---------------------------------
- Phoenix requires a long-running server process; not suitable for
  serverless or ephemeral CI environments without a sidecar.
- IBM watsonx Orchestrate does not natively export OTel traces to
  Phoenix. You would need to instrument the agent client separately.
- The IBM ADK telemetry-analyzer skill (available) can parse OTel traces
  exported from the local orchestrate server — consider this as an
  alternative to Phoenix for IBM-native telemetry.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("eval.phoenix")

_PHOENIX_ENABLED = False


def setup_phoenix() -> bool:
    """
    Attempt to initialise Arize Phoenix tracing.

    Returns True if setup succeeded, False otherwise.
    Failure is always non-fatal — evaluation continues without Phoenix.
    """
    if not _PHOENIX_ENABLED:
        log.info(
            "Phoenix integration is disabled. Set phoenix.enabled: true "
            "in eval/config/eval_config.yaml and ensure arize-phoenix "
            "is installed to activate."
        )
        return False

    try:
        import phoenix as px  # type: ignore[import]
        from openinference.instrumentation import TraceConfig  # type: ignore[import]

        endpoint = os.environ.get(
            "PHOENIX_COLLECTOR_ENDPOINT",
            "http://localhost:6006/v1/traces",
        )
        px.launch_app()
        log.info("Arize Phoenix UI started. Traces will be sent to %s", endpoint)
        return True
    except ImportError:
        log.warning(
            "arize-phoenix is not installed. "
            "Run: pip install arize-phoenix\n"
            "See eval/scripts/phoenix_integration.py for full setup instructions."
        )
        return False
    except Exception as exc:
        log.warning("Phoenix setup failed: %s", exc)
        return False


def record_span(
    case_id: str,
    tool_name: str,
    inputs: dict,
    outputs: dict,
    latency_sec: float,
    passed: bool,
) -> None:
    """
    Record a single tool-call span in Phoenix (no-op when not enabled).

    Parameters
    ----------
    case_id     : Test case ID (e.g. 'TC-01')
    tool_name   : MCP tool name called
    inputs      : Tool input parameters
    outputs     : Tool output (or empty dict on error)
    latency_sec : Wall-clock call duration in seconds
    passed      : Whether all assertions passed
    """
    if not _PHOENIX_ENABLED:
        return

    try:
        from opentelemetry import trace  # type: ignore[import]

        tracer = trace.get_tracer("irs-taxrisk-eval")
        with tracer.start_as_current_span(f"eval.{case_id}.{tool_name}") as span:
            span.set_attribute("eval.case_id", case_id)
            span.set_attribute("eval.tool", tool_name)
            span.set_attribute("eval.latency_sec", latency_sec)
            span.set_attribute("eval.passed", passed)
    except Exception as exc:
        log.debug("Phoenix span recording failed (non-fatal): %s", exc)
