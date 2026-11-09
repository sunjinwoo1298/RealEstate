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
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.core.database import close_db_connection, get_session_factory
from backend.models.lead import ConsentStatus, Lead, LeadStatus
from backend.models.lead_qualification import ConfigurationType, LeadQualification
from backend.models.lead_source import LeadSource, SourceType
from backend.models.project import Project
from backend.models.site_visit import SiteVisit, SiteVisitStatus

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


_IST = ZoneInfo("Asia/Kolkata")

# The client's sample table (Project / Wants / Visit Status). Hardik's visit
# is "Booked 2026-11-01 11:00". Kavita is "Visited" with no date given, so
# 2026-11-02 11:00 IST is assumed. No executive is assigned (none was given).
SAMPLE_DETAILS = {
    "LD-58210": {
        "project": "Project 1",
        "configuration": ConfigurationType.BHK_3,
        "lead_status": LeadStatus.VISIT_BOOKED,
        "visit": (SiteVisitStatus.CONFIRMED, datetime(2026, 11, 1, 11, 0, tzinfo=_IST)),
    },
    "LD-58211": {
        "project": "Project 2",
        "configuration": ConfigurationType.BHK_2,
        "lead_status": LeadStatus.NEW,
        "visit": None,
    },
    "LD-58224": {
        "project": "Project 2",
        "configuration": ConfigurationType.BHK_2,
        "lead_status": LeadStatus.VISIT_COMPLETED,
        "visit": (SiteVisitStatus.COMPLETED, datetime(2026, 11, 2, 11, 0, tzinfo=_IST)),
    },
}


async def _apply_sample_details(db) -> None:
    """Idempotently adds project, wanted configuration, status and visit for the three sample leads."""
    for external_id, details in SAMPLE_DETAILS.items():
        source = (
            await db.execute(select(LeadSource).where(LeadSource.external_lead_id == external_id))
        ).scalars().first()
        if source is None:
            continue
        lead = (await db.execute(select(Lead).where(Lead.id == source.lead_id))).scalar_one()
        project = (await db.execute(select(Project).where(Project.name == details["project"]))).scalar_one_or_none()
        if project is None:
            project = Project(name=details["project"], description=f"{details['project']} (sample data)", is_active=True)
            db.add(project)
            await db.flush()
        qualification = (
            await db.execute(select(LeadQualification).where(LeadQualification.lead_id == lead.id))
        ).scalar_one_or_none()
        if qualification is None:
            db.add(LeadQualification(lead_id=lead.id, project_id=project.id, configuration=details["configuration"]))
        if details["visit"] is not None:
            has_visit = (await db.execute(select(SiteVisit).where(SiteVisit.lead_id == lead.id))).scalars().first()
            if has_visit is None:
                status, start = details["visit"]
                db.add(
                    SiteVisit(
                        lead_id=lead.id,
                        project_id=project.id,
                        executive_id=None,
                        start_time=start,
                        end_time=start + timedelta(hours=1),
                        status=status,
                        booking_reference=f"SV-{uuid.uuid4().hex[:8].upper()}",
                    )
                )
        if lead.lead_status == LeadStatus.NEW:
            lead.lead_status = details["lead_status"]
        await db.commit()
        print(f"Sample details applied for {external_id}.")


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
        await _apply_sample_details(db)


def main() -> None:
    try:
        asyncio.run(_seed())
    finally:
        asyncio.run(close_db_connection())


if __name__ == "__main__":
    main()
