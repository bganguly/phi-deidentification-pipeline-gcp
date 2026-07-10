from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from celery import Task
from sqlalchemy import case, update

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.core.database import SyncSessionLocal
from app.core.models import Job, Record, RedactionLog
from app.phi.detector import DetectedEntity, detect_phi
from app.phi.claude_fallback import detect_phi_claude
from app.phi.replacer import hash_phi, synthetic_replacement
from app.telemetry.metrics import (
    phi_claude_fallback_total,
    phi_entities_detected_total,
    phi_records_processed_total,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_record(self: Task, record_id: str, job_id: str) -> dict:
    try:
        return _run(record_id, job_id)
    except Exception as exc:
        logger.error("record %s failed: %s", record_id, exc, exc_info=True)
        raise self.retry(exc=exc)


def _run(record_id: str, job_id: str) -> dict:
    with SyncSessionLocal() as db:
        record = db.get(Record, uuid.UUID(record_id))
        if record is None:
            raise ValueError(f"record {record_id} not found")

        raw_text = record.raw_text or ""
        entities, confidence = detect_phi(raw_text)

        model_tier = "spacy+regex"
        if confidence < settings.confidence_threshold:
            entities = _merge(entities, detect_phi_claude(raw_text))
            model_tier = "claude"
            phi_claude_fallback_total.inc()

        deidentified, logs = _process_entities(raw_text, entities, record.id, model_tier)

        record.deidentified_text = deidentified
        record.status = "completed"
        for log_entry in logs:
            db.add(log_entry)

        # Atomic increment + mark job complete when last record finishes
        db.execute(
            update(Job)
            .where(Job.id == uuid.UUID(job_id))
            .values(
                completed_count=Job.completed_count + 1,
                updated_at=datetime.now(timezone.utc),
                status=case(
                    (Job.completed_count + 1 >= Job.record_count, "completed"),
                    else_=Job.status,
                ),
            )
        )
        db.commit()

        phi_records_processed_total.inc()
        phi_entities_detected_total.inc(len(entities))

        return {"record_id": record_id, "entities": len(entities), "model": model_tier}


def _process_entities(
    text: str,
    entities: list[DetectedEntity],
    record_id: uuid.UUID,
    model_tier: str,
) -> tuple[str, list[RedactionLog]]:
    # Sort descending by start so replacements don't shift offsets of earlier spans
    sorted_ents = sorted(entities, key=lambda e: e.start, reverse=True)
    result = text
    logs: list[RedactionLog] = []
    seen_starts: set[int] = set()

    for ent in sorted_ents:
        if ent.start in seen_starts:
            continue
        seen_starts.add(ent.start)

        replacement = synthetic_replacement(ent.text, ent.label)
        result = result[: ent.start] + replacement + result[ent.end :]
        logs.append(RedactionLog(
            record_id=record_id,
            field_hash=hash_phi(ent.text),
            entity_type=ent.label,
            replacement=replacement,
            confidence=ent.confidence,
            model_used=ent.source,
        ))

    return result, logs


def _merge(
    primary: list[DetectedEntity],
    supplemental: list[DetectedEntity],
) -> list[DetectedEntity]:
    primary_spans = {(e.start, e.end) for e in primary}
    return primary + [e for e in supplemental if (e.start, e.end) not in primary_spans]
