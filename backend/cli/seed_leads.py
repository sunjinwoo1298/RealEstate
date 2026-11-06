"""
Idempotent development seed script for Feature 02 (Lead Ingestion & Deduplication).

Usage:
    conda activate minor
    python -m backend.cli.seed_leads

Seeds the three provided demo enquiries as Lead + LeadSource records, keyed
by their external/demo reference ids (LD-58210, LD-58211, LD-58224) so the
script can be re-run safely without creating duplicates.

No buyer phone number or email address was supplied for these examples, so
none is fabricated here: normalized_phone/normalized_email are left null,
consistent with the nullable Lead schema. Real ingestion (website, webhook,
manual, CSV) still requires a valid phone number.
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from backend.core.database import close_db_connection, get_session_factory
from backend.models.lead import ConsentStatus, Lead
from backend.models.lead_source import LeadSource, SourceType

DEMO_ENQUIRIES = [
    {
        "external_lead_id": "LD-58210",
        "full_name": "Hardik Patel",
        "source_type": SourceType.PROPERTY_PORTAL,
        "campaign_name": "Project 1 - 3 BHK",
    },
    {
        "external_lead_id": "LD-58211",
        "full_name": "Nidhi Shah",
        "source_type": SourceType.SOCIAL_AD,
        "campaign_name": "Project 2 - 2 BHK",
    },
    {
        "external_lead_id": "LD-58224",
        "full_name": "Kavita Joshi",
        "source_type": SourceType.HOARDING,
        "campaign_name": "Project 2 - 2 BHK",
    },
]


async def _seed() -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        for entry in DEMO_ENQUIRIES:
            existing = await db.execute(
                select(LeadSource).where(
                    LeadSource.source_type == entry["source_type"],
                    LeadSource.external_lead_id == entry["external_lead_id"],
                )
            )
            if existing.scalar_one_or_none() is not None:
                print(f"Skipping {entry['external_lead_id']}: already seeded.")
                continue

            lead = Lead(
                full_name=entry["full_name"],
                normalized_phone=None,
                normalized_email=None,
                consent_status=ConsentStatus.NOT_RECORDED,
            )
            db.add(lead)
            await db.flush()

            lead_source = LeadSource(
                lead_id=lead.id,
                source_type=entry["source_type"],
                external_lead_id=entry["external_lead_id"],
                campaign_name=entry["campaign_name"],
                raw_payload={"demo_reference": entry["external_lead_id"]},
                submitted_at=datetime.now(timezone.utc),
            )
            db.add(lead_source)
            await db.commit()
            print(f"Seeded {entry['external_lead_id']} ({entry['full_name']}).")


def main() -> None:
    try:
        asyncio.run(_seed())
    finally:
        asyncio.run(close_db_connection())


if __name__ == "__main__":
    main()
