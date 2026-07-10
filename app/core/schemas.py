from pydantic import BaseModel


class IngestRecord(BaseModel):
    id: str | None = None
    text: str


class IngestRequest(BaseModel):
    records: list[IngestRecord]


class IngestResponse(BaseModel):
    job_id: str
    status: str
    record_count: int


class RecordOut(BaseModel):
    id: str
    original_id: str | None
    deidentified_text: str | None
    status: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    record_count: int
    completed_count: int
    records: list[RecordOut]
