"""
eval/scripts/test_eval_deterministic.py
========================================
pytest integration for the deterministic evaluation harness.

Runs every test case in golden_dataset.json via pytest so results appear
in the standard pytest output and CI reports. Each test case becomes one
pytest test node.

Usage
-----
    # From repo root with venv active:
    pytest eval/scripts/test_eval_deterministic.py -v

    # Single case:
    pytest eval/scripts/test_eval_deterministic.py -v -k "TC-02"

    # With consistency repeats: use the EVAL_REPEAT env var
    EVAL_REPEAT=3 pytest eval/scripts/test_eval_deterministic.py -v
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATASET_PATH = REPO_ROOT / "eval" / "datasets" / "golden_dataset.json"

# Number of consistency repeats: controlled by EVAL_REPEAT env var (default 1)
_REPEAT = int(os.environ.get("EVAL_REPEAT", "1"))


def _load_cases() -> list[tuple[str, dict]]:
    with open(DATASET_PATH) as f:
        ds = json.load(f)
    return [(tc["id"], tc) for tc in ds["test_cases"]]


@pytest.mark.parametrize("tc_id,tc", _load_cases(), ids=[t[0] for t in _load_cases()])
@pytest.mark.asyncio
async def test_case(tc_id: str, tc: dict):
    """
    Run a single golden-dataset test case deterministically.

    Each assertion is checked individually so pytest pinpoints which
    assertion within a case failed.
    """
    # Add eval/scripts to sys.path so harness can be imported without
    # the eval package needing __init__.py files.
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "harness", REPO_ROOT / "eval" / "scripts" / "harness.py"
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    run_test_case = _mod.run_test_case

    result = await run_test_case(tc, repeat=_REPEAT)

    # Check each assertion in run 0
    for ar in result["runs"][0]["assertion_results"]:
        if ar.get("passed") is None:
            pytest.skip(ar.get("message", "skipped"))
        assert ar["passed"], (
            f"[{tc_id}] Assertion '{ar['assertion_type']}' FAILED: {ar.get('message', '')}"
            f" | expected={ar.get('expected')} actual={ar.get('actual')}"
        )

    # If repeat > 1, check consistency across runs
    if _REPEAT > 1 and result.get("consistency"):
        cons = result["consistency"]
        if not cons["consistent"]:
            pytest.fail(
                f"[{tc_id}] Consistency FAILED across {_REPEAT} runs: {cons['issues']}"
            )
