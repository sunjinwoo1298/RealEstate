from __future__ import annotations
import csv
import io
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import ValidationException
from backend.models.lead import ConsentStatus
from backend.models.lead_source import SourceType
from backend.schemas.lead import CsvImportResponse, CsvImportRowResult
from backend.services.lead_ingestion_service import LeadIngestionService

REQUIRED_COLUMNS = {"full_name", "phone"}
OPTIONAL_COLUMNS = {"email", "preferred_language", "campaign_name", "external_lead_id"}


class CsvImportService:
    """
    Parses and ingests a CSV lead import. Each row is processed independently
    so a single malformed row does not block the rest of a batch.
    """

    @staticmethod
    async def import_csv(db: AsyncSession, file_bytes: bytes, filename: str) -> CsvImportResponse:
        if not filename.lower().endswith(".csv"):
            raise ValidationException("Only .csv files are accepted")

        if len(file_bytes) > settings.CSV_IMPORT_MAX_FILE_SIZE_BYTES:
            raise ValidationException(
                f"CSV file exceeds the maximum allowed size of {settings.CSV_IMPORT_MAX_FILE_SIZE_BYTES} bytes"
            )

        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationException("CSV file must be UTF-8 encoded") from exc

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValidationException("CSV file has no header row")

        header = {name.strip().lower() for name in reader.fieldnames}
        missing = REQUIRED_COLUMNS - header
        if missing:
            raise ValidationException(f"CSV is missing required column(s): {', '.join(sorted(missing))}")

        rows = list(reader)
        if len(rows) > settings.CSV_IMPORT_MAX_ROWS:
            raise ValidationException(f"CSV exceeds the maximum allowed row count of {settings.CSV_IMPORT_MAX_ROWS}")
        if not rows:
            raise ValidationException("CSV file contains no data rows")

        results: List[CsvImportRowResult] = []
        created_count = 0
        matched_count = 0
        failed_count = 0

        for index, row in enumerate(rows, start=2):  # row 1 is the header
            normalized_row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            full_name = normalized_row.get("full_name", "")
            phone = normalized_row.get("phone", "")

            if not full_name or not phone:
                failed_count += 1
                results.append(
                    CsvImportRowResult(row_number=index, status="FAILED", message="full_name and phone are required")
                )
                continue

            try:
                ingestion = await LeadIngestionService.ingest(
                    db,
                    full_name=full_name,
                    raw_phone=phone,
                    raw_email=normalized_row.get("email") or None,
                    preferred_language=normalized_row.get("preferred_language") or None,
                    source_type=SourceType.CSV_IMPORT,
                    external_lead_id=normalized_row.get("external_lead_id") or None,
                    campaign_name=normalized_row.get("campaign_name") or None,
                    raw_payload=dict(row),
                    consent_status=ConsentStatus.NOT_RECORDED,
                )
            except Exception as exc:  # noqa: BLE001 - row-level isolation by design
                await db.rollback()
                failed_count += 1
                results.append(CsvImportRowResult(row_number=index, status="FAILED", message=str(exc)))
                continue

            if ingestion.created_new_lead:
                created_count += 1
                row_status = "CREATED"
            else:
                matched_count += 1
                row_status = "MATCHED_EXISTING"

            results.append(
                CsvImportRowResult(row_number=index, status=row_status, lead_id=ingestion.lead.id)
            )

        return CsvImportResponse(
            total_rows=len(rows),
            created=created_count,
            matched=matched_count,
            failed=failed_count,
            results=results,
        )
