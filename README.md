# PHI De-identification Pipeline — spaCy + Claude Haiku 4.5 + FastAPI

Production-grade **healthcare PHI detection and synthetic substitution pipeline** with a
two-tier detection strategy: spaCy biomedical NER handles ~90% of records as tier-1;
Claude Haiku 4.5 covers ambiguous fallbacks. Detected entities are replaced with
Faker-generated synthetic equivalents — not blank redaction — preserving analytical signal.
Full observability via structured JSON logs, Prometheus metrics, and OpenTelemetry traces → Jaeger.

> **Demo batch:** 50 clinical records generated on the fly (randomised names, SSNs, MRNs, dates, addresses, phones — no pre-existing files) · ~350 PHI entities detected and replaced · <10% of records reach Claude (spaCy handles the rest) · 3 parallel Celery workers · real-time progress with per-record Jaeger trace links

---

## How it works

1. **Records generated in the browser** — no files, no uploads. 50 clinical notes are constructed in JavaScript from randomised Faker values (name, SSN, MRN, DOB, address, phone, physician). Each contains 6–8 PHI entities.
2. **POST /ingest** — all 50 records are sent as one JSON batch. FastAPI writes a `Job` row and 50 `Record` rows to PostgreSQL (`raw_text` persisted, `deidentified_text` null, `status = pending`), then enqueues one Celery task per record onto Redis. Returns a `job_id` immediately.
3. **Celery workers process records in parallel** — each worker reads its `Record` from PostgreSQL and runs spaCy `en_core_sci_md` + regex patterns (SSN, MRN, PHONE, EMAIL). This produces a list of detected entities and a mean confidence score across them.
4. **Claude fallback (tier-2)** — the 0.85 threshold is evaluated per-record, not per-entity. If spaCy/regex finds entities, mean confidence is ≥ 0.90 and Claude is not called. Claude is only invoked when spaCy finds *nothing* but the text contains PHI-indicator keywords (`patient`, `ssn`, `mrn`, etc.) — confidence returns 0.40, triggering the fallback. Claude returns structured JSON with character offsets; any new spans are merged in without duplicating spaCy's results.
5. **Synthetic substitution** — entities are sorted by character offset descending so replacements don't shift earlier spans. Each span is string-spliced with a Faker value matched to its type (names → `faker.name()`, dates shifted ±30 days, SSNs → `faker.ssn()`, etc.).
6. **Two writes, one commit** — `Record.deidentified_text` is updated and one `RedactionLog` row is written per entity: SHA-256 hash of the original value, the Faker replacement, entity type, confidence, and which model detected it. The original PHI value is never stored.
7. **Browser polls GET /records/{job_id}** — once per second until all 50 complete. Completions stream back as workers finish.

---

## Remote deployment

Two supported targets:

| Target | Command | What's deployed |
|---|---|---|
| Cloud Run (API only) | `./deploy.sh` | API container → Cloud Run; worker **not** deployed |
| GKE (full stack) | `terraform apply` in `infra/` + `kubectl apply -f k8s/` | API + Celery workers + HPA on GKE cluster |

**Cloud Run prerequisites** — create `.env.cloud` before running `deploy.sh`:
```
DATABASE_URL=postgresql+asyncpg://...    # managed Cloud SQL or external PostgreSQL
DATABASE_SYNC_URL=postgresql+psycopg2://...
REDIS_URL=redis://...                    # Cloud Memorystore or external Redis
PIPELINE_ACCESS_TOKEN=<your-token>
ANTHROPIC_API_KEY=sk-ant-...
```
`deploy.sh` builds the API image, pushes to GCR, deploys to Cloud Run, and automatically writes the live URL into the portfolio's `deploy-live.js`. Without a deployed Celery worker, `/ingest` will accept records and queue them in Redis but nothing will process them — use GKE for a complete deployment.

**GKE** via `infra/` provisions a GKE cluster, Cloud SQL, Artifact Registry, and VPC. `k8s/` manifests deploy the API, Celery workers, and an HPA that scales workers horizontally under load.

---

## Using real clinical documents

The `/ingest` endpoint accepts any text — replace synthetic records with real clinical notes in the same JSON format. Key considerations:

| Concern | Detail |
|---|---|
| **spaCy/regex tier** | Runs fully on your infrastructure — no data leaves |
| **Claude fallback** | Sends raw text to Anthropic's API. For HIPAA compliance, a Business Associate Agreement (BAA) with Anthropic is required, or set `CONFIDENCE_THRESHOLD=1.0` in `.env` to disable Claude entirely and rely on spaCy/regex only |
| **Audit trail** | `redaction_log` stores SHA-256 hashes of original values — you can verify a specific value was present without retaining raw PII in the database |

