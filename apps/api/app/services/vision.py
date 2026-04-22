from app.schemas.vision import (
    ImportedEventPreview,
    ScheduleImportRequest,
    ScheduleImportResponse,
)


def preview_schedule_import(payload: ScheduleImportRequest) -> ScheduleImportResponse:
    source = "raw_text" if payload.raw_text else "image_url"
    return ScheduleImportResponse(
        source=source,
        extracted_events=[
            ImportedEventPreview(
                title="Imported Study Block",
                starts_at="2026-04-20T09:00:00",
                ends_at="2026-04-20T11:00:00",
            ),
            ImportedEventPreview(
                title="Imported Lab Session",
                starts_at="2026-04-20T13:30:00",
                ends_at="2026-04-20T15:00:00",
            ),
        ],
        approval_required=True,
    )

