from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_token
from app.core.database import get_db
from app.core.models import Job, Record
from app.core.schemas import IngestRequest, IngestResponse
from app.tasks.deidentify import process_record

router = APIRouter(dependencies=[Depends(verify_token)])


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    job = Job(record_count=len(request.records))
    db.add(job)
    await db.flush()

    dispatches: list[tuple[str, str]] = []
    for req_record in request.records:
        record = Record(
            job_id=job.id,
            original_id=req_record.id,
            raw_text=req_record.text,
        )
        db.add(record)
        await db.flush()
        dispatches.append((str(record.id), str(job.id)))

    # Commit before dispatching so workers can read the persisted rows
    await db.commit()

    for record_id, job_id in dispatches:
        process_record.delay(record_id, job_id)

    return IngestResponse(
        job_id=str(job.id),
        status="pending",
        record_count=len(request.records),
    )
