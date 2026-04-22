from pydantic import BaseModel, HttpUrl


class ScheduleImportRequest(BaseModel):
    image_url: HttpUrl | None = None
    raw_text: str | None = None
    timezone: str = "UTC"


class ImportedEventPreview(BaseModel):
    title: str
    starts_at: str
    ends_at: str


class ScheduleImportResponse(BaseModel):
    source: str
    extracted_events: list[ImportedEventPreview]
    approval_required: bool = True

