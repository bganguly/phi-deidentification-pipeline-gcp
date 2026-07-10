#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_CLOUD="${SCRIPT_DIR}/.env.cloud"
[ -f "${ENV_CLOUD}" ] || echo "PIPELINE_ACCESS_TOKEN=$(openssl rand -hex 32)" > "${ENV_CLOUD}"
python3 "${SCRIPT_DIR}/scripts/generate_token.py" "$@"
