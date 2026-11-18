#!/usr/bin/env bash
# Register the IRS AI Risk server as a LOCAL MCP toolkit in watsonx Orchestrate.
#
# A local MCP toolkit ships this server's code to Orchestrate, which installs
# it (via requirements.txt at package_root) and runs `python server.py` over
# stdio INSIDE the Orchestrate runtime — no HTTP, no Code Engine, no container.
#
# Prerequisites:
#   - Python 3.11–3.14 (python3.12 detected on this machine)
#   - ADK installed: pip install --upgrade ibm-watsonx-orchestrate
#   - Config: cp deploy/ibm/local-mcp-toolkit/.env.example deploy/ibm/local-mcp-toolkit/.env
#             then edit the .env file
#
# Usage (from repo root):
#   set -a; source deploy/ibm/local-mcp-toolkit/.env; set +a
#   export WXO_API_KEY="<your ibm cloud api key>"  # or omit to be prompted
#   bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh [--dry-run]
#
# Flags:
#   --dry-run   Build the staging directory and validate imports, but do NOT
#               connect to Orchestrate, remove any existing toolkit, or import.
#               Use this to verify the package before a live registration.
set -euo pipefail

# ── Parse flags ───────────────────────────────────────────────────────────────
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

# ── Config validation ─────────────────────────────────────────────────────────
: "${WXO_ENV_NAME:?set WXO_ENV_NAME (source deploy/ibm/local-mcp-toolkit/.env)}"
: "${WXO_INSTANCE_URL:?set WXO_INSTANCE_URL}"
: "${TOOLKIT_NAME:?set TOOLKIT_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
STAGE_DIR="${SCRIPT_DIR}/_stage"
TOOLKIT_YAML="${SCRIPT_DIR}/_toolkit.generated.yaml"
PACKAGE_NAME="irs_risk"

echo "=== IRS AI Risk — watsonx Orchestrate Toolkit Registration ==="
echo "  env name:      ${WXO_ENV_NAME}"
echo "  instance URL:  ${WXO_INSTANCE_URL}"
echo "  toolkit name:  ${TOOLKIT_NAME}"
echo "  package:       ${PACKAGE_NAME}"
echo ""

# ── Confirm ADK, obtain API key, and activate Orchestrate env (skip in dry-run) ──
if [[ "${DRY_RUN}" == "false" ]]; then
  if ! command -v orchestrate >/dev/null 2>&1; then
    echo "FATAL: 'orchestrate' not found. Install the ADK:" >&2
    echo "       pip install --upgrade ibm-watsonx-orchestrate" >&2
    exit 1
  fi

  # Obtain the API key (never written to disk)
  API_KEY="${WXO_API_KEY:-}"
  if [[ -z "${API_KEY}" ]]; then
    echo "=== watsonx Orchestrate API key ==="
    read -r -s -p "  API key (input hidden): " API_KEY
    echo ""
    if [[ -z "${API_KEY}" ]]; then
      echo "FATAL: no API key provided." >&2
      exit 1
    fi
  fi

  # Activate the Orchestrate environment
  echo "=== Activating ADK environment '${WXO_ENV_NAME}' ==="
  if orchestrate env list 2>/dev/null | grep -q "${WXO_ENV_NAME}"; then
    echo "  env exists — reusing."
  else
    echo "  adding new environment..."
    orchestrate env add --name "${WXO_ENV_NAME}" --url "${WXO_INSTANCE_URL}" --type ibm_iam
  fi
  orchestrate env activate "${WXO_ENV_NAME}" --api-key "${API_KEY}"
  echo ""
  orchestrate env list
  echo ""
fi

echo "=== Staging minimal package_root at ${STAGE_DIR} ==="
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

# Flatten src/irs_risk → _stage/irs_risk
cp -R "${REPO_ROOT}/src/${PACKAGE_NAME}" "${STAGE_DIR}/${PACKAGE_NAME}"