---

## What this demonstrates

| Skill | Evidence |
|---|---|
| **Pragmatic LLM integration** | Claude is not used for everything — it is invoked surgically only when rules-based NLP falls short, minimising API cost and latency |
| **Cost-conscious AI design** | Two-tier architecture keeps ~90% of records within the free spaCy/regex tier; Claude spend scales with edge-case volume, not total record count |
| **Production API design** | Async FastAPI + Celery decouples ingestion from processing; records persist before workers start so no data is lost if a worker crashes |
| **Compliance-aware audit logging** | SHA-256 hashes satisfy audit requirements without storing raw PHI — a deliberate design choice, not an afterthought |
| **Healthcare domain knowledge** | Correct PHI entity taxonomy (PERSON, DATE, SSN, MRN, PHONE, EMAIL, GPE, LOC, ORG); date shifting preserves temporal relationships rather than nulling dates |
| **Observability** | Every record produces an OTel trace visible in Jaeger; Prometheus counters track processed records, entity counts, and Claude fallback rate |
| **Infrastructure as code** | Terraform (GKE) + Pulumi-style `deploy.sh` (Cloud Run); `k8s/` manifests with HPA for worker autoscaling |

---

| | |
|---|---|
| **LLM integration (Claude Haiku 4.5)** | Anthropic SDK; tier-2 fallback for low-confidence records; structured JSON output via system prompt; entity extraction with character offsets |
| **NLP / biomedical NER** | spaCy `en_core_sci_md`; detects PERSON, DATE, GPE, LOC, ORG; regex tier for SSN, MRN, PHONE, EMAIL (0.97 confidence) |
| **Synthetic substitution** | Faker-generated replacements per entity type — names, SSNs, MRNs, shifted dates, emails, phone numbers, addresses — not blank redaction |
| **Async Python API** | FastAPI + asyncpg; Celery workers consume Redis queue for batch processing; Alembic DDL migrations on PostgreSQL 16 |
| **Observability** | Prometheus metrics endpoint; OpenTelemetry traces → Jaeger (OTLP gRPC); structured JSON logging |
| **Audit logging** | SHA-256 hash of every original PHI value stored in PostgreSQL redaction log — enables compliance audit without retaining raw PII |
| **Auth** | HMAC-SHA256 time-limited bearer tokens; `grant-access.sh` issues 48h tokens |
| **IaC** | Terraform (`infra/`) — GKE cluster, Cloud SQL, Artifact Registry, VPC; `k8s/` manifests with HPA on workers |
| **CI/CD** | `deploy.sh` — Docker Compose local stack or Cloud Run deploy; `cloudbuild.yaml` for GCP Cloud Build |

---

## Detection Strategy

```
Clinical text
      │
      ▼
┌─────────────────────────────────────────────┐
│  Tier 1 — spaCy en_core_sci_md              │
│  • Biomedical NER: PERSON, DATE, GPE,       │
│    LOC, ORG  (confidence: 0.90)             │
│  • Regex: SSN, MRN, PHONE, EMAIL            │
│    (confidence: 0.97)                       │
└────────────────────┬────────────────────────┘
                     │
           confidence ≥ 0.85?
                     │
          ┌──────────┴──────────┐
         YES                   NO
          │                    │
          ▼                    ▼
     Synthetic          ┌─────────────────────┐
    substitution        │  Tier 2 — Claude    │
     (Faker)            │  Haiku 4.5          │
          │             │  Structured JSON     │
          │             │  entity extraction   │
          │             └──────────┬──────────┘
          │                        │
          └──────────┬─────────────┘
                     ▼
         Redacted text + audit log
         (SHA-256 of originals → PostgreSQL)
```

### Entity types & replacements

| PHI Type | Detection | Replacement |
|---|---|---|
| `PERSON` | spaCy NER | `faker.name()` |
| `DATE` | spaCy NER | Date shifted ±30 days |
| `SSN` | Regex `\d{3}-\d{2}-\d{4}` | `faker.ssn()` |
| `MRN` | Regex `MRN[:\s#-]*\d{6,10}` | `MRN-########` |
| `PHONE` | Regex (US formats) | `faker.phone_number()` |
| `EMAIL` | Regex RFC-5321 | `faker.email()` |
| `GPE` / `LOC` | spaCy NER | `faker.city()` |
| `ORG` | spaCy NER | `faker.company()` |

---

## Running

