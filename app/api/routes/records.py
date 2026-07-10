import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_token
from app.core.database import get_db
from app.core.models import Job, Record
from app.core.schemas import JobResponse, RecordOut

router = APIRouter(dependencies=[Depends(verify_token)])


@router.get("/records/{job_id}", response_model=JobResponse)
async def get_records(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job_id format")

    job = await db.get(Job, job_uuid)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    result = await db.execute(select(Record).where(Record.job_id == job_uuid))
    records = result.scalars().all()

    return JobResponse(
        job_id=str(job.id),
        status=job.status,
        record_count=job.record_count,
        completed_count=job.completed_count,
        records=[
            RecordOut(
                id=str(r.id),
                original_id=r.original_id,
                deidentified_text=r.deidentified_text,
                status=r.status,
            )
            for r in records
        ],
    )