# Orchestrate entry point and dependencies
cp "${SCRIPT_DIR}/server.py"        "${STAGE_DIR}/server.py"
cp "${SCRIPT_DIR}/requirements.txt" "${STAGE_DIR}/requirements.txt"

# Drop __pycache__ directories to keep the upload small
find "${STAGE_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

STAGE_SIZE="$(du -sh "${STAGE_DIR}" | cut -f1)"
echo "  staged package_root size: ${STAGE_SIZE}"
echo "  staged contents:"
find "${STAGE_DIR}" -type f | sort | sed 's|^|    |'
echo ""

# ── Staging validation — verify the package imports correctly ─────────────────
echo "=== Validating staged package imports ==="
VALIDATE_PY="${STAGE_DIR}/_validate.py"
cat > "${VALIDATE_PY}" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from irs_risk.app import mcp
import asyncio
async def check():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "irs_evaluate_tax_profile", "irs_reconcile_income",
        "irs_get_guidance", "irs_get_synthetic_record", "irs_generate_briefing",
    }
    missing = expected - names
    if missing:
        print(f"FAIL: missing tools: {missing}", file=sys.stderr); sys.exit(1)
    print(f"OK: {len(names)} tools discoverable: {sorted(names)}")
asyncio.run(check())
PYEOF
if python3 "${VALIDATE_PY}" 2>&1; then
  echo "  staging validation PASSED"
else
  echo "FATAL: staging validation failed — aborting. Fix the error above before re-running." >&2
  rm -rf "${STAGE_DIR}" "${VALIDATE_PY}"
  exit 1
fi
rm -f "${VALIDATE_PY}"
echo ""

# ── Generate the toolkit spec pointing at the staging dir ─────────────────────
sed -E "s|^package_root:.*|package_root: ${STAGE_DIR}|" \
  "${SCRIPT_DIR}/toolkit.yaml" > "${TOOLKIT_YAML}"
echo "=== Generated toolkit spec: ${TOOLKIT_YAML} ==="
cat "${TOOLKIT_YAML}"
echo ""

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "=== DRY RUN complete — staging directory and spec written but NOT uploaded ==="
  echo "  Stage dir: ${STAGE_DIR}"
  echo "  Spec file: ${TOOLKIT_YAML}"
  echo "  Re-run without --dry-run to perform the live registration."
  exit 0
fi

# ── Remove existing registration (requires explicit confirmation) ─────────────
echo "=== Checking for existing toolkit '${TOOLKIT_NAME}' ==="
if orchestrate toolkits list 2>/dev/null | grep -q "${TOOLKIT_NAME}"; then
  echo ""
  echo "  ⚠  An existing toolkit named '${TOOLKIT_NAME}' was found."
  echo "     Removing it will make all agents using it unavailable until re-import completes."
  read -r -p "  Delete existing toolkit and re-import? [y/N]: " CONFIRM
  if [[ "${CONFIRM}" =~ ^[Yy]$ ]]; then
    orchestrate toolkits remove --name "${TOOLKIT_NAME}"
    echo "  Removed."
  else
    echo "  Aborted by user. Existing toolkit is unchanged." >&2
    rm -rf "${STAGE_DIR}" "${TOOLKIT_YAML}"
    exit 1
  fi
else
  echo "  not found — fresh registration."
fi
echo ""

# ── Import the toolkit ────────────────────────────────────────────────────────
echo "=== Importing local MCP toolkit '${TOOLKIT_NAME}' ==="
orchestrate toolkits import -f "${TOOLKIT_YAML}"

# ── Clean up generated artifacts ─────────────────────────────────────────────
rm -rf "${STAGE_DIR}" "${TOOLKIT_YAML}"

echo ""
echo "=== Registered toolkit list ==="
orchestrate toolkits list
echo ""
echo "Next steps:"
echo "  1. Verify the five IRS tools appear in the toolkit list above."
echo "  2. Create or update your IRS agent to use toolkit '${TOOLKIT_NAME}'."
echo "  3. Test with: orchestrate agents chat --name <agent-name>"
