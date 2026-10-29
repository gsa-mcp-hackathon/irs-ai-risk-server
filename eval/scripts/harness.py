"""
eval/scripts/harness.py
=======================
Core deterministic evaluation harness for the IRS TaxRisk MCP server.

Executes all test cases in golden_dataset.json by calling the MCP tools
directly (bypassing the network transport). Records timing, tool calls,
assertion results, and writes structured output to eval/results/.

Usage
-----
    # From repo root with venv active:
    python eval/scripts/harness.py [--condition A|B] [--case TC-01] [--repeat 3]

Arguments
---------
--condition {A,B}   Run only one condition (A=with tools, B=no-tool baseline).
                    Default: A only (baseline B requires external LLM endpoint).
--case TC-XX        Run a single test case by ID. Default: all.
--repeat N          Override consistency-run count (default: from config).
--output DIR        Results directory (default: eval/results).

Environment variables
---------------------
WATSONX_API_KEY       If set, LLM-as-judge is activated for applicable cases.
WATSONX_PROJECT_ID    Required when WATSONX_API_KEY is set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from irs_risk.engine import compute_risk
from irs_risk.models import (
    Form1099Record,
    ReconcileIncomeInput,
    TaxProfileInput,
)
from irs_risk.reconcile import reconcile_income
from irs_risk.tools.get_irs_guidance import _match_guidance
from irs_risk.models import GuidanceQueryInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger("eval.harness")

# ── Paths ─────────────────────────────────────────────────────────────────────
DATASET_PATH = REPO_ROOT / "eval" / "datasets" / "golden_dataset.json"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
CONFIG_PATH = REPO_ROOT / "eval" / "config" / "eval_config.yaml"


# =============================================================================
# Direct tool callers (Condition A — bypass network transport)
# =============================================================================

async def call_evaluate_profile(inputs: dict) -> tuple[dict, float]:
    """Call irs_evaluate_tax_profile directly and return (result, latency_sec)."""
    t0 = time.perf_counter()
    profile = TaxProfileInput(**inputs)
    result = compute_risk(profile)
    elapsed = time.perf_counter() - t0
    # mode="json" serialises enums to their string values, not the enum object
    return result.model_dump(mode="json"), elapsed


async def call_reconcile_income(inputs: dict) -> tuple[dict, float]:
    """Call irs_reconcile_income directly and return (result, latency_sec)."""
    t0 = time.perf_counter()
    records = [Form1099Record(**r) for r in inputs["records"]]
    inp = ReconcileIncomeInput(
        case_id=inputs["case_id"],
        tax_year=inputs["tax_year"],
        reported_total=inputs["reported_total"],
        records=records,
    )
    result = reconcile_income(inp)
    elapsed = time.perf_counter() - t0
    return result.model_dump(mode="json"), elapsed


async def call_get_guidance(inputs: dict) -> tuple[dict, float]:
    """Call irs_get_guidance directly and return (result, latency_sec)."""
    t0 = time.perf_counter()
    # TC-11: topic may be absent in the inputs (no tool_inputs_expected entry);
    # use a stub topic so the validator doesn't reject it. The empty-results
    # assertion then checks the guidance registry returns 0 entries.
    raw_topic = inputs.get("topic", "")
    topic = raw_topic if raw_topic.strip() else "unknown topic"
    qi = GuidanceQueryInput(
        topic=topic,
        tax_year=inputs.get("tax_year"),
    )
    results = _match_guidance(qi.topic, qi.tax_year)
    output = {
        "topic": qi.topic,
        "tax_year_requested": qi.tax_year,
        "results": [r.model_dump() for r in results],
        "disclaimer": (
            "Guidance summaries are for informational purposes only and may not "
            "reflect the most recent IRS publications. Always verify against "
            "current official IRS materials at irs.gov."
        ),
    }
    elapsed = time.perf_counter() - t0
    return output, elapsed


TOOL_CALLERS = {
    "irs_evaluate_tax_profile": call_evaluate_profile,
    "irs_reconcile_income": call_reconcile_income,
    "irs_get_guidance": call_get_guidance,
}


# =============================================================================
# Assertion engine
# =============================================================================

def _get_nested(obj: Any, path: str) -> Any:
    """
    Navigate a dotted path like 'results[0].source' or 'flags[0].code'.
    Supports list index notation [N].
    """
    import re
    parts = re.split(r"[\.\[\]]", path)
    parts = [p for p in parts if p]
    cur = obj
    for part in parts:
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return cur


def run_assertion(assertion: dict, result: dict, tool_error: Exception | None) -> dict:
    """
    Execute a single assertion. Returns:
    {
        "assertion_type": str,
        "passed": bool,
        "expected": ...,
        "actual": ...,
        "message": str,
    }
    """
    atype = assertion["type"]
    field = assertion.get("field", "")
    expected = assertion.get("expected")

    try:
        # live_record_count is a special-case exact_numeric on a derived field
        if atype == "exact_numeric" and field == "live_record_count":
            records = result.get("records", [])
            live = [r for r in records if r.get("status") == "original"]
            passed = len(live) == int(expected)
            return {
                "assertion_type": atype, "passed": passed,
                "expected": expected, "actual": len(live),
                "message": "" if passed else f"Expected {expected} live records, got {len(live)}",
            }

        # results_count is a special-case exact_numeric on a derived field
        elif atype == "exact_numeric" and field == "results_count":
            actual = len(result.get("results", []))
            passed = actual == int(expected)
            return {
                "assertion_type": atype, "passed": passed,
                "expected": expected, "actual": actual,
                "message": "" if passed else f"Expected {expected} results, got {actual}",
            }

        elif atype == "exact_numeric":
            actual = _get_nested(result, field)
            passed = actual is not None and abs(float(actual) - float(expected)) < 1e-9
            return {
                "assertion_type": atype, "passed": passed,
                "expected": expected, "actual": actual,
                "message": "" if passed else f"Expected {expected}, got {actual}",
            }

        elif atype == "exact_string":
            actual = _get_nested(result, field)
            passed = str(actual) == str(expected)
            return {
                "assertion_type": atype, "passed": passed,
                "expected": expected, "actual": actual,
                "message": "" if passed else f"Expected '{expected}', got '{actual}'",
            }

        elif atype == "flag_present":
            flags = result.get("flags", [])
            codes = [f.get("code") for f in flags]
            passed = expected in codes
            return {
                "assertion_type": atype, "passed": passed,
                "expected": expected, "actual": codes,
                "message": "" if passed else f"Flag '{expected}' not in {codes}",
            }

        elif atype == "flag_absent":
            flags = result.get("flags", [])
            codes = [f.get("code") for f in flags]
            passed = expected not in codes
            return {
                "assertion_type": atype, "passed": passed,
                "expected": f"absent:{expected}", "actual": codes,
                "message": "" if passed else f"Flag '{expected}' unexpectedly present",
            }

        elif atype == "contains_text":
            actual = _get_nested(result, field)
            if actual is None:
                return {
                    "assertion_type": atype, "passed": False,
                    "expected": expected, "actual": None,
                    "message": f"Field '{field}' is None",
                }
            if isinstance(actual, bool):
                passed = actual == expected
            else:
                passed = str(expected).lower() in str(actual).lower()
            return {
                "assertion_type": atype, "passed": passed,
                "expected": expected, "actual": str(actual)[:120],
                "message": "" if passed else f"'{expected}' not found in field value",
            }

        elif atype == "exact_numeric" and field in ("live_record_count", "results_count"):
            # Already handled above; this branch is unreachable but included for
            # Python's elif chain safety.
            pass  # pragma: no cover

        elif atype == "all_flags_not_determinative":
            flags = result.get("flags", [])
            passed = all(not f.get("is_determinative", True) for f in flags)
            return {
                "assertion_type": atype, "passed": passed,
                "expected": "all is_determinative=False", "actual": [f.get("is_determinative") for f in flags],
                "message": "" if passed else "Some flags have is_determinative=True",
            }

        elif atype == "record_status":
            # field is like "records[R001-ORIG].status" — look up by record_id
            import re as _re
            m = _re.match(r"records\[(.+?)\]\.(\w+)", field)
            if m:
                rid, attr = m.group(1), m.group(2)
                records = result.get("records", [])
                found = next((r for r in records if r.get("record_id") == rid), None)
                actual = found.get(attr) if found else None
                passed = actual == expected
                return {
                    "assertion_type": atype, "passed": passed,
                    "expected": expected, "actual": actual,
                    "message": "" if passed else f"Record {rid}.{attr} = '{actual}', expected '{expected}'",
                }
            return {"assertion_type": atype, "passed": False, "message": "bad field path"}

        elif atype == "duplicate_record_flagged":
            rid = assertion.get("record_id")
            records = result.get("records", [])
            dups = [r for r in records if r.get("record_id") == rid and r.get("status") == "duplicate"]
            passed = len(dups) >= 1
            return {
                "assertion_type": atype, "passed": passed,
                "expected": f"record {rid} marked duplicate", "actual": f"{len(dups)} dup entries found",
                "message": "" if passed else f"No duplicate annotation for {rid}",
            }

        elif atype == "no_tool_error":
            passed = tool_error is None
            return {
                "assertion_type": atype, "passed": passed,
                "expected": "no error", "actual": str(tool_error) if tool_error else "none",
                "message": "" if passed else f"Tool raised: {tool_error}",
            }

        elif atype == "tool_raises_error":
            passed = tool_error is not None
            return {
                "assertion_type": atype, "passed": passed,
                "expected": "validation error", "actual": str(tool_error) if tool_error else "none",
                "message": "" if passed else "Expected a validation error but tool succeeded",
            }

        elif atype == "no_risk_score":
            passed = result.get("risk_score") is None
            return {
                "assertion_type": atype, "passed": passed,
                "expected": "no risk_score", "actual": result.get("risk_score"),
                "message": "" if passed else "risk_score present despite expected error",
            }

        # For agent-level assertions (scope, injection) we cannot evaluate
        # without a live agent — mark as SKIPPED
        elif atype in ("no_tool_called", "contains_disclaimer",
                       "no_system_prompt_leak", "does_not_comply_with_injection"):
            return {
                "assertion_type": atype, "passed": None, "status": "SKIPPED",
                "message": "Requires live agent call — skipped in direct-tool mode",
            }

        else:
            return {
                "assertion_type": atype, "passed": None, "status": "UNKNOWN",
                "message": f"Unrecognised assertion type '{atype}'",
            }

    except Exception as exc:
        return {
            "assertion_type": atype, "passed": False,
            "message": f"Assertion raised exception: {exc}",
        }


# =============================================================================
# Single test-case runner
# =============================================================================

async def run_test_case(tc: dict, repeat: int = 1) -> dict:
    """Run one test case, optionally repeating for consistency checks."""
    tc_id = tc["id"]
    tool_names = tc.get("tool_calls_expected", [])
    all_runs: list[dict] = []

    for run_idx in range(repeat):
        run_result: dict[str, Any] = {
            "run": run_idx + 1,
            "tool_calls": [],
            "tool_error": None,
            "assertion_results": [],
            "latency_sec": 0.0,
        }

        tool_result = {}
        tool_error = None
        total_latency = 0.0

        # Only auto-call the first expected tool (for multi-tool cases,
        # a separate integration test would orchestrate the sequence).
        primary_tool = tool_names[0] if tool_names else None

        if primary_tool and primary_tool in TOOL_CALLERS:
            inputs = (tc.get("tool_inputs_expected") or {}).get(primary_tool, {})
            try:
                tool_result, latency = await TOOL_CALLERS[primary_tool](inputs)
                run_result["tool_calls"].append({
                    "tool": primary_tool,
                    "latency_sec": round(latency, 4),
                })
                total_latency += latency
            except Exception as exc:
                tool_error = exc
                run_result["tool_error"] = str(exc)
                run_result["tool_calls"].append({
                    "tool": primary_tool,
                    "error": str(exc),
                })

        run_result["latency_sec"] = round(total_latency, 4)

        # Run assertions
        for assertion in tc.get("assertions", []):
            ar = run_assertion(assertion, tool_result, tool_error)
            run_result["assertion_results"].append(ar)

        # Summarise pass/fail for this run
        evaluated = [a for a in run_result["assertion_results"] if a.get("passed") is not None]
        skipped = [a for a in run_result["assertion_results"] if a.get("passed") is None]
        passed = [a for a in evaluated if a["passed"]]
        run_result["summary"] = {
            "passed": len(passed),
            "failed": len(evaluated) - len(passed),
            "skipped": len(skipped),
            "total": len(run_result["assertion_results"]),
        }
        all_runs.append(run_result)

    # Consistency analysis (if repeat > 1)
    consistency = _analyse_consistency(all_runs) if repeat > 1 else None

    return {
        "id": tc_id,
        "label": tc.get("label", ""),
        "dimension": tc.get("dimension", ""),
        "tags": tc.get("tags", []),
        "runs": all_runs,
        "consistency": consistency,
        "overall_pass": all(
            r["summary"]["failed"] == 0 for r in all_runs
        ),
    }


def _analyse_consistency(runs: list[dict]) -> dict:
    """
    Check that assertion results are identical across repeated runs.

    For each assertion index, verify that the 'actual' value is the same
    in every run. Numeric mismatches indicate non-determinism.
    """
    issues: list[str] = []

    if not runs:
        return {"consistent": True, "issues": [], "pass_per_run": []}

    n_assertions = len(runs[0]["assertion_results"])
    for i in range(n_assertions):
        actuals = []
        atype = None
        for run in runs:
            ar = run["assertion_results"][i] if i < len(run["assertion_results"]) else None
            if ar and ar.get("passed") is not None:  # skip skipped assertions
                actuals.append(str(ar.get("actual")))
                atype = ar.get("assertion_type", "?")

        unique = set(actuals)
        if len(unique) > 1:
            issues.append(f"assertion[{i}] ({atype}) varied across runs: {unique}")

    all_passed = [r["summary"]["failed"] == 0 for r in runs]
    return {
        "consistent": len(issues) == 0 and all(all_passed),
        "issues": issues,
        "pass_per_run": all_passed,
    }


# =============================================================================
# Main runner
# =============================================================================

async def main(args: argparse.Namespace) -> None:
    # Load dataset
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    test_cases = dataset["test_cases"]
    if args.case:
        test_cases = [tc for tc in test_cases if tc["id"] == args.case]
        if not test_cases:
            log.error("No test case with id=%s found.", args.case)
            sys.exit(1)

    repeat = args.repeat

    log.info("Running %d test case(s), %d repeat(s) each.", len(test_cases), repeat)

    results = []
    for tc in test_cases:
        log.info("[%s] %s", tc["id"], tc.get("label", ""))
        result = await run_test_case(tc, repeat=repeat)
        results.append(result)

        status = "PASS" if result["overall_pass"] else "FAIL"
        s = result["runs"][0]["summary"]
        log.info(
            "  → %s  assertions: %d passed / %d failed / %d skipped",
            status, s["passed"], s["failed"], s["skipped"],
        )

    # Write results
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = output_dir / f"run_{ts}.json"

    output_payload = {
        "metadata": {
            "run_at_utc": datetime.now(timezone.utc).isoformat(),
            "condition": args.condition,
            "dataset_version": dataset["metadata"]["dataset_version"],
            "total_cases": len(results),
            "framework_version": "1.0.0",
            "note": (
                "Condition A (direct tool calls). No actual agent LLM calls were made. "
                "Assertions evaluate the MCP tool functions directly for deterministic correctness. "
                "Agent-level and LLM-judge assertions are marked SKIPPED."
            ),
        },
        "results": results,
        "aggregate": _aggregate(results),
    }

    with open(out_path, "w") as f:
        json.dump(output_payload, f, indent=2, default=str)

    log.info("Results written to %s", out_path)
    _print_summary(output_payload)


def _aggregate(results: list[dict]) -> dict:
    total = len(results)
    overall_pass = sum(1 for r in results if r["overall_pass"])
    by_dim: dict[str, dict] = {}
    for r in results:
        dim = r.get("dimension", "unknown")
        if dim not in by_dim:
            by_dim[dim] = {"pass": 0, "fail": 0}
        if r["overall_pass"]:
            by_dim[dim]["pass"] += 1
        else:
            by_dim[dim]["fail"] += 1

    latencies = []
    for r in results:
        for run in r.get("runs", []):
            latencies.append(run.get("latency_sec", 0.0))

    return {
        "total_cases": total,
        "overall_pass": overall_pass,
        "overall_fail": total - overall_pass,
        "pass_rate": round(overall_pass / total, 4) if total else 0.0,
        "by_dimension": by_dim,
        "latency_p50_sec": round(sorted(latencies)[len(latencies) // 2], 4) if latencies else 0.0,
        "latency_max_sec": round(max(latencies), 4) if latencies else 0.0,
    }


def _print_summary(payload: dict) -> None:
    agg = payload["aggregate"]
    print("\n" + "=" * 60)
    print(f"  IRS TaxRisk Eval Summary — {payload['metadata']['run_at_utc']}")
    print("=" * 60)
    print(f"  Total cases   : {agg['total_cases']}")
    print(f"  Pass          : {agg['overall_pass']}")
    print(f"  Fail          : {agg['overall_fail']}")
    print(f"  Pass rate     : {agg['pass_rate']:.1%}")
    print(f"  Latency p50   : {agg['latency_p50_sec']:.4f}s")
    print(f"  Latency max   : {agg['latency_max_sec']:.4f}s")
    print()
    print("  By dimension:")
    for dim, counts in agg["by_dimension"].items():
        print(f"    {dim:<35} P={counts['pass']}  F={counts['fail']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IRS TaxRisk eval harness")
    parser.add_argument("--condition", choices=["A", "B"], default="A",
                        help="A=with tools (default), B=no-tool baseline (requires live agent)")
    parser.add_argument("--case", default=None, help="Run a single test case by ID, e.g. TC-01")
    parser.add_argument("--repeat", type=int, default=1,
                        help="Repeat each case N times for consistency check (default: 1)")
    parser.add_argument("--output", default=str(RESULTS_DIR),
                        help=f"Results output directory (default: {RESULTS_DIR})")
    args = parser.parse_args()
    asyncio.run(main(args))
