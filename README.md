# PHI De-identification Pipeline — spaCy + Claude Haiku 4.5 + FastAPI

Production-grade **healthcare PHI detection and synthetic substitution pipeline** with a
two-tier detection strategy: spaCy biomedical NER handles ~90% of records as tier-1;
Claude Haiku 4.5 covers ambiguous fallbacks. Detected entities are replaced with
Faker-generated synthetic equivalents — not blank redaction — preserving analytical signal.
Full observability via structured JSON logs, Prometheus metrics, and OpenTelemetry traces → Jaeger.

> **Demo batch:** 50 clinical records generated on the fly (randomised names, SSNs, MRNs, dates, addresses, phones — no pre-existing files) · ~350 PHI entities detected and replaced · <10% of records reach Claude (spaCy handles the rest) · 3 parallel Celery workers · real-time progress with per-record Jaeger trace links

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
