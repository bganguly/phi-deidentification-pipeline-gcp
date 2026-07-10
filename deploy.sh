#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"

# ── Anthropic API key resolution ──────────────────────────────────────────────
# Priority: (1) already in shell env  (2) already in .env  (3) prompt user
_resolve_api_key() {
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "▶ ANTHROPIC_API_KEY found in shell environment"
    return
  fi

  if [[ -f "${ENV_FILE}" ]] && grep -q "^ANTHROPIC_API_KEY=sk-ant" "${ENV_FILE}" 2>/dev/null; then
    echo "▶ ANTHROPIC_API_KEY found in .env"
    return
  fi

  echo ""
  read -rp "Enter your Anthropic API key (sk-ant-...): " _key
  if [[ -z "${_key}" ]]; then
    echo "Error: API key required." >&2
    exit 1
  fi
  export ANTHROPIC_API_KEY="${_key}"

  # Persist into .env so subsequent runs skip the prompt
  if [[ -f "${ENV_FILE}" ]]; then
    # Replace placeholder line if present, otherwise append
    if grep -q "^ANTHROPIC_API_KEY=" "${ENV_FILE}"; then
      sed -i '' "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${_key}|" "${ENV_FILE}"
    else
      echo "ANTHROPIC_API_KEY=${_key}" >> "${ENV_FILE}"
    fi
  fi
  echo "▶ API key saved to .env"
}

# ── Bootstrap .env ────────────────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "▶ Created .env from .env.example"
fi

# ── Target selection ──────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PHI De-identification Pipeline"
echo "    [1] local  — Docker Compose (API + worker + Redis + Postgres + Jaeger + Grafana)"
echo "    [2] down   — tear down local stack"
echo "    [3] cloud  — deploy API to Cloud Run + update portfolio deploy-live.js"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TARGET="local"
if read -r -t 10 -p "Choose [1/2/3, default=1]: " CHOICE 2>/dev/null; then
  case "${CHOICE}" in
    2) TARGET="down" ;;
    3) TARGET="cloud" ;;
    *) TARGET="local" ;;
  esac
else
  echo ""
  echo "No input — defaulting to local"
fi

# ── Local stack ───────────────────────────────────────────────────────────────
if [[ "${TARGET}" == "local" ]]; then
  _resolve_api_key

  echo ""
  echo "▶ Starting stack..."
  docker compose -f "${SCRIPT_DIR}/docker-compose.yml" up --build -d

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Stack ready"
  echo "    API / docs   : http://localhost:8000  |  http://localhost:8000/docs"
  echo "    Jaeger UI    : http://localhost:16686"
  echo "    Grafana      : http://localhost:3000  (admin / admin)"
  echo "    Prometheus   : http://localhost:9090"
  echo ""
  echo "  Seed demo data:"
  echo "    python ${SCRIPT_DIR}/scripts/seed.py"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Tear down ─────────────────────────────────────────────────────────────────
elif [[ "${TARGET}" == "down" ]]; then
  echo "▶ Stopping stack..."
  docker compose -f "${SCRIPT_DIR}/docker-compose.yml" down -v
  echo "✓ Stack stopped and volumes removed"

# ── Cloud Run deployment ──────────────────────────────────────────────────────
elif [[ "${TARGET}" == "cloud" ]]; then
  _resolve_api_key

  # Prerequisites
  command -v gcloud >/dev/null 2>&1 || { echo "Error: gcloud CLI not found. Install it first."; exit 1; }

  # GCP config — prefer env vars, fall back to prompts
  GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
  if [[ -z "${GCP_PROJECT}" ]]; then
    read -rp "GCP Project ID: " GCP_PROJECT
  fi
  GCP_REGION="${GCP_REGION:-us-central1}"
  SERVICE_NAME="phi-pipeline-api"
  IMAGE="gcr.io/${GCP_PROJECT}/${SERVICE_NAME}:latest"

  # Cloud-specific env vars (separate from local .env)
  ENV_CLOUD="${SCRIPT_DIR}/.env.cloud"
  if [[ ! -f "${ENV_CLOUD}" ]]; then
    echo ""
    echo "Error: .env.cloud not found. Create it with cloud DATABASE_URL, DATABASE_SYNC_URL,"
    echo "  REDIS_URL, and PIPELINE_ACCESS_TOKEN for the Cloud Run deployment."
    echo ""
    echo "  Example:"
    echo "    DATABASE_URL=postgresql+asyncpg://phi:PASSWORD@/phi_pipeline?host=/cloudsql/PROJECT:REGION:INSTANCE"
    echo "    DATABASE_SYNC_URL=postgresql+psycopg2://phi:PASSWORD@/phi_pipeline?host=/cloudsql/PROJECT:REGION:INSTANCE"
    echo "    REDIS_URL=redis://HOST:6379/0"
    echo "    PIPELINE_ACCESS_TOKEN=your-secret-token"
    exit 1
  fi

  # Load cloud env vars (no export; we pass them explicitly to gcloud)
  _get_cloud_var() { grep "^${1}=" "${ENV_CLOUD}" | cut -d= -f2-; }
  CLOUD_DB_URL="$(_get_cloud_var DATABASE_URL)"
  CLOUD_DB_SYNC_URL="$(_get_cloud_var DATABASE_SYNC_URL)"
  CLOUD_REDIS_URL="$(_get_cloud_var REDIS_URL)"
  PIPELINE_ACCESS_TOKEN="$(_get_cloud_var PIPELINE_ACCESS_TOKEN)"

  [[ -z "${PIPELINE_ACCESS_TOKEN}" ]] && { echo "Error: PIPELINE_ACCESS_TOKEN must be set in .env.cloud"; exit 1; }

  echo ""
  echo "▶ Building API image..."
  docker build -f "${SCRIPT_DIR}/docker/Dockerfile.api" -t "${IMAGE}" "${SCRIPT_DIR}"

  echo "▶ Pushing to GCR..."
  docker push "${IMAGE}"

  echo "▶ Deploying to Cloud Run (${GCP_REGION})..."
  gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}" \
    --region "${GCP_REGION}" \
    --project "${GCP_PROJECT}" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "DATABASE_URL=${CLOUD_DB_URL},DATABASE_SYNC_URL=${CLOUD_DB_SYNC_URL},REDIS_URL=${CLOUD_REDIS_URL},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},PIPELINE_ACCESS_TOKEN=${PIPELINE_ACCESS_TOKEN}" \
    --quiet

  SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${GCP_REGION}" --project "${GCP_PROJECT}" \
    --format 'value(status.url)')"

  echo "▶ Service URL: ${SERVICE_URL}"
  echo ""
  echo "  If this is first deployment, set phiBackendUrl once in portfolio/deploy-live.js:"
  echo "    phiBackendUrl: '${SERVICE_URL}',"
  echo "  Access is controlled by the token — not by this URL."

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Cloud Run deployment complete"
  echo "    API URL      : ${SERVICE_URL}"
  echo "    Docs         : ${SERVICE_URL}/docs"
  echo "    Access token : set in .env.cloud"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi
