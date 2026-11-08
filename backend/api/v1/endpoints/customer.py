from __future__ import annotations
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_customer, get_db_session
from backend.models.customer_account import CustomerAccount
from backend.schemas.customer_auth import GenericMessageResponse
from backend.schemas.customer_profile import (
    ChangePasswordRequest,
    CustomerEnquirySummary,
    CustomerProfile,
    CustomerProfileUpdateRequest,
)
from backend.services.customer_auth_service import CustomerAuthService
from backend.services.customer_enquiry_service import CustomerEnquiryService
from backend.services.customer_profile_service import CustomerProfileService

# Separate from `customer_auth.py`'s `/customer-auth` prefix -- this router
# holds the customer *portal* resources (profile, enquiry, password change)
# added in this feature, all authenticated via the same `CustomerPrincipal`
# (`get_current_customer`) but never via the cookie-based refresh/logout
# flow, so none of these need the `verify_same_origin` CSRF dependency.
router = APIRouter(prefix="/customer", tags=["Customer Portal"])


@router.get("/me", response_model=CustomerProfile, summary="Get the authenticated customer's profile")
async def get_my_profile(
    current_customer: CustomerAccount = Depends(get_current_customer),
) -> CustomerProfile:
    return CustomerProfileService.to_profile(current_customer)


@router.patch("/me", response_model=CustomerProfile, summary="Update the authenticated customer's profile")
async def update_my_profile(
    payload: CustomerProfileUpdateRequest,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerProfile:
    return await CustomerProfileService.update_profile(
        db, current_customer, full_name=payload.full_name, phone=payload.phone
    )


@router.get(
    "/me/enquiry",
    response_model=CustomerEnquirySummary,
    summary="Get a sanitized summary of the customer's own enquiry, if any",
)
async def get_my_enquiry(
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> CustomerEnquirySummary:
    return await CustomerEnquiryService.get_enquiry_summary(db, current_customer)


@router.post(
    "/me/change-password",
    response_model=GenericMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change the authenticated customer's password",
)
async def change_my_password(
    payload: ChangePasswordRequest,
    current_customer: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db_session),
) -> GenericMessageResponse:
    await CustomerAuthService.change_password(
        db,
        current_customer,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return GenericMessageResponse(message="Your password has been changed. Please sign in again.")
