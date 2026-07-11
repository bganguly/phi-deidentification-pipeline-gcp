#!/usr/bin/env bash
# Usage: ./scripts/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORTFOLIO_DIR="/Users/bikram/Personal/interview-prep/grouped-projects/portfolio"
DEPLOY_LIVE="${PORTFOLIO_DIR}/deploy-live.js"

printf '\n  [1] Local  — Docker Compose local stack\n'
printf '  [2] Cloud  — deploy to Cloud Run\n'
printf '  [3] Down   — tear down local Docker stack\n\n'
read -rp 'Choose [1]: ' _MODE
case "${_MODE:-1}" in
  2) TARGET="cloud" ;;
  3) TARGET="down" ;;
  *) TARGET="local" ;;
esac

# ── Down ──────────────────────────────────────────────────────────────────────
if [[ "${TARGET}" == "down" ]]; then
  docker compose -f "${ROOT_DIR}/docker-compose.yml" down -v
  echo "✓ Stack stopped."
  exit 0
fi

# ── Local ─────────────────────────────────────────────────────────────────────
if [[ "${TARGET}" == "local" ]]; then
  ENV_FILE="${ROOT_DIR}/.env"
  [[ ! -f "${ENV_FILE}" ]] && cp "${ROOT_DIR}/.env.example" "${ENV_FILE}"
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && ! grep -q "^ANTHROPIC_API_KEY=sk-ant" "${ENV_FILE}" 2>/dev/null; then
    read -rp "Enter your Anthropic API key (sk-ant-...): " _key
    [[ -z "${_key}" ]] && { echo "Error: API key required." >&2; exit 1; }
    export ANTHROPIC_API_KEY="${_key}"
    grep -q "^ANTHROPIC_API_KEY=" "${ENV_FILE}" \
      && sed -i '' "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${_key}|" "${ENV_FILE}" \
      || echo "ANTHROPIC_API_KEY=${_key}" >> "${ENV_FILE}"
  fi
  docker compose -f "${ROOT_DIR}/docker-compose.yml" up --build -d
  echo "✓ API: http://localhost:8000  |  Docs: http://localhost:8000/docs"
  exit 0
fi

# ── Cloud Run ─────────────────────────────────────────────────────────────────
echo "▶ Cloud Run deploy"

command -v gcloud >/dev/null 2>&1 || { echo "Error: gcloud CLI not found."; exit 1; }

ENV_CLOUD="${ROOT_DIR}/.env.cloud"
[[ -f "${ENV_CLOUD}" ]] || { echo "Error: .env.cloud not found. Add DATABASE_URL, DATABASE_SYNC_URL, REDIS_URL, PIPELINE_ACCESS_TOKEN."; exit 1; }

_cv() { grep "^${1}=" "${ENV_CLOUD}" | cut -d= -f2- || true; }
CLOUD_DB_URL="$(_cv DATABASE_URL)"
CLOUD_DB_SYNC_URL="$(_cv DATABASE_SYNC_URL)"
CLOUD_REDIS_URL="$(_cv REDIS_URL)"
PIPELINE_ACCESS_TOKEN="$(_cv PIPELINE_ACCESS_TOKEN)"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-$(_cv ANTHROPIC_API_KEY)}"

[[ -z "${PIPELINE_ACCESS_TOKEN}" ]] && { echo "Error: PIPELINE_ACCESS_TOKEN missing from .env.cloud"; exit 1; }
if [[ -z "${ANTHROPIC_API_KEY}" ]]; then
  read -rsp "Anthropic API key (sk-ant-...): " ANTHROPIC_API_KEY; echo
  [[ -z "${ANTHROPIC_API_KEY}" ]] && { echo "Error: API key required."; exit 1; }
fi

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
[[ -z "${GCP_PROJECT}" ]] && read -rp "GCP Project ID: " GCP_PROJECT
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="phi-pipeline-api"
IMAGE="gcr.io/${GCP_PROJECT}/${SERVICE_NAME}:latest"

if ! docker info >/dev/null 2>&1; then
  echo "▶ Starting Docker Desktop..."
  open -a Docker
  until docker info >/dev/null 2>&1; do sleep 2; done
  echo "▶ Docker ready"
fi

echo "▶ Building image..."
docker build -f "${ROOT_DIR}/docker/Dockerfile.api" -t "${IMAGE}" "${ROOT_DIR}"

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

echo "▶ Updating deploy-live.js → ${SERVICE_URL}"
sed -i '' "s|phiBackendUrl:.*|phiBackendUrl: '${SERVICE_URL}',|" "${DEPLOY_LIVE}"

echo "▶ Pushing portfolio..."
git -C "${PORTFOLIO_DIR}" add deploy-live.js
git -C "${PORTFOLIO_DIR}" commit -m "Set phiBackendUrl to ${SERVICE_URL}"
git -C "${PORTFOLIO_DIR}" push

echo ""
echo "✓ Live: ${SERVICE_URL}"
echo "  Docs: ${SERVICE_URL}/docs"
