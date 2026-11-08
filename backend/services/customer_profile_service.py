from __future__ import annotations
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer_account import CustomerAccount
from backend.schemas.customer_profile import CustomerProfile
from backend.services.normalization_service import normalize_phone_optional


class CustomerProfileService:
    """
    Read/update access to a CustomerAccount's own profile fields. Deriving
    the account exclusively from the caller's `CustomerPrincipal` is the
    endpoint layer's job (`get_current_customer`) -- this service only ever
    operates on the `CustomerAccount` instance it is handed. Profile updates
    touch full_name/phone only and never `CustomerAccount.lead_id`, Lead
    identity, LeadSource history, conversations, bookings, or staff
    assignments.
    """

    @staticmethod
    def _completeness(customer: CustomerAccount) -> int:
        checks = [
            bool(customer.full_name),
            customer.email_verified_at is not None,
            customer.phone is not None,
        ]
        return round(100 * sum(checks) / len(checks))

    @staticmethod
    def to_profile(customer: CustomerAccount) -> CustomerProfile:
        return CustomerProfile(
            id=customer.id,
            full_name=customer.full_name,
            email=customer.email,
            email_verified=customer.email_verified_at is not None,
            phone=customer.phone,
            phone_verified=customer.phone_verified_at is not None,
            status=customer.status,
            lead_linked=customer.lead_id is not None,
            created_at=customer.created_at,
            profile_completeness=CustomerProfileService._completeness(customer),
        )

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        customer: CustomerAccount,
        *,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> CustomerProfile:
        """
        Updates only the fields explicitly supplied (None means "not
        provided", matching this codebase's existing partial-update
        convention -- see `ProjectService.update_project`). A newly supplied
        phone number is validated/normalized but never marked verified --
        phone verification would require its own, separate workflow, which
        does not exist -- and updating it never triggers customer-to-Lead
        linking, which only ever runs once, immediately after email
        verification (`CustomerLeadLinkingService`).
        """
        if full_name is not None:
            customer.full_name = full_name.strip()
        if phone is not None:
            customer.phone = normalize_phone_optional(phone)
            customer.phone_verified_at = None

        await db.commit()
        await db.refresh(customer)
        return CustomerProfileService.to_profile(customer)
