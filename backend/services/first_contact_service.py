from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import logger
from backend.models.conversation import (
    ChannelType,
    Conversation,
    ConversationLanguage,
    ConversationState,
    ConversationStatus,
)
from backend.models.lead import ConsentStatus, Lead, LeadStatus
from backend.models.lead_qualification import LeadQualification
from backend.models.lead_source import SourceType
from backend.models.message import Message, MessageType, SenderType
from backend.models.project import Project

# Sources whose buyers filled in an enquiry elsewhere and are waiting for a reply.
# (Web-chat leads are already talking to the assistant; CSV / manual entries are staff-driven.)
OUTREACH_SOURCES = {SourceType.PROPERTY_PORTAL, SourceType.SOCIAL_AD, SourceType.HOARDING, SourceType.WEBSITE}

_GREETING = {
    "EN": "Hello {name}, thank you for your enquiry{about}. I am the EstateFlow assistant. Tell me what you are looking for (2 or 3 BHK and your budget) and I can share project details and book a site visit for you.{rera} Reply STOP at any time to opt out.",
    "HI": "नमस्ते {name}, आपकी पूछताछ{about} के लिए धन्यवाद। मैं EstateFlow असिस्टेंट हूँ। बताइए आप क्या खोज रहे हैं (2 या 3 BHK और आपका बजट), मैं प्रोजेक्ट की जानकारी दूँगा और साइट विज़िट बुक करूँगा।{rera} कभी भी बंद करने के लिए STOP लिखें।",
    "GU": "નમસ્તે {name}, તમારી પૂછપરછ{about} બદલ આભાર. હું EstateFlow આસિસ્ટન્ટ છું. તમે શું શોધી રહ્યા છો (2 કે 3 BHK અને બજેટ) તે કહો, હું પ્રોજેક્ટની માહિતી આપીશ અને સાઇટ વિઝિટ બુક કરીશ.{rera} બંધ કરવા માટે ગમે ત્યારે STOP લખો.",
}


class FirstContactService:
    """
    Immediate first reply to an enquiry that arrived from a portal, social ad,
    hoarding number or the website form, so no lead waits for a human to find it.

    The outbound channel is simulated (logged, like the email provider): the
    message is stored as the AI's first message in a conversation, which is
    exactly what the first-response analytics measure. Consent is respected:
    opted-out or consent-declined leads, and leads with no phone or email on
    file, are never contacted.
    """

    @staticmethod
    async def send_first_contact(db: AsyncSession, lead: Lead) -> Optional[Message]:
        if lead.lead_status == LeadStatus.OPTED_OUT or lead.consent_status == ConsentStatus.DECLINED:
            return None
        if not lead.normalized_phone and not lead.normalized_email:
            return None
        already = (
            await db.execute(
                select(Message.id)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.lead_id == lead.id, Message.sender_type == SenderType.AI)
                .limit(1)
            )
        ).first()
        if already is not None:
            return None

        language = (lead.preferred_language or "EN").upper()
        language = language if language in _GREETING else "EN"
        project = (
            (
                await db.execute(
                    select(Project)
                    .join(LeadQualification, LeadQualification.project_id == Project.id)
                    .where(LeadQualification.lead_id == lead.id)
                )
            )
            .scalars()
            .first()
        )
        name = (lead.full_name or "").split()[0] if lead.full_name else ""
        if project is None:
            about = ""
        elif language == "EN":
            about = f" about {project.name}"
        else:
            about = f" ({project.name})"
        rera = f" RERA registration: {project.rera_number}." if project is not None and project.rera_number else ""
        content = _GREETING[language].format(name=name or "there", about=about, rera=rera)

        conversation = Conversation(
            lead_id=lead.id,
            channel=ChannelType.WEB_CHAT,
            status=ConversationStatus.ACTIVE,
            language=ConversationLanguage(language),
            conversation_state=ConversationState.DISCOVERY,
        )
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.AI,
            sender_id=None,
            content=content,
            message_type=MessageType.TEXT,
            extra_metadata={"first_contact": True, "delivery": "SIMULATED_OUTBOUND"},
        )
        db.add(message)
        if lead.lead_status == LeadStatus.NEW:
            lead.lead_status = LeadStatus.AI_CONTACTED
        await db.commit()
        await db.refresh(message)
        logger.info(f"[SIMULATED FIRST CONTACT] lead={lead.id} language={language} -- not a real message send")
        return message