| Action | Command |
|---|---|
| Start local stack (Docker Compose) | `./deploy.sh local` |
| Stop local stack | `./deploy.sh down` |
| Deploy to Cloud Run | `./deploy.sh` |
| Issue a 48h access token | `./grant-access.sh` |

Local prerequisites: **Docker** and **Docker Compose**. An **Anthropic API key** is prompted on first run.

The local stack starts: FastAPI API · Celery worker · PostgreSQL 16 · Redis 7 · Jaeger · Prometheus · Grafana.

### What works locally vs cloud

| | Local (Docker Compose) | Cloud Run |
|---|---|---|
| Swagger UI + REST API | ✅ `localhost:8000/docs` | ✅ |
| `scripts/seed.py` batch ingest | ✅ | ✅ |
| Jaeger trace UI | ✅ `localhost:16686` | — |
| Prometheus / Grafana | ✅ `localhost:9090` / `:3000` | — |
| Portfolio browser demo (Claude direct) | ✅ calls Anthropic API from browser, no backend needed | ✅ |
| Portfolio batch demo (50 records live) | ❌ hardwired to Cloud Run URL via `deploy.sh` | ✅ |

> **Cloud cost:** Cloud Run bills while running. Tear down with `./deploy.sh down` or `terraform destroy` when not actively demoing.

---

## Local Endpoints

| Service | URL |
|---|---|
| API + Swagger UI | http://localhost:8000/docs |
| Jaeger traces | http://localhost:16686 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin) |

```bash
# health
curl http://localhost:8000/health

# de-identify a record (bearer token required after first deploy)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient John Smith, DOB 03/15/1982, SSN 123-45-6789, MRN: 00456789"}'

# batch submit (returns job id, workers process async)
curl -X POST http://localhost:8000/ingest/batch \
  -H "Content-Type: application/json" \
  -d '[{"text": "..."}, {"text": "..."}]'
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Local / Docker Compose                          │
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐    │
│  │  FastAPI (8000)  │   │  Celery Worker   │   │  Redis (6379)    │    │
│  │  asyncpg         │──►│  batch jobs      │◄──│  task queue      │    │
│  │  OTLP traces     │   │  spaCy + Claude  │   └──────────────────┘    │
│  └────────┬─────────┘   └────────┬─────────┘                           │
│           │                      │                                      │
│           └──────────┬───────────┘                                      │
│                      ▼                                                  │
│           ┌──────────────────────┐                                      │
│           │  PostgreSQL 16       │                                      │
│           │  phi_pipeline DB     │                                      │
│           │  • records table     │                                      │
│           │  • redaction_log     │                                      │
│           │    (SHA-256 hashes)  │                                      │
│           │  • Alembic DDL       │                                      │
│           └──────────────────────┘                                      │
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐    │
│  │  Jaeger (16686)  │   │ Prometheus (9090) │   │  Grafana (3000)  │    │
│  │  OTLP gRPC 4317  │   │  /metrics scrape  │   │  dashboards      │    │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         GCP (Cloud Run / GKE)                           │
│                                                                         │
│  Artifact Registry                                                      │
│  ┌──────────────────┐                                                   │
│  │  api image       │                                                   │
│  │  worker image    │                                                   │
│  └──────────────────┘                                                   │
│           │ image pull                                                  │
│           ▼                                                             │
│  Cloud Run: phi-api          GKE (k8s/)                                 │
│  ┌───────────────────┐       ┌─────────────────────────────────┐        │
│  │ FastAPI            │  or  │ api-deployment + HPA            │        │
│  │ HMAC bearer auth   │      │ worker-deployment + HPA         │        │
│  │ /ingest /records   │      │ configmap / secret              │        │
│  └───────────────────┘       └─────────────────────────────────┘        │
│                                                                         │
│  Terraform IaC (infra/)                                                 │
│  └─ GKE cluster · Cloud SQL PG 16 · Artifact Registry · VPC            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

| Concern | Approach |
|---|---|
| **Two-tier detection** | spaCy handles the common case cheaply (~90% of records); Claude Haiku 4.5 is invoked only when spaCy confidence drops below 0.85 — minimises API cost while catching edge cases |
| **Synthetic substitution over redaction** | Faker replacements preserve entity structure (dates stay dates, names stay names) so downstream analytics on de-identified data remain valid |
| **SHA-256 audit log** | Original PHI values are hashed before storage — allows auditors to verify a specific value was present without retaining raw PII in the database |
| **Async batch processing** | Celery + Redis queue decouples ingestion from processing; worker HPA scales horizontally under load |
| **Time-limited tokens** | HMAC-SHA256 bearer tokens with 48h expiry via `grant-access.sh` — no long-lived credentials exposed |
